"""AST pass of the vtable report: per-unit MSVC vftable layouts of the classes that own vtables.

For every unit that references a ``??_7`` name, the unit is parsed with libclang (same flags
and header shim as tools.compile_probe, function bodies skipped), the class each vtable
name belongs to is looked up in that unit's own view, and the MSVC vftable layout of that
class is computed from the view:

* the primary base is the first non-virtual base that has a vfptr; its vftable is extended
  with the class's new virtual methods;
* new virtual methods are grouped by name in the order of each name's first declaration in
  the class, and within a group in reverse declaration order (MSVC's overload quirk);
* a method overrides a base slot with the same name and parameter types; a virtual
  destructor takes one slot (the deleting destructor);
* a ``{for `B'}`` vftable is B's table as overridden by the class.

Each view gives (slot count, destructor slot, slot names). Views of the same vtable address
that differ in slot count or destructor slot are flagged. Virtual bases are not modelled;
such views are marked.

libclang comes from the system (Ubuntu python3-clang-N, Arch clang); it is imported lazily.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_CI = None


def cindex():
    """Import clang.cindex, searching the usual system locations."""
    global _CI
    if _CI is not None:
        return _CI
    try:
        import clang.cindex as ci
    except ImportError:
        import glob
        for p in sorted(glob.glob('/usr/lib/python3*/dist-packages')) + sorted(glob.glob('/usr/lib/python3*/site-packages')):
            if os.path.isdir(os.path.join(p, 'clang')) and p not in sys.path:
                sys.path.append(p)
        import clang.cindex as ci
    if not ci.Config.loaded:
        import glob
        for pat in ['/usr/lib/llvm-*/lib/libclang.so', '/usr/lib/x86_64-linux-gnu/libclang-*.so',
                    '/usr/lib/libclang.so']:
            hits = sorted(glob.glob(pat))
            if hits:
                ci.Config.set_library_file(hits[-1])
                break
    _CI = ci
    return ci


_RESOURCE_DIR = None


def _resource_dir():
    """Clang's resource directory (libclang needs it passed explicitly)."""
    global _RESOURCE_DIR
    if _RESOURCE_DIR is None:
        import subprocess
        try:
            _RESOURCE_DIR = subprocess.run(['clang', '-print-resource-dir'], capture_output=True,
                                           text=True).stdout.strip()
        except OSError:
            _RESOURCE_DIR = ''
    return _RESOURCE_DIR


def parse_args_for(unit: dict, upstream: Path) -> List[str]:
    """The compile probe's flags for one unit, for libclang."""
    from tools.compile_probe.__main__ import BASE_FLAGS, DEFAULT_STD, SHIM, translate_flags
    src = upstream / unit['source']
    is_c = src.suffix == '.c'
    args = list(BASE_FLAGS) + ['-x', 'c' if is_c else 'c++']
    if not is_c:
        args.append('-std=' + DEFAULT_STD)
    args += ['-include', str(SHIM / 'fnv_prelude.h'), '-isystem', str(SHIM), '-I', str(upstream / 'include')]
    args += translate_flags(unit['flags'], is_c)
    if _resource_dir():
        args += ['-resource-dir', _resource_dir()]
    return args


# ---------------------------------------------------------------------------
# Class views

def qualified_name(cur) -> str:
    ci = cindex()
    parts = []
    c = cur
    while c is not None and c.kind != ci.CursorKind.TRANSLATION_UNIT:
        k = c.kind
        if k == ci.CursorKind.NAMESPACE:
            parts.append(c.spelling or "`anonymous namespace'")
        elif k in (ci.CursorKind.CLASS_DECL, ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL,
                   ci.CursorKind.CLASS_TEMPLATE, ci.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION):
            parts.append(c.spelling)
        elif k in (ci.CursorKind.FUNCTION_DECL, ci.CursorKind.CXX_METHOD):
            parts.append(c.spelling)   # local class; MSVC names these differently
        c = c.semantic_parent
    return '::'.join(reversed(parts))


def strip_template_args(name: str) -> str:
    """'A<int, B<x>>::C<y>' -> 'A::C'."""
    out, depth = [], 0
    for ch in name:
        if ch == '<':
            depth += 1
        elif ch == '>':
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return ''.join(out)


