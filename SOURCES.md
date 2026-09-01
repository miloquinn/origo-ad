# Sources and license review

本页记录截至 2026-09-01 的上游取证。自动生成报告记录每次实际拉取内容的 SHA-256；下表的提交与日期用于说明本次选型，不用于锁死每日更新。

## Included by default

| Source | Input and format | License | Activity checked | Default risk decision |
| --- | --- | --- | --- | --- |
| [HaGeZi Multi LIGHT](https://github.com/hagezi/dns-blocklists) | [`wildcard/light-onlydomains.txt`](https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/light-onlydomains.txt), one exact hostname per line | [GPL-3.0](https://github.com/hagezi/dns-blocklists/blob/main/LICENSE) | repository pushed 2026-09-01; upstream file reports an 8-hour expiry | Included as the baseline. Upstream labels LIGHT as relaxed/minimal-breakage. Exact entries remain `DOMAIN`, so aggregation does not broaden them to suffixes. |
| [ACL4SSR BanAD](https://github.com/ACL4SSR/ACL4SSR) | [`Clash/BanAD.list`](https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/BanAD.list), Clash classical rules | [CC-BY-SA-4.0](https://github.com/ACL4SSR/ACL4SSR/blob/master/LICENSE) | repository pushed 2026-08-31 | Included for Chinese ad-network coverage. `DOMAIN-KEYWORD` is intentionally excluded because keyword matching can affect unrelated hosts. CC-BY-SA-4.0 is [one-way compatible with GPLv3](https://creativecommons.org/compatible-licenses/). |
| [AdGuard CNAME disguised ads](https://github.com/AdguardTeam/cname-trackers) | [`combined_disguised_ads_justdomains.txt`](https://raw.githubusercontent.com/AdguardTeam/cname-trackers/master/data/combined_disguised_ads_justdomains.txt), exact and explicit `*.` hosts | [MIT](https://github.com/AdguardTeam/cname-trackers/blob/master/LICENSE) | latest data timestamp 2026-08-17 | Included only for the ads category. Exact hosts stay exact; explicit wildcard hosts become suffix rules. Trackers, clickthroughs, microsites and mail trackers are not imported. |

### Changes made by Origo Ad

The included inputs are normalized to lowercase ASCII hostnames, invalid/non-domain rule types are discarded, duplicate and suffix-covered entries are removed, the local allowlist is applied, and Egern/Surge-compatible artifacts are rendered. These adaptations and the combined output are distributed under GPL-3.0-only while preserving upstream attribution.

## Reviewed but excluded

| Project | License / activity | Why it is reference-only |
| --- | --- | --- |
| [SukkaW/Surge](https://github.com/SukkaW/Surge) | AGPL-3.0 except a separately licensed China IP file; repository pushed 2026-08-31 | The generated [`reject` domainset](https://ruleset.skk.moe/List/domainset/reject.conf) is active and well engineered, but intentionally combines ads, tracking, privacy, anti-mining and other categories. Its scope and AGPL obligations do not fit this focused GPL-3.0-only default artifact. Its whitelist-first build design informed this project's safety model. |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | GPL-2.0; repository pushed 2026-08-31 | The repository is active, but [`AdvertisingLite_Domain.list`](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/AdvertisingLite/AdvertisingLite_Domain.list) still reports `UPDATED: 2025-12-08`, warns of possible false positives, and already incorporates ACL4SSR material. GPL-2.0 content is not mixed into the GPL-3.0-only output. The project's reject-only/no-third-party-script safety guidance informed the domain-only design. |
| [ACL4SSR BanProgramAD](https://github.com/ACL4SSR/ACL4SSR/blob/master/Clash/BanProgramAD.list) | CC-BY-SA-4.0; same active repository | App-specific entries provide more coverage but the upstream itself notes possible side effects. It is excluded from the balanced default until each addition can be covered by local regression cases. |
| [AdGuard CNAME trackers](https://github.com/AdguardTeam/cname-trackers) | MIT; data updated 2026-08-17 | The upstream warns that blocking all disguised trackers may break sites. Only the much narrower ads category is used. |

## Maintenance rules

- Moving branch URLs are intentional for daily refreshes; the build report records the exact downloaded SHA-256 and response metadata.
- A source license change is a manual-review event. Do not merely edit `sources.json` to silence a mismatch.
- Do not add executable scripts, redirects, response rewrites, MITM hostnames, full privacy lists, anti-phishing lists or malware lists to the balanced artifact.
- Upstream allowlists are evidence, not automatic inputs. Add a local exception only after reproducing an Origo Ad false positive.
- This review is engineering due diligence, not legal advice.
