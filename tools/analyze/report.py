"""Markdown rendering of out/analyze/summary.json (counts only; no upstream code)."""
from __future__ import annotations

import json

CLASS_NOTES = {
    'name-only': 'same convention, kind and parameters: harmless, needs only linkage by address',
    'thiscall-fastcall': '__thiscall on one side, __fastcall on the other (the MSVC ECX idiom)',
    'member-free': 'member on one side, free/static on the other, same convention',
    'cc-conflict': 'any other convention difference',
    'params-differ': 'same convention and kind, different parameters or return type',
    'function-as-data': 'the function address is also referenced through a data symbol',
    'identical': 'referenced only under its definition name (or not at all)',
}


def _table(rows, header):
    out = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)


def write_markdown(s, path):
    lines = ['# Phase 1 analysis summary', '']
    r = s.get('recipe', {})
    if r:
        lines += ['## Recipe', '', _table([
            ('units', r['units']), ('function addresses', r['function_addresses']),
            ('EH tails', r['eh_tails']), ('symbol bindings', r['symbol_bindings']),
            ('bound addresses', r['bound_addresses']), ('distinct names', r['distinct_names']),
            ('names bound to several addresses', r['names_bound_to_several_addresses']),
            ('malformed names', len(r.get('malformed_names', []))),
        ], ['what', 'count']), '']
        lines += ['Address kinds:', '', _table(sorted(r['address_kinds'].items(), key=lambda kv: -kv[1]),
                                               ['kind', 'addresses']), '']
    c = s.get('conventions')
    if c:
        lines += ['## Calling conventions', '',
                  'Per function address, the worst class over all (definition, other name) pairs '
                  '(severity order as listed); `linux` is the worst i686-Linux verdict for that address.', '']
        order = ['cc-conflict', 'thiscall-fastcall', 'member-free', 'function-as-data', 'params-differ',
                 'name-only', 'identical']
        rows = []
        for k in order:
            n = c['exclusive_worst_class'].get(k, 0)
            eq = c.get('address_equivalence', {}).get(k, {})
            linux = ', '.join('%s %d' % (kk[6:], v) for kk, v in sorted(eq.items()) if kk.startswith('linux:'))
            rows.append((k, n, c['inclusive_class'].get(k, '') if k != 'identical' else '',
                         c['pairs_by_class'].get(k, '') if k != 'identical' else '', linux, CLASS_NOTES.get(k, '')))
        lines += [_table(rows, ['class', 'addresses (worst)', 'addresses (any)', 'name pairs', 'linux verdicts',
                                'meaning']), '']
        lines += ['Function addresses never referenced by relocation: %d; referenced only under names '
                  'other than their definition: %d.' % (c['unreferenced_function_addresses'],
                                                        c['referenced_only_under_other_names']), '']
    d = s.get('data')
    if d:
        lines += ['## Data', '', 'Referenced non-function addresses: %d (%d outside the code range).' % (
            d['referenced_non_function_addresses'], d['data_addresses_outside_code_range']), '',
                  _table(sorted(d['by_subkind'].items(), key=lambda kv: -kv[1]), ['kind/subkind', 'addresses']), '',
                  'Imported functions (IAT): %d.' % d['imported_functions'], '']
    v = s.get('vtables')
    if v:
        lines += ['## Vtables', '', _table([(k, v[k]) for k in sorted(v) if not isinstance(v[k], dict)],
                                         ['what', 'count']), '']
        if isinstance(v.get('ast'), dict):
            a = v['ast']
            lines += ['AST pass:', '', _table([(k, json.dumps(a[k]) if isinstance(a[k], dict) else a[k])
                                               for k in sorted(a)], ['what', 'value']), '']
    path.write_text('\n'.join(lines))
