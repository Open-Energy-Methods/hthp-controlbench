# WP5 — Comparative assessment: PI versus constrained MPC

**Scope:** synthetic, uncalibrated HTHP-shaped thermal plant; versioned WP4 scenario matrix. No industrial validation, real-fluid-cycle calibration or formal stability certificate.

## Protocol and scope of the comparison

- **Input:** exactly 20 declared WP3/WP4 scenarios × 5 fixed controllers, with a common nonlinear truth plant, one noisy/delayed buffer-temperature observation, 60-s sensing and 120-s command interval. MPC uses a nominal-model predictor for unmeasured states; PI does not need this additional model.
- **Future information:** this primary 100-run dataset uses disturbance persistence for MPC, not perfect future disturbance forecasts. Perfect-forecast sensitivity belongs in a separate analysis.
- **Tuning:** the four PI gains and MPC weights are carried over from WP3/WP4. They are *not* retuned or re-optimised using the cases here.
- **Primary outcome:** IAE in K·s; secondary outcomes are electrical energy (kWh), total command variation, specification-qualified service, physical thermal shortfall, actual MPC fallback events and solver acceptance.
- **Predeclared service gate for conditional electricity comparison:** quality fraction ≥ 1−10⁻⁹, unserved specification energy ≤10⁻⁶ kWh and physical heat shortfall ≤10⁻⁶ kWh for **both** controllers. These are analytical bookkeeping tolerances, not industrial process or safety acceptance limits.
- **Missing/failing runs:** failures are preserved and explicitly reported. No finite-error comparison is imputed for an incomplete case. There are no such failures in this saved matrix.
- **Statistical status:** this is a deliberately selected, correlated set of deterministic scenarios and three noise seeds per noise level. Case counts and group medians are descriptive, **not** empirical probabilities, confidence intervals or significance tests.
- **Energy is not cost:** no measured tariffs, emission factors, or equivalent service-value accounting exist in the matrix. No economic ranking is claimed.

## Headline results

- **Complete runs:** 100/100 (0 failed).
- **Raw lowest IAE:** MPC 14/20, relay PI 6/20. These raw counts include scenarios where *nobody* met service.
- **Service-qualified lowest IAE:** MPC 13, relay PI 5 across 18 cases with at least one qualified method.
- **MPC versus relay PI, both meeting service gate:** 18/20 cases.
- **All five controllers meet service gate:** 16/20 cases.
- **MPC accepted/fallback decisions:** 2352/2400 accepted updates, 48 PI fallback events, all in severe_actuator_capacity_minus40pct.

### Controller summary (case-wise descriptive medians)

| Controller | Qualified cases | Median IAE (K·s) | Median electricity (kWh) | Median command TV | Raw IAE wins | Service-qualified Pareto appearances |
|---|---:|---:|---:|---:|---:|---:|
| `IMC_lambda_0p5tau` | 16/20 | 2,852.94 | 584.48 | 0.209 | 0 | 16 |
| `IMC_lambda_1tau` | 16/20 | 4,342.91 | 586.33 | 0.194 | 0 | 16 |
| `IMC_lambda_2tau` | 16/20 | 6,073.51 | 589.09 | 0.135 | 0 | 16 |
| `relay_PI` | 18/20 | 1,221.57 | 583.53 | 0.275 | 6 | 18 |
| `MPC_persistence_120s` | 18/20 | 2,078.17 | 584.20 | 0.449 | 14 | 16 |

### Selected paired cases: MPC minus relay-derived PI

Negative ΔIAE means less tracking error for MPC; positive Δelectricity means higher electrical use. Electrical deltas are **not** efficiency claims when service is not equivalent.

