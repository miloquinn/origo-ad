#!/usr/bin/env python3
"""Build deterministic, domain-only Origo ad-blocking artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "sources.json"
ALLOWLIST_FILE = ROOT / "config" / "allowlist.txt"
DIST_DIR = ROOT / "dist"
LITE_MODULE_NAME = "origo-ad-lite.module"
LITE_RULESET_NAME = "origo-ad-lite.list"
LITE_REPORT_NAME = "build-report-lite.json"
MODULE_NAME = "origo-ad-balanced.module"
RULESET_NAME = "origo-ad-balanced.list"
REPORT_NAME = "build-report.json"
POWERFUL_MODULE_NAME = "origo-ad-powerful.module"
POWERFUL_RULESET_NAME = "origo-ad-powerful.list"
POWERFUL_REPORT_NAME = "build-report-powerful.json"
PROJECT_URL = "https://github.com/miloquinn/origo-ad"
USER_AGENT = "origo-ad/2 (+https://github.com/miloquinn/origo-ad)"
VALID_RULE_KINDS = {"DOMAIN", "DOMAIN-SUFFIX"}
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
TIER_DETAILS = {
    "lite": {
        "name": "Origo Ad Lite",
        "description": "Lite exact-domain ad and tracker blocking for lower overhead; no MITM, rewrite, or script execution.",
    },
    "balanced": {
        "name": "Origo Ad Balanced",
        "description": "Balanced domain-only ad and tracker blocking; no MITM, rewrite, or script execution.",
    },
    "powerful": {
        "name": "Origo Ad Powerful",
        "description": "Powerful domain-only ad, tracker, telemetry, and badware blocking; no MITM, rewrite, or script execution.",
    },
}


class BuildError(RuntimeError):
    """Raised when input or output fails a publication safety check."""


@dataclass(frozen=True)
class ArtifactNames:
    module: str
    ruleset: str
    report: str


@dataclass(frozen=True, order=True)
class Rule:
    kind: str
    domain: str


@dataclass
class ParseResult:
    rules: set[Rule] = field(default_factory=set)
    raw_candidates: int = 0
    invalid: int = 0
    duplicates: int = 0
    excluded_by_type: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True)
class FetchedSource:
    text: str
    sha256: str
    byte_count: int
    etag: str | None
    last_modified: str | None


def artifact_names(tier: str) -> ArtifactNames:
    if tier == "lite":
        return ArtifactNames(LITE_MODULE_NAME, LITE_RULESET_NAME, LITE_REPORT_NAME)
    if tier == "balanced":
        return ArtifactNames(MODULE_NAME, RULESET_NAME, REPORT_NAME)
    if tier == "powerful":
        return ArtifactNames(POWERFUL_MODULE_NAME, POWERFUL_RULESET_NAME, POWERFUL_REPORT_NAME)
    raise BuildError(f"unknown tier: {tier!r}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"cannot read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"expected a JSON object in {path}")
    return value


def normalize_domain(value: str) -> str | None:
    candidate = value.strip().lower()
    if candidate.startswith("*."):
        candidate = candidate[2:]
    candidate = candidate.rstrip(".")
    if not candidate or len(candidate) > 253 or "." not in candidate:
        return None
    if any(ord(char) > 127 for char in candidate):
        return None
    labels = candidate.split(".")
    if all(label.isdigit() for label in labels):
        return None
    if any(not LABEL_RE.fullmatch(label) for label in labels):
        return None
    return candidate


def parse_source(text: str, source: dict) -> ParseResult:
    result = ParseResult()
    source_format = source.get("format")
    default_rule = source.get("default_rule", "DOMAIN")
    if source_format not in {"domains", "classical"}:
        raise BuildError(f"unsupported source format: {source_format!r}")
    if default_rule not in VALID_RULE_KINDS:
        raise BuildError(f"unsupported default rule: {default_rule!r}")

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith(("#", ";", "!")):
            continue
        result.raw_candidates += 1

        if source_format == "domains":
            kind = "DOMAIN-SUFFIX" if line.startswith("*.") else default_rule
            value = line
        else:
            parts = [part.strip() for part in line.split(",")]
            kind = parts[0].upper() if parts else ""
            if kind not in VALID_RULE_KINDS:
                result.excluded_by_type[kind or "MALFORMED"] += 1
                continue
            if len(parts) < 2:
                result.invalid += 1
                continue
            value = parts[1]

        domain = normalize_domain(value)
        if domain is None:
            result.invalid += 1
            continue
        rule = Rule(kind, domain)
        if rule in result.rules:
            result.duplicates += 1
        result.rules.add(rule)

    return result


def parse_allowlist(path: Path) -> set[Rule]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"cannot read allowlist {path}: {exc}") from exc

    rules: set[Rule] = set()
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",", 1)]
        if len(parts) == 1:
            kind, value = "DOMAIN", parts[0]
        else:
            kind, value = parts[0].upper(), parts[1]
        domain = normalize_domain(value)
        if kind not in VALID_RULE_KINDS or domain is None:
            raise BuildError(f"invalid allowlist entry at {path}:{line_number}: {raw_line!r}")
        rules.add(Rule(kind, domain))
    if not rules:
        raise BuildError("allowlist must not be empty")
    return rules


def is_same_or_subdomain(domain: str, parent: str) -> bool:
    return domain == parent or domain.endswith("." + parent)


def domain_suffixes(domain: str) -> tuple[str, ...]:
    labels = domain.split(".")
    return tuple(".".join(labels[index:]) for index in range(len(labels) - 1))


def conflicts_with_allowlist(block: Rule, allow: Rule) -> bool:
    if block.kind == "DOMAIN":
        if allow.kind == "DOMAIN":
            return block.domain == allow.domain
        return is_same_or_subdomain(block.domain, allow.domain)

    if allow.kind == "DOMAIN":
        return is_same_or_subdomain(allow.domain, block.domain)
    return is_same_or_subdomain(block.domain, allow.domain) or is_same_or_subdomain(allow.domain, block.domain)


def rule_sort_key(rule: Rule) -> tuple[str, int]:
    return (rule.domain, 0 if rule.kind == "DOMAIN-SUFFIX" else 1)


def merge_rules(rules: Iterable[Rule], allowlist: set[Rule]) -> tuple[list[Rule], dict[str, int]]:
    unique = set(rules)
    allowed = {
        block
        for block in unique
        if any(conflicts_with_allowlist(block, allow) for allow in allowlist)
    }
    remaining = unique - allowed
    suffixes = sorted(
        (rule for rule in remaining if rule.kind == "DOMAIN-SUFFIX"),
        key=lambda rule: (rule.domain.count("."), rule.domain),
    )
    kept_suffixes: list[Rule] = []
    kept_suffix_domains: set[str] = set()
    redundant_suffixes = 0
    for rule in suffixes:
        if any(parent in kept_suffix_domains for parent in domain_suffixes(rule.domain)):
            redundant_suffixes += 1
            continue
        kept_suffixes.append(rule)
        kept_suffix_domains.add(rule.domain)

    kept_exact: list[Rule] = []
    covered_exact = 0
    for rule in (item for item in remaining if item.kind == "DOMAIN"):
        if any(parent in kept_suffix_domains for parent in domain_suffixes(rule.domain)):
            covered_exact += 1
            continue
        kept_exact.append(rule)

    merged = sorted([*kept_suffixes, *kept_exact], key=rule_sort_key)
    return merged, {
        "input_unique": len(unique),
        "allowlist_removed": len(allowed),
        "redundant_suffixes": redundant_suffixes,
        "covered_exact": covered_exact,
        "final": len(merged),
    }


def missing_coverage(required: Iterable[Rule], candidate: Iterable[Rule]) -> list[Rule]:
    candidate_rules = set(candidate)
    candidate_suffixes = {rule.domain for rule in candidate_rules if rule.kind == "DOMAIN-SUFFIX"}
    missing: list[Rule] = []
    for rule in required:
        if rule in candidate_rules:
            continue
        if not set(domain_suffixes(rule.domain)).intersection(candidate_suffixes):
            missing.append(rule)
    return sorted(missing, key=rule_sort_key)


def enforce_count(name: str, count: int, minimum: int, maximum: int) -> None:
    if count < minimum or count > maximum:
        raise BuildError(f"{name} count {count} is outside safe range [{minimum}, {maximum}]")


def enforce_delta(name: str, previous: int, current: int, max_ratio: float, max_absolute: int) -> None:
    if previous <= 0:
        raise BuildError(f"{name} baseline count must be positive")
    absolute = abs(current - previous)
    ratio = absolute / previous
    if ratio > max_ratio and absolute > max_absolute:
        raise BuildError(
            f"{name} changed from {previous} to {current} "
            f"({ratio:.1%}, {absolute} rules), exceeding both safety limits"
        )


def fetch_source(source: dict) -> FetchedSource:
    url = source["url"]
    max_bytes = int(source["max_bytes"])
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain,application/octet-stream;q=0.9,*/*;q=0.1"},
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise BuildError(f"{source['id']} returned HTTP {status}")
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise BuildError(f"{source['id']} exceeded max_bytes={max_bytes}")
                content_type = response.headers.get_content_type()
                if content_type not in {"text/plain", "application/octet-stream"}:
                    raise BuildError(f"{source['id']} returned unexpected content type {content_type!r}")
                try:
                    text = data.decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    raise BuildError(f"{source['id']} is not valid UTF-8") from exc
                return FetchedSource(
                    text=text,
                    sha256=sha256_bytes(data),
                    byte_count=len(data),
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                )
        except (BuildError, OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1 << attempt)
    raise BuildError(f"failed to fetch required source {source['id']}: {last_error}")


def source_report(source: dict, fetched: FetchedSource, parsed: ParseResult) -> dict:
    return {
        "id": source["id"],
        "name": source["name"],
        "url": source["url"],
        "homepage": source["homepage"],
        "license": source["license"],
        "license_url": source["license_url"],
        "risk": source["risk"],
        "sha256": fetched.sha256,
        "bytes": fetched.byte_count,
        "etag": fetched.etag,
        "last_modified": fetched.last_modified,
        "raw_candidates": parsed.raw_candidates,
        "accepted_unique": len(parsed.rules),
        "invalid": parsed.invalid,
        "duplicates": parsed.duplicates,
        "excluded_by_type": dict(sorted(parsed.excluded_by_type.items())),
    }


def render_egern_module(rules: list[Rule], metadata: dict, tier: str = "balanced") -> str:
    details = TIER_DETAILS.get(tier)
    if details is None:
        raise BuildError(f"unknown tier: {tier!r}")
    lines = [
        f"#!name={details['name']}",
        f"#!desc={details['description']}",
        "#!author=origo-ad contributors",
        f"#!homepage={PROJECT_URL}",
        "#!license=GPL-3.0-only",
        f"#!generated-source-sha256={metadata['build_id']}",
        f"#!rule-count={metadata['rule_count']}",
        "",
    ]
    for source in metadata.get("sources", []):
        lines.append(f"# Source: {source['name']} ({source['license']}) {source['url']}")
    if metadata.get("sources"):
        lines.append("")
    lines.append("[Rule]")
    lines.extend(f"{rule.kind},{rule.domain},REJECT" for rule in rules)
    return "\n".join(lines) + "\n"


def render_surge_ruleset(rules: list[Rule], metadata: dict, tier: str = "balanced") -> str:
    details = TIER_DETAILS.get(tier)
    if details is None:
        raise BuildError(f"unknown tier: {tier!r}")
    lines = [
        f"# NAME: {details['name']}",
        f"# DESCRIPTION: {details['description']}",
        f"# HOMEPAGE: {PROJECT_URL}",
        "# LICENSE: GPL-3.0-only",
        f"# SOURCE-SHA256: {metadata['build_id']}",
        f"# RULES: {metadata['rule_count']}",
    ]
    for source in metadata.get("sources", []):
        lines.append(f"# SOURCE: {source['name']} ({source['license']}) {source['url']}")
    lines.append("")
    lines.extend(f"{rule.kind},{rule.domain}" for rule in rules)
    return "\n".join(lines) + "\n"


def make_report(
    metadata: dict,
    sources: list[dict],
    rules: list[Rule],
    merge_stats: dict,
    module: str,
    ruleset: str,
    tier: str = "balanced",
) -> dict:
    names = artifact_names(tier)
    return {
        "schema_version": 1,
        "tier": tier,
        "build_id": metadata["build_id"],
        "license": "GPL-3.0-only",
        "configuration": metadata.get("configuration", {}),
        "sources": sources,
        "summary": {
            "final_rule_count": len(rules),
            "domain_count": sum(rule.kind == "DOMAIN" for rule in rules),
            "domain_suffix_count": sum(rule.kind == "DOMAIN-SUFFIX" for rule in rules),
            **merge_stats,
        },
        "artifacts": {
            names.module: {"sha256": sha256_text(module), "bytes": len(module.encode("utf-8"))},
            names.ruleset: {"sha256": sha256_text(ruleset), "bytes": len(ruleset.encode("utf-8"))},
        },
    }


def parse_rendered_rules(text: str, module: bool) -> tuple[str, list[Rule]]:
    build_id = ""
    rules: list[Rule] = []
    in_rule_section = not module
    seen_rule_section = not module
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            if line.startswith("#!generated-source-sha256="):
                build_id = line.split("=", 1)[1]
            elif line.startswith("# SOURCE-SHA256:"):
                build_id = line.split(":", 1)[1].strip()
            continue
        if module and line == "[Rule]":
            if seen_rule_section:
                raise BuildError("module contains duplicate [Rule] sections")
            in_rule_section = True
            seen_rule_section = True
            continue
        if line.startswith("["):
            raise BuildError(f"unexpected module section {line}")
        if not in_rule_section:
            continue
        parts = line.split(",")
        expected_parts = 3 if module else 2
        if len(parts) != expected_parts or (module and parts[2] != "REJECT"):
            raise BuildError(f"invalid generated rule: {line}")
        kind, domain = parts[0], parts[1]
        if kind not in VALID_RULE_KINDS or normalize_domain(domain) != domain:
            raise BuildError(f"invalid generated domain rule: {line}")
        rules.append(Rule(kind, domain))
    if not seen_rule_section:
        raise BuildError("module is missing [Rule]")
    if not build_id:
        raise BuildError("artifact is missing source hash metadata")
    return build_id, rules


def validate_dist(dist_dir: Path, min_rules: int, max_rules: int, tier: str = "balanced") -> None:
    names = artifact_names(tier)
    module_path = dist_dir / names.module
    ruleset_path = dist_dir / names.ruleset
    report_path = dist_dir / names.report
    for path in (module_path, ruleset_path, report_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise BuildError(f"missing or empty artifact: {path}")

    module = module_path.read_text(encoding="utf-8")
    ruleset = ruleset_path.read_text(encoding="utf-8")
    report = read_json(report_path)
    module_build_id, module_rules = parse_rendered_rules(module, module=True)
    ruleset_build_id, ruleset_rules = parse_rendered_rules(ruleset, module=False)
    if module_rules != ruleset_rules:
        raise BuildError("module and ruleset contain different rules")
    if module_rules != sorted(set(module_rules), key=rule_sort_key):
        raise BuildError("generated rules are duplicated or not deterministically sorted")
    enforce_count("final artifact", len(module_rules), min_rules, max_rules)

    report_build_id = report.get("build_id")
    if len({module_build_id, ruleset_build_id, report_build_id}) != 1:
        raise BuildError("artifact build IDs do not match")
    if report.get("summary", {}).get("final_rule_count") != len(module_rules):
        raise BuildError("report rule count does not match artifacts")
    expected = report.get("artifacts", {})
    actual = {names.module: sha256_text(module), names.ruleset: sha256_text(ruleset)}
    for name, digest in actual.items():
        if expected.get(name, {}).get("sha256") != digest:
            raise BuildError(f"artifact digest mismatch: {name}")


def load_baseline(path: Path) -> dict | None:
    if not path.exists():
        return None
    baseline = read_json(path)
    if baseline.get("schema_version") != 1:
        return None
    return baseline


def check_baseline(
    config: dict,
    tier_config: dict,
    baseline: dict | None,
    source_reports: list[dict],
    final_count: int,
) -> None:
    if baseline is None:
        return
    safety = config["safety"]
    source_settings = {source["id"]: source for source in config["sources"]}
    previous_sources = {source["id"]: source for source in baseline.get("sources", [])}
    for source in source_reports:
        previous = previous_sources.get(source["id"])
        if not previous:
            continue
        settings = source_settings[source["id"]]
        enforce_delta(
            f"source {source['id']}",
            int(previous["accepted_unique"]),
            int(source["accepted_unique"]),
            float(settings.get("max_delta_ratio", safety["source_max_delta_ratio"])),
            int(settings.get("max_delta_absolute", safety["source_max_delta_absolute"])),
        )
    previous_final = baseline.get("summary", {}).get("final_rule_count")
    if previous_final:
        enforce_delta(
            "final artifact",
            int(previous_final),
            final_count,
            float(tier_config["final_max_delta_ratio"]),
            int(tier_config["final_max_delta_absolute"]),
        )


def write_artifacts(
    dist_dir: Path,
    files: dict[str, str],
    min_rules: int,
    max_rules: int,
    tier: str = "balanced",
) -> None:
    dist_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".origo-ad-build-", dir=ROOT) as temp_name:
        temp_dir = Path(temp_name)
        staged: dict[str, Path] = {}
        for name, content in files.items():
            path = temp_dir / name
            path.write_text(content, encoding="utf-8")
            staged[name] = path
        validate_dist(temp_dir, min_rules, max_rules, tier=tier)
        for name, path in staged.items():
            os.replace(path, dist_dir / name)


def build(
    config_path: Path,
    allowlist_path: Path,
    dist_dir: Path,
    use_baseline: bool,
    tier: str = "balanced",
) -> dict:
    allowlist_bytes = allowlist_path.read_bytes()
    config = read_json(config_path)
    if config.get("schema_version") != 1 or not isinstance(config.get("sources"), list):
        raise BuildError("sources.json must use schema_version 1 and contain a sources array")
    tier_config = config.get("tiers", {}).get(tier)
    if not isinstance(tier_config, dict):
        raise BuildError(f"sources.json is missing tier configuration for {tier!r}")

    safety = config.get("safety", {})
    required_safety = {"source_max_delta_ratio", "source_max_delta_absolute"}
    required_tier_safety = {
        "final_min_rules",
        "final_max_rules",
        "final_max_delta_ratio",
        "final_max_delta_absolute",
    }
    if not required_safety.issubset(safety) or not required_tier_safety.issubset(tier_config):
        raise BuildError("sources.json is missing required source or tier safety settings")

    names = artifact_names(tier)
    selected_sources = [source for source in config["sources"] if tier in source.get("tiers", [])]
    source_ids = [source.get("id") for source in selected_sources]
    if not selected_sources or len(source_ids) != len(set(source_ids)):
        raise BuildError(f"tier {tier!r} must contain at least one source with unique IDs")

    baseline = load_baseline(dist_dir / names.report) if use_baseline else None
    all_rules: set[Rule] = set()
    reports: list[dict] = []
    source_digests: list[str] = []
    for source in selected_sources:
        fetched = fetch_source(source)
        parsed = parse_source(fetched.text, source)
        enforce_count(
            f"source {source['id']}",
            len(parsed.rules),
            int(source["min_entries"]),
            int(source["max_entries"]),
        )
        invalid_ratio = parsed.invalid / max(parsed.raw_candidates, 1)
        if invalid_ratio > float(source.get("max_invalid_ratio", 0.01)):
            raise BuildError(f"source {source['id']} invalid ratio {invalid_ratio:.2%} is too high")
        all_rules.update(parsed.rules)
        reports.append(source_report(source, fetched, parsed))
        source_digests.append(fetched.sha256)

    allowlist = parse_allowlist(allowlist_path)
    rules, merge_stats = merge_rules(all_rules, allowlist)
    minimum = int(tier_config["final_min_rules"])
    maximum = int(tier_config["final_max_rules"])
    enforce_count(f"{tier} final artifact", len(rules), minimum, maximum)
    check_baseline(config, tier_config, baseline, reports, len(rules))

    selected_config = json.dumps(
        {"tier": tier, "settings": tier_config, "sources": selected_sources},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    build_material = "\n".join(
        [sha256_bytes(selected_config), sha256_bytes(allowlist_bytes), *source_digests]
    )
    build_id = sha256_text(build_material)
    metadata = {
        "build_id": build_id,
        "rule_count": len(rules),
        "sources": reports,
        "configuration": {
            "tier": tier,
            "policy": tier_config.get("policy"),
            "sources_sha256": sha256_bytes(selected_config),
            "allowlist_sha256": sha256_bytes(allowlist_bytes),
            "allowlist_rule_count": len(allowlist),
        },
    }
    module = render_egern_module(rules, metadata, tier=tier)
    ruleset = render_surge_ruleset(rules, metadata, tier=tier)
    report = make_report(metadata, reports, rules, merge_stats, module, ruleset, tier=tier)
    report_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    write_artifacts(
        dist_dir,
        {names.module: module, names.ruleset: ruleset, names.report: report_text},
        minimum,
        maximum,
        tier=tier,
    )
    validate_dist(dist_dir, minimum, maximum, tier=tier)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=SOURCES_FILE)
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST_FILE)
    parser.add_argument("--dist", type=Path, default=DIST_DIR)
    parser.add_argument("--tier", choices=sorted(TIER_DETAILS), default="balanced")
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Skip comparison with the existing report (for reviewed bootstrap changes only).",
    )
    args = parser.parse_args()
    try:
        report = build(args.config, args.allowlist, args.dist, not args.no_baseline, tier=args.tier)
    except (BuildError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"build failed: {exc}", file=os.sys.stderr)
        return 1
    names = artifact_names(args.tier)
    print(f"wrote {args.dist / names.module}")
    print(f"wrote {args.dist / names.ruleset}")
    print(f"wrote {args.dist / names.report}")
    print(f"rules: {report['summary']['final_rule_count']}")
    print(f"build id: {report['build_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
