import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
    def _write_splash_manifest(self, directory: Path) -> tuple[Path, dict]:
        manifest = {
            "schema_version": 1,
            "entries": [
                {
                    "id": "covered-app",
                    "app": "Covered",
                    "host": "ads.covered.example",
                    "path": "/getSplash",
                    "match": "exact",
                    "source_line": 1,
                },
                {
                    "id": "selected-app",
                    "app": "Selected",
                    "host": "api.selected.example",
                    "path": "/v{version}/launchad",
                    "match": "exact",
                    "source_line": 2,
                },
                {
                    "id": "bilibili-native",
                    "app": "Bilibili",
                    "host": "app.bilibili.com",
                    "path": "/x/v2/splash/list",
                    "match": "exact",
                    "rewrite": "bilibili-preload",
                    "source_line": 3,
                },
            ],
        }
        path = directory / "splash.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, manifest

    def _write_splash_artifacts(self, dist: Path, manifest_path: Path) -> tuple[dict, str, str]:
        manifest = build.splash.load_manifest(manifest_path)
        rules = [build.Rule("DOMAIN", "ads.covered.example")]
        entries = build.splash.select_entries(manifest, rules)
        splash_report = {
            "manifest_sha256": build.sha256_bytes(manifest_path.read_bytes()),
            "entries": entries,
            "excluded_by_domain_count": 1,
            **build.splash_processing_counts(entries),
        }
        metadata = {
            "build_id": "splash123",
            "rule_count": 1,
            "configuration": {"splash_manifest_sha256": splash_report["manifest_sha256"]},
            "splash": splash_report,
        }
        module = build.render_egern_module(rules, metadata)
        egern_config = build.render_egern_config(rules, metadata)
        ruleset = build.render_surge_ruleset(rules, metadata)
        names = build.artifact_names("balanced")
        report = build.make_report(
            metadata,
            [],
            rules,
            {},
            module,
            ruleset,
            surge_module=module,
            egern_config=egern_config,
        )
        (dist / names.module).write_text(module, encoding="utf-8")
        (dist / names.surge_module).write_text(module, encoding="utf-8")
        (dist / names.egern_config).write_text(egern_config, encoding="utf-8")
        (dist / names.ruleset).write_text(ruleset, encoding="utf-8")
        (dist / names.report).write_text(json.dumps(report), encoding="utf-8")
        return report, module, ruleset

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
        self.assertEqual(names.egern_config, "origo-ad-lite.yaml")
        self.assertEqual(names.ruleset, "origo-ad-lite.list")
        self.assertEqual(names.report, "build-report-lite.json")

    def test_domain_only_report_does_not_publish_native_egern_config(self):
        rules = [build.Rule("DOMAIN", "ads.example")]
        metadata = {"build_id": "plain123", "rule_count": 1}
        module = build.render_egern_module(rules, metadata)
        ruleset = build.render_surge_ruleset(rules, metadata)

        report = build.make_report(metadata, [], rules, {}, module, ruleset)

        self.assertNotIn(build.artifact_names("balanced").egern_config, report["artifacts"])

    def test_splash_rules_are_only_added_to_script_free_modules(self):
        rules = [build.Rule("DOMAIN", "ads.example")]
        entries = [
            {
                "id": "sample-app",
                "app": "Sample",
                "host": "api.sample.example",
                "path": "/getSplash",
                "match": "exact",
                "source_line": 1,
            }
        ]
        metadata = {
            "build_id": "splash123",
            "rule_count": 1,
            "splash": {"entries": entries},
        }

        module = build.render_egern_module(rules, metadata)
        ruleset = build.render_surge_ruleset(rules, metadata)

        self.assertIn("using HTTPS MITM", module)
        self.assertIn("[URL Rewrite]", module)
        self.assertIn("[MITM]", module)
        self.assertNotIn("[Script]", module)
        self.assertNotIn("[URL Rewrite]", ruleset)
        self.assertNotIn("[MITM]", ruleset)
        self.assertIn("domain-only", ruleset)

    def test_renders_native_egern_schema_with_domain_and_splash_rules(self):
        rules = [build.Rule("DOMAIN", "ads.example"), build.Rule("DOMAIN-SUFFIX", "tracker.example")]
        entries = [
            {
                "id": "sample-app",
                "app": "Sample",
                "host": "api.sample.example",
                "path": "/getSplash",
                "match": "exact",
                "source_line": 1,
            }
        ]
        metadata = {
            "build_id": "splash123",
            "rule_count": 2,
            "splash": {"entries": entries},
        }

        rendered = build.render_egern_config(rules, metadata)
        document = json.loads(rendered)

        self.assertEqual(document["name"], "Origo Ad Balanced")
        self.assertEqual(
            document["rules"],
            [
                {"domain": {"match": "ads.example", "policy": "REJECT"}},
                {"domain_suffix": {"match": "tracker.example", "policy": "REJECT"}},
            ],
        )
        native_sections = build.splash.native_sections(entries)
        for key, value in native_sections.items():
            self.assertEqual(document[key], value)
        self.assertNotIn("scripts", document)

    def test_module_and_native_egern_have_exact_splash_endpoint_parity(self):
        entries = [
            {
                "id": "reject-app",
                "app": "Reject",
                "host": "reject.example",
                "path": "/getSplash",
                "match": "exact",
                "source_line": 1,
            },
            {
                "id": "empty-json-app",
                "app": "Empty JSON",
                "host": "response.example",
                "path": "/launchad",
                "match": "exact",
                "response": "empty-json",
                "source_line": 2,
            },
        ]
        metadata = {
            "build_id": "splash123",
            "rule_count": 1,
            "splash": {"entries": entries},
        }

        module = build.render_egern_module([build.Rule("DOMAIN", "ads.example")], metadata)
        native = json.loads(build.render_egern_config([build.Rule("DOMAIN", "ads.example")], metadata))
        module_patterns = {
            line.split(" _ reject", 1)[0].split(" data-type=", 1)[0]
            for line in module.splitlines()
            if line.startswith("^https?")
        }
        native_patterns = {
            item["match"]
            for section in ("url_rewrites", "map_locals")
            for item in native.get(section, [])
        }

        self.assertEqual(module_patterns, native_patterns)
        self.assertEqual(native_patterns, {build.splash.pattern(entry) for entry in entries})
        self.assertEqual(native["url_rewrites"][0]["location"], "http://reject/")
        self.assertEqual(native["map_locals"][0]["status_code"], 200)
        self.assertEqual(native["map_locals"][0]["headers"], {"Content-Type": "application/json"})
        self.assertEqual(native["map_locals"][0]["body"], "{}")

    def test_native_body_rewrite_is_not_degraded_into_surge_reject(self):
        entry = {
            "id": "bilibili-native",
            "app": "Bilibili",
            "host": "app.bilibili.com",
            "path": "/x/v2/splash/list",
            "match": "exact",
            "rewrite": "bilibili-preload",
            "source_line": 1,
        }
        metadata = {
            "build_id": "splash123",
            "rule_count": 1,
            "splash": {"entries": [entry]},
        }

        module = build.render_egern_module([build.Rule("DOMAIN", "ads.example")], metadata)
        native = json.loads(build.render_egern_config([build.Rule("DOMAIN", "ads.example")], metadata))
        response_jq = native["body_rewrites"][0]["response_jq"]

        self.assertEqual(response_jq["match"], build.splash.pattern(entry))
        self.assertEqual(response_jq["filter"], build.splash.BODY_REWRITES["bilibili-preload"])
        self.assertNotIn(build.splash.pattern(entry), module)
        self.assertNotIn("[URL Rewrite]", module)
        self.assertNotIn("[MITM]", module)
        self.assertEqual(
            build.splash_processing_counts([entry]),
            {
                "rule_count": 1,
                "surge_rule_count": 0,
                "egern_url_rewrite_count": 0,
                "egern_map_local_count": 0,
                "egern_body_rewrite_count": 1,
                "mitm_host_count": 1,
                "surge_mitm_host_count": 0,
            },
        )

    def test_splash_validator_requires_identical_sgmodule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            dist.mkdir()
            manifest_path, _ = self._write_splash_manifest(root)
            report, module, _ = self._write_splash_artifacts(dist, manifest_path)
            names = build.artifact_names("balanced")

            build.validate_dist(dist, 1, 10, splash_manifest_path=manifest_path)
            (dist / names.surge_module).write_text(module + "# changed\n", encoding="utf-8")
            report["artifacts"][names.surge_module]["sha256"] = build.sha256_text(module + "# changed\n")
            (dist / names.report).write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(build.BuildError, "artifacts differ"):
                build.validate_dist(dist, 1, 10, splash_manifest_path=manifest_path)

    def test_splash_staging_failure_preserves_verified_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            dist.mkdir()
            manifest_path, _ = self._write_splash_manifest(root)
            staged = root / "staged"
            staged.mkdir()
            self._write_splash_artifacts(staged, manifest_path)
            names = build.artifact_names("balanced")
            for name in (names.module, names.surge_module, names.egern_config, names.ruleset, names.report):
                (dist / name).write_text("previous verified artifact\n", encoding="utf-8")
            incomplete_files = {
                name: (staged / name).read_text(encoding="utf-8")
                for name in (names.module, names.ruleset, names.report)
            }

            with self.assertRaisesRegex(build.BuildError, "missing or empty artifact"):
                build.write_artifacts(
                    dist,
                    incomplete_files,
                    1,
                    10,
                    splash_manifest_path=manifest_path,
                )

            for name in (names.module, names.surge_module, names.egern_config, names.ruleset, names.report):
                self.assertEqual((dist / name).read_text(encoding="utf-8"), "previous verified artifact\n")

    def test_splash_validator_rejects_missing_native_egern_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            dist.mkdir()
            manifest_path, _ = self._write_splash_manifest(root)
            self._write_splash_artifacts(dist, manifest_path)
            (dist / build.artifact_names("balanced").egern_config).unlink()

            with self.assertRaisesRegex(build.BuildError, "missing or empty artifact"):
                build.validate_dist(dist, 1, 10, splash_manifest_path=manifest_path)

    def test_splash_validator_rejects_rehashed_native_egern_tampering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            dist.mkdir()
            manifest_path, _ = self._write_splash_manifest(root)
            report, _, _ = self._write_splash_artifacts(dist, manifest_path)
            names = build.artifact_names("balanced")
            native_path = dist / names.egern_config
            document = json.loads(native_path.read_text(encoding="utf-8"))
            document["rules"][0]["domain"]["policy"] = "DIRECT"
            tampered = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            native_path.write_text(tampered, encoding="utf-8")
            report["artifacts"][names.egern_config] = {
                "sha256": build.sha256_text(tampered),
                "bytes": len(tampered.encode("utf-8")),
            }
            (dist / names.report).write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(build.BuildError, "does not match build report"):
                build.validate_dist(dist, 1, 10, splash_manifest_path=manifest_path)

    def test_splash_validator_rejects_corrupted_native_egern_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            dist.mkdir()
            manifest_path, _ = self._write_splash_manifest(root)
            report, _, _ = self._write_splash_artifacts(dist, manifest_path)
            names = build.artifact_names("balanced")
            corrupted = "{not-json}\n"
            (dist / names.egern_config).write_text(corrupted, encoding="utf-8")
            report["artifacts"][names.egern_config] = {
                "sha256": build.sha256_text(corrupted),
                "bytes": len(corrupted.encode("utf-8")),
            }
            (dist / names.report).write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(build.BuildError, "invalid native Egern configuration"):
                build.validate_dist(dist, 1, 10, splash_manifest_path=manifest_path)

    def test_splash_validator_rejects_section_tampering_even_with_updated_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            dist.mkdir()
            manifest_path, _ = self._write_splash_manifest(root)
            report, module, _ = self._write_splash_artifacts(dist, manifest_path)
            names = build.artifact_names("balanced")
            tampered = module.replace("_ reject", "_ reject-dict", 1)
            (dist / names.module).write_text(tampered, encoding="utf-8")
            (dist / names.surge_module).write_text(tampered, encoding="utf-8")
            report["artifacts"][names.module]["sha256"] = build.sha256_text(tampered)
            report["artifacts"][names.surge_module]["sha256"] = build.sha256_text(tampered)
            (dist / names.report).write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(build.BuildError, "splash sections"):
                build.validate_dist(dist, 1, 10, splash_manifest_path=manifest_path)

    def test_splash_validator_rejects_report_entries_that_differ_from_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            dist.mkdir()
            manifest_path, _ = self._write_splash_manifest(root)
            report, _, _ = self._write_splash_artifacts(dist, manifest_path)
            names = build.artifact_names("balanced")
            report["splash"]["excluded_by_domain_count"] = 0
            (dist / names.report).write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(build.BuildError, "does not match current manifest"):
                build.validate_dist(dist, 1, 10, splash_manifest_path=manifest_path)

    def test_splash_validator_rejects_processing_count_tampering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            dist.mkdir()
            manifest_path, _ = self._write_splash_manifest(root)
            report, _, _ = self._write_splash_artifacts(dist, manifest_path)
            report["splash"]["egern_body_rewrite_count"] = 0
            names = build.artifact_names("balanced")
            (dist / names.report).write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(build.BuildError, "does not match current manifest"):
                build.validate_dist(dist, 1, 10, splash_manifest_path=manifest_path)

    def test_full_build_adds_splash_artifacts_and_keeps_ruleset_domain_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "dist"
            allowlist = root / "allowlist.txt"
            allowlist.write_text("DOMAIN,allowed.example\n", encoding="utf-8")
            manifest_path, _ = self._write_splash_manifest(root)
            config = {
                "schema_version": 1,
                "safety": {"source_max_delta_ratio": 1, "source_max_delta_absolute": 10},
                "tiers": {
                    tier: {
                        "policy": f"{tier}-test",
                        "final_min_rules": 1,
                        "final_max_rules": 10,
                        "final_max_delta_ratio": 1,
                        "final_max_delta_absolute": 10,
                    }
                    for tier in build.TIER_DETAILS
                },
                "sources": [
                    {
                        "id": "fixture",
                        "name": "Fixture",
                        "url": "https://example.test/rules",
                        "homepage": "https://example.test",
                        "license": "MIT",
                        "license_url": "https://example.test/license",
                        "format": "domains",
                        "default_rule": "DOMAIN",
                        "tiers": list(build.TIER_DETAILS),
                        "risk": "fixture",
                        "min_entries": 1,
                        "max_entries": 10,
                        "max_bytes": 1000,
                    }
                ],
                "splash_rules": manifest_path.name,
            }
            config_path = root / "sources.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            fetched = build.FetchedSource(
                text="ads.covered.example\ndomain-only.example\n",
                sha256=build.sha256_text("fixture"),
                byte_count=8,
                etag=None,
                last_modified=None,
            )

            with mock.patch.object(build, "fetch_source", return_value=fetched):
                for tier in build.TIER_DETAILS:
                    report = build.build(config_path, allowlist, dist, use_baseline=False, tier=tier)
                    names = build.artifact_names(tier)
                    module = (dist / names.module).read_text(encoding="utf-8")
                    egern_document = json.loads((dist / names.egern_config).read_text(encoding="utf-8"))
                    self.assertEqual(module, (dist / names.surge_module).read_text(encoding="utf-8"))
                    self.assertIn("[URL Rewrite]", module)
                    self.assertNotIn("[Script]", module)
                    self.assertNotIn("[URL Rewrite]", (dist / names.ruleset).read_text(encoding="utf-8"))
                    self.assertEqual(report["splash"]["excluded_by_domain_count"], 1)
                    self.assertEqual(report["splash"]["rule_count"], 2)
                    self.assertEqual(report["splash"]["surge_rule_count"], 1)
                    self.assertEqual(report["splash"]["egern_url_rewrite_count"], 1)
                    self.assertEqual(report["splash"]["egern_map_local_count"], 0)
                    self.assertEqual(report["splash"]["egern_body_rewrite_count"], 1)
                    self.assertEqual(report["splash"]["mitm_host_count"], 2)
                    self.assertEqual(report["splash"]["surge_mitm_host_count"], 1)
                    self.assertIn(names.surge_module, report["artifacts"])
                    self.assertIn(names.egern_config, report["artifacts"])
                    self.assertEqual(
                        {item["match"] for item in egern_document["url_rewrites"]},
                        {
                            build.splash.pattern(item)
                            for item in report["splash"]["entries"]
                            if "rewrite" not in item
                        },
                    )
                    self.assertEqual(
                        {
                            item["response_jq"]["match"]
                            for item in egern_document["body_rewrites"]
                        },
                        {
                            build.splash.pattern(item)
                            for item in report["splash"]["entries"]
                            if "rewrite" in item
                        },
                    )
                    self.assertNotIn("app.bilibili.com", module)

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
