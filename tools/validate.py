#!/usr/bin/env python3
"""Validate committed Origo Ad artifacts without network access."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import build


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "sources.json")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        config = build.read_json(args.config)
        safety = config["safety"]
        build.validate_dist(
            args.dist,
            int(safety["final_min_rules"]),
            int(safety["final_max_rules"]),
        )
    except (build.BuildError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"validated {args.dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
