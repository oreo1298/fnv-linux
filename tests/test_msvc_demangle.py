import pytest

from tools.common.msvc_demangle import demangle, try_demangle, DemangleError
from tools.common.undname import find_undname, undname_batch

# Synthetic decorated names (not taken from upstream) with their llvm-undname rendering.
CASES = [
    ('?f@@YAXH@Z', 'void __cdecl f(int)'),
    ('?g@@YAXXZ', 'void __cdecl g(void)'),
    ('?v@@YAHHZZ', 'int __cdecl v(int, ...)'),
    ('?w@@YAHZZ', 'int __cdecl w(...)'),
    ('?s@@YGHPAX@Z', 'int __stdcall s(void *)'),
    ('?q@@YIXPAUFoo@@HE@Z', 'void __fastcall q(struct Foo *, int, unsigned char)'),
    ('?Get@Foo@@QBEHXZ', 'public: int __thiscall Foo::Get(void) const'),
    ('?Set@Foo@@IAEXM@Z', 'protected: void __thiscall Foo::Set(float)'),
    ('?Make@Foo@@SAPAV1@H@Z', 'public: static class Foo * __cdecl Foo::Make(int)'),
    ('?Run@Foo@@UAEX_N@Z', 'public: virtual void __thiscall Foo::Run(bool)'),
    ('?Hidden@Foo@@AAGXXZ', 'private: void __stdcall Foo::Hidden(void)'),
    ('??0Foo@@QAE@XZ', 'public: __thiscall Foo::Foo(void)'),
    ('??1Foo@@UAE@XZ', 'public: virtual __thiscall Foo::~Foo(void)'),
    ('??_GFoo@@UAEPAXI@Z', "public: virtual void * __thiscall Foo::`scalar deleting dtor'(unsigned int)"),
    ('??_EFoo@@W7AEPAXI@Z',
     "[thunk]: public: virtual void * __thiscall Foo::`vector deleting dtor'`adjustor{8}'(unsigned int)"),
    ('??4Foo@@QAEAAV0@ABV0@@Z', 'public: class Foo & __thiscall Foo::operator=(class Foo const &)'),
    ('??BFoo@@QBEHXZ', 'public: int __thiscall Foo::operator int(void) const'),
    ('?x@@3HA', 'int x'),
    ('?p@@3PBDB', 'char const *p'),
    ('?pp@@3QBQBDB', 'char const *const *const pp'),
    ('?m@Foo@@2_NA', 'public: static bool Foo::m'),
    ('?n@ns@@3PAY01HA', 'int (*ns::n)[2]'),
    ('?fp@@3P6AXH@ZA', 'void (__cdecl *fp)(int)'),
    ('?t@@3V?$Box@H@@A', 'class Box<int> t'),
    ('?t2@@3V?$Pair@PAVFoo@@$0EAA@@@A', 'class Pair<class Foo *, 1024> t2'),
    ('?Call@@YAXP8Foo@@AEXH@Z@Z', 'void __cdecl Call(void (__thiscall Foo::*)(int))'),
    ('??_7Foo@@6B@', "const Foo::`vftable'"),
    ('??_7Foo@@6BBar@@@', "const Foo::`vftable'{for `Bar'}"),
    ('??_8Foo@@7B@', "const Foo::`vbtable'"),
    ('??_R0?AVFoo@@@8', "class Foo `RTTI Type Descriptor'"),
    ('??__Eg_init@@YAXXZ', "void __cdecl `dynamic initializer for 'g_init''(void)"),
    ('??_C@_05ABCDEFGH@hello?$AA@', '"hello"'),
    ('??_C@_01ABCDEFGH@?6?$AA@', '"\\n"'),
    ('?Local@@YAXXZ', 'void __cdecl Local(void)'),
    ('?y@?A0x1234abcd@@3HA', "int `anonymous namespace'::y"),
]


@pytest.mark.parametrize('mangled,expected', CASES)
def test_render(mangled, expected):
    assert demangle(mangled).render() == expected


@pytest.mark.skipif(find_undname() is None, reason='llvm-undname not installed')
def test_matches_llvm_undname():
    oracle = undname_batch([m for m, _ in CASES])
    for mangled, _ in CASES:
        assert oracle[mangled] is not None, mangled
        assert demangle(mangled).render() == oracle[mangled], mangled


def test_structure_member_vs_free():
    m = demangle('?Get@Foo@@QBEHXZ')
    assert m.kind == 'function' and m.is_member and not m.is_static_member
    assert m.cc == 'thiscall' and m.this_quals == 'const' and m.access == 'public'
    assert m.params == () and m.ret == 'int'
    assert m.scope == ('Foo',) and m.unqualified == 'Get' and m.qualified == 'Foo::Get'

    f = demangle('?q@@YIXPAUFoo@@HE@Z')
    assert not f.is_member and f.cc == 'fastcall'
    assert f.params == ('struct Foo *', 'int', 'unsigned char')

    s = demangle('?Make@Foo@@SAPAV1@H@Z')
    assert s.is_static_member and not s.is_member and s.cc == 'cdecl'

    v = demangle('?Run@Foo@@UAEX_N@Z')
    assert v.is_virtual and v.is_member

    t = demangle('??_EFoo@@W7AEPAXI@Z')
    assert t.is_thunk and t.sig.static_adjust == 8 and t.special == 'vector_deleting_dtor'


def test_specials():
    assert demangle('??0Foo@@QAE@XZ').special == 'ctor'
    assert demangle('??1Foo@@UAE@XZ').special == 'dtor'
    assert demangle('??_GFoo@@UAEPAXI@Z').special == 'scalar_deleting_dtor'
    assert demangle('??4Foo@@QAEAAV0@ABV0@@Z').special == 'operator'
    vt = demangle('??_7Foo@@6BBar@@@')
    assert vt.kind == 'vftable' and vt.scope == ('Foo',) and vt.table_target.text() == 'Bar'


def test_variadic_and_void():
    assert demangle('?g@@YAXXZ').params == ()
    v = demangle('?v@@YAHHZZ')
    assert v.params == ('int',) and v.variadic


def test_param_backrefs():
    # 'PAUFoo@@' is memorized as param 0; '0' refers back to it.
    s = demangle('?h@@YAXPAUFoo@@0@Z')
    assert s.params == ('struct Foo *', 'struct Foo *')


def test_c_names():
    c = demangle('_plain')
    assert c.kind == 'c_name' and c.cc == 'cdecl' and c.c_name == 'plain'
    s = demangle('_Sleep@4')
    assert s.cc == 'stdcall' and s.c_name == 'Sleep' and s.c_arg_bytes == 4
    f = demangle('@fast@8')
    assert f.cc == 'fastcall' and f.c_name == 'fast' and f.c_arg_bytes == 8
    i = demangle('__imp__Sleep@4')
    assert i.kind == 'import' and i.inner.c_name == 'Sleep'
    i2 = demangle('__imp_?f@@YAXH@Z')
    assert i2.kind == 'import' and i2.inner.kind == 'function'
    assert demangle('$SG1234').kind == 'string_label'
    assert demangle('__real@3f800000').kind == 'float_constant'
    eh = demangle('__ehhandler$?f@@YAXH@Z')
    assert eh.kind == 'eh_helper' and eh.inner.qualified == 'f'


def test_malformed():
    with pytest.raises(DemangleError):
        demangle('?Bad@@QAEAPAVFoo@@XZ')   # reference without pointee qualifier
    assert try_demangle('?Bad@@QAEAPAVFoo@@XZ').kind == 'unknown'
