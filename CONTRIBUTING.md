# 协作流程

本项目是多人协作的 ADC 设计：项目负责人维护架构、规格、行为级模型、顶层与验证流程；
各模块负责人在规格约束下完成晶体管级设计。所有设计数据都是 **Spectre 网表 + RNL**，
不使用 Virtuoso 等图形化 EDA 工具（仿真器除外）。

## 1. 分支与合并

| 分支 | 用途 | 合并方式 |
|---|---|---|
| `main` | 已评审、CI 通过的状态；每次架构/规格冻结打标签（`arch-v0.1`、`spec-v0.2` …） | 只通过 PR，`--no-ff` |
| `feat/<topic>` | 负责人的流程/模型/顶层工作 | PR 到 `main` |
| `block/<block>-<topic>` | 模块负责人的晶体管级设计，例如 `block/comp-strongarm` | PR 到 `main` |
| `fix/<topic>`、`docs/<topic>` | 小修正 | PR 到 `main` |

* 一个 PR 只做一件事；模块 PR 只改动 `design/xtor/<block>/`、该模块的 `results/` 和必要的文档。
* 修改 `specs/arch.yaml` 或 `specs/blocks/*.yaml` 的端口 / 指标属于**接口变更**，必须由负责人批准，
  PR 加 `spec` 标签，并在描述中说明对其它模块的影响。
* 禁止对 `main` 强推。共享分支上需要改写历史时，先通知所有基于它工作的人。

## 2. 提交信息

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <summary>

<body: why, what, evidence>
```

`type` ∈ `feat fix docs refactor test ci chore perf`；`scope` 为模块名（`comp`、`cdac` …）或
`arch`、`flow`、`behav`、`top`、`ci`。示例：`feat(comp): StrongARM with preamp, meets CMP-01..08 at TT`。

## 3. 绝对不能进入 git 的内容

* PDK 数据：器件模型文件、从模型中提取的参数表、模型卡片片段。
* 站点信息：服务器名、服务器路径、cshrc / 环境脚本路径、PDK 安装路径、许可证信息。
  这些只写在被忽略的 `site.local.yaml`（模板 `site.example.yaml`）中，**提交信息里也不能出现**。
* 原始仿真数据（PSF、波形、日志）。只提交 `results/` 下的小体积 JSON 结论。

`python -m adcflow check hygiene` 在本地和 CI 中检查上述内容。建议启用提交钩子：

```bash
git config core.hooksPath tools/hooks
```

## 4. 模块负责人的工作流程

1. 阅读 `docs/architecture.md`、`docs/verification.md` 和本模块的 `specs/blocks/<block>.yaml`。
2. 新建分支 `block/<block>-<topic>`，在 `design/xtor/<block>/<block>.scs` 中写晶体管级子电路：
   子电路名和端口顺序必须与规格完全一致（CI 检查），并带完整的 RNL 原理图（精确的
   PLACE / ORIENT / WIRE）以及 RNL 语义（差分对、电流镜、MATCHED、GROUP 等）。
3. 器件尺寸参数可用 `pdk-callback` 工具求解；只把实例参数写入网表，不写模型数据。
4. 逐个运行模块验收用例（`docs/workflow.md`），在 45 个工艺角下满足全部指标：
   `python -m adcflow sim <test> --view <block>=xtor --corners all`
5. 把规格中的 `status` 从 `behavioral` 改为 `xtor-wip` → `xtor-review`，提交 `results/` 与网表，发 PR。
6. 负责人评审并在顶层（其余模块行为级）跑 `tb_top_sine` 后，把状态改为 `signoff` 合并。
   CI 对 `signoff` 模块要求：每个指标在其工艺角集合上都有**未过期**且通过的结果。

## 5. 评审要点

* 端口、电源域、负载条件与规格一致；没有修改其它模块文件。
* `python -m adcflow check all`、`pytest` 通过。
* 结果 JSON 的 `meta.files` 哈希与提交的网表一致（否则 CI 报 stale）。
* 原理图可读：信号从左到右、电源在上地在下、对称结构对齐、关键尺寸有标注。
