# WP6: Self-optimising-control screening and active constraints

**Status:** Executed synthetic steady-state study and exploratory dynamic/noisy-plant pilot. NOT physical validation.

## Two separate actuator models

The published WP2 reference has just one manipulated compressor command. At the qualifying economic optimum, minimum service is active, so the residual free steady-state economic DOF is **zero**. Its local process bypass is an *algebraic service valve*, not an HTHP optimiser DOF. This is a defensible negative SOC result for the original tested configuration.

The optional WP6 study explicitly introduces hot-loop circulation ratio `r` as a **second hypothetical actuator**, with an assumed pump electricity `P_pump(r)=2500 r^3 W`, a hot-side film-resistance share of 0.4, and a `r^0.8` hot-side heat-transfer correlation. These are research assumptions, NOT measured pump/HX curves. Process-side bypass remains local to service; the HTHP optimiser controls `r`, **not** the bypass fraction.

## Economic problem and active constraints

`min_{r,T_b,n} J=P_compressor(n,T_h,T_src)+P_pump(r)` subject to `Q_process>=Q_requested`, `T_proc,out>=T_required`, two steady thermal balances, hot-loop flow/temperature and compressor bounds. For a fixed feasible `r`, the tested synthetic objective rises with buffer-temperature backoff; hence `T_b=T_b,min,service(r,d)` and `n` is determined by energy balance, leaving **one** economic DOF `r` in interior regions. The reduction is tested against the 2D objective, not assumed globally.

Positive electricity price simply scales the steady objective. With no thermal storage scheduling or time coupling, the optimal steady `r` is unchanged by tariff level. This project does **not** claim demand-response savings from static SOC.

**Training grid:** 20 points. **Held-out grid:** 9 points. Synthetic settings fully declared in `SOCParameters` and JSON.

## Candidate controlled variables (CV)

1. `CV=r` fixed at a training-selected constant (no on-line reoptimisation).
2. Per-active-region empirical `CV=r+β_return ΔT_return+β_source ΔT_source` constant, with separate `r=r_max` constraint control; coefficients fitted to **training** offline optima.
3. Per-active-region *stationarity-derived* linear CV with `β_d=J_{rd}/J_{rr}` at an interior anchor and a separately selected pump-upper constraint. This follows the local first-order optimality condition; it is not an implementation or proof of the Manum–Skogestad nullspace result.

Candidates are held at constant CV setpoints within regions. Setpoint/active-region switching is explicit, with no hidden online RTO for policies under test. The offline optimum is recomputed for each held-out point only as a **counterfactual** to quantify loss.

### Held-out synthetic steady-state economic loss

| CV policy | Feasible / 9 | Mean loss (W) | Max loss (W) | Max relative loss (%) |
|---|---:|---:|---:|---:|
| global_constant_r | 9/9 | 61.281 | 140.012 | 0.1233607% |
| piecewise_empirical_CV | 9/9 | 0.025 | 0.101 | 0.0000852% |
| piecewise_stationarity_CV | 9/9 | 0.015 | 0.043 | 0.0000488% |

### Model-mismatch uncertainty (fixed policy; reoptimised oracle)

The nominal CVs are **not refitted** when pump power, hot-side film resistance, or the hot-flow UA exponent changes. Six synthetic equipment variants × nine held-out disturbances × three policies are evaluated. All missing feasibility is retained explicitly in the CSV.

| Policy | Maximum feasible loss across uncertainty variants (W) | Infeasible policy trials |
|---|---:|---:|
| global_constant_r | 397.481 | 0 / 54 |
| piecewise_empirical_CV | 108.153 | 0 / 54 |
| piecewise_stationarity_CV | 112.395 | 0 / 54 |

All electric powers are steady-state synthetic W. Loss is **J_policy − J_opt** at the **same process service**, and never assigned to infeasible points. Relative loss uses the positive total-electric-power objective, not a tariff-weighted saving estimate. The training/held-out split is artificial and not a probabilistic population sample.

### Active sets

Of 20 training operating points, 8 bind the upper hot-loop pump limit; the remaining 12 have an interior economic circulation optimum. All feasible steady economic optima bind the minimum service requirement. This is an explicit constraint-following region plus a separately evaluated free economic DOF, rather than relabelling a tariff schedule as SOC.

