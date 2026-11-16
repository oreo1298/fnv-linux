"""Model of fnv_decomp's build recipe, build/units.json.

Linking in fnv_decomp is by original address, not by name: every unit lists in
``symbols`` the decorated names it uses (defines or references) and the
original address each one stands for. This module loads the recipe and builds
the address-keyed views the analyses need.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = ['Function', 'Unit', 'Recipe', 'load_recipe', 'fmt_addr']


def fmt_addr(a: int) -> str:
    return '0x%08x' % a


def _num(v) -> int:
    return int(v, 0) if isinstance(v, str) else int(v)


@dataclass
class Function:
    address: int
    symbol: str
    size: int
    unit: int                         # index into Recipe.units
    fold_aliases: List[str] = field(default_factory=list)

    @property
    def names(self):
        return [self.symbol] + list(self.fold_aliases)


@dataclass
class Unit:
    index: int
    source: str
    compiler: str
    flags: List[str]
    functions: List[Function]
    symbols: Dict[str, int]
    eh_tails: List[dict]
    literal_symbols: List[str]

    @property
    def label(self) -> str:
        """Stable identifier: source path, plus #n when several units build the same source."""
        return self.source if not getattr(self, '_dup', 0) else '%s#%d' % (self.source, self._dup)


class Recipe:
    def __init__(self, data: dict, root: Optional[Path] = None):
        self.root = Path(root) if root else None
        self.note = data.get('note')
        self.totals = data.get('totals', {})
        self.units: List[Unit] = []
        seen_sources = defaultdict(int)
        for i, u in enumerate(data['units']):
            funcs = [Function(_num(f['address']), f['symbol'], int(f['size']), i, list(f.get('fold_aliases', [])))
                     for f in u.get('functions', [])]
            unit = Unit(i, u['source'], u.get('compiler', ''), list(u.get('flags', [])), funcs,
                        {k: _num(v) for k, v in u.get('symbols', {}).items()},
                        list(u.get('eh_tails', [])), list(u.get('literal_symbols', [])))
            unit._dup = seen_sources[u['source']]
            seen_sources[u['source']] += 1
            self.units.append(unit)

        # address -> definitions (a few addresses are built by more than one unit variant)
        self.definitions: Dict[int, List[Function]] = defaultdict(list)
        for u in self.units:
            for f in u.functions:
                self.definitions[f.address].append(f)
        self.function_addresses = set(self.definitions)

        self.eh_tails: Dict[int, Tuple[int, dict]] = {}
        for u in self.units:
            for t in u.eh_tails:
                self.eh_tails[_num(t['address'])] = (u.index, t)

        # address -> [(unit index, name)] over every unit's symbols{}
        self.references: Dict[int, List[Tuple[int, str]]] = defaultdict(list)
        # name -> set of addresses (a name should map to one address; some do not)
        self.name_addresses: Dict[str, set] = defaultdict(set)
        for u in self.units:
            for name, addr in u.symbols.items():
                self.references[addr].append((u.index, name))
                self.name_addresses[name].add(addr)
        for u in self.units:
            for f in u.functions:
                for n in f.names:
                    self.name_addresses[n].add(f.address)

    # -- convenience -------------------------------------------------------------
    @property
    def binding_count(self) -> int:
        return sum(len(u.symbols) for u in self.units)

    def definition_names(self, addr: int) -> set:
        names = set()
        for f in self.definitions.get(addr, ()):
            names.update(f.names)
        return names

    def names_at(self, addr: int) -> set:
        """Every name bound to addr anywhere (definitions and references)."""
        names = {n for _, n in self.references.get(addr, ())}
        names |= self.definition_names(addr)
        return names

    def code_range(self) -> Tuple[int, int]:
        """[lowest function address, highest function end) - a proxy for .text without the exe."""
        lo = min(self.function_addresses)
        hi = max(f.address + f.size for fs in self.definitions.values() for f in fs)
        return lo, hi

    def source_path(self, unit: Unit) -> Optional[Path]:
        return self.root / unit.source if self.root else None


def load_recipe(upstream_root) -> Recipe:
    """Load build/units.json from an fnv_decomp checkout."""
    root = Path(upstream_root)
    with open(root / 'build' / 'units.json', encoding='utf-8') as fh:
        data = json.load(fh)
    return Recipe(data, root)
