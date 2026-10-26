# 工作环境与常用命令

## 1. 本地环境（一次性）

```bash
pip install -e ".[analysis,dev]"          # adcflow 工具包 + adctoolbox 0.6.4 + pytest
git config core.hooksPath tools/hooks     # 提交前检查（hygiene / ports / 生成文件）
```

* **RNL 命令行**：安装与 CI 相同的版本 `core-v0.5.2`（见 rnl 项目的 Release 页，下载后核对 SHA256），
  放到 `PATH` 中，`rnl --version` 应显示 0.5.2。
* **站点配置**：复制 `site.example.yaml` 为 `site.local.yaml`（已被 git 忽略）或 `~/.adcflow/site.yaml`，
  填写仿真服务器的 ssh 别名、服务器本地盘上的临时目录、Spectre 环境脚本、PDK 模型目录与文件名。
  这些信息**绝不提交**。ssh 需要免密（`ssh -o BatchMode=yes <alias> true` 能通过）。
* MATLAB 版 ADCToolbox 可选，用于 `analysis/` 中的交互分析；CI 与验收只用 Python 版。

## 2. 生成文件

以下文件由 `python -m adcflow gen` 从 `specs/` 生成，不要手改（CI 会检查是否同步）：

| 文件 | 来源 |
|---|---|
| `design/rnl/adc28_blocks.rnl`、`design/rnl/adc28_va.rnl` | 模块端口、Verilog-A 模块端口 → DEVICE 与符号 |
| `design/behav/veriloga/adc_arch*.vams` | `specs/arch.yaml` 的权重、单位电容等常数 |
| `design/behav/adc_cdac.scs` | 行为级 CDAC（26 个半电容 + 开关矩阵，含原理图） |
| `design/top/adc_top.scs` | 顶层结构网表与原理图（`tools/adcflow/gen_top.py` 中的连接表） |
| `tb/**/*.scs` | 验收测试台（`tools/adcflow/gen_tb.py`） |
| `docs/specs.md` | 模块规格表 |

## 3. 运行验收用例

```bash
python -m adcflow sim <test> [--corners typ|quick|all|<name,...>] [--view <block>=xtor ...] \
       [--param name=value ...] [--mode aps] [--jobs 6] [--keep] [--no-record]
python -m adcflow report [--block adc_comp]     # 结果对照规格
python -m adcflow corners all                   # 45 个工艺角名称
python -m adcflow clean-remote --older-than-h 12   # 清理服务器上本项目的遗留目录
```

每次 `sim`：

1. 在 `build/runs/<run_id>/` 生成仿真 deck（全局参数、工艺角模型段、各模块视图、Verilog-A、测试台）；
2. 打包上传到服务器本地盘的 `<remote_root>/<run_id>/`，并行运行 Spectre（共享 Verilog-A 编译缓存）；
3. 只取回小文件（监视器输出、日志、需要的波形，单文件默认 ≤ 50 MB），**随后删除服务器目录**；
4. 调用度量函数，把指标与判定写入 `results/<block>/<test>/<view>/<corner>.json`，
   其中 `meta.files` 记录所用网表、Verilog-A、规格文件的哈希。

视图选择：默认全部行为级；`--view adc_comp=xtor` 使用 `design/xtor/adc_comp/adc_comp.scs`，
此时自动包含所选工艺角的 PDK 模型段并打开器件噪声（`devnoise=1`）。

仿真模式默认 `aps`。`ax` / `mx` 在本项目的 Verilog-A 行为级模型上精度不足
（行为级 ADC 的 ENOB 从 11.25 掉到 10.63），只能用于晶体管级的快速探索，验收必须用 `aps`。

## 4. 新增或修改测试台

* 测试台在 `tools/adcflow/gen_tb.py` 中描述（元件、网络、参数、分析），`gen` 生成网表和原理图。
* 第一行 `parameters` 中的参数可由规格 `params:` 或 `--param` 覆盖；`vdd vdd18 tempc noise_en devnoise
  beh_speed vref_in` 由 deck 提供，测试台中不要声明。
* 监视器写小文本文件（`tb/common/veriloga/`）；只在度量需要时保存波形（`save` 列出信号）。
* 度量函数放在 `tools/adcflow/measure/<block>.py`，签名 `fn(job_dir, ctx) -> dict`，键名即规格中的 `metric`。
* 规格中的 `prepare: module:fn` 在建 job 时改写参数（例如把 `fin_target` 换成相干频点）；返回的
  `_files: {文件名: 文本}` 会写进 job 目录，测试台用相对路径读取（`tb_ref_replay` 的 `iload.pwl` / `trig.pwl`）。

## 5. 晶体管级设计的签核

1. `design/xtor/<block>/<block>.scs`：子电路名、端口与规格一致，完整 RNL 原理图与语义。
2. 本模块全部用例：`--view <block>=xtor --corners all`（规格要求 `mc` 的用例另跑蒙特卡洛）。
3. 顶层混合仿真：`python -m adcflow sim tb_top_sine --view <block>=xtor --corners quick`。
4. 提交网表与 `results/`，规格状态改为 `xtor-review`，发 PR；负责人复核后改为 `signoff`。

## 6. 服务器使用规则

* 只在服务器本地盘的临时目录下仿真，不在 `/home` 下运行；
* 服务器上的数据随时可能被清除：有用的数据仿真结束就取回，大文件只取需要的部分；
* 每次运行结束自动删除服务器目录；异常退出后用 `clean-remote` 清理。
