# Researcher red-team review — HTHP-ControlBench (3 November 2026)

**Scope:** code-level and evidence-chain review for a doctoral application in dynamic industrial high-temperature heat-pump control. **Verdict:** usable as an honestly scoped *computational research sample*; **not publication-ready**, externally validated, or a demonstrated industrial heat-pump controller.

**Review integrity:** this is a new internally conducted adversarial examination of the project's equations, controller code, published ledgers and CI. It is **NOT** an unaffiliated academic peer review, hardware validation, independent thermodynamic laboratory calibration, or proof that no other defects remain. Findings are separated into software/numerical checks and unsupported physical assumptions. The freeze point is the WP7 v3 main-branch ledger merged as PR #24 and the post-hoc v4 eligibility rederivation; any later scientific revision needs a new benchmark version and re-review.

## 1. Research-claim audit

| Claim that a panel may infer | What the actual evidence shows | Status |
|---|---|---|
| A physically plausible, executable lumped-thermal reference model exists | SI-unit thermal balances, accepted-state checks on WP7, conservation residuals, CoolProp/IF97 enthalpy and property-map rejection tests; CI replays original versions | **Supported as numerical model**; not equipment fidelity |
| The 310 kW nominal HTHP is a rated/available commercial configuration | **No**. Compressor suction-volume reference is *derived by fitting output to 310 kW at 75% modulation*. Isentropic efficiency, HX UA, source/sink heat-capacity rates, water pressure, motor losses, oil and equipment limits are assumed | **NOT ESTABLISHED** |
| A WP7 property-model observer is independently validated | Truth and observer use separate code paths but the **same** idealised compressor Q/P map, IF97 fluid properties and assumptions. No physically separate header, speed and temperature data from the claimed equipment | **Internal numerical check only** |
| Advanced MPC is better than tuned PI | Under fixed simulated scenarios property MPC often lowers tracking IAE; the local QP has arbitrary relative tracking/effort/power/slack weights, uses only limited noise/plant uncertainty, and no real-time timing or stability proof. A lower IAE is not proof of lower total cost | **Only conditional tracking finding** |
| MPC reduces electricity | On WP7 v3 four originally accepted 0.5 kWh-terminal-tolerance pairs, **all have positive MPC-minus-PI electrical energy** (MPC higher). These are idealised compressor-input estimates, not measured kWh | **NO savings demonstrated** |
| The original four v3 electricity pair comparisons are robust to equivalence choices | The per-store/total thermal inventory gate is arbitrary **0.5 kWh_th**. An *independently reimplemented* endpoint gate applied at 0.10 kWh_th retains **only 1/10** paired comparisons, not 4/10. Sensor/actuator terminal matching must also hold | **TOLERANCE-SENSITIVE** |
| SOC is proven near-optimal on the system | Original one-input plant has no free steady economic DOF at its active process service threshold. WP6's positive SOC examples add a **separate hypothetical pump-flow actuator** and explore a narrow synthetic landscape | **Exploratory on changed architecture** |
| WP8 proves realistic industrial flexibility savings | ~€0.107/day conditional, idealised model/tariff (60→15 s convergence). No OEM map, measured source/sink, auxiliary power, compressor start/stop economics or measured tariff dispatch | **Numerical example only** |
| External experimental compressor data validate this plant | Measured data have genuine publication provenance but come from **different hardware**, operating definitions and in one dataset two-phase/oil-mixed conditions. Model parameters were not independently identified against these datasets | **Provenance check, not model validation** |
| All integral updates are guaranteed accepted in WP8 | The previous 24 h RK4 loop checked intermediate stages, but **did not validate the weighted accepted endpoint before committing** physical state and tariff/service integrals. This review adds a fail-closed endpoint validator and regression | **CODE DEFECT CORRECTED in this audit** |

## 2. Priority risks for a scientific reviewer

### R1 — Reference machine has no independent physical parameterisation (critical to deployment)

`realfluid.build_cycle_map()` calculates `vdot = (310 kW / q_cond,specific) / (rho_suction × 0.75)` and then takes constant displacement and internal isentropic efficiency across its off-design grid. This is mathematically circular if the resulting 310 kW is later presented as a **prediction of capacity**. It is acceptable only as a **design-normalised hypothetical plant**. Without the actual compressor Q/P map, geometry/displacement, efficiency-versus-speed, pressure/temperature limits, source/sink flows and HX/auxiliaries, neither industrial feasibility nor real energy performance can be claimed.

**Required closure:** select a named real compressor/rig and compare an independently supplied measured/OEM map to cycle predictions at operating points *not used to calibrate the model*. Keep failed, missing and out-of-envelope points. Safety and equipment reviews remain separate.

### R2 — Property-model “independence” is only code-level (high)

`wp7_control.run_property_controller()` integrates the plant using the WP7 cycle map; `wp7_predictor.PropertyPredictor` propagates the same map and IF97 enthalpy through the WP8 `_stage` implementation. Different integrator functions are a useful regression, but identical property assumptions can reproduce each other's structural mistakes. Initial hidden states are known in the simulation, which also favours the model-based estimator over a realistic commissioning observer.

**Required closure:** build a truly distinct truth source (a independently parameterised measured rig dataset or an alternative validated component-network model) with provenance, measurement uncertainty, time alignment and measured actual compressor modulation. Split calibration and future held-out testing. Do not describe the 0.014 K internal error as hardware observer accuracy.

### R3 — Electricity comparisons depend on endpoint-inventory tolerance (high)

