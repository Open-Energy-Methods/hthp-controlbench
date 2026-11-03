# WP7 v2: property-consistent predictive control and observer cross-check

**15/15 complete**, **10/10 service-qualified pairs**,
**5/10 also terminal-inventory/actuator matched**.

## Protocol

Same uncalibrated WP7 physical truth, setpoints, noise seeds, disturbance history,
fixed nominal WP3 PI gains and WP4 MPC QP weights/solver as v1.
The v1 15-run published source is SHA-256 frozen and all 10 PI physical
trajectories, sampled observations and energy KPIs are reproduced before
any result is written.

**Changed variable:** the observer and MPC's state/power predictor both
use the property-backed IF97 enthalpy and CoolProp condenser map,
rather than the WP2 synthetic surrogate. The QP remains local and
may reject infeasible/nonlinear rollouts or fall back to PI.

| Scenario | Old MPC IAE (K s) | New MPC IAE (K s) | Old fallbacks | New fallbacks | New header observer MAE (K) |
|---|---:|---:|---:|---:|---:|
| nominal | 187.1788 | 306.1694 | 0 | 0 | 0.0140 |
| source_minus3K | 799.1058 | 350.4182 | 0 | 0 | 0.0140 |
| sensor_noise_0p20K | 919.8052 | 942.2686 | 0 | 0 | 0.1131 |
| sensor_delay_60s | 203.7979 | 311.6391 | 0 | 0 | 0.0155 |
| combined_noise_delay_source | 1074.3733 | 882.3236 | 0 | 0 | 0.1063 |

## Electricity-comparison eligibility

Numerical completeness and simulated full service are *insufficient* for electricity savings;
the final header thermal energy, IF97 buffer inventory, total inventory and final
compressor modulation/command must also match within declared numerical limits.
Ineligible entries are left null; no forced ranking.

| Scenario | PI baseline | Complete? | Service? | Terminal match? | ΔIAE new MPC–PI (K s) | Eligible Δelectricity (kWh) |
|---|---|---|---|---|---:|---:|
| nominal | PI_IMC | True | True | True | -1139.3342 | 0.7581 |
| nominal | PI_relay | True | True | True | -361.1827 | 0.1637 |
| source_minus3K | PI_IMC | True | True | False | -2981.2784 | — |
| source_minus3K | PI_relay | True | True | True | -775.4546 | 0.6407 |
| sensor_noise_0p20K | PI_IMC | True | True | False | -155.2255 | — |
| sensor_noise_0p20K | PI_relay | True | True | False | -482.2145 | — |
| sensor_delay_60s | PI_IMC | True | True | True | -1153.9495 | 0.7834 |
| sensor_delay_60s | PI_relay | True | True | True | -355.7347 | 0.1769 |
| combined_noise_delay_source | PI_IMC | True | True | False | -1346.8549 | — |
| combined_noise_delay_source | PI_relay | True | True | False | -69.8542 | — |

## Evidence boundaries

This is an internal numerical agreement and model-transfer study, not
an independent measured observer dataset or calibrated industrial model.
Both physical truth and model are derived from the same assumed CoolProp
and IF97 physics; matching a model to its own equations is not empirical validation.
No OEM compressor, finite source/sink, oil envelope, pressure rating,
robust MPC stability or financial savings claim.
Adverse solver fallbacks and nonqualified cases remain in the ledger.
