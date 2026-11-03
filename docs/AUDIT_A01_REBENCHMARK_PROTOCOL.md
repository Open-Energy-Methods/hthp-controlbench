# Corrected L1 PI/MPC synthetic benchmarking — independent regeneration

**Version:** `L1_RelayPeak_v2`. This version is distinct from the historical
unversioned WP3–WP5 files in `/results`, which used a relay gain estimated at
hysteresis switching thresholds. The new benchmark is generated from the same
**synthetic** WP2 nonlinear plant, after the A01 true-peak correction; it is
not an experimental heat-pump controller or a WP7-property-truth rerun.

The original 20 predeclared scenarios, 5 fixed controllers, same one-sensor
measurement budget, and 120-s control updates are kept unchanged. The
Tyreus–Luyben controller changes solely because its nominal identification
now measures the half peak-to-peak temperature amplitude over actual settled
relay cycles. The IMC gains and MPC configuration are not opportunistically
retuned for any scenario. Both improvements and adverse controller results
must remain in the published ledger.

## Reproducibility command

In an environment with the optional solver/plot dependencies installed, run
from the repo root:

```sh
python scripts/run_wp3.py
python scripts/run_wp3_robustness.py
python scripts/run_wp4_robustness.py
python scripts/run_wp5.py
python scripts/snapshot_a01_rebenchmark.py
```

The last command checks the 20×5 matrix, WP5-source SHA, newly identified
relay settings and an independently rerun nominal relay PI simulation before
writing an immutable `results/L1_RelayPeak_v2` snapshot with per-file SHA-256
checksums and source-commit information.

GitHub Actions runs the same source scripts and uploads the snapshot as an
artifact. Neither old files nor reported historical rankings are overwritten.

**Interpretation limit:** reported case wins describe the selected synthetic
scenario set, not a probability, validated real-fluid equipment result, or
confidence interval. A04 common property-backed controller benchmarking
remains an unresolved independent scientific task.
