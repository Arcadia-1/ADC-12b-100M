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
* **结果过期**：结果 JSON 中的文件哈希与当前文件不一致即为过期，签核模块的过期结果 CI 报错。证据图（§4）不单独计哈希：
  图与 JSON 来自同一次仿真，JSON 过期则其图一并过期。

## 3. 行为级基线（架构 v0.2，TT，`aps`，`results/*/behav/`）

行为级视图在 TT 下通过了全部已记录的指标（`python -m adcflow report`，`check results --strict` 无错误无警告），
证明测试台、度量与限值彼此一致；晶体管级视图将用同一批测试台验收。

| 模块 | 关键结果 |
|---|---|
| 顶层 `tb_top_sine`（1024 点，49.71 MHz，−1 dBFS，噪声开） | ENOB 11.39（校准后 11.43），SFDR 84.0 dB，FS 0.993 V，t_conv 2.69 ns，无丢失 RDY，4.17 mW（AVDD18 3.76 mW） |
| 顶层低频 / 占空比 45 %、55 % | ENOB 11.34 / 11.31 / 11.25 |
| `adc_comp` | 噪声 75.9 µV，1 mV 时延 76 ps，τ 8 ps，回踢 3×10⁻⁷ µV（行为级比较器无回踢），能耗 112 fJ |
| `adc_sarlogic` | 1000 次随机转换 0 错误，转换 2.55 ns（比较器 70 ps 时 2.90 ns），超时 285 ps，213 µW |
| `adc_cdac` | C_S 1.029 pF，FS 0.993 V，权重误差 < 0.001 %；RL12 建立 12.4 ps，τ 1.3 ps，起始建立 11.6 ps；跟踪 SFDR 96.5 dB / SNDR 89.9 dB |
| `adc_bootstrap` | VG−VIN 0.855 V，关断 16 ps，开启 63 ps；跟踪 SFDR 97.2 dB / SNDR 89.6 dB |
| `adc_clkgen` | PHI_S 延时 46 ps，PHI_S→PHI_B 40 ps，抖动 46 fs，占空比 45/55 % 无错误 |
| `adc_ref`（follower 2 mA + 1.5 pF） | 回放 ENOB 损失 0.027 bit，判决 12~14 变化 41 µV，记忆 ≈ 0，最大跌落 9.0 mV；噪声 61.5 µV；直流 −2.0 mV（100 µA 负载） |

* 加入证据图后（§4）重跑了全部 21 个结果：每个指标、规格值、参数与上一版基线逐项相同（行为级仿真是确定性的）。
* 噪声关闭时顶层 ENOB 约 11.85（量化极限 12.0；v0.1 测得，v0.2 未重测）；`ax` 模式下行为级 ADC 精度不足，因此验收一律用 `aps`。
* 行为级参考的 AVDD18 电流即 follower 偏置（2 mA）加 CDAC 平均电流；其余模块的功耗为预算值
  （固定电流 + 每次判决的电荷），不代表电路实际功耗。
* 参考电压的规格只约束判决时刻的行为（`tb_ref_replay`），回放方法见 `docs/reference.md` §6。

## 4. 证据图

每个结果 JSON 都带可读的证据图：度量函数用已读入的数据画图，写在结果旁，
`results/<block>/<test>/<view>/<stem>.<tag>.png`（`<stem>` 是 JSON 文件名去掉扩展名，例如
`tt_nom_27.spectrum.png`、`tt_nom_27__duty0.45.codes.png`），JSON 里的

```json
"figures": [{"file": "tt_nom_27.spectrum.png", "caption": "一句话说明这张图。"}]
```

列出文件与说明。约定：matplotlib（Agg）、固定样式与字体、图中文字一律英文；坐标轴带单位；
有规格的地方画出规格线（限值取自 `specs/blocks/*.yaml`，由 `figures.limits` 读取）；
每张图顶部一行 `测试 | 视图 | 工艺角`；每个 PNG ≤ 200 KB（超出时自动降低分辨率）；输出不含时间戳，同一数据画出的图逐字节相同。
重跑一个结果会先删掉它旧的图，再写新图。

| 测试 | 图（`<tag>`） | 内容 |
|---|---|---|
| `tb_comp_delay` | `delay` | 延时随输入差的变化（含 ln 拟合与限值）、±1 mV 判决瞬态并标出延时、复位到 10 % VDD |
| `tb_comp_noise` | `noise` | 判决概率与高斯 CDF 拟合（及限值处的曲线）、拟合残差与二项分布误差带 |
| `tb_comp_kickback` | `kickback` | 每个周期后的差分输入、每周期变化量对限值、Cin |
| `tb_cdac_weights` | `weights` | 各位权重与标称、各位权重误差对 0.5 % 限值、上升/下降步长不对称 |
| `tb_cdac_settle` | `settle` | 整个序列的顶板波形；起始与 RL12 / RL5 / RL0 之后的误差（对数坐标），标出容差线、建立时间与限值；规格表 |
| `tb_cdac_track` | `spectrum` | 顶板采样谱，SFDR / SNDR 对限值 |
| `tb_bootstrap_dc` | `switch` | VG−VIN 随输入、最坏关断 / 开启边沿（时延与限值）、栅压应力对 1.0 V SOA 限值、规格表 |
| `tb_bootstrap_track` | `spectrum` | 经自举开关采样的频谱，SFDR / SNDR 对限值 |
| `tb_clkgen_timing` | `timing` | CLK 下降 / 上升沿处 PHI_S、PHI_B、CONV 时序、PHI_S 下降沿（80 %→20 %）、占空比 50 / 45 / 55 % 各周期的延时与间隔对限值、规格表 |
| `tb_clkgen_jitter` | `jitter` | 采样相位沿的直方图与高斯、各沿残差、限值处曲线 |
| `tb_sarlogic_func` | `decisions`、`conversion`、`timing` | 输出码对输入、各判决位置的错码数、转换时间直方图；一次异步转换的波形（14 个比较器时钟、DAC 控制沿、RDY）；各环路时间逐事件对限值 |
| `tb_sarlogic_rand`、`_func_slow` | `decisions` | 同上（无波形） |
| `tb_sarlogic_timeout` | `decisions`、`timeout` | 同上；比较器不应答时 CLKC 被超时拉低的波形与每次超时时间对窗口 |
| `tb_ref_dc` | `dc` | VREFP 随负载、随 AVDD18、VCM 随负载（含窗口与斜率限值）、规格表 |
| `tb_ref_noise` | `psd` | VREFP / VCM 噪声谱密度与 10 kHz 积分起点、积分噪声对 120 µV 限值 |
| `tb_ref_replay` | `replay` | 各判决时刻 VREFP 偏差对冗余容差包络与 12~14 判决限值、转换前 VREFP 的记忆、转换内跌落、ENOB 代价 |
| `tb_top_sine`、`_sine_lf`、`_duty` | `spectrum`、`codes` | 输出谱（标称与校准权重）标注 ENOB / SNDR / SFDR 与限值；码对正弦相位折叠及拟合、拟合误差、转换时间直方图 |

`python -m adcflow check results --strict` 检查：`figures` 中列出的文件必须存在、命名为 `<stem>.<tag>.png`
并 ≤ 200 KB；`--strict` 下每个有结果的 JSON 必须有图（失败的结果除外）；结果旁未列入清单的 PNG 报警告。
新增测试的度量函数从 `ctx["figs"]` 取得接收器并至少画一张图，见 `docs/workflow.md` §4。