The original `compare_property_pair()` gate uses **0.5 kWh_th** tolerance *each* for header, buffer and combined inventory and **0.02** for terminal modulation and command. These are convenience thresholds, not uncertainty bounds. At v3 0.5 kWh_th four of ten pairs are labelled electricity-comparable; tighter matching changes that count materially (see `results/wp7_comparability_claim_audit_v4.md`).

The original eligible nominal property-MPC versus relay-PI case has **+0.1637 kWh_e** extra modelled electricity and **−0.1856 kWh_th** difference in final total thermal inventory. Those are *different carriers*, not quantities to directly subtract, but the residual makes an apparently precise policy-energy ranking harder to interpret as a matched-energy comparison. The fixed tolerance was not inferred from sensor metrology or a cycle repeatability distribution.

**Required closure:** either (a) report sensitivity to stricter end-state equivalence and do not claim a robust aggregate energy ranking or (b) extend the experiment with a common terminal restoration policy, identical useful heat/initial-final inventories and independently audited cycle-power assumptions. Report tariff cost separately from kWh.

### R4 — The “economic MPC” objective is not a justified optimal-control objective (high)

`mpc.MPCConfig` mixes squared temperature error, command movement, soft process-service slack, an effort term, and a price-scaled electrical-power cost. Its coefficients `w_tracking=12`, `w_movement=25`, `w_effort=.05`, `w_slack=1200`, `w_electric_eur=2` are illustrative, not tuned against an industrial cost definition. The maximum QP service slack is *20 K*. The MPC has finite horizon and uses a locally linearised model with a nonlinear rollout screening and fallback to bounded PI; this is a legitimate prototype but not a proof of global optimality, robust constraint satisfaction or economic efficiency.

**Required closure:** predefine dimensions/normalisation of each objective term, identify externally meaningful costs, compare multiple *predeclared* weight settings and a true same-service terminal-restoring policy, include solve-time budget, model mismatch and stability/safety guard behaviour. If changing weights, publish as a new benchmark, not a retroactive correction of WP7 v3.

### R5 — Scenarios and statistical strength are limited (medium to high)

WP7 v3 has **five user-chosen scenarios × three controllers**, 2 hours each; the only genuine *experimental* data audit involves different compressors. A single random seed for each noisy case is not an uncertainty distribution. The ±15% UA and +30% lag are explicitly illustrative, **not** empirically estimated tolerances. The 15%-lower-HX-UA case is infeasible for the prescribed initial 130°C buffer, so all three controller slots are null-rank; that is a useful physical-feasibility observation, not a controller-comparison loss.

**Required closure:** show full response curves with measurable sensor budgets, predefine many independent seeds and physically motivated variation envelopes, disclose number of scenarios that fail before a controller runs, calculate uncertainty intervals only when a real statistical sampling design warrants them.

### R6 — Research studies cannot be silently pooled (medium)

WP2–WP5 operate on a synthetic performance map; WP6 changes the plant architecture to add a circulation actuator; WP7 uses an idealised CoolProp heat/power map; WP8 adds hypothetical storage/price constraints. These are a suite of **linked hypotheses**, not one independently validated industrial process. Cross-study energy efficiency rankings are invalid without common plant topology and equal service/actuation/equipment assumptions.

### R7 — CI proves repeatability, not empirical validity (medium)

Full GitHub Python 3.10/3.11/3.12 tests and versioned artifacts are useful software controls. But a mathematical error shared by the plant, estimator and test assertions may satisfy every test. Tests against the same package do not supply sensor accuracy, manufacturer compressor maps, or uncertainty bounds. Document negative cases and cross-check with independently implemented analytical balances, alternate toolchains, and eventually laboratory measurements.

## 3. Corrective code work from this review

1. `scripts/audit_wp7_comparability.py` independently reads frozen v3 **raw per-controller** ledger and **re-derives** the same-scenario, same-noise, full-horizon, service, terminal-inventory and terminal-actuation comparisons; it does **not** use `compare_property_pair` or modify old records. It publishes strict-threshold sensitivity for the original results and rejects a tampered original comparator.
2. `ht_hp_controlbench.storage_flexibility.simulate_24h` now checks the **accepted** RK4 candidate for finite state, real-fluid water liquid margin, declared compressor map and optional hypothetical equipment limits *before* committing any energy, service or electricity/cost integral. A new adversarial test deliberately makes four valid RK4 substage **inputs** lead to an invalid weighted endpoint; none of its energy/service/cash is committed.
3. The application-facing project snapshot is explicitly linked to this limitation review. No control gains, reference efficiencies, compressor ratings or v3 results have been adjusted to manufacture a favourable comparison.

## 4. Publication and application decision

- **Acceptable for a PhD application:** yes, as a clearly labelled *independent computational research prototype* showing modelling ability, careful failure handling and research questions. Include the negative electricity and capacity results.
- **Acceptable as a validated scientific article on industrial controller superiority:** no. The plant truth is assumed, the optimisation objective is insufficiently justified for economics, equivalence results are tolerance sensitive and the outcome set has no independent measurement or statistical uncertainty basis.
- **Acceptable to control a real HTHP:** no. No equipment-rated compressor limits, machine/rig identity, regulatory pressure review, safety supervisor, real-time test, sensor calibration or control stability qualification.

**Scientifically highest-value next work:** named *external* HTHP experimental data with source provenance; a frozen input/output identification and held-out validation protocol; then rigorously matched baseline/controller testing. Another dozen synthetic controllers or unvalidated RL policy is lower value than closing even one of these gaps.

This document is an internal red-team audit, not independent publication peer review. Further defects may exist.
