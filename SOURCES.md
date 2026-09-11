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
- Do not import executable scripts, redirects or remote response payloads. The user-authorized splash lane may publish reviewed URL rejects, inline constant responses, finite native JSON filters and literal MITM hosts from `config/splash.json`; never convert shared API hosts into domain blocks. Broad privacy/security categories require explicit Powerful-only review.
- Upstream allowlists are evidence, not automatic inputs. Add a local exception only after reproducing an Origo Ad false positive.
- This review is engineering due diligence, not legal advice.


## Curated opening-ad endpoints (2026-09-08)

The user explicitly requested opening-ad blocking in all three tiers. The reviewed reference is [deezertidal/Surge_Module](https://github.com/deezertidal/Surge_Module), whose current tree at `5cc38f47de2ccb13ed8b06d99a1d753cd3afb3c9` contains a README, `files/` and `rule/`. Its README links to modules hosted on yfamilys.com. The GitHub tree does not contain the supplied ultra+ module or a root license file; we do not describe it as a licensed, vendored source or claim that the pasted snapshot corresponds to that commit.

`config/splash.json` records the repository, module URL, user-supplied snapshot SHA-256 and source line for each endpoint fact. Entries with `source_url` instead cite an immutable source revision and its own line numbers. Origo independently renders bounded literal-host/path rules from 68 selected endpoints: 45 original rejects, 12 inline local responses and 11 Egern-only field modifications. We do not vendor the original module, remote scripts, response files or broad regular expressions. No automated scraper updates this lane.

Additional implementation evidence (read as endpoint/response-shape facts, not downloaded as executable dependencies):

- [Biliverse Bilibili response handler, fixed revision](https://github.com/Biliverse/ADBlock/blob/43b07841fa55ba77e29d478cab0be44c8b49a3c2/src/process/Response.mjs#L73-L90): four explicit splash paths on `app.bilibili.com` and `app.biliapi.net`. Origo deletes only `data.show`, `event_list` and `preload`; unlike the reference it preserves account fields. No third-party JavaScript is executed.
- [fmz200 JD handler, fixed revision](https://github.com/fmz200/wool_scripts/blob/6e7bf91a2b412ff75177084e0d593af19a3c5947/Scripts/jingdong/jingdong.js#L258-L265): `functionId=start` changes advertising images and display count, preserving other startup fields.
- [fmz200 Xiaohongshu handler, fixed revision](https://github.com/fmz200/wool_scripts/blob/6e7bf91a2b412ff75177084e0d593af19a3c5947/Scripts/xiaohongshu/xiaohongshu.js#L52-L64): future-dated ad group and creative windows, preserving configuration shape.
- [fmz200 Bevol launch handler, fixed revision](https://github.com/fmz200/wool_scripts/blob/3ca7487b4e4b86d9af76e50df72c62eacfbb659e/Scripts/mlxx/mlxx.js#L47-L51) and its [module route](https://github.com/fmz200/wool_scripts/blob/3ca7487b4e4b86d9af76e50df72c62eacfbb659e/Surge/module/split/partM/MeiLiXiuXing.sgmodule#L10-L11): Egern processes only `api.bevol.com/appmain/app/home/launch`, clearing `result.openAppAdvert.openAdvertOnline` when it is an array and zeroing numeric `result.openAdKeepTime`. The finite jq template preserves other launch settings, missing fields and unknown types. The account, membership and other branches of the upstream script are excluded; the mixed launch response has no Surge reject or empty-response equivalent.
- [fmz200 Meituan Waimai](https://github.com/fmz200/wool_scripts/blob/6e7bf91a2b412ff75177084e0d593af19a3c5947/Surge/module/split/partM/Meituan-MeituanWaimai.sgmodule#L9-L10), [Zhihu](https://github.com/fmz200/wool_scripts/blob/6e7bf91a2b412ff75177084e0d593af19a3c5947/Surge/module/split/partZ/Zhihu.sgmodule#L45-L47) and [Xianyu](https://github.com/fmz200/wool_scripts/blob/6e7bf91a2b412ff75177084e0d593af19a3c5947/Surge/module/split/partX/XianYu.sgmodule#L42-L43): independently rendered, bounded advertisement branches with inline `{}` responses.

The other six local-response candidates retain the response class from the supplied ultra+ snapshot. Empty JSON is `{}`; whitespace-only reject-200 payloads are normalized to an empty body. Taobao's main splash response mixes initialization fields and remains excluded pending a current device response sample. Shared native/Surge local responses are tested for exact status, body and content-type equivalence. Egern-only jq edits are never translated into whole-response rejection for Surge.

All tiers use the same reviewed candidates. Entries already covered by a tier's domain blocks are omitted from its URL/MITM sections. The build report records selected entries and how many were already covered. The one new allowlist correction is the exact shared API host `app.biliapi.net`: Powerful previously blocked it wholesale, while the fixed Biliverse handler above also processes normal `/x/v2/feed/index` requests on that host. It now remains available with path-scoped splash filtering; other Bilibili tracking hosts remain blocked. This is based on the shared API contract, not a claim of phone-level reproduction.

Official implementation references:

- [Egern FAQ: Surge module import](https://egernapp.com/zh-CN/docs/faq/)
- [Egern native modules](https://egernapp.com/docs/configuration/modules/)
- [Egern native response jq filters](https://egernapp.com/docs/configuration/body_rewrites/)
- [Egern rule_set reference syntax](https://egernapp.com/docs/configuration/rules/)
- [Rust regex supported syntax](https://docs.rs/regex/latest/regex/): no look-around or backreferences. The installed Egern 2.20 packet-tunnel binary contains this regex engine; matching expressions therefore use only the shared regular subset. Tests additionally compile them with ripgrep's default Rust engine when it is available.
- [Egern inline Map Local schema](https://egernapp.com/docs/configuration/example/)
- [Surge inline Map Local syntax and minimum versions](https://manual.nssurge.com/http/map-local.html)
- [Surge URL Rewrite syntax and HTTPS requirement](https://manual.nssurge.com/http/url-rewrite.html)
- [Surge module hostname append](https://manual.nssurge.com/profile/module.html)
- [Surge HTTPS decryption](https://manual.nssurge.com/http/mitm.html)

Verification covers generation, matching boundaries, negative URLs representing normal functionality, execution of JSON filters against representative fixtures when jq is present, independent Ruby/Psych YAML parsing, domain overlap, provenance hashes and tamper rejection. Native modules use one tier-bound rule_set reference instead of tens of thousands of inline rule objects. This removes the large native parsing load without claiming that memory was the cause of the reported startup failure. Client startup, trusted-CA setup, certificate pinning, cached/IP-direct requests and live App-version behavior require device verification and are not implied by these tests.
