"""Batch wrapper around llvm-undname for readable MSVC names (optional)."""
from __future__ import annotations

import shutil
import subprocess

_CANDIDATES = ('llvm-undname', 'llvm-undname-18', 'llvm-undname-19', 'llvm-undname-20', 'llvm-undname-17')


def find_undname():
    for c in _CANDIDATES:
        path = shutil.which(c)
        if path:
            return path
    return None


def undname_batch(names, exe=None, chunk=20000):
    """Return {name: readable or None} using llvm-undname. Names must not contain newlines.

    llvm-undname echoes each input line, then prints the result (or an error line),
    then a blank line. Inputs are fed in chunks and re-aligned by the echo.
    """
    exe = exe or find_undname()
    if exe is None:
        raise FileNotFoundError('llvm-undname not found')
    names = [n for n in names if n and '\n' not in n]
    result = {}
    for start in range(0, len(names), chunk):
        part = names[start:start + chunk]
        proc = subprocess.run([exe], input='\n'.join(part) + '\n', capture_output=True, text=True,
                              errors='replace')
        lines = (proc.stdout + proc.stderr).split('\n') if not proc.stdout else proc.stdout.split('\n')
        # stdout holds "echo\nresult\n\n" triples; errors go to stderr, leaving "echo\n\n".
        i = 0
        for n in part:
            while i < len(lines) and lines[i] != n:
                i += 1
            if i >= len(lines):
                break
            i += 1
            out = lines[i] if i < len(lines) else ''
            if out == '' or out.startswith('error:'):
                result[n] = None
            else:
                result[n] = out
                i += 1
    return result
