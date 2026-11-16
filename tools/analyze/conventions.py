"""Calling-convention mismatch report.

For every function address, the defining decorated name is compared with every
other name bound to that address. Each (definition, reference name) pair gets
one class:

  name-only          same convention, same member/free kind, same parameters: harmless
  thiscall-fastcall  one side __thiscall, the other __fastcall: the MSVC idiom of defining
                     a member as a free __fastcall function (arg 1 in ECX, dummy EDX);
                     fine under MSVC, breaks on Linux where this goes on the stack
  member-free        member on one side, free/static function on the other, same convention
  cc-conflict        any other convention difference
  params-differ      same convention and kind, but parameters or return type differ
  function-as-data   the address is also referenced as a data symbol
  other-kind         referenced under a name that is neither function nor data
  malformed          the reference name does not demangle

Each pair also gets msvc_equivalent / linux_equivalent (yes/no/unknown) from
tools.analyze.abi, i.e. whether a call through the reference's declaration
reaches the definition with the same registers, stack and cleanup.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.analyze.abi import equivalent, layout_of
from tools.analyze.addresses import AddressMap
from tools.common.msvc_demangle import Symbol
from tools.common.source_index import SourceIndex, identifier_for
from tools.common.units import fmt_addr

CLASSES = ['cc-conflict', 'thiscall-fastcall', 'member-free', 'function-as-data', 'params-differ',
           'other-kind', 'malformed', 'name-only']   # severity order, worst first


def _is_func(s: Symbol) -> bool:
    return s.kind in ('function', 'c_name')


def _param_diff(d: Symbol, r: Symbol) -> str:
    """'' when parameters and return type are the same; else count / abi / types / ret."""
    if d.kind == 'c_name' or r.kind == 'c_name':
        ld, lr = layout_of(d, 'msvc'), layout_of(r, 'msvc')
        if ld and lr and ld.stack_bytes is not None and lr.stack_bytes is not None \
                and ld.stack_bytes != lr.stack_bytes:
            return 'count'
        return ''
    pd, pr = d.params, r.params
    if pd is None or pr is None:
        return ''
    if len(pd) != len(pr) or d.variadic != r.variadic:
        return 'count'
    if pd != pr:
        return 'abi' if equivalent(d, r, 'msvc') == 'no' else 'types'
    if d.ret != r.ret:
        return 'ret-abi' if equivalent(d, r, 'msvc') == 'no' else 'ret'
    return ''


def classify_pair(d: Symbol, r: Symbol) -> Tuple[str, str]:
    """Class and detail for definition d vs reference r (both demangled)."""
    if r.kind == 'unknown':
        return 'malformed', r.extra.get('error', '')
    if r.kind == 'data':
        return 'function-as-data', ''
    if not _is_func(r):
        return 'other-kind', r.kind
    if not _is_func(d):
        return 'other-kind', 'definition is ' + d.kind
    dm, rm = d.is_member, r.is_member
    dcc, rcc = d.cc or 'cdecl', r.cc or 'cdecl'
    if d.variadic:
        dcc = 'cdecl'
    if r.variadic:
        rcc = 'cdecl'
    detail = _param_diff(d, r)
    if {dcc, rcc} == {'thiscall', 'fastcall'}:
        return 'thiscall-fastcall', detail
    if dm != rm:
        if dcc == rcc:
            return 'member-free', detail
        return 'cc-conflict', '%s %s vs %s %s' % ('member' if dm else 'free', dcc, 'member' if rm else 'free', rcc)
    if dcc != rcc:
        return 'cc-conflict', '%s vs %s' % (dcc, rcc)
    if detail:
        return 'params-differ', detail
    return 'name-only', ''


@dataclass
class PairRow:
    address: int
    cls: str
    detail: str
    msvc_eq: str
    linux_eq: str
    def_symbol: str
    def_unit: int
    ref_symbol: str
    ref_units: List[int]


class ConventionReport:
    def __init__(self, amap: AddressMap):
        self.amap = amap
        self.rows: List[PairRow] = []
        self.address_classes: Dict[int, set] = defaultdict(set)
        self.pair_cache: Dict[Tuple[str, str], Tuple[str, str, str, str]] = {}
        self.unreferenced = 0           # function addresses no unit references by relocation
        self.def_conflicts: List[Tuple[int, str, str]] = []
        self._build()

    def _classify(self, dname, rname):
        key = (dname, rname)
        hit = self.pair_cache.get(key)
        if hit is None:
            d, r = self.amap.sym(dname), self.amap.sym(rname)
            cls, detail = classify_pair(d, r)
            both = _is_func(d) and _is_func(r)
            msvc = equivalent(d, r, 'msvc') if both else 'n/a'
            linux = equivalent(d, r, 'linux') if both else 'n/a'
            hit = self.pair_cache[key] = (cls, detail, msvc, linux)
        return hit

    def _build(self):
        recipe = self.amap.recipe
        for a, info in self.amap.infos.items():
            if info.kind != 'function':
                continue
            defs = info.definitions
            def_name, def_unit = defs[0]
            def_names = {n for n, _ in defs}
            # Two variant units defining one address under different names.
            for n, u in defs[1:]:
                if n != def_name:
                    cls, detail, msvc, linux = self._classify(def_name, n)
                    self.def_conflicts.append((a, n, cls))
            refs = {n: us for n, us in info.names.items() if us}
            if not refs:
                self.unreferenced += 1
            for n, us in sorted(info.names.items()):
                if n in def_names:
                    continue
                cls, detail, msvc, linux = self._classify(def_name, n)
                self.address_classes[a].add(cls)
                self.rows.append(PairRow(a, cls, detail, msvc, linux, def_name, def_unit, n, us))

    # -- summaries ---------------------------------------------------------------
    def worst_class(self, a) -> str:
        cs = self.address_classes.get(a)
        if not cs:
            return 'identical'
        for c in CLASSES:
            if c in cs:
                return c
        return 'identical'

    def summary(self) -> dict:
        fn_addrs = [a for a, i in self.amap.infos.items() if i.kind == 'function']
        exclusive = Counter(self.worst_class(a) for a in fn_addrs)
        inclusive = Counter(c for cs in self.address_classes.values() for c in cs)
        pairs = Counter(r.cls for r in self.rows)
        eq = defaultdict(Counter)
        for r in self.rows:
            eq[r.cls]['msvc:' + r.msvc_eq] += 1
            eq[r.cls]['linux:' + r.linux_eq] += 1
        from tools.analyze.abi import worst
        addr_eq = defaultdict(Counter)
        by_addr = self.rows_by_address()
        for a in fn_addrs:
            rows = by_addr.get(a)
            if not rows:
                continue
            m = l = 'yes'
            for r in rows:
                if r.cls in ('function-as-data', 'other-kind', 'malformed'):
                    continue
                m, l = worst(m, r.msvc_eq), worst(l, r.linux_eq)
            addr_eq[self.worst_class(a)]['msvc:' + m] += 1
            addr_eq[self.worst_class(a)]['linux:' + l] += 1
        linux_total = Counter()
        for k, v in addr_eq.items():
            for kk, n in v.items():
                if kk.startswith('linux:'):
                    linux_total[kk[6:]] += n
        details = defaultdict(Counter)
        for r in self.rows:
            details[r.cls][r.detail or '-'] += 1
        only_other = sum(1 for a in fn_addrs
                         if self.amap.infos[a].names and
                         not any(us for n, us in self.amap.infos[a].names.items()
                                 if n in {d for d, _ in self.amap.infos[a].definitions}) and
                         any(us for us in self.amap.infos[a].names.values()))
        return {
            'function_addresses': len(fn_addrs),
            'unreferenced_function_addresses': self.unreferenced,
            'referenced_only_under_other_names': only_other,
            'addresses_with_other_names': len(self.address_classes),
            'exclusive_worst_class': dict(exclusive),
            'inclusive_class': dict(inclusive),
            'pairs_by_class': dict(pairs),
            'pair_equivalence': {k: dict(v) for k, v in eq.items()},
            'address_equivalence': {k: dict(v) for k, v in addr_eq.items()},
            'address_linux_verdicts': dict(linux_total),
            'details': {k: dict(v.most_common(12)) for k, v in details.items()},
            'variant_definition_conflicts': len(self.def_conflicts),
        }

    _rows_by_address = None

    def rows_by_address(self):
        if self._rows_by_address is None:
            m = defaultdict(list)
            for r in self.rows:
                m[r.address].append(r)
            self._rows_by_address = m
        return self._rows_by_address

    # -- CSV ---------------------------------------------------------------------
    def write_csv(self, path: Path, index: Optional[SourceIndex], readable: Dict[str, str],
                  include_name_only=True):
        """One row per (address, reference name, referencing unit), with source locations."""
        recipe = self.amap.recipe
        tag_locs = index.all_tags(u.source for u in recipe.units) if index else {}
        per_unit: Dict[int, List[Tuple[PairRow, int]]] = defaultdict(list)
        for r in self.rows:
            if not include_name_only and r.cls == 'name-only':
                continue
            for u in r.ref_units:
                per_unit[u].append((r, u))
        out_rows = []
        for u, items in per_unit.items():
            info = index.scan(recipe.units[u].source) if index else None
            for r, _ in items:
                ident = identifier_for(self.amap.sym(r.ref_symbol))
                loc = index.locate(info, ident) if index else None
                site = index.use_site(info, ident) if index else None
                out_rows.append((r, u, loc, site))
        out_rows.sort(key=lambda t: (CLASSES.index(t[0].cls), t[0].address, t[0].ref_symbol, t[1]))
        with open(path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['address', 'class', 'detail', 'msvc_equivalent', 'linux_equivalent',
                        'def_symbol', 'def_readable', 'def_unit', 'def_location',
                        'ref_symbol', 'ref_readable', 'ref_unit', 'ref_location', 'ref_site'])
            for r, u, loc, site in out_rows:
                dl = tag_locs.get(r.address)
                w.writerow([fmt_addr(r.address), r.cls, r.detail, r.msvc_eq, r.linux_eq,
                            r.def_symbol, readable.get(r.def_symbol, ''), recipe.units[r.def_unit].label,
                            '%s:%d' % dl[0] if dl else '',
                            r.ref_symbol, readable.get(r.ref_symbol, ''), recipe.units[u].label,
                            '%s:%d' % loc if loc else '',
                            '%s@%d' % (fmt_addr(site[1]), site[0]) if site else ''])
        return len(out_rows)
