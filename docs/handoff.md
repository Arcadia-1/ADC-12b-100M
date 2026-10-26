# 晶体管级设计分工包

架构 v0.2 与各模块规格已冻结（标签 `arch-v0.2`、`spec-v0.2`）。下列 6 个模块可以**并行**开展晶体管级设计，
彼此只通过规格中的端口和负载条件耦合。每个模块的完整规格在 [`docs/specs.md`](specs.md)，
流程见 [`CONTRIBUTING.md`](../CONTRIBUTING.md) 与 [`docs/workflow.md`](workflow.md)。

## 总览

| 模块 | 关键指标 | 主要风险 | 依赖 / 交互 | 建议人选侧重 |
|---|---|---|---|---|
| `adc_comp` | 噪声 ≤ 80 µV，1 mV 时延 ≤ 80 ps，τ ≤ 15 ps，回踢 ≤ 40 µV/周期 | 慢角延时、回踢电荷留在浮空上极板 | 负载与时钟来自 SAR 逻辑 | 动态比较器 / 噪声 |
| `adc_sarlogic` | 全角转换 ≤ 4.1 ns（70 ps 比较器），环路开销 ≤ 35/40 ps，两段 DAC 等待 | SS/0.81 V/−40 °C 慢 1.6× 以上 | 驱动 CDAC 控制（12 fF/线） | 异步数字 / 定制逻辑 |
| `adc_cdac` | C_S = 1.03 pF（权重 980 560 318 180 102 57 32 18 10 6 3 2 1），权重误差 ≤ 0.5 %，τ ≤ 15 ps，跟踪 SFDR ≥ 85 dB | 0.25 fF 半电容、驱动器 PMOS 在 0.81 V 关断不彻底、底板结电容非线性 | 栅压来自 bootstrap，控制来自 SAR 逻辑 | 电容阵列 / 开关 |
| `adc_bootstrap` | VG−VIN ≥ 0.72 V 且波动 ≤ 40 mV，关断 ≤ 60 ps，跟踪 SFDR ≥ 82 dB | 器件耐压（≤ 1.0 V）、负载为整个输入开关栅电容 | 负载 = CDAC 输入开关（规格给出参考负载） | 采样开关 |
| `adc_clkgen` | PHI_S→PHI_B 20–80 ps，先断后合，PHI_S 下降沿 ≤ 20 ps、抖动 ≤ 60 fs | 抖动、占空比 45/55 % | 驱动所有相位负载 | 时钟 |
| `adc_ref` | 电荷回放 ENOB 损失 ≤ 0.1 bit，判决 12~14 期间变化 ≤ 200 µV，噪声 ≤ 80 µV，直流 ±5 mV；不设功耗上限 | 全部片内（不用 nF 电容），小去耦下的恢复速度；只能用 1.8 V 供电得到 0.9 V | 负载 ≈ 1 pC/转换（与码基本无关） | 模拟 / 驱动 |

## 共同要求

* 新建 `design/xtor/<block>/<block>.scs`，子电路名与端口顺序与规格一致（`python -m adcflow check ports`）。
* 只用 PDK 器件（`nch_*_mac`、`pch_*_mac`、`cfmom_2t`、`*moscap*` 等，见 `design/rnl/adc28.rnl`）。
  理想元件只允许用于：去耦电容的寄生模型、尚无 PDK 等效的 CDAC 单位电容（需负责人同意并附寄生/失配模型）。
* 每个网表带**完整**的 RNL 原理图（精确的 PLACE / ORIENT / WIRE，`rnl check` 0 错误 0 警告 0 提示）
  和**高层语义**（`$DIFFERENTIAL_PAIR`、`$CURRENT_MIRROR`、`$MATCHED`、`$BRANCH`、`@GROUP` 等），方便评审。
* 验收：本模块全部用例 `--view <block>=xtor --corners all`，再做顶层混合仿真（其余模块行为级）。
* 不得修改其它模块、测试台或规格；需要改接口时先在 issue 中与负责人讨论。

## 各模块要点

### adc_comp
* 输入共模约 0.49 V（0.40–0.56 V），首次比较差分输入可达 0.75 V；NMOS 输入、ulvt。
* 建议双尾（double-tail）或带预放大的 StrongARM：预放大级隔离回踢；输出带反相器满足 RTZ。
* 噪声主要由输入对 gm 与积分电容决定；在 125 °C、ff/ss 角都要满足 80 µV。
* 失调不影响线性（冗余），但 σ ≤ 5 mV（蒙特卡洛 50 次）以免吃掉量程。

