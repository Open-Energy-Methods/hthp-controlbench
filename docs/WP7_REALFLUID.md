# WP7 — Real-fluid thermodynamic anchor and guarded offdesign map

**Scope:** Refrigerant property calculations with CoolProp HEOS, water pressure/enthalpy with CoolProp IF97 and a parallel HEOS saturation check. This is a first-principles **four-state steady-state cycle screen** plus a separately solved TESPy component network using the **same CoolProp EOS**. Neither is calibrated equipment or a dynamic refrigerant twin. WP2–WP6 remain intentionally unchanged.

## Questions and evidence levels

1. Is the baseline 60 °C bulk heat source / 133.05 °C hot-header target within the **subcritical** saturation and EOS operating range of any chosen candidate fluid?
2. What are the refrigerant saturation pressures, compressor discharge temperature, suction vapour density, idealised cycle COP, and *implied* nominal mass flow at an assumed 310 kW condenser duty?
3. Which portions of a declared source/header temperature grid pass the same constraints without extrapolation?
4. Can an imposed, non-validated constant-volumetric-flow relation construct a property-dependent capacity/power map? What are its held-out interpolation errors?
5. Is assumed 6 bar(a) hot water in the compressed-liquid region, and what conditional inventory follows from the full IF97 enthalpy difference?

**Evidence tags:** `property-calculated` (CoolProp EOS and IF97); `synthetic` (compressor efficiency, superheat, subcooling, imposed reference duty, hypothetical 6 bar loop); `cross-backend water-only` (IF97 versus HEOS); **no** `equipment calibrated`, `manufacturer validated`, `experimental`, `certified`, or `independently validated EOS` claims. The TESPy network is a component-equation cross-check, not an independent property model.

## Modelling boundary and thermodynamic equations

Four-point single-stage **subcritical** vapour-compression cycle, refrigerant without line pressure losses or auxiliary components. Heat transfer at *refrigerant saturation* conditions is deliberately separated from bulk source and loop temperature:

- `T_evap = T_source,bulk − 5 K`; `T_cond = T_header + 5 K`; default refrigerant-side approach temperatures are **assumptions**.
- At point 1, suction vapour: `p1=p_sat(T_evap)`, `T1=T_evap+5 K`, with `h1`, `s1`, `rho1` from the actual CoolProp EOS.
- Condensing pressure `p2=p_sat(T_cond)`; ideal isentropic compressor discharge `h2s=h(p2,s1)`; actual `h2=h1+(h2s−h1)/eta_is`, with assumed `eta_is=0.75`.
- Condenser exit saturated-side compressed liquid at `p2`, `T3=T_cond−4 K`, `h3=h(p2,T3)`.
- Expansion isenthalpic: `h4=h3`. At `p1`, outlet quality must lie in `[0,1]` or the state is rejected for this topology.
- Specific compressor energy `w=h2−h1`; condenser specific heat `q_cond=h2−h3`; evaporator specific heat `q_ev=h1−h3`; energy test `q_cond = w+q_ev`.
- `COP_heating=q_cond/w` must satisfy `1<COP≤T_cond/(T_cond−T_evap)`. This compares against the **refrigerant-side** Carnot limit, not reservoir Carnot. Volumetric condenser heating capacity at compressor suction is `rho1*q_cond` (J/m³), a thermophysical metric, not manufacturer-rated displacement.

Tcrit, Tmax, Tmin, saturation pressures, discharge temperature, **discharge saturated-vapor enthalpy at condensing pressure**, and permitted throttle quality are queried from CoolProp, not hardcoded. A voluntary `T_cond ≤ Tcrit−5 K` property-screening guard is applied. It is **not** a refrigerant manufacturer's safe design envelope. A `P,H` discharge-temperature flash **alone** cannot identify a wet compressor discharge: the explicit guard requires `h2 > h_sat,vapor(p2)+1 J/kg` to exclude liquid-vapour mixtures. The model rejects absent EOS states, invalid phase, zero/negative work or heat, and attempts to treat transcritical CO₂ as a subcritical drop-in.

### Investigated fluids

| Fluid identifier | Model expectation at 138.05°C condensing saturation | Design conclusion |
|---|---|---|
| `R1233zd(E)` | Subcritical *candidate*, subject to discharge state and EOS maximum temperature | Property-calculated screen only |
| `R1336mzz(Z)` | Subcritical *candidate*; different isomer from `R1336mzz(E)` | Property-calculated screen only |
| `R134a` | Critical temperature below needed condensing temperature | Reject ordinary subcritical topology |
| `Ammonia` | Critical temperature below needed condensing temperature | Reject ordinary subcritical topology at this target |
| `CarbonDioxide` | Requires a different transcritical gas-cooler topology | Explicitly not modelled or substituted |

Do not equate a property-library PASS with acceptable discharge temperatures, compressor displacement, pressure equipment rating, refrigerant safety class, oil/chemical compatibility, lifetime, availability or legal approval. None of those have been established.

## Water and conditional thermal inventory

IF97 pressure at the saturated liquid boundary `p_sat(T_header)` is queried directly. At assumed `p_loop=600,000 Pa abs`, the *numerical screen* requires `p_loop > 1.15*p_sat(T_hot)`. The actual system design margin is **not** established. Same-temperature HEOS water saturation is calculated separately, with the relative difference recorded.

For 5000 kg of water at the assumed pressure, conditional inventory is

