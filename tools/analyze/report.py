"""Markdown rendering of out/analyze/summary.json (filled in as steps land)."""
import json


def write_markdown(summary, path):
    path.write_text('```json\n' + json.dumps(summary, indent=1, sort_keys=True) + '\n```\n')
