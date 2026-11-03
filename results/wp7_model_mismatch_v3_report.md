# WP7 v3 — model/plant mismatch: frozen PI versus property MPC

**Exploratory numerical model mismatch — NOT measured equipment uncertainty, not independent OEM data, not evidence of robust stability.**

All 15 frozen-controller runs evaluated. **12/15 numerically complete**, **8/10 service-qualified pairs**, **4/10 also terminal-equivalent for conditional electricity comparison.**

## Protocol

Identical CoolProp/IF97 property map, actuator bounds/slew, setpoint, single buffer sensor, sampled noise and delay (same seed per pair), 120s control updates, frozen WP3 PI gains, frozen WP4 local-QP MPC settings and property-model observer. The **truth** alone uses the declared alternate HX process UA, header–buffer conductance, or compressor lag; predictor remains nominal. All variants have their own equal-service reference initialization. The nominal case must reproduce *every* published v2 PI physical/control trace and KPI exactly; the MPC is compared with explicit strict float tolerances. The first cross-environment replay exposed a 5.6e-6 K nominal MPC trajectory difference. Tolerances were introduced after diagnosing that difference; they are not preregistered physical error margins. All solver statuses and accepted step counts must still match.

These ±15% / +30% perturbations are **chosen illustrative errors**, not manufacturer tolerances or confidence intervals. The error family does not include a perturbed compressor Q/P map, compressor oil, finite water source/sink, or calibrated sensor bias.

## Paired results (MPC minus PI)

| True plant scenario | PI comparator | Complete | Same qualified service | Terminal match | ΔIAE K·s | Δelectricity kWh if eligible | MPC fallbacks |
|---|---|---|---|---|---:|---:|---:|
| nominal | PI_IMC | True | True | True | -1139.334 | 0.758 | 0 |
| nominal | PI_relay | True | True | True | -361.183 | 0.164 | 0 |
| ua_proc_minus15_source_drop3 | PI_IMC | False | False | False | — | — | 0 |
| ua_proc_minus15_source_drop3 | PI_relay | False | False | False | — | — | 0 |
| ua_proc_plus15_noisy_delayed | PI_IMC | True | True | False | -851.072 | — | 0 |
| ua_proc_plus15_noisy_delayed | PI_relay | True | True | True | -409.590 | 0.418 | 0 |
| compressor_lag_plus30_source_drop3 | PI_IMC | True | True | False | -2990.569 | — | 0 |
| compressor_lag_plus30_source_drop3 | PI_relay | True | True | True | -767.891 | 0.631 | 0 |
| header_buffer_khb_minus15_combined | PI_IMC | True | True | False | -1206.220 | — | 0 |
| header_buffer_khb_minus15_combined | PI_relay | True | True | False | -475.899 | — | 0 |

The electricity eligibility gate is unchanged from WP7 v2: both controllers must finish the *entire* run, deliver qualified service, and have final header/buffer/total thermal inventories (0.5 kWh) and actual/final commanded modulation (0.02) within the same tolerances. Pairs that fail any gate receive **null**, not zero savings.
No tuning or scenario selection was based on these outcomes.

## Interpretation

This test demonstrates sensitivity to deliberately perturbed lumped-parameter physics, not predictive accuracy on a real HTHP. Neither nominal nor perturbed model has independent OEM calibration. Small tracking errors do not imply a lower electricity bill. Instrumented validation, additional out-of-sample source/sink bounds, model identification, uncertainty intervals and pilot trials are requirements for any industrial claim.

Raw machine-readable histories, controller fallback statuses and exact comparator gates are in [the v3 JSON](wp7_model_mismatch_v3.json). Reproduce with `python scripts/run_wp7_model_mismatch.py` after `pip install -e '.[realfluid,qp]'`.
