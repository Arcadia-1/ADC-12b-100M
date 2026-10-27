# Contributing / 协作指南

**English summary.** This repository is a 12-bit-class, 100 MS/s asynchronous SAR ADC in 28 nm HPC+,
described entirely as plain Spectre netlists plus RNL schematic records (no schematic editor). The
architecture, block specifications, behavioral models, testbenches and the `adcflow` tool are done and pass
at the typical corner; the transistor-level design of the blocks is open to contributors. You (or your AI
agent) take **one block**, claim it with a pull request, design it at transistor level against its spec and
deliver it through pull requests that the project lead (GitHub `many-question`) reviews. Everything below is
written in Chinese; this file is meant to be read by an AI agent that has been pointed at its raw URL, and by
people. Process details and PDK access are not in this repository: contact `many-question` (see section 11).

---

## 1. 项目是什么，去哪里看

12 bit 级、100 MS/s 异步 SAR ADC（28 nm HPC+，0.9 V / 1.8 V）。所有设计数据都是 **Spectre 网表 + RNL 原理图记录**，
不使用 Virtuoso 等图形化原理图工具。架构、规格、行为级模型、测试台和 `adcflow` 流程都已完成，行为级验证在 TT 角全部通过；
项目在晶体管级设计之前停下，把各模块交给不同的人并行完成。

仓库：<https://github.com/many-question/ADC-12b-100M>（本文件原始地址：
<https://raw.githubusercontent.com/many-question/ADC-12b-100M/main/CONTRIBUTING.md>）。
项目网站（进度、验证结果、各模块原理图）：<https://many-question.github.io/ADC-12b-100M/>。

