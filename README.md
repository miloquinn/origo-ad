# Origo Ad

Origo Ad 是一个独立的开源广告与追踪规则聚合项目。Lite / Balanced / Powerful 三档模块包含域名拦截和经过人工筛选的 App 开屏广告 URL 拒绝规则，不执行第三方脚本、不下载远程响应文件。单独的 `.list` RULE-SET 仍然只有域名规则。

**2026-09-07 起，原有三个 `.module` 地址增加了开屏广告处理和精确 MITM 主机名单。** HTTPS 开屏接口需要在客户端启用 MITM，并安装、信任客户端自己生成的 CA 证书。只更新模块而未启用 MITM，不会获得这些 HTTPS URL 规则的效果；原有域名拦截仍有效。模块不携带 CA 私钥、不修改证书信任、不强制启用全局 MITM。

## 稳定产物

- [Egern Lite 模块 `origo-ad-lite.module`](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-lite.module)：最低域名规则开销档，LIGHT 精确域名基线 + 精选开屏规则。
- [Surge Lite RULE-SET `origo-ad-lite.list`](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-lite.list)：Lite 的纯域名无策略版本，不含开屏 URL 处理。
- [Egern 模块 `origo-ad-balanced.module`](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.module)：日常推荐主产物，包含域名 `REJECT` 与精选开屏规则。
- [Surge classical RULE-SET `origo-ad-balanced.list`](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.list)：不带策略，供支持 `DOMAIN` / `DOMAIN-SUFFIX` RULE-SET 语法的客户端引用。
- [Egern Powerful 模块 `origo-ad-powerful.module`](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-powerful.module)：域名覆盖更激进的可选档，附带同一组精选开屏规则。
- [Surge Powerful RULE-SET `origo-ad-powerful.list`](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-powerful.list)：Powerful 的无策略版本。
- 生成报告 [`build-report-lite.json`](https://github.com/miloquinn/origo-ad/raw/main/dist/build-report-lite.json)、[`build-report.json`](https://github.com/miloquinn/origo-ad/raw/main/dist/build-report.json) 与 [`build-report-powerful.json`](https://github.com/miloquinn/origo-ad/raw/main/dist/build-report-powerful.json)：分别记录三档的上游 URL、许可证、SHA-256、原始/接受/排除数量，以及最终产物摘要和哈希。

Egern 示例：

```yaml
modules:
- name: Origo Ad Lite
  url: https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-lite.module
  enabled: false
- name: Origo Ad Balanced
  url: https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.module
  enabled: true
- name: Origo Ad Powerful
  url: https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-powerful.module
  enabled: false
```

三档不要同时启用。低开销优先时使用 Lite，日常默认使用 Balanced；明确需要更多追踪、遥测域名覆盖，并能自行处理误杀时再切换 Powerful。三档开屏候选相同，不以更多脚本或更宽的 MITM 来区分档位。

本仓库没有修改或打包 Origo VPN 配置，不发布第三方脚本或“解锁”功能。Egern 可以导入 Surge 格式模块，因此保留现有 `.module` 格式和地址。Surge 用户使用下面的完整模块；仅订阅 `.list` 不会加载 URL Rewrite / MITM：

- [Surge Lite 完整模块](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-lite.sgmodule)
- [Surge Balanced 完整模块](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.sgmodule)
- [Surge Powerful 完整模块](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-powerful.sgmodule)

每档 `.module` 与 `.sgmodule` 内容相同。完整模块已经包含域名规则，无需再重复订阅同档 `.list`。

## 默认策略

域名列表追求覆盖与误杀之间的平衡：

1. HaGeZi Multi LIGHT 提供经过低误杀治理的精确主机名基线；精确规则不会被擅自扩大成整个域名后缀。
2. ACL4SSR BanAD 补充常见中文广告联盟；只接受 `DOMAIN` 和 `DOMAIN-SUFFIX`，高误杀风险的 `DOMAIN-KEYWORD`、IP 和 URL 正则会被统计后丢弃。
3. AdGuard CNAME disguised ads 只补充 ads 分类；普通条目保持精确匹配，明确的 `*.` 条目才转换为后缀匹配。
4. `config/allowlist.txt` 在合并前保护登录、支付、系统连通性、证书检查和开发基础设施等关键主机。如果某条上游后缀规则会覆盖受保护主机，该后缀规则整体不发布。
5. 规则统一转为小写 ASCII hostname，拒绝 URL、IP、Unicode、非法标签，跨源去重，并删除已被更宽后缀覆盖的精确项。

Lite 的域名部分只保留 HaGeZi Multi LIGHT 的精确域名，并使用同一白名单和安全门。Balanced 在 Lite 基础上增加 ACL4SSR BanAD 与 AdGuard CNAME ads。

Powerful 的域名部分在同一安全边界内继承 Balanced 的 LIGHT 基线，再叠加 HaGeZi Multi PRO++ mini 和 ACL4SSR BanProgramAD，确保覆盖范围不会比 Balanced 窄。PRO++ mini 是为移动端/有限内存过滤器缩减后的激进列表；上游明确提醒可能误杀少量正常域名，因此它不是默认档。域名上游仍不接受 `DOMAIN-KEYWORD`、IP、URL 正则、脚本或 MITM；开屏 URL 规则来自独立、人工审查的本地清单。

完整来源、许可证、活跃度和排除理由见 [SOURCES.md](SOURCES.md)。

## 开屏广告范围与使用

[`config/splash.json`](config/splash.json) 记录 45 个开屏端点候选，包括腾讯新闻、QQ 音乐、腾讯地图、起点读书、大众点评、拼多多、麦当劳、天翼云盘、途牛、微店、Jump 等接口。它们来自用户提供的 ultra+ 快照中的开屏端点事实，由 Origo 重新编写有主机和路径边界的匹配规则。端点是否仍用于某个 App 版本、广告是否已缓存、拒绝后是否保留倒计时，需要真机确认；这些不是“已验证支持 45 个 App”的承诺。

- 三档使用同一份候选清单；已被该档域名规则覆盖的主机不再添加 URL 规则和 MITM，因此不同档位的有效 URL 数量可能不同。不会为了 URL 去广告而放行已拦截域名。
- 只匹配明确的开屏路径；共享 API 域名不会被扩大成整域名拒绝。路径中的 `{version}` 只匹配数字 API 版本，资源目录只在斜杠边界向下匹配。
- MITM 仅列出实际使用 URL 规则的精确主机，无通配符。精确主机仍可能同时承载普通 API；MITM 的解密范围是主机级，URL 拒绝范围才是路径级。
- 不导入 ultra+ 的账户资料、固件更新、书架刷新、微信链接提示处理，也不导入跨作者脚本或远程 Map Local 文件。
- `config/allowlist.txt` 是域名生成白名单，不代表某主机被排除于 MITM。开屏清单单独审核。不要同时启用 ultra+、startingad 等重叠模块来测试本项目。
- 开屏清单固定在 Git 中，日更任务不会自动从 ultra+ 增加端点。增删要改清单并通过匹配、正常功能反例和产物验证。

Egern：更新当前启用档位的模块，在客户端检查 URL 重写和 MITM 主机是否已导入；如需 HTTPS 开屏处理，在客户端自行启用 MITM 并信任本机生成的 CA。Surge：导入同档 `.sgmodule`，启用 Rewrite / MITM 并使用自己的 CA。不要使用来源不明的现成 CA。

验证时选一个常用 App，彻底退出后重新打开，在客户端请求记录中确认具体开屏 URL 命中；再检查登录、首页、搜索等正常操作。若异常，先停用模块定位；需要保留纯域名过滤时改用同档 `.list`。已有缓存、本地渲染广告、证书固定或未经过代理的流量，可能无法通过这些规则消除。

## 本地构建与验证

只需要 Python 3.10+ 标准库：

```bash
python3 -m unittest discover -s tests -v
python3 tools/build.py --tier lite
python3 tools/build.py
python3 tools/build.py --tier powerful
python3 tools/validate.py
```

首次建立经过人工审查的新基线时，可以显式跳过旧报告的增减比较：

```bash
python3 tools/build.py --tier lite --no-baseline
python3 tools/build.py --no-baseline
python3 tools/build.py --tier powerful --no-baseline
```

`--no-baseline` 不会跳过来源数量、输入大小、非法条目比例、最终数量、格式、开屏清单、空产物或哈希一致性校验；日常自动更新不会使用这个参数。

## 发布安全门

生成器在写入 `dist` 前完成全部检查：

- 当前档位的全部必需上游均须成功返回 UTF-8 文本，且不能超过配置的字节上限。
- 每个上游的规范化数量必须落在独立的最小/最大范围内。
- 若已有对应档位的生成报告，每来源和最终产物都必须通过“相对变化 + 绝对变化”双阈值；小幅日常波动不会误报，大规模污染或清空会停止发布。
- 最终产物必须非空；Lite 必须在 35,000–60,000 条之间，Balanced 必须在 40,000–70,000 条之间，Powerful 必须在 60,000–90,000 条之间，且均须排序稳定、无重复、模块中的域名部分与 RULE-SET 内容一致。
- 离线总验证还会检查 `Lite ⊆ Balanced ⊆ Powerful` 的语义覆盖关系。
- 开屏规则必须来自本地清单，模块附加段必须与清单生成结果逐字一致；检查精确 MITM 主机、无脚本、无重复及与域名拦截的去重。
- `.module` / `.sgmodule` 必须一致；`.list` 继续保持纯域名格式。
- 报告中的 SHA-256 必须与文件实际内容一致，并记录开屏清单哈希和有效端点。
- 所有产物先在临时目录完成，再替换 `dist`，失败不会发布新结果。

## GitHub Actions

`.github/workflows/update-rules.yml` 每天 02:17 UTC 运行，也支持手动触发。流程依次运行单元测试、联网构建 Lite、Balanced、Powerful 和三档离线验证。任何上游请求、格式或安全门失败都会使任务失败，并保留仓库中上一版已验证产物。

工作流只暂存 `dist`；如果内容没有变化，不会创建提交。若产物确实变化且全部验证通过，才会以 `github-actions[bot]` 提交并推送。并发更新不会互相取消，避免构建进行到一半时被中断。

## 许可证

本项目代码及组合产物采用 `GPL-3.0-only`，见 [LICENSE](LICENSE)。每个上游仍保留自己的许可证与署名：HaGeZi 为 GPL-3.0，ACL4SSR 为 CC-BY-SA-4.0，AdGuard CNAME Trackers 为 MIT。Creative Commons 官方将 CC-BY-SA-4.0 到 GPLv3 定义为单向兼容；本项目在报告和 [SOURCES.md](SOURCES.md) 中保留来源、许可和改动说明。

规则无法保证零误杀。遇到问题时，请先确认触发的具体域名，再提交最小化的 allowlist 修正；不要用放行整个顶级服务域的方式掩盖问题。
