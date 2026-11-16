"""Index of fnv_decomp sources: @fnv address tags, local includes, identifier lines.

Used to point report rows at source lines (``file:line``). This is for human
navigation only; transforms use Clang tooling, not this index.
"""
from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = ['SourceIndex', 'TAG_RE']

TAG_RE = re.compile(r'//\s*@fnv\s+(0x[0-9a-fA-F]+)')
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"')
_IDENT_RE = re.compile(r'~?[A-Za-z_][A-Za-z0-9_]*')


class FileInfo:
    __slots__ = ('path', 'tags', 'includes', 'idents')

    def __init__(self, path: Path, tags, includes, idents):
        self.path = path
        self.tags: List[Tuple[int, int]] = tags          # (line, address), in line order
        self.includes: List[Path] = includes
        self.idents: Dict[str, List[int]] = idents     # identifier -> line numbers (1-based)

    def enclosing_tag(self, line: int) -> Optional[Tuple[int, int]]:
        """The last @fnv tag at or before line, as (tag line, address)."""
        lo, hi = 0, len(self.tags)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.tags[mid][0] <= line:
                lo = mid + 1
            else:
                hi = mid
        return self.tags[lo - 1] if lo else None


class SourceIndex:
    def __init__(self, root, include_dirs=('include',)):
        self.root = Path(root).resolve()
        self.include_dirs = [self.root / d for d in include_dirs]
        self._files: Dict[Path, FileInfo] = {}
        self._tag_map: Optional[Dict[int, List[Tuple[str, int]]]] = None

    def rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root))
        except ValueError:
            return str(path)

    def file(self, path) -> Optional[FileInfo]:
        path = Path(path)
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        info = self._files.get(path)
        if info is not None:
            return info
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return None
        tags, includes = [], []
        idents: Dict[str, List[int]] = defaultdict(list)
        for n, line in enumerate(text.splitlines(), 1):
            m = TAG_RE.search(line)
            if m:
                tags.append((n, int(m.group(1), 16)))
            mi = _INCLUDE_RE.match(line)
            if mi:
                inc = self._resolve_include(path.parent, mi.group(1))
                if inc is not None:
                    includes.append(inc)
                continue
            code = line.split('//', 1)[0]
            for ident in set(_IDENT_RE.findall(code)):
                idents[ident].append(n)
        info = FileInfo(path, tags, includes, dict(idents))
        self._files[path] = info
        return info

    def _resolve_include(self, base: Path, name: str) -> Optional[Path]:
        name = name.replace('\\', '/')
        for d in [base] + self.include_dirs:
            p = d / name
            if p.is_file():
                return p.resolve()
            # MSVC include lookup is case-insensitive.
            parent = p.parent
            if parent.is_dir():
                low = p.name.lower()
                for q in parent.iterdir():
                    if q.name.lower() == low and q.is_file():
                        return q.resolve()
        return None

    @lru_cache(maxsize=None)
    def include_closure(self, path: Path) -> Tuple[Path, ...]:
        """The file followed by its local includes, depth-first, each once."""
        order, seen, stack = [], set(), [Path(path).resolve()]
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            info = self.file(p)
            if info is None:
                continue
            order.append(p)
            stack.extend(reversed(info.includes))
        return tuple(order)

    def find_identifier(self, source, ident: str) -> Optional[Tuple[str, int]]:
        """First line mentioning ident in source, else in its include closure."""
        root_file = (self.root / source).resolve()
        for p in self.include_closure(root_file):
            info = self.file(p)
            lines = info.idents.get(ident) if info else None
            if lines:
                return self.rel(p), lines[0]
        return None

    def use_site(self, source, ident: str) -> Optional[Tuple[int, int]]:
        """(line, @fnv address) of the first tagged function in source whose body mentions ident."""
        info = self.file(source)
        if info is None or not info.tags:
            return None
        for line in info.idents.get(ident, ()):
            tag = info.enclosing_tag(line)
            if tag is not None and line > tag[0]:
                return line, tag[1]
        return None

    def tag_locations(self, sources) -> Dict[int, List[Tuple[str, int]]]:
        """address -> [(file, line)] for every @fnv tag in the given source files."""
        if self._tag_map is None:
            self._tag_map = defaultdict(list)
            for s in sources:
                info = self.file(s)
                if info is None:
                    continue
                for line, addr in info.tags:
                    self._tag_map[addr].append((self.rel(info.path), line))
        return self._tag_map
