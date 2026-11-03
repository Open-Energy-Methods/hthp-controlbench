# WP7 — Numerical thermodynamic research closeout

> **Status: numerical research completed under assumptions; equipment feasibility UNVERIFIED.**

This is a separate property-backed model; WP2–WP6 plant and published controller rankings are unchanged.

## Nominal same-service closure

- Process qualification: **True** at buffer 130.00 °C.
- Actual heat delivered to process: **300.000 kW**; compressor condenser duty required **310.000 kW**.
- Implied reference compressor command: **0.75000**, with no manufacturer envelope established.
- Calculated cycle compressor electricity at this operating point: **123.472 kW** (no motor/auxiliary losses).
- Condensing pressure **22.189 bar(a)**; discharge **142.88 °C**; these are NOT rated limits.

## Water buffer charging

- No-OEM-limits scenario: **conditional_quasisteady_charge_path__EQUIPMENT_UNVERIFIED**.
- Hypothetical pressure/discharge cap scenario (24 bar(a), 145°C): **blocked_or_unverified**.
- Under optimistic quasisteady assumptions, 39.118 kWh enthalpy from 128.40 to 135°C at 6 bar(a) requires **25.9 min**.
- Charge-surplus range 76.6–105.8 kW, still *not a device charging-time estimate*.

## TESPy genuine design → offdesign

TESPy saved one nominal design state and solved three offdesign mass-flow points via a declared, artificial efficiency characteristic. It uses CoolProp internally and is **not** a manufacturer-calibrated compressor map.

| Mass ratio | Assumed efficiency | TESPy COP | Direct same-EOS COP |
|---|---:|---:|---:|
| 0.75 | 0.7275 | 2.46537 | 2.46537 |
| 1.00 | 0.7500 | 2.51069 | 2.51069 |
| 1.10 | 0.7455 | 2.50163 | 2.50163 |

## Real-fluid PI dynamic pilot

Original WP3 PI gains were **frozen**, while the simulated plant uses a CoolProp-dependent Q/P map and integrates water specific enthalpy. A pilot is not a full repeated WP4 MPC study.

| Controller | Status | IAE (K·s) | Electric (kWh) | Process service fraction | Energy residual J |
|---|---|---:|---:|---:|---:|
| FOPDT_IMC_lambda_0p5tau | completed | 1707.3 | 242.706 | 1.000 | 4.47e-06 |
| Relay_TyreusLuyben | completed | 347.0 | 244.936 | 1.000 | 3.86e-07 |

## Hard scientific limits

The reference displacement is **inferred by forcing 310 kW at 75% modulation**. Neither its capacity nor its efficiency is measured. The 6 bar water pressure is an assumption, not an equipment rating. A CoolProp state PASS cannot certify pressure equipment, compressor thermal survival, refrigerant/oil suitability or chargeability.

The charging path assumes an infinitely fast header thermal equilibration, no rate ramp and no stratification, making its time an **illustrative optimistic model output**, not an operational claim. Failure under hypothetical limits is a sensitivity result, not evidence about any existing compressor.

System dynamic controller comparisons are pilot sensitivity checks, NOT proof of superiority of PI, MPC or SOC with a real fluid.

Sources: CoolProp high-level API, IF97 documentation and R1233zd(E) EOS; TESPy network/design-offdesign documentation. Exact links and versions in `wp7_completion_summary.json`.

Final classification: **WP7 research-software closure achieved; manufacturer/hardware verification open external dependency.**
