import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build  # noqa: E402


class DomainNormalizationTests(unittest.TestCase):
    def test_normalizes_safe_ascii_domains(self):
        self.assertEqual(build.normalize_domain(" Ads.Example.COM. "), "ads.example.com")
        self.assertEqual(build.normalize_domain("*.track.example"), "track.example")

    def test_rejects_urls_ips_unicode_and_invalid_labels(self):
        for value in (
            "https://ads.example.com/path",
            "0.0.0.0",
            "127.0.0.1",
            "广告.example",
            "bad_label.example",
            "-bad.example",
            "localhost",
        ):
            with self.subTest(value=value):
                self.assertIsNone(build.normalize_domain(value))


class SourceParsingTests(unittest.TestCase):
    def test_parses_exact_domain_source_without_broadening(self):
        source = {"format": "domains", "default_rule": "DOMAIN"}
        result = build.parse_source("# header\nads.example\n*.wild.example\n", source)

        self.assertEqual(
            result.rules,
            {
                build.Rule("DOMAIN", "ads.example"),
                build.Rule("DOMAIN-SUFFIX", "wild.example"),
            },
        )

    def test_parses_classical_rules_and_excludes_risky_types(self):
        source = {"format": "classical"}
        result = build.parse_source(
            "\n".join(
                [
                    "DOMAIN,exact.example",
                    "DOMAIN-SUFFIX,suffix.example",
                    "DOMAIN-KEYWORD,advert",
                    "IP-CIDR,192.0.2.0/24",
                    "URL-REGEX,^https://example",
                ]
            ),
            source,
        )

        self.assertEqual(
            result.rules,
            {
                build.Rule("DOMAIN", "exact.example"),
                build.Rule("DOMAIN-SUFFIX", "suffix.example"),
            },
        )
        self.assertEqual(result.excluded_by_type["DOMAIN-KEYWORD"], 1)
        self.assertEqual(result.excluded_by_type["IP-CIDR"], 1)
        self.assertEqual(result.excluded_by_type["URL-REGEX"], 1)


class MergeTests(unittest.TestCase):
    def test_deduplicates_and_removes_exact_rules_covered_by_suffix(self):
        rules = {
            build.Rule("DOMAIN", "ads.example.com"),
            build.Rule("DOMAIN", "tracker.other.test"),
            build.Rule("DOMAIN-SUFFIX", "example.com"),
        }

        merged, stats = build.merge_rules(rules, set())

        self.assertEqual(
            merged,
            [
                build.Rule("DOMAIN-SUFFIX", "example.com"),
                build.Rule("DOMAIN", "tracker.other.test"),
            ],
        )
        self.assertEqual(stats["covered_exact"], 1)

    def test_allowlist_protects_exact_hosts_from_parent_suffix_rules(self):
        rules = {
            build.Rule("DOMAIN-SUFFIX", "example.com"),
            build.Rule("DOMAIN", "ads.safe.test"),
            build.Rule("DOMAIN", "tracker.other.test"),
        }
        allowlist = {build.Rule("DOMAIN", "login.example.com"), build.Rule("DOMAIN-SUFFIX", "safe.test")}

        merged, stats = build.merge_rules(rules, allowlist)

        self.assertEqual(merged, [build.Rule("DOMAIN", "tracker.other.test")])
        self.assertEqual(stats["allowlist_removed"], 2)

    def test_powerful_coverage_accepts_equivalent_or_broader_suffixes(self):
        balanced = [
            build.Rule("DOMAIN", "ads.example.com"),
            build.Rule("DOMAIN-SUFFIX", "track.example.com"),
        ]
        powerful = [
            build.Rule("DOMAIN-SUFFIX", "example.com"),
            build.Rule("DOMAIN", "other.test"),
        ]

        self.assertEqual(build.missing_coverage(balanced, powerful), [])
        self.assertEqual(
            build.missing_coverage([build.Rule("DOMAIN-SUFFIX", "missing.test")], powerful),
            [build.Rule("DOMAIN-SUFFIX", "missing.test")],
        )


class SafetyTests(unittest.TestCase):
    def test_rejects_empty_and_out_of_range_sources(self):
        with self.assertRaises(build.BuildError):
            build.enforce_count("small", 0, 1, 10)
        with self.assertRaises(build.BuildError):
            build.enforce_count("large", 11, 1, 10)

    def test_baseline_delta_uses_ratio_and_absolute_guard(self):
        build.enforce_delta("stable", 10_000, 10_700, 0.10, 2_000)
        with self.assertRaises(build.BuildError):
            build.enforce_delta("polluted", 10_000, 13_000, 0.20, 2_000)


