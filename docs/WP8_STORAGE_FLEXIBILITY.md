# WP8 — Finite thermal storage and price flexibility: implementation and scientific protocol

**Status:** Simulation-only, evidence-conditional, **not an OEM equipment or financial validation**. This WP8 model is explicitly distinct from the frozen WP2–WP6 experiment baselines and depends on the uncalibrated WP7 R1233zd(E) CoolProp map.

## Research question and hypotheses

**RQ:** Does a finite, service-temperature-qualified and theoretically reachable high-temperature water buffer enable material electricity-cost shifting, compared with a fixed, well-tuned PI baseline, once the heat pump's performance changes with operating temperature and all service, actuator and recharge limits are enforced?

- H8.1: nominal enthalpy inventory is *not* automatically dispatchable usable storage; finite heat exchanger flow and heat-pump reachability are limiting constraints.
- H8.2: A tariff-scheduled PI heuristic may reduce a conditional bill at a synthetic high-price event, even while **increasing total compressor kWh** due to hotter charging and storage losses.
- H8.3: restrictive physical/equipment envelopes and longer price events can make arbitrage **infeasible**. Such cases must be recorded as rejections, not cheaper controller operations.

## Shared physical model and strict scopes

The WP8 dynamic model has three physical states: a finite-temperature header `T_h` (WP2 `C_h=5 MJ/K`), well-mixed **water specific enthalpy** `h_b(T_b, p_b)` representing `m_b` kg water (nominal 5000 kg), and actual compressor modulation `n`, with the same 90 s lag and command slew bound as WP3.

The independent dynamic conservation equations are:

\[
C_h\,dT_h/dt = Q_{HP}(n,T_{src},T_h) - K_{hb}(T_h-T_b) - UA_h(T_h-T_a)
\]
\[
m_b\,dh_b/dt = K_{hb}(T_h-T_b) - Q_{process,transferred}(T_b) - UA_b(T_b-T_a)
\]
\[
\tau_n\,dn/dt = n_{command} - n.
\]

**Critical**: *physically transferred* process heat goes into the storage balance even when service is unqualified; `Q_spec_qualified` is reporting only. The process temperature is obtained from the actual finite-flow counterflow ε–NTU exchanger and duty-limiter; output must meet `120°C`. The **minimum buffer** is solved from the finite exchanger, around 128.38°C at nominal assumptions; it is not 120°C. Saturated-water pressure and h(T,p) use CoolProp `IF97::Water` at a provisional **6 bar absolute**. This is not mechanical pressure-system acceptance.

Compressor `(Q_HP,P_el)` comes from WP7's interpolated CoolProp-based cycle map for a **synthetically sized** 310 kW point at `n=0.75`. The model must not extrapolate beyond declared speed `[0.5,1]`, source `[55,65]°C`, and header `[130,140]°C` grids. Each RK4 step checks the water liquid condition. Declared hypothetical pressure/discharge caps are separately enforced using real-fluid EOS states. Their numerical values are **thought experiments, not manufacturer ratings**.

### Storage inventory versus actual flexible service

Potential nominal enthalpy above service threshold:

\[
E_{inventory}=m_b\,[h_w(T_{upper},p_b)-h_w(T_{min,service},p_b)]
\]

This inventory is credited **only conditionally** when an entire sampled `n=1` charge path has positive surplus while satisfying the process outlet threshold, grid, and water-phase gates. A verified reachable upper temperature additionally needs OEM pressure/temperature/displacement/efficiency curves: **none are provided**. The `scan_reachable_band` output is thus `conditional_full_path__EQUIPMENT_UNVERIFIED`, or `path_blocked` with the exact first failed sample. Sampled scanning is a screening approximation, not a mathematical proof of feasibility between all points. The 'E/300 kW' time is a naive *full-load* upper bound before heat-pump contribution, losses and ramp effects; it is **not** a rated discharge autonomy.

An illustrative second scenario applies **invented** 24 bar(a) condenser pressure and 145°C discharge-temperature limits to expose cases where the EOS calculations remain valid but the hypothesized machine cannot charge. This limit scenario is not a real machine and must **not** be described as manufacturer validation.

## 24-h experiment and comparator

Fixed process duty: 300 kW, process return 90°C and minimum process supply 120°C, 60°C source, 20°C ambient. Fixed-reference comparator: the original WP3 IMC-0.5τ PI controller gains (`Kp=0.03842421356 1/K`, `Ki=1.23872086e-5 1/(K s)`), adapted to the WP7 thermal plant **without retuning**. Fixed buffer setpoint 130°C.

The alternative uses the **same PI controller** with only a transparent tariff-scheduled buffer setpoint: 134°C from 04:00–06:00 for precharging, 128.8°C from 06:00–06:15 for drawing down thermal headroom, then 130°C for the remainder. This alternative has *advance perfect knowledge of the synthetic event start/end*; it is a **heuristic**, **not** SOC, economic MPC or a forecast-uncertainty claim. Both policies use the same initial buffer state and compressor initial equilibrium, same 120 s controller sampling, **0.05 modulation command change per control update**, finite compressor lag, thermal masses, heat pump, heat losses and process duty. Actual initial command is determined from the WP7 service balance rather than the synthetic WP2 capacity map.