## Exploratory dynamic/noisy-plant pilot

The flow actuator has a first-order lag (`tau_r=75s`) and command-step limit, while compressor modulation and the two thermal states retain WP2 dynamics. A **single measured buffer temperature** controls the PI compressor loop; flow measurement, process return and source temperatures are assumed available. Noise and FIFO measurement delay are applied identically to compared policies. The `offline_rto` reference reoptimises using the **current** measured disturbance and does not know the future. Dynamic trials use a 2 K quality backoff not present in the ideal steady economic optimum.

| Disturbance schedule | Noise / measurement delay | Policy | Electric energy (kWh) | Spec-unserved heat (kWh) | Service-compliant fraction |
|---|---|---|---:|---:|---:|
| mild_steps | 0.0 K / 0.0 s | offline_rto | 540.235 | 0.000 | 1.000 |
| mild_steps | 0.0 K / 0.0 s | regime_soc | 540.222 | 0.000 | 1.000 |
| mild_steps | 0.0 K / 0.0 s | constant_soc | 539.925 | 0.000 | 1.000 |
| mild_steps | 0.2 K / 120.0 s | offline_rto | 540.547 | 0.000 | 1.000 |
| mild_steps | 0.2 K / 120.0 s | regime_soc | 540.536 | 0.000 | 1.000 |
| mild_steps | 0.2 K / 120.0 s | constant_soc | 540.211 | 0.000 | 1.000 |
| stress_return_jump | 0.0 K / 0.0 s | offline_rto | 529.496 | 0.000 | 1.000 |
| stress_return_jump | 0.0 K / 0.0 s | regime_soc | 529.500 | 0.000 | 1.000 |
| stress_return_jump | 0.0 K / 0.0 s | constant_soc | 530.141 | 0.000 | 1.000 |
| stress_return_jump | 0.2 K / 120.0 s | offline_rto | 529.151 | 0.000 | 1.000 |
| stress_return_jump | 0.2 K / 120.0 s | regime_soc | 529.155 | 0.000 | 1.000 |
| stress_return_jump | 0.2 K / 120.0 s | constant_soc | 529.867 | 60.556 | 0.950 |

A difference in electricity use under **unequal heat service** is not an economic saving. The ideal-steady offline-optimal result and the dynamic online-RTO comparator are separate reference quantities; signed dynamic electricity differences need not be nonnegative. The Hessian-based CV is only locally stationarity-preserving, and service quality under disturbances must be independently demonstrated.

## Reproducibility and limitations

- Run `python scripts/run_wp6.py` and `python -m unittest discover -s tests`. The WP6 script emits the complete WP6 tables, JSON, figures and report and never edits the earlier WP2–WP5 datasets.
- `results/wp6_offline_optima.csv`: full training and hold-out active-constraint ledger.
- `results/wp6_assumption_sensitivity.csv`: 162 fixed-policy out-of-envelope synthetic equipment checks.
- `results/wp6_heldout_losses.csv`: every policy/heldout pair including infeasible flags.
- `results/wp6_dynamic_scenarios.csv`: paired dynamic cases, quality compliance and energy balance.
- `results/wp6_summary.json`: parameter/provenance ledger, CVs, loss summary, excluded results.
- Quality-defined unserved heat treats a below-specification outlet as an unqualified process interval even when a small amount of physical heat is missing; these are deliberately separate metrics and must not be conflated.
- `results/wp6_active_set_map.png` and `results/wp6_heldout_loss.png` are descriptive figures generated by the same script.
- This is a synthetic model extension with no pump manufacturer curves, fluid screening, lab data or calibrated UA/pressure envelope; it does not establish real thermal performance or formal closed-loop robust stability.
- Skogestad (2000), DOI `10.1016/S0959-1524(00)00023-8` and Manum & Skogestad (2012), DOI `10.1016/j.jprocont.2012.02.015` establish classic steady-state SOC principles. The latter presents a **steady-state/quadratic** active-set formulation; the dynamic/noisy nonlinear case here is independent exploratory work, not validated by that citation.