def index_classes(tu) -> Dict[str, list]:
    """qualified name (template args stripped) -> class definition cursors in the TU."""
    ci = cindex()
    K = ci.CursorKind
    result = defaultdict(list)
    containers = {K.NAMESPACE, K.LINKAGE_SPEC, K.UNEXPOSED_DECL, K.CLASS_DECL, K.STRUCT_DECL,
                  K.CLASS_TEMPLATE, K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION}
    records = {K.CLASS_DECL, K.STRUCT_DECL, K.CLASS_TEMPLATE, K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION}
    stack = list(tu.cursor.get_children())
    while stack:
        c = stack.pop()
        k = c.kind
        if k in records and c.is_definition():
            result[strip_template_args(qualified_name(c))].append(c)
        if k in containers:
            stack.extend(c.get_children())
    return result


class Slot:
    __slots__ = ('name', 'key', 'owner', 'is_dtor', 'pure')

    def __init__(self, name, key, owner, is_dtor, pure):
        self.name, self.key, self.owner, self.is_dtor, self.pure = name, key, owner, is_dtor, pure


class LayoutError(Exception):
    pass


def _method_key(m) -> Tuple[str, Tuple[str, ...]]:
    ci = cindex()
    if m.kind == ci.CursorKind.DESTRUCTOR:
        return ('~', ())
    params = tuple(a.type.get_canonical().spelling for a in m.get_arguments())
    return (m.spelling, params)


def _bases(c) -> List[Tuple[object, bool]]:
    ci = cindex()
    out = []
    for ch in c.get_children():
        if ch.kind == ci.CursorKind.CXX_BASE_SPECIFIER:
            decl = ch.type.get_declaration()
            d = decl.get_definition() if decl is not None else None
            if d is not None and not any(True for _ in d.get_children()):
                d = None   # an implicit template instantiation: libclang shows no members
            if d is None:
                # Template base: use the template's pattern.
                for gc in ch.get_children():
                    if gc.kind in (ci.CursorKind.TEMPLATE_REF, ci.CursorKind.TYPE_REF):
                        r = gc.referenced
                        d = r.get_definition() if r is not None else None
                        if d is not None:
                            break
            is_virtual = bool(ci.conf.lib.clang_isVirtualBase(ch))
            out.append((d, is_virtual, ch.type.spelling))
    return out


def vftables(c, depth=0) -> List[Tuple[Tuple[str, ...], List[Slot]]]:
    """MSVC vftables of class definition c: [(subobject path, slots)], primary first."""
    ci = cindex()
    if depth > 40:
        raise LayoutError('inheritance too deep')
    tables: List[Tuple[Tuple[str, ...], List[Slot]]] = []
    for d, is_virtual, spelling in _bases(c):
        if d is None:
            raise LayoutError('incomplete base ' + spelling)
        if is_virtual:
            raise LayoutError('virtual base ' + spelling)
        for path, slots in vftables(d, depth + 1):
            tables.append(((strip_template_args(qualified_name(d)),) + path,
                           [Slot(s.name, s.key, s.owner, s.is_dtor, s.pure) for s in slots]))
    methods = [ch for ch in c.get_children()
               if ch.kind in (ci.CursorKind.CXX_METHOD, ci.CursorKind.DESTRUCTOR,
                              ci.CursorKind.FUNCTION_TEMPLATE)]
    def group_key(ch):
        return '~' if ch.kind == ci.CursorKind.DESTRUCTOR else ch.spelling

    first_decl_order: Dict[str, int] = {}
    for i, ch in enumerate(c.get_children()):
        nm = group_key(ch)
        if nm and nm not in first_decl_order:
            first_decl_order[nm] = i
    owner = strip_template_args(qualified_name(c))
    # Every class has a destructor (implicit if not declared); it overrides a virtual one in a base.
    for _, slots in tables:
        for s in slots:
            if s.is_dtor:
                s.owner, s.name = owner, '~' + c.spelling
    new_virtuals = []
    for m in methods:
        key = _method_key(m)
        is_dtor = m.kind == ci.CursorKind.DESTRUCTOR
        overrides = False
        for _, slots in tables:
            for s in slots:
                if s.key == key or (is_dtor and s.is_dtor):
                    s.owner, s.name = owner, m.spelling
                    overrides = True
        if overrides:
            continue
        if m.kind != ci.CursorKind.FUNCTION_TEMPLATE and m.is_virtual_method():
            new_virtuals.append(m)
    if new_virtuals:
        groups: Dict[str, list] = defaultdict(list)
        for m in new_virtuals:
            groups[group_key(m)].append(m)
        order = sorted(groups, key=lambda n: first_decl_order.get(n, 1 << 30))
        new_slots = []
        for n in order:
            for m in reversed(groups[n]):
                is_dtor = m.kind == ci.CursorKind.DESTRUCTOR
                new_slots.append(Slot(m.spelling, _method_key(m), owner, is_dtor, m.is_pure_virtual_method()))
        if tables:
            tables[0][1].extend(new_slots)
        else:
            tables.append(((), new_slots))
    return tables