| Case | ΔIAE (%) | Δelectricity (kWh) | Δcommand TV | Service compliant for both? | MPC fallback count |
|---|---:|---:|---:|---|---:|
| `nominal` | -84.3 | 0.58 | 0.18 | yes | 0 |
| `measurement_delay_180s` | -58.8 | 0.57 | 0.25 | yes | 0 |
| `noise_0.30K_seed_23` | -31.5 | 0.37 | 0.31 | yes | 0 |
| `heatpump_capacity_minus20pct` | 435.6 | -20.74 | -0.10 | yes | 0 |
| `process_UA_minus20pct` | 937.9 | 6.51 | 0.22 | NO — noncompliant | 0 |
| `severe_actuator_capacity_minus40pct` | -0.8 | 1.00 | -0.05 | NO — noncompliant | 48 |
| `combined_noise_0.3K_delay_180s_capacity_minus20pct` | 143.1 | -16.43 | 0.16 | yes | 0 |
| `combined_noise_0.3K_delay_180s_bypass` | 61.9 | 2.48 | -0.08 | yes | 0 |
| `bypass_UA_flow_exponent_0.8` | 289.7 | 1.89 | 0.21 | yes | 0 |

### Failure modes and conditional interpretation

1. **Loss of process heat-transfer UA (`process_UA_minus20pct`):** despite successful numerical completion, process service fails across the controller set. Lower electricity would be uninterpretable as an efficiency improvement. Temperature tracking (buffer setpoint IAE) and process service are different objectives; a controller may achieve one without the other.
2. **Severe compressor derating (`severe_actuator_capacity_minus40pct`):** physical supply is insufficient. The MPC reports 48 PI fallback events out of 120 decisions; other methods also fail required service. This is an equipment-feasibility limit, not controller success.
3. **Moderate capacity model mismatch:** relay PI outperforms MPC in IAE for ±20% compressor-capacity cases. No claim of globally superior predictive control is supported.
4. **Measurement delay/noise:** MPC performs better on IAE in the isolated delay and seeded noise cases, but it is not universally superior under combined noise, delay and capacity mismatch.
5. **Actuator effort and electrical energy:** nominal MPC consumes approximately 0.67 kWh more than relay PI over the simulated four-hour horizon. Lower IAE does not establish electricity savings. The actuator TV proxy is not a calibrated wear metric.
6. **Prediction/observer limits:** model-state reconstruction is open-loop nominal propagation with sampled buffer-temperature correction, not a statistically consistent estimator or proof of detection of bias, outage or drifting noise.

### Scenario categories (unweighted, descriptive only)

| Category | Cases | Paired qualified MPC vs relay | MPC lower IAE (raw) | Median paired ΔIAE (%) |
|---|---:|---:|---:|---:|
| bypass and UA | 1 | 1 | 0 | 289.7 |
| capacity change | 3 | 2 | 1 | 435.6 |
| combined disturbance | 2 | 2 | 0 | 102.5 |
| nominal | 1 | 1 | 1 | -84.3 |
| seeded sensor noise | 6 | 6 | 6 | -38.9 |
| sensor delay | 2 | 2 | 2 | -69.9 |
| setpoint excursion | 1 | 1 | 1 | -9.9 |
| thermal parameter change | 4 | 3 | 3 | -77.8 |

## Disturbance-forecast information sensitivity (separate from equal-information rankings)

| Case | Persistence IAE (K·s) | Perfect-future IAE (K·s) | Perfect-future minus persistence (K·s) |
|---|---:|---:|---:|
| `nominal` | 153.19 | 140.47 | -12.72 |
| `heatpump_capacity_minus20pct` | 14,743.94 | 14,794.63 | 50.69 |

This is a **two-case information sensitivity**, not a different entry in the equal-information 100-run benchmark. Perfect future disturbances are extra information unavailable to the PI baselines. Better forecasts do not guarantee better tracking when the internal plant model is inaccurate.


## Complexity and reproducibility

