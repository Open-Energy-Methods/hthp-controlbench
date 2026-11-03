# WP7 control-transfer experiment — property-backed shared truth (pilot v1)

This is a **new numerical pilot**, not a new validated compressor model. It does
not replace existing WP7 CoolProp/TESPy property, water and thermodynamic work.

## Scientific question

Can the previously fixed WP3 IMC and relay PI baselines and WP4 persistence
MPC be transferred to a **different**, property-derived plant without hiding
model mismatch, changing information, re-tuning against the test cases, or
mistaking heat-quality failure for energy savings?

## Fair common plant and sensor protocol

- **Truth for all methods:** same R1233zd(E) condenser heat and electrical
  map, calculated using CoolProp and its hypothetical reference displacement;
  same IF97 6-bar(a) enthalpy buffer, hot-header capacitance, UA, losses, lag
  and bounded compressor modulation. There is no OEM compressor map.
- **Predictor:** MPC intentionally still uses the *WP2 synthetic* temperature
  and electrical-power model. This tests model transfer and is **not** a
  property-consistent MPC or validated plant observer.
- **Measurements:** one common buffer-temperature sensor at 60 s, same paired
  Gaussian noise seed and delay in seconds. Both controllers update every 120 s
  and receive the same current source/return disturbances. No future actual
  disturbance sequence is supplied to MPC.
- **Unmeasured states:** only the known shared initial header temperature and
  compressor modulation are initialized once. Thereafter header and modulation
  are propagated by the nominal synthetic predictor, not copied from the
  property truth. Sensor updates correct only estimated buffer temperature.
  Observer discrepancy against *post hoc* truth is reported.
- **Actuation:** same bounded command step, full-scale limits restricted to
  the supported property-map modulation interval, and the same compressor lag.
- **Thermodynamic rejection:** any off-map source, header or modulation,
  property backend exception, loss of assumed water-liquid pressure margin,
  nonfinite state or failed conservation tolerance stops the entire run. An
  incomplete run cannot be assigned a successful electricity or IAE metric.
- **Service gate:** full-horizon process qualification, unserved specified
  energy <= 1e-6 kWh and physical process shortfall <= 1e-6 kWh.
  Electricity deltas are reported only when *both* PI and MPC are complete
  and satisfy that same gate, **and** have matched independent terminal
  header energy, IF97 buffer enthalpy inventory and their sum (each within
  0.5 kWh), compressor modulation and final applied command (each within 0.02).
  Offset header/buffer inventory discrepancies cannot cancel. These tolerances
  are *numerical comparability* thresholds, not calibrated uncertainty bands
  or industrial process acceptance thresholds.

## Fixed scenario protocol

The initial five deliberately chosen deterministic scenarios are nominal,
3 K source reduction, 0.2 K sensor noise, 60 s measurement delay and a
combined source/return/noise/delay perturbation. Their values are fixed in
`declared_property_cases()`; there is no data-driven selection of favourable
runs. Short 360 s structural unit tests use analytic fake water/refrigerant
properties and **must never** be presented as a real refrigerant study.

```bash
python -m pip install -e '.[plots,qp,realfluid]'
python -m unittest discover -s tests -p 'test_wp7_control.py' -v
python scripts/run_wp7_control.py
```

The final script writes `results/wp7_control_pilot.json` with all decision
states and paired noise draws, `results/wp7_control_pilot.csv` for individual
runs, `results/wp7_control_pairs.csv` for eligibility-gated comparisons and
`results/wp7_control_pilot_report.md` with results. Failed runs remain
explicit. No outcome is presumed before numerical generation.

## Explicit non-conclusions

There is no OEM efficiency/displacement/pressure map, finite evaporator or
sink hydraulic rating, manufacturer fluid/lubricant compatibility evidence,
real-data observer validation, formal MPC stability or robust-safety
certificate. The synthetic WP2 predictor can reject/fallback or act poorly on
the property truth; such a result is evidence of *model mismatch*, not evidence
that MPC as a method is inferior. Likewise an improved KPI does not generalize
to real machines.

Before issue #12 can be closed, extend to **property-consistent MPC state
prediction**, independent observer/estimator testing, out-of-training envelopes,
QP/margin checks under diverse failures, cross-timestep convergence, and
transparent adverse cases. Issues #13–#15 cover separate hardware, SOC,
storage and release-validation gates.
