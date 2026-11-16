"""Structured demangler for 32-bit MSVC decorated names.

The grammar and the text rendering follow LLVM's MicrosoftDemangle (the engine
behind ``llvm-undname``), so ``Symbol.render()`` can be checked against
``llvm-undname`` name by name. Unlike ``llvm-undname`` this returns structure:
symbol kind, member/free/static, access, calling convention, parameter and
return types. That structure is what the ABI analysis needs.

Besides C++ names (``?...``) this also classifies the undecorated and
C-decorated names that appear in fnv_decomp's ``build/units.json``:

* ``_name`` (cdecl C), ``_name@N`` (stdcall C), ``@name@N`` (fastcall C)
* ``__imp_<name>`` import address table slots
* ``$SG123`` string literal labels, ``$LN12`` code labels
* ``__real@<hex>`` / ``__xmm@<hex>`` floating point constants
* ``__ehhandler$<name>`` / ``__unwindfunclet$<name>$N`` EH helpers

Usage::

    sym = demangle('?f@@YAXH@Z')
    sym.kind        -> 'function'
    sym.cc          -> 'cdecl'
    sym.params      -> ('int',)
    sym.render()    -> 'void __cdecl f(int)'
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = ['DemangleError', 'Symbol', 'demangle', 'try_demangle']


class DemangleError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Qualifiers and flags

Q_NONE, Q_CONST, Q_VOLATILE, Q_RESTRICT, Q_UNALIGNED, Q_PTR64 = 0, 1, 2, 4, 8, 16

FC_NONE = 0
FC_PUBLIC = 1 << 0
FC_PROTECTED = 1 << 1
FC_PRIVATE = 1 << 2
FC_GLOBAL = 1 << 3
FC_STATIC = 1 << 4
FC_VIRTUAL = 1 << 5
FC_FAR = 1 << 6
FC_EXTERN_C = 1 << 7
FC_NO_PARAMETER_LIST = 1 << 8
FC_VIRTUAL_THIS_ADJUST = 1 << 9
FC_VIRTUAL_THIS_ADJUST_EX = 1 << 10
FC_STATIC_THIS_ADJUST = 1 << 11

# Output flags (subset of LLVM's).
OF_DEFAULT = 0
OF_NO_CALLING_CONVENTION = 1
OF_NO_TAG_SPECIFIER = 2
OF_NO_ACCESS_SPECIFIER = 4
OF_NO_MEMBER_TYPE = 8
OF_NO_RETURN_TYPE = 16
OF_NO_VARIABLE_TYPE = 32

CALLING_CONVENTIONS = {
    'A': 'cdecl', 'B': 'cdecl', 'C': 'pascal', 'D': 'pascal', 'E': 'thiscall', 'F': 'thiscall',
    'G': 'stdcall', 'H': 'stdcall', 'I': 'fastcall', 'J': 'fastcall', 'M': 'clrcall', 'N': 'clrcall',
    'O': 'eabi', 'P': 'eabi', 'Q': 'vectorcall', 'S': 'swiftcall', 'W': 'swiftasynccall',
}
CC_KEYWORDS = {
    'cdecl': '__cdecl', 'pascal': '__pascal', 'thiscall': '__thiscall', 'stdcall': '__stdcall',
    'fastcall': '__fastcall', 'clrcall': '__clrcall', 'eabi': '__eabi', 'vectorcall': '__vectorcall',
    'swiftcall': '__attribute__((__swiftcall__))', 'swiftasynccall': '__attribute__((__swiftasynccall__))',
}

FUNCTION_CLASSES = {
    'A': FC_PRIVATE, 'B': FC_PRIVATE | FC_FAR,
    'C': FC_PRIVATE | FC_STATIC, 'D': FC_PRIVATE | FC_STATIC | FC_FAR,
    'E': FC_PRIVATE | FC_VIRTUAL, 'F': FC_PRIVATE | FC_VIRTUAL | FC_FAR,
    'G': FC_PRIVATE | FC_STATIC_THIS_ADJUST, 'H': FC_PRIVATE | FC_STATIC_THIS_ADJUST | FC_FAR,
    'I': FC_PROTECTED, 'J': FC_PROTECTED | FC_FAR,
    'K': FC_PROTECTED | FC_STATIC, 'L': FC_PROTECTED | FC_STATIC | FC_FAR,
    'M': FC_PROTECTED | FC_VIRTUAL, 'N': FC_PROTECTED | FC_VIRTUAL | FC_FAR,
    'O': FC_PROTECTED | FC_VIRTUAL | FC_STATIC_THIS_ADJUST,
    'P': FC_PROTECTED | FC_VIRTUAL | FC_STATIC_THIS_ADJUST | FC_FAR,
    'Q': FC_PUBLIC, 'R': FC_PUBLIC | FC_FAR,
    'S': FC_PUBLIC | FC_STATIC, 'T': FC_PUBLIC | FC_STATIC | FC_FAR,
    'U': FC_PUBLIC | FC_VIRTUAL, 'V': FC_PUBLIC | FC_VIRTUAL | FC_FAR,
    'W': FC_PUBLIC | FC_VIRTUAL | FC_STATIC_THIS_ADJUST,
    'X': FC_PUBLIC | FC_VIRTUAL | FC_STATIC_THIS_ADJUST | FC_FAR,
    'Y': FC_GLOBAL, 'Z': FC_GLOBAL | FC_FAR,
}
VTORDISP_CLASSES = {
    '0': FC_PRIVATE | FC_VIRTUAL, '1': FC_PRIVATE | FC_VIRTUAL | FC_FAR,
    '2': FC_PROTECTED | FC_VIRTUAL, '3': FC_PROTECTED | FC_VIRTUAL | FC_FAR,
    '4': FC_PUBLIC | FC_VIRTUAL, '5': FC_PUBLIC | FC_VIRTUAL | FC_FAR,
}

PRIMITIVES = {
    'X': 'void', 'C': 'signed char', 'D': 'char', 'E': 'unsigned char', 'F': 'short',
    'G': 'unsigned short', 'H': 'int', 'I': 'unsigned int', 'J': 'long', 'K': 'unsigned long',
    'M': 'float', 'N': 'double', 'O': 'long double',
}
PRIMITIVES_UNDERSCORE = {
    'N': 'bool', 'J': '__int64', 'K': 'unsigned __int64', 'W': 'wchar_t', 'Q': 'char8_t',
    'S': 'char16_t', 'U': 'char32_t',
}

# Operator / special-member names: (group, code) -> (kind, text)
_BASIC = {
    '0': ('ctor', None), '1': ('dtor', None), '2': ('op', 'operator new'), '3': ('op', 'operator delete'),
    '4': ('op', 'operator='), '5': ('op', 'operator>>'), '6': ('op', 'operator<<'), '7': ('op', 'operator!'),
    '8': ('op', 'operator=='), '9': ('op', 'operator!='), 'A': ('op', 'operator[]'), 'B': ('conv', None),
    'C': ('op', 'operator->'), 'D': ('op', 'operator*'), 'E': ('op', 'operator++'), 'F': ('op', 'operator--'),
    'G': ('op', 'operator-'), 'H': ('op', 'operator+'), 'I': ('op', 'operator&'), 'J': ('op', 'operator->*'),
    'K': ('op', 'operator/'), 'L': ('op', 'operator%'), 'M': ('op', 'operator<'), 'N': ('op', 'operator<='),
    'O': ('op', 'operator>'), 'P': ('op', 'operator>='), 'Q': ('op', 'operator,'), 'R': ('op', 'operator()'),
    'S': ('op', 'operator~'), 'T': ('op', 'operator^'), 'U': ('op', 'operator|'), 'V': ('op', 'operator&&'),
    'W': ('op', 'operator||'), 'X': ('op', 'operator*='), 'Y': ('op', 'operator+='), 'Z': ('op', 'operator-='),
}
_UNDER = {
    '0': ('op', 'operator/='), '1': ('op', 'operator%='), '2': ('op', 'operator>>='), '3': ('op', 'operator<<='),
    '4': ('op', 'operator&='), '5': ('op', 'operator|='), '6': ('op', 'operator^='),
    '7': ('special', "`vftable'"), '8': ('special', "`vbtable'"), '9': ('special', "`vcall'"),
    'A': ('special', "`typeof'"), 'B': ('special', "`local static guard'"), 'C': ('special', "`string'"),
    'D': ('special', "`vbase dtor'"), 'E': ('special', "`vector deleting dtor'"),
    'F': ('special', "`default ctor closure'"), 'G': ('special', "`scalar deleting dtor'"),
    'H': ('special', "`vector ctor iterator'"), 'I': ('special', "`vector dtor iterator'"),
    'J': ('special', "`vector vbase ctor iterator'"), 'K': ('special', "`virtual displacement map'"),
    'L': ('special', "`eh vector ctor iterator'"), 'M': ('special', "`eh vector dtor iterator'"),
    'N': ('special', "`eh vector vbase ctor iterator'"), 'O': ('special', "`copy ctor closure'"),
    'P': ('special', "`udt returning'"), 'S': ('special', "`local vftable'"),
    'T': ('special', "`local vftable ctor closure'"), 'U': ('op', 'operator new[]'),
    'V': ('op', 'operator delete[]'), 'X': ('special', "`placement delete closure'"),
    'Y': ('special', "`placement delete[] closure'"),
}
_DOUBLE_UNDER = {
    'A': ('special', "`managed vector ctor iterator'"), 'B': ('special', "`managed vector dtor iterator'"),
    'C': ('special', "`EH vector copy ctor iterator'"), 'D': ('special', "`EH vector vbase copy ctor iterator'"),
    'G': ('special', "`vector copy ctor iterator'"), 'H': ('special', "`vector vbase copy ctor iterator'"),
    'I': ('special', "`managed vector copy ctor iterator'"), 'L': ('op', 'operator co_await'),
    'M': ('op', 'operator<=>'),
}

# Special intrinsic symbol prefixes (after the leading '?'), longest first.
_SPECIAL_INTRINSICS = [
    ('?_R0', 'rtti_type_descriptor'), ('?_R1', 'rtti_base_class_descriptor'),
    ('?_R2', 'rtti_base_class_array'), ('?_R3', 'rtti_class_hierarchy_descriptor'),
    ('?_R4', 'rtti_complete_object_locator'), ('?_C@_', 'string_literal'),
    ('?__E', 'dynamic_initializer'), ('?__F', 'dynamic_atexit_destructor'),
    ('?__J', 'local_static_thread_guard'), ('?_7', 'vftable'), ('?_8', 'vbtable'),
    ('?_9', 'vcall_thunk'), ('?_A', 'typeof'), ('?_B', 'local_static_guard'),
    ('?_S', 'local_vftable'),
]


# ---------------------------------------------------------------------------
# Output helpers (mirror LLVM's OutputBuffer conventions)

class _Out:
    __slots__ = ('parts',)

    def __init__(self):
        self.parts = []

    def write(self, s):
        if s:
            self.parts.append(s)

    def back(self):
        for p in reversed(self.parts):
            if p:
                return p[-1]
        return ''

    def space_if_necessary(self):
        c = self.back()
        if c and (c.isalnum() or c == '>'):
            self.parts.append(' ')

    def text(self):
        return ''.join(self.parts)


def _write_quals(out, quals, space_before, space_after):
    if not quals & (Q_CONST | Q_VOLATILE | Q_RESTRICT):
        return
    start = len(out.parts)
    for mask, text in ((Q_CONST, 'const'), (Q_VOLATILE, 'volatile'), (Q_RESTRICT, '__restrict')):
        if quals & mask:
            if space_before:
                out.write(' ')
            out.write(text)
            space_before = True
    if space_after and len(out.parts) > start:
        out.write(' ')


# ---------------------------------------------------------------------------
# Name nodes

class Ident:
    """One component of a qualified name."""
    template_args: Optional[list] = None

    def output(self, out, flags):
        raise NotImplementedError

    def output_template(self, out, flags):
        if self.template_args is None:
            return
        out.write('<')
        for i, a in enumerate(self.template_args):
            if i:
                out.write(', ')
            a.output(out, flags)
        out.write('>')

    def text(self, flags=OF_DEFAULT):
        o = _Out()
        self.output(o, flags)
        return o.text()


class NamedIdent(Ident):
    def __init__(self, name, template_args=None):
        self.name = name
        self.template_args = template_args

    def output(self, out, flags):
        out.write(self.name)
        self.output_template(out, flags)


class OperatorIdent(Ident):
    def __init__(self, kind, text):
        self.kind = kind          # 'op' or 'special'
        self.op_text = text
        self.template_args = None

    def output(self, out, flags):
        out.write(self.op_text)
        self.output_template(out, flags)


class StructorIdent(Ident):
    def __init__(self, is_dtor):
        self.is_dtor = is_dtor
        self.cls = None
        self.template_args = None

    def output(self, out, flags):
        if self.is_dtor:
            out.write('~')
        if self.cls is not None:
            self.cls.output(out, flags)
        self.output_template(out, flags)


class ConversionIdent(Ident):
    def __init__(self):
        self.target = None
        self.template_args = None

    def output(self, out, flags):
        out.write('operator')
        self.output_template(out, flags)
        out.write(' ')
        if self.target is not None:
            self.target.output(out, flags)


class DynamicStructorIdent(Ident):
    def __init__(self, is_dtor):
        self.is_dtor = is_dtor
        self.variable = None
        self.name = None
        self.template_args = None

    def output(self, out, flags):
        out.write("`dynamic atexit destructor for " if self.is_dtor else "`dynamic initializer for ")
        if self.variable is not None:
            out.write('`')
            self.variable.output(out, flags)
            out.write("''")
        else:
            out.write("'")
            self.name.output(out, flags)
            out.write("''")


class LocalStaticGuardIdent(Ident):
    def __init__(self, is_thread):
        self.is_thread = is_thread
        self.scope_index = 0
        self.template_args = None

    def output(self, out, flags):
        out.write("`local static thread guard'" if self.is_thread else "`local static guard'")
        if self.scope_index > 0:
            out.write('{%d}' % self.scope_index)


class QualifiedName:
    def __init__(self, components):
        self.components = components  # outermost first

    @property
    def unqualified(self):
        return self.components[-1]

    def output(self, out, flags):
        for i, c in enumerate(self.components):
            if i:
                out.write('::')
            c.output(out, flags)

    def text(self, flags=OF_DEFAULT):
        o = _Out()
        self.output(o, flags)
        return o.text()


# ---------------------------------------------------------------------------
# Type nodes

class Type:
    quals = Q_NONE

    def pre(self, out, flags):
        raise NotImplementedError

    def post(self, out, flags):
        pass

    def output(self, out, flags):
        self.pre(out, flags)
        self.post(out, flags)

    def text(self, flags=OF_DEFAULT):
        o = _Out()
        self.output(o, flags)
        return o.text()


class PrimitiveType(Type):
    def __init__(self, name):
        self.name = name
        self.quals = Q_NONE

    def pre(self, out, flags):
        out.write(self.name)
        _write_quals(out, self.quals, True, False)


class TagType(Type):
    def __init__(self, tag, qname):
        self.tag = tag  # class / struct / union / enum
        self.qname = qname
        self.quals = Q_NONE

    def pre(self, out, flags):
        if not flags & OF_NO_TAG_SPECIFIER:
            out.write(self.tag + ' ')
        self.qname.output(out, flags)
        _write_quals(out, self.quals, True, False)


class CustomType(Type):
    def __init__(self, ident):
        self.ident = ident
        self.quals = Q_NONE

    def pre(self, out, flags):
        self.ident.output(out, flags)


class ArrayType(Type):
    def __init__(self, dims, elem):
        self.dims = dims
        self.elem = elem
        self.quals = Q_NONE

    def pre(self, out, flags):
        self.elem.pre(out, flags)
        _write_quals(out, self.quals, True, False)

    def post(self, out, flags):
        out.write('[' + ']['.join(str(d) for d in self.dims) + ']')
        self.elem.post(out, flags)


class FunctionType(Type):
    """Function signature (also the signature part of a function symbol)."""

    def __init__(self):
        self.quals = Q_NONE           # this-qualifiers for member functions
        self.ref_qualifier = None
        self.cc = None
        self.ret = None               # Type or None (structors)
        self.params = None            # list[Type] or None for (void)
        self.variadic = False
        self.noexcept = False
        self.fclass = FC_NONE
        # thunk adjustments
        self.static_adjust = None
        self.vtordisp = None          # (vbptr_off, vboff_off, vtordisp_off, static_off) or (None, None, v, s)

    def pre(self, out, flags):
        fc = self.fclass
        if not flags & OF_NO_ACCESS_SPECIFIER:
            if fc & FC_PUBLIC:
                out.write('public: ')
            if fc & FC_PROTECTED:
                out.write('protected: ')
            if fc & FC_PRIVATE:
                out.write('private: ')
        if not flags & OF_NO_MEMBER_TYPE:
            if not fc & FC_GLOBAL and fc & FC_STATIC:
                out.write('static ')
            if fc & FC_VIRTUAL:
                out.write('virtual ')
            if fc & FC_EXTERN_C:
                out.write('extern "C" ')
        if not flags & OF_NO_RETURN_TYPE and self.ret is not None:
            self.ret.pre(out, flags)
            out.write(' ')
        if not flags & OF_NO_CALLING_CONVENTION and self.cc:
            out.write(CC_KEYWORDS[self.cc])

    def post(self, out, flags):
        if not self.fclass & FC_NO_PARAMETER_LIST:
            out.write('(')
            if self.params is not None:
                for i, p in enumerate(self.params):
                    if i:
                        out.write(', ')
                    p.output(out, flags)
            else:
                out.write('void')
            if self.variadic:
                if out.back() != '(':
                    out.write(', ')
                out.write('...')
            out.write(')')
        if self.quals & Q_CONST:
            out.write(' const')
        if self.quals & Q_VOLATILE:
            out.write(' volatile')
        if self.quals & Q_RESTRICT:
            out.write(' __restrict')
        if self.quals & Q_UNALIGNED:
            out.write(' __unaligned')
        if self.noexcept:
            out.write(' noexcept')
        if self.ref_qualifier == '&':
            out.write(' &')
        elif self.ref_qualifier == '&&':
            out.write(' &&')
        if not flags & OF_NO_RETURN_TYPE and self.ret is not None:
            self.ret.post(out, flags)


class ThunkSignature(FunctionType):
    def pre(self, out, flags):
        out.write('[thunk]: ')
        FunctionType.pre(self, out, flags)

    def post(self, out, flags):
        if self.fclass & FC_STATIC_THIS_ADJUST:
            out.write("`adjustor{%d}'" % self.static_adjust)
        elif self.fclass & FC_VIRTUAL_THIS_ADJUST:
            vbptr, vboff, vtordisp, static = self.vtordisp
            if self.fclass & FC_VIRTUAL_THIS_ADJUST_EX:
                out.write("`vtordispex{%d, %d, %d, %d}'" % (vbptr, vboff, vtordisp, static))
            else:
                out.write("`vtordisp{%d, %d}'" % (vtordisp, static))
        FunctionType.post(self, out, flags)


class PointerType(Type):
    def __init__(self, affinity):
        self.affinity = affinity      # '*', '&', '&&'
        self.quals = Q_NONE
        self.pointee = None
        self.class_parent = None      # QualifiedName for member pointers

    def pre(self, out, flags):
        p = self.pointee
        if isinstance(p, FunctionType):
            p.pre(out, flags | OF_NO_CALLING_CONVENTION)
        else:
            p.pre(out, flags)
        out.space_if_necessary()
        if self.quals & Q_UNALIGNED:
            out.write('__unaligned ')
        if isinstance(p, ArrayType):
            out.write('(')
        elif isinstance(p, FunctionType):
            out.write('(')
            if p.cc:
                out.write(CC_KEYWORDS[p.cc])
            out.write(' ')
        if self.class_parent is not None:
            self.class_parent.output(out, flags)
            out.write('::')
        out.write(self.affinity)
        _write_quals(out, self.quals, False, False)

    def post(self, out, flags):
        if isinstance(self.pointee, (ArrayType, FunctionType)):
            out.write(')')
        self.pointee.post(out, flags)


class IntegerLiteral:
    def __init__(self, value, negative):
        self.value = value
        self.negative = negative

    def output(self, out, flags):
        out.write(('-' if self.negative else '') + str(self.value))


class TemplateSymbolRef:
    def __init__(self):
        self.symbol = None
        self.affinity = None
        self.offsets = []
        self.is_member_pointer = False

    def output(self, out, flags):
        if self.offsets:
            out.write('{')
        elif self.affinity == '*':
            out.write('&')
        if self.symbol is not None:
            self.symbol.output(out, flags)
            if self.offsets:
                out.write(', ')
        if self.offsets:
            out.write(', '.join(str(o) for o in self.offsets))
            out.write('}')


# ---------------------------------------------------------------------------
# Symbols

@dataclass
class Symbol:
    """A demangled symbol.

    kind is one of: function, data, vftable, vbtable, local_vftable,
    rtti_type_descriptor, rtti_base_class_descriptor, rtti_base_class_array,
    rtti_class_hierarchy_descriptor, rtti_complete_object_locator,
    string_literal, local_static_guard, vcall_thunk, c_name, import,
    string_label, code_label, float_constant, eh_helper, unknown.
    """
    mangled: str
    kind: str
    qname: Optional[QualifiedName] = None
    sig: Optional[FunctionType] = None
    var_type: Optional[Type] = None
    storage: Optional[str] = None       # data: private_static, protected_static, public_static, global, local_static
    table_quals: int = Q_NONE
    table_target: Optional[QualifiedName] = None
    c_cc: Optional[str] = None           # for c_name: cdecl / stdcall / fastcall / None (undecorated)
    c_name: Optional[str] = None
    c_arg_bytes: Optional[int] = None
    inner: Optional['Symbol'] = None    # for import / eh_helper
    literal_text: Optional[str] = None
    literal_char_width: int = 1
    literal_length: Optional[int] = None
    rendered_override: Optional[str] = None
    extra: dict = field(default_factory=dict)

    # ---- convenience accessors -------------------------------------------
    @property
    def is_function(self):
        return self.kind == 'function'

    @property
    def is_member(self):
        """Non-static member function (has a this pointer)."""
        if self.sig is None:
            return False
        return not self.sig.fclass & (FC_GLOBAL | FC_STATIC) and not self.sig.fclass & FC_EXTERN_C

    @property
    def is_static_member(self):
        return self.sig is not None and bool(self.sig.fclass & FC_STATIC) and not self.sig.fclass & FC_GLOBAL

    @property
    def is_virtual(self):
        return self.sig is not None and bool(self.sig.fclass & (FC_VIRTUAL | FC_STATIC_THIS_ADJUST | FC_VIRTUAL_THIS_ADJUST))

    @property
    def is_thunk(self):
        return self.sig is not None and bool(self.sig.fclass & (FC_STATIC_THIS_ADJUST | FC_VIRTUAL_THIS_ADJUST))

    @property
    def access(self):
        if self.sig is None:
            return {'private_static': 'private', 'protected_static': 'protected',
                    'public_static': 'public'}.get(self.storage)
        fc = self.sig.fclass
        if fc & FC_PUBLIC:
            return 'public'
        if fc & FC_PROTECTED:
            return 'protected'
        if fc & FC_PRIVATE:
            return 'private'
        return None

    @property
    def cc(self):
        if self.sig is not None:
            return self.sig.cc
        return self.c_cc

    @property
    def this_quals(self):
        if not self.is_member:
            return ''
        q = self.sig.quals
        return ' '.join(t for m, t in ((Q_CONST, 'const'), (Q_VOLATILE, 'volatile')) if q & m)

    @property
    def params(self):
        """Rendered parameter types; () for (void); None when unknown."""
        if self.sig is None or self.sig.fclass & FC_NO_PARAMETER_LIST:
            return None
        return tuple(p.text() for p in (self.sig.params or ()))

    @property
    def param_types(self):
        if self.sig is None:
            return None
        return list(self.sig.params or ())

    @property
    def variadic(self):
        return bool(self.sig and self.sig.variadic)

    @property
    def ret(self):
        if self.sig is None or self.sig.ret is None:
            return None
        return self.sig.ret.text()

    @property
    def scope(self):
        """Qualifier components as text (outermost first), excluding the name itself."""
        if self.qname is None:
            return ()
        return tuple(c.text() for c in self.qname.components[:-1])

    @property
    def unqualified(self):
        if self.qname is None:
            return self.c_name
        return self.qname.unqualified.text()

    @property
    def qualified(self):
        if self.qname is None:
            return self.c_name
        return self.qname.text()

    @property
    def special(self):
        """ctor, dtor, scalar_deleting_dtor, vector_deleting_dtor, operator, conversion, ... or None."""
        if self.qname is None:
            return None
        u = self.qname.unqualified
        if isinstance(u, StructorIdent):
            return 'dtor' if u.is_dtor else 'ctor'
        if isinstance(u, ConversionIdent):
            return 'conversion'
        if isinstance(u, DynamicStructorIdent):
            return 'dynamic_atexit_destructor' if u.is_dtor else 'dynamic_initializer'
        if isinstance(u, OperatorIdent):
            if u.kind == 'op':
                return 'operator'
            return u.op_text.strip("`'").replace(' ', '_')
        return None

    def render(self, flags=OF_DEFAULT):
        """Readable text in llvm-undname's format."""
        if self.rendered_override is not None:
            return self.rendered_override
        out = _Out()
        k = self.kind
        if k == 'function':
            self.sig.pre(out, flags)
            out.space_if_necessary()
            self.qname.output(out, flags)
            self.sig.post(out, flags)
        elif k in ('data',):
            access = {'private_static': 'private', 'protected_static': 'protected',
                      'public_static': 'public'}.get(self.storage)
            if not flags & OF_NO_ACCESS_SPECIFIER and access:
                out.write(access + ': ')
            if not flags & OF_NO_MEMBER_TYPE and access:
                out.write('static ')
            if not flags & OF_NO_VARIABLE_TYPE and self.var_type is not None:
                self.var_type.pre(out, flags)
                out.space_if_necessary()
            self.qname.output(out, flags)
            if not flags & OF_NO_VARIABLE_TYPE and self.var_type is not None:
                self.var_type.post(out, flags)
        elif k in ('vftable', 'vbtable', 'local_vftable', 'rtti_complete_object_locator'):
            _write_quals(out, self.table_quals, False, True)
            self.qname.output(out, flags)
            if self.table_target is not None:
                out.write("{for `")
                self.table_target.output(out, flags)
                out.write("'}")
        elif k in ('import', 'eh_helper') and self.inner is not None:
            return self.inner.render(flags)
        elif self.qname is not None:
            self.qname.output(out, flags)
        else:
            return self.c_name or self.mangled
        return out.text()

    def output(self, out, flags):
        out.write(self.render(flags))