| 想看什么 | 文件 |
|---|---|
| 架构、指标分配、误差预算 | [docs/architecture.md](https://github.com/many-question/ADC-12b-100M/blob/main/docs/architecture.md) |
| 各模块规格（端口、指标、用例、工艺角集合） | [docs/specs.md](https://github.com/many-question/ADC-12b-100M/blob/main/docs/specs.md)；机器可读版 `specs/blocks/<block>.yaml` |
| 模块交接包（要点、风险、建议顺序） | [docs/handoff.md](https://github.com/many-question/ADC-12b-100M/blob/main/docs/handoff.md) |
| 工具与流程（环境、`adcflow sim`、签核步骤） | [docs/workflow.md](https://github.com/many-question/ADC-12b-100M/blob/main/docs/workflow.md) |
| 验证策略与用例 | [docs/verification.md](https://github.com/many-question/ADC-12b-100M/blob/main/docs/verification.md) |
| 设计推导与被排除的方案 | [docs/reference.md](https://github.com/many-question/ADC-12b-100M/blob/main/docs/reference.md) |

## 2. 两种角色

* **项目负责人**：`many-question`。维护架构、规格、接口、测试台、顶层与流程；评审并合并所有 PR；决定签核。
* **模块负责人**（模块 owner）：认领了某个模块、且认领 PR 已被项目负责人合并的 GitHub 用户。
  记录在 `specs/blocks/<block>.yaml` 的 `owner:` 字段（值是 GitHub 登录名，`TBD` 表示未认领），
  项目网站上该模块显示的负责人就是它。

## 3. 选一个模块

模块有 6 个可认领：`adc_comp`（比较器）、`adc_sarlogic`（异步 SAR 逻辑）、`adc_cdac`（电容阵列与驱动）、
`adc_bootstrap`（栅压自举采样开关）、`adc_clkgen`（时钟相位）、`adc_ref`（参考驱动）。`adc_top` 由项目负责人维护。

1. 打开 `specs/blocks/*.yaml`（或项目网站的模块页），找到 `owner: TBD` 的模块；已有登录名的模块已被认领，不要重复认领。
2. 读 `docs/handoff.md` 里该模块的要点，再读 `specs/blocks/<block>.yaml`（端口、指标、用例）。
3. 同时被几个人认领时，先合并的认领 PR 生效。想了解模块之间的依赖（例如 `adc_cdac` 与 `adc_bootstrap`），
   见 `docs/handoff.md`。

## 4. 认领（claim）

1. Fork 本仓库，从最新 `main` 建分支（例如 `block/<block>-claim`）。
2. **只**把 `specs/blocks/<block>.yaml` 中的 `owner: TBD` 改为 `owner: <你的 GitHub 登录名>`，不要改别的。
3. 向本仓库的 `main` 发 PR，**标题必须是 `[<block>] claim`**，例如 `[adc_comp] claim`。描述里写一个简短计划：
   拓扑思路、预计关键风险、预计时间、你的仿真环境是否具备（见第 8 节）。
4. 项目负责人合并后，你在网站上显示为该模块的负责人。认领 CI 检查：PR 只能把 `owner` 从 `TBD` 改成**PR 作者自己的**登录名，
   或把自己的认领改回 `TBD`（放弃认领）；其它任何 `owner` 变更只能由项目负责人做。
5. 所有与该模块有关的 PR 标题都以 `[<block>]` 开头（`[adc_comp] first netlist`、`[adc_comp] results at all corners`），
   网站据此把 PR 链接到模块页。

## 5. 你可以改什么，什么要先开 issue

| 可以直接在 PR 中改（模块负责人） | 先开 issue，由项目负责人决定 |
|---|---|
| `design/xtor/<block>/<block>.scs`：你的模块的晶体管级网表和它的 RNL 原理图 | 端口、端口顺序、电源域、负载条件 |
| `results/<block>/` 下由 `adcflow sim` 生成的结果 | `specs/` 里的任何指标、`specs/arch.yaml` |
| 规格里本模块的 `status`（`behavioral → xtor-wip → xtor-review`；`signoff` 由项目负责人改） | 测试台 `tb/`、度量函数 `tools/adcflow/measure/`、`tools/`、CI |
| 你模块说明里的文字更正 | 其它模块、顶层 `design/top/`、行为级模型 `design/behav/` |

* 开 issue 用仓库的 issue 模板，说明哪个模块、要改什么、为什么、对其它模块的影响；得到项目负责人同意后再发对应 PR。
* 一个 PR 只做一件事；不要在模块 PR 里夹带其它模块或工具改动。
* `docs/specs.md`、`design/rnl/adc28_blocks.rnl`、`tb/**` 等是生成文件，由 `python -m adcflow gen` 生成，不要手改。

## 6. 设计规则

* **只用网表 + RNL**：晶体管级设计写成 `design/xtor/<block>/<block>.scs`（Spectre 语法），带**完整**的 RNL 原理图
  （精确的 PLACE / ORIENT / WIRE）和高层语义（差分对、电流镜、`MATCHED`、`GROUP` 等）。不要提交 Virtuoso 原理图、
  版图或其它图形化工具的文件。RNL 语法与画法可参考仓库里已有的网表，以及 [RNL 项目](https://github.com/rich-netlist/rnl)。
* **子电路名和端口顺序与规格完全一致**（`python -m adcflow check ports` 检查）；不得修改端口。
* **只用 PDK 器件**（`design/rnl/adc28.rnl` 里列出的 MOS、`cfmom_2t`、MOS 电容等）。理想元件只在 `docs/handoff.md`
  允许的情形使用，并需事先在 issue 中得到同意。
* **PDK 数据与模型绝不进入 git**：不提交模型文件、从模型中提取的参数表、模型卡片片段。网表里只写实例参数。
* **不要写工艺厂商名**：全仓库只称 “28 nm HPC+”，也不要写 PDK 产品代号。
* **不要写任何机器、服务器、主机名、目录路径、环境脚本路径、许可证信息**，文件里和提交信息里都不行。
  这些只放在被 git 忽略的 `site.local.yaml`。`python -m adcflow check hygiene` 在本地和 CI 中检查。
* 不要提交原始仿真数据（PSF、波形、日志），只提交 `results/` 下的小体积 JSON 结论和图。

## 7. 开始之前：本地环境

```bash
git clone https://github.com/<你的账号>/ADC-12b-100M && cd ADC-12b-100M
pip install -e ".[analysis,dev]"          # adcflow 工具包 + pytest
git config core.hooksPath tools/hooks     # 提交前检查（hygiene / ports / 生成文件）
```

* 安装与 CI 相同版本的 RNL 命令行（`core-v0.5.2`，核对 SHA256），见 `docs/workflow.md`。
* 复制 `site.example.yaml` 为 `site.local.yaml`（已被 git 忽略，**绝不提交**），按注释填写**你自己的**仿真环境。
* 提交信息用 [Conventional Commits](https://www.conventionalcommits.org/)：`feat(comp): StrongARM with preamp`，
  `type` ∈ `feat fix docs refactor test ci chore perf`，`scope` 为模块名。禁止对 `main` 强推。

## 8. 你自己的仿真环境与 PDK

仿真需要 Cadence Spectre 和 28 nm HPC+ 的 PDK 模型，二者都**不在仓库中，也不由本项目提供**：

* 你需要自己的 Spectre 许可和 PDK 访问权限（通常来自你所在的公司、学校或项目的授权）。
* 工具通过 `site.local.yaml` 找到你的环境（说明见 `site.example.yaml` 与 `docs/workflow.md`）；这个文件只在你自己的机器上。
* 没有 PDK 访问，或不确定该用哪个工艺角库、哪些器件时：联系 `many-question`（第 11 节），不要猜测，也不要把任何 PDK 内容贴进 issue 或 PR。

## 9. 验收与提交结果

1. 逐个运行本模块的验收用例（用例名与工艺角集合见 `specs/blocks/<block>.yaml`）：

   ```bash
   python -m adcflow sim <test> --view <block>=xtor --corners all     # 例如 tb_comp_delay
   python -m adcflow report --block <block>                           # 结果对照规格
   ```

   规格要求蒙特卡洛的用例另行运行；验收用 `--mode aps`（默认）。
2. 全部指标在其工艺角集合上通过后，再做顶层混合仿真（其余模块行为级）：
   `python -m adcflow sim tb_top_sine --view <block>=xtor --corners quick`。
3. 把 `results/<block>/` 的结果 JSON（`adcflow sim` 自动写入，meta 里记录了所用网表的哈希）连同网表一起提交；
   结果必须对应提交的那一版网表，否则 CI 判定过期。结果还会带图（`results/` 下的指标图，由工具生成），一并提交即可。
4. 提交前本地运行 CI 的检查，必须全部通过：

   ```bash
   python -m adcflow check all
   python -m pytest -q -m "not slow"
   ```

CI 会检查：hygiene（无站点信息、模型卡片、工艺厂商名、大文件）、端口契约、RNL（0 错误 0 警告，网表必须画完整）、
生成文件同步、`owner` 变更规则、`results/` 与当前规格一致且未过期、单元测试。

## 10. PR 流程与评审

1. 从最新 `main` 分支（例如 `block/<block>-<topic>`）工作，增量提交；可以先发草稿 PR 让项目负责人早期看到方向。
2. 向 `main` 发 PR，标题 `[<block>] <summary>`，按 PR 模板填写：做了什么、模块状态变化、证据（`report` 摘要与运行的命令）、检查清单。
3. CI 全绿后，项目负责人评审：端口与规格一致；没有改动其它模块、测试台或规格；结果未过期且在全部工艺角通过；
   原理图可读（信号从左到右、电源在上地在下、对称结构对齐、关键尺寸有标注）。意见在 PR 里讨论并修改。
4. 状态流转：`behavioral`（未开始）→ `xtor-wip` → `xtor-review`（交付评审）→ `signoff`。项目负责人在顶层混合仿真和
   全角回归通过后把状态改为 `signoff` 并合并；`signoff` 的模块要求每个指标在其工艺角集合上都有未过期且通过的结果。
5. 合并后网站自动更新进度、结果和原理图。

## 11. 联系项目负责人

工艺细节、PDK 访问、规格疑问、不确定该不该改某个文件，或任何其它你需要的信息：联系 `many-question`。

* GitHub：[@many-question](https://github.com/many-question)（在 issue 或 PR 里 @ 即可）
* 邮件：jielu1995@outlook.com

## 12. 给 AI agent 的清单

1. 读第 1~6 节，选一个 `owner: TBD` 的模块，向用户确认。
2. fork → 分支 → 只改 `owner` → 发 `[<block>] claim` PR，等待合并。
3. 合并后读 `specs/blocks/<block>.yaml` 与 `docs/handoff.md`，在 `design/xtor/<block>/` 里写网表和 RNL；
   端口、规格、测试台、其它模块的改动一律先开 issue。
4. 用户提供的仿真环境只写进被忽略的 `site.local.yaml`；在任何文件、提交信息、PR 和 issue 里都不要出现工艺厂商名、
   PDK 内容、机器、服务器或路径信息。
5. `adcflow check all` 与 `pytest` 通过、结果已提交，再发 `[<block>] …` PR，等待项目负责人评审。
