# Monte Carlo Robustness Report

- Output prefix: `v53_monte_carlo_gate`
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

- Combined total PnL: `29884.0000`
- Day -1: `15081.0000`
- Day -2: `14803.0000`

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

- Overall samples: `12` | mean `24462.75` | p10 `16227.5` | cvar10 `16099.25` | std `5021.0519`
- Profile `all`: count `12`, mean `24462.75`, p10 `16227.5`, cvar10 `16099.25`
- Profile `plausible`: count `9`, mean `27172.8333`, p10 `24770.6`, cvar10 `24519.0`
- Profile `stress`: count `3`, mean `16332.5`, p10 `16060.4`, cvar10 `16034.5`
- `bootstrap_balanced`: count `3`, mean `24913.1667`, p10 `24581.9`, cvar10 `24519.0`
- `bootstrap_path`: count `3`, mean `28315.5`, p10 `26701.7`, cvar10 `26580.5`
- `bootstrap_stress`: count `3`, mean `16332.5`, p10 `16060.4`, cvar10 `16034.5`
- `original_noise`: count `3`, mean `28289.8333`, p10 `27609.7`, cvar10 `27527.0`

## Comparison

- Primary: `Traderv53`
- Compare: `Traderv52`
- Shared samples: `12`
- Mean delta: `-189.2917`
- Median delta: `0.0`
- P10 delta: `-883.45`
- Win rate: `0.3333`

- `bootstrap_balanced`: mean delta `216.3333`, p10 delta `7.0`, win rate `0.6667`
- `bootstrap_path`: mean delta `0.0`, p10 delta `0.0`, win rate `0.0`
- `bootstrap_stress`: mean delta `-817.1667`, p10 delta `-1003.5`, win rate `0.0`
- `original_noise`: mean delta `-156.3333`, p10 delta `-711.2`, win rate `0.6667`

- Profile `all`: mean delta `-189.2917`, p10 delta `-883.45`, win rate `0.3333`
- Profile `plausible`: mean delta `20.0`, p10 delta `-223.4`, win rate `0.4444`
- Profile `stress`: mean delta `-817.1667`, p10 delta `-1003.5`, win rate `0.0`
