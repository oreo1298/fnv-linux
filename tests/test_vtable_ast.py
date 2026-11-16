"""The vftable layout computed from libclang cursors matches Clang's own MSVC vftable layout."""
import re
import shutil
import subprocess

import pytest

try:
    from tools.analyze import vtable_ast
    vtable_ast.cindex()
    HAVE_LIBCLANG = True
except Exception:  # pragma: no cover - environment dependent
    HAVE_LIBCLANG = False

pytestmark = pytest.mark.skipif(not HAVE_LIBCLANG or shutil.which('clang++') is None,
                                reason='needs libclang and clang++')

SOURCE = '''
struct Base { virtual ~Base() {} virtual void a() {} virtual void b(int) {} virtual void b(float) {} };
struct Derived : Base { void a() {} virtual void c() {} virtual void b(double) {} };
struct Other { virtual void o() {} };
struct Multi : Base, Other { void o() {} virtual void m() {} };
struct NoDtor { virtual int f() { return 0; } virtual int g() { return 1; } };
struct Leaf : NoDtor { int g() { return 2; } virtual ~Leaf() {} };
template <class T> struct Arr { virtual ~Arr() {} virtual void Grow(int) {} T* p; };
struct IntArr : Arr<int> { virtual void Extra() {} };
Derived d; Multi m; Leaf l; IntArr ia;
'''

VFT_RE = re.compile(r"^VFTable for '([^']+)'(?: in '([^']+)')? \((\d+) entr")


def msvc_oracle(tmp_path):
    """{(class, for-base or None): [slot texts]} from clang -fdump-vtable-layouts on an MSVC target."""
    src = tmp_path / 'v.cpp'
    src.write_text(SOURCE)
    out = subprocess.run(['clang++', '--target=i686-pc-windows-msvc', '-fms-extensions', '-Xclang',
                          '-fdump-vtable-layouts', '-S', '-emit-llvm', '-o', '/dev/null', str(src)],
                         capture_output=True, text=True).stdout
    tables, cur = {}, None
    for line in out.splitlines():
        m = VFT_RE.match(line)
        if m:
            base, cls = m.group(1), m.group(2)
            cur = (cls or base, base if cls else None)
            tables[cur] = []
        elif cur and re.match(r'^\s+\d+ \| ', line):
            text = line.split('|', 1)[1].strip()
            if not text.endswith('RTTI'):
                tables[cur].append(text)
        elif not line.strip():
            cur = None
    return tables


def test_layouts_match_clang_msvc(tmp_path):
    ci = vtable_ast.cindex()
    oracle = msvc_oracle(tmp_path)
    src = tmp_path / 'v.cpp'
    tu = ci.Index.create().parse(str(src), args=['-x', 'c++', '--target=i686-linux-gnu', '-std=gnu++14'])
    classes = vtable_ast.index_classes(tu)

    def ours(cls, target=None):
        return vtable_ast.view_layout(classes[cls][0], target)

    # (class, oracle key): the oracle names a class's primary vftable after the base that owns it.
    checks = [('Base', ('Base', None)), ('Derived', ('Derived', 'Base')), ('Multi', ('Multi', 'Base')),
              ('Leaf', ('Leaf', 'NoDtor')), ('IntArr', ('IntArr', 'Arr'))]
    for cls, key in checks:
        expected = oracle[key]
        got = ours(cls)
        assert got['status'] == 'ok', got
        assert got['slots'] == len(expected), (cls, got['slot_names'], expected)
        dtor_expected = next((i for i, t in enumerate(expected) if 'scalar deleting' in t), None)
        assert got['dtor_slot'] == dtor_expected, (cls, got, expected)
        # Slot order: compare method names.
        names = [re.sub(r'.*::(~?\w+)\(.*', r'\1', t) for t in expected]
        assert [n.split('<')[0] for n in got['slot_names']] == [n.split('<')[0] for n in names], (cls, got, names)

    other = ours('Multi', 'Other')
    assert other['slots'] == len(oracle[('Multi', 'Other')]) == 1
    assert other['dtor_slot'] is None