# ---------------------------------------------------------------------------
# Parser

class _Backrefs:
    __slots__ = ('names', 'params')

    def __init__(self):
        self.names = []
        self.params = []


class _Parser:
    def __init__(self, text):
        self.s = text
        self.i = 0
        self.br = _Backrefs()

    # -- low level -----------------------------------------------------------
    def peek(self, n=0):
        j = self.i + n
        return self.s[j] if j < len(self.s) else ''

    def startswith(self, prefix):
        return self.s.startswith(prefix, self.i)

    def consume(self, prefix):
        if self.s.startswith(prefix, self.i):
            self.i += len(prefix)
            return True
        return False

    def pop(self):
        if self.i >= len(self.s):
            raise DemangleError('unexpected end')
        c = self.s[self.i]
        self.i += 1
        return c

    def empty(self):
        return self.i >= len(self.s)

    def fail(self, why):
        raise DemangleError('%s at %d in %r' % (why, self.i, self.s))

    def starts_with_digit(self):
        c = self.peek()
        return c != '' and c.isdigit()

    # -- numbers ---------------------------------------------------------------
    def number(self):
        neg = self.consume('?')
        if self.starts_with_digit():
            v = ord(self.pop()) - ord('0') + 1
            return v, neg
        v = 0
        while not self.empty():
            c = self.pop()
            if c == '@':
                return v, neg
            if 'A' <= c <= 'P':
                v = (v << 4) + (ord(c) - ord('A'))
                continue
            break
        self.fail('bad number')

    def signed(self):
        v, neg = self.number()
        return -v if neg else v

    def unsigned(self):
        v, neg = self.number()
        if neg:
            self.fail('negative unsigned')
        return v

    # -- names -----------------------------------------------------------------
    def memorize_string(self, s):
        if len(self.br.names) >= 10:
            return
        for n in self.br.names:
            if n.name == s:
                return
        self.br.names.append(NamedIdent(s))

    def memorize_ident(self, ident):
        self.memorize_string(ident.text())

    def simple_name(self, memorize):
        j = self.s.find('@', self.i)
        if j < 0:
            self.fail('unterminated name')
        name = self.s[self.i:j]
        self.i = j + 1
        if memorize:
            self.memorize_string(name)
        return NamedIdent(name)

    def backref_name(self):
        k = ord(self.pop()) - ord('0')
        if k >= len(self.br.names):
            self.fail('bad name backref')
        return self.br.names[k]

    def template_instantiation_name(self, memorize_template):
        if not self.consume('?$'):
            self.fail('expected ?$')
        outer = self.br
        self.br = _Backrefs()
        try:
            ident = self.unqualified_symbol_name(simple=True)
            args = self.template_parameter_list()
            ident.template_args = args
        finally:
            self.br = outer
        if memorize_template:
            self.memorize_ident(ident)
        return ident

    def unqualified_symbol_name(self, simple):
        if self.starts_with_digit():
            return self.backref_name()
        if self.startswith('?$'):
            return self.template_instantiation_name(memorize_template=False)
        if self.startswith('?'):
            return self.function_identifier_code()
        return self.simple_name(memorize=simple)

    def function_identifier_code(self):
        self.consume('?')
        if self.empty():
            self.fail('empty operator')
        if self.consume('__'):
            table, group = _DOUBLE_UNDER, '__'
        elif self.consume('_'):
            table, group = _UNDER, '_'
        else:
            table, group = _BASIC, ''
        c = self.pop()
        if group == '__' and c == 'K':
            name = self.simple_name(memorize=False)
            return OperatorIdent('op', 'operator ""' + name.name)
        entry = table.get(c)
        if entry is None:
            self.fail('unknown operator code ?%s%s' % (group, c))
        kind, text = entry
        if kind == 'ctor':
            return StructorIdent(False)
        if kind == 'dtor':
            return StructorIdent(True)
        if kind == 'conv':
            return ConversionIdent()
        return OperatorIdent(kind, text)

    def starts_with_local_scope(self):
        if self.peek() != '?':
            return False
        j = self.s.find('?', self.i + 1)
        if j < 0:
            return False
        cand = self.s[self.i + 1:j]
        if not cand:
            return False
        if len(cand) == 1:
            return cand == '@' or cand.isdigit()
        if cand[-1] != '@':
            return False
        cand = cand[:-1]
        if not cand or not ('B' <= cand[0] <= 'P'):
            return False
        return all('A' <= c <= 'P' for c in cand[1:])

    def locally_scoped_name_piece(self):
        self.consume('?')
        num, _ = self.number()
        self.consume('?')
        scope = self.parse_symbol()
        return NamedIdent("`%s'::`%d'" % (scope.render(), num))

    def anonymous_namespace(self):
        self.consume('?A')
        j = self.s.find('@', self.i)
        if j < 0:
            self.fail('unterminated anonymous namespace')
        self.memorize_string(self.s[self.i:j])
        self.i = j + 1
        return NamedIdent("`anonymous namespace'")

    def name_scope_piece(self):
        if self.starts_with_digit():
            return self.backref_name()
        if self.startswith('?$'):
            return self.template_instantiation_name(memorize_template=True)
        if self.startswith('?A'):
            return self.anonymous_namespace()
        if self.starts_with_local_scope():
            return self.locally_scoped_name_piece()
        return self.simple_name(memorize=True)

    def name_scope_chain(self, unqualified):
        comps = [unqualified]
        while not self.consume('@'):
            if self.empty():
                self.fail('unterminated scope chain')
            comps.append(self.name_scope_piece())
        comps.reverse()
        return QualifiedName(comps)

    def fully_qualified_symbol_name(self):
        ident = self.unqualified_symbol_name(simple=True)
        qn = self.name_scope_chain(ident)
        if isinstance(ident, StructorIdent):
            if len(qn.components) < 2:
                self.fail('structor without class')
            ident.cls = qn.components[-2]
        return qn

    def unqualified_type_name(self, memorize):
        if self.starts_with_digit():
            return self.backref_name()
        if self.startswith('?$'):
            return self.template_instantiation_name(memorize_template=True)
        return self.simple_name(memorize)

    def fully_qualified_type_name(self):
        ident = self.unqualified_type_name(memorize=True)
        return self.name_scope_chain(ident)

    # -- qualifiers --------------------------------------------------------------
    def qualifiers(self):
        c = self.pop()
        table = {'Q': (Q_NONE, True), 'R': (Q_CONST, True), 'S': (Q_VOLATILE, True),
                 'T': (Q_CONST | Q_VOLATILE, True), 'A': (Q_NONE, False), 'B': (Q_CONST, False),
                 'C': (Q_VOLATILE, False), 'D': (Q_CONST | Q_VOLATILE, False)}
        if c not in table:
            self.fail('bad qualifier %r' % c)
        return table[c]

    def pointer_ext_qualifiers(self):
        q = Q_NONE
        if self.consume('E'):
            q |= Q_PTR64
        if self.consume('I'):
            q |= Q_RESTRICT
        if self.consume('F'):
            q |= Q_UNALIGNED
        return q

    def pointer_cv(self):
        if self.consume('$$Q'):
            return Q_NONE, '&&'
        if self.consume('$$R'):
            return Q_VOLATILE, '&&'
        c = self.pop()
        table = {'A': (Q_NONE, '&'), 'B': (Q_VOLATILE, '&'), 'P': (Q_NONE, '*'), 'Q': (Q_CONST, '*'),
                 'R': (Q_VOLATILE, '*'), 'S': (Q_CONST | Q_VOLATILE, '*')}
        if c not in table:
            self.fail('bad pointer cv %r' % c)
        return table[c]

    # -- types -------------------------------------------------------------------
    def is_member_pointer(self):
        s, j = self.s, self.i
        c = s[j] if j < len(s) else ''
        if c in ('$', 'A', 'B'):
            return False
        j += 1
        c = s[j] if j < len(s) else ''
        if c.isdigit():
            if c not in '68':
                self.fail('bad function pointer kind')
            return c == '8'
        for q in 'EIF':
            if j < len(s) and s[j] == q:
                j += 1
        c = s[j] if j < len(s) else ''
        if c in 'ABCD':
            return False
        if c in 'QRST':
            return True
        self.fail('bad pointer target')

    def parse_type(self, mode='drop'):
        quals = Q_NONE
        if mode == 'mangle':
            quals, _ = self.qualifiers()
        elif mode == 'result':
            if self.consume('?'):
                quals, _ = self.qualifiers()
        if self.empty():
            self.fail('expected type')
        c = self.peek()
        if c in 'TUV' or (c == 'W' and self.peek(1) == '4'):
            ty = self.class_type()
        elif c in 'APQRS' or self.startswith('$$Q') or self.startswith('$$R') or c == 'B':
            if self.is_member_pointer():
                ty = self.member_pointer_type()
            else:
                ty = self.pointer_type()
        elif c == 'Y':
            ty = self.array_type()
        elif self.startswith('$$A8@@'):
            self.i += 6
            ty = self.function_type(has_this_quals=True)
        elif self.startswith('$$A6'):
            self.i += 4
            ty = self.function_type(has_this_quals=False)
        elif c == '?':
            self.i += 1
            ident = self.unqualified_type_name(memorize=True)
            if not self.consume('@'):
                self.fail('bad custom type')
            ty = CustomType(ident)
        else:
            ty = self.primitive_type()
        ty.quals |= quals
        return ty

    def primitive_type(self):
        if self.consume('$$T'):
            return PrimitiveType('std::nullptr_t')
        c = self.pop()
        if c in PRIMITIVES:
            return PrimitiveType(PRIMITIVES[c])
        if c == '_':
            c2 = self.pop()
            if c2 in PRIMITIVES_UNDERSCORE:
                return PrimitiveType(PRIMITIVES_UNDERSCORE[c2])
        self.fail('unknown primitive %r' % c)

    def class_type(self):
        c = self.pop()
        if c == 'W':
            self.pop()  # the '4' (underlying type int)
            tag = 'enum'
        else:
            tag = {'T': 'union', 'U': 'struct', 'V': 'class'}[c]
        return TagType(tag, self.fully_qualified_type_name())

    def pointer_type(self):
        quals, aff = self.pointer_cv()
        p = PointerType(aff)
        p.quals = quals
        if self.consume('6'):
            p.pointee = self.function_type(has_this_quals=False)
            return p
        p.quals |= self.pointer_ext_qualifiers()
        p.pointee = self.parse_type('mangle')
        return p

    def member_pointer_type(self):
        quals, aff = self.pointer_cv()
        p = PointerType(aff)
        p.quals = quals | self.pointer_ext_qualifiers()
        if self.consume('8'):
            p.class_parent = self.fully_qualified_type_name()
            p.pointee = self.function_type(has_this_quals=True)
        else:
            pq, _ = self.qualifiers()
            p.class_parent = self.fully_qualified_type_name()
            p.pointee = self.parse_type('drop')
            p.pointee.quals = pq
        return p

    def array_type(self):
        self.consume('Y')
        rank, neg = self.number()
        if neg or rank == 0:
            self.fail('bad array rank')
        dims = []
        for _ in range(rank):
            d, neg = self.number()
            if neg:
                self.fail('negative dimension')
            dims.append(d)
        at = ArrayType(dims, None)
        if self.consume('$$C'):
            at.quals, _ = self.qualifiers()
        at.elem = self.parse_type('drop')
        return at

    def calling_convention(self):
        c = self.pop()
        if c not in CALLING_CONVENTIONS:
            self.fail('bad calling convention %r' % c)
        return CALLING_CONVENTIONS[c]

    def function_type(self, has_this_quals):
        ft = FunctionType()
        if has_this_quals:
            ft.quals = self.pointer_ext_qualifiers()
            if self.consume('G'):
                ft.ref_qualifier = '&'
            elif self.consume('H'):
                ft.ref_qualifier = '&&'
            q, _ = self.qualifiers()
            ft.quals |= q
        ft.cc = self.calling_convention()
        if not self.consume('@'):
            ft.ret = self.parse_type('result')
        ft.params, ft.variadic = self.function_params()
        if self.consume('_E'):
            ft.noexcept = True
        elif not self.consume('Z'):
            self.fail('bad throw specification')
        return ft

    def function_params(self):
        if self.consume('X'):
            return None, False
        params = []
        while not self.empty() and self.peek() not in ('@', 'Z'):
            if self.starts_with_digit():
                k = ord(self.pop()) - ord('0')
                if k >= len(self.br.params):
                    self.fail('bad param backref')
                params.append(self.br.params[k])
                continue
            start = self.i
            t = self.parse_type('drop')
            params.append(t)
            if len(self.br.params) <= 9 and self.i - start > 1:
                self.br.params.append(t)
        if self.consume('@'):
            return params, False
        if self.consume('Z'):
            return params, True
        self.fail('unterminated parameter list')

    def template_parameter_list(self):
        args = []
        while not self.startswith('@'):
            if self.empty():
                self.fail('unterminated template args')
            if self.consume('$S') or self.consume('$$V') or self.consume('$$$V') or self.consume('$$Z'):
                continue
            if self.consume('$M'):
                self.parse_type('drop')
            if self.consume('$$Y'):
                args.append(self.fully_qualified_type_name())
            elif self.consume('$$B'):
                args.append(self.parse_type('drop'))
            elif self.consume('$$C'):
                args.append(self.parse_type('mangle'))
            elif self.startswith('$1') or self.startswith('$H') or self.startswith('$I') or self.startswith('$J'):
                ref = TemplateSymbolRef()
                ref.is_member_pointer = True
                self.i += 1
                spec = self.pop()
                if self.startswith('?'):
                    ref.symbol = self.parse_symbol()
                    if ref.symbol.qname is not None:
                        self.memorize_ident(ref.symbol.qname.unqualified)
                n = {'J': 3, 'I': 2, 'H': 1, '1': 0}[spec]
                ref.offsets = [self.signed() for _ in range(n)]
                ref.affinity = '*'
                args.append(ref)
            elif self.startswith('$E?'):
                self.i += 2
                ref = TemplateSymbolRef()
                ref.symbol = self.parse_symbol()
                ref.affinity = '&'
                args.append(ref)
            elif self.startswith('$F') or self.startswith('$G'):
                ref = TemplateSymbolRef()
                self.i += 1
                spec = self.pop()
                n = 3 if spec == 'G' else 2
                ref.offsets = [self.signed() for _ in range(n)]
                ref.is_member_pointer = True
                args.append(ref)
            elif self.consume('$0'):
                v, neg = self.number()
                args.append(IntegerLiteral(v, neg))
            else:
                args.append(self.parse_type('drop'))
        self.consume('@')
        return args

    # -- symbols -------------------------------------------------------------------
    def function_class(self):
        c = self.pop()
        if c == '9':
            return FC_EXTERN_C | FC_NO_PARAMETER_LIST
        if c in FUNCTION_CLASSES:
            return FUNCTION_CLASSES[c]
        if c == '$':
            vflag = FC_VIRTUAL_THIS_ADJUST
            if self.consume('R'):
                vflag |= FC_VIRTUAL_THIS_ADJUST_EX
            c2 = self.pop()
            if c2 in VTORDISP_CLASSES:
                return VTORDISP_CLASSES[c2] | vflag
        self.fail('bad function class %r' % c)

    def function_encoding(self):
        extra = FC_NONE
        if self.consume('$$J0'):
            extra = FC_EXTERN_C
        fc = self.function_class() | extra
        static_adjust = None
        vtordisp = None
        if fc & FC_STATIC_THIS_ADJUST:
            static_adjust = self.signed()
        elif fc & FC_VIRTUAL_THIS_ADJUST:
            vbptr = vboff = None
            if fc & FC_VIRTUAL_THIS_ADJUST_EX:
                vbptr = self.signed()
                vboff = self.signed()
            vtordisp = (vbptr, vboff, self.signed(), self.signed())
        if fc & FC_NO_PARAMETER_LIST:
            ft = FunctionType()
        else:
            ft = self.function_type(has_this_quals=not fc & (FC_GLOBAL | FC_STATIC))
        if static_adjust is not None or vtordisp is not None:
            th = ThunkSignature()
            th.__dict__.update(ft.__dict__)
            th.static_adjust = static_adjust
            th.vtordisp = vtordisp
            ft = th
        ft.fclass = fc
        return ft

    def encoded_symbol(self, mangled, qn):
        c = self.peek()
        if c in '01234':
            self.i += 1
            storage = {'0': 'private_static', '1': 'protected_static', '2': 'public_static',
                       '3': 'global', '4': 'local_static'}[c]
            ty = self.parse_type('drop')
            if isinstance(ty, PointerType):
                ty.quals |= self.pointer_ext_qualifiers()
                extra, _ = self.qualifiers()
                if ty.class_parent is not None:
                    self.fully_qualified_type_name()
                ty.pointee.quals |= extra
            else:
                ty.quals = self.qualifiers()[0]
            return Symbol(mangled, 'data', qname=qn, var_type=ty, storage=storage)
        sig = self.function_encoding()
        u = qn.unqualified
        if isinstance(u, ConversionIdent):
            u.target = sig.ret
        return Symbol(mangled, 'function', qname=qn, sig=sig)

    def declarator(self, mangled):
        qn = self.fully_qualified_symbol_name()
        return self.encoded_symbol(mangled, qn)

    def special_table(self, mangled, kind, text):
        qn = self.name_scope_chain(OperatorIdent('special', text))
        c = self.pop()
        if c not in '67':
            self.fail('bad special table')
        quals, _ = self.qualifiers()
        target = None
        if not self.consume('@'):
            target = self.fully_qualified_type_name()
        return Symbol(mangled, kind, qname=qn, table_quals=quals, table_target=target)

    def init_fini_stub(self, mangled, is_dtor):
        ident = DynamicStructorIdent(is_dtor)
        known_member = self.consume('?')
        sym = self.declarator(mangled)
        if sym.kind == 'data':
            ident.variable = sym
            for _ in range(2 if known_member else 1):
                if not self.consume('@'):
                    self.fail('bad dynamic initializer')
            sig = self.function_encoding()
            return Symbol(mangled, 'function', qname=QualifiedName([ident]), sig=sig)
        if known_member:
            self.fail('expected static data member')
        ident.name = sym.qname
        sym.qname = QualifiedName([ident])
        return sym

    def local_static_guard(self, mangled, is_thread):
        ident = LocalStaticGuardIdent(is_thread)
        qn = self.name_scope_chain(ident)
        if self.consume('4IA'):
            visible = False
        elif self.consume('5'):
            visible = True
        else:
            self.fail('bad local static guard')
        if not self.empty():
            ident.scope_index = self.unsigned()
        return Symbol(mangled, 'local_static_guard', qname=qn, extra={'visible': visible})

    def string_literal(self, mangled):
        # ??_C@_<width><length><crc>@<chars>@
        width_c = self.pop()
        if width_c not in '01':
            self.fail('bad string literal width')
        width = 1 if width_c == '0' else 2
        length = self.unsigned()
        j = self.s.find('@', self.i)
        if j < 0:
            self.fail('bad string literal crc')
        self.i = j + 1
        raw = []
        while not self.empty() and self.peek() != '@':
            raw.append(self.string_char())
        self.consume('@')
        data = bytes(raw)
        if width == 2:
            text = data.decode('utf-16-be', 'replace')
        else:
            text = data.decode('latin-1')
        truncated = length > len(data)
        text = text.rstrip('\0')
        sym = Symbol(mangled, 'string_literal', literal_text=text, literal_char_width=width,
                     literal_length=length)
        sym.rendered_override = (('L' if width == 2 else '') + '"' + _escape(text) + '"'
                                 + ('...' if truncated else ''))
        return sym

    def string_char(self):
        c = self.pop()
        if c != '?':
            return ord(c)
        c = self.pop()
        if c == '$':
            hi = self.pop()
            lo = self.pop()
            return ((ord(hi) - ord('A')) << 4) | (ord(lo) - ord('A'))
        if c.isdigit():
            return b',/\\:. \n\t\'-'[ord(c) - ord('0')]
        if 'a' <= c <= 'z':
            return 0xE1 + ord(c) - ord('a')
        if 'A' <= c <= 'Z':
            return 0xC1 + ord(c) - ord('A')
        self.fail('bad string char')

    def parse_symbol(self):
        """Parse one '?'-prefixed symbol starting at the current position."""
        start = self.i
        if not self.consume('?'):
            self.fail("expected '?'")
        for prefix, kind in _SPECIAL_INTRINSICS:
            if self.startswith(prefix):
                self.i += len(prefix)
                return self.special_intrinsic(self.s[start:], kind)
        return self.declarator(self.s[start:])

    def special_intrinsic(self, mangled, kind):
        if kind == 'string_literal':
            return self.string_literal(mangled)
        if kind in ('vftable', 'vbtable', 'local_vftable', 'rtti_complete_object_locator'):
            text = {'vftable': "`vftable'", 'vbtable': "`vbtable'", 'local_vftable': "`local vftable'",
                    'rtti_complete_object_locator': "`RTTI Complete Object Locator'"}[kind]
            return self.special_table(mangled, kind, text)
        if kind == 'dynamic_initializer':
            return self.init_fini_stub(mangled, False)
        if kind == 'dynamic_atexit_destructor':
            return self.init_fini_stub(mangled, True)
        if kind in ('local_static_guard', 'local_static_thread_guard'):
            return self.local_static_guard(mangled, kind == 'local_static_thread_guard')
        if kind == 'rtti_type_descriptor':
            ty = self.parse_type('result')
            if not self.consume('@8'):
                self.fail('bad RTTI type descriptor')
            sym = Symbol(mangled, kind, var_type=ty)
            sym.rendered_override = ty.text() + " `RTTI Type Descriptor'"
            return sym
        if kind in ('rtti_base_class_array', 'rtti_class_hierarchy_descriptor'):
            text = {"rtti_base_class_array": "`RTTI Base Class Array'",
                    "rtti_class_hierarchy_descriptor": "`RTTI Class Hierarchy Descriptor'"}[kind]
            qn = self.name_scope_chain(NamedIdent(text))
            self.consume('8')
            return Symbol(mangled, kind, qname=qn)
        if kind == 'rtti_base_class_descriptor':
            nv = self.signed()
            vbp = self.signed()
            vbt = self.signed()
            fl = self.unsigned()
            text = "`RTTI Base Class Descriptor at (%d,%d,%d,%d)'" % (nv, vbp, vbt, fl)
            qn = self.name_scope_chain(NamedIdent(text))
            self.consume('8')
            return Symbol(mangled, kind, qname=qn)
        if kind == 'vcall_thunk':
            qn = self.name_scope_chain(NamedIdent("`vcall'"))
            self.consume('$B')
            off = self.unsigned()
            self.consume('A')
            cc = self.calling_convention()
            qn.components[-1] = NamedIdent("`vcall'{%d, {flat}}" % off)
            sym = Symbol(mangled, kind, qname=qn)
            sym.extra['cc'] = cc
            return sym
        self.fail('unsupported special intrinsic ' + kind)


