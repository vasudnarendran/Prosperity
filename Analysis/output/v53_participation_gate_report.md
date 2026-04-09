# Monte Carlo Robustness Report

- Output prefix: `v53_participation_gate`
- Bots: Traderv53.py, Traderv52.py

## Families

- `original_noise`: Original historical path with very mild execution-noise perturbations.
- `bootstrap_path`: Block-bootstrap of the historical path with no fill perturbation.
- `bootstrap_balanced`: Block-bootstrap with calibrated mild-to-moderate execution degradation.
- `bootstrap_stress`: Block-bootstrap with stressed execution assumptions.

## Baseline Replay

### Traderv52

- Combined total PnL: `29884.0000`
- Day -1: `15081.0000`
- Day -2: `14803.0000`

### Traderv53

- Combined total PnL: `29888.0000`
- Day -1: `14934.0000`
- Day -2: `14954.0000`

## Monte Carlo Summary

### Traderv52

- Overall samples: `12` | mean `24652.0417` | p10 `16947.7` | cvar10 `16784.0` | std `4716.17`
- Profile `all`: count `12`, mean `24652.0417`, p10 `16947.7`, cvar10 `16784.0`
- Profile `plausible`: count `9`, mean `27152.8333`, p10 `24722.0`, cvar10 `24064.0`
- Profile `stress`: count `3`, mean `17149.6667`, p10 `16748.0`, cvar10 `16724.0`
- `bootstrap_balanced`: count `3`, mean `24696.8333`, p10 `24228.5`, cvar10 `24064.0`
- `bootstrap_path`: count `3`, mean `28315.5`, p10 `26701.7`, cvar10 `26580.5`
- `bootstrap_stress`: count `3`, mean `17149.6667`, p10 `16748.0`, cvar10 `16724.0`
- `original_noise`: count `3`, mean `28446.1667`, p10 `27987.6`, cvar10 `27876.5`

### Traderv53

- Overall samples: `12` | mean `24722.5` | p10 `16737.7` | cvar10 `16558.0` | std `4756.6666`
- Profile `all`: count `12`, mean `24722.5`, p10 `16737.7`, cvar10 `16558.0`
- Profile `plausible`: count `9`, mean `27294.3333`, p10 `24850.6`, cvar10 `24661.0`
- Profile `stress`: count `3`, mean `17007.0`, p10 `16528.0`, cvar10 `16508.0`
- `bootstrap_balanced`: count `3`, mean `25201.0`, p10 `24708.4`, cvar10 `24661.0`
- `bootstrap_path`: count `3`, mean `28350.1667`, p10 `26793.8`, cvar10 `26641.0`
- `bootstrap_stress`: count `3`, mean `17007.0`, p10 `16528.0`, cvar10 `16508.0`
- `original_noise`: count `3`, mean `28331.8333`, p10 `28025.7`, cvar10 `28015.0`

## Comparison

- Primary: `Traderv53`
- Compare: `Traderv52`
- Shared samples: `12`
- Mean delta: `70.4583`
- Median delta: `-146.5`
- P10 delta: `-398.9`
- Win rate: `0.4167`

- `bootstrap_balanced`: mean delta `504.1667`, p10 delta `-13.6`, win rate `0.6667`
- `bootstrap_path`: mean delta `34.6667`, p10 delta `-471.4`, win rate `0.3333`
- `bootstrap_stress`: mean delta `-142.6667`, p10 delta `-232.0`, win rate `0.3333`
- `original_noise`: mean delta `-114.3333`, p10 delta `-357.2`, win rate `0.3333`

- Profile `all`: mean delta `70.4583`, p10 delta `-398.9`, win rate `0.4167`
- Profile `plausible`: mean delta `141.5`, p10 delta `-442.7`, win rate `0.4444`
- Profile `stress`: mean delta `-142.6667`, p10 delta `-232.0`, win rate `0.3333`
