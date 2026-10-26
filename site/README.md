# 项目网站生成器

把仓库内容生成为一个静态网站：概览、进展、验证结果、各模块页面（含可交互原理图）和渲染后的文档。
只读仓库里的文件，**不需要仿真服务器，也不需要 PDK**。每个 PR 都会构建一次（`.github/workflows/site.yml`），
合并到 `main` 后部署到 GitHub Pages。

## 本地构建

```bash
pip install -e . -r site/requirements.txt     # adcflow + markdown-it-py（一次性）
python site/build.py                          # 生成 build/site/
python site/build.py --serve                  # 构建并在 http://127.0.0.1:8000/ 预览
```

构建出错（规格/结果读取失败、文档里有死链、页面内链接或锚点失效）时返回非零退出码；`--no-strict` 只报告不失败。

## 数据来源

| 页面 | 来源（用 `adcflow` 的读取函数，不重复实现逻辑） |
|---|---|
| 概览 | `specs/arch.yaml`（`adcflow.arch.Arch` 的派生量）、`results/` 中顶层 ENOB、所有规格的判定统计 |
| 进展 | `specs/blocks/*.yaml`（状态、负责人、版本）、网表文件是否存在、`git` 标签与最近修改日期 |
| 验证 | `adcflow.checks.load_results` / `judge`：用当前限值重新判定每个结果文件，哈希不一致标“过期” |
| 模块 | 端口、指标、用例来自 `specs/blocks/<block>.yaml`；原理图来自该模块的视图与测试台网表 |
| 文档 | `docs/*.md`、`CONTRIBUTING.md`（仓库内链接改写成站内页面或 GitHub 链接） |

模块状态变化（例如 `design/xtor/<block>/` 出现网表、`status` 变为 `xtor-wip`）后，重新构建即可，页面不需要手改。

## 原理图

原理图由托管的 RNL 网页查看器（<https://rich-netlist.github.io/rnl/viewer/>）绘制：页面里嵌入 `viewer/?embed=1&url=<网表地址>`，
切换网表用 `postMessage`；“完整查看器”按钮直接打开 `viewer/?url=<网表地址>`。查看器是从浏览器里去取网表的，所以网表必须能被
浏览器通过 HTTPS 访问，并允许跨域（CORS）；`@USE-PACKAGE(path="../rnl/adc28.rnl")` 这类相对路径要求保持 `design/` 的目录结构。

| `--netlist-base` | 网表位置 | 用途 |
|---|---|---|
| `pages`（默认） | 发布在站点旁边的 `repo/design/…`、`repo/tb/…`（同一目录结构） | 线上站点：和页面同一次构建、同一个提交，GitHub Pages 自带 `Access-Control-Allow-Origin: *` |
| `raw` | `https://raw.githubusercontent.com/<repo>/<提交>/…`（固定到提交，需先推送） | PR 预览与本地检查：不依赖本机服务器 |
| 任意 URL 前缀 | 该前缀下的仓库目录结构 | 特殊托管 |

本地用默认的 `pages` 模式时，网表由本机 `127.0.0.1` 提供，而查看器页面在 `https://` 上：新版 Chrome 会拦截公网页面访问本机地址
（“本地网络访问”权限），此时在地址栏允许该权限，或者改用 `--netlist-base raw`。`--serve` 已经给出 CORS 头。

## 文件

```
site/
  build.py             入口：读取数据、生成页面、复制网表、检查内链
  sitegen/data.py      从 specs / results / git 收集页面数据（调用 adcflow）
  sitegen/render.py    各页面的 HTML
  sitegen/md.py        Markdown → HTML（标题锚点、仓库内链接改写）
  sitegen/linkcheck.py 构建后的内链与锚点检查
  static/style.css     样式（明 / 暗主题，手机与桌面）
  static/app.js        主题切换与原理图查看器的嵌入逻辑
```

不引入前端构建工具；除了 `markdown-it-py`，只用 Python 标准库与 `adcflow` 已有依赖。页面不请求任何第三方资源
（字体用系统字体），只有原理图 iframe 会访问 RNL 查看器。

## 约束

* 不得把服务器名、服务器路径、PDK 路径或模型数据放进站点（`python -m adcflow check hygiene` 必须保持干净）。
  生成器只读已跟踪的设计、规格、结果与文档文件，不读 `site.local.yaml`。
* 站点是仓库的视图：内容以仓库为准，改文字请改 `specs/`、`docs/`，不要改生成出来的页面。
