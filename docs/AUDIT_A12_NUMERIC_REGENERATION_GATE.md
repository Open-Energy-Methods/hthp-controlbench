# Audit A12 — numerical-regeneration gate for corrected L1

The corrected `results/L1_RelayPeak_v2/` snapshot was generated under PR #11
from the synthetic, uncalibrated WP2 plant. Source-code fixes to
`ht_hp_controlbench/pi.py` and the PI/MPC numerical comparison scripts can
otherwise leave the published CSV/JSON files stale.

`scripts/check_published_benchmark.py` compares fresh **WP3, WP3 robustness
and WP4 robustness** simulation rows with the published v2 snapshot by
scenario-controller identity, numeric outputs and the full WP4 information
budget (sensor, solver status and fallback states). It separately verifies
that regenerated WP5 analysis refers to the same WP4 CSV content SHA and
preserves the reviewed service-qualified outcomes.

The GitHub Actions Python 3.12 job runs the checker *after* regenerating the
WP3–WP5 results, so the comparator never evaluates a previously committed
flat result file in place of a fresh model run. Unit tests deliberately alter
IAE, observation mode, nonfinite electricity and row completeness; every
tampering case must fail.

Numeric tolerances are `rel_tol=1e-5` and `abs_tol=2e-4`, designed as a
cross-environment deterministic regression screen (not measurement
uncertainty or experimental agreement). A genuine scientific-model change
must receive a separately reviewed `L1_..._v3` dataset rather than
silently overwriting v2 or raising regression tolerances without justification.

This gate does not independently validate thermodynamic model parameters,
predictive control stability, OEM compressor limits or physical energy
measurements. It is only one part of audit issue #15 and does not close the
broader WP9 publication/readiness requirements.
