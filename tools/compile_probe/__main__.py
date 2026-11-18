"""Phase 2: compile every fnv_decomp unit for i686 Linux with Clang, as a baseline.

usage: python3 -m tools.compile_probe [--mode syntax|obj] [--jobs N] [--only TEXT] [--limit N]
                                      [--upstream DIR] [--out DIR] [--error-limit N]

Each unit from build/units.json is compiled from the pristine upstream checkout
with

  clang++ --target=i686-linux-gnu -fms-extensions -fms-compatibility -fasm-blocks
          -malign-double -include shim/include/fnv_prelude.h -isystem shim/include
          -I <upstream>/include  <MSVC flags translated>  <unit>

(-fsyntax-only in syntax mode, -c into out/compile_probe/obj in obj mode).
Results go to out/compile_probe/<mode>/: results.json (per unit), histogram.csv
(error message templates by units affected and occurrences) and summary.md.
Nothing upstream is modified.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / 'shim' / 'include'
TARGET = 'i686-linux-gnu'
DEFAULT_STD = 'gnu++14'
BASE_FLAGS = ['--target=' + TARGET, '-fms-extensions', '-fms-compatibility', '-fasm-blocks', '-malign-double',
              # Clang's MS-compat behaviour level, not _MSC_VER (the prelude sets that to 1500).
              # Below 19 Clang turns off char16_t/char32_t, which libstdc++ needs.
              '-fms-compatibility-version=19.00',
              # MSVC's long double is 64-bit. With -malign-double an 80-bit long double would be
              # 12 bytes with 8-byte alignment, which libstdc++'s <cmath> arrays reject.
              '-mlong-double-64',
              # MSVC 2008 has no two-phase lookup: template bodies are only checked when
              # instantiated. Clang enables this emulation by default for MSVC targets only.
              '-fdelayed-template-parsing',
              # Floating point uses SSE2 (decided over x87): scalar float/double math in SSE
              # registers, and the SSE builtins the intrinsics need (_mm_prefetch, _mm_setcsr).
              # The game already requires an SSE2-class CPU.
              '-msse2', '-mfpmath=sse']

DIAG_RE = re.compile(r'^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+): (?P<sev>fatal error|error|warning): '
                     r'(?P<msg>.*?)(?: \[(?P<flag>-W[^\]]+)\])?$')


def translate_flags(msvc_flags, is_c):
    """MSVC options -> Clang options (only those that affect parsing or codegen semantics)."""
    out = []
    eh = None
    for f in msvc_flags:
        fl = f.lower()
        if f.startswith('/D'):
            out.append('-D' + f[2:])
        elif fl == '/ehsc' or fl == '/ehs':
            eh = True
        elif fl == '/ehs-c-':
            eh = False
        elif fl == '/o2' or fl == '/o1':
            out.append('-O2' if fl == '/o2' else '-Os')
        elif fl == '/od':
            out.append('-O0')
        elif fl == '/fp:fast':
            out.append('-ffast-math')
        elif fl == '/mt':
            out.append('-D_MT')
        # /Gy /GS /GS- /GF /Oy /Oy- /Ob0 /Ob1: no effect on what we probe here
    if not is_c:
        if eh is True:
            out += ['-fexceptions', '-fcxx-exceptions', '-D_CPPUNWIND']
        elif eh is False:
            out += ['-fno-exceptions']
    return out


def command(unit, upstream: Path, mode: str, obj_dir: Path, error_limit: int, std=None):
    src = upstream / unit['source']
    is_c = src.suffix == '.c'
    cmd = ['clang' if is_c else 'clang++'] + BASE_FLAGS
    if std and not is_c:
        cmd.append('-std=' + std)
    cmd += ['-include', str(SHIM / 'fnv_prelude.h'), '-isystem', str(SHIM),
            '-I', str(upstream / 'include')]
    cmd += translate_flags(unit['flags'], is_c)
    cmd += ['-ferror-limit=%d' % error_limit, '-fno-color-diagnostics', '-fno-caret-diagnostics',
            # -w keeps Clang's default-error diagnostics (e.g. ISO C++17 'register'), unlike
            # -Wno-everything, so both modes count the same errors.
            '-w']
    if mode == 'syntax':
        cmd.append('-fsyntax-only')
    else:
        obj = obj_dir / (unit['source'].replace('/', '__') + '.%d.o' % unit['_index'])
        cmd += ['-c', '-o', str(obj)]
    cmd.append(str(src))
    return cmd


NOTE_RE = re.compile(r'^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+): note: (?P<msg>.*)$')


def _rel(f, upstream):
    try:
        return str(Path(f).resolve().relative_to(upstream.resolve()))
    except ValueError:
        try:
            return 'shim:' + str(Path(f).resolve().relative_to(SHIM))
        except ValueError:
            return 'system:' + Path(f).name


_QUOTED = re.compile(r"'[^']*'")
_NUM = re.compile(r'\b\d+\b')


def template(msg: str) -> str:
    """Error message with identifiers and numbers abstracted, for the histogram."""
    return _NUM.sub('N', _QUOTED.sub("'X'", msg))


def run_unit(unit, upstream, mode, obj_dir, error_limit, timeout, std=None):
    cmd = command(unit, upstream, mode, obj_dir, error_limit, std)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=timeout,
                           cwd=str(upstream))
        rc, err = p.returncode, p.stderr
        status = None
    except subprocess.TimeoutExpired:
        rc, err, status = -1, '', 'timeout'
    dt = time.time() - t0
    diags = []
    for line in err.splitlines():
        m = DIAG_RE.match(line)
        if m and m.group('sev') != 'warning':
            diags.append({'file': _rel(m.group('file'), upstream), 'line': int(m.group('line')),
                          'sev': m.group('sev'), 'msg': m.group('msg')})
        elif diags and ': note: ' in line and len(diags[-1].setdefault('notes', [])) < 2:
            nm = NOTE_RE.match(line)
            if nm:
                diags[-1]['notes'].append({'file': _rel(nm.group('file'), upstream), 'line': int(nm.group('line')),
                                           'msg': nm.group('msg')})
    if status is None:
        if rc == 0:
            status = 'ok'
        elif any(d['sev'] == 'fatal error' for d in diags):
            status = 'fatal'
        elif diags:
            status = 'errors'
        else:
            status = 'crash' if rc < 0 or 'PLEASE submit a bug report' in err else 'failed'
    res = {'index': unit['_index'], 'source': unit['source'], 'status': status, 'seconds': round(dt, 2),
           'errors': len(diags), 'diagnostics': diags[:error_limit]}
    if status in ('crash', 'failed'):
        res['tail'] = err[-2000:]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--upstream', default=str(ROOT / 'upstream' / 'fnv_decomp'))
    ap.add_argument('--out', default=str(ROOT / 'out' / 'compile_probe'))
    ap.add_argument('--mode', choices=['syntax', 'obj'], default='syntax')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 2)
    ap.add_argument('--only', action='append', default=[], help='units whose source contains TEXT')
    ap.add_argument('--limit', type=int, default=0, help='first N matching units (0 = all)')
    ap.add_argument('--sample', type=int, default=0, help='N units spread evenly over the list')
    ap.add_argument('--error-limit', type=int, default=50)
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--print-command', action='store_true')
    ap.add_argument('--std', default=DEFAULT_STD,
                    help='C++ dialect (default %(default)s: the closest to MSVC 2008 that libstdc++ accepts; '
                         'Clang\'s own default, gnu++17, rejects register and dynamic exception '
                         'specifications and crashes Clang on 5 units)')
    ap.add_argument('--tag', default='', help='suffix for the output directory')
    ap.add_argument('--recategorize', action='store_true',
                    help='recompute categories and summaries from an existing results.json')
    args = ap.parse_args(argv)
    if args.recategorize:
        return recategorize(Path(args.upstream).resolve(),
                            Path(args.out) / (args.mode + ('-' + args.tag if args.tag else '')))

    upstream = Path(args.upstream).resolve()
    units = json.loads((upstream / 'build' / 'units.json').read_text())['units']
    for i, u in enumerate(units):
        u['_index'] = i
    if args.only:
        units = [u for u in units if any(t in u['source'] for t in args.only)]
    if args.sample:
        step = max(1, len(units) // args.sample)
        units = units[::step][:args.sample]
    if args.limit:
        units = units[:args.limit]
    out = Path(args.out) / (args.mode + ('-' + args.tag if args.tag else ''))
    out.mkdir(parents=True, exist_ok=True)
    obj_dir = Path(args.out) / 'obj'
    if args.mode == 'obj':
        obj_dir.mkdir(parents=True, exist_ok=True)
    if args.print_command:
        for u in units:
            print(' '.join(command(u, upstream, args.mode, obj_dir, args.error_limit, args.std)))
        return

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(run_unit, u, upstream, args.mode, obj_dir, args.error_limit, args.timeout, args.std)
                for u in units]
        for n, f in enumerate(as_completed(futs), 1):
            results.append(f.result())
            if n % 100 == 0 or n == len(futs):
                ok = sum(1 for r in results if r['status'] == 'ok')
                print('[compile_probe] %d/%d done, %d ok, %.0fs' % (n, len(futs), ok, time.time() - t0),
                      file=sys.stderr, flush=True)
    results.sort(key=lambda r: r['index'])
    from tools.compile_probe.categories import categorize_results
    summary = summarize(results, args.mode, time.time() - t0)
    summary['categories'] = categorize_results(results, upstream)
    summary['std'] = args.std
    summary['flags'] = BASE_FLAGS
    (out / 'results.json').write_text(json.dumps({'summary': summary, 'units': results}, indent=1))
    write_histogram(results, out / 'histogram.csv')
    (out / 'summary.md').write_text(markdown(summary))
    print(markdown(summary))


def recategorize(upstream: Path, out: Path):
    from tools.compile_probe.categories import categorize_results
    doc = json.loads((out / 'results.json').read_text())
    results = doc['units']
    old = doc['summary']
    summary = summarize(results, old['mode'], old['seconds'])
    for k in ('std', 'flags'):
        if k in old:
            summary[k] = old[k]
    summary['categories'] = categorize_results(results, upstream)
    (out / 'results.json').write_text(json.dumps({'summary': summary, 'units': results}, indent=1))
    write_histogram(results, out / 'histogram.csv')
    (out / 'summary.md').write_text(markdown(summary))
    print(markdown(summary))


def summarize(results, mode, seconds):
    status = Counter(r['status'] for r in results)
    by_template_units = defaultdict(set)
    by_template_count = Counter()
    first = Counter()
    by_file_units = defaultdict(set)
    for r in results:
        seen = set()
        for i, d in enumerate(r['diagnostics']):
            t = template(d['msg'])
            by_template_count[t] += 1
            by_template_units[t].add(r['index'])
            by_file_units[d['file'].split(':')[0] if d['file'].startswith(('shim:', 'system:')) else
                          ('include/' if d['file'].startswith('include/') else 'unit')].add(r['index'])
            if i == 0:
                first[t] += 1
    top = sorted(by_template_units, key=lambda t: (-len(by_template_units[t]), -by_template_count[t]))
    return {
        'mode': mode, 'units': len(results), 'seconds': round(seconds),
        'status': dict(status),
        'pass_rate': round(100.0 * status.get('ok', 0) / max(1, len(results)), 1),
        'top_errors': [{'template': t, 'units': len(by_template_units[t]), 'occurrences': by_template_count[t],
                        'first_error_in': first.get(t, 0)} for t in top[:40]],
        'error_location_units': {k: len(v) for k, v in by_file_units.items()},
    }


def write_histogram(results, path):
    units = defaultdict(set)
    count = Counter()
    example = {}
    for r in results:
        for d in r['diagnostics']:
            t = template(d['msg'])
            units[t].add(r['index'])
            count[t] += 1
            example.setdefault(t, '%s:%d' % (d['file'], d['line']))
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['units', 'occurrences', 'template', 'example_location'])
        for t in sorted(units, key=lambda t: (-len(units[t]), -count[t])):
            w.writerow([len(units[t]), count[t], t, example[t]])


def markdown(s):
    lines = ['### %s mode: %d units, %.1f%% pass (%ds)' % (s['mode'], s['units'], s['pass_rate'], s['seconds']),
             '', 'Status: ' + ', '.join('%s %d' % kv for kv in sorted(s['status'].items())), '']
    if s.get('categories'):
        lines += ['Root-cause categories (units with at least one such error; first = units whose first '
                  'error is in the category):', '',
                  '| # | category | units | first |', '|---|---|---|---|']
        for i, c in enumerate(s['categories'], 1):
            lines.append('| %d | %s | %d | %d |' % (i, c['category'], c['units'], c['first']))
        lines.append('')
    lines += ['Clang message templates:', '',
             '| # | units | occurrences | first error in | error (identifiers as \'X\', numbers as N) |',
             '|---|---|---|---|---|']
    for i, e in enumerate(s['top_errors'][:25], 1):
        lines.append('| %d | %d | %d | %d | %s |' % (i, e['units'], e['occurrences'], e['first_error_in'],
                                                   e['template'].replace('|', '\\|')))
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    main()