### adc_sarlogic
* 行为级模型 `design/behav/veriloga/adc_sarlogic_va.va` 是功能与时序的参考实现。
* 关键路径：比较器 VALID → 位锁存 → UP/DN → DAC 等待 → CLKC。前 6 步等待 40 ps，之后 75 ps（TT），
  等待延时应与 CDAC 驱动器同向随工艺变化（同类器件的延时链）。
* 超时（≈ 250 ps）强制判 1；CONV 下降时未完成也要装载输出寄存器并给出 RDY。
* D 输出驱动 50 fF；RDY 在 D 稳定后 ≥ 100 ps 上升，在下一个 CONV 上升时下降。

### adc_cdac
* 26 个半电容（`cu = 0.5 fF`，LSB 半电容 0.25 fF），j = 9（180）和 j = 6（32）不采样（满量程 > VREF 的关键）。
* 输入开关：栅极接 VG 的 NMOS，按电容大小缩放（时间常数相同），并联总电阻 ≤ 30 Ω。
* 驱动器：VREFP/VREFN 之间的反相器，CONV = 0 时采样半电容的驱动器三态；`DH` 拉低 H 半，`RL` 抬高 L 半。
  在 VDD = 0.81 V、VREFP = 0.9 V 时 PMOS 关断栅压只有 0.09 V，需用 svt/hvt 或从 VREFP 取预驱动电源。
* 上极板寄生 ≤ 10 % C_DAC（含比较器输入），上极板复位开关在 PHI_S 下降时断开（采样时刻）。

### adc_bootstrap
* 经典栅压自举（Abo/Gray 结构），升压电容在转换期间充电；负载为一侧全部输入开关的栅电容
  （测试台中用 48 µm/30 nm `nch_ulvt_mac` + 1.0285 pF 作为参考负载）。
* 所有薄栅器件端电压 ≤ 1.0 V（各工艺角）；PHI_B 下降后 VG 需在 60 ps 内降到 0.1 V 以下。

### adc_clkgen
* 输入为外部 CLK（高电平跟踪）。相位顺序：CLK↓ → PHI_S↓ → PHI_B↓（20–80 ps 后）→ CONV↑；
  CLK↑ → CONV↓ → PHI_B↑/PHI_S↑（先断后合）。
* PHI_S 下降沿决定采样时刻：边沿 ≤ 20 ps、抖动 ≤ 60 fs（瞬态噪声测量）。

### adc_ref
* VREF_IN（0.900 V，高阻）→ VREFP，必须由 AVDD18 供电（可用 1.8 V 厚栅器件）。**全部片内**：
  nF 级去耦只能放片外（键合线寄生），不采用；pF 级去耦可以串电阻。拓扑、电流、去耦由设计者决定，不设功耗上限。
* 规格只约束 VREFP 在比较器使用它的时刻：`tb_ref_replay` 把系统级模型一次近 Nyquist 转换序列的 CDAC 电荷
  （起始 0.46 pC + 13 次切换，含与信号相关的部分）灌入 VREFP，在每个判决时刻采样，再送回模型计算 ENOB 损失
  （REF-12 ≤ 0.1 bit）；判决 12~14 没有冗余，期间 VREFP 变化 ≤ 200 µV（REF-13）；无跨转换记忆（REF-14）；
  总噪声 ≤ 80 µV（REF-08）。
* 行为级起点：开环 NMOS follower（EKV 模型）2 mA、去耦 1.5 pF，回放损失 0.027 bit。系统级模型给出的方向：
  节点电容越小越好，恢复时间常数 C/g_s ≲ 60~80 ps；几十 pF 的去耦配 mA 级驱动是最坏区域。
  研究过程与被排除的方案见 [`docs/reference.md`](reference.md)。
* 需要在晶体管级确认：器件 g_s/I 与源极电容、慢角大信号恢复、栅极复制偏置的精度与噪声、AVDD18 耦合。
* VCM = 0.45 V ± 10 mV，只给上极板复位，负载很小。

## 建议顺序

1. 同时启动：`adc_comp`、`adc_sarlogic`（共同决定转换时间），`adc_cdac` + `adc_bootstrap`（共同决定线性度，
   两人需对齐输入开关的栅电容与导通电阻），`adc_ref`、`adc_clkgen`（相对独立）。
2. 每个模块通过自己的验收后，负责人逐个替换进顶层（`--view <block>=xtor`）跑 `tb_top_sine` quick 角。
3. 全部替换后跑 45 角顶层回归，签核。
