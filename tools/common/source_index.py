"""Index of fnv_decomp sources: @fnv address tags, local includes, identifier lines.

Used to point report rows at source lines (``file:line``). This is for human
navigation only; transforms use Clang tooling, not this index.

Memory: a full identifier index (every line) is built only for the file being
processed (``scan``); headers keep only the first line of each identifier.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

__all__ = ['SourceIndex', 'FileInfo', 'TAG_RE', 'identifier_for']

TAG_RE = re.compile(r'//\s*@fnv\s+(0x[0-9a-fA-F]+)')
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"')
_IDENT_RE = re.compile(r'~?[A-Za-z_][A-Za-z0-9_]*')


class FileInfo:
    __slots__ = ('path', 'tags', 'includes', 'idents')

    def __init__(self, path: Path, tags, includes, idents):
        self.path = path
        self.tags: List[Tuple[int, int]] = tags          # (line, address), in line order
        self.includes: List[Path] = includes
        self.idents: Dict[str, object] = idents        # identifier -> [lines] (full) or first line

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


def identifier_for(sym) -> Optional[str]:
    """The source identifier most likely to spell a reference to sym (for locating lines)."""
    from tools.common.msvc_demangle import ConversionIdent, NamedIdent, OperatorIdent, StructorIdent
    if sym.kind in ('import', 'eh_helper') and sym.inner is not None:
        return identifier_for(sym.inner)
    if sym.qname is None:
        return sym.c_name
    u = sym.qname.unqualified
    comps = sym.qname.components
    if isinstance(u, StructorIdent):
        cls = u.cls.name if isinstance(u.cls, NamedIdent) else None
        return ('~' + cls) if (u.is_dtor and cls) else cls
    if isinstance(u, OperatorIdent):
        if u.kind == 'op':
            return 'operator'
        if 'dtor' in u.op_text and len(comps) >= 2 and isinstance(comps[-2], NamedIdent):
            return '~' + comps[-2].name
        if len(comps) >= 2 and isinstance(comps[-2], NamedIdent):
            return comps[-2].name
        return None
    if isinstance(u, ConversionIdent):
        return 'operator'
    if isinstance(u, NamedIdent):
        return u.name if _IDENT_RE.fullmatch(u.name) else None
    return None


class SourceIndex:
    def __init__(self, root, include_dirs=('include',)):
        self.root = Path(root).resolve()
        self.include_dirs = [self.root / d for d in include_dirs]
        self._headers: Dict[Path, FileInfo] = {}
        self._closures: Dict[Path, Tuple[Path, ...]] = {}

    def rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root))
        except ValueError:
            return str(path)

    def _abs(self, path) -> Path:
        path = Path(path)
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()

    def scan(self, path, full=True) -> Optional[FileInfo]:
        """Index one file. full=True keeps every line per identifier, else only the first."""
        path = self._abs(path)
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return None
        tags, includes = [], []
        idents: Dict[str, object] = defaultdict(list) if full else {}
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
            if full:
                for ident in set(_IDENT_RE.findall(code)):
                    idents[ident].append(n)
            else:
                for ident in _IDENT_RE.findall(code):
                    if ident not in idents:
                        idents[ident] = n
        return FileInfo(path, tags, includes, dict(idents))

    def header(self, path) -> Optional[FileInfo]:
        path = self._abs(path)
        info = self._headers.get(path)
        if info is None and path not in self._headers:
            info = self.scan(path, full=False)
            self._headers[path] = info
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

    def closure(self, includes: Iterable[Path]) -> Tuple[Path, ...]:
        """Local headers reachable from includes, depth-first, each once."""
        key = tuple(includes)
        order, seen, stack = [], set(), list(reversed(key))
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            info = self.header(p)
            if info is None:
                continue
            order.append(p)
            stack.extend(reversed(info.includes))
        return tuple(order)

    def locate(self, unit: FileInfo, ident: Optional[str]) -> Optional[Tuple[str, int]]:
        """First line mentioning ident in the unit file, else in its local headers."""
        if not ident or unit is None:
            return None
        lines = unit.idents.get(ident)
        if lines:
            return self.rel(unit.path), lines[0] if isinstance(lines, list) else lines
        closure = self._closures.get(unit.path)
        if closure is None:
            closure = self._closures[unit.path] = self.closure(unit.includes)
        for p in closure:
            info = self.header(p)
            line = info.idents.get(ident) if info else None
            if line:
                return self.rel(p), line
        return None

    @staticmethod
    def use_site(unit: FileInfo, ident: Optional[str]) -> Optional[Tuple[int, int]]:
        """(line, @fnv address) of the first tagged function in unit whose body mentions ident."""
        if not ident or unit is None or not unit.tags:
            return None
        lines = unit.idents.get(ident)
        if lines is None:
            return None
        if not isinstance(lines, list):
            lines = [lines]
        for line in lines:
            tag = unit.enclosing_tag(line)
            if tag is not None and line > tag[0]:
                return line, tag[1]
        return None

    def all_tags(self, sources: Iterable[str]) -> Dict[int, List[Tuple[str, int]]]:
        """address -> [(file, line)] for every @fnv tag in the given source files."""
        result: Dict[int, List[Tuple[str, int]]] = defaultdict(list)
        for s in dict.fromkeys(sources):
            path = self._abs(s)
            try:
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            rel = self.rel(path)
            for n, line in enumerate(text.splitlines(), 1):
                m = TAG_RE.search(line)
                if m:
                    result[int(m.group(1), 16)].append((rel, n))
        return result
