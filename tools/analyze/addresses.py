"""Address classification and the alias map.

Every original address that units.json mentions is classified, and every
decorated name bound to it is collected with the units that use it. The alias
map is emitted as JSON/CSV and as GNU ld script fragments that later phases
link with:

* canonical symbols ``fnv.f.XXXXXXXX`` (function defined at original address
  0xXXXXXXXX) and ``fnv.d.XXXXXXXX`` (data at original address 0xXXXXXXXX);
  they are mangling-independent, so Phase 3 transforms can attach them to
  declarations with asm labels;
* ``data.ld``: ``fnv.d.X = 0xX;`` absolute definitions of every data address;
* ``aliases.ld``: every MSVC decorated name -> its canonical symbol, for a link
  that keeps MSVC names. Names bound to more than one address are left out
  (they need per-unit renaming) and listed in the report.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set

from tools.common.msvc_demangle import Symbol, try_demangle
from tools.common.units import Recipe, fmt_addr

IMAGE_BASE = 0x400000


def densest_cluster(addrs, gap=0x40):
    """[lo, hi) of the largest run of addresses with gaps <= gap. Used for the import address
    table: a few __imp_ names are bound to ordinary data (function pointers declared as imports)."""
    addrs = sorted(set(addrs))
    if not addrs:
        return (0, 0)
    best, start = (0, 0, 0), 0
    for i in range(1, len(addrs) + 1):
        if i == len(addrs) or addrs[i] - addrs[i - 1] > gap:
            if i - start > best[0]:
                best = (i - start, addrs[start], addrs[i - 1] + 4)
            start = i
    return best[1], best[2]

# Name kinds, from the demangled symbol.
DATA_KIND_PRIORITY = ['vtable', 'vbtable', 'rtti', 'string', 'import', 'float_constant', 'guard', 'global']


def name_kind(sym: Symbol) -> str:
    k = sym.kind
    if k in ('vftable', 'local_vftable'):
        return 'vtable'
    if k == 'vbtable':
        return 'vbtable'
    if k.startswith('rtti_'):
        return 'rtti'
    if k in ('string_literal', 'string_label'):
        return 'string'
    if k == 'import':
        return 'import'
    if k == 'float_constant':
        return 'float_constant'
    if k == 'local_static_guard':
        return 'guard'
    if k == 'data':
        return 'global'
    if k in ('function', 'c_name', 'eh_helper', 'vcall_thunk'):
        return 'code_name'
    if k == 'code_label':
        return 'label'
    return 'unknown'


@dataclass
class AddressInfo:
    address: int
    kind: str                          # function, eh_tail, code, vtable, vbtable, rtti, string, import,
                                       # float_constant, guard, global, unknown
    in_code_range: bool
    definitions: List[tuple] = field(default_factory=list)       # [(symbol, unit index)]
    names: Dict[str, List[int]] = field(default_factory=dict)    # name -> unit indices referencing it
    name_kinds: Counter = field(default_factory=Counter)
    mixed: bool = False                # names disagree on the data kind

    @property
    def canonical(self) -> str:
        prefix = 'f' if self.kind == 'function' else ('t' if self.kind == 'eh_tail' else
                                                     ('c' if self.kind == 'code' else 'd'))
        return 'fnv.%s.%08x' % (prefix, self.address)

    @property
    def is_data(self) -> bool:
        return self.kind not in ('function', 'eh_tail', 'code', 'absolute')


class AddressMap:
    def __init__(self, recipe: Recipe):
        self.recipe = recipe
        self.symbols: Dict[str, Symbol] = {}
        self.infos: Dict[int, AddressInfo] = {}
        lo, hi = recipe.code_range()
        self.code_lo, self.code_hi = lo, hi
        imp = [a for n, aset in recipe.name_addresses.items() if n.startswith('__imp_') for a in aset]
        self.iat = densest_cluster(imp)
        addrs: Set[int] = set(recipe.function_addresses) | set(recipe.references)
        for a in sorted(addrs):
            names: Dict[str, List[int]] = defaultdict(list)
            for ui, n in recipe.references.get(a, ()):
                names[n].append(ui)
            defs = [(n, f.unit) for f in recipe.definitions.get(a, ()) for n in f.names]
            for n, _ in defs:
                names.setdefault(n, [])
            kinds = Counter(name_kind(self.sym(n)) for n in names)
            in_code = lo <= a < hi
            if a in recipe.function_addresses:
                kind = 'function'
            elif a in recipe.eh_tails:
                kind = 'eh_tail'
            elif a < IMAGE_BASE:
                kind = 'absolute'     # e.g. __tls_array (fs:[0x2c])
            elif self.iat[0] <= a < self.iat[1]:
                kind = 'import'       # IAT slot, sometimes named without __imp_
            else:
                data_kinds = [k for k in DATA_KIND_PRIORITY if kinds.get(k)]
                if data_kinds:
                    kind = data_kinds[0]
                elif in_code:
                    kind = 'code'
                elif kinds.get('code_name') or kinds.get('label'):
                    kind = 'global'   # C-decorated data, or locals of extern "C" functions
                else:
                    kind = 'unknown'
            info = AddressInfo(a, kind, in_code, defs, {n: sorted(set(u)) for n, u in names.items()}, kinds)
            info.mixed = len([k for k in DATA_KIND_PRIORITY if kinds.get(k)]) > 1
            self.infos[a] = info

    def sym(self, name: str) -> Symbol:
        s = self.symbols.get(name)
        if s is None:
            s = self.symbols[name] = try_demangle(name)
        return s

    def colliding_names(self) -> Dict[str, Set[int]]:
        """Names bound to more than one address across units."""
        return {n: a for n, a in self.recipe.name_addresses.items() if len(a) > 1}

    def kind_counts(self) -> Counter:
        return Counter(i.kind for i in self.infos.values())


# ---------------------------------------------------------------------------
# Writers

def write_alias_map(amap: AddressMap, out: Path, readable: Dict[str, str]):
    out.mkdir(parents=True, exist_ok=True)
    recipe = amap.recipe
    collisions = amap.colliding_names()

    # JSON: address -> entry
    doc = {}
    for a, info in amap.infos.items():
        doc[fmt_addr(a)] = {
            'kind': info.kind,
            'canonical': info.canonical,
            'in_code_range': info.in_code_range,
            'definitions': [{'symbol': n, 'unit': recipe.units[u].label} for n, u in info.definitions],
            'names': {n: [recipe.units[u].label for u in us] for n, us in sorted(info.names.items())},
        }
    with open(out / 'aliases.json', 'w', encoding='utf-8') as fh:
        json.dump({'note': 'Generated by tools/analyze. Every original address units.json mentions, '
                           'with its definition(s) and every decorated name bound to it.',
                   'addresses': doc}, fh, indent=1)

    with open(out / 'aliases.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['address', 'kind', 'canonical', 'name', 'is_definition', 'name_bound_elsewhere',
                    'unit_count', 'units', 'readable'])
        for a, info in amap.infos.items():
            def_names = {n for n, _ in info.definitions}
            for n, us in sorted(info.names.items()):
                w.writerow([fmt_addr(a), info.kind, info.canonical, n, int(n in def_names),
                            int(n in collisions), len(us), ';'.join(recipe.units[u].label for u in us),
                            readable.get(n, '')])

    header = ('/* Generated by tools/analyze from fnv_decomp build/units.json. Do not edit.\n'
              '   Canonical symbols: fnv.f.<addr> function, fnv.t.<addr> EH tail, fnv.c.<addr> other code,\n'
              '   fnv.d.<addr> data at its original virtual address. */\n')
    with open(out / 'data.ld', 'w', encoding='utf-8') as fh:
        fh.write(header)
        fh.write('/* Data symbols at their original virtual addresses. */\n')
        for a, info in amap.infos.items():
            if info.is_data:
                fh.write('%s = 0x%08x;\n' % (info.canonical, a))
    skipped = 0
    with open(out / 'aliases.ld', 'w', encoding='utf-8') as fh:
        fh.write(header)
        fh.write('/* Every decorated name -> canonical symbol, as PROVIDE so that a definition in an\n'
                 '   object always wins. A function canonical falls back to its definition name, so\n'
                 '   this works whether objects define fnv.f.<addr> (asm labels) or MSVC names.\n'
                 '   Data canonicals are defined by data.ld. */\n')
        for a, info in amap.infos.items():
            def_names = [n for n, _ in info.definitions if n not in collisions]
            if info.kind == 'function' and def_names:
                fh.write('PROVIDE(%s = "%s");\n' % (info.canonical, def_names[0]))
            for n in sorted(info.names):
                if n in collisions or '"' in n or '\n' in n:
                    skipped += 1
                    continue
                if info.kind == 'function' and def_names and n == def_names[0]:
                    continue
                fh.write('PROVIDE("%s" = %s);\n' % (n, info.canonical))
        fh.write('/* %d names bound to more than one address were left out; see aliases.csv. */\n' % skipped)
    return skipped