`E_hypothetical = 5000 kg × (h_IF97(135°C,6 bar) − h_IF97(128.38°C,6 bar)) / 3.6e6` kWh.

The 135 °C top state has **not** been proven reachable by an actual compressor in service, and the lower state remains HX/flow-dependent. Report this as *conditional enthalpy arithmetic only*, not usable shifting/storage capacity. WP8 must enforce charge power, recharge duration, service quality, water pressure limits and actual achievable upper temperature.

## Offdesign property-anchored-but-uncalibrated map

For each fluid that passes the reference point and all grid points:

- Source bulk temperatures: 55, 60, 65 °C.
- Hot header temperatures: 130, 133.05, 140 °C.
- Normalised compressor modulation: `n ∈ {0.5, 0.75, 1.0}`.
- Assume 310 kW condenser heat at `n_ref=0.75`, `T_source=60 °C`, `T_header=133.05 °C` **by definition**, not by manufacturer testing.
- Set `m_dot_ref = 310 kW/q_cond,ref`, infer `Vdot_equivalent_full = m_dot_ref/(rho_suction,ref*n_ref)`.
- For other states use **assumed** constant equivalent volumetric flow per unit modulation `m_dot=Vdot_equivalent_full × n × rho_suction(T_source,T_header)`.
- Build `Q_cond(n,T_source,T_header)` and `P_comp(n,T_source,T_header)` as **joint property-calculated arrays**; the original legacy synthetic COP/heat-output map is not changed.
- Interpolate only inside strictly increasing sampled axes and only after every grid corner passes validity. No extrapolation is permitted. Four withheld interior triplets quantify interpolation residuals against fresh property calls, not field measurements.

The derived displacement is not swept volume, isentropic efficiency is not a measured function of lift or speed, pressure losses are omitted, and the control plant has **not** been rerun using these maps. A successful mapping exercise does not certify the WP4 MPC controller or WP6 SOC ranking for a real refrigerant.

## Uncertainty / negative tests

The script separately scans assumed `eta_is` values 0.65, 0.75, 0.85 and condenser approach 5, 8 K, preserving rejected combinations. These are sensitivity bounds, **not** identified compressor parameter distributions. A property state that fails is never replaced by an extrapolated COP, assumed constant heat, or a universal 'second-law efficiency'.

Main tests cover enthalpy/energy balance, subcritical critical-temperature guard, phase quality, EOS maximum, water IF97/HEOS consistency, map bounds and withheld interpolation. Structural tests run with an explicitly fake property backend when CoolProp is missing, while *real-CoolProp tests must run in CI*. The experiment script **fails closed** if CoolProp is unavailable or no refrigerant permits a complete reference map.

## Reproduce / provenance

```bash
python -m pip install -e '.[realfluid,plots,qp]'
python -m unittest discover -s tests -v
python scripts/run_wp7.py
```

The GitHub workflow uses all three supported Python versions to run CoolProp WP7; TESPy cross-check runs on Python 3.11 and 3.12, since TESPy 0.11 requires >=3.11. The 3.12 run also publishes a downloadable **WP7 real-fluid artifact**. Generated files: `results/wp7_nominal_fluid_screen.csv`, `wp7_envelope.csv`, `wp7_water_if97.csv`, `wp7_map_reference.csv`, `wp7_map_holdout.csv`, `wp7_efficiency_approach_sensitivity.csv`, `wp7_synthetic_vs_cycle.csv`, `wp7_summary.json`, `wp7_scientific_report.md`, and `wp7_cop_temperature.png` (when matplotlib installed).

**Additional WP7 verification:** a TESPy component-network design solve is provided at three matched reference states, and must pass a 2% same-model discrepancy gate in CI. This independently solves network equations but **shares CoolProp thermophysical data** and does not establish manufacturer-calibrated TESPy offdesign.

**Not completed by this initial implementation:** TESPy manufacturer-based design/offdesign characteristics, machine-specific compressor specification/efficiency maps, refrigerant lifecycle and code compliance, measured thermodynamic/flow calibration, physically constrained compressor-coupled dynamic controller reruns, manufacturer-validated 135 °C charging margin. WP7 **must not be called fully equipment-validated** until these are completed.

## Published sources and checking scope

- CoolProp [high-level properties API](https://coolprop.org/coolprop/HighLevelAPI.html), including saturation-quality and state identifiers.
- CoolProp [water IF97 documentation](https://coolprop.org/fluid_properties/IF97.html); water HEOS uses the distinct IAPWS-95-based EOS.
- CoolProp [R1233zd(E) EOS and range](https://coolprop.org/fluid_properties/fluids/R1233zd%28E%29.html) and [R1336mzz(Z) EOS and range](https://coolprop.github.io/devdocs/fluid_properties/fluids/R1336mzz%28Z%29.html).
- [TESPy heat-pump design and part-load tutorial](https://tespy.readthedocs.io/en/main/model_library/heat_pump_partload.html): shows how manufacturer compressor maps and offdesign HX scaling should ultimately be anchored. The component-network cross-check now runs separately on Python 3.11 and 3.12; it is not a manufacturer-based offdesign simulation.
- Frozen research specification: `docs/RESEARCH_PLAN_v0.5.md` §4.5, WP7 acceptance matrix.

All numeric equipment choices in this stage remain hypothetical unless explicitly supported by a tested property EOS.
