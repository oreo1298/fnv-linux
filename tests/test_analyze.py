import shutil
import subprocess

import pytest

from tools.analyze.abi import compat
from tools.analyze.addresses import AddressMap, densest_cluster, write_alias_map
from tools.analyze.conventions import ConventionReport, classify_pair
from tools.analyze.data import DataReport, subkind
from tools.common.msvc_demangle import demangle
from tools.common.units import Recipe


def d(name):
    return demangle(name)


# --- ABI model ------------------------------------------------------------------

@pytest.mark.parametrize('defn,ref,msvc,linux', [
    # MSVC idiom: __fastcall free function with a dummy EDX parameter standing in for __thiscall.
    ('?q@@YIPAXPAUFoo@@HE@Z', '??_GFoo@@UAEPAXI@Z', 'yes-if-unused', 'no'),
    # One-argument __fastcall vs zero-argument __thiscall: identical under MSVC.
    ('?q@@YIXPAUFoo@@@Z', '?Get@Foo@@QAEXXZ', 'yes', 'if-this-unused'),
    # Member defined, referenced as a free cdecl function without this.
    ('?Get@Foo@@QAEXXZ', '?f@@YAXXZ', 'if-this-unused', 'if-this-unused'),
    # Member defined, referenced as cdecl free function taking self: Linux passes this on the stack.
    ('?Get@Foo@@QAEXXZ', '?f@@YAXPAUFoo@@@Z', 'if-this-unused', 'yes'),
    ('?f@@YAXH@Z', '?f@@YAXHH@Z', 'yes', 'yes'),                 # cdecl: extra args are harmless
    ('?f@@YAXHH@Z', '?f@@YAXH@Z', 'yes-if-unused', 'yes-if-unused'),
    ('?f@@YGXH@Z', '?f@@YGXHH@Z', 'no', 'no'),                   # stdcall: callee pops differ
    ('?f@@YAMXZ', '?f@@YAXXZ', 'no', 'no'),                      # float result left on x87 stack
    ('?f@@YAXM@Z', '?f@@YAXH@Z', 'yes', 'yes'),                  # 4-byte slot either way
    ('?f@@YAXN@Z', '?f@@YAXH@Z', 'no', 'no'),                    # 8-byte slot read, 4 written
    ('?f@@YGXH@Z', '_f@4', 'unknown', 'unknown'),                # same bytes; C name has no return type
    ('?f@@YGXH@Z', '_f@8', 'no', 'no'),
])
def test_compat(defn, ref, msvc, linux):
    assert compat(d(defn), d(ref), 'msvc') == msvc
    assert compat(d(defn), d(ref), 'linux') == linux


def test_classify_pair():
    assert classify_pair(d('?q@@YIXPAUFoo@@@Z'), d('?Get@Foo@@QAEXXZ'))[0] == 'thiscall-fastcall'
    assert classify_pair(d('?Get@Foo@@QAEXXZ'), d('?Get@Bar@@QAEXXZ'))[0] == 'name-only'
    assert classify_pair(d('?f@@YAXH@Z'), d('?g@@YAXHH@Z')) == ('params-differ', 'count')
    assert classify_pair(d('?f@@YAXPAUA@@@Z'), d('?g@@YAXPAUB@@@Z')) == ('params-differ', 'types')
    assert classify_pair(d('?Get@Foo@@QAGXXZ'), d('?f@@YGXPAUFoo@@@Z'))[0] == 'member-free'
    assert classify_pair(d('?f@@YAXXZ'), d('?f@@YGXXZ'))[0] == 'cc-conflict'
    assert classify_pair(d('?f@@YAXXZ'), d('?DAT_00500000@@3HA'))[0] == 'function-as-data'


# --- Synthetic recipe -------------------------------------------------------------

