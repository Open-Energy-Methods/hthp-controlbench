# WP7: matched property-backed PI/MPC control pilot

**Benchmark:** `WP7_PropertyTruth_SyntheticPredictor_Pilot_v1`. **15/15 full-horizon runs completed**.
**10/10 comparisons** pass full service; only **4/10** also match final thermal inventories and actuator states.

## What is and is not matched

- PI and MPC use the SAME property-derived refrigerant heat/electricity lookup, IF97 water enthalpy, thermal conductances, actuator lag, numerical timestep and process heat demand.
- Both use a single sampled buffer-temperature sensor, paired noise seed, identical delay, current known disturbances and 120-second command clock.
- MPC predicts on the older, uncalibrated WP2 *synthetic* model. The observer propagates its unmeasured states using that model without accessing the true header temperature or compressor modulation after initialization.
- PI gains are fixed from the WP3 nominal identification. MPC QP structure/weights are frozen before these scenarios; no calibration on the 5 cases.
- Every property-map extrapolation or water-pressure phase failure stops that run. Such incomplete runs cannot be ranked.
- An electricity saving cannot be credited unless both runs also finish with independently matched header, IF97 buffer and total thermal inventories (0.5 kWh each), actual compressor modulation and final command (0.02 each).
- A zero heat shortage in a simplified synthetic process does not establish guaranteed commercial heat service.

## Run ledger

| Scenario | Controller | Status | IAE (K s) | Electricity (kWh) | Spec-unserved (kWh) | Fallbacks |
|---|---|---|---:|---:|---:|---:|
| nominal | PI_IMC | complete | 1445.504 | 248.997 | 0.000 | 0 |
| nominal | PI_relay | complete | 667.352 | 249.591 | 0.000 | 0 |
| nominal | MPC_persistence | complete | 187.179 | 249.891 | 0.000 | 0 |
| source_minus3K | PI_IMC | complete | 3331.697 | 248.664 | 0.000 | 0 |
| source_minus3K | PI_relay | complete | 1125.873 | 253.099 | 0.000 | 0 |
| source_minus3K | MPC_persistence | complete | 799.106 | 252.706 | 0.000 | 0 |
| sensor_noise_0p20K | PI_IMC | complete | 1097.494 | 249.439 | 0.000 | 0 |
| sensor_noise_0p20K | PI_relay | complete | 1424.483 | 249.182 | 0.000 | 0 |
| sensor_noise_0p20K | MPC_persistence | complete | 919.805 | 249.775 | 0.000 | 0 |
| sensor_delay_60s | PI_IMC | complete | 1465.589 | 248.984 | 0.000 | 0 |
| sensor_delay_60s | PI_relay | complete | 667.374 | 249.591 | 0.000 | 0 |
| sensor_delay_60s | MPC_persistence | complete | 203.798 | 249.905 | 0.000 | 0 |
| combined_noise_delay_source | PI_IMC | complete | 2229.179 | 244.940 | 0.000 | 0 |
| combined_noise_delay_source | PI_relay | complete | 952.178 | 247.410 | 0.000 | 0 |
| combined_noise_delay_source | MPC_persistence | complete | 1074.373 | 246.423 | 0.000 | 0 |

## Matched paired interpretations

Electricity comparisons require complete simulations, qualified service, independently matched final thermal inventories and matched final actuator states. Raw electricity differences outside these gates remain diagnostics only. No tariff, OEM capacity or statistical confidence claim is made.

| Scenario | PI baseline | Both service eligible? | Terminal equivalent? | Electricity comparable? | ΔIAE (K s) | Conditional Δelectricity (kWh) |
|---|---|---|---|---:|---:|
| nominal | PI_IMC | True | True | True | -1258.325 | 0.894 |
| nominal | PI_relay | True | True | True | -480.173 | 0.300 |
| source_minus3K | PI_IMC | True | False | False | -2532.591 | — |
| source_minus3K | PI_relay | True | False | False | -326.767 | — |
| sensor_noise_0p20K | PI_IMC | True | False | False | -177.689 | — |
| sensor_noise_0p20K | PI_relay | True | False | False | -504.678 | — |
| sensor_delay_60s | PI_IMC | True | True | True | -1261.791 | 0.920 |
| sensor_delay_60s | PI_relay | True | True | True | -463.576 | 0.314 |
| combined_noise_delay_source | PI_IMC | True | False | False | -1154.805 | — |
| combined_noise_delay_source | PI_relay | True | False | False | 122.196 | — |

## Limits and next experiments

This is a **limited numerical transfer test**, not a validated property-predictor MPC: the MPC uses the same historical synthetic WP2 predictor. The property map itself is a hypothetical displacement/efficiency surrogate derived from the target 310 kW reference output, not manufacturer data.
Before credible controller conclusions: introduce a property-consistent predictive model, independent observer validation, tighter holds, multiple out-of-training sensor/actuator disturbances, explicit constraint and solver logging, a finite source/sink hydraulic model and measured OEM envelopes.

Reproduce: `python scripts/run_wp7_control.py` with CoolProp/OSQP extras; run the WP7 controller unit/integration tests first.
