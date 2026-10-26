## What

<!-- One paragraph: which block / tool / spec, what changed and why. -->

## Block status

- Block: `adc_...`   status before -> after: `behavioral` / `xtor-wip` / `xtor-review` / `signoff`
- Specs changed? <!-- yes: link the discussion; specs/blocks changes need the project lead -->

## Evidence

<!-- Paste the summary of `python -m adcflow report --block adc_...` and the
     commands you ran, e.g.
       python -m adcflow sim tb_comp_delay --view adc_comp=xtor --corners all
     Results are recorded under results/ and must be committed with the netlist
     they were simulated with (CI rejects stale results for signoff blocks). -->

## Checklist

- [ ] `python -m adcflow check all` passes locally (hygiene, ports, rnl, generated files, results)
- [ ] `python -m pytest -q -m "not slow"` passes
- [ ] Netlist has a complete RNL drawing and RNL semantics (structures / groups)
- [ ] No server names, server paths, shell-setup paths, PDK paths or model data anywhere (files and commit messages)
- [ ] Port list unchanged, or the spec change is approved