class RenderingTests(unittest.TestCase):
    def test_renders_stable_egern_and_ruleset_formats(self):
        rules = [build.Rule("DOMAIN", "ads.example"), build.Rule("DOMAIN-SUFFIX", "tracker.example")]
        metadata = {"build_id": "abc123", "rule_count": 2}

        module = build.render_egern_module(rules, metadata)
        ruleset = build.render_surge_ruleset(rules, metadata)

        self.assertIn("#!name=Origo Ad Balanced", module)
        self.assertIn("[Rule]\nDOMAIN,ads.example,REJECT", module)
        self.assertIn("DOMAIN-SUFFIX,tracker.example,REJECT", module)
        self.assertIn("DOMAIN,ads.example", ruleset)
        self.assertNotIn(",REJECT", ruleset)

    def test_renders_powerful_as_an_independent_domain_only_tier(self):
        rules = [build.Rule("DOMAIN", "ads.example")]
        metadata = {"build_id": "power123", "rule_count": 1}

        module = build.render_egern_module(rules, metadata, tier="powerful")
        ruleset = build.render_surge_ruleset(rules, metadata, tier="powerful")

        self.assertIn("#!name=Origo Ad Powerful", module)
        self.assertIn("Powerful domain-only", module)
        self.assertIn("# NAME: Origo Ad Powerful", ruleset)
        self.assertNotIn("[Script]", module)
        self.assertNotIn("[MITM]", module)

    def test_renders_lite_with_the_expected_public_artifact_names(self):
        rules = [build.Rule("DOMAIN", "ads.example")]
        metadata = {"build_id": "lite123", "rule_count": 1}

        module = build.render_egern_module(rules, metadata, tier="lite")
        names = build.artifact_names("lite")

        self.assertIn("#!name=Origo Ad Lite", module)
        self.assertIn("Lite exact-domain", module)
        self.assertEqual(names.module, "origo-ad-lite.module")
        self.assertEqual(names.ruleset, "origo-ad-lite.list")
        self.assertEqual(names.report, "build-report-lite.json")

    def test_validator_detects_report_or_artifact_tampering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist = Path(temp_dir)
            rules = [build.Rule("DOMAIN", "ads.example")]
            metadata = {"build_id": "abc123", "rule_count": 1}
            module = build.render_egern_module(rules, metadata)
            ruleset = build.render_surge_ruleset(rules, metadata)
            (dist / "origo-ad-balanced.module").write_text(module, encoding="utf-8")
            (dist / "origo-ad-balanced.list").write_text(ruleset, encoding="utf-8")
            report = build.make_report(metadata, [], rules, {}, module, ruleset)
            (dist / "build-report.json").write_text(json.dumps(report), encoding="utf-8")

            build.validate_dist(dist, min_rules=1, max_rules=10)
            (dist / "origo-ad-balanced.list").write_text(ruleset + "DOMAIN,bad.example\n", encoding="utf-8")
            with self.assertRaises(build.BuildError):
                build.validate_dist(dist, min_rules=1, max_rules=10)

    def test_validator_supports_powerful_artifact_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist = Path(temp_dir)
            rules = [build.Rule("DOMAIN-SUFFIX", "ads.example")]
            metadata = {"build_id": "power123", "rule_count": 1}
            module = build.render_egern_module(rules, metadata, tier="powerful")
            ruleset = build.render_surge_ruleset(rules, metadata, tier="powerful")
            names = build.artifact_names("powerful")
            (dist / names.module).write_text(module, encoding="utf-8")
            (dist / names.ruleset).write_text(ruleset, encoding="utf-8")
            report = build.make_report(metadata, [], rules, {}, module, ruleset, tier="powerful")
            (dist / names.report).write_text(json.dumps(report), encoding="utf-8")

            build.validate_dist(dist, min_rules=1, max_rules=10, tier="powerful")

    def test_invalid_staged_artifacts_do_not_replace_verified_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist = Path(temp_dir) / "dist"
            dist.mkdir()
            for name in (build.MODULE_NAME, build.RULESET_NAME, build.REPORT_NAME):
                (dist / name).write_text("previous verified artifact\n", encoding="utf-8")

            with self.assertRaises(build.BuildError):
                build.write_artifacts(
                    dist,
                    {
                        build.MODULE_NAME: "invalid\n",
                        build.RULESET_NAME: "invalid\n",
                        build.REPORT_NAME: "{}\n",
                    },
                    min_rules=1,
                    max_rules=10,
                )

            for name in (build.MODULE_NAME, build.RULESET_NAME, build.REPORT_NAME):
                self.assertEqual((dist / name).read_text(encoding="utf-8"), "previous verified artifact\n")


if __name__ == "__main__":
    unittest.main()
