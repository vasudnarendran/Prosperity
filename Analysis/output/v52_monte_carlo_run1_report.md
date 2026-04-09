# Monte Carlo Robustness Report

- Output prefix: `v52_monte_carlo_run1`
- Bots: Traderv52.py, Traderv51.py

## Families

- `original_noise`: Original historical path with mild execution-noise perturbations.
- `bootstrap_path`: Block-bootstrap of the historical path with no fill perturbation.
- `bootstrap_balanced`: Block-bootstrap with moderate passive-fill degradation and mild aggressive slippage.
- `bootstrap_stress`: Block-bootstrap with stressed execution assumptions.

## Baseline Replay

### Traderv51

- Combined total PnL: `29488.5000`
- Day -1: `14868.0000`
- Day -2: `14620.5000`

### Traderv52

- Combined total PnL: `29884.0000`
- Day -1: `15081.0000`
- Day -2: `14803.0000`

## Monte Carlo Summary

### Traderv51

- Overall samples: `12` | mean `22925.9583` | p10 `14477.35` | cvar10 `13758.0` | std `5465.4519`
- `bootstrap_balanced`: count `3`, mean `21505.3333`, p10 `20760.7`, cvar10 `20536.5`
- `bootstrap_path`: count `3`, mean `28231.1667`, p10 `26370.2`, cvar10 `26266.0`
- `bootstrap_stress`: count `3`, mean `14976.8333`, p10 `13522.2`, cvar10 `13365.0`
- `original_noise`: count `3`, mean `26990.5`, p10 `26611.9`, cvar10 `26487.0`

### Traderv52

- Overall samples: `12` | mean `22757.4167` | p10 `14198.2` | cvar10 `13774.0` | std `5688.8054`
- `bootstrap_balanced`: count `3`, mean `21081.5`, p10 `19959.0`, cvar10 `19604.5`
- `bootstrap_path`: count `3`, mean `28315.5`, p10 `26701.7`, cvar10 `26580.5`
- `bootstrap_stress`: count `3`, mean `14456.0`, p10 `13627.6`, cvar10 `13530.0`
- `original_noise`: count `3`, mean `27176.6667`, p10 `26208.8`, cvar10 `25950.5`

## Comparison

- Primary: `Traderv52`
- Compare: `Traderv51`
- Shared samples: `12`
- Mean delta: `-168.5417`
- Median delta: `-1.25`
- P10 delta: `-943.7`
- Win rate: `0.5`

- `bootstrap_balanced`: mean delta `-423.8333`, p10 delta `-942.4`, win rate `0.3333`
- `bootstrap_path`: mean delta `84.3333`, p10 delta `-305.9`, win rate `0.6667`
- `bootstrap_stress`: mean delta `-520.8333`, p10 delta `-1302.2`, win rate `0.3333`
- `original_noise`: mean delta `186.1667`, p10 delta `-403.1`, win rate `0.6667`
