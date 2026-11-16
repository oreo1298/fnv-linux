"""Root-cause categories for Clang diagnostics on fnv_decomp units.

Clang's messages are grouped into the MSVC leniencies and per-unit-view problems behind
them, so the baseline can be read as a work list for Phase 3. Rules are tried in order on
each error; the first that matches wins. Some rules look at the source line of the error or
of its first note (e.g. to tell a forward-declared enum from a forward-declared class).
"""
from __future__ import annotations

import linecache
import re
from collections import Counter, defaultdict
from pathlib import Path

SSE_RE = re.compile(r"__m128|LocalM128|\b_mm_|__v4sf|m128_")

INCOMPLETE_RE = re.compile(r"(field has incomplete type|is an incomplete type|variable has incomplete type|"
                           r"incomplete type .* (used|named)|incomplete result type|"
                           r"initialization of incomplete type|arithmetic on a pointer to an incomplete type|"
                           r"incomplete definition of type|member access into incomplete type|"
                           r"base class has incomplete type|parameter of incomplete type)")

RULES = [
    # (category, message regex, optional predicate(diag, line, note_line))
    ('MSVC SSE model: own __m128 / intrinsic redeclarations',
     re.compile(r'.'), lambda d, line, note: bool(SSE_RE.search(d['msg']) or SSE_RE.search(line))),
    ('forward-declared enum used as a complete type',
     INCOMPLETE_RE, lambda d, line, note: bool(re.search(r'\benum\b', note))),
    ('SEH (__try/__except/__finally) unsupported on Linux',
     re.compile(r"SEH '.*' is not supported|__try|__except|__finally"), None),
    ('calling-convention redeclaration',
     re.compile(r'(previously declared without calling convention|different calling convention|'
                r'calling convention .* (mismatch|differs))'), None),
    ('__if_exists / __if_not_exists on an undefined template',
     re.compile(r'implicit instantiation of undefined template'),
     lambda d, line, note: '__if_' in line),
    ('undefined template instantiated',
     re.compile(r'implicit instantiation of undefined template'), None),
    ('incomplete class type in this unit\'s view',
     INCOMPLETE_RE, None),
    ('unknown or missing base class',
     re.compile(r"(unknown class name|expected class name)"), None),
    ('incomplete class type in this unit\'s view',
     re.compile(r"(with incomplete return type|argument type .* is incomplete)"), None),
    ('per-unit class views disagree (hierarchy / members)',
     re.compile(r"(cannot initialize object parameter|not related by inheritance|no matching member function|"
                r"no member named .* in |cannot initialize a parameter of type|comparison of distinct pointer types|"
                r"cannot initialize a variable of type|cannot initialize return object|"
                r"no viable conversion|cannot cast from|is not a base of|ambiguous conversion from derived|"
                r"incompatible pointer types|cannot be assigned|no matching function for call|"
                r"no matching constructor|reinterpret_cast from .* casts away|"
                r"invalid operands to binary expression)"), None),
    ('conflicting redeclarations (types, linkage, return type)',
     re.compile(r"(conflicting types for|C language linkage conflicts|different language linkage|"
                r"differ only in their return type|redefinition of|redeclaration of|"
                r"typedef redefinition|use of .* with tag type that does not match|"
                r"declared as a different kind of symbol|out-of-line definition of .* does not match|"
                r"conflicts with a previous declaration|in global scope conflicts with declaration with C language linkage|"
                r"is ambiguous|found in multiple base classes)"), None),
    ('operator new/delete declared inside a namespace',
     re.compile(r"cannot be declared inside a namespace"), None),
    ('layout static assert fails or is not constant under Clang',
     re.compile(r"(declared as an array with a negative size|variable length array declaration not allowed at file scope)"),
     None),
    ('C++ dialect strictness (narrowing, temporaries, specialization order)',
     re.compile(r"(cannot be narrowed|taking the address of a temporary|explicit specialization of .* after instantiation|"
                r"ISO C\+\+|non-const lvalue reference .* cannot bind to a temporary|"
                r"cannot jump from|jump bypasses|goto into protected scope|must be a constant expression|"
                r"is a private member|is a protected member|'this' argument to member function .* has type|"
                r"from rvalue to reference type|address of an rvalue|missing exception specification|"
                r"exception specifications are not allowed|exception specification is not available|"
                r"need to include <typeinfo>|template specialization requires|"
                r"implicitly-deleted|deleted function .* cannot override)"), None),
    ('MS inline asm rejected',
     re.compile(r"(invalid operand for instruction|unknown token in expression|invalid instruction mnemonic|"
                r"unexpected token in|cannot use more than one symbol in memory operand|\binline asm\b|"
                r"\basm\b)", re.I), None),
    ('undeclared identifier / unknown type',
     re.compile(r"(use of undeclared identifier|unknown type name|undeclared identifier|no type named|"
                r"no template named|unexpected type name|expected unqualified-id|expected expression|"
                r"expected '.'|expected ';'|expected '\)'|is not a class, namespace, or enumeration)"), None),
]


def _source_line(upstream: Path, f: str, line: int) -> str:
    if f.startswith(('shim:', 'system:')):
        return ''
    return linecache.getline(str(upstream / f), line)


def categorize(d, upstream: Path) -> str:
    line = _source_line(upstream, d['file'], d['line'])
    notes = d.get('notes') or []
    note_line = _source_line(upstream, notes[0]['file'], notes[0]['line']) if notes else ''
    for name, rx, pred in RULES:
        if rx.search(d['msg']) and (pred is None or pred(d, line, note_line)):
            return name
    if d['sev'] == 'fatal error':
        return 'fatal error (missing header or error limit)'
    return 'other'


def categorize_results(results, upstream: Path):
    """[{category, units, first, occurrences}] sorted by units affected."""
    units = defaultdict(set)
    first = Counter()
    occ = Counter()
    for r in results:
        for i, d in enumerate(r['diagnostics']):
            if 'too many errors emitted' in d['msg']:
                continue
            c = categorize(d, upstream)
            d['category'] = c
            units[c].add(r['index'])
            occ[c] += 1
            if i == 0:
                first[c] += 1
    return [{'category': c, 'units': len(units[c]), 'first': first[c], 'occurrences': occ[c]}
            for c in sorted(units, key=lambda c: (-len(units[c]), -first[c]))]
