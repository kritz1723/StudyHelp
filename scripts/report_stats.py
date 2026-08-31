#!/usr/bin/env python3
"""Print what a built site contains, for the deploy log.

This lives in a script rather than inline in the workflow so it can be tested.
It previously ran as inline YAML, formatted every value as a number, and broke
the deploy the first time a statistic arrived as a mapping -- a failure that
could not have been caught before pushing.

    python3 scripts/report_stats.py [--site site]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def format_stats(stats):
    """Render statistics for the log, whatever shape each value has."""
    lines = []
    for key, value in stats.items():
        if isinstance(value, dict):
            inner = ", ".join(f"{k} {v:,}" if isinstance(v, (int, float)) else f"{k} {v}"
                              for k, v in sorted(value.items()))
            lines.append(f"{key}: {inner}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {value}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value:,}")
        else:
            lines.append(f"{key}: {value}")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=str(ROOT / "site"))
    args = parser.parse_args()

    site = Path(args.site)
    stats = json.loads((site / "stats.json").read_text(encoding="utf-8"))
    for line in format_stats(stats):
        print(line)

    lemma_dir = site / "lemma"
    if lemma_dir.exists():
        print(f"lemma files: {len(list(lemma_dir.glob('*.json'))):,}")


if __name__ == "__main__":
    main()
