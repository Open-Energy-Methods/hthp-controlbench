# WP3 robustness study — simulated PI controls (v0.2)

**Evidence status:** executed, deterministic **synthetic** sensitivity experiments on the WP2 L1 plant. This study is not empirical hardware PID tuning, not a calibrated heat-pump twin, and not a robust-stability proof. The parent research specification v0.5 remains unchanged.

## Research questions

1. Do the PI tuning approaches maintain buffer-temperature tracking when the *measurement* is noisy/delayed, without using true states in the feedback loop?
2. How does performance change when the *true* plant differs from the nominal identified model (thermal capacitance, UA, header/buffer coupling, compressor capacity), with the same fixed gains and nominal bias?
3. Do hard compressor-command constraints and anti-windup prevent numerical runaway under deliberately infeasible thermal demand, and how quickly can control recover from a temporary setpoint excursion?
4. Are tracking, actuator effort, delivered-energy deficit, and service-quality shortfall telling the same story? (They need not.)

## Protocol (predeclared, fully scripted)

- Nominal plant: `Parameters(hx_mode='no_bypass')`. **Only this plant** is used to identify the FOPDT and relay oscillation models. Tuning is performed once before the scenario sweep. Four fixed candidate gains: IMC with `lambda/tau` = 0.5, 1, 2, and relay-derived Tyreus–Luyben PI. No retuning or gain/bias recalibration during the stress tests.
- All runs initialize at the **nominal** equilibrium, with setpoint `T_b,0 + 0.4 K`, and follow identical process-return/source-temperature disturbance schedules. Where physical parameters change, the actual plant is deliberately no longer at its own equilibrium. Controllers receive no oracle knowledge of those changed parameters.
- Plant integration: explicit RK4, `10 s`. PI sampling/hold: `60 s`. Scenario duration: `14,400 s` (4 h). Hard command limits `0 <= u <= 1` with absolute step change `<= 0.05` per controller update; first-order compressor modulation state remains separate from the applied command.
- Measurement layer: adds zero-mean, independently drawn Gaussian noise **at sample times** with standard deviation `0.1 K` or `0.3 K` and fixed seeds `11,23,47`; measured samples may be delayed by 1 or 3 full PI update intervals (60/180 s). Noise affects **only** observed `T_b` in `PIController.command`, not the plant thermodynamics. The same seed/innovation sequence is paired across tunings, even though the true trajectories differ.
- One-at-a-time plant perturbations: buffer capacitance `-20%, +20%`; header-to-buffer conductance `-20%`; process exchanger `UA -20%`; rated heat-pump capacity `-20%, +20%`. Additional cases: capacity reduced `40%` (deliberately service-infeasible), bypass transfer with `UA(f)=UA0*f^0.8`, combined `0.3 K` sensor noise + `180 s` delay + capacity derating, and combined sensing limitations + bypass operation.
- One temporary **artificial test setpoint** excursion of +12 K is imposed from 1200 to 3000 s to deliberately exercise saturation and recovery. It is not a required industrial service temperature and should not be interpreted as one.
- Total: **20 scenarios × 4 controllers = 80 runs**, including failed runs if any (both CSV and JSON record errors). The code does not filter unfavorable outcomes.

Reproduce:

```bash
python -m pip install -e '.[plots]'
python -m unittest discover -s tests -v
python scripts/run_wp3.py
python scripts/run_wp3_robustness.py
```

Outputs: `results/wp3_robustness_matrix.csv`, `results/wp3_robustness_summary.json`, and `results/wp3_robustness_comparison.png`. Every metric is calculated from **true plant states**, not measured values. No test data are used for tuning.

## Reported KPIs and interpretation

