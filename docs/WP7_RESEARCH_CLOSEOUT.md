# WP7 research closeout — thermodynamic feasibility with explicit equipment limits

## Decision and evidence boundary

**Research status:** first numerical thermodynamic research closure, **not** industrial equipment validation. WP7 offers two independent physical *equation implementations* (direct CoolProp cycle and TESPy network with the **same EOS**), water IF97 calculations, an operating-state rejection screen, a conditional storage-charge calculation, and a pilot dynamic plant using the real-fluid-derived Q/P map. The isolated scientific outputs are reproducible in CI; the older synthetic controller rankings remain unmodified.

The only property-cycle-pass candidate at the explicitly tested reference is **R1233zd(E)**. This is not a commercial refrigerant selection or assurance of compressor/pressure equipment compatibility. The original full-property screen rejects R1336mzz(Z) because the model predicts insufficiently superheated compressor discharge, rejects R134a and ammonia for a critical-temperature/subcritical-topology violation, and refuses to assess CO₂ with an inappropriate subcritical condenser. A different architecture or operating point could yield different eligibility.

## Scientific inputs versus assumptions

| Item | Source / status |
|---|---|
| Saturation, enthalpy, density, isentropic compression | **CoolProp HEOS**, 8.x; property-based calculated |
| Water h(T,p), saturation margin | **CoolProp IF97** and an HEOS water crosscheck |
| Compressor efficiency at design | **0.75 assumed**; no measured map |
| Reference heating capacity and modulation | **310 kW, n=0.75 imposed**; equivalent volume flow inferred by algebra, not measured |
| Source and header approaches, superheat/subcooling | 5/5/5/4 K **assumed** |
| HP, thermal-buffer and HX dynamics | WP2 declared synthetic geometry and UA; **not calibrated** |
| Water-loop pressure | **6 bar absolute assumed**, not a rated system design pressure |
| Max condenser pressure, discharge temperature, pressure ratio | **UNKNOWN** unless hypothetical thresholds are explicitly provided; never classified as OEM-approved |
| TESPy compressor η(m/m_design) characteristic | Synthetic illustrative points `(0.5,0.88),(0.75,0.97),(1,1),(1.25,0.985)`; **not manufacturer data** |

## Core equations and implementation

1. The subcritical refrigerant cycle uses `h2=h1+(h2s−h1)/eta_is`, `q_cond=h2−h3`, `w=h2−h1`, `q_evap=h1−h3`, `COP=q_cond/w`, and requires explicit dry discharge, physically possible refrigerant Carnot bound, positive duties and conservation `q_cond=w+q_evap`.
2. For fixed buffer temperature `T_b` and process return, the WP2 process-side finite-HX calculation determines the physically transferred process duty `Q_proc`. To hold the buffer at steady state: `Q_hb=Q_proc+UA_b(T_b−T_amb)`, `T_h=T_b+Q_hb/K_hb`, `Q_HP,required=Q_hb+UA_h(T_h−T_amb)`. Process qualification remains separate and must be true before any result counts as *same service*.
3. Required compressor modulation comes from a **property-derived, assumed full-speed equivalent suction flow**, `Q_HP(n,T_s,T_h)=n*Vdot_full*rho_1(T_s,T_h)*(h2−h3)`. Values outside the declared three-axis map or above full modulation are rejected, not extrapolated.
4. The non-calibrated **max-speed** buffer charge screen finds the quasi-steady header `Q_HP(n=1,T_h)=K_hb(T_h−T_b)+UA_h(T_h−T_amb)` inside the declared map bounds. The water enthalpy inventory is `E=m*[h_IF97(T_high,p)−h_IF97(T_low,p)]`; the approximate optimistic time is `∫m dh_IF97 / [K_hb(T_h−T_b)−Q_proc−UA_b(T_b−T_amb)]`. Any loss of process service, nonpositive charge surplus, limit violation or absent root blocks the path. This is **not a measured or guaranteed minimum charge time**, because the header thermal inertia, compressor start/ramp, water stratification, hydraulic design, auxiliary power and control imperfections are omitted.
5. A separate **dynamic pilot** uses WP2 thermal conductances and actuator lag, but replaces compressor output/electricity with a bounded CoolProp-derived joint Q/P map; the buffer state is **IF97 specific enthalpy**, so its energy balance does not approximate `m*4200 J/kg/K` over the full cycle. Existing WP3 PI gains are frozen, not retuned; out-of-grid dynamic states fail closed and are reported instead of clipped.
6. A genuine TESPy design→offdesign experiment saves the design state and invokes `Network.solve('offdesign',design_path=...)` with altered refrigerant mass flow and declared synthetic compressor η(m/m_design). All network points are checked against independent direct-cycle code using the **same CoolProp EOS**. This is **not** a manufacturer compressor characteristic, independently measured properties or a heat-exchanger UA calibration.

## Scientific acceptance / blockers

The following tests must pass in CI: property-COP/phase/saturation guards; stable storage enthalpy and energy conservation; actual HX service gate; hypothetical pressure/discharge limits; no map extrapolation; full dynamic-enthalpy energy closure; TESPy offdesign re-solves; traceable CoolProp and TESPy versions; and deterministic regeneration of `results/wp7_*` files. No favorable numeric result can substitute for missing rated machine specifications.

**Remaining external evidence** (cannot be honestly manufactured in this repository): manufacturer compressor displacement, measured efficiency/speed envelope, maximum discharge temperature/pressure, refrigerant/oil compatibility, HX pressure-loss and UA data, pump and auxiliary power, pressure-vessel design review, safety/regulatory approval, measured 310 kW output and buffer charging. Likewise, the complete WP4 PI/MPC/SOC study has **not** been rerun under a manufacturer-calibrated fluid plant. Those remain separate validation gates beyond the numerical WP7 closeout.

## Reproduce and evidence links

```bash
python -m pip install -e '.[plots,qp,realfluid,tespy]'
python -m unittest discover -s tests -v
python scripts/run_wp7.py
python scripts/run_wp7_tespy.py
python scripts/run_wp7_completion.py
```

Output files include `wp7_system_service_screen.csv`, `wp7_charge_profile.csv` (when charge feasible under assumptions), `wp7_realfluid_PI_pilot.csv`, `wp7_actual_TESPy_offdesign.csv`, `wp7_completion_summary.json`, and `wp7_completion_report.md`. GitHub Actions generates all outputs on its 3.12 runner, records the tool versions, and fails the pipeline on unhandled property or network discrepancies.

- [CoolProp High-Level API / phase and saturation](https://coolprop.org/coolprop/HighLevelAPI.html)
- [CoolProp IF97 water backend](https://coolprop.org/fluid_properties/IF97.html)
- [CoolProp R1233zd(E) EOS and original reference](https://coolprop.org/fluid_properties/fluids/R1233zd%28E%29.html)
- [TESPy network design/offdesign semantics](https://tespy.readthedocs.io/en/stable/building_blocks/networks.html)
- [TESPy compressor characteristic line](https://tespy.readthedocs.io/en/stable/building_blocks/components.html)

**Final scientific classification:** WP7 is complete only as a **reproducible numerical thermodynamic research work package with conditional assumptions and explicit negative/uncertain results**, not as an experimentally validated high-temperature heat-pump machine.