def _escape(text):
    out = []
    for ch in text:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "'":
            out.append("\\'")
        elif ch == '\\':
            out.append('\\\\')
        elif ch in '\a\b\f\n\r\t\v':
            out.append({'\a': '\\a', '\b': '\\b', '\f': '\\f', '\n': '\\n', '\r': '\\r',
                        '\t': '\\t', '\v': '\\v'}[ch])
        elif o == 0:
            out.append('\\0')
        elif o < 0x20 or o == 0x7f:
            out.append('\\x%02X' % o)
        else:
            out.append(ch)
    return ''.join(out)


# ---------------------------------------------------------------------------
# Entry points

def _c_name(name):
    """Classify a name without a leading '?'."""
    if name.startswith('__imp_'):
        inner = demangle(name[len('__imp_'):])
        return Symbol(name, 'import', inner=inner, c_name=inner.c_name)
    if name.startswith('__ehhandler$') or name.startswith('__unwindfunclet$') or name.startswith('__catch$'):
        prefix, _, rest = name.partition('$')
        target = rest
        if prefix == '__unwindfunclet' or prefix == '__catch':
            target = rest.rsplit('$', 1)[0]
        sym = Symbol(name, 'eh_helper', c_name=name)
        sym.extra['helper'] = prefix
        try:
            sym.inner = demangle(target)
        except DemangleError:
            pass
        return sym
    if name.startswith('$SG'):
        return Symbol(name, 'string_label', c_name=name)
    if name.startswith('$LN'):
        return Symbol(name, 'code_label', c_name=name)
    if name.startswith('__real@') or name.startswith('__xmm@') or name.startswith('__mask@'):
        return Symbol(name, 'float_constant', c_name=name)
    if name.startswith('@'):
        body, sep, n = name[1:].rpartition('@')
        if sep and n.isdigit():
            return Symbol(name, 'c_name', c_cc='fastcall', c_name=body, c_arg_bytes=int(n))
        return Symbol(name, 'unknown', c_name=name)
    if name.startswith('_'):
        body = name[1:]
        head, sep, n = body.rpartition('@')
        if sep and n.isdigit() and head:
            return Symbol(name, 'c_name', c_cc='stdcall', c_name=head, c_arg_bytes=int(n))
        return Symbol(name, 'c_name', c_cc='cdecl', c_name=body)
    return Symbol(name, 'c_name', c_cc=None, c_name=name)


def demangle(name: str) -> Symbol:
    """Demangle one name. Raises DemangleError for malformed C++ names."""
    if not name.startswith('?'):
        return _c_name(name)
    p = _Parser(name)
    sym = p.parse_symbol()
    if not p.empty():
        sym.extra['trailing'] = name[p.i:]
    return sym


def try_demangle(name: str) -> Symbol:
    """Like demangle(), but returns kind='unknown' instead of raising."""
    try:
        return demangle(name)
    except (DemangleError, IndexError, KeyError) as e:
        return Symbol(name, 'unknown', c_name=name, extra={'error': str(e)})
