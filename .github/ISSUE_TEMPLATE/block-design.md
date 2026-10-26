---
name: Block design task
about: Transistor-level design of one ADC block against its specification
title: "[block] adc_... transistor-level design"
labels: block
---

## Block

- Spec: `specs/blocks/adc_....yaml` (version: )
- Behavioral reference: `design/behav/adc_....scs`
- Transistor view to create: `design/xtor/adc_.../adc_....scs`
- Owner:
- Target date:

## Acceptance

All specs of the block pass at their corner sets with the transistor view:

```
python -m adcflow sim <test> --view adc_...=xtor --corners all
python -m adcflow report --block adc_...
```

Then the full ADC with this block in transistor level and the rest behavioral:

```
python -m adcflow sim tb_top_sine --view adc_...=xtor --corners quick
```

## Notes / open questions

<!-- Interface questions go to the project lead before changing ports or specs. -->