- **IAE (K·s)**: integral of absolute buffer-temperature setpoint error, including the temporary setpoint-excursion scenario by design. Comparisons should be made *within* scenarios, not between scenario-dependent targets.
- **RMSE and maximum absolute error (K)**: truth-state tracking errors; reported separately from command movement.
- **Command total variation**: sum of absolute change in commanded `u` at the 60-s update points. It is a dimensionless *proxy* for actuator cycling, not calibrated wear or life consumption.
- **Sensor delay/noise**: only an observation-channel model. The three noise seeds do not justify confidence intervals, general stochastic claims or industrial sensor realism.
- **Quality-unserved kWh**: the pre-existing all-or-nothing specification flag (`q_spec_unserved`) integrated over time. It can report the full requested duty whenever process temperature quality is inadequate; it must **not** be confused with physically missing energy.
- **Physical-energy shortfall kWh**: integrated positive `(Q_requested - Q_physically_transferred)` for the fixed-throughput scenarios, using the declared return-temperature schedule.
- **Integral saturation events / fraction of command points at a bound**, max per-update slew, accumulated electricity and conservation residual are reported independently. `finite=True` and a passing numerical test are *not* physical service-validation certificates.
- **Recovery**: first time after the +12 K setpoint excursion that absolute tracking error remains within 1 K for at least 600 s. No qualifying recovery yields an empty value, not an invented duration.

## Selected reproducible findings

| Scenario | IMC λ=0.5τ IAE | Relay-derived IAE | Main limitation or trade-off |
|---|---:|---:|---|
| Nominal | 2,686 K·s | 790 K·s | Relay tighter nominal tracking |
| 180-s measurement delay | 2,732 K·s | 2,820 K·s | Relay response worsens more under delay |
| 0.3 K noise (median of 3 seeds) | 2,640 K·s | 2,309 K·s | Relay total command variation **10.19**, versus IMC **2.95** |
| HP thermal capacity −20% | 14,747 K·s | 1,880 K·s | Relay reaches hard `u=1` (22 internal saturation events); IMC below-spec service accumulates |
| Combined noise/delay/−20% capacity | 14,800 K·s | 7,120 K·s | Relay command variation **7.67**, versus IMC **2.84** |
| Severe −40% HP capacity | 98,112 K·s | 94,666 K·s | **Both fail required service**; missing thermal capacity cannot be tuned away |
| Temporary +12 K setpoint/recovery | 28,142 K·s | 23,103 K·s | Relay recovers to sustained ±1 K in **1,050 s**, IMC in **3,140 s**, but higher movement |

The relay setting obtains the lowest IAE in **17/20** stress cases; the remaining three favor IMC `0.5τ`. This is **not** a statistical success rate or probability that relay PI is best: cases are correlated and deliberately selected. The gain choice for the later MPC comparator must be justified under multiple objectives and documented equally, not chosen to make MPC look favorable. At minimum retain IMC `0.5τ` and the relay PI as distinct reference baselines; report the full tuning sweep.

## Robustness limitations and next verification gates

- No measured sensor calibration, correlated noise, quantization, outliers, packet drops or time-varying delays. No state estimator or derivative filter. No hardware-in-the-loop and no actual valve/compressor time-series data.
- The PI controller does not implement a derivative term; these are **PI**, not PID, experiments.
- One-at-a-time parameter changes and two combined cases are **screening**, not a complete uncertainty distribution, formal loop-stability margin, or proof of robust control.
- Heat-pump performance remains a synthetic COP/capacity map; the differential model may not predict real high-lift plant dynamics. Severe capacity failure identifies a synthetic infeasible regime; do not interpret as operational safety advice.
- The model retains an ideal algebraic process-bypass controller and provisional flow-`UA` relationship. Service-classification conventions can amplify quality shortfall on near-threshold excursions, hence the distinct physical-deficit KPI.
- Before comparing with WP4 MPC, define the primary performance and actuation objectives *a priori*, report identical information sets separately from forecast-advantaged MPC, and retain both well-performing and conservative PI variants. Add a nonlinear rollout check for MPC crossing the bypass active-set kink.