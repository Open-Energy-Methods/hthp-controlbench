# WP4 extension — robustness, one-sensor fairness and numerical QP solver audit

**Scope:** computational research, synthetic uncalibrated heat-pump plant. This is not evidence of industrial controller deployment, experimental identification or robust-stability certification.

## Questions

1. Does the preliminary nominal PI–MPC ordering survive WP3's twenty predefined uncertainty/saturation cases when both algorithms receive the **same temperature sensor** and sample with the **same control period**?
2. How frequently does the MPC fall back to bounded PI when its local QP or nonlinear trust checks fail?
3. Does a dedicated quadratic-programming solver (OSQP) solve the **same finite-horizon QP** with similar accepted commands and objective values to the original SLSQP backend?
4. What apparent MPC benefit is due to **future disturbance information**, rather than the control algorithm alone?

## Source and architecture

- Model, heat exchanger, energy accounting: original WP2 `core.py` and RK4 `sim.py`, unchanged.
- PI tunings: original WP3 FOPDT/IMC λ ∈ {0.5τ,1τ,2τ} and relay-derived Tyreus–Luyben; **identified only on the nominal plant, then fixed**.
- Scenario list: imported directly from WP3 `robustness.declared_cases` — twenty named cases with **paired Gaussian seeds** for noise and 60-/180-second measurement delays, source/return disturbances, plant-parameter perturbation, bypass variant, saturation and setpoint excursion.
- **Sensor:** one buffer-temperature measurement every **60 s**; noise is added to the sensor *not the nonlinear plant*. Historical measurements are delivered via a causal FIFO with a delay of `delay_updates × 60 s`. Neither controller sees future noisy samples.
- **Controller update:** every **120 s**. All five controllers are rerun using this clock. Thus the numeric results are **not directly comparable to the earlier WP3 60-s controller matrix**.
- MPC state reconstruction uses a known nominal **open-loop model propagation** of `T_h` and `n` from past applied commands, with the delayed/noisy buffer sample replacing `T_b`. It never reads the future or instantaneous true unmeasured header/modulation states. This **is not a verified Kalman observer**, and propagating nominal dynamics in an uncertain plant induces estimation error.
- Disturbance knowledge: current source/return conditions, **persistence** over the MPC horizon. The perfect-future-disturbance variant is shown **separately**, not counted as equal-information MPC.
- MPC horizon six controller intervals, 120-s interval, nonlinear integration step **20 s** for this robustness matrix. Check `tests/` for 10-s integration calculations and numerical verification.

## Three-valued reporting

Every scheduled controller/scenario run produces one CSV row. The `finite` field indicates whether the numerical simulation completed. MPC `accepted_mpc`, `pi_fallbacks`, `fallback_fraction` and per-status counts are reported independently of finite completion. A numerically completed run with high unmet service is **not** a successful controller deployment. A feasible QP may still be rejected by the nonlinear rollout and return to PI. `service_unserved_kWh` is based on the specified temperature-quality metric, whereas `physical_energy_shortfall_kWh` concerns physical heat transfer. Energy-balance residuals are also recorded.

## Measured synthetic results

See [`results/wp4_robustness_matrix.csv`](../results/wp4_robustness_matrix.csv) and the JSON summary. The twenty cases × five methods give **100 complete simulation runs** with no numerical run omissions. Lowest IAE across these five methods: **MPC 14/20**, relay-derived PI **6/20**, other PI tunings **0/20**. This is a result on the fixed synthetic scenario set, not a statistical confidence estimate.

| Case | IMC 0.5τ IAE [K s] | Relay PI IAE [K s] | MPC persistence IAE [K s] | MPC fallbacks |
|---|---:|---:|---:|---:|
| Nominal | 2,708.95 | 789.30 | **153.19** | 0 |
| 180-s sensor delay | 2,757.69 | 4,019.94 | **382.32** | 0 |
| 0.3-K noise + 180-s delay + 20% heat-pump derating | 14,693.44 | **6,647.47** | 14,815.66 | 0 |
| Deliberate 40% capacity derating | 98,302.85 | 95,709.49 | **94,941.71** | 48 |

At nominal conditions, electric consumption is **584.11 kWh for MPC** versus **583.44 kWh for relay PI** over four simulated hours, so improved tracking **does not imply electricity savings**. Relay PI is substantially better under the combined derating/noise/delay stress despite being worse under 180-s delay alone. Severe physical derating leaves service substantially unmet across controllers; some MPC updates fall back because SLSQP cannot resolve the constrained QP. No controller can create missing compressor capacity.

*Separate extra-information test:* perfect future disturbances yield MPC IAE 140.48 K s in the nominal scenario (vs 153.19 under persistence); under 20% capacity derating, perfect future IAE 14,794.63 K s (vs 14,743.94 under persistence). Advance information is **not** guaranteed to improve results under unmodelled parameter changes.

## Boundary/derivative correction

The earlier LTV Jacobian used a central difference in actual modulation `n` even at `n=0` or `n=1`. That probes outside the declared plant domain and caused spurious `modulation state out of bounds` fallbacks in saturation cases. This extension uses a feasible central/one-sided finite-difference quotient for both discrete dynamics and electrical power. Tests explicitly exercise both modulation boundaries. The observer projects only floating-point drift to admissible modulation bounds; it does not use true plant states. **The severe case still produces 48 actual SLSQP solve failures/fallbacks**, which remain reported.

## Dedicated OSQP cross-check

The same assembled quadratic form `0.5 zᵀHz + gᵀz` and linear constraints are sent to (a) SLSQP and (b) OSQP through a sparse CSC upper-triangular Hessian and bounds. Both solutions must independently satisfy hard linear constraints and the nonlinear rollout before being accepted. The optional OSQP dependency is installed in the Python CI matrix. Run:

```bash
python -m pip install -e '.[plots,qp]'
python -m unittest discover -s tests -v
python scripts/run_wp4_solver_audit.py
python scripts/run_wp4_robustness.py
```

The solver audit saves `results/wp4_solver_audit.json` and fails if either backend rejects a nominal test point or their first commands differ by >0.02 or raw QP objectives by >0.5. Three declared operating points are checked. The thresholds are numerical reproducibility screens, **not** robust-stability or optimality certificates. OSQP's status and independent primal checks are required; simply reporting a returned vector is insufficient. OSQP is not presently available in the author's offline container, so OSQP-specific local tests skip; **GitHub CI is the authoritative executable check for that backend**. Do not claim any OSQP agreement before its CI job succeeds.

**OSQP reference:** [Python interface](https://osqp.org/docs/interfaces/python.html).

## Known limitations

- The plant's compressor and COP maps are illustrative; no real-fluid feasibility proof or manufacturer calibration exists.
- The minimal observer does not identify bias or guarantee convergence under poor sensor quality or parameter drift.
- No correlated-noise, sensor outage, nonlinear estimator, stochastic uncertainty or formal closed-loop stability margin is established.
- The MPC trust region uses a single expansion point across each horizon even though it is updated every controller cycle. The nonlinear rollout guard helps but is not a global guarantee.
- A fall back to PI may still fail service when compressor capacity is physically insufficient.
- The SLSQP and OSQP backend comparison tests only finite-dimensional numerical consistency at selected operating points, not solver execution time under industrial real-time conditions.
- The 20 scenarios are representative synthetic stress tests, **not a sampled distribution** of realistic industrial faults. Scenario counts must not be interpreted as probabilities.

## Next work packages

The control comparison still needs a stronger estimator/sensor fault model, careful uncertainty envelopes, and real-fluid-cycle anchoring. WP5 study synthesis and the independent SOC and thermodynamic studies remain future work.