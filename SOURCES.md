# Sources and license review

本页记录截至 2026-09-02 的上游取证。自动生成报告记录每次实际拉取内容的 SHA-256；下表的提交与日期用于说明本次选型，不用于锁死每日更新。

## Included by tier

| Source | Tier | Input and format | License | Risk decision |
| --- | --- | --- | --- | --- |
| [HaGeZi Multi LIGHT](https://github.com/hagezi/dns-blocklists) | Lite, Balanced, Powerful | [`wildcard/light-onlydomains.txt`](https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/light-onlydomains.txt), one exact hostname per line | [GPL-3.0](https://github.com/hagezi/dns-blocklists/blob/main/LICENSE) | Relaxed/minimal-breakage baseline. Broader tiers explicitly inherit it so they cannot silently lose Lite coverage. Exact entries remain `DOMAIN`, so aggregation does not broaden them to suffixes. |
| [HaGeZi Multi PRO++ mini](https://github.com/hagezi/dns-blocklists) | Powerful | [`wildcard/pro.plus.mini-onlydomains.txt`](https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/pro.plus.mini-onlydomains.txt), one exact hostname per line | [GPL-3.0](https://github.com/hagezi/dns-blocklists/blob/main/LICENSE) | Size-optimized for mobile/limited-memory blockers but deliberately aggressive. Upstream warns that some legitimate domains may be blocked, so it is never enabled by default. |
| [ACL4SSR BanAD](https://github.com/ACL4SSR/ACL4SSR) | Balanced, Powerful | [`Clash/BanAD.list`](https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/BanAD.list), Clash classical rules | [CC-BY-SA-4.0](https://github.com/ACL4SSR/ACL4SSR/blob/master/LICENSE) | Chinese ad-network coverage. `DOMAIN-KEYWORD` is intentionally excluded because keyword matching can affect unrelated hosts. CC-BY-SA-4.0 is [one-way compatible with GPLv3](https://creativecommons.org/compatible-licenses/). |
| [ACL4SSR BanProgramAD](https://github.com/ACL4SSR/ACL4SSR) | Powerful | [`Clash/BanProgramAD.list`](https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/BanProgramAD.list), Clash classical rules | [CC-BY-SA-4.0](https://github.com/ACL4SSR/ACL4SSR/blob/master/LICENSE) | App-specific advertising and analytics coverage. Included only in Powerful because upstream notes possible minor side effects; keyword and IP rules remain excluded. |
| [AdGuard CNAME disguised ads](https://github.com/AdguardTeam/cname-trackers) | Balanced, Powerful | [`combined_disguised_ads_justdomains.txt`](https://raw.githubusercontent.com/AdguardTeam/cname-trackers/master/data/combined_disguised_ads_justdomains.txt), exact and explicit `*.` hosts | [MIT](https://github.com/AdguardTeam/cname-trackers/blob/master/LICENSE) | Ads category only. Exact hosts stay exact; explicit wildcard hosts become suffix rules. Trackers, clickthroughs, microsites and mail trackers are not imported. |

Activity snapshot: both HaGeZi tier files reported updates on 2026-09-01 and an 8-hour expiry; ACL4SSR was active on 2026-08-31; the AdGuard CNAME ads dataset reported its latest update on 2026-08-17. Moving URLs are guarded by per-source hashes and historical count thresholds rather than treated as immutable releases.

### Changes made by Origo Ad

The included inputs are normalized to lowercase ASCII hostnames, invalid/non-domain rule types are discarded, duplicate and suffix-covered entries are removed, the local allowlist is applied, and Egern/Surge-compatible artifacts are rendered. These adaptations and the combined output are distributed under GPL-3.0-only while preserving upstream attribution.

## Reviewed but excluded

| Project | License / activity | Why it is reference-only |
| --- | --- | --- |
| [SukkaW/Surge](https://github.com/SukkaW/Surge) | AGPL-3.0 except a separately licensed China IP file; repository pushed 2026-08-31 | The generated [`reject` domainset](https://ruleset.skk.moe/List/domainset/reject.conf) is active and well engineered, but intentionally combines ads, tracking, privacy, anti-mining and other categories. Its scope and AGPL obligations do not fit this focused GPL-3.0-only default artifact. Its whitelist-first build design informed this project's safety model. |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | GPL-2.0; repository pushed 2026-08-31 | The repository is active, but [`AdvertisingLite_Domain.list`](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/AdvertisingLite/AdvertisingLite_Domain.list) still reports `UPDATED: 2025-12-08`, warns of possible false positives, and already incorporates ACL4SSR material. GPL-2.0 content is not mixed into the GPL-3.0-only output. The project's reject-only/no-third-party-script safety guidance informed the domain-only design. |
| [AdGuard CNAME trackers](https://github.com/AdguardTeam/cname-trackers) | MIT; data updated 2026-08-17 | The upstream warns that blocking all disguised trackers may break sites. Only the much narrower ads category is used. |

## Maintenance rules

- Moving branch URLs are intentional for daily refreshes; the build report records the exact downloaded SHA-256 and response metadata.
- A source license change is a manual-review event. Do not merely edit `sources.json` to silence a mismatch.
- Do not add executable scripts, redirects, response rewrites or MITM hostnames to either tier. Broad privacy/security categories require explicit Powerful-only review.
- Upstream allowlists are evidence, not automatic inputs. Add a local exception only after reproducing an Origo Ad false positive.
- This review is engineering due diligence, not legal advice.
