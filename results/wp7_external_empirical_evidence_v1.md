# WP7 — independent empirical evidence and verification gate v1

**Current target system/equipment:** NOT VALIDATED. **Current independent
instrumented observer:** NOT VALIDATED. Nothing about this external
data transfers physical capacity, design pressure or controller safety to WP7.

## Source-provenance audit (actual checksum-verified raw CSVs)

- [Widmaier et al. 2026](https://zenodo.org/records/17599603), DOI `10.5281/zenodo.17599603`: **32,073 records**; **31,702** EN12900 manufacturer-model **generated** rows; **371** independent measured rows; only **22** measured pure R1233zd(E). Measured overall compressor η_is median **0.600** (range 0.302–0.678). **DO NOT interpret this as a calibrated WP7 compressor:** it is a different
machine and overall *electrical* efficiency is not the WP7 assumed internal η_is.

- [Leclercq experimental two-phase/oil scroll](https://zenodo.org/records/20445833), DOI `10.5281/zenodo.20445833`: **67** independent R1233zd(E) measured records; reported η_is median **0.559** (range 0.342–0.783). This is two-phase/oil compressor research, **out of scope** for direct
validation of WP7's dry-vapor reference cycle.

Both source raw-file MD5 checksums must match Zenodo's published metadata.
The report includes their SHA-256 digests and versioned DOIs; no source
rows are copied into the repository. License CC BY 4.0; give attribution.

## Reference model: conditional arithmetic, not measured equipment

- Nominal condenser request: **310.0 kW**; predicted ideal EOS COP **2.511**.
- Ideal compressor power without auxiliary/motor losses: **123.47 kW**.
- Ideal evaporator thermal input: **186.53 kW**.
- Compressor equivalent full-speed displacement **0.20423 m³/s** **IMPLIED FROM OUTPUT, NOT OEM MEASURED**.
- Illustrative heat-source mass-flow minimums assume water at
4200 J/(kg K) and a completely usable heat-source temperature drop;
**no pinch/UA, hydraulic or fluid compatibility check exists**:

| Assumed available source drop | Ideal necessary source flow |
|---:|---:|
| 5 K | 8.882 kg/s |
| 10 K | 4.441 kg/s |
| 15 K | 2.961 kg/s |

The separate heat-sink capacity screen is also **UNVERIFIED**.
Illustrative water-based required condenser-side flows are only
necessary enthalpy arithmetic (not measured or pressure/HX qualified):

| Assumed available sink temperature rise | Ideal necessary sink flow |
|---:|---:|
| 10 K | 7.381 kg/s |
| 20 K | 3.690 kg/s |
| 30 K | 2.460 kg/s |

## What blocks actual equipment and observer acceptance

- **14/14 required asset-matched evidence sections missing**: no nominated OEM compressor,
independent efficiency/displacement/pressure envelope, source/sink mass
flow and heat-exchanger capacities, instrument calibration, safety basis.
- Independent source **and sink** flows were **not supplied**, so the necessary
energy bound itself is UNVERIFIED, despite the illustrative flow table.
- No independent, time-aligned HEADER-temperature and ACTUAL modulation
trace from a configured matching HTHP; v2 observer validation currently
tests two numerical formulations sharing assumptions, not measured truth.
- Independent datasets at other scales/topologies test external
plausibility and limitations; they cannot prove 310 kW at 133C.
- The [Bayreuth 37 kW R1233zd(E) HTHP dataset](https://data.mendeley.com/datasets/56m3dd55zf/1)
is a promising full-cycle *external* test set, but its downloadable
files were **not obtained** through the public API (401). It is listed
as NOT_INGESTED, not as a computed validation.
- BITZER CSH2T documents useful heat output up to **120C**, not the
higher hypothetical 133C reference. That family cannot serve as
the missing model-specific 133C certification without further OEM evidence.

## Actionable external-data requests

1. Identify the actual or proposed **manufacturer model, serial/configuration,
   refrigerant/oil and VSD speed limits** with signed datasheet and Q/P map.
2. Obtain continuous measured evaporator-side source and sink flow,
   temperatures, pressures, HX design/UA, pinch and permissible temperature drops.
3. Acquire a separate excitation/validation time series with timestamped
   applied command, actual compressor modulation and independently
   measured header/buffer/source/return temperatures, including calibration
   certificates and uncertainties.
4. Predeclare held-out conditions, validate time alignment and sensor delay;
   compute estimator residuals using the **unmodified frozen model**.
5. Add reviewed pressure-equipment compliance and industrial safety evidence;
   numerical EOS feasibility is never equivalent to a certified asset.

Reproduce against the original public files without network:
`python scripts/run_wp7_external_empirical_audit.py --data-dir /path/to/verified/csvs`.
For live original downloads use:
`python scripts/run_wp7_external_empirical_audit.py`.
Requires CoolProp for the separate *assumed-model arithmetic*; CSV parsing uses stdlib.

Evidence integrity is enforced in `tests/test_wp7_external_evidence.py`.
