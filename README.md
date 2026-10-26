# ADC-12b-100M

12-bit-class, 100 MS/s asynchronous SAR ADC in TSMC 28 nm HPC+ (0.9 V / 1.8 V), designed as
**Spectre netlists with RNL (Rich Netlist) schematics** — no schematic editor, only netlists,
Verilog-A behavioral models, Python tooling and Spectre.

| | |
|---|---|
| Architecture | bottom-plate sampling, split-capacitor redundant CDAC (13 weights), 14 async decisions |
| Resolution | 14 raw bits, 4540 levels (12.15 bit), weights `1960 1120 636 360 204 114 64 36 20 12 6 4 2 1` |
| Full scale | 0.993 V differential peak (VREF = 0.9 V; inputs 0..0.9 V single-ended, 50 Ω source) |
| Target | ENOB > 10.5 at ~50 MHz, −1 dBFS in all 45 corners; power as low as practical (no hard limit) |
| Output | parallel raw bits D13..D0 + RDY; reconstruction `code = Σ W·D` in software |

## Repository

| Path | Content |
|---|---|
| `docs/architecture.md` | architecture, budgets, timing, conventions |
| `docs/reference.md` | VREFP study: CDAC load, redundancy vs reference, on-chip follower, specs |
| `docs/specs.md` | block specifications and acceptance tests (generated from `specs/blocks/`) |
| `docs/verification.md`, `docs/workflow.md` | verification plan; environment and commands |
| `specs/` | single source of truth: `arch.yaml`, `corners.yaml`, `blocks/*.yaml`, `va_modules.yaml` |
| `design/rnl/` | RNL packages: project styles, PDK device rules, generated block / Verilog-A symbols |
| `design/behav/` | behavioral view of every block (Spectre + Verilog-A) |
| `design/xtor/<block>/` | transistor-level views (block owners) |
| `design/top/adc_top.scs` | structural top level (same file for any mix of views) |
| `tb/` | acceptance testbenches and their Verilog-A monitors |
| `site/` | static project website (`python site/build.py`), built by CI on every PR, deployed from `main` |
| `tools/adcflow/` | system model, generators, remote Spectre runner, measurements, CI checks |
| `results/` | recorded acceptance results (small JSON, hashed against the netlists) |

## Quick start

```bash
pip install -e ".[analysis,dev]"
cp site.example.yaml site.local.yaml      # fill in the simulation server and PDK paths (never committed)
python -m adcflow budget                  # architecture budget from the system model
python -m adcflow check all               # what CI checks
python -m adcflow sim tb_top_sine         # full behavioral ADC on the server
python -m adcflow report
```

See `CONTRIBUTING.md` for the branch / review / sign-off process.
