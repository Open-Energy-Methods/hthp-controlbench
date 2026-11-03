# WP7 v4 — strict comparability and claim-boundary audit

**Scope:** Post-hoc sensitivity of the terminal-inventory equivalence
gate for the immutable WP7 v3 simulator. All original trajectories
are re-read; no controller is retuned and no simulation results are
replaced. This is NOT independent physical validation.

## Independent rederivation of the original electricity-eligibility gate

The existing comparator permits **0.5 kWh thermal difference** in each
of header, buffer, and their total, plus 0.02 difference in final
compressor modulation and applied command. The raw v3 service and
end-state fields were independently checked here, confirming the
published default 4/10 eligible pairs.

The allowable 0.5 kWh terminal thermal inventory difference is
**not a measurement uncertainty** and can be comparable to the
reported idealised electrical-power differences. These thermal and
electrical energy values cannot simply be subtracted as if COP=1.
Therefore, positive/negative energy rankings must be described as
conditional on declared equivalence tolerances and idealised model.

## Sensitivity to tighter thermal-inventory equality

| Per-component AND total inventory tolerance | Eligible of 10 paired comparisons |
|---:|---:|
| 0.50 kWh thermal | 4/10 |
| 0.25 kWh thermal | 2/10 |
| 0.10 kWh thermal | 1/10 |
| 0.05 kWh thermal | 1/10 |
| 0.01 kWh thermal | 1/10 |

The actuator endpoint tolerance remains 0.02 in all rows.
These alternative thresholds were introduced **after** seeing
the v3 benchmark and are a claim-robustness audit, not
preregistered hypothesis tests.

## The four original nominal-tolerance eligible pairs

| Scenario | PI baseline | MPC−PI electricity (kWh_e) | MPC−PI final thermal inventory (kWh_th) |
|---|---|---:|---:|
| nominal | PI_IMC | +0.7581 | +0.0008 |
| nominal | PI_relay | +0.1637 | -0.1856 |
| ua_proc_plus15_noisy_delayed | PI_relay | +0.4185 | +0.2837 |
| compressor_lag_plus30_source_drop3 | PI_relay | +0.6312 | +0.2576 |

The original 0.5 kWh criterion labels all four above as
terminal-equivalent, but a stricter criterion retains only
the subset shown above. In all originally eligible cases MPC's
computed compressor electricity is higher; **that is a property
of this synthetic objective, policy and scenario set**, not an
industrial efficiency ranking or statistically significant result.

## Research readiness judgement

- **Software regression:** v3 15-run source/target identities and original
  0.5 kWh eligibility flags are independently reproducible.
- **Scientific limitation:** simulator truth and MPC predictor share the
  same uncalibrated refrigerant Q/P map and water EOS; the mismatch
  study varies only a few assumed lumped thermal parameters.
- **Optimizer limitation:** QP weight choices (temperature error,
  movement, slack and electric cost) are not justified by
  a formal multiobjective design or matched alternative design.
- **Comparison limitation:** 2-hour transients, discrete cases,
  fixed 300 kW heat demand and no measured actuator/sensor/error model.
- **Validation limitation:** no actual heat-pump equipment, measured
  compressor map, independent plant truth or safety approval.
- **Recommendation:** show methods and falsifying outcomes in a
  PhD *research sample*, not as a research paper claiming controller
  energy savings, SOC deployment or equipment certification.

Raw calculations: [machine-readable independent audit](wp7_comparability_claim_audit_v4.json).
Reproduce with `python scripts/audit_wp7_comparability.py`.