def view_layout(c, for_target: Optional[str]) -> dict:
    """Layout of the vftable named by (class c, {for target})."""
    try:
        tables = vftables(c)
    except LayoutError as e:
        return {'status': 'unsupported', 'reason': str(e)}
    except Exception as e:  # libclang can surface odd cursors on broken code
        return {'status': 'error', 'reason': '%s: %s' % (type(e).__name__, e)}
    if not tables:
        return {'status': 'no-vftable'}
    table = None
    if for_target is None:
        table = tables[0]
    else:
        want = strip_template_args(for_target)
        for path, slots in tables:
            if path and (path[-1] == want or path[0] == want or path[-1].endswith('::' + want)):
                table = (path, slots)
                break
        if table is None:
            for path, slots in tables:
                if want in path:
                    table = (path, slots)
                    break
        if table is None:
            return {'status': 'no-subobject', 'reason': 'no vftable for ' + for_target}
    path, slots = table
    dtor = [i for i, s in enumerate(slots) if s.is_dtor]
    return {'status': 'ok', 'slots': len(slots), 'dtor_slot': dtor[0] if dtor else None,
            'slot_names': [s.name for s in slots], 'tables': len(tables)}


def analyze_unit(job) -> dict:
    """Worker: parse one unit and compute layouts for its vtable classes."""
    unit, upstream, wanted = job
    ci = cindex()
    upstream = Path(upstream)
    index = ci.Index.create()
    opts = ci.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES | ci.TranslationUnit.PARSE_INCOMPLETE
    try:
        tu = index.parse(str(upstream / unit['source']), args=parse_args_for(unit, upstream), options=opts)
    except ci.TranslationUnitLoadError as e:
        return {'unit': unit['_index'], 'error': 'parse failed: %s' % e, 'views': []}
    errors = sum(1 for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error)
    classes = index_classes(tu)
    views = []
    for (cls, target, name) in wanted:
        key = strip_template_args(cls)
        defs = classes.get(key)
        if not defs:
            # MSVC qualifies local/anonymous classes differently; fall back to the last component.
            short = key.split('::')[-1]
            cands = [d for k, ds in classes.items() if k.split('::')[-1] == short for d in ds]
            defs = cands if len(cands) == 1 else None
        if not defs:
            views.append({'name': name, 'class': cls, 'for': target, 'status': 'class-not-found'})
            continue
        d = defs[0]
        lay = view_layout(d, target)
        loc = d.location
        lay.update({'name': name, 'class': cls, 'for': target,
                    'defined_at': '%s:%d' % (Path(str(loc.file)).resolve().relative_to(upstream.resolve())
                                             if loc.file and str(loc.file).startswith(str(upstream)) else
                                             (loc.file.name if loc.file else '?'), loc.line),
                    'definitions_in_unit': len(defs)})
        views.append(lay)
    return {'unit': unit['_index'], 'errors': errors, 'views': views}


# ---------------------------------------------------------------------------
# Driver (called from tools.analyze.vtables)