Synthetic energy-only price sequence: `0.16 EUR/kWh` during 00:00–04:00, `0.06` during 04:00–06:00, `0.40` during 06:00–06:15, and `0.16` until 24:00. This is not an actual Swedish or Norwegian spot price or total industrial electricity tariff. Electricity cost integrates **actual electrical power** at every numerical step:

\[
C=\sum_k p_k\,\frac{\int_{t_k}^{t_{k+1}} P_{el}(t)dt}{3.6\times10^6}
\]

Prices must align with the integration time grid. 24 h is used to allow the terminal buffer enthalpy to return to reference; this is a chosen protocol, not a basis for claiming annual value. The constant price and long-peak tests are **negative controls**.

## Exact cost-credit gates

`compare_flexibility()` returns a conditional model saving **only** when ALL of the following hold:

1. Both 24-h nonlinear runs completed without grid, phase or declared-equipment-limit violation;
2. Each physical process sample met the supply-temperature requirement (`service_qualified_fraction=1`), and `spec_unserved_kwh <=1e-7`;
3. Terminal enthalpy inventories of the policies differ by at most **0.5 kWh**; a smaller energy bill obtained by emptying the tank is never credited;
4. The declared high price is strictly above the low price; a flat price cannot be counted as tariff arbitrage.

Partial-run cost and electricity differences are **null rather than falsely subtracting unequal durations**. Failed runs, partial service, source/EOS interpolation failures or terminal mismatches produce `cost_saving_not_creditable` and `eligible_cost_saving_eur=null`; the raw cost and kWh deltas remain visible for diagnosis but may **not** be presented as savings. Even an eligible saving is explicitly named **`conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED`**, never real equipment acceptance. The absence of measured prices, taxes, OEM maps and hard hardware limits prohibits real financial conclusions.

## Planned sensitivity matrix and possible negative results

The reproducible script includes nominal 5000 kg; 2500 kg and 10000 kg; a 45-minute high-price event (instead of 15 minutes); flat tariff; hypothetical equipment limits; and a cooler 55°C source. All cases retain the same controller gains and model. It reports performance, service, and failed-case ledgers, not just winning percentages. A bigger buffer stores more conditional enthalpy but may be impossible to charge fully in the available two-hour window. A smaller buffer can deplete quickly. A flat tariff can still alter electricity consumption via COP; that is not **price arbitrage**.

If the nominal *uncapped* cycle gives a positive eligible saving, it is still **conditional on synthetic compressor sizing and thermodynamics**. If the hypothetical cap blocks charging, the correct conclusion is **zero verified flexible value** in that cap scenario. There is no manufactured annualized saving, NPV or payback without capital cost, life-cycle cycling or a valid electricity price series.

## Verification strategy

- Pure structural tests inject **explicitly fake** analytic properties to test IF97 enthalpy scaling, slew, full-day physical balance, tariff accounting, refusal of credit for service failure and zero credit under flat prices. These outputs are never published as real-fluid research numbers.
- GitHub CI installs CoolProp to test actual refrigerant and water properties, then regenerates full scenario CSV/JSON and figures on Python 3.12. A clean CI checkout must not silently use a fake cycle when CoolProp is absent.
- Compare energy-balance residual at end of every dynamic run: `C_h ΔT_h + m_b Δh_b = ∫(Q_HP − Q_process,transferred − Q_loss,h − Q_loss,b) dt`.
- Verify nominal dynamic results and report *all* rejections. Grid/saturation limits are model constraints but not equipment certification.
- Preserve old WP2–WP7 numerical experiments and tests.

### Research provenance

- WP7 research closeout: `docs/WP7_RESEARCH_CLOSEOUT.md`, `ht_hp_controlbench/thermo_feasibility.py`, `ht_hp_controlbench/realfluid.py`.
- Primary IAPWS water-property release: https://iapws.org/technical-guidance/release/IF97-Rev
- CoolProp IF97 backend: https://coolprop.org/fluid_properties/IF97.html
- All sensitivities synthetic; no imported real-time power-market prices or undocumented manufacturer data.

**Closure boundary:** WP8 provides reproducible scientific evidence of when thermal flexibility is possible *under assumed plant parameters* and why it may be valueless under more restrictive envelopes. Equipment validation, full dynamic refrigerant transients and market-based commercial conclusions remain future external-data requirements.


### Truncated simulation accounting

The reported `service_qualified_fraction` now uses the **full requested 24-hour horizon** as its denominator. A step that is rejected by a property, physical, or equipment-envelope check is *not* counted as delivered service; remaining unrun steps also cannot count as qualified service. `service_qualified_fraction_completed` is a diagnostic fraction of successfully integrated steps only, and `completed_fraction` records the portion of the requested horizon actually integrated. `spec_unserved_kwh` integrates shortfall on **completed** steps only, so it is not a credible full-horizon service estimate after an aborted simulation. Such runs are ineligible for any tariff-cost comparison, and partial-run cost/electricity deltas are null. This avoids fractions exceeding 1 when numerical integration aborts mid-step.
