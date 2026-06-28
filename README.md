# Origo Ad

Origo Ad 是一组面向 Egern 的去广告模块和 Origo VPN 配置模板。

它把仍在维护的上游去广告规则重新打包成三档：省电、日常、强力。默认思路不是一上来就把所有脚本和响应体处理全打开，而是在尽量保留广告拦截效果的同时，控制 iPhone 上 Egern 的耗电和误伤。

## 快速链接

- Lite: [dist/origo-ad-lite.module](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-lite.module)
- Balanced: [dist/origo-ad-balanced.module](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.module)
- Powerful: [dist/origo-ad-powerful.module](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-powerful.module)
- Origo VPN 模板: [dist/origo-vpn-template.yaml](https://github.com/miloquinn/origo-ad/raw/main/dist/origo-vpn-template.yaml)

## 模块档位

运行生成器后会得到：

- `dist/origo-ad-lite.module`
  - 最省电档。
  - 只保留上游模块里低成本的域名/IP 类 `Rule` 拦截。
  - 丢弃 `URL-REGEX`、`URL Rewrite`、`Body Rewrite`、`Map Local`、`MITM`、`Script`。
  - 适合只想要基础拦截、优先省电的配置。

- `dist/origo-ad-balanced.module`
  - 日常推荐档。
  - 保留 `Rule`、`URL Rewrite`、低成本 `Rewrite`、`Map Local`、`MITM`。
  - `MITM` 会合并为一条 `hostname = %APPEND% ...`，并补入旧配置里的 Google/YouTube/归因统计等泛域名。
  - 仍然丢弃 `Body Rewrite` 和 `Script`，这是最主要的省电点。
  - 适合默认开启。

- `dist/origo-ad-powerful.module`
  - 最强去广告档。
  - 保留 `Argument`、`Rule`、`URL Rewrite`、`Rewrite`、`Map Local`、`Body Rewrite`、`Script`、`MITM`。
  - 去广告最强，但会重新引入响应体处理和脚本执行，更耗电，也更容易误伤。
  - 适合某些 App 广告仍然明显时手动切换，不建议和 Lite/Balanced 同时开。

- `dist/origo15-module-snippet.yaml`
  - 可以复制到你的 Egern 配置里参考。
  - 默认关闭原来的 `StartUpAds.module` / `BlockAds.module`，换成生成后的省电模块 URL 占位。

- `dist/build-report.json`
  - 记录上游来源、各 section 原始数量、保留数量、丢弃数量。

## 本地生成

```bash
cd /Users/xiaoyuan/work/origo-ad
/usr/bin/python3 tools/build.py
```

默认读取：

```text
/Users/xiaoyuan/Downloads/origo15.yaml
```

如果只是想重新生成模块，不需要读取原配置也可以：

```bash
/usr/bin/python3 tools/build.py --no-profile
```

## 推荐接入方式

先用 `balanced`。

在 Egern 配置里只开启一个 Origo Ad 档位。默认推荐：

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

配置片段示例会生成到：

```text
dist/origo15-module-snippet.yaml
```

如果还想进一步省电，再换 `lite`，但 HTTPS rewrite / map local 类去广告会明显变弱。

如果还不够，再手动换 `powerful`。不要同时开三档，开 Powerful 时建议关掉 Lite/Balanced，避免重复处理。

## Origo VPN 模板

公开模板位于：

```text
https://github.com/miloquinn/origo-ad/raw/main/dist/origo-vpn-template.yaml
```

模板来自个人 `origo20.yaml`，但已经脱敏：

- 外部订阅 URL 改为 `YOUR_ORIGO_SUB_TOKEN`、`YOUR_VALTROGEN_ACCESS_KEY`、`YOUR_SANMAO_TOKEN`、`YOUR_PQ_TOKEN` 占位。
- 移除了 `ca_p12` 和 `ca_passphrase`，避免公开 Egern CA 证书。
- 保留策略组、规则、MITM hostnames、模块开关和 Origo Ad Balanced 接入方式。

使用模板时，需要把占位符替换为自己的订阅信息；Egern CA 证书建议在本机重新生成或导入，不要使用公开文件承载私有证书。

## GitHub Actions 自动更新

仓库里已经带了工作流：

```text
.github/workflows/update-modules.yml
```

它会：

- 每 6 小时自动运行一次。
- 也可以在 GitHub Actions 页面手动点 `Run workflow`。
- 拉取 `sources.json` 里的活跃上游模块。
- 重新生成 `dist/origo-ad-lite.module`、`dist/origo-ad-balanced.module` 和 `dist/origo-ad-powerful.module`。
- 确认 lite / balanced 里没有 `[Body Rewrite]`、`[Script]`、`script_url`、`body_required`。
- 纯去广告 LoonLab 模块会被合并进生成产物；解锁会员、功能增强、定时任务类模块建议继续作为独立模块按需开启。
- 只有上游内容真的变了，才自动 commit 并 push。

Egern 可以直接引用 raw URL：

```text
https://github.com/miloquinn/origo-ad/raw/main/dist/origo-ad-balanced.module
```

也可以本地生成时指定 URL：

```bash
/usr/bin/python3 tools/build.py --base-url "https://github.com/<你的 GitHub 用户名>/<仓库名>/raw/main/dist"
```

### 创建远程仓库

如果你用 GitHub CLI：

```bash
cd /Users/xiaoyuan/work/origo-ad
gh repo create origo-ad --public --source=. --remote=origin --push
```

之后 GitHub Actions 就会按计划自动更新。

## 省电原则

从重到轻大概是：

1. `Script` / `Body Rewrite`
2. 大量 `Map Local` / `URL Rewrite`
3. `URL-REGEX` 规则
4. 普通 `DOMAIN` / `DOMAIN-SUFFIX` / `IP-CIDR` 拦截

所以 lite 默认把 1、2、3 都删掉；balanced 保留 MITM 和 rewrite 但删掉 1；powerful 全部保留。

## 上游来源

上游 URL 在 `sources.json`。当前默认源：

- `fmz200/wool_scripts` 的 `Surge/module/blockAds.module`
- `blackmatrix7/ios_rule_script` 的 `rewrite/Surge/AdvertisingLite/AdvertisingLite.sgmodule`
- `LoonLab / 103516` 的纯去广告插件：
  - `Bilibili.lpx`
  - `X_Web.lpx`
  - `Xueqiu.lpx`
  - `Reddit.lpx`
  - `RedNote.lpx`

生成器每次会重新拉取上游，输出报告里会记录时间和数量。

没有合并进 `origo-ad` 的 LoonLab 插件主要是带解锁或功能增强的模块，例如 `BaiduNetDisk.lpx`、`YouTube.lpx`、`NeteaseMusic.lpx`、`BodianMusic.lpx`、`ChinaMobile.lpx`、`IPPure.lpx`、`AppStoreMonitor.lpx`。这些更适合在 Egern 配置里保持独立开关。
