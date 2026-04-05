# Analysis

Run the analysis tool from the project root:

```bash
python3 Analysis/analyze.py
```

Run the layered V15 parameter sweep from the project root:

```bash
python3 Analysis/v15_parameter_sweep.py
```

Run the V17 microstructure sweep from the project root:

```bash
python3 Analysis/v17_micro_sweep.py
```

Run the wider-step V17 coarse sweep from the project root:

```bash
python3 Analysis/v17_coarse_sweep.py
```

Run the V18 regression-model sweep from the project root:

```bash
python3 Analysis/v18_regression_sweep.py
```

Run the V20 higher-risk TOMATOES carry sweep from the project root:

```bash
python3 Analysis/v20_risk_sweep.py
```

Run the V27 PDE-style control sweep from the project root:

```bash
python3 Analysis/v27_pde_sweep.py
```

Run the V27 alpha and dynamic holding-limit sweep from the project root:

```bash
python3 Analysis/v27_alpha_hold_sweep.py
```

Run the broader V27.1 continuation sweep from the project root:

```bash
python3 Analysis/v27_1_broad_sweep.py
```

Train the offline TOMATOES ML model from the project root:

```bash
python3 Analysis/train_tomatoes_offline_model.py
```

It writes human-readable reports to:

```bash
Analysis/output/
```

Main outputs:

- `README.txt`
- `emeralds_report.txt`
- `tomatoes_report.txt`
- `bot_comparison.txt`
- `matching_report.txt`
- `results_report.txt`
- `v15_sweep_report.txt`
- `v15_sweep_results.csv`
- `v17_sweep_report.txt`
- `v17_sweep_results.csv`
- `v17_coarse_report.txt`
- `v17_coarse_results.csv`
- `v18_sweep_report.txt`
- `v18_sweep_results.csv`
- `v20_sweep_report.txt`
- `v20_sweep_results.csv`
- `v27_pde_sweep_report.txt`
- `v27_pde_sweep_results.csv`
- `v27_alpha_hold_report.txt`
- `v27_alpha_hold_results.csv`
- `v27_1_broad_sweep_report.txt`
- `v27_1_broad_sweep_results.csv`
- `tomatoes_offline_model_report.txt`
- `tomatoes_offline_model_best_mse.json`
- `tomatoes_offline_model_best_proxy.json`
