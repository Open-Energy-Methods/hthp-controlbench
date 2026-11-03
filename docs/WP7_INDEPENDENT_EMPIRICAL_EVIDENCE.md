# WP7 — independent empirical equipment and observer evidence audit

**Status:** External experimental evidence located; two public experimental
datasets undergo raw-file checksum and provenance inspection.
**WP7 reference equipment is still not validated.** **The property observer is
still not independently measured or validated.**

This document distinguishes: (1) a property calculation, (2) independent
external hardware measurements **on other equipment**, (3) an independently
approved equipment operating envelope **for the same specified compressor**,
and (4) a time-aligned, held-out dynamic observer test **on the same installed
system**. These are not equivalent levels of evidence. Do not move a
result from one category to another by analogy.

## 1. External data discovery, scope and citations

| Evidence source | Type | Directly comparable to WP7? | Appropriate use |
|---|---|---|---|
| [Widmaier et al., 2026, Zenodo](https://doi.org/10.5281/zenodo.17599603) | **Mixed**: calculated EN12900 manufacturer-polynomial results and independent OST/Milano compressor measurements | **No**: other compressor geometries and overall electric efficiency basis | Audit source labels, extract the **pure R1233zd(E) experimentally measured subset** and compare plausible efficiency ranges with explicit definitional caveats |
| [Leclercq, 2026, Zenodo](https://doi.org/10.5281/zenodo.20445833) | Measured R1233zd(E) scroll compressor in **two-phase/oil-mixed** inlet conditions | **No**: wet/two-phase flow, oil and different compressor architecture | Audit phase-specific efficiency and experimental variability, explicitly out of WP7 dry suction model domain |
| [Jeßberger et al., 2026, Mendeley Data](https://doi.org/10.17632/56m3dd55zf.1) | Experimental **37 kW** single-stage R1233zd(E) HTHP: part-load/off-design measurements, heat sink 75–140°C | Potentially relevant to **whole-cycle** validation, but **not** the WP7 310 kW asset | Next data-adapter candidate; source metadata established but direct API download returned **401**, so **no raw calculations or measured validation claim** made |
| [Ramirez et al., Applied Thermal Engineering, 2024](https://doi.org/10.1016/j.applthermaleng.2024.122961) | Experimental R1233zd(E) HTHP with external subcooler, ~38.6 kW at 148.5°C | **No**: materially different cycle topology, duty and compressor | Literature evidence that *some* equipment reached high temperature; cannot transfer ratings |
| [BITZER CSH2T product information](https://www.bitzer.de/mv/en/products/screw-compressors/csh2t/) | OEM family-level information with R1233zd(E), useful output up to **120°C** | **No**: nominal WP7 header ≈133.05°C, no matching exact compressor certified | Reject using this family brochure as proof of the hypothetical 133°C asset |

The two Zenodo datasets are labelled **CC BY 4.0** and accompanied by
published MD5 checksums. The numerical runner retrieves their original bytes
from Zenodo, checks MD5 and records SHA-256, then parses strict CSV. It
**never downloads via an unverified random mirror** and never counts
manufacturer-model-generated EN12900 rows as experimental observations.
It stores only aggregated statistics and citations, **not raw source rows**.

The Widmaier README explicitly separates the source-labelled data. This is
critical: a combined CSV with tens of thousands of records is mostly
manufacturer-polynomial outputs, *not independent equipment measurements*.
The pure-R1233zd experimental subset uses overall isentropic efficiency
defined using **electrical input**. WP7's assumed `eta_isentropic=0.75`
instead enters `h2=h1+(h2s-h1)/eta`, omitting motor, drive, auxiliaries and
a real compressor map. No matched-duty direct residual is valid without
reconciling definitions and compressor identities.

## 2. Reference physical quantities — conditional, not equipment evidence

The WP7 baseline requests **310 kW** condenser heat at a source temperature
of 60°C and header ≈133.05°C; `CycleAssumptions` forces that output at
75% modulation by **inferring an equivalent suction volume rate**. It does
not import a swept volume, power curve or compressor efficiency from OEM
documentation.

The external audit separately recomputes the model's condenser COP,
compressor ideal power and evaporator heat extraction using CoolProp.
Its finite-source and finite-sink tests start with **UNKNOWN mass
flow / allowable inlet/outlet limits**, not guessed industrial sensor readings.
Illustrative water enthalpy balances give **necessary minimum mass flows**
for assumed 5/10/15 K source cooling and 10/20/30 K sink heating. These
are not proof of HX UA, pinch, pressure drop, pump availability,
evaporator frosting, compressor oil compatibility or 310 kW thermal delivery.
A measured source/sink energy bound below the required duty is a negative
screen; a bound above it is necessary but not sufficient for feasible heat transfer.

A *real* feasibility decision must combine the model-specific compressor
map, refrigerant quality/speed limits, measured source/sink flow and
temperature bounds, finite UA/pinch and pressure losses. A source-energy
upper bound below required evaporator duty is a valid negative finding; a
large upper bound is **not** a positive equipment rating.

## 3. Independent equipment evidence gate — required fields

`ht_hp_controlbench/wp7_external_evidence.py::REQUIRED_ASSET_EVIDENCE`
enumerates fourteen asset-specific obligations:

- actual manufacturer/model/serial/configuration;
- model-specific approved refrigerant, motor, pressure/speed/discharge,
  lubricant and efficiency maps;
- OEM swept volume and heating-power map independent of the 310 kW target;
- finite source/sink flows, temperatures and allowable operating limits;
- evaporator, condenser and process HX thermal/hydraulic maps;
- motor/drive/auxiliary electrical metering;
- calibrated sensor metadata and environmental disturbance records;
- training and **time-disjoint** held-out observer datasets;
- pressure equipment ratings, relief/interlocks, applicable safety basis.

A link about a *different* compressor is ineligible even if R1233zd(E) is
common. A plausible number inferred from the assumed duty is not evidence.
The automatic gate is deliberately conservative: even when all reference
documents are supplied, it returns review required rather than automatically
granting regulatory/safety certification.

## 4. Independent observer validation — required acquisition protocol

The existing v2 numerical observer knows the initial `T_header` and actual
`n` once, predicts future hidden states using its property model and
corrects only `T_buffer` via noisy/delayed single-sensor samples. Its
≈0.014 K noiseless-model discrepancy is an **internal numerical cross-check**,
not an independent hardware error estimate.

For real validation acquire **from the same asset**, with synchronized clock:

1. **Control inputs**: actual applied compressor command and actual measured
   modulation/speed (not just setpoint), actuator deadband/slew/saturation,
   controller timestamps, measured source and return conditions.
2. **Measured output**: timestamped buffer temperature at the actual controller
   sensor location, including calibration, uncertainty, sample averaging and
   communication delay.
3. **Withheld reference states**: *independent* header temperature and actual
   compressor speed/modulation, collected for **post hoc** scoring only, and
   never passed to the property predictor during the validation rollout.
4. **Coverage**: steady and controlled excitations, ramp changes, ambient
   variation, realistic noise/delay, and safe high/low source limits, entirely
   inside verified OEM and process-service limits.
5. **Split and hold**: choose calibration/train and strictly nonoverlapping
   future holdout periods in advance, freeze the model and estimator before
   holdout, and report measured MAE, RMSE, signed bias, maximum error and
   confidence/uncertainty intervals.
6. **Evidence integrity**: preserve raw-file SHA-256, calibration documents,
   asset identity, operator permission, source of time synchronization and
   rejected/missing/censored intervals. Unknown or proprietary evidence
   is simply absent; never reconstruct fake measurement traces.

The code includes `observer_record_gate` to reject missing provenance,
timebase problems, target-asset mismatch, absent withheld channels and
train/held-out leakage. Even a complete metadata packet is
`INSTRUMENTED_TRACE_PRESENT__INDEPENDENT_REVIEW_REQUIRED`,
not an automatic empirical-validity certificate.

With **actual** matching-asset data, run
`python scripts/score_wp7_measured_observer.py --csv /secured/log.csv
--manifest /secured/manifest.json --output /secured/result.json`.
The runner checks the raw file SHA-256 and uses the nominal property
observer only with initial measured hidden states, subsequent buffer
temperature, prior applied commands and known source/return disturbances.
Later header/modulation measurements are **post-hoc scoring only**.
It computes held-out MAE/RMSE/bias/max-error but returns
`DESCRIPTIVE_MEASURED_HOLDOUT_RESIDUALS__INDEPENDENT_REVIEW_REQUIRED`
even with small errors. It refuses unaligned or unmodelled sensor latency.
See [the strict seven-channel data contract](WP7_INSTRUMENTED_OBSERVER_DATA_CONTRACT.md).
No matching real records are included in this project.

## 5. Reproduction / scope limits

```bash
python -m pip install -e '.[realfluid]'
python -m unittest discover -s tests -p 'test_wp7_external_evidence.py' -v
python scripts/run_wp7_external_empirical_audit.py
```

The default command checks the LIVE public Zenodo files and will fail if the
network rejects access or hashes change; use `--data-dir` with legitimately
downloaded, unchanged CC-BY CSVs to work offline. Both paths use the **same
checksum guard**.

Outputs: `results/wp7_external_empirical_evidence_v1.json`,
`results/wp7_external_empirical_evidence_v1.md` and
`results/wp7_external_empirical_source_counts_v1.csv`.

These outputs have a limited claim: **external empirical evidence screening
and explicit nonvalidation of the reference machine and real observer**.
They do not close issue #12's field-observer validation or issue #13's
equipment and finite-source/sink feasibility. They do not confer CE,
PED, F-gas, refrigerant compliance or permission to operate a real plant.

## 6. What would change the verdict?

Only authentic independent evidence for a *named target asset*: model-specific
manufacturer thermal/electrical/pressure/speed map, certified operating
envelope, source/sink instrumentation and finite-HX proof, plus separately
measured held-out dynamic input/output/hidden-state traces under real control.
The entire validation procedure must be rerun on those records, with source
hashes and independent review. A source from another test rig, a model-derived
sample or a manufacturer's family-level brochure cannot close this gate.
