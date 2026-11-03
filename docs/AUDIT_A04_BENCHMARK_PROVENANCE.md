# Audit A04 — controller benchmark lineage and corrected regeneration

The pre-audit legacy source results under `results/wp3_*`, `results/wp4_*`
and `results/wp5_*` are **not** automatically converted into corrected
experimental evidence. They were produced with an earlier relay amplitude
estimated at hysteresis switching values. The A01 fix changed the identification.

## Correction

- `ht_hp_controlbench/benchmark.py` provides one nominal-plant identification
  source for WP4 and its robustness extension: three IMC PI settings and one
  peak-based relay PI. There is no hard-coded old `Kp=0.3452` in the WP4
  baseline script.
- The WP5 written report derives the fallback count, nominal electricity
  difference and failed-run count from the current run rather than fixed
  historical numbers.
- `HTHP_RESULTS_DIR` redirects all five WP3–WP5 output scripts. Running
  `python scripts/run_corrected_benchmark.py` writes a separate
  `results/L1_RelayPeak_v2/` result set, preserving historical root-level files.
  This requires the optional QP and plotting dependencies for full coverage.
- The manifest records source checksums, dependency versions, exact nominal PI
  gain values, source matrix checksum and independently regenerated WP5 counts.
  It rejects a mismatched WP4 summary ID, WP5 matrix hash or incomplete matrix.

## Scientific interpretation

Until generated v2 outputs are reviewed and published, all pre-existing WP5
rankings remain legacy historical results. Even after regeneration, all WP3–WP5
comparisons remain conditional on an uncalibrated, synthetic compressor model.
A separate matched benchmark against the **WP7 property-backed dynamic plant**
is required before transferring controller rankings to that model. There is no
manufacturer equipment map, certified real-time MPC timing, robust stability
proof, or measured heat-pump efficiency in this audit.