- The simulated plant has **3 physical states** (`T_h`, `T_b`, `n`) and one commanded input `u`; nominal MPC uses a six-step prediction horizon, **6 command variables + 6 service-slack variables = 12 QP variables** per update. The PI baseline uses proportional/integral feedback with documented gains and anti-windup.
- The 100-run matrix contains **2,400 MPC update decisions** in total, with 48 actual fallbacks. Controller solve times are **not** contained in the saved robustness CSV; the optional `scripts/benchmark_wp5_runtime.py` measures wall-clock *end-to-end simulation runtime* on an explicitly identified machine, not QP solve latency.
- OSQP/SLSQP agreement at three predeclared QP operating points is verified in `scripts/run_wp4_solver_audit.py`. That check is not a general execution-time, optimality or industrial real-time proof.
- The Pareto set is computed only among service-eligible methods using (IAE, electricity, command TV) in each case. A controller is Pareto-undominated if no eligible controller is at least as good in all three and strictly better in one. This is **not** an economic optimum.
- Run `python scripts/run_wp4_robustness.py` then `python scripts/run_wp5.py` to reconstruct the input matrix and report. One version-pinned commit must bind the source, parameters and derived outputs; changes to the WP4 matrix invalidate the previously generated WP5 report.

### Optional end-to-end runtime pilot (machine-dependent)

- Environment: `Linux-6.18.57-x86_64-with-glibc2.41`; Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0; 2 repetitions of 7200 simulated seconds each.
- These figures include numerical integration, simulated sensing, observer updates, QP assembly, solver and Python interpreter overhead. They are **not per-solve MPC execution times**, worst-case execution times or proof of real-time readiness.

| Case | Method | Median full-simulation wall time (s) | Range (s) |
|---|---|---:|---:|
| `nominal` | `IMC_0p5` | 0.047 | 0.047–0.048 |
| `nominal` | `relay_PI` | 0.046 | 0.044–0.049 |
| `nominal` | `MPC_persistence` | 0.859 | 0.831–0.887 |
| `noise_0.30K_seed_11` | `IMC_0p5` | 0.062 | 0.054–0.070 |
| `noise_0.30K_seed_11` | `relay_PI` | 0.041 | 0.041–0.042 |
| `noise_0.30K_seed_11` | `MPC_persistence` | 0.867 | 0.803–0.931 |
| `heatpump_capacity_minus20pct` | `IMC_0p5` | 0.058 | 0.043–0.073 |
| `heatpump_capacity_minus20pct` | `relay_PI` | 0.041 | 0.041–0.042 |
| `heatpump_capacity_minus20pct` | `MPC_persistence` | 0.877 | 0.814–0.941 |

## What this study cannot establish

- No manufacturer data, real refrigerant cycle, commissioned controller, physically measured process duty or calibrated HX `UA(f)`; no conclusion generalises to a particular industrial HTHP.
- No economic savings, absolute cost, guaranteed heat delivery, formal closed-loop stability, delay margin, safety integrity level, sample-based failure probability or statistically independent uncertainty estimate.
- No dedicated sensor-bias, sensor dropout, correlated-noise or externally validated forecast-error benchmark yet. The price scenarios, storage tariff flexibility and SOC active-set economic loss remain separate future research stages.
- The 20 scenarios are not a representative probabilistic distribution; counting scenario wins does not measure employment, publication or industrial deployment probabilities.

## Source data and result artifacts

- `results/wp4_robustness_matrix.csv` — source 100 runs (20 scenarios × 5 methods).
- `results/wp4_robustness_summary.json` — provenance and perfect-future-forecast exploratory rows.
- `results/wp5_case_comparison.csv` — 20 source-linked case-level comparisons, including the service gate.
- `results/wp5_paired_comparisons.csv` — all 80 MPC-versus-PI raw paired effects.
- `results/wp5_controller_summary.csv` — controller summary and Pareto appearances.
- `results/wp5_category_summary.csv` — declared grouped descriptive analysis.
- `results/wp5_forecast_sensitivity.csv` — two additional-information scenarios; never included in equal-information rankings.
- `results/wp5_runtime_local.json` — optional platform-specific end-to-end benchmarking, not MPC solver-only timing.
- `results/wp5_analysis.json` — machine-readable full audit, metadata and failures.
- `results/wp5_paired_tracking.png` and `results/wp5_eligible_energy.png` — visual summaries; infeasible pairs excluded from conditional electricity comparison.

**WP5 stage outcome:** a reproducible *comparative analysis of the existing synthetic benchmark*. The broader research plan’s real-fluid and price-service-validity tasks remain outstanding; WP5 is not evidence of a calibrated thermal control product.
