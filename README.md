# Origo Ad

Origo Ad 是一个独立的开源广告与追踪域名规则聚合项目。默认产物只包含域名级拦截：不执行第三方脚本，不做 URL/响应体重写，不要求 MITM，因此比旧版重写模块更容易审计，也更适合作为日常默认规则。

## 稳定产物

- [Egern 模块 `origo-ad-balanced.module`](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.module)：仓库当前明确支持的主产物，规则已带 `REJECT` 策略。
- [Surge classical RULE-SET `origo-ad-balanced.list`](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.list)：不带策略，供支持 `DOMAIN` / `DOMAIN-SUFFIX` RULE-SET 语法的客户端引用。
- [生成报告 `build-report.json`](https://github.com/miloquinn/origo-ad/raw/main/dist/build-report.json)：记录每个上游的 URL、许可证、SHA-256、原始/接受/排除数量，以及最终产物摘要和哈希。

Egern 示例：

```yaml
modules:
- name: Origo Ad Balanced
  url: https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.module
  enabled: true
```

本仓库没有修改或打包 Origo VPN 配置，也不再发布脚本、MITM 主机名或“解锁”类功能。

## 默认策略

默认列表追求覆盖与误杀之间的平衡：

1. HaGeZi Multi LIGHT 提供经过低误杀治理的精确主机名基线；精确规则不会被擅自扩大成整个域名后缀。
2. ACL4SSR BanAD 补充常见中文广告联盟；只接受 `DOMAIN` 和 `DOMAIN-SUFFIX`，高误杀风险的 `DOMAIN-KEYWORD`、IP 和 URL 正则会被统计后丢弃。
3. AdGuard CNAME disguised ads 只补充 ads 分类；普通条目保持精确匹配，明确的 `*.` 条目才转换为后缀匹配。
4. `config/allowlist.txt` 在合并前保护登录、支付、系统连通性、证书检查和开发基础设施等关键主机。如果某条上游后缀规则会覆盖受保护主机，该后缀规则整体不发布。
5. 规则统一转为小写 ASCII hostname，拒绝 URL、IP、Unicode、非法标签，跨源去重，并删除已被更宽后缀覆盖的精确项。

完整来源、许可证、活跃度和排除理由见 [SOURCES.md](SOURCES.md)。

## 本地构建与验证

只需要 Python 3.10+ 标准库：

```bash
python3 -m unittest discover -s tests -v
python3 tools/build.py
python3 tools/validate.py
```

首次建立经过人工审查的新基线时，可以显式跳过旧报告的增减比较：

```bash
python3 tools/build.py --no-baseline
```

`--no-baseline` 不会跳过来源数量、输入大小、非法条目比例、最终数量、格式、空产物或哈希一致性校验；日常自动更新不会使用这个参数。

## 发布安全门

生成器在写入 `dist` 前完成全部检查：

- 三个必需上游均须成功返回 UTF-8 文本，且不能超过配置的字节上限。
- 每个上游的规范化数量必须落在独立的最小/最大范围内。
- 若已有 `dist/build-report.json`，每来源和最终产物都必须通过“相对变化 + 绝对变化”双阈值；小幅日常波动不会误报，大规模污染或清空会停止发布。
- 最终产物必须非空、规则数在 40,000–70,000 之间、排序稳定、无重复，模块与 RULE-SET 内容必须一致。
- 报告中的 SHA-256 必须与文件实际内容一致。
- 所有产物先在临时目录完成，再替换 `dist`，失败不会发布新结果。

## GitHub Actions

`.github/workflows/update-rules.yml` 每天 02:17 UTC 运行，也支持手动触发。流程依次运行单元测试、联网构建和离线验证。任何上游请求、格式或安全门失败都会使任务失败，并保留仓库中上一版已验证产物。

工作流只暂存 `dist`；如果内容没有变化，不会创建提交。若产物确实变化且全部验证通过，才会以 `github-actions[bot]` 提交并推送。并发更新不会互相取消，避免构建进行到一半时被中断。

## 许可证

本项目代码及组合产物采用 `GPL-3.0-only`，见 [LICENSE](LICENSE)。每个上游仍保留自己的许可证与署名：HaGeZi 为 GPL-3.0，ACL4SSR 为 CC-BY-SA-4.0，AdGuard CNAME Trackers 为 MIT。Creative Commons 官方将 CC-BY-SA-4.0 到 GPLv3 定义为单向兼容；本项目在报告和 [SOURCES.md](SOURCES.md) 中保留来源、许可和改动说明。

规则无法保证零误杀。遇到问题时，请先确认触发的具体域名，再提交最小化的 allowlist 修正；不要用放行整个顶级服务域的方式掩盖问题。
