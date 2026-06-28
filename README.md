# Origo Ad

这个小项目把仍在维护的去广告模块重新打包成更省电的 Egern 模块。

目标不是追求“挡得最狠”，而是降低 iPhone 上 Egern 的持续处理成本：少做 HTTPS 解密、少跑响应脚本、少读响应 body。

## 输出

运行生成器后会得到：

- `dist/origo-ad-lite.module`
  - 最省电。
  - 只保留上游模块里低成本的域名/IP 类 `Rule` 拦截。
  - 默认丢弃 `URL-REGEX`、`URL Rewrite`、`Body Rewrite`、`Map Local`、`Script`。

- `dist/origo-ad-balanced.module`
  - 折中版。
  - 保留 `Rule`、`URL Rewrite`、`Map Local`。
  - 仍然丢弃 `Body Rewrite` 和 `Script`，这是最主要的省电点。

- `dist/origo-ad-powerful.module`
  - 最强版。
  - 保留 `Rule`、`URL Rewrite`、`Map Local`、`Body Rewrite`、`Script`、`MITM`。
  - 去广告最强，但会重新引入响应体处理和脚本执行，更耗电。

- `dist/origo15-module-snippet.yaml`
  - 可以复制到你的 Egern 配置里参考。
  - 默认关闭原来的 `StartUpAds.module` / `BlockAds.module`，换成生成后的省电模块 URL 占位。

- `dist/build-report.json`
  - 记录上游来源、各 section 原始数量、保留数量、丢弃数量。

## 使用

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

先用 `lite`。

把 `dist/origo-ad-lite.module` 放到一个 Egern 能访问的 HTTPS URL，然后在 Egern 配置里把原来的重模块关掉，新增这个轻量模块。

配置片段示例会生成到：

```text
dist/origo15-module-snippet.yaml
```

如果广告回来了，再换 `balanced`。

如果还不够，再手动换 `powerful`。不要同时开三档，开 Powerful 时建议关掉 Lite/Balanced，避免重复处理。

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
- 只有上游内容真的变了，才自动 commit 并 push。

推到 GitHub 后，Egern 可以直接引用 raw URL：

```text
https://github.com/<你的 GitHub 用户名>/origo-ad/raw/main/dist/origo-ad-lite.module
```

如果你的仓库名不是 `origo-ad`，或者默认分支不是 `main`，把 URL 对应改一下。

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

所以 lite 默认把 1、2、3 都删掉；balanced 删掉 1；powerful 全部保留。

## 上游来源

上游 URL 在 `sources.json`。当前默认源：

- `fmz200/wool_scripts` 的 `Surge/module/blockAds.module`
- `blackmatrix7/ios_rule_script` 的 `rewrite/Surge/AdvertisingLite/AdvertisingLite.sgmodule`

生成器每次会重新拉取上游，输出报告里会记录时间和数量。
