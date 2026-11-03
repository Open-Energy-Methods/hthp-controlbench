# WP7 v2: property-consistent MPC prediction and observer cross-check

## Controlled comparison

The previously published `WP7_PropertyTruth_SyntheticPredictor_Pilot_v1`
remains frozen. Its MPC predicted condenser and buffer behavior using the
WP2 *synthetic* three-state plant, despite its truth trajectory using
CoolProp refrigerant heat/power and 6-bar IF97 water enthalpy.

The v2 experiment retains exactly the same five predeclared cases, PI gains
from WP3, nominal MPC tuning, command period (120 s), sensing period (60 s),
time step (20 s), horizon (six periods), process HX, property map, pressure
and assumed compressor displacement. It only replaces two internal
`MPC_property` components:

1. **Predictor**: a property-model step function reconstructs 6-bar IF97
   water enthalpy from the observed buffer temperature, steps an
   enthalpy-based RK4 system with the WP7 condenser heat/electrical lookup,
   and fails closed if any substage OR accepted endpoint leaves the
   liquid-phase or declared property-map envelope.
2. **Observer**: the same property dynamics propagate unmeasured header
   temperature and compressor lag from the last **known applied input and
   exogenous disturbance**. At each sensor tick, only the estimated buffer
   temperature is replaced with the delayed/noisy single-sensor reading.
   No hidden true header or compressor state is sampled during control.

The original WP4 local QP and nonlinear-rollout acceptance machinery now
accept injection of the different state/power model. Its defaults are
unchanged and synthetic WP3–WP5 benchmark semantics are preserved.
When a property prediction, local QP, or nonlinear consistency test fails,
the existing bounded PI backup takes over. Fallbacks are counted.

## Independent numerical observer cross-check

This is independent **of controller action**, not independent empirical
sensor or compressor data:

- The same frozen PI trajectory is run with the old synthetic observer and
  the new enthalpy observer. PI only reads the measured buffer temperature;
  the physical truth, sensor noise, applied commands and energy metrics must
  be IDENTICAL, byte-for-byte for discrete traces and to numerical tolerance
  for the KPIs. Any difference is a regression, not performance evidence.
- Under noiseless nominal conditions, the property observer's unmeasured
  header/modulation estimates are compared after the fact against a separate
  truth RK4 implementation in `wp7_control.py` (the predictor reuses
  `storage_flexibility._stage`). Tests require small deviations.
- An additional held-out noisy/delayed sensor scenario uses an independent
  seed, and verifies that both observers read the same noisy sequence and
  produce the same physical PI truth, without accessing future true hidden
  states. Diagnostics report absolute header and modulation estimation errors
  and pre-update buffer innovations. Those errors are *post hoc only*.
- An artificially invalid refrigerant condition must cause explicit
  rejection, never interpolated heat or fabricated electrical power.

This tests software consistency and numerical observability assumptions,
**NOT measurement-based state-estimator identification or validation**.

## Evidence and limits

The `scripts/run_wp7_property_predictor.py` runner loads and hashes
`results/wp7_control_pilot.json`, reruns both PI baselines, and strictly
verifies that all ten PI physical trajectories, sensor draws and energy KPIs
reproduce the frozen v1 results. It then evaluates `MPC_property` on each
same scenario. The old MPC outcomes are read from the versioned source, not
regenerated or rewritten. Outputs:

- `results/wp7_property_predictor_v2.json` — full per-controller
  physical service, sensor/observer traces, applied controls and QP status
- `results/wp7_property_predictor_v2_pairs.csv` — same-service and
  terminal-inventory/actuator-gated pair comparisons
- `results/wp7_property_predictor_v2_transfer.csv` — old-vs-new MPC IAE
  and fallback counts, **descriptive only**
- `results/wp7_property_predictor_v2_report.md` — reviewed numerical
  outcome and interpretation

The predeclared 0.5 kWh per-store/total terminal energy, 0.02 compressor
modulation and 0.02 final-command tolerances still gate *all* electricity
comparisons; same simulated process service alone is not sufficient.

Nothing changes the independent OEM and finite-source/sink uncertainty:
the 310 kW reference compressor displacement, isentropic efficiency, heat
exchanger coefficients and water pressure are hypothetical and uncalibrated.
The same thermodynamic assumptions define truth and predictor. Accordingly
even a perfect v2 observer is **not** independent physical validation;
commercial control, regulatory, stable-operation or money-saving claims
remain unsupported. Issue #12 is not closed by this incremental study.

## Reproduction

```bash
python -m pip install -e '.[qp,realfluid,plots]'
python -m unittest discover -s tests -p 'test_wp7_property_predictor.py' -v
python scripts/run_wp7_property_predictor.py
```
