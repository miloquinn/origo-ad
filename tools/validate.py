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
    parser.add_argument("--tier", choices=["all", *sorted(build.TIER_DETAILS)], default="all")
    args = parser.parse_args()
    try:
        config = build.read_json(args.config)
        tiers = sorted(config["tiers"]) if args.tier == "all" else [args.tier]
        for tier in tiers:
            safety = config["tiers"][tier]
            build.validate_dist(
                args.dist,
                int(safety["final_min_rules"]),
                int(safety["final_max_rules"]),
                tier=tier,
            )
        if args.tier == "all":
            tier_rules = {}
            for tier in ("lite", "balanced", "powerful"):
                names = build.artifact_names(tier)
                _, tier_rules[tier] = build.parse_rendered_rules(
                    (args.dist / names.module).read_text(encoding="utf-8"),
                    module=True,
                )
            for narrower, broader in (("lite", "balanced"), ("balanced", "powerful")):
                missing = build.missing_coverage(tier_rules[narrower], tier_rules[broader])
                if missing:
                    raise build.BuildError(
                        f"{broader} tier does not cover {len(missing)} {narrower} rules; "
                        f"first missing: {missing[0]}"
                    )
    except (build.BuildError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"validated {args.dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
