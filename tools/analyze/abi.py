"""Argument-passing model for 32-bit x86, under MSVC rules and under Clang i686 Linux rules.

The model works from decorated names only, so it knows types by name, not size:
aggregates passed or returned by value are kept symbolic (their names).

A call through a reference declaration R reaches a definition D correctly when
every argument location D reads (ECX, EDX, stack slots) is written by R with the
same size, the callee pops what the caller expects, and the return value comes
back in the same place. compat(D, R) returns:

  yes             same locations, cleanup and return
  yes-if-unused   D reads a location R does not write that is not D's first argument
                  (typically the dummy EDX parameter of the MSVC __fastcall-as-__thiscall
                  idiom, or trailing cdecl parameters); correct only if D never uses it
  if-this-unused  D's first argument (this / self) is not where D reads it; correct only
                  if D never uses it, which is rare
  no              different cleanup, a location with a different size, or a
                  different return location
  unknown         aggregates by value of unknown size, or a C-decorated name
                  without a parameter list

MSVC (what the original binary uses):
  * non-static members default to __thiscall: this in ECX, args on the stack, callee pops
  * __fastcall: the first two DWORD-or-smaller integer/pointer args (left to right) in ECX, EDX
  * __stdcall: stack, callee pops; __cdecl: stack, caller pops; variadic forces __cdecl
  * float/double results in ST0, 64-bit integers in EDX:EAX

Clang i686 Linux (Itanium/SysV), as the port compiles today:
  * a member whose MSVC convention is __thiscall gets __cdecl with this as the first stack arg
    (the decorated name cannot tell an explicit __thiscall from the default; we assume default)
  * explicit __stdcall / __fastcall are honoured as on MSVC
  * aggregates are returned through a hidden pointer that is the first stack argument and
    that the callee pops
  * member function pointers are 8 bytes instead of 4 (long double is 8 bytes on both: the
    port compiles with -mlong-double-64, as MSVC's long double is 64-bit)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from tools.common.msvc_demangle import (ArrayType, CustomType, FunctionType, PointerType, PrimitiveType,
                                        Symbol, TagType)

INT_REGS = ('ecx', 'edx')
VERDICT_ORDER = ['no', 'if-this-unused', 'unknown', 'yes-if-unused', 'yes']


def worst(a, b):
    return a if VERDICT_ORDER.index(a) < VERDICT_ORDER.index(b) else b


def type_class(t) -> Tuple[str, ...]:
    """Class of a parameter or return type: ('int4',), ('i8',), ('f4',), ('f8',), ('f80',),
    ('memfnptr',), ('agg', name), ('void',)."""
    if isinstance(t, PointerType):
        if t.class_parent is not None and isinstance(t.pointee, FunctionType):
            return ('memfnptr',)
        return ('int4',)
    if isinstance(t, PrimitiveType):
        n = t.name
        if n == 'void':
            return ('void',)
        if n == 'float':
            return ('f4',)
        if n == 'double':
            return ('f8',)
        if n == 'long double':
            return ('f80',)
        if n in ('__int64', 'unsigned __int64'):
            return ('i8',)
        return ('int4',)
    if isinstance(t, TagType):
        if t.tag == 'enum':
            return ('int4',)
        return ('agg', t.qname.text())
    if isinstance(t, (ArrayType, FunctionType)):
        return ('int4',)
    if isinstance(t, CustomType):
        return ('agg', t.text())
    return ('agg', '?')


def _size(cls, model):
    k = cls[0]
    if k in ('int4', 'f4'):
        return 4
    if k in ('i8', 'f8'):
        return 8
    if k == 'f80':
        return 8   # MSVC; and the port uses -mlong-double-64
    if k == 'memfnptr':
        return 4 if model == 'msvc' else 8
    return None  # aggregate of unknown size


@dataclass(frozen=True)
class Layout:
    cc: str                          # effective convention
    regs: Tuple[str, ...]            # registers carrying arguments
    stack: Optional[Tuple]           # ((offset, size), ...) in order; size None = unknown aggregate
    stack_bytes: Optional[int]       # total stack argument bytes (None if unknown)
    pops: Optional[int]              # bytes the callee pops (None if unknown)
    ret: Tuple                       # return class
    first: Optional[object] = None   # location of the first argument: 'ecx', 'edx' or a stack offset

    @property
    def known(self):
        return self.stack is not None


def _ret_class(ret, model):
    if ret is None:
        return ('void',)
    cls = type_class(ret)
    k = cls[0]
    if k in ('f4', 'f8', 'f80'):
        return ('x87',)
    if k == 'i8':
        return ('edx:eax',)
    if k == 'agg':
        return ('sret', cls[1]) if model == 'linux' else ('agg', cls[1])
    if k == 'memfnptr':
        return ('sret', 'memfnptr') if model == 'linux' else ('int4',)
    return cls


def layout_of(sym: Symbol, model: str) -> Optional[Layout]:
    """Argument layout of a function symbol under 'msvc' or 'linux' rules; None if not a function."""
    if sym.kind == 'c_name':
        cc = sym.c_cc or 'cdecl'
        n = sym.c_arg_bytes
        if cc == 'stdcall' and n is not None:
            return Layout(cc, (), None, n, n, ('unknown',))
        if cc == 'fastcall' and n is not None:
            regs = INT_REGS[:min(2, n // 4)]
            rest = max(0, n - 4 * len(regs))
            return Layout(cc, regs, None, rest, rest, ('unknown',))
        return Layout(cc, (), None, None, 0, ('unknown',))
    if sym.kind != 'function' or sym.sig is None:
        return None
    member = sym.is_member
    cc = sym.cc or 'cdecl'
    if sym.variadic:
        cc = 'cdecl'
    if model == 'linux' and member and cc == 'thiscall':
        cc = 'cdecl'
    args = ([('int4',)] if member else []) + [type_class(p) for p in (sym.sig.params or ())]
    ret = _ret_class(sym.sig.ret, model)
    regs, rest = [], []
    if cc == 'thiscall':
        if args:
            regs.append('ecx')
            rest = args[1:]
    elif cc == 'fastcall':
        free = list(INT_REGS)
        for a in args:
            if free and a[0] == 'int4':
                regs.append(free.pop(0))
            else:
                rest.append(a)
    else:
        rest = args
    sizes = [_size(a, model) for a in rest]
    if model == 'linux' and ret[0] == 'sret':
        sizes = [4] + sizes          # hidden return pointer, first stack argument
    first = None
    if args:
        if regs and (cc == 'thiscall' or args[0][0] == 'int4' and cc == 'fastcall'):
            first = regs[0]
        else:
            first = 4 if (model == 'linux' and ret[0] == 'sret') else 0
    stack, off, known = [], 0, True
    for s in sizes:
        stack.append((off if known else None, s))
        if s is None:
            known = False
        else:
            off += (s + 3) & ~3
    total = off if known else None
    if cc in ('stdcall', 'fastcall', 'thiscall'):
        pops = total
    elif model == 'linux' and ret[0] == 'sret':
        pops = 4                      # SysV i386: callee pops the hidden pointer
    else:
        pops = 0
    return Layout(cc, tuple(regs), tuple(stack), total, pops, ret, first)


def _ret_compat(d, r):
    if d == r:
        return 'yes'
    kinds = {d[0], r[0]}
    if kinds <= {'void', 'int4', 'edx:eax'}:
        return 'yes'             # EAX/EDX set or ignored
    if 'unknown' in kinds:
        return 'unknown'
    if d[0] in ('agg', 'sret') and r[0] in ('agg', 'sret'):
        return 'unknown'         # same mechanism, different aggregate names
    if 'agg' in kinds and 'x87' not in kinds:
        return 'unknown'         # MSVC may return small aggregates in EDX:EAX
    return 'no'                  # x87 result on one side only, or sret vs register


def compat(d: Symbol, r: Symbol, model: str) -> str:
    """Can a call through reference r reach definition d? See module docstring."""
    ld, lr = layout_of(d, model), layout_of(r, model)
    if ld is None or lr is None:
        return 'unknown'
    if (d.kind == 'c_name' or r.kind == 'c_name') and 'sret' in (ld.ret[0], lr.ret[0]):
        return 'unknown'      # a C-decorated name does not say what it returns
    verdict = 'yes'
    # Cleanup.
    if ld.pops is not None and lr.pops is not None:
        if ld.pops != lr.pops:
            return 'no'
    else:
        verdict = 'unknown'
    # Registers: D reading a register R does not set.
    for reg in ld.regs:
        if reg not in lr.regs:
            verdict = worst(verdict, 'if-this-unused' if reg == ld.first else 'yes-if-unused')
    # Stack slots.
    if ld.known and lr.known:
        dmap = {o: s for o, s in ld.stack if o is not None}
        rmap = {o: s for o, s in lr.stack if o is not None}
        if ld.stack != lr.stack and any(s is None for _, s in ld.stack + lr.stack):
            verdict = worst(verdict, 'unknown')   # offsets after an unknown-size aggregate
        for o, s in dmap.items():
            if o not in rmap:
                if any(ro < o < ro + (rs or 0) for ro, rs in rmap.items()):
                    return 'no'          # D reads the middle of an argument R passes
                verdict = worst(verdict, 'if-this-unused' if o == ld.first else 'yes-if-unused')
            elif rmap[o] != s:
                if rmap[o] is None or s is None:
                    verdict = worst(verdict, 'unknown')
                else:
                    return 'no'
        # R passing an argument where D expects nothing: harmless (unless cleanup differs, handled).
        # R passing in a register what D reads from the stack is caught above as a missing slot.
    else:
        if ld.stack_bytes is not None and lr.stack_bytes is not None and ld.stack_bytes > lr.stack_bytes:
            verdict = worst(verdict, 'yes-if-unused')
        if ld.stack_bytes is None or lr.stack_bytes is None:
            verdict = worst(verdict, 'unknown')
    return worst(verdict, _ret_compat(ld.ret, lr.ret))


# Backwards-compatible name used by the convention report.
def equivalent(a: Symbol, b: Symbol, model: str) -> str:
    return compat(a, b, model)
