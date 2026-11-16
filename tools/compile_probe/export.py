"""Export compile-probe results for the repo: status/compile_probe_units.tsv (one row per unit:
syntax and object status, error count, first-error root-cause category) and a per-area
rollup in Markdown. Contains paths, counts and our category names only, never upstream code
or messages.

usage: python3 -m tools.compile_probe.export [--out-dir out/compile_probe] [--status-dir status]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def area(source: str) -> str:
    parts = source.split('/')
    if parts[0] == 'third_party':
        return 'third_party'
    if len(parts) > 2:
        return '/'.join(parts[:2])
    return 'src (top level)'


def load(path):
    doc = json.loads(Path(path).read_text())
    return {u['index']: u for u in doc['units']}, doc['summary']


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out-dir', default=str(ROOT / 'out' / 'compile_probe'))
    ap.add_argument('--status-dir', default=str(ROOT / 'status'))
    args = ap.parse_args(argv)
    syn, ssum = load(Path(args.out_dir) / 'syntax' / 'results.json')
    obj, osum = load(Path(args.out_dir) / 'obj' / 'results.json')
    status_dir = Path(args.status_dir)
    status_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in sorted(syn):
        s, o = syn[i], obj.get(i, {})
        first = next((d.get('category', '') for d in s['diagnostics'] if 'too many errors' not in d['msg']), '')
        cats = sorted({d.get('category', '') for d in s['diagnostics'] if d.get('category')})
        rows.append((i, s['source'], s['status'], o.get('status', ''), s['errors'], first, '; '.join(cats)))
    with open(status_dir / 'compile_probe_units.tsv', 'w', encoding='utf-8') as fh:
        fh.write('# Phase 2 compile probe, per unit. index = position in build/units.json.\n')
        fh.write('# std=%s flags=%s\n' % (ssum.get('std'), ' '.join(ssum.get('flags', []))))
        fh.write('index\tsource\tsyntax\tobject\terrors\tfirst_error_category\tall_categories\n')
        for r in rows:
            fh.write('\t'.join(str(x) for x in r) + '\n')
    by_area = defaultdict(Counter)
    for i, src, st, ost, *_ in rows:
        by_area[area(src)]['units'] += 1
        by_area[area(src)]['syntax_ok'] += st == 'ok'
        by_area[area(src)]['obj_ok'] += ost == 'ok'
    lines = ['| area | units | -fsyntax-only ok | -c ok |', '|---|---|---|---|']
    for a, c in sorted(by_area.items(), key=lambda kv: -kv[1]['units']):
        lines.append('| %s | %d | %d (%.0f%%) | %d (%.0f%%) |' % (
            a, c['units'], c['syntax_ok'], 100.0 * c['syntax_ok'] / c['units'],
            c['obj_ok'], 100.0 * c['obj_ok'] / c['units']))
    (status_dir / 'compile_probe_areas.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
