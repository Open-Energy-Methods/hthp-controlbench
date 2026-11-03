# WP7 instrumented observer — data contract and fail-closed scoring

**No instrumented matching-asset data currently exists in this repository.**
This is a **readiness contract**, not an assertion that external hardware
measurements or live control have been performed.

## Raw CSV: mandatory data channels

Every sample must be from the **same nominated physical HTHP asset**;
timestamps must be monotonically increasing and aligned to the measurement
clock. Use **SI units**, never silently convert the reported sensor values.

| CSV column | Units | Required provenance and use |
|---|---|---|
| `time_s` | s | Monotonically increasing acquisition time; no duplicate or imputed timestamps |
| `buffer_measured_k` | K | **Only live feedback sensor** supplied to the observer; sensor location and calibration must be documented |
| `header_measured_k` | K | Independent withheld *truth reference*: at t=0 it initializes the model, afterward it is used **only for scoring** |
| `modulation_measured` | 0–1 fraction | Independent actual shaft/control modulation, **not just requested command**; also withheld except initialization |
| `command_applied` | 0–1 fraction | Compressor command physically applied over the following interval; motor/drive feedback should be separately documented |
| `source_measured_k` | K | Observed source boundary condition; previous sample held between updates |
| `return_measured_k` | K | Observed process return; previous sample held between updates |

Do not generate fake values to satisfy this schema. Do not treat a CFD,
CoolProp, synthetic WP2/WP7 trajectory, other-laboratory dataset or
unreferenced spreadsheet as *independent rig measurements*.

## Required provenance manifest

The JSON supplied to `--manifest` must contain these fields:

- `raw_data_sha256`: the exact SHA-256 of the unmodified CSV bytes
- `measurement_reference_uri`: independent recording source/protocol
- `sensor_calibration_uri`: traceable sensor/DAQ calibration documentation
- `instrumented_asset_id`: matching model / serial or installation identifier
- `train_interval`: `[start_s, end_s]`
- `heldout_interval`: `[start_s, end_s]`; **strictly later** than training
- `sensor_delay_s`: **0 for current direct-aligned implementation**; a nonzero
  delay returns `SENSOR_DELAY_OR_CLOCK_NOT_ALIGNED__NO_SCORE`, never a
  fabricated corrected result
- `time_sync_uncertainty_s`: documented nonnegative numerical uncertainty in
  clock synchronization

The implementation checks the input SHA-256 and sample alignment. It does
**not** independently authenticate the DAQ, calibration certificates or
claimed asset identity; these need external signed review.

```bash
python scripts/score_wp7_measured_observer.py \
    --csv /secured/instrumented_plant_samples.csv \
    --manifest /secured/signed_provenance_manifest.json \
    --output /secured/wp7_heldout_observer_results.json
```

The script does **not** download raw operational logs, fabricate inputs or
commit local measurements to a public repository. Scored residuals remain
**provisional** and report status
`DESCRIPTIVE_MEASURED_HOLDOUT_RESIDUALS__INDEPENDENT_REVIEW_REQUIRED`
even when small. It uses the existing *hypothetical* WP7 property map,
not an independently measured 310 kW compressor map.

For an actual publishable equipment validation, first freeze a model that
uses a documented, asset-specific OEM compressor map, measured finite
source/sink and HX capabilities and acceptable pressure/safety limits.
Then report held-out observer header/modulation MAE, RMSE, bias, maxima and
uncertainties using the independent instrumentation, with all rejected and
out-of-envelope intervals included. The current tool calculates those
descriptive errors but cannot provide their experimental interpretation
without the authentic source data and qualified review.
