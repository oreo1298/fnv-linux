"""Vtable report.

Name level (from units.json): for each vtable address, every ``??_7`` name bound
to it, the class each name belongs to, the ``{for `Base'}`` subobject, and the
units that reference it.

AST level (Clang, via tools.analyze.vtable_ast): for each class that owns one of
those vtables, every unit's own view of the class (its definition as that unit
sees it) is parsed, and its MSVC vftable layout is computed: slot count and the
slot of the virtual destructor. Views of the same vtable address that disagree
are flagged.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from tools.analyze.addresses import AddressMap
from tools.common.units import fmt_addr


def vtable_class(sym) -> Tuple[str, Optional[str]]:
    """(qualified class name, for-subobject or None) of a ??_7 / ??_S symbol."""
    comps = sym.qname.components[:-1]
    cls = '::'.join(c.text() for c in comps)
    target = sym.table_target.text() if sym.table_target is not None else None
    return cls, target


@dataclass
class VtableEntry:
    address: int
    names: Dict[str, List[int]]                      # ??_7 name -> units
    classes: Dict[Tuple[str, Optional[str]], List[str]] = field(default_factory=dict)  # (class, for) -> names
    other_names: List[str] = field(default_factory=list)
    views: List[dict] = field(default_factory=list)   # filled by the AST pass

    @property
    def units(self) -> Set[int]:
        return {u for us in self.names.values() for u in us}


class VtableReport:
    def __init__(self, amap: AddressMap, upstream: Path, jobs=0, sample=0, log=None, ast=True):
        self.amap = amap
        self.upstream = Path(upstream)
        self.entries: Dict[int, VtableEntry] = {}
        self.log = log or (lambda m: None)
        for a, info in amap.infos.items():
            vt_names = {n: us for n, us in info.names.items() if amap.sym(n).kind in ('vftable', 'local_vftable')}
            if not vt_names:
                continue
            e = VtableEntry(a, vt_names)
            for n in vt_names:
                e.classes.setdefault(vtable_class(amap.sym(n)), []).append(n)
            e.other_names = sorted(n for n in info.names if n not in vt_names)
            self.entries[a] = e
        self.ast_stats = None
        if ast:
            from tools.analyze import vtable_ast
            self.ast_stats = vtable_ast.collect(self, jobs=jobs, sample=sample, log=self.log)

    # -- summaries ---------------------------------------------------------------
    def summary(self) -> dict:
        es = list(self.entries.values())
        multi_class = [e for e in es if len({c for c, _ in e.classes}) > 1]
        secondary = [e for e in es if any(t is not None for _, t in e.classes)]
        s = {
            'vtable_addresses': len(es),
            'distinct_vtable_names': len({n for e in es for n in e.names}),
            'address_name_pairs': sum(len(e.names) for e in es),
            'addresses_with_several_names': sum(1 for e in es if len(e.names) > 1),
            'addresses_with_several_class_names': len(multi_class),
            'max_class_names_per_address': max((len({c for c, _ in e.classes}) for e in es), default=0),
            'secondary_subobject_vtables': len(secondary),
            'addresses_also_referenced_as_other_symbols': sum(1 for e in es if e.other_names),
            'vtable_names_bound_to_several_addresses': sum(
                1 for n, a in self.amap.colliding_names().items() if n.startswith('??_7')),
            'referencing_units': len({u for e in es for u in e.units}),
            'units_per_address': dict(Counter(min(len(e.units), 10) for e in es)),
        }
        if self.ast_stats is not None:
            s['ast'] = self.ast_stats
        return s

    def write(self, out: Path, readable: Dict[str, str]):
        recipe = self.amap.recipe
        with open(out / 'vtables.csv', 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['address', 'class', 'for_subobject', 'name', 'unit_count', 'units', 'other_names'])
            for a, e in sorted(self.entries.items()):
                for (cls, target), names in sorted(e.classes.items(), key=lambda kv: (kv[0][0], kv[0][1] or '')):
                    for n in names:
                        us = e.names[n]
                        w.writerow([fmt_addr(a), cls, target or '', n, len(us),
                                    ';'.join(recipe.units[u].label for u in us), ';'.join(e.other_names)])
        if self.ast_stats is not None:
            from tools.analyze import vtable_ast
            vtable_ast.write(self, out)
