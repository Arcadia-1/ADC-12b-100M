# 验证计划

各模块的端口、指标与用例清单见 [`docs/specs.md`](specs.md)（由规格生成）。本文说明验证的层次、
约定和行为级模型的现状。

## 1. 层次

| 层次 | 工具 | 作用 |
|---|---|---|
| 系统级模型 | `tools/adcflow/model.py` | 架构与预算；所有仿真结果的参照（`python -m adcflow budget`） |
| 行为级视图 | `design/behav/*.scs` + Verilog-A | 每个模块与晶体管级视图端口完全一致；验证测试台、度量与顶层时序 |
| 模块验收 | `tb/<block>/*.scs` + `measure/<block>.py` | 同一测试台测行为级或晶体管级；限值来自规格 |
| 顶层验收 | `tb/top/tb_top_sine.scs` | 任意视图组合，45 个工艺角回归 |
| CI | GitHub Actions | 端口契约、RNL、生成文件、结果判定、单元测试、站点信息检查 |

## 2. 约定

* **工艺角**：`<process>_<supply>_<temp>`，例如 `tt_nom_27`、`ss_low_m40`。集合 `typ`（TT）、
  `quick`（7 个极端角）、`all`（45 个）。电源 ±10 % 同时作用于 0.9 V 与 1.8 V；VREF_IN 恒为 0.900 V。
* **噪声**：`noise_en=1` 时行为级模型注入比较器噪声、采样 kT/C 与时钟抖动；有晶体管级视图时
  （`devnoise=1`）打开 Spectre 瞬态噪声（`noisefmax`）。
* **正弦测试频率**：`fin_target=49.9 MHz` 取不超过 Nyquist−3 个频点的最大相干奇数频点
  （1024 点：49.71 MHz；256 点：48.83 MHz），避免窗函数主瓣碰到 Nyquist 频点。
* **ENOB**：按 −1 dBFS 输入测得的 SNDR 计算（不归一化到满量程），即 `(SNDR − 1.76)/6.02`；
  同时报告标称权重与正弦前台校准权重两种结果，验收以标称权重为准。
* **结果过期**：结果 JSON 中的文件哈希与当前文件不一致即为过期，签核模块的过期结果 CI 报错。

## 3. 行为级基线（TT，`aps`，`results/*/behav/`）

行为级视图在 TT 下通过了全部已记录的指标（`python -m adcflow report`），证明测试台、度量与
限值彼此一致；晶体管级视图将用同一批测试台验收。

| 模块 | 关键结果 |
|---|---|
| 顶层 `tb_top_sine`（1024 点，49.71 MHz，−1 dBFS，噪声开） | ENOB 11.43，SFDR 83.9 dB，FS 0.999 V，t_conv 2.68 ns，0.84 mW，无丢失 RDY |
| 顶层低频 / 占空比 45 %、55 % | ENOB 11.49 / 11.43 / 11.29 |
| `adc_comp` | 噪声 75.9 µV，1 mV 时延 76 ps，τ 8 ps，回踢 0.3 µV，能耗 112 fJ |
| `adc_sarlogic` | 1000 次随机转换 0 错误，转换 2.53 ns（比较器 70 ps 时 2.88 ns），超时 285 ps，213 µW |
| `adc_cdac` | C_S 1.024 pF，FS 0.9987 V，权重误差 < 0.001 %，跟踪 SFDR 96.5 dB / SNDR 89.9 dB |
| `adc_bootstrap` | 跟踪 SFDR 97.0 dB / SNDR 89.5 dB（参考开关 + 50 Ω） |
| `adc_clkgen` | PHI_S 延时 46 ps，PHI_S→PHI_B 40 ps，抖动 46 fs，占空比 45/55 % 无错误 |
| `adc_ref` | VREFP 误差 −0.1 mV，判决时刻纹波 0.34 mV，码相关漂移 4.6 µV，噪声 2.9 µV |

* `tb_cdac_settle` 与 `tb_bootstrap_dc` 的行为级结果待补（服务器不可用时中断，属于取回链路问题，已修复）。
* 噪声关闭时顶层 ENOB 11.85（量化极限 12.0）；`ax` 模式下同一行为级 ADC 只有 10.63，因此验收一律用 `aps`。
* 行为级模型的功耗为预算值（固定电流 + 每次判决的电荷），不代表电路实际功耗。