def collect(report, jobs=0, sample=0, log=None):
    log = log or (lambda m: None)
    try:
        cindex()
    except Exception as e:  # pragma: no cover - environment dependent
        log('libclang unavailable (%s); skipping the AST pass' % e)
        return {'skipped': 'libclang unavailable: %s' % e}
    recipe = report.amap.recipe
    from tools.analyze.vtables import vtable_class
    per_unit: Dict[int, List[Tuple[str, Optional[str], str]]] = defaultdict(list)
    for a, e in report.entries.items():
        for n, us in e.names.items():
            cls, target = vtable_class(report.amap.sym(n))
            for u in us:
                per_unit[u].append((cls, target, n))
    units = sorted(per_unit)
    sampled = False
    if sample and sample < len(units):
        step = len(units) / float(sample)
        units = [units[int(i * step)] for i in range(sample)]
        sampled = True
    raw = json.loads((report.upstream / 'build' / 'units.json').read_text())['units']
    jobsl = []
    for u in units:
        d = dict(raw[u])
        d['_index'] = u
        jobsl.append((d, str(report.upstream), per_unit[u]))
    log('vtable AST pass over %d units%s' % (len(jobsl), ' (sample)' if sampled else ''))
    results = []
    workers = jobs or max(1, (os.cpu_count() or 2))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(analyze_unit, j) for j in jobsl]
        for i, f in enumerate(as_completed(futs), 1):
            try:
                results.append(f.result())
            except Exception as e:  # a crashed worker
                results.append({'unit': -1, 'error': repr(e), 'views': []})
            if i % 50 == 0:
                log('  %d/%d units' % (i, len(futs)))
    report.ast_results = results
    # Attach views to vtable entries.
    name_to_addr = {}
    for a, e in report.entries.items():
        for n in e.names:
            name_to_addr.setdefault(n, set()).add(a)
    for r in results:
        for v in r.get('views', []):
            v['unit'] = r['unit']
            for a in name_to_addr.get(v['name'], ()):
                if r['unit'] in report.entries[a].names.get(v['name'], ()):
                    report.entries[a].views.append(v)
    return summarize(report, len(jobsl), sampled)


def summarize(report, n_units, sampled) -> dict:
    status = Counter()
    conflicts_slots = conflicts_dtor = analysed = 0
    multi_view = 0
    for a, e in report.entries.items():
        ok = [v for v in e.views if v.get('status') == 'ok']
        for v in e.views:
            status[v.get('status')] += 1
        if not ok:
            continue
        analysed += 1
        if len(ok) > 1:
            multi_view += 1
        e.slot_counts = sorted({v['slots'] for v in ok})
        e.dtor_slots = sorted({-1 if v['dtor_slot'] is None else v['dtor_slot'] for v in ok})
        if len(e.slot_counts) > 1:
            conflicts_slots += 1
        if len(e.dtor_slots) > 1:
            conflicts_dtor += 1
    either = sum(1 for e in report.entries.values()
                 if len(getattr(e, 'slot_counts', [])) > 1 or len(getattr(e, 'dtor_slots', [])) > 1)
    return {
        'units_parsed': n_units, 'sampled': sampled,
        'view_status': dict(status),
        'addresses_with_layout': analysed,
        'addresses_with_several_layouts': multi_view,
        'slot_count_conflicts': conflicts_slots,
        'dtor_position_conflicts': conflicts_dtor,
        'addresses_with_any_conflict': either,
        'units_with_parse_errors': sum(1 for r in report.ast_results if r.get('errors')),
    }


def write(report, out: Path):
    recipe = report.amap.recipe
    from tools.common.units import fmt_addr
    with open(out / 'vtable_views.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['address', 'conflict', 'name', 'class', 'for_subobject', 'unit', 'status', 'slots',
                    'dtor_slot', 'defined_at', 'reason', 'slot_names'])
        for a, e in sorted(report.entries.items()):
            conflict = []
            if len(getattr(e, 'slot_counts', [])) > 1:
                conflict.append('slots')
            if len(getattr(e, 'dtor_slots', [])) > 1:
                conflict.append('dtor')
            for v in sorted(e.views, key=lambda v: (v['name'], v['unit'])):
                w.writerow([fmt_addr(a), '+'.join(conflict), v['name'], v['class'], v.get('for') or '',
                            recipe.units[v['unit']].label, v.get('status'), v.get('slots', ''),
                            '' if v.get('dtor_slot') is None else v['dtor_slot'], v.get('defined_at', ''),
                            v.get('reason', ''), ' '.join(v.get('slot_names', []))])