def synthetic_recipe():
    return Recipe({'units': [
        {'source': 'src/a.cpp', 'compiler': 'sp1', 'flags': [],
         'functions': [{'address': '0x00401000', 'symbol': '?Get@Foo@@QAEXXZ', 'size': 16},
                       {'address': '0x00401010', 'symbol': '?Destroy@@YIPAXPAUFoo@@HE@Z', 'size': 16}],
         'symbols': {'?Get@Foo@@QAEXXZ': '0x00401000', '??_7Foo@@6B@': '0x00600000',
                     '?DAT_00700000@@3HA': '0x00700000', '__imp__Sleep@4': '0x00500000'}},
        {'source': 'src/b.cpp', 'compiler': 'sp1', 'flags': [],
         'functions': [{'address': '0x00401020', 'symbol': '?Run@@YAXXZ', 'size': 16}],
         'symbols': {'?Get@FooView@@QAEXXZ': '0x00401000', '??_GFoo@@UAEPAXI@Z': '0x00401010',
                     '??_7FooView@@6B@': '0x00600000', '?g_count@@3HA': '0x00700000',
                     '??_C@_02ABCDEFGH@hi?$AA@': '0x00600100', '__imp__Beep@8': '0x00500004'}},
    ]})


def test_address_map_and_reports(tmp_path):
    amap = AddressMap(synthetic_recipe())
    kinds = {a: i.kind for a, i in amap.infos.items()}
    assert kinds[0x00401000] == 'function'
    assert kinds[0x00600000] == 'vtable'
    assert kinds[0x00700000] == 'global'
    assert kinds[0x00500000] == 'import'
    assert kinds[0x00600100] == 'string'
    assert amap.infos[0x00700000].canonical == 'fnv.d.00700000'

    conv = ConventionReport(amap)
    classes = {(r.address, r.ref_symbol): r.cls for r in conv.rows}
    assert classes[(0x00401000, '?Get@FooView@@QAEXXZ')] == 'name-only'
    assert classes[(0x00401010, '??_GFoo@@UAEPAXI@Z')] == 'thiscall-fastcall'
    s = conv.summary()
    assert s['exclusive_worst_class']['thiscall-fastcall'] == 1
    assert s['unreferenced_function_addresses'] == 1   # ?Run is never referenced

    dr = DataReport(amap)
    assert dr.summary()['by_kind']['vtable'] == 1
    assert subkind(amap, amap.infos[0x00700000]) == 'named'      # one real name is enough


def test_densest_cluster():
    assert densest_cluster([0x1000, 0x1004, 0x1008, 0x9000]) == (0x1000, 0x100c)


@pytest.mark.skipif(not (shutil.which('clang') and shutil.which('ld')), reason='needs clang and GNU ld')
def test_ld_fragments_link(tmp_path):
    """The generated fragments resolve aliases and data in a real i686 link."""
    amap = AddressMap(synthetic_recipe())
    write_alias_map(amap, tmp_path, {})
    src = tmp_path / 'm.c'
    src.write_text(
        'void get(void) __asm__("?Get@Foo@@QAEXXZ");\n'
        'void get(void) {}\n'
        'extern void view(void) __asm__("?Get@FooView@@QAEXXZ");\n'
        'extern int count __asm__("?g_count@@3HA");\n'
        'int _start(void) { view(); return count; }\n')
    obj = tmp_path / 'm.o'
    subprocess.run(['clang', '--target=i686-linux-gnu', '-ffreestanding', '-fno-pic', '-c', str(src),
                    '-o', str(obj)], check=True)
    exe = tmp_path / 'm.elf'
    subprocess.run(['ld', '-m', 'elf_i386', '-e', '_start', '-o', str(exe), str(obj),
                    str(tmp_path / 'aliases.ld'), str(tmp_path / 'data.ld')], check=True)
    nm = subprocess.run(['nm', str(exe)], capture_output=True, text=True, check=True).stdout
    syms = {line.split()[-1]: line.split()[0] for line in nm.splitlines() if len(line.split()) == 3}
    assert syms['?Get@FooView@@QAEXXZ'] == syms['?Get@Foo@@QAEXXZ']
    assert int(syms['?g_count@@3HA'], 16) == 0x00700000
    assert int(syms['fnv.d.00700000'], 16) == 0x00700000
