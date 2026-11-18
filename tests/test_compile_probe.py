import shutil
import subprocess
from pathlib import Path

import pytest

from tools.compile_probe.__main__ import BASE_FLAGS, SHIM, template, translate_flags

needs_clang = pytest.mark.skipif(shutil.which('clang++') is None, reason='needs clang')


def test_float_math_is_sse(tmp_path):
    """Scalar float math uses SSE registers, not x87 (decision recorded in PLAN.md)."""
    if shutil.which('clang') is None:
        pytest.skip('needs clang')
    src = tmp_path / 'f.c'
    src.write_text('float f(float a, float b) { return a * b + 1.0f; }\n')
    asm = subprocess.run(['clang'] + BASE_FLAGS + ['-O2', '-S', '-o', '-', str(src)],
                         capture_output=True, text=True, check=True).stdout
    assert 'mulss' in asm and 'fmul' not in asm


def test_translate_flags():
    assert translate_flags(['/MT', '/O2', '/EHsc', '/Gy'], False) == \
        ['-D_MT', '-O2', '-fexceptions', '-fcxx-exceptions', '-D_CPPUNWIND']
    assert translate_flags(['/Od', '/EHs-c-'], False) == ['-O0', '-fno-exceptions']
    assert translate_flags(['/Dmemcpy=x', '/O2'], True) == ['-Dmemcpy=x', '-O2']


def test_template():
    assert template("use of undeclared identifier 'Foo'") == "use of undeclared identifier 'X'"
    assert template("size of array element of type 'T' (12 bytes)") == "size of array element of type 'X' (N bytes)"


def _compile(tmp_path, source, lang='c++', run=False, extra=()):
    src = tmp_path / ('t.cpp' if lang == 'c++' else 't.c')
    src.write_text(source)
    out = tmp_path / 't.out'
    cmd = ['clang++' if lang == 'c++' else 'clang'] + BASE_FLAGS
    cmd += ['-include', str(SHIM / 'fnv_prelude.h'), '-isystem', str(SHIM), '-O2', str(src)]
    cmd += list(extra)
    cmd += ['-o', str(out)] if run else ['-fsyntax-only']
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    if run:
        r = subprocess.run([str(out)], capture_output=True, text=True)
        return r.returncode, r.stdout
    return 0, ''


@needs_clang
def test_shim_headers_parse_as_cpp_and_c(tmp_path):
    body = '#include <windows.h>\n#include <d3d9.h>\n#include <commctrl.h>\n#include <crtdefs.h>\n'
    _compile(tmp_path, body + '#include <intrin.h>\nint main() { return 0; }\n')
    _compile(tmp_path, body + 'int main(void) { return 0; }\n', lang='c')


@needs_clang
def test_shim_layouts(tmp_path):
    src = '''#include <windows.h>
#include <d3d9.h>
#include <intrin.h>
#include <stddef.h>
#define CHECK(c) typedef char check_##__LINE__[(c) ? 1 : -1]
CHECK(sizeof(DWORD) == 4 && sizeof(LONG) == 4 && sizeof(HANDLE) == 4);
CHECK(sizeof(CRITICAL_SECTION) == 24);
CHECK(sizeof(SYSTEMTIME) == 16 && sizeof(FILETIME) == 8);
CHECK(sizeof(WIN32_FIND_DATAA) == 320);
CHECK(sizeof(D3DMATRIX) == 64 && sizeof(D3DSURFACE_DESC) == 32);
CHECK(sizeof(__m128) == 16 && __alignof(__m128) == 16 && offsetof(__m128, m128_f32) == 0);
CHECK(sizeof(__m64) == 8 && sizeof(__m128i) == 16);
CHECK(sizeof(long double) == 8);   /* -mlong-double-64: MSVC's long double */
#ifndef __SSE2__
#error SSE2 floating point expected
#endif
int main() { return 0; }
'''
    _compile(tmp_path, src)


@needs_clang
def test_sse_shim_semantics(tmp_path):
    src = r'''#include <intrin.h>
#include <stdio.h>
int main() {
  __m128 a = _mm_setr_ps(1, 2, 3, 4), b = _mm_set_ps1(2);
  __m128 s = _mm_shuffle_ps(a, b, _MM_SHUFFLE(0, 1, 2, 3));
  __m128 n = _mm_set_ps1(__builtin_nanf(""));
  __m128 mn = _mm_min_ps(n, a);        /* MINPS returns the second operand on NaN */
  __m128 r = _mm_rsqrt_ss(_mm_set_ss(4.0f));
  printf("%g %g %g %g|%d|%g|%d\n", s.m128_f32[0], s.m128_f32[1], s.m128_f32[2], s.m128_f32[3],
         _mm_movemask_ps(_mm_cmplt_ps(a, b)), mn.m128_f32[2], r.m128_f32[0] > 0.49f && r.m128_f32[0] < 0.51f);
  return 0;
}
'''
    rc, out = _compile(tmp_path, src, run=True)
    assert rc == 0
    assert out.strip() == '4 3 2 2|1|3|1'
