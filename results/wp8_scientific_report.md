# WP8 — Storage and tariff flexibility (synthetic, equipment unverified)

## Thermodynamic and scope gates

- CoolProp 8.0.0, R1233zd(E), nominal source 60°C, 6 bar(a) assumed water loop.
- Finite process HX service threshold is **128.38°C**, not 120°C.
- Storage enthalpy uses IF97 h(T,p); every counted cost benefit requires 100% specification service,
  no declared property/rating constraint failure, and final inventory agreement within 0.5 kWh.
- Compressor electrical power depends on water-header temperature through the WP7 property map;
  high-temperature precharge may **increase total electricity** even if a synthetic tariff bill decreases.

## 24-h reference comparison

- Outcome: **conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED**; reasons: [].
- Baseline electricity: **2963.322 kWh**; scheduled: **2983.862 kWh**.
- Baseline synthetic cost: **€456.845**; scheduled: **€456.739**.
- Additional scheduled electricity versus baseline: **20.539 kWh** (positive means more kWh) if both runs completed.
- Conditionally creditable saving: **0.10674507003642475 EUR**, if eligible; otherwise NONE.
- Neither a reduced bill nor an acceptable service fraction constitutes an *actual industrial* saving.

## Disclosed scenarios

| Case | Status | Eligible simulated saving (EUR) | Service fraction (schedule) | Note |
|---|---|---:|---:|---|
| reference_15min_event | conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED | 0.107 | 1.0000 | conditional only |
| small_buffer_2500kg | conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED | -0.459 | 1.0000 | conditional only |
| large_buffer_10000kg | conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED | 0.989 | 1.0000 | conditional only |
| long_peak_45min | conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED | 1.836 | 1.0000 | conditional only |
| flat_tariff | cost_saving_not_creditable | — | 1.0000 | no_strict_high_low_price_spread |
| hypothetical_ratings_24bar_145C | cost_saving_not_creditable | — | 0.1812 | simulation_or_envelope_failed;process_service_failed;terminal_storage_inventory_mismatch |
| cold_source_55C | conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED | -0.021 | 1.0000 | conditional only |

## Storage sensitivity

| Mass (kg) | Constraint gate | Conditional inventory (kWh) | Reachability |
|---:|---|---:|---|
| 2500 | EOS_only__NO_OEM | 19.549 | conditional_full_path__EQUIPMENT_UNVERIFIED:  |
| 2500 | hypothetical_24bar_145C | 7.812 | path_blocked: hypothetical_equipment_limit_exceeded |
| 5000 | EOS_only__NO_OEM | 39.099 | conditional_full_path__EQUIPMENT_UNVERIFIED:  |
| 5000 | hypothetical_24bar_145C | 15.625 | path_blocked: hypothetical_equipment_limit_exceeded |
| 10000 | EOS_only__NO_OEM | 78.197 | conditional_full_path__EQUIPMENT_UNVERIFIED:  |
| 10000 | hypothetical_24bar_145C | 31.249 | path_blocked: hypothetical_equipment_limit_exceeded |

## Scientific interpretation

- An *unlimited-rating conditional model* and a *hypothetically capped scenario* are not evidence of actual equipment reachability.
- There is no demonstrated equipment-verified electricity-price arbitrage without a manufacturer capacity and pressure/discharge map.
- Small buffer energy relative to 300 kW process heat restricts the peak event length; larger tanks can help only with finite recharge capacity.
- A flat price or a long service-failing peak is a falsification control; no monetary saving is credited.
- The scheduled PI policy uses advance knowledge of synthetic tariff events and must not be relabelled SOC.

### External scientific provenance

- IAPWS IF97 revised industrial water formulation: https://iapws.org/technical-guidance/release/IF97-Rev
- CoolProp 8.0 IF97 backend: https://coolprop.org/fluid_properties/IF97.html
- Previous WP7 physical-service, CoolProp compressor and TESPy offdesign results: docs/WP7_RESEARCH_CLOSEOUT.md

### Reproduction

`python scripts/run_wp8.py --full` (requires `pip install -e ".[plots,realfluid]"`).
Generated figures: `results/wp8_buffer_trace.png`, `results/wp8_cost_comparison.png`, and `results/wp8_scenario_savings.png`.
