# WP7 property-truth / WP2 controller-transfer pilot (Audit A04)

**Status:** scientific pilot, **not** manufacturer-validated equipment or a
property-model-derived MPC controller. This study is deliberately distinct from
the corrected synthetic benchmark `L1_RelayPeak_v2` and does not alter its
rankings.

## What is actually compared

- **Truth:** the same WP7 refrigerant-property Q/P map and IF97 water-enthalpy
  dynamic plant for *both* controllers, with finite-process-HX physical service
  qualification and the same actuator modulation, slew and lag. The nominal
  compressor displacement, isentropic efficiency, HX UA, water pressure and
  source temperature remain **assumed** rather than OEM-calibrated.
- **Controllers:** fixed nominal WP3 IMC-0.5tau PI and the existing WP4 MPC,
  both originally tuned/designed on WP2's synthetic model. MPC uses that same
  fixed WP2 model to predict unmeasured header temperature and compressor
  modulation. It is **not** a newly developed WP7-property predictor.
- **Observations:** one sampled buffer-temperature signal every 60 seconds,
  optionally with paired seeded noise and/or 60-second delay. Both update the
  compressor command every 120 seconds. Current exogenous source/return
  temperatures and last applied command are available to both; the MPC does
  not receive the true unmeasured header or modulation state after initialisation.
- **Boundaries:** operating points outside the declared interpolation grid and
  water-phase envelope fail closed. No extrapolation or imputation of failed
  runs. Controller ranking/delta fields are NULL unless **both** complete and
  provide fully specification-qualified process heat.
- **Experiments:** independent nominal, 1-K source drop and 0.1-K seeded
  sensor-noise pilots, under a 40-minute matched horizon. These are selected
  cases, not a probabilistic robustness sample.

The true heat-pump map is not based on measured compressor capacity/efficiency,
discharge-temperature or pressure limits. The finite heat-source/sink flow and
pinches are not independently verified, and no terminal-state matching is
imposed to justify electricity *savings*. Differences are conditional
diagnostics, not calibrated cost/energy benefits.

Run `python scripts/run_wp7_controller_transfer.py` after installing
`pip install -e ".[qp,realfluid]"`. Unit tests use a synthetic invertible
property backend to exercise sensing and map-rejection behavior; GitHub Actions
also runs the separate CoolProp research script. No empirical validation,
formal stability proof, hardware pressure conformity or certified safety
assessment exists.

**Still open in issue #12:** a property-map-aware MPC predictor, thorough
observer residual/error analysis, independent held-out source/sink disturbances,
matched real-fluid PI/MPC designs, solver worst-case timing, and equipment
validation. This pilot is the first cross-model transfer screen only.
