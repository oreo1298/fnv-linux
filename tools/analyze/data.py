"""Data report: every referenced non-function address, classified.

Kinds: vtable, vbtable, rtti, string, import, float_constant, guard, global (plain
data), code (inside the code range but not an in-scope function: runtime/library
code, thunks, labels, inline data such as jump tables), eh_tail, unknown.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Dict

from tools.analyze.addresses import AddressMap, name_kind
from tools.common.units import fmt_addr

_DAT_RE = re.compile(r'^(DAT|g|PTR|PTR_DAT|LAB|UNK|FLOAT|DOUBLE|s|u)_[0-9a-fA-F]{6,8}')


def subkind(amap: AddressMap, info) -> str:
    syms = [amap.sym(n) for n in info.names]
    if info.kind == 'rtti':
        ks = sorted({s.kind for s in syms if s.kind.startswith('rtti_')})
        return ','.join(k[len('rtti_'):] for k in ks)
    if info.kind == 'string':
        ks = sorted({s.kind for s in syms if s.kind in ('string_literal', 'string_label')})
        return ','.join(ks)
    if info.kind == 'global':
        if not any(s.kind == 'data' for s in syms):
            return 'c-name'
        names = [s.unqualified or '' for s in syms if s.kind == 'data']
        if names and all(_DAT_RE.match(n) for n in names):
            return 'placeholder-name'
        return 'named'
    if info.kind == 'code':
        ks = {s.kind for s in syms}
        if ks & {'function', 'c_name'}:
            return 'out-of-scope-function'
        if ks == {'eh_helper'}:
            return 'eh-handler'
        if 'code_label' in ks:
            return 'label'
        if 'data' in ks:
            return 'inline-data'
        return 'other'
    if info.kind == 'import':
        return 'iat-slot' if any(s.kind == 'import' for s in syms) else 'iat-slot-c-name'
    return ''


class DataReport:
    def __init__(self, amap: AddressMap):
        self.amap = amap
        self.infos = [i for i in amap.infos.values() if i.kind != 'function']

    def summary(self) -> dict:
        kinds = Counter(i.kind for i in self.infos)
        sub = Counter('%s/%s' % (i.kind, subkind(self.amap, i)) for i in self.infos)
        data_like = [i for i in self.infos if i.kind not in ('code', 'eh_tail')]
        imports = sorted({(self.amap.sym(n).inner.c_name or self.amap.sym(n).inner.qualified or n)
                          for i in self.infos if i.kind == 'import' for n in i.names
                          if self.amap.sym(n).kind == 'import' and self.amap.sym(n).inner is not None})
        return {
            'referenced_non_function_addresses': len(self.infos),
            'by_kind': dict(kinds),
            'by_subkind': dict(sub),
            'data_addresses_outside_code_range': sum(1 for i in data_like if not i.in_code_range),
            'non_function_addresses_inside_code_range': sum(1 for i in self.infos if i.in_code_range),
            'mixed_kind_addresses': sum(1 for i in self.infos if i.mixed),
            'imported_functions': len(imports),
            'imports': imports,
        }

    def write_csv(self, path: Path, readable: Dict[str, str]):
        recipe = self.amap.recipe
        with open(path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['address', 'kind', 'subkind', 'in_code_range', 'mixed', 'canonical', 'name_count',
                        'names', 'readable', 'unit_count', 'units'])
            for i in sorted(self.infos, key=lambda x: x.address):
                units = sorted({u for us in i.names.values() for u in us})
                names = sorted(i.names)
                w.writerow([fmt_addr(i.address), i.kind, subkind(self.amap, i), int(i.in_code_range),
                            int(i.mixed), i.canonical, len(names), ';'.join(names),
                            readable.get(names[0], '') if names else '', len(units),
                            ';'.join(recipe.units[u].label for u in units)])
