"""Phase 1 linkage and ABI analysis of fnv_decomp. No game files needed.

usage: python3 -m tools.analyze [--upstream DIR] [--out DIR] [--no-locations]
                                [--vtable-sample N] [--jobs N] [step ...]

steps: aliases conventions data vtables (default: all)

Outputs go to out/analyze/ (gitignored): aliases.{json,csv,ld}, data.ld,
conventions.csv, data.csv, vtables.csv, vtable_slots.csv, summary.json and
summary.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from tools.analyze.addresses import AddressMap, write_alias_map
from tools.common.msvc_demangle import Symbol
from tools.common.source_index import SourceIndex
from tools.common.undname import find_undname, undname_batch
from tools.common.units import load_recipe

ROOT = Path(__file__).resolve().parents[2]
STEPS = ['aliases', 'conventions', 'data', 'vtables']


def readable_names(amap: AddressMap, names, use_undname=True):
    """name -> readable text; llvm-undname when available, else our own renderer."""
    names = sorted(set(names))
    result = {}
    if use_undname and find_undname():
        result = {k: v for k, v in undname_batch([n for n in names if n.startswith('?')]).items() if v}
    for n in names:
        if n not in result:
            s = amap.sym(n)
            if s.kind == 'unknown':
                result[n] = ''
            elif s.kind == 'c_name':
                result[n] = '%s%s' % (s.c_name, ' [%s]' % s.c_cc if s.c_cc else '')
            else:
                result[n] = s.render()
    return result


def log(msg):
    print('[analyze %s] %s' % (time.strftime('%H:%M:%S'), msg), file=sys.stderr, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--upstream', default=str(ROOT / 'upstream' / 'fnv_decomp'))
    ap.add_argument('--out', default=str(ROOT / 'out' / 'analyze'))
    ap.add_argument('--no-locations', action='store_true', help='skip source line lookup (faster)')
    ap.add_argument('--no-undname', action='store_true', help='do not use llvm-undname for readable names')
    ap.add_argument('--vtable-sample', type=int, default=0,
                    help='parse only N units (0 = every unit with a vtable reference)')
    ap.add_argument('--jobs', type=int, default=0, help='parallel clang jobs for the vtable AST pass')
    ap.add_argument('steps', nargs='*', choices=STEPS + [[]], default=[])
    args = ap.parse_args(argv)
    steps = args.steps or STEPS

    upstream = Path(args.upstream)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log('loading %s' % (upstream / 'build/units.json'))
    recipe = load_recipe(upstream)
    amap = AddressMap(recipe)
    log('%d units, %d function addresses, %d bindings over %d addresses' % (
        len(recipe.units), len(recipe.function_addresses), recipe.binding_count, len(recipe.references)))
    all_names = set(recipe.name_addresses)
    readable = readable_names(amap, all_names, not args.no_undname)
    index = None if args.no_locations else SourceIndex(upstream)

    summary_path = out / 'summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    summary['recipe'] = {
        'units': len(recipe.units), 'function_addresses': len(recipe.function_addresses),
        'symbol_bindings': recipe.binding_count, 'bound_addresses': len(recipe.references),
        'distinct_names': len(all_names), 'eh_tails': len(recipe.eh_tails),
        'malformed_names': sorted(n for n in all_names if amap.sym(n).kind == 'unknown'),
        'names_bound_to_several_addresses': len(amap.colliding_names()),
        'address_kinds': dict(amap.kind_counts()),
    }

    if 'aliases' in steps:
        log('alias map')
        skipped = write_alias_map(amap, out, readable)
        summary['aliases'] = {'ld_names_skipped_for_collisions': skipped}

    if 'conventions' in steps:
        from tools.analyze.conventions import ConventionReport
        log('calling conventions')
        conv = ConventionReport(amap)
        summary['conventions'] = conv.summary()
        log('writing conventions.csv (source locations: %s)' % ('no' if index is None else 'yes'))
        n = conv.write_csv(out / 'conventions.csv', index, readable)
        summary['conventions']['csv_rows'] = n

    if 'data' in steps:
        from tools.analyze.data import DataReport
        log('data report')
        dr = DataReport(amap)
        summary['data'] = dr.summary()
        dr.write_csv(out / 'data.csv', readable)

    if 'vtables' in steps:
        from tools.analyze.vtables import VtableReport
        log('vtable report')
        vr = VtableReport(amap, upstream, jobs=args.jobs, sample=args.vtable_sample, log=log)
        summary['vtables'] = vr.summary()
        vr.write(out, readable)

    summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True))
    from tools.analyze.report import write_markdown
    write_markdown(summary, out / 'summary.md')
    log('done: %s' % out)


if __name__ == '__main__':
    main()
