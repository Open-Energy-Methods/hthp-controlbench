# HTHP-ControlBench — Master Research and Implementation Plan

**Version:** v0.5 · **Status:** revised research specification, not implemented HTHP software. **Review basis:** v0.4 independent scientific audit, plus independent double-precision re-evaluation of bypass and passive cases. No deadlines or calendar-based project gates.

**Status:** Proposed; no implementation or empirical results claimed  
**Version:** 0.4 — finite-capacity-rate process HX, explicit process-flow/demand degrees of freedom, conservative LTV-MPC tests and three linked studies (2 November 2026)  
**Project owner:** Abhijith Sivaprasadan  
**Research alignment:** Industrial high-temperature heat-pump control; related to the SINTEF Energy / Brunel HeatMinds research topic, but independently developed and without institutional affiliation or a project delivery deadline  
**Provisional repository name:** `HTHP-ControlBench` (not yet created)  
**Research modality:** Transparent, independent, simulation-based research demonstrator; no access to an actual industrial HTHP claimed  
**Primary audience:** Thermal engineering and control researchers, reproducibility reviewers, doctoral research evaluators, and future independent contributors
**Research packaging decision:** One shared codebase/model and reproducibility harness; three independently testable studies (dynamic PI/MPC, SOC/active sets, fluid/storage feasibility), with an integrated synthesis. These are proposed studies, not published papers.

> **Important:** This is a proposal and execution specification, not evidence that any model, experiment, or controller described here has been completed. Numerical parameters, model fidelity, and experimental outcomes must be resolved through a documented design and verification process. The project is *not* affiliated with, sponsored by, or validated by SINTEF, Brunel, DLR, Siemens Energy, or any heat-pump manufacturer.

## 0. Executive summary and non-negotiables

**Problem.** Industrial high-temperature heat-pump (HTHP) control is a coupled thermodynamic, dynamic, economic and operational problem. The incremental value of model predictive control (MPC) over a tuned proportional-integral (PI) controller depends on thermal inertia, forecast information, operating constraints, process-duty requirements, available flexibility, and model mismatch. A sophisticated solver does not automatically improve performance.

**Primary aim.** Build an open, independently reproducible and *simulation-only* research benchmark: a physically consistent process-side HTHP plant, a systematically tuned PI/PID baseline, a constrained MPC controller, a rigorous self-optimising-control (SOC) investigation, steady-state real-fluid cycle anchoring and thermal-storage feasibility analyses. Extensions to dynamic refrigerant modelling and reinforcement learning (RL) are research options after the foundational stages are established—not excluded for calendar reasons.

**One overarching research question:** Under which operating regimes does predictive control provide material economic and operational value over well-tuned simple feedback control when heat duty, heat-source conditions, storage, forecasts and plant uncertainty vary?

**Research contributions to test, not presume:** (i) a transparent nonlinear-versus-linearized controller benchmark; (ii) an empirically documented PI tuning and robustness baseline; (iii) an MPC cost formulation consistent with convex-QP requirements; (iv) quantitative usable-flexibility boundaries; (v) per-active-set economic-loss maps for genuine SOC or a defensible *negative* SOC result; and (vi) operating-envelope calibration from refrigerant thermodynamics.

**Build principle:** Advance by scientific dependency and acceptance evidence, not by fixed dates, timeboxes, application deadlines or arbitrary feature counts. All stages are planned in full; no result is claimed until code and tests exist. The optional extensions remain optional because of their marginal scientific question and access requirements, not because of a deadline.

**Core scientific safeguards:**

1. The truth simulator is a physically bounded nonlinear process model. MPC predicts with a distinct, locally linearized model; PI and MPC both control the *same* truth simulator.
2. The controller command `u = n_cmd` and actual compressor modulation state `n` are different quantities; actuator lag and command limits apply explicitly.
3. Electricity consumption is linearized as **one joint function** `P_el(n, T_src, T_h)` before building the convex QP. A ratio of separately-linearized heat and COP maps is **not affine**.
4. Heat-pump evaporating and condensing temperatures are separated from industrial source/supply temperatures by nonzero heat-exchanger approaches. COP bounds use physically specified Kelvin temperatures.
5. The price-flexibility study must first establish usable thermal buffer energy **above the minimum service condition**, not just nominal mass×cp×arbitrary temperature range. Physical heat transfer and specification-qualified service are *different* variables; energy conservation uses physical transfer even if temperature quality fails.
6. No rule-based tariff schedule is called self-optimising control without an active-set/DOF analysis and measured economic loss relative to feasible offline optimum.
7. Simulation verification, independent code/model agreement, thermodynamic plausibility, and experimental validation are separately labeled. No industrial hardware validation or product-grade safety claim is implied.
8. Each MPC control step relinearizes the state model and electrical-power map around the current estimate/reference; derivative, trust-region and bumpless-fallback tests are mandatory.
9. A nominal point cannot be called feasible until **finite hot- and cold-side heat-capacity rates**, the process-side HX, header-to-buffer coupling, actual process-flow convention, thermal losses, pressurization and rated HP capacity close simultaneously.
10. Process duty is derived consistently from process mass flow, return temperature and required service temperature (or from an explicitly separate, local duty controller). It is **not** an unconstrained independent signal that can make incompatible flow/temperature requirements disappear.
11. MPC candidate trajectories must satisfy a declared **componentwise trust region**, independently checked nonlinear rollout tolerances, and a slew-limited PI fallback at every handoff, with all failures reported.

**Outputs:** source code, cited parameter ledger, frozen scenario manifest, tests and CI, model-equations and derivation notes, benchmark tables/figures, **three separately falsifiable research studies using a common codebase and one synthesis**, a full technical report with appendices, and an independently auditable limitations register. Short reviewer summaries are generated only from passed results.

**Status at v0.5:** the HTHP dynamic plant, controllers and benchmarking experiments remain **proposed and unimplemented**. A separate **synthetic algebraic WP1 reference worksheet** has now been executed with six passing tests; this does not establish an implemented dynamic heat pump or thermodynamic cycle. Algebraic examples have been independently recomputed using declared synthetic parameters; they are **not** component calibration, real-cycle data, physical validation, or claims of equipment performance. The finite-hot-loop **solved-bypass** example in §4.1 is the default nominal teaching case (the passive-HX comparator is separately calculated); §16.2 retains the old calculations as a documented limit case.

## 1. Background and evidence provenance

### 1.1 Employer-defined requirements

The SINTEF position requires (i) modelling and analysing dynamic thermal systems, (ii) thermodynamic cycle analysis, (iii) control theory and PID tuning, and (iv) MATLAB/Python scientific programming. Additional valued areas: MPC/RL, heat-pump thermal design, optimisation, self-optimising control. The advertised PhD evaluates control strategies in dynamic industrial process integration and pilot-scale laboratory settings. **This project does not claim to substitute for actual physical laboratory experience.**

Official advertisement: <https://www.sintef.no/karriere-i-sintef/ledige-stillinger-i-sintef/stilling/145824/>.

### 1.2 Established relevant experience versus new work

**Existing, self-reported/portfolio-backed experience** (to be audited in repositories before code reuse):

| Existing work | Reusable idea | Do not overstate |
|---|---|---|
| [OpenSteamOpt](https://github.com/abhijith-sivaprasadan/opensteamopt) | Dynamic steam-plant model structure; Python shadow-model and config/CLI ideas; its 24-hour RTO is a one-shot MILP and its pressure trim is proportional feedback, **not MPC** | Steam boiler dynamics are not refrigerant dynamics; RTO is not equivalent to MPC or SOC |
| [ThermoTwin-F](https://github.com/abhijith-sivaprasadan/thermotwin) | Reduced-order transient subsystem, sensor errors, model verification, five-step simulated grid-regulation MPC | Gas-turbine core is primarily steady-state per operating point; the actual five-step MPC is written in **Fortran** for simulated grid frequency. Use as an algorithm reference, not as reusable Python or a heat-pump controller |
| [TES Discharge Screen](https://github.com/abhijith-sivaprasadan/tes-discharge-screen) | Thermal inventory and model-to-model cross-check methodology; implement new comparisons in pure Python | The repo's existing compiled FMU route depends on Windows; do not make Ubuntu CI depend on that binary. Cross-model agreement is **not** hardware validation |
| [GridGuardPINN](https://github.com/abhijith-sivaprasadan/GridGuardPINN) | A *different* pattern: surrogate-accuracy gating through physics residuals and out-of-distribution testing | Surrogate-accuracy gating is **not** an MPC-solver-infeasibility fallback; do not port its gate to the controller. Results are not heat-pump evidence |
| Siemens Energy/KTH thesis | Numerical assumptions, mesh verification, thermal physics, sensor/DAQ troubleshooting | CFD investigation was steady-state; does not confer PID tuning or heat-pump hardware validation |
| KTH R134a laboratory | Compression cycle, COP, measured power and heat duties | Low-temperature laboratory rig is not an industrial HTHP and should not be used as HTHP validation |

**New project must supply:** a dedicated heat-pump-oriented plant model, identified and tuned feedback controllers, transparent control design and quantitative results that can be independently reproduced.

### 1.3 Terminology and truth controls

- **Physical verification:** energy and mass balances, dimensional analysis, limit-case tests, solver convergence. Does not establish real-world accuracy.
- **Cross-model verification:** agreement between two independent implementations. Does not establish empirical validity.
- **Calibration/benchmark anchoring:** selecting plausible steady operating points using property models or literature. Does not validate transients.
- **Experimental validation:** comparisons with measurements not used in calibration. NOT in initial project scope.
- **MPC:** constrained receding-horizon numerical optimisation with state prediction and implementation of only the first control action. Merely running setpoint optimisation is not MPC.
- **PID tuning:** documented computation or systematic experimental/simulated tuning, not merely inserting a plausible Kp/Ki pair.
- **SOC:** identified controlled variables yielding low economic loss when held at constant setpoints across a specified disturbance set, with explicit constraints and measured loss. Fixed schedules or heuristics alone are *not* SOC.
- **High-temperature heat pump:** an actual thermodynamic heating technology operating at elevated heat delivery temperatures, not merely a generic hot-water tank with an arbitrarily assigned COP.

## 2. Research question, hypotheses and falsifiability

### 2.1 Primary research question (RQ1)

For a specified industrial heating duty, physically bounded operating envelope, and thermal-buffer capacity, when does constrained MPC yield measurably better temperature service, electricity cost or energy consumption than a properly tuned PI/PID baseline?

### 2.2 Additional research questions

- **RQ2 (robustness):** How sensitive are relative controller rankings to unmodeled heat losses, uncertainty in cycle COP, wrong thermal capacitance/UA, imperfect forecasts, and measurement bias?
- **RQ3 (complexity):** Is the benefit of MPC materially greater than its computational burden and implementation complexity on the chosen scenarios?
- **RQ4 (SOC, hypothesis-dependent):** Can one identify a measurable controlled variable or linear measurement combination that maintains acceptably low economic loss at constant setpoint over a defined disturbance envelope, compared with reoptimisation?
- **RQ5 (flexibility):** How do thermal buffer size, compressor modulation range, and process-temperature limits determine the value of price-responsive control?
- **RQ6 (verification):** Which model and solver assumptions materially affect performance claims and could reverse the controller ranking?

### 2.3 Hypotheses (NOT results)

- H1: Under slowly varying duty and weak constraints, a carefully tuned PI controller may perform nearly as well as MPC.
- H2: Under forecasts, actuator bounds, and meaningful thermal storage flexibility, MPC may improve operational cost, but *not necessarily total electrical kWh*.
- H3: Under strong model mismatch or noisy temperature feedback, an improperly tuned MPC may perform worse than PI or require a fallback.
- H4: SOC may provide acceptable economic loss over a restricted set of disturbances, while changing tariffs or active constraints may demand switching/scheduling; a universal constant setpoint is not presumed.

**Reject H1–H4 where numerical evidence contradicts them.** Do not set target savings such as “15% less energy” as success criteria.

## 3. Research alternatives and merit-based ROI

All core stages belong to a single coherent programme. Alternatives here identify *comparisons of research value*, not mutually exclusive attempts to rush an application. Ratings are hypotheses for peer review, not measured performance or interview probabilities.

| Route | Scientific purpose | Gap closure | Differentiation | Dependency/reuse truth | Priority |
|---|---|---|---|---|---|
| A. Steam PI study | Rehearse reproducible identification, tuning and anti-windup using OpenSteamOpt | Feedback/PID method, not HTHP specific | Low-to-moderate | Existing dynamic steam model, not refrigerant-cycle physics | Supporting exercise |
| B. Dedicated HTHP plant + PI | Establish physically bounded thermal dynamics and documented baseline | Direct | Essential | New plant equations; reuse software patterns only | **Core foundation** |
| C. Constrained MPC | Test incremental complexity versus PI on *same* nonlinear plant | Direct + advanced control | High if robust | New Python QP/controller; Fortran MPC only a conceptual reference | **Core** |
| D. Genuine SOC | Test controlled-variable selection, economic losses, active-set regions | Direct + named doctoral research topic | Potentially highest | Entire SOC analysis is new work | **Core** |
| G. Storage & tariff | Establish what flexible energy is truly usable and valuable | Direct integration relevance | High when physically credible | Storage method references only | **Core**, coupled with B–D |
| E. Real-fluid cycle anchoring | Give capacity/COP map a reproducible thermodynamic envelope | Thermodynamics and model credibility | Essential scientific depth | TESPy/CoolProp design/off-design *reference*, not dynamic refrigerant plant | **Core**, parallel where valid |
| F. Detailed refrigerant dynamics | Study fast transients, expansion valve/superheat, richer plant truth | Deep physical fidelity | High | New research and calibration burden | Extension |
| H. RL | Compare learning-based methods with verified baselines | Advanced algorithms | Question-dependent | Independent training/safety evaluation | Extension |
| I. Hardware/HIL | Physical controller evaluation | Very high | Very high | Requires authorised rig, supervision, safety and data | **Access-dependent**, not currently available |

**ROI principle:** evaluate gap closure, scientific insight, quality of reproducible evidence, transferability and marginal complexity. Report engineering workload as a descriptive resource estimate if useful, **without milestone dates or speed-based kill rules**. A broad design is not automatically a higher return than a narrow, deeply verified one. Dynamic thermal modelling, PI/PID, MPC, SOC, real-fluid screening and storage analysis all remain first-class deliverables.

### 3.1 Recommended scientific packaging: three linked studies, one software repository

The v0.2 independent panel rated **three independently scoped but linked studies** above one omnibus study (illustrative panel ratings 93 versus 83/100). These are subjective, rubric-dependent judgments, **not** measured acceptance probabilities or scientific results. Adopt the useful *separation of falsifiable claims* without multiplying the physical model or creating three drifting codebases:

| Study | Independently falsifiable question | Core evidence | Reuse dependency |
|---|---|---|---|
| **I. Dynamic feedback and MPC** | On the same nonlinear HTHP-shaped plant, when does an LTV-MPC improve service, constraint compliance or economics relative to two independently tuned PI baselines? | PI identification, disturbance rejection, nonlinear rollout, convexity/gradient checks, model-mismatch/rank reversal | Shared L1 plant, measured-value interface and scenarios |
| **II. Genuine SOC and regime changes** | Can fixed controlled variables yield low economic loss within feasible active-constraint regimes and robust switching? This extends Manum–Skogestad's **steady-state/quadratic** method to a **dynamic/noisy** plant; that extension is not validated by the citation. | DOF counting, offline optimum, controlled-variable derivation, per-regime loss distributions, negative result if no valid SOC variable | Shared process, constraints, scenario suite; may introduce clearly scoped second actuator |
| **III. Thermodynamic and storage feasibility** | Which fluid/topology and usable buffer configurations physically support specified high-temperature service and economic flexibility? | Property/cycle validity, service/HX temperatures, pressure/phase, capacity/recharge limits, sensitivity and traceable assumptions | Shared feasibility record and plant performance-map interface |

**Architecture:** a single `HTHP-ControlBench` repository and tagged model definitions, with `studies/01_control`, `studies/02_soc`, `studies/03_thermodynamics_storage`, plus one synthesis. *Standalone* means each study is separately evaluable and reproducible, **not** three independently calibrated simulators or automatically three journal papers. Keep an integrated narrative tying the three answers together. Any split into separate repositories or journal manuscripts is justified only after actual results warrant it.

**Return-on-effort:** evaluate physical defensibility, control gap closure, falsifiability, reproducibility, and transferability; track extra documentation and model-version drift risks. Selection is based on scientific merit and evidence, not an external schedule.

## 4. Proposed system and scope boundaries

### 4.1 Physical process, independent variables and pressure boundary

**Conceptual topology:** industrial heat source -> evaporator/refrigerant loop -> condenser -> pressurised hot-water header -> buffer/exchange path -> industrial process exchanger -> return. The source, hot-water header, buffer, process outlet, and refrigerant saturation temperatures are different physical quantities. Each heat-exchanger approach, pump/flow assumption and sensor location must appear on the system schematic.

**States:** `T_h` (header), `T_b` (buffer) and `n` (actual compressor modulation); **manipulated command** `u=n_cmd` is not a state. The baseline is one-input; add a second actuator (e.g. process/recirculation flow) only if a DOF study and physical equations justify it. **Disturbances:** source temperature `T_src`, process return `T_proc,ret`, externally specified process throughput when enabled, ambient `T_amb`, service target and electricity price. `Q_requested` is a **derived service duty** from flow, inlet and required outlet conditions—not an independently chosen actuator or inconsistent duplicate disturbance. Price affects the control objective, not the uncontrolled ODE.

**Fixed service target versus selected operating point:** the illustrative industrial *process outlet requirement* is `T_proc,required = 120 °C` and `Q_requested=300 kW_th`, at source bulk `T_src=60 °C`. **120 °C is not the header temperature.** Both the process HX and header-buffer coupling impose positive temperature differences. Determine the *header* setpoint from the exchanger capacity, selected buffer operating temperature and coupling at nominal duty. A generic `125–130 °C` header is **not guaranteed sufficient**.

**Two process-side degrees-of-freedom declarations.** The **default** is a fixed physical process flow, `C_proc=10 kW/K` at the nominal case, with industrial heat demand derived from its return temperature and service target: `Q_requested=C_proc*(T_proc,required-T_proc,ret)`. With `T_proc,ret=90°C` and `T_proc,required=120°C`, duty is `300 kW`. A duty disturbance with fixed flow and fixed delivery target must therefore change `T_proc,ret` or the required service schedule; for example, increasing return temperature from 90°C to 95°C lowers duty to 250 kW at the same flow. Alternative **exogenously varying process throughput** provides a *prescribed measured process-flow disturbance* (not an HTHP manipulated variable). A third, **HTHP-optimised controlled-flow variant**, may introduce process-flow/bypass actuator choice into MPC/SOC with its own physical dynamics, admissible limits, service trade-offs and additional degrees of freedom; it is a distinct later study, not silently present in the baseline. The **local process-side three-way bypass** in the ordinary duty-limiter mode is instead an externally specified algebraic service-control function: the HTHP optimiser cannot select its valve fraction. It adds an algebraic calculation, **not** an L1 dynamic state or a second HTHP decision variable unless actuator dynamics and authority are explicitly introduced. Do not infer equipment flow from an independently prescribed `Q_requested` in the core simulator.

**Finite-capacity-rate counterflow HX — baseline.** For a counterflow heat exchanger with positive heat-capacity rates `C_proc` and `C_hot` at the evaluation point (both in kW/K), use `C_min=min(C_proc,C_hot)`, `C_max=max(C_proc,C_hot)`, `C_r=C_min/C_max`, and `NTU=UA_proc/C_min`. For `C_r != 1`,

```text
ε_counterflow = [1-exp(-NTU*(1-C_r))] / [1-C_r*exp(-NTU*(1-C_r))]
ε_counterflow(C_r=1) = NTU/(1+NTU)
Q_HX_max = max(0, ε_counterflow*C_min*(T_b-T_proc,ret))
T_b,min,service = T_proc,ret + C_proc*(T_proc,required-T_proc,ret)/(ε_counterflow*C_min)
```

This assumes a counterflow configuration, effective constant `UA`, sensible-heat transfer, and inlet hot-stream temperature approximated by the well-mixed buffer state `T_b`. The formula is the standard two-capacity-rate effectiveness–NTU relation; see Lienhard & Lienhard, *A Heat Transfer Textbook*, 5th edition, §3.3, Eq. (3.21): <https://ahtt.mit.edu/wp-content/uploads/2020/08/AHTTv510.pdf>.  If the actual exchanger is parallel-flow or its effectiveness/UA varies with flow, substitute its own equation and recompute the nominal point; this baseline is not universal. The v0.3 shortcut `1-exp(-UA_proc/C_proc)` is recovered **only** for `C_hot/C_proc→∞` (assuming `C_proc=C_min`) and belongs in limit-case tests, not as the default finite-flow plant.

**Worked finite-flow nominal point (invented engineering assumptions; algebra only):**

| Parameter | Value | Basis/status |
|---|---:|---|
| Industrial return / minimum qualified outlet | `90°C / 120°C` | Assumed pressurized-water process |
| Nominal process-side capacity rate `C_proc` | `10 kW/K` | Fixed process throughput; ≈2.38 kg/s for pedagogical `c_p=4.2 kJ/(kg K)` |
| Hot-loop capacity rate through process HX `C_hot` | `100 kW/K` | Assumed circulating flow; ≈23.81 kg/s with same `c_p` |
| Process HX conductance `UA_proc` | `16 kW/K` | Assumed, not equipment data |
| `C_r`, `NTU`, counterflow effectiveness | `0.10`, `1.60`, `0.7815902848` | Double-precision general two-stream relation |
| Required process duty | `300 kW` | `C_proc*(120−90)`, not an independent input |
| Minimum buffer temperature for 120°C service | `≈128.38°C` | `90 + 300/(0.7815902848×10)` |
| Chosen nominal buffer temperature | `130°C` | Assumed operating margin ≈1.62 K above minimum |
| Maximum process HX capacity at 130°C | `≈312.6 kW` | `0.7815902848×10×(130−90)`; full-flow capacity, not actual draw in bypass mode |
| Header→buffer duty / `K_hb` | `305 kW / 100 kW/K` | **Bypass-solved** transfer of 300 kW + 5 kW buffer loss |
| Nominal header temperature | `≈133.05°C` | `130 + 305/100`, **bypass-solved** nominal point |
| Required heat-pump output at steady nominal point | `310 kW` | **Bypass-solved** 300 kW process heat + assumed 5+5 kW thermal losses |

**Local heat draw / capacity distinction (v0.5 physically named mechanism).** The baseline `duty_limiter` mode assumes a **process-side three-way bypass/mixing valve**: a locally controlled fraction `f∈[0,1]` of fixed total process flow passes through the exchanger; the remainder bypasses and recombines at the outlet. This is a *separate local process service controller*, **not** the HTHP command `u=n_cmd` and not an extra HTHP optimisation degree of freedom. Model `C_proc,HX=f*C_proc` and recompute `C_min(f), C_r(f), NTU(f), ε(f)` **at the reduced HX-side flow** (with constant effective `UA_proc` explicitly a provisional approximation, not a hardware-wide truth). Solve `Q(f)=Q_requested` on `[0,1]` if attainable, or use `f=1` and report unmet service when not. The bypass fraction is algebraic; real valve lag/rate, hot-loop pump hydraulic effects, and flow-dependent `UA(f)` are **additional models** to test/introduce before making any hardware claim.

**Separate nominal-mode worksheet (the same `T_b=130°C`, `C_proc=10`, `C_hot=100`, `UA=16` assumptions):**

| Quantity | `duty_limiter` — locally solved bypass | `no_bypass` — passive full-flow HX |
|---|---:|---:|
| Fraction of process flow through HX `f` | `≈0.931469` | `1` |
| Effectiveness *for actual HX-side flow* | `≈0.805180` | `0.781590285` |
| HX-side process capacity rate | `≈9.31469 kW/K` | `10 kW/K` |
| Physical heat transferred | `300.000 kW` | `312.636 kW` |
| Mixed process outlet (`90°C` inlet) | `120.000°C` | `121.264°C` |
| HX-side process outlet (before mixing) | `≈122.207°C` | `121.264°C` |
| Header-to-buffer duty (`+5 kW` buffer loss) | `305.000 kW` | `317.636 kW` |
| Nominal header `T_h=T_b+Q_hb/K_hb` | `133.050°C` | `133.176°C` |
| HP thermal output incl. `5 kW` header loss | `310.000 kW` | `322.636 kW` |

At `T_b=130°C`, the old scalar `alpha_local=Q_requested/Q_HX_max≈0.959582` is **not** the physically solved bypass fraction `f≈0.931469`, and must not be used to calculate heat transfer. This mismatch is the reason for the new `test_local_duty_limiter_physical.py`. The 310 kW COP/electricity example below refers **only to the bypass-solved nominal point**. The no-bypass case needs its own 322.636 kW capacity and COP calculation at its own 133.176°C header. Do not compare cost using one mode's power as the other's.

**Flow-dependent conductance and valve limitations:** Fixed `UA=16 kW/K` at reduced flow is a deliberately simplified *conditional* approximation. In a physical exchanger, flow-dependent film coefficients make `UA(f)` vary; the study must run a sensitivity analysis or independently calibrated conductance relation and identify where the constant-UA results cease to be reliable. The algebraic `f` assumes a near-instantaneous local valve and ideal mixing with no mixing loss; it is not a newly introduced dynamic state. If valve response is material to the controlled timescale, add `df/dt` and its actuator bounds with a distinct research scope. Retain the passive `no_bypass` comparison and report excess duty/overtemperature when present.

**Historical ideal-hot-loop limit (v0.3, preserved only for comparison):** If `C_hot/C_proc→∞`, the same `C_proc=10, UA=16` gives `ε=0.7981`, `T_b,min≈127.59°C`. At `T_b=128°C` it supports `Q_HX_max≈303.3 kW`, and with 300 kW process transfer plus a 5 kW buffer loss it gives `T_h≈131.05°C` and `Q_HP≈310 kW`. These numbers are correct **under that limit**, but are not the finite-flow default.

**Cycle Carnot sanity check for the bypass-solved 310 kW nominal point (not real-fluid validation).** Assume explicitly and provisionally `T_src,bulk=60°C`, `ΔT_evap=5 K`, `ΔT_cond=5 K`. Then `T_evap,sat=55°C=328.15 K` and `T_cond,sat=T_h+5 K=138.05°C=411.20 K`. Hence the refrigerant-side reversible heating bound is `COP_Carnot≈411.20/(411.20−328.15)=4.951`. An **illustrative**, not calibrated, `η_II=0.45` would yield a **model-specific** `COP≈2.228` and `P_el≈139.2 kW` for 310 kW heat output; `Q_source≈170.8 kW`. This is only a numerical bookkeeping reference and cannot establish feasible refrigerant pressure, compressor operation, discharge temperature or the true available 310 kW at this point. The actual physical Carnot ceiling is ≈4.951 for these illustrative saturation temperatures; multiplying by ηII is a **model assumption**, not a universal thermodynamic limit.

**Process-service feasibility is thus a coupled inequality:**

```text
C_proc = measured_or_fixed_process_flow * cp_proc                  # not an implicit free control input
Q_requested = C_proc * (T_proc,required - T_proc,ret)               # positive heating duty for default service
C_min = min(C_proc,C_hot); C_r = C_min/max(C_proc,C_hot)
epsilon = epsilon_counterflow(NTU=UA_proc/C_min, C_r)
T_b >= T_proc,ret + Q_requested/(epsilon*C_min)
T_h >= T_b + (Q_proc,transferred + Q_loss,b)/K_hb
Q_HP(n,T_src,T_h) >= Q_proc,transferred + Q_loss,b + Q_loss,h       # steady case
```

Do not choose `T_h`, `K_hb` and approach margins independently. For variable return temperature or flow, recompute exchanger effectiveness and minimum service-capable `T_b` rather than hard-code a generic `HX_approach=5K`.

**Pressurised-water and refrigerant boundary:** the nominal 120–133.18 °C hot-water circuit requires a pressure safely above water saturation pressure at **the hottest relevant water state**, plus a design-specific margin; ~1.99 bar(a) at 120 °C and ~2.70 bar(a) at 130 °C are reference anchors, **not pressure setpoints**. At the **133.05°C bypass-solved nominal header**, interpolation of the water saturation-pressure curve gives **approximately 2.98 bar(a)**; this is an illustrative *minimum saturation reference*, not a design pressure. Recompute it from IAPWS-IF97 at full precision and add pressure margin, boiling/pump transients and the **hottest modeled water temperature** when evaluating a real envelope. Use IAPWS-IF97/CoolProp water properties to compute `p_sat(T_h,max)` and prove a liquid phase within the modeled envelope; no hardware-operating procedure is inferred. Refrigerant-side evaporating temperature is lower than source bulk and condensing temperature exceeds hot-side temperature by explicit approach values. Internal cycle COP/validity must be evaluated there, not with reservoir-only temperatures.

**System boundary:** include source heat uptake, electric compressor input, condenser heat, process HX heat physically transferred, storage changes and thermal losses. Real compressor starts, oil management, refrigerant charge, piping losses, detailed hydraulics and equipment protection trips are outside the first reduced-order model unless separately justified. Sensor uncertainty is a measurement layer and must not change truth-state energy balances.

**First WP1 deliverable:** a nominal feasibility ledger showing each mass/heat balance, HX effectiveness or LMTD, minimum service buffer temperature, `K_hb` temperature drop, minimum condenser duty, physical pressure bound, refrigerant saturation approaches, and rated capacity/charge margin. If a plausible fluid cycle cannot meet this algebraic point, revise the operating point or topology rather than silently altering physical constraints.

### 4.2 Model fidelity hierarchy and truth labels

- **L0 — analytic reference**: nominal steady balances, heat-capacity sizing, Carnot bound with explicitly defined reservoir and refrigerant temperatures, liquid-phase pressure requirement.
- **L1 — nonlinear reduced-order dynamic plant (core)**: two heat capacities + first-order compressor lag; bounded heating capacity and electric power functions; conservation, actuator and measurement models. Independently implement before fitting control predictors.
- **L2 — local linearized discrete-time predictor (core)**: derive state Jacobians and `P_el` Jacobian near operating points; use only *inside* constrained MPC; quantify mismatch from L1.
- **L3 — fluid-specific steady-state reference (core, parallel branch)**: screen fluids, verify validity, pressure and cycle feasibility using TESPy/CoolProp or independently cited equations; build design/off-design thermal/electric power maps, with calibration/uncertainty and discontinuity checks. This is **not** a dynamic refrigerant twin.
- **L4 — detailed two-phase/refrigerant dynamic model (extension)**: independently evaluated Modelica/FMI or alternative if new research question and reliable parameters justify it.

L3 is a normal programme stage rather than a "maybe if time" addon. Initially L1 may use a *declared generic bounded map* while L3 generates physically constrained reference data. Promote the map to "fluid-anchored" only after comparison and acceptance tests pass. Model validity is local to its supported envelope.

### 4.3 Nonlinear state-space plant and energy accounting (provisional)

All temperatures use K in computation, heat/power W, capacity J/K, conductance W/K and time s; °C may be used for *differences* in the illustrative examples. The L1 truth model has three differential states: two thermal capacities and compressor lag. The baseline uses a mixed buffer and an effective header-buffer conductance, not a fully resolved hydronic/HX model. Declare this approximation and test its sensitivity. For L1 keep thermal capacitances `C_h` and `C_b` constant; the temperature-dependent `c_p(T,p)` integral in §4.4 is a separate higher-fidelity storage-sizing check, and any resulting discrepancy must be quantified before connecting the two.

```text
x=[T_h,T_b,n]                                  # two thermal states + actual modulation
u=n_cmd                                       # command, not the same as n
C_h*dT_h/dt = Q_HP(n,T_src,T_h) - Q_hb - Q_loss,h
C_b*dT_b/dt = Q_hb - Q_proc,transferred - Q_loss,b
Q_hb       = K_hb*(T_h-T_b)
Q_loss,h   = UA_h*(T_h-T_amb)
Q_loss,b   = UA_b*(T_b-T_amb)
dn/dt      = (sat_and_slew(u)-n)/tau_n        # must define discrete slew semantics
P_el       = bounded_P_el(n,T_src,T_h)
Q_source   = Q_HP - P_el                     # declared heat-pump boundary

# Process HX: counterflow, two finite thermal-capacity rates.
# C_proc fixed in default; C_hot a separately specified hot circulation flow.
C_proc      = m_dot_proc*c_p,proc            # W/K; declared fixed nominally
C_hot       = m_dot_hot*c_p,hot              # W/K; hot-side loop circulation
C_min       = min(C_proc,C_hot); C_max = max(C_proc,C_hot)
C_r         = C_min/C_max; NTU = UA_proc/C_min
epsilon     = counterflow_effectiveness(NTU,C_r) # C_r==1 branch explicitly
Q_HX_max    = max(0, epsilon*C_min*(T_b-T_proc,ret))
Q_requested = C_proc*(T_proc,required-T_proc,ret) # default service definition
# Full-flow reference Q_HX_max is only the passive upper capacity at current T_b.
# The local bypass valve is NOT an HTHP MPC actuator or extra dynamic state.
# Assume constant effective UA_proc over f as a provisional simplification.
def Q_at_bypass(f):
    if f <= 0 or C_proc <= 0 or C_hot <= 0 or T_b <= T_proc,ret: return 0
    C_proc_HX = f*C_proc                           # through HX, not total process flow
    Cmin = min(C_proc_HX,C_hot); Cmax = max(C_proc_HX,C_hot)
    eff = counterflow_effectiveness(UA_proc/Cmin,Cmin/Cmax)
    return eff*Cmin*(T_b-T_proc,ret)
if process_HX_mode == "duty_limiter":
    if Q_requested <= 0: f=0
    elif Q_requested >= Q_at_bypass(1): f=1          # undercapacity => unmet service logged
    else: f = bracketed_root(Q_at_bypass(f)-Q_requested, bracket=[0,1])
    Q_proc,transferred = Q_at_bypass(f)
elif process_HX_mode == "no_bypass":
    f=1
    Q_proc,transferred = Q_at_bypass(1)             # may EXCEED target
else:
    reject_undefined_HX_mode()
# Both modes conserve actual HX transfer; passive case need not match Q_requested.
# Total fixed process stream mixes heated fraction and unheated bypass return.
T_proc,out = T_proc,ret + Q_proc,transferred/C_proc   # after bypass mixing
T_proc,HX,out = T_proc,ret + Q_proc,transferred/(f*C_proc) if f>0 else T_proc,ret
T_hot,out = T_b - Q_proc,transferred/C_hot            # hot-loop HX outlet
T_b,min,service = T_proc,ret + Q_requested/(epsilon*C_min)
service_temp_ok = (T_proc,out >= T_proc,required - tolerance_K)
service_duty_ok = (Q_proc,transferred >= Q_requested - tolerance_W)
service_met     = service_temp_ok and service_duty_ok
Q_energy_shortfall = max(0, Q_requested-Q_proc,transferred)
Q_spec_qualified = Q_proc,transferred if service_met else 0  # KPI ONLY, not ODE
Q_spec_unserved  = max(0,Q_requested-Q_spec_qualified)        # conservative KPI

E_storage_change = C_h*(T_h_end-T_h_start)+C_b*(T_b_end-T_b_start)
E_balance_residual = integral(Q_HP-Q_proc,transferred-Q_loss,h-Q_loss,b)dt - E_storage_change
E_el_kWh = integral(P_el dt)/3.6e6
```

**Important semantics:** Physical heat `Q_proc,transferred` remains in the buffer energy balance even when `T_proc,out` fails the 120 °C service target. The specification-compliant indicator and `Q_spec_qualified` belong exclusively in evaluation/reporting. Do **not** set physical heat transfer to zero merely to enforce a service-quality criterion; that can violate conservation. A less conservative study may report the partially useful heat separately, but cannot claim qualified high-temperature service. The earlier abstraction `alpha_local*Q_HX_max` has been **removed as a governing law**. In `duty_limiter` mode, physical heat is calculated by the HX flow-fraction law and a bracketed root of the requested process duty. The HTHP controller neither chooses `f` nor receives it as a free optimisation degree of freedom. In `no_bypass` mode, `f=1`, so physical transfer is `Q_HX_max` and excess energy/process overtemperature must be reported. Neither mode is hardware-validated: ideal mixing and fixed-UA assumptions require explicit sensitivity tests and potentially flow-dependent `UA(f)` and valve dynamics before extrapolation. For shutdown (`C_proc=0`, or `C_hot=0`), set transfer to zero by an explicit flow-off case before computing effectiveness, and avoid `0/0`. Demand from exogenous throughput variation must be computed consistently as `Q_requested=C_proc(t)*(T_required(t)-T_return(t))`, not solved backwards to invent a controllable flow rate.

**Same definition for truth and predictive constraints:** With the declared `UA_proc`, full-stream `C_proc` and `C_hot` during a prediction interval, the MPC's nominal service-availability condition is `T_b >= T_b,min,service - service_slack` using **full-flow** `f=1` effectiveness. That inequality tests whether 120°C service is physically *possible*; the locally solved bypass then determines actual heat transfer. In both passive and bypass modes evaluate physical process outlet, available HX capacity, required process heat and any excess transfer against the **same** nonlinear plant. The bypass root is a deterministic, endogenous algebraic response to current conditions (not an MPC control action). Under exogenously varying process throughput, both `C_proc(t)` and the resulting duty are *forecasted disturbances*; for a truly controlled-flow variant introduce the additional actuator explicitly and use its effect on `C_r`, `NTU`, and HX transfer. Under nonlinear HX dynamics or limited local-duty control, independently re-evaluate the nonlinear truth plant's actual outlet temperature and transferred heat. The slack is a planned violation measure, not proof of delivered service. Store `Q_proc,transferred`, `T_proc,out`, `service_met`, `Q_energy_shortfall`, `Q_spec_unserved`, and `slack` for every timestep. A separate test must assert plant/metric/predictor service consistency across the threshold.

**Thermodynamic bounds:** `Q_HP(n,T_src,T_h)` and `P_el` require a shared feasible operating envelope. When COP is defined, compute `T_evap,sat=T_src-DeltaT_evap` and `T_cond,sat=T_h+DeltaT_cond` in **K**; the **absolute Carnot limit** is `COP_Carnot,refrig=T_cond,sat/(T_cond,sat-T_evap,sat)` for a valid heating-cycle region. A calibrated/specified second-law efficiency `eta_II` supplies a *stricter model assumption* (`COP_model<=eta_II*COP_Carnot,refrig`) when explicitly adopted; `eta_II` is not a universal thermodynamic law. Validate the refrigerant/pressure regime and ensure real temperatures/finite approaches are physically possible. Do not rely only on the more generous bulk-reservoir Carnot estimate.

**Numerical and system tests:** energy balance includes actual transferred heat, not required demand or qualified KPI; verify heat pump first law `Q_source+P_el≈Q_HP` on its declared boundary. Compare nonlinear ODE integration at decreasing time steps and against steady analytic limits, with actuator slew/lag and measurement noise handled separately. Record a baseline `m_dot,proc` and justify whether a rapidly changing process flow should become a state, a disturbance or a controlled input in a higher-fidelity model.

### 4.4 Flexibility feasibility and genuinely usable thermal inventory

**Arithmetic upper bound versus service energy.** At `m_b=5000 kg`, a *single pedagogical constant* `c_p=4.2 kJ/(kg·K)` and a hypothetical `20 K` band, the nominal arithmetic inventory is `116.7 kWh_th` or `23.3 min` at `300 kW_th` **if all energy were service-qualified**. This is not a measured or physically validated autonomy estimate.

**Actual service threshold:** for the **finite-capacity-rate baseline** HX in §4.1, `T_b,min,service≈128.38 °C`; `127.59 °C` is only the idealised infinite-hot-loop limit. Neither equals 120 °C, and neither is a justified arbitrary buffer lower limit. Define the upper bound using *both* liquid phase/pressure and achievable thermal/actuator capacity:

```text
T_b,max,physical = min(
  T_b,max,pressure_and_phase(p_loop,margin),
  T_b,max,reachable(Q_HP,max(T_src,T_h),K_hb,process_duty,losses,actuator_limits)
)
E_usable = integral_{T_b,min,service}^{T_b,max,physical} m_b*c_p(T,p_loop) dT
if T_b,max,physical <= T_b,min,service: E_usable = 0
```

The reachable term is the largest attainable equilibrium or dynamic temperature state **given the heat pump's fluid-specific maximum output at the rising header temperature**, `Q_hb=K_hb*(T_h-T_b)` and thermal losses; it must not be set from a nameplate maximum at an unrelated operating condition. Charging and discharging headroom, flow limits and ramp rates further constrain usable autonomy. For example, **if** `T_b,max=135 °C` turns out to be attainable, the finite-flow minimum `128.38 °C` leaves `(5000 kg × 4.2 kJ/(kg K) × (135−128.38) K)/3600 ≈ 38.6 kWh_th`, i.e. **about 7.7 minutes** at 300 kW_th before losses and dynamic draw constraints. The **old ideal-hot-loop limit** (`127.59 °C` minimum) would yield ≈43.2 kWh_th and ≈8.6 minutes; the unrestricted arithmetic 20 K range gives ≈116.7 kWh_th under that **same** 4.2 kJ/(kg K) comparator. For all physically anchored results, replace the constant with a verified `c_p(T,p_loop)` integral from IAPWS-IF97 and label the sensitivity. These are **conditional inventories**, not claims that 135°C is reachable. WP1 must derive attainable `T_b,max` from the heat-pump rated/off-design map, pressure/phase and header coupling **before any usable-storage claim passes**.

**Feasibility first:** require actual temperature-qualified service throughout any claimed electricity-price shift. Report price-event duration, usable kWh, extra charging energy/time, COP consequences of charging at higher delivery temperature, and whether a higher price-saving result sacrifices more compressor electricity elsewhere. With no feasible excess heating capacity or no usable storage, report the absence of meaningful arbitrage rather than silently creating flexibility in the optimizer.

**DOF implications:** compressor command alone plus hard temperature and heat-duty constraints may leave no nontrivial steady-state economic freedom. Explicitly count free degrees of freedom and active constraints before declaring an SOC candidate. Adding flow or bypass actuation is a separate physical model upgrade and must be paired with real process/HX equations, added limits and a fair comparator.

### 4.5 Real-fluid cycle anchor, pressure validity and literature provenance

Use TESPy for **steady-state design/off-design** performance studies, CoolProp for thermophysical properties, and critically evaluated independent literature/manufacturer maps. TESPy does not by itself validate the dynamic plant or represent all HTHP controller physics.

For each refrigerant candidate (e.g., R1233zd(E), R1336mzz(Z) where supported, ammonia only if pressure constraints credible, transcritical CO2 as a **different cycle topology** rather than a direct drop-in): record saturation/critical limits, property-library identifier/version, minimum/maximum validity, evaporation and condensation pressure, compressor discharge temperature, volumetric capacity, working pressure and mechanical/safety feasibility, and the source of any cycle efficiencies. Exclude R134a from an ordinary subcritical 120°C condensation case because its critical temperature is below that target. Do not claim a technology is commercially acceptable simply because a property API returns values.

**Data lineage:** every point tagged `synthetic`, `literature`, `property-calculated`, `independently cross-model checked`, or `measured` (only if data actually exist and are shareable). Construct bounded interpolation maps `Q_HP(n,T_src,T_h)` and `P_el(n,T_src,T_h)` and mask states outside the feasible envelope. Use held-out thermodynamic points to test map interpolation and linearization error. Preserve source IDs, fluid names and configuration hashes.

**Cycle anchoring deliverable:** a reproducible report of the physical operating envelope and how cycle uncertainties propagate into dynamic-controller conclusions. Failure to identify a credible fluid/cycle operating envelope is a substantive negative scientific result that must be reported. Until anchoring passes, clearly label the nonlinear dynamics as a *generic HTHP-shaped synthetic plant*, not a validated heat pump.

References: [TESPy steady-state tutorial](https://tespy.readthedocs.io/en/main/basic_tutorials/heat_pump.html), [TESPy design/off-design scope](https://tespy.readthedocs.io/en/main/), [CoolProp high-level API](https://coolprop.org/coolprop/HighLevelAPI.html).

## 5. Controller specifications and fair baselines

### 5.1 Common experimental interface

```python
Controller.reset(initial_state, initial_measurements, params, seed)
Controller.step(t, y_measured, disturbances_observed, forecasts_allowed) -> u_command
```

All controllers receive comparable measured states/sensors and act within the **same** physical actuator/safety envelope. Store controller configuration, solver status and control action on every step. Use held-out scenarios for final assessment; separate tuning and evaluation data. Forecast assumptions are documented and may be varied independently.

### 5.2 Baseline 0: uncontrolled and thermostat/on-off (optional)

A bounded on/off controller can illustrate basic hysteresis and system response, but it is not the proper scientific comparator for MPC. Keep it as optional context, not a straw man.

### 5.3 Baseline 1: tuned PI (mandatory)

`e(t) = T_b,set - T_b,measured` (or selected process/service variable). Implement a discrete PI with clearly defined sample time:

```text
u_raw[k] = Kp * e[k] + I[k] + u_feedforward[k]
u_sat[k] = clip(u_raw[k], u_min, u_max)
I[k+1] = I[k] + Ki*dt*e[k] + Kaw*(u_sat[k] - u_raw[k])*dt
```

Include actuator slew and lag in the plant, bounded integrator and anti-windup; use a consistent sign convention and distinguish integral time from integral gain. Document **two genuinely independent simulated-plant tuning routes**: (a) identified step-response plus IMC/lambda; (b) bounded relay-feedback/autotune, or a separately justified independent stability/frequency-based method if relay tests are unsuitable. The methods must not both simply reuse the same identified step-response curve. Predefine safe-in-simulation bounds and diagnostic conditions for relay oscillation, compare gains and tracking/robustness without cherry-picking the weaker PI, then perform sensitivity around the chosen gains. PID with filtered derivative is a separate test where it improves the physical response (derivative may amplify measurement noise). Report tuning data and resulting `Kp`, `Ki`, optionally `Kd` and filter `N` with units.

**Actuation distinction:** `du_max_per_update` bounds the *command* `u=n_cmd` at each sample (including a controller-to-controller handoff); `tau_n` separately governs how fast actual compressor modulation state `n` follows that command. These are complementary, **not interchangeable**, and their numerical limits must not be conflated or blindly applied to both variables. If a physical compressor has an additional independently sourced ramp limit, add it explicitly instead of double-counting one ramp constraint.

**PI gate:** stable for designated nominal scenarios; both tuning routes documented with Kp/Ki and units, disagreement quantified; temperature error and actuator effects reported; no silent overriding of saturation; repeatable from one command.

### 5.4 Controller 2: constrained MPC with an auditable convex QP

Start from the independently implemented L1 ODE `dx/dt=f(x,u,d)`, including compressor *actual* modulation state `n` and independent command `u`. **At every control update k**, estimate current state, update/linearize `A_c=∂f/∂x`, `B_c=∂f/∂u`, `E_c=∂f/∂d`, then discretize `A_d,B_d,E_d,g_d` for the declared sample time. This is **locally linear/time-varying (LTV) MPC**, not a once-per-scenario frozen LTI controller. Within each QP the first version may hold Jacobians fixed around that update point, but must enforce trust regions and measure prediction error over the horizon; if that is inadequate, linearize at a predicted reference trajectory (successive linearization) with its own numerical acceptance tests. Verify step responses against nonlinear reference at multiple operating points.

**Forecast meaning:** Nonlinear replay of a proposed sequence uses the **same forecast disturbances** as the QP; it measures *local surrogate/linearization fidelity under that forecast*, **not** predictive skill against unknown true future disturbances. Actual forecast errors are evaluated only in the separate held-out disturbed-plant experiment.

**Mandatory provisional LTV validity thresholds (synthetic starting values; tune only against held-out nonlinear prediction tests):** At every QP solve, constrain predicted deviation from that step's re-linearization center to `|T_h(j)-T_h0|<=5 K`, `|T_b(j)-T_b0|<=5 K`, and `|n(j)-n0|<=0.15` over each prediction stage (with separately enforced global equipment bounds and actuator slew). Evaluate the solved command sequence in the **independent nonlinear L1 plant** from the current state, using the same declared forecast. Reject it when the **maximum absolute** header or buffer temperature mismatch exceeds `1.0 K`, or `max_j |P_el,L1-P_el,L2|/max(|P_el,L1|,1000 W)` exceeds `0.05`; near-zero power remains flagged rather than masked. Trigger a shorter-horizon re-solve (at most one retry in the initial implementation) and then a bounded PI fallback if mismatch remains too large or the QP is infeasible. Test controlled perturbations that force either rejection path. These thresholds are **provisional research parameters, not industrial safety limits, not evidence of predictive accuracy**; they are recorded and subjected to sensitivity/robustness analysis. A fixed linearization throughout one horizon is an explicitly limited model, even if that linearization is refreshed at the next control update.

**Mandatory electrical-power derivation:** define the entire nonlinear electrical-power map first, `P_el=f_P(n,T_src,T_h)`, whether it was originally built from calibrated cycle data or the expression `Q_HP/COP`. Then calculate a **single joint numerical/analytic Jacobian of P_el itself** at the valid operating point:

```text
P_el_affine[k] = P0 + P_n*(n[k]-n0) + P_Th*(T_h[k]-Th0)
                      + P_src*(T_src_forecast[k]-Tsrc0)
```

where `P_n=∂P_el/∂n`, `P_Th=∂P_el/∂T_h`, `P_src=∂P_el/∂T_src`. **Recompute P0 and its joint gradient at every MPC update**, at the actual current/estimated operating point using the matched source forecast for that update (and, if needed, a per-stage linearized trajectory). The derivative can be checked against the quotient-rule identity when both Q and COP are differentiable. Log a Jacobian timestamp, center, and locality error per MPC step to prove cadence, not merely correctness of one derivative. **Never divide two separately-linearized functions** inside a QP and call the result affine. At each MPC step, the forecasted `T_src` is a parameter (not an independently controlled decision variable); the resulting expression is affine in the predicted states and commands.

**Convexity audit:** QP Hessian `P` must be positive semidefinite; dynamics and feasible constraints affine; nonnegative known electricity price multiplies an affine electrical-power term, so the stage cost remains affine/convex for fixed prices. If negative prices are studied, price times a *still affine* power approximation is also affine; physical and nonnegative power feasibility remain mandatory. The QP is only a **local approximation** to the nonlinear economic problem, not globally equivalent to it. Record approximation errors and ensure the affine P estimate cannot drive the solution into negative or invalid power territory. Use local trust regions and **every-control-step linearization updates**, a feasibility recheck against the nonlinear plant, and guarded fallback when outside the valid envelope. The fixed-Jacobian-in-horizon approximation can be poor under price-driven excursions; test it and tighten trust regions or adopt trajectory-wise sequential QP as required. If nonlinear cost/constraints are retained, call the solver problem an NLP or sequential approximation, not a convex QP.

```text
minimize sum_k [
   w_service * (T_b[k]-T_b,service_reference[k])**2
 + w_change * (u[k]-u[k-1])**2
 + w_effort * (u[k]-u_ref)**2
 + tariff_EUR_per_kWh[k] * P_el_affine[k] * Δt_s / 3.6e6
 + w_slack * slack[k]**2
] + terminal_cost
subject to discretized dynamics;
           `T_b[k] >= T_b,min,service(d_forecast[k]) - slack[k]`, where `T_b,min,service = T_proc,ret + (T_proc,required-T_proc,ret)/epsilon(UA_proc,C_proc)` for the chosen finite-flow HX: T_b,min = T_proc,ret + Q_requested/[epsilon(NTU,C_r)*C_min];  # independently verify L1 service
           T_h, T_b, n, u bounded; ramp and admissible envelope constraints;
           P_el_affine[k] >= 0 within the model's valid trust region;
           slack >= 0, finite and heavily reported/penalized.
```

For price in EUR/kWh, electrical power in W and step size in seconds, **currency cost** equals `tariff * P_el * dt / 3.6e6`, not simply `tariff * P_el * dt`. Keep the tariff-free PI objective and comparison costs on the same unit basis. Define consistent units and dimensional scaling of all objective terms; explicitly document whether energy consumption or currency cost is being optimized. Since service constraints may be relaxed by slack, *report every relaxation as unmet service*, not a constraint-safe success. Nonlinear equipment safety limits should be hard-masked at the plant-command/simulation layer; the QP is not an industrial safety controller.

**Fallback and bumpless transfer:** if the MPC solver fails, violates physics/constraints, or produces a nonfinite command, apply a bounded PI command at the current timestep and log the failure. Before switching, initialize the PI integral term to reproduce the last **actually applied command** `u_last`: for `u_PI,raw=Kp*e+I+u_ff`, set `I=clip(u_last-Kp*e-u_ff, I_min,I_max)` and then **apply the global command-slew clamp at the handoff step itself**:

```text
I_new = clip(u_applied_prev - Kp*e_now - u_ff_now, I_min, I_max)
u_PI_raw = Kp*e_now + I_new + u_ff_now
u_next = clip(u_applied_prev + clip(u_PI_raw-u_applied_prev,
                                    -du_max_per_update, +du_max_per_update),
              u_min,u_max)
```

Here `du_max_per_update=0.05` of the 0–1 command range per **declared** controller update is an illustrative test value; a later physical or cycle model may require a different limit. This same slew clamp applies in PI, MPC and handoff paths. If clipped integral limits make an exactly bumpless transfer impossible, log the nonzero jump explicitly. This is a simulation transfer rule, not hardware safety certification. Log transfer transients, any remaining mismatch due to saturation/integrator clipping, and recovery. Do not hold stale commands indefinitely.

**Research checks:** OSQP/CVXPY formulation and solver-status tests, derivative finite-difference convergence, linearized-power positivity/trust regions, local prediction error, horizon sensitivity, solve latency and failures, parameter-mismatch rankings and an equal-information protocol. [OSQP QP definition](https://osqp.org/docs/solver/).

### 5.5 Controller 3: setpoint-scheduled PI / simple heuristic (recommended intermediary)

Add a transparent, *clearly labeled heuristic* for tariff or demand changes. This is a fair simple benchmark to MPC, and often proves more useful than pretending that every simple policy is SOC. Use identical service and actuator constraints. Distinguish its access to price forecasts and heating duty predictions from what MPC receives.

### 5.6 Controller 4: genuine SOC, including active-constraint regime changes (core)

Self-optimising control (SOC) is **not** a synonym for tariff-based setpoint scheduling. Derive it from a *steady-state economic optimisation*, identify feasible unconstrained degrees of freedom, then select controlled variables whose constant setpoints produce small economic loss over disturbances **within a mapped active set**.

1. Define economic cost `J(u,d)` per feasible process operation and list equal-service and operating constraints; document whether the comparison is steady-state or dynamic, and never confuse an offline price-window dispatch problem with classic steady-state SOC.
2. On a validated disturbance grid of demand, source conditions and exogenous tariff *regimes*, solve offline steady-state optima and record active constraints and nonzero free degrees of freedom. If the process is fully constrained, explicitly report that there may be **no meaningful SOC choice**.
3. Form measurable controlled-variable candidates `c=h(y)` including appropriately justified single measurements or linear combinations. Noise, bias, observability, constraint activation and disturbance sensitivity matter.
4. Identify `c_set` or `H` for each economically/physically legitimate active-set region; freeze policy and validate on held-out disturbances.
5. Quantify `L(d)=J_SOC(d)-J_opt(d)` against **the same** feasible constraints and service level, report absolute cost/heat and relative loss when denominator is meaningful. Report any infeasible or regime-switching point rather than excluding it.
6. Implement a low-level feedback loop maintaining the identified CV, with documented transitions/hysteresis between regimes. Map transient deviations, switching/chatter and instrument uncertainty.
7. If optimal operation is dictated entirely by an active limit, or a time-varying supervisory tariff schedule is the actual mechanism, label the result *constraint-following or scheduled/heuristic control* rather than SOC. A negative SOC result is valid research.

**Citation/novelty boundary:** Manum & Skogestad (2012) establishes active-set SOC ideas within a steady-state/quadratic setting. Applying its selected controlled variables and regime switching to a nonlinear, dynamic, noisy HTHP plant is **this project’s proposed extension** and requires independent evidence; a tariff-heuristic schedule does not become SOC merely by adopting that label.

### 5.7 Controller 5: reinforcement learning (separate extension)

Investigate RL only after the plant and comparative baselines pass verification and robust train/test separation exists. Any RL comparison needs reward specification, constraints/safety shield, training-budget parity, random seeds, out-of-distribution tests and learning curves. Avoid claiming novelty or safety by reward shaping alone.

## 6. Experiment design and preregistration

### 6.1 Variables, operating envelope and input schema

File `configs/base.yaml` stores validated/assumed thermal capacitances, UA values, **both process-HX capacity rates and flow interpretation** (`process_flow_mode: fixed | exogenous | controlled`; default fixed), **local process heat-draw mode** (`duty_limiter | no_bypass`; default explicitly solved local process-side bypass with conditional constant-UA and instantaneous-mixing assumptions), source temperature, refrigerant/COP map coefficients, temperature constraints, compressor capacity, modulation/rate limits, initial conditions, integration timestep, controller timestep, forecast availability and observation noise. The process-flow mode `controlled` is forbidden until a second actuator, its state/limits/rate and a new controller interface are implemented. `C_proc=10kW/K`, `C_hot=100kW/K`, `UA_proc=16kW/K`, `K_hb=100kW/K`, `T_proc,required=120°C`, `T_proc,ret=90°C`, `T_b,nominal=130°C`, and `Q_loss,b=Q_loss,h=5kW` are synthetic initial ledger values, not equipment data. MPC local validity starts provisionally at `(ΔT_h,ΔT_b,Δn)=(5K,5K,0.15)` and nonlinear mismatch `(1K,1K,5% P_el)` and must be audited against independent rollouts; initial uniform command slew is `du_max_per_update=0.05` per declared controller update.

A separate `configs/assumptions.yaml` marks for **each parameter**: units, value, source, plausibility range, calibration status, and whether synthetic, literature-derived or measured. No synthetic number may be silently presented as a manufacturer's specification.

### 6.2 Pre-registered scenario matrix

| ID | Scenario | Inputs/disturbances | Main question | Core? |
|---|---|---|---|---|
| S0 | Nominal constant demand | Fixed source, reference duty, price | Stability, energy closure, control effort | Yes |
| S1 | Demand step / ramp | e.g. bounded ±10–25% step and recovery | Settling, overshoot, service violation | Yes |
| S2 | Source-temperature ramp | Plausible source decline/recovery | Disturbance rejection, compressor limits | Yes |
| S3 | Tariff event | Synthetic 24-h low/high price windows, service band and buffer | Does storage actually enable cost arbitrage? | Yes, only after feasibility gate |
| S4 | Actuator saturation | Demand approaching available heat-pump rating | Anti-windup, graceful constraint handling | Yes |
| S5 | Parameter mismatch | e.g. C, UA, COP parameters perturbed ±10–20% | Robustness and controller rank stability | Yes in comparative phase |
| S6 | Sensor bias / noise | e.g. bias, dropout, correlated noise with seeded draws | Measurement resilience and fallbacks | Core |
| S7 | Forecast errors | Missed demand/price change, imperfect horizon | MPC sensitivity to information advantage | Core |
| S8 | Usable thermal storage sweep | Multiple `C_b` values, service-temperature limits, HX approaches and max recharge capacity | Identifiability of *usable* flexibility value | Core |
| S9 | SOC active-set operating regimes | Source/demand/tariff regimes and held-out disturbances | Identify genuine CV, detect free DOF and quantify economic loss | Core |

All percentages/temperature events above are **proposed test ranges**; do not hard-code until checking operating-point feasibility. Define time units, initial conditions, step onset, dwell duration and recovery conditions exactly in a scenario manifest. Do not tune parameters on the final held-out scenarios.

### 6.3 Data and forecast integrity

- Synthetic inputs are labeled and generated from versioned scripts with fixed seed and logged statistical characteristics.
- If using public historical Nord Pool prices, identify dataset, bidding zone, timezone, daylight saving handling and license; public prices *do not validate heat-pump physics*.
- Compare an **equal-information** experiment (same present measurements and no future forecasts), a **perfect-forecast upper bound** and an **imperfect-forecast realistic variant**. A controller given perfect future demand must not be compared to PI as if it were an ordinary fair algorithm comparison.
- Separate parameter identification and controller tuning data from final held-out evaluation scenarios.

### 6.4 Required output metrics and definitions

| Dimension | Metric | Specification |
|---|---|---|
| Control quality | IAE = integral(abs(T_b - T_ref) dt) | Units K·s or K·h; define target even for price-driven setpoint variations |
| Control quality | ITAE / settling / overshoot | Specify event window, output, tolerance, and whether overshoot is meaningful |
| Service reliability | Process-outlet-temperature violation, `service_met`, minimum T_proc,out, energy shortfall and spec-unserved energy | Report physical transferred heat and spec-qualified service separately; a temperature-quality failure does not nullify energy transfer |
| Constraint safety | Peak magnitude, duration and frequency of each violation | Distinguish hard physical envelope violations, allowed slack and service deficits |
| Energy | `E_el` (kWh_el), `E_proc,transferred` (kWh_th), `E_proc,spec_qualified` (kWh_th) | The ODE uses physical transferred heat; fair controller comparisons require equivalent qualified service |
| Performance | Refrigeration-cycle/heat-pump COP at condenser boundary (`sum Q_HP / sum P_el`) and service-delivery efficiency (spec-qualified heat/electricity) | **Never call** `spec-qualified heat/electricity` the thermodynamic heat-pump COP; state the chosen boundary and all losses |
| Economics | `C_el = sum(price * P_el * delta_t)` | One price series for all controllers, fixed currency, no arbitrary penalty mixing |
| Controller effort | total variation of u, number of starts, saturation time | Starts if on/off permitted; count only if included in plant |
| Complexity | median/p95 solve time, fail fraction, model size, tuning workload | Hardware/environment description, including CPU/platform |
| Robustness | metric distributions over parameter perturbations/seeds | Report median and range/CI, not cherry-picked best run |
| SOC only | relative economic loss from optimum | `L = J_soc - J_opt`, with same feasible constraints |

Report both raw values and ratios: `((J_MPC - J_PI)/J_PI)*100%` with explicit interpretation (negative means lower cost/error). Avoid percentage improvement when baseline denominator is zero or incomparable. Pair and seed stochastic scenarios; avoid false precision on deterministic synthetic runs.

### 6.5 Fairness protocol

1. All controllers act on the same underlying *nonlinear plant* and physical equipment constraints.
2. MPC's linear prediction model differs from the truth simulator; both compared with an intentional model-mismatch test.
3. Both PI and MPC undergo documented tuning/search budgets; no hand-picked weak baseline.
4. Provide equal-information comparison plus a separate forecast-advantaged sensitivity study.
5. Compare equivalent **specification-qualified** thermal service and report actual **physical heat transfer** separately; infeasible runs cannot be called “cheap.” An equal-service comparison should either restrict to scenarios/policies meeting the same duty and outlet-temperature requirements or display a separate Pareto frontier of cost versus quality violations, without hiding penalized shortfalls.
6. Pre-register primary metrics before looking at results; disclose changed experiments and exclude failed runs only with explicit justification.
7. Use paired seeds and disclose all scenario outcomes, including MPC solver failures and SOC regimes with poor loss.
8. Report parameter provenance and a separate limitations table alongside every headline finding.

## 7. Verification, validation and quality gates

### 7.1 Physics and numerical invariants (automatic tests)

**New v0.4 acceptance tests (required, not just named):**

- `test_hx_effectiveness_assumption.py`: for `C_proc=10, C_hot=100, UA=16` (kW/K), check `C_r=0.1`, `NTU=1.6`, general counterflow `ε≈0.78159` and `T_b,min≈128.38°C`. Check `C_hot/C_proc→∞` converges numerically to `1-exp(-1.6)≈0.79810`, `C_r=1` uses its finite special case, and zero flow follows the off branch instead of dividing by zero. **Do not** apply the single-stream approximation at `C_r=0.1` merely because it seems close; quantify the difference. Also check `Q_proc,transferred = C_proc*(T_proc,out-T_proc,ret) = C_hot*(T_b-T_hot,out)` for positive flows. The general formula must be the actual default L1 formula.
- `test_local_duty_limiter_physical.py`: verify `Q(f)` from the **finite-flow HX equation at `C_proc,HX=f*C_proc`**, bracketed solve on `[0,1]`, `f≈0.9314688744` and `ε(f)≈0.8051798837` at the stated nominal case, while the disallowed scalar `300/312.636≈0.959582` is distinct. Assert process-stream and hot-loop HX heat balances, bypass mixing, `f=0`/low-duty/undercapacity cases, and correct reporting of service shortfall without deleting physically transferred heat. Reject a change that replaces the physical root with `alpha_local*Q_HX_max`. Keep fixed-UA approximation and `UA(f)` sensitivity labelled; verify no-bypass output ≈121.2636°C at 130°C buffer and its distinct ≈322.636 kW steady HP requirement. Root-uniqueness/monotonicity must be verified over the declared parameter envelope, not assumed universally.
- `test_process_hx_dof.py`: fixed process flow is invariant under a controller `u` change; `Q_requested` is computed from declared flow and service/return temperatures; an exogenous-throughput option varies flow **as a disturbance** without adding an MPC decision variable; a `controlled` process flow is rejected unless the independent actuator, bounds/rate, and full HX recalculation exist. Test a 90→95°C return step giving 300→250 kW for `C_proc=10kW/K`, `T_required=120°C`. Test physical bypass-root and no-bypass transfer variants (not the deleted scalar limiter) for energy and service accounting; distinguish locally solved `f` from an HTHP-controlled-flow decision.
- `test_mpc_trust_region_trigger.py`: reject a QP proposal outside `(5K,5K,0.15)` stagewise validity region (or mark it infeasible by hard QP bounds); separately inject a modeled/true-plant mismatch exceeding `(1K,1K,5% P_el)` on nonlinear replay; verify exactly bounded retry then PI fallback, with no hidden successful-run substitution. Log triggers, current state, center, and controller update index.
- `test_mpc_to_pi_bumpless.py`: check integral pre-load and clipping and separately enforce `|u_applied[k]-u_applied[k-1]|<=0.05` under initial sample-time assumptions, including switching with a saturated controller. Report transfer error if integral state bounds prevent exact matching.
- `test_nominal_point_feasibility.py`: recompute baseline finite-flow `T_b,min≈128.38°C`, `T_b,nom=130°C`, `T_h≈133.05°C`, `Q_HP,required=310kW` **for solved bypass `f≈0.931469`**; additionally check at `f=1` that `Q_proc≈312.636 kW`, `T_h≈133.176°C` and `Q_HP,required≈322.636kW`; recompute refrigerant-side Carnot ≈4.951 for `T_src=60°C`, 5 K approaches; check units and `Q_source+P_el=Q_HP` for the declared synthetic ηII=0.45. Distinguish mathematical closure from real-fluid/rated capacity feasibility. Show old v0.3 nominal numbers only in the `C_r→0` regression. This **algebraic feasibility script is the first required passing numerical gate** before ODE/controller implementation, but is not real-fluid or rated compressor validation. For initial bypass feasibility, demonstrate both a converged root and a meaningful no-bypass comparator; the L1 ODE may be implemented in passive mode first if the local valve dynamics are not yet specified.


- At rest/no heat/demand, temperature evolution matches analytic heat-loss-only solution.
- For constant conditions, numerical equilibrium residuals of each ODE approach zero within declared tolerance.
- Discrete energy accounting: heat pump delivered thermal energy ≈ **actual physical process-HX heat transfer** + storage change + environmental losses + numerical residual. `Q_spec_qualified`/unserved service metrics must never appear in the energy-balance residual.
- `COP >= 0` where defined; **absolute COP thermodynamic bound** `COP <= T_cond,sat/(T_cond,sat-T_evap,sat)` using refrigerant **saturation** temperatures in Kelvin and declared nonzero approaches; if `eta_II` is a calibrated model assumption, separately test `COP_model <= eta_II*COP_Carnot,refrig` rather than misrepresent it as the universal law. Check `p_sat`/pressure phase limits, no NaN, negative absolute temperature, unphysical power, or outside-envelope extrapolations.
- `u` (requested command) and actual compressor modulation `n` are separately recorded and remain inside distinct bounds; correct actuator slew, lag and saturation logic.
- At zero **usable** thermal buffering or zero tariff variation, measured shifting benefits vanish or become explainable by other constraints; test process-outlet-temperature eligibility of every counted **qualified** kWh.
- **Separate named service-consistency test:** for below/at/above `T_b,min,service`, assert that the L1 plant outputs `Q_proc,transferred`, `T_proc,out`, `service_met` and evaluation KPIs consistently, and that the MPC service constraint uses the same threshold/forecasts; failing temperature quality does not make the physical energy transfer vanish.
- Integration timestep refinement (e.g. dt, dt/2, dt/4): key metrics and energy closure converge; report tolerances justified by output scale.
- MPC linearized predictor matches nonlinear small-signal response near the linearization point; report deterioration farther from nominal. Verify the **joint derivative of P_el** and bound the power-surrogate error within the declared local trust region.
- Anti-windup recovery after saturation is bounded and demonstrably improves upon disabled anti-windup for a chosen case; **bumpless PI transfer** reproduces last applied MPC command within explicit clipping/slew tolerances.
- **Every-step LTV test:** trigger multiple control updates at deliberately different `(n,T_h,T_src)` states and assert that `A_d,B_d,E_d,g_d` and the joint `P_el` Jacobian are recomputed each step, timestamped, locally accurate, and not silently reused from an earlier operating point.
- **Independent PI tuning cross-check:** step-response IMC and relay/independent tuning each produce logged gains and test traces; report differences instead of selecting a weak baseline.
- Unit tests for temperature conversions, power-to-energy integration, COP, process/refrigerant approach temperatures, **effectiveness/UA and `T_b,min,service`**, buffer usable temperature band, absolute pressure/phase plausibility, forecast alignment and daylight saving treatment if real prices are used.

### 7.2 Independent reference checks

- Hand-calculated nominal energy balance and COP limit.
- Compare selected steady-cycle operating points with TESPy/CoolProp if implemented, preserving solver/refrigerant versions.
- If a Python/Modelica implementation is added, compare *states under identical exogenous inputs* and document agreement thresholds.
- No experimental data = label project “simulation verified, not hardware validated.” Never put “validated high-temperature heat-pump controller” on the CV without physical evidence.

### 7.3 Code and reproducibility

Use `pytest`, type hints where useful, static formatting/linting, pinned dependency resolution, GitHub Actions on Ubuntu/Python versions, deterministic seeds, reproducible results/artifact generation, and failure-on-violation tests. Record CPU and execution environment for timing comparisons. A single `make reproduce` or `python -m hthp_controlbench run --suite core` should reproduce report tables and figures from a clean checkout.

### 7.4 Security, safety and IP

- Public code must not contain Siemens Energy/Alleima internal data, undocumented proprietary curves or confidential test-rig information.
- Do not operate any high-temperature/refrigeration/pressurized apparatus independently to “validate” a simulated controller.
- Any later laboratory tests require equipment owner approval, formal safety procedure, suitable rated hardware and professional supervision.
- Properly cite software/data licenses; do not copy GPL/incompatible snippets into a permissively licensed repository without checking terms.
- Include a `DISCLAIMER.md`: not for industrial deployment or safety-critical control.

## 8. Engineering architecture and deliverables

### 8.1 Suggested repository tree

```text
HTHP-ControlBench/
├── README.md                       # question, scope, truth labels, quickstart, key figures
├── LICENSE
├── CITATION.cff                    # creator ORCID: 0009-0009-8429-1266
├── pyproject.toml / uv.lock        # actual adopted dependency/pinning mechanism
├── Makefile
├── configs/
│   ├── base.yaml
│   ├── assumptions.yaml
│   ├── scenarios.yaml
│   └── controller_tuning.yaml
├── src/hthp_controlbench/
│   ├── plant/                       # physical parameters, balance ODE, cycle map
│   │   ├── dynamics.py
│   │   ├── performance_map.py
│   │   ├── envelope.py
│   │   └── cycle_reference.py       # TESPy/CoolProp steady-state reference anchor
│   ├── sensors/measurement.py
│   ├── controllers/
│   │   ├── interface.py
│   │   ├── pi_pid.py
│   │   ├── scheduled_pi.py
│   │   ├── mpc.py
│   │   ├── soc.py                  # active-regime maps, actual SOC when qualified
│   │   └── safety_fallback.py
│   ├── scenarios/generator.py
│   ├── identification/step_response.py
│   ├── evaluation/{metrics.py,runner.py,compare.py}
│   └── cli.py
├── tests/
│   ├── test_physics.py
│   ├── test_units.py
│   ├── test_controller_bounds.py
│   ├── test_pid_tuning.py
│   ├── test_pid_tuning_independent.py
│   ├── test_service_quality_consistency.py
│   ├── test_hx_effectiveness_assumption.py
│   ├── test_process_hx_dof.py
│   ├── test_local_duty_limiter_physical.py
│   ├── test_nominal_point_feasibility.py
│   ├── test_mpc_prediction.py
│   ├── test_mpc_power_jacobian.py
│   ├── test_mpc_relinearization_each_step.py
│   ├── test_mpc_trust_region_trigger.py
│   ├── test_mpc_to_pi_bumpless.py
│   ├── test_buffer_usable_flex.py
│   ├── test_soc_active_sets.py
│   ├── test_fallback.py
│   ├── test_reproducibility.py
│   └── test_scenarios.py
├── experiments/
│   ├── preregistration.md
│   ├── scenario_manifest.csv
│   ├── active_set_matrix.csv
│   └── frozen_config_hashes.txt
├── studies/
│   ├── 01_dynamic_pi_mpc/      # standalone, reproducible study I
│   ├── 02_soc_active_sets/     # standalone, reproducible study II
│   ├── 03_fluid_storage/       # standalone, reproducible study III
│   └── synthesis/             # cross-study limitations and conclusions
├── results/
│   ├── summary.csv
│   ├── cases/
│   ├── figures/
│   └── environment.json
├── docs/
│   ├── model-equations.md
│   ├── fluid-screening.md
│   ├── flexibility-sizing.md
│   ├── assumptions-and-provenance.md
│   ├── controller-design.md
│   ├── verification-matrix.md
│   ├── mpc-jacobian-and-convexity.md
│   ├── limitations.md
│   ├── literature-review.md
│   ├── study-report.md
│   └── future-experimental-validation.md
└── .github/workflows/ci.yml
```

If packaging is costly, shrink the tree; deliverable substance is more important than architectural flourish. Avoid empty boilerplate modules and tests that only assert `True`.

### 8.2 Research report and review outputs

Produce **three independently evaluable technical studies** backed by one shared model and reproducibility harness, plus an integrated synthesis (length determined by scientific content rather than a deadline). Required: falsifiable RQs; actual thermodynamic fluid/operating-envelope audit; dynamic mass/energy/control equations; explicit measured-versus-synthetic provenance; PI identification and gain units; MPC Jacobians and QP convexity proof; self-optimisation active-set/DOF and loss analysis; storage usable-energy calculations; matched-scenario protocol; uncertainty; all failure cases; negative results; claims/limitations; exact release reproducibility.

Also generate a separate concise research brief and optional project summary from the same tested results. The brief cannot claim stages that have not passed. Documentation is a maintained research product, not an afterthought.

### 8.3 Essential figures (scientific evidence, not decorative)

1. Physical system and states/actuators schematic with pressure/temperature validity notes.
2. Nominal and disturbed temperatures, heat duty, electrical power and compressor command: PI vs MPC.
3. Controller feasibility and service-compliance plot (T_min, u limits, constraints).
4. Energy-balance residual and timestep convergence check.
5. Scenario-by-controller KPI matrix with *absolute* values, not only “% improvement.”
6. Electricity price, thermal-buffer energy and control dispatch for S3 if feasible.
7. Model-mismatch distribution (optional for minimum paper; required for stronger research claim).
8. SOC offline optimum vs constant-CV economic loss if SOC is implemented.

### 8.4 Research dissemination and external representation

- The public README provides scope, one-command reproduction, versioned results, physical operating envelope, assumptions/uncertainty and verification-vs-validation distinctions.
- Technical note, plots, raw results and a one-page reviewer summary are generated from a tagged, reproducible state when ready; no publication/DOI inflation.
- CV or application wording is independently updated *only when achieved results exist*; no project delivery milestone is coupled to any job-application schedule.
- Zenodo archive is an optional scholarly dissemination step after quality checks, with creator ORCID **0009-0009-8429-1266** and correct release metadata.
- Decline any request to represent this as a commissioned/sponsored SINTEF or Brunel project; do not represent a virtual plant as hardware validated.

## 9. Work packages, dependency sequence and scientific acceptance

**No dates, implementation deadlines, application-day cutoffs or time-based feature kills.** Proceed when prerequisite evidence passes. Fluid-cycle work can proceed in parallel once nominal boundary conditions are declared; storage feasibility must precede any price-advantage conclusion.

| WP/stage | Research output | Prerequisite(s) | Minimum acceptance evidence |
|---|---|---|---|
| WP0 — provenance and RQs | Literature/assumption register, physical boundaries, falsifiable questions, parameter source table | None | Each scientific claim identified as source, assumption or hypothesis |
| WP1 — thermodynamic/pressure feasibility | **Two finite HX capacity rates, fixed/exogenous/controlled throughput declaration, physically solved local bypass and passive-HX comparator**, coupled `K_hb`, HX `UA`, pressure, rated capacity and refrigerant-side COP check; usable storage band | WP0 | Reproducible **finite-flow** nominal table, `C_r→0` regression, COP 60°C source/5K+5K approaches, independently *derived* reachable `T_b,max` before usable-energy claims; refrigerant/rated limits tagged provisional until checked |
| WP2 — L1 nonlinear plant | 3-state ODE, compressor lag, **general counterflow HX with finite `C_hot,C_proc`**, bracket-solved process bypass (`f`, algebraic, not state) and passive-HX variants, separate physical heat/service quality | WP1 | Steady balance, timestep convergence, separate named **HX-effectiveness**, **process-flow DOF**, **physically solved bypass**, and **plant/controller service-quality** tests; physical transfer always conserved |
| WP3 — identification & tuned PI | Open-loop identification, **IMC/lambda and independent relay/other tuning**, PI gains/units, anti-windup, noise tests | WP2 | Stable repeatable disturbance response; both tuning methods recorded with gain/robustness comparisons, no weak-baseline selection |
| WP4 — L2 predictor & MPC | **Every-step LTV state/power relinearization**, distinct predictor, joint `P_el` Jacobian, QP convexity, finite-HX service constraint; **numerically specified trust/mismatch limits, slew-limited bumpless PI fallback** | WP2–3 | Timed Jacobians, gradient/locality, PSD, controller-flow and service consistency, **named trust-region trigger**, finite retry/fallback, nonlinear rollout and **handoff slew** tests |
| WP5 — fair comparative study | Fixed disturbances, matched constraints, forecast information variants, mismatch tests and KPIs | WP3–4 | Scenario-by-controller complete table including failures, unmet demand and uncertainty |
| WP6 — SOC/plantwide optimisation | Offline economic optimum, active sets, DOFs, candidate CVs, region policies and loss analysis **beyond steady-state/quadratic source scope** | WP1–5 | Reproducible `J_SOC - J_opt` per region; dynamic/noise performance independently tested; negative findings preserved |
| WP7 — real-fluid cycle anchor | Fluid screening, design/off-design TESPy/CoolProp points; bounded calibrated maps | WP1; parallel with WP2–6 as appropriate | Fluid/pressure validity verified for chosen envelope; cross-check errors reported |
| WP8 — storage and flexibility study | Capacity and service-temperature sensitivity; tariff-value experiments | WP1, WP2, WP5; run alongside WP6 | No counted shifting outside usable heat, recharge, service and actuator feasibility |
| WP9 — three linked studies, synthesis, CI and release | Reproducible studies I–III, synthesis, full reports, figures, software | All relevant core WPs accepted | Independent per-study reproduction from one tagged model/version; integrated limitations and scope audit |
| WP10 — optional advanced studies | RL, detailed dynamic refrigerant cycle, multivariable control, HIL with authorized lab access | WPs 1–9 and independent justification | Separate hypotheses, methods, validation and safety requirements |

**Dependencies:** `WP0 -> WP1 -> WP2 -> WP3 -> WP4 -> WP5 -> WP6`; `WP1 -> WP7`; `WP1+WP2 -> WP8` with final price scenarios dependent on WP5. WP9 synthesizes *completed* core work. WP7 can iteratively refine the L1 reference map after validation; document when its assumptions change the controller ranking.

### 9.1 Definition of done — scientific stages, not date-based gates

- **Stage A (plant and PI):** feasible synthetic HTHP-shaped plant, three distinguishable states, documented tuning, conservation and integration tests, at least demand/source disturbances, anti-windup and unit checks.
- **Stage B (constrained MPC):** Stage A + local predictor and verified power Jacobian; PSD QP; same nonlinear truth plant, robust infeasibility fallback, information-fair scenarios; report negative results.
- **Stage C (SOC):** Stage B + steady-state economic analysis, independently mapped active sets and free DOFs, feasible candidate CVs and held-out loss maps. If there is no valid CV, explicitly retain a negative result and separate heuristic-policy evaluation.
- **Stage D (thermodynamic and flexibility):** justified real-fluid design/off-design maps and usable storage conditions, including pressure, service quality, excess charging capability and feasible tariff events.
- **Stage E (research-ready):** stages A–D captured in pinned reproducible software, CI, method derivations, limitations, technical report and independent reviewer instructions.
- **Optional:** detailed dynamic refrigeration model, RL and authorized hardware study each justify their own measurement and validation programme. No software simulation is called experimentally validated.

## 10. Research sequence and rational decision points (time-independent)

These are **evidence gates**, not dates or workload-based kill switches:

1. **Physics gate:** audit process topology, **temperature-qualified process outlet and distinct physical heat flow**, **two-stream counterflow HX effectiveness, solved local bypass/no-bypass alternatives and declared process-flow/HTHP-control DOFs**, source/hot side approaches, water pressure, **coupled `K_hb`, losses, rated HP capability**, nominal energy balance, and reachable usable buffer energy. If infeasible, change assumptions and document model version rather than silently adjusting outputs.
2. **Numerics gate:** demonstrate step-size convergence and heat accounting; state/control distinction and identification inputs must work before controllers claim success.
3. **Baseline gate:** establish a strong tuned PI before interpreting MPC improvements. Include **an independent second tuning method**, anti-windup, and actuator limits.
4. **Optimiser gate:** derive electrical-power affine Jacobian and prove convex QP structure; verify **every-step relinearization**, **explicit componentwise trust region and numerical nonlinear-rollout mismatch**, service-consistent constraints, **bumpless PI fallback with command-slew clamp**. If QP assumptions fail, formulate a separately labeled nonlinear control problem.
5. **Fairness gate:** identical nonlinear plant, matched information, constraints, disturbance sets, service and predeclared KPIs. Do not exclude failures.
6. **SOC gate:** characterize active-constraint regimes, count unconstrained DOFs, derive CV and quantify economics; a negative/no-SOC finding is a legitimate output.
7. **Thermodynamic anchoring gate:** real-fluid properties, rated/cycle feasibility and interpolation test, with explicit differences from generic map and their effect on controller rankings.
8. **Research release gate:** external code/science audit, reproducibility, documentation and truth-label verification before any release or CV result claim.

**Important sequencing note:** real-fluid screening and usable-flexibility calculations are *foundational research*, not optional last-minute extras. More detailed fluid-map calibration can run in parallel with comparator development after the nominal feasibility audit, then trigger a new named benchmark version if the underlying plant changes.

## 11. Scientific and engineering risks, mitigations and invalidation rules

| Risk | Evidence to seek | Correct response |
|---|---|---|
| Unrealistic refrigerant/cycle point | Critical-temperature/pressure, approach and compressor envelope checks | Mark generic model as provisional; reject unusable fluid configuration |
| Single-stream exchanger formula applied to a finite hot-loop | General `C_r`/NTU calculation, flow/UA uncertainty and `C_r→0` regression | Enforce actual two-stream HX formula; recompute all nominal and flexible-energy numbers |
| Heat-demand signal incompatible with fixed process flow/temperature | Check `Q_requested = C_proc*(T_required-T_return)` and separate local duty-limiter control | Make duty derived, vary exogenous return temperature/throughput, or model a second actuator explicitly |
| Not enough service-quality thermal inventory | Usable kWh, process exchanger effectiveness, coupled `K_hb` gap, capacity/charge headroom and losses | Recalculate feasibility; report insufficient arbitrage potential as a result |
| Heat energy counted as served below specification | Physical `Q_proc,transferred` vs process outlet and `service_met` | Keep physical heat in the ODE; split specification-qualified and merely transferred heat metrics; test thresholds |
| Frozen MPC Jacobian after operating point changes | Timestamp and local gradient at each actual control update | Enforce LTV relinearization, trust-region validity and fallback on nonlinear check |
| Abrupt MPC→PI transfer | Handoff control trace and integral-state initialization | Initialize PI I-state to previous applied command with clipping and slew; report transient |
| Electrical-power QP secretly nonlinear | Joint power Jacobian; QP Hessian PSD; linear constraints | Re-derive or use properly designated nonlinear/sequential solver |
| `n` state confused with `u` command | Separate actuator model, bound and log each | Correct equations, interface, units and tests |
| SOC is really a tariff heuristic | Free DOFs and active-set loss analysis | Rename, report zero-DOF or negative finding |
| Controller success depends on its own prediction model | Distinct nonlinear plant; mismatch and parameter uncertainty | Report rank reversal/failure rather than hide |
| Fault-handling mechanism imported from unrelated work | Review source behavior and actual failure modes | Implement basic deterministic PI fallback, not surrogate-trust gate |
| Pressure/phase uncertainty | Water phase boundary and design margins | Restrict to simulated operating envelope; never prescribe physical operation |
| Cross-model verification described as experimental validation | Provenance tags and independent physical data checklist | Use “simulation-verified” only; experimental validation unavailable |
| Benchmark tuned to chosen scenario | Freeze tuning and held-out cases | Audit results and publish entire scenario distribution |
| Real price data issues | License, bidding zone, DST, tariff granularity | Begin with transparent synthetic cases; document real data use separately |
| Operating map black-box or extrapolated | Held-out cycle points and map gradients | Bound interpolation/trust domain and report uncertainty |
| Unauthorized hardware or proprietary data | Permission/ownership checklist | Use public/synthetic values; no unsupervised pressure/refrigeration experiments |

**No arbitrary deadline stop criteria:** scientific contradictions trigger redesign, scope relabeling or a valid negative result, never fabricated success.

## 12. Background literature and toolchain — initial seed, not exhaustive review

### 12.1 Official/technical starting points

1. SINTEF job description: <https://www.sintef.no/karriere-i-sintef/ledige-stillinger-i-sintef/stilling/145824/>
2. TESPy heat-pump modelling: <https://tespy.readthedocs.io/en/dev/basic_tutorials/heat_pump.html>
3. CoolProp high-level API: <https://coolprop.org/coolprop/HighLevelAPI.html>
4. OSQP QP formulation: <https://osqp.org/docs/solver/>
5. CVXPY and OSQP: <https://osqp.org/docs/parsers/cvxpy.html>
6. Skogestad 2000 SOC: <https://doi.org/10.1016/S0098-1354(00)00405-1>
7. Skogestad 2000 plantwide control: <https://doi.org/10.1016/S0959-1524(00)00023-8>
8. Manum & Skogestad 2012 active-set SOC: <https://doi.org/10.1016/j.jprocont.2012.02.015>
9. **IAPWS-IF97 primary release** (water/steam pressure and state properties): <https://iapws.org/technical-guidance/release/IF97-Rev>; cross-check using **CoolProp IF97** `PropsSI` with documented version: <https://coolprop.github.io/devdocs/fluid_properties/IF97.html>. The former processconvert.com converter is **not** a primary reference and is not retained as a numerical authority.

**Citation scope note:** Manum & Skogestad (2012) demonstrates a steady-state, quadratic-cost, active-set SOC approach. Generalization to a nonlinear dynamic noisy HTHP must be independently demonstrated and is a *hypothesis* of Study II, not proven by this reference.

### 12.2 Literature-review tasks

- Find 6–12 **directly relevant peer-reviewed** papers on industrial HTHP transient modelling and control, including operating conditions, data and actual validation status.
- Extract benchmark models and parameter sources; do not assume paper code is reusable/licensed.
- Find at least 2 sources on identification and IMC/lambda PI/PID tuning, 2 on heat-pump/industrial process MPC, and original self-optimising-control literature.
- Provide a critique matrix: plant physical scope, controller scope, reference baselines, scenarios, model mismatch, hardware validation, stated limitations, reproducible data/code.
- Prioritize independent primary studies and manufacturer/technical references for fluid operating envelopes.
- Record publication year and DOI; distinguish papers from guides, tutorials and repositories.

## 13. Scientific-return / engineering-effort framework for independent reviewers

This is a research portfolio valuation exercise, **not** an interview probability, salary projection, or deadline scheduling calculation. Independent reviewers should return **raw rubric scores with confidence**, and optional effort estimates as complexity descriptors; never let a unit-of-time ranking replace scientific merit.

### 13.1 Scorecard (0–5 per criterion, weighted to 100)

| Dimension | Weight | Question |
|---|---:|---|
| Physical/thermodynamic defensibility | 25 | Is the heat-pump/cycle/thermal-inventory physics sufficiently verified and bounded? |
| Control-theory gap closure | 25 | Does it demonstrate real PI tuning, predictive control methods, SOC only when justified? |
| Scientific insight and falsifiability | 20 | Could results teach us when control complexity is worthwhile or not? |
| Reproducibility and evidence quality | 20 | Is independent re-execution, sensitivity and failure disclosure possible? |
| Transferability and design parsimony | 10 | Can methods be adapted to other industrial thermal systems without invented reuse claims? |

For each route A–I from §3, report `raw score`, `weighted total`, `confidence`, `core dependencies`, `new work`, `reusable code vs reusable methodology`, `risk of misleading result`, and `value of a scientifically rigorous negative result`. Effort may be shown as low/medium/high engineering complexity and qualitative leverage, **not** as a deadline assumption. Avoid multiplying unjustified numerical ratings into a fabricated hiring probability.

### 13.2 Return-on-effort versus total scientific return

A small PI exercise may score very highly per unit of effort and still make a lower ultimate research contribution than robust SOC active-set mapping. Report both the marginal evidence value of an individual work package and the end-state scientific value of the full integrated study. Scientific merit and implementation dependency—not a date—determine the recommended order.

### 13.3 Competing programme architectures for reviewer comparison

- **Architecture A: integrated comparative control programme (recommended initial hypothesis):** physically bounded L1 + PI/MPC + genuine SOC + real-fluid cycle reference + usable storage, written as one consistent research programme.
- **Architecture B: staged separate experimental papers:** first PI vs MPC under known/uncertain plant, second SOC active sets, third fluid/storage impact; shared model and datasets but independent falsifiable RQs.
- **Architecture C: physical-model-first programme:** extensive TESPy/design-off-design calibration and component envelopes before control optimization; assess whether this yields substantially more robust conclusions than A.
- **Architecture D: optimization-first programme:** rich supervisory storage scheduling then lower-layer PI/MPC comparison; assess danger of producing dispatch rather than HTHP dynamic-control research.

A reviewer should propose revised hypotheses, compare architectural ROI, and state what evidence could reverse the preferred architecture.

## 14. Independent scientific-review questions (red-team)

1. Do the model and P&ID represent a physically possible industrial heat pump with a *service-side* 120°C requirement, and are the hot-water pressure and HX approaches credible?
2. Are all temperatures clearly assigned to source/sink reservoirs, refrigerant saturation points or process supply/return?
3. Does the finite water buffer provide usable thermal service, after minimum process temperature, approach, losses and recharge capacity?
4. Are the nonlinear plant, command `u`, compressor state `n`, and controller measurement/forecast interface consistent?
5. Does `P_el(n,T_src,T_h)` have a verified joint Jacobian and a locally justified nonnegative affine approximation? Is the resulting MPC QP truly convex? Does it stay accurate over the prediction horizon?
6. Is PI tuned transparently on identification data, and are its saturation, derivative/noise and integral recovery behavior credible?
7. Are predictions and the truth plant distinct enough to expose real model mismatch, without claiming independent physical validation?
8. Do PI and MPC have genuinely comparable forecasts, constraints and service delivery, and is a perfect-forecast upper-bound separately labeled?
9. Could an apparent electricity-cost reduction simply represent unmet heat duty or buffer depletion at the end of the test?
10. What happens to controller ranking when UA, C, COP, sensor quality, price shape and initial buffer state change?
11. Does the SOC subproblem have free economic degrees of freedom in each active-set regime? Are candidate CVs measurable and actual cost losses reported?
12. Is a regime-switching setpoint schedule honestly separated from true SOC?
13. What refrigerant models/operating envelopes can anchor the plant without extrapolation or pressure violations?
14. Which existing repository contains directly reusable *code* versus only algorithmic inspiration or testing practices?
15. Are software/license/data provenance, exact synthetic assumptions and unavailable hardware-validation boundaries plain to independent users?
16. What negative results, sensitivity reversals or infeasibilities would constitute a genuine publishable insight?
17. Is the overall question best answered by one integrated benchmark or by several independently peer-reviewable studies?
18. What would a specialist in thermal-process control, heat-pump thermodynamics or optimisation regard as the strongest remaining confounder?

## 15. Research governance and decision records

1. Version every assumption, source, fluid/operating envelope, test set, model form and control tuning procedure. Preserve the actual change rationale and comparison consequences.
2. Numerical findings must identify code commit, dependency lock, plant and controller config, scenario seed, solver version and region of validity.
3. Every plotted baseline and MPC trajectory must report service quality, heat balance and whether it is synthetic or physically anchored; cherry-picking is prohibited.
4. Project stages are accepted solely through predefined tests. Do not call a stage "complete" because a plan, presentation or README exists.
5. Do not confuse hardware access with simulation development: external physical validation is not presently possible; it requires permissions and safe apparatus, and is neither asserted nor required for the numerical study.
6. Evaluate extras by marginal scientific information and verification burden. UI, RL, complex FMI, publication ceremonies and additional control acronyms must answer specific new questions or stay separate.
7. Incorporate red-team feedback selectively: record KEEP/MODIFY/ADD/REJECT reasoning instead of automatically accepting all requested complexity.
8. Once enough evidence exists, freeze a research release for independent replication. The project has no mandatory research delivery date, and scientific stages are not coupled to employment submissions.

## 16. First executable research tasks (dependency-ordered; no time constraints)

- [ ] Create a source-traceable system schematic that distinguishes source, refrigerant, pressurised hot-water loop, process delivery and buffer; define heat-exchanger approach temperatures.
- [ ] **First executable algebraic gate:** compute full-flow `ε=0.781590284755` from `C_hot=100`, `C_proc=10`, `UA=16` (kW/K), prove general counterflow limit cases, and root-solve a physically named process-side bypass `f≈0.931468874443` to deliver 300 kW at 130°C buffer. For this **solved-bypass** mode: `T_b,min≈128.38°C`, `T_h≈133.05°C`, `Q_HP≈310 kW`. Separately compute the passive `f=1` case: `Q_proc≈312.636 kW`, `T_h≈133.176°C`, `Q_HP≈322.636 kW`. Do not confuse algebraic closure with real-fluid/rated compressor capability.
- [ ] Run the 5,000 kg/20 K arithmetic example and replace it with **service-threshold-based** inventory (`T_b,min,service` and physically reachable `T_b,max`) under fluid, pressure, charging and recharge constraints.
- [ ] Specify L1 states `[T_h,T_b,n]`, independent `u`, **fixed-process-flow default versus exogenous-throughput and controlled-flow variants**, and the **explicit local-duty-limiting mechanism versus passive/no-bypass HX**; keep physical process heat, actual outlet temperature and qualified-service KPIs separate in the ODE, sensor and evaluation layers.
- [ ] Create a finite parameter ledger with base values, source and scenario sensitivity ranges; declare generic versus fluid-specific map status.
- [ ] Implement the L1 ODE and pass conservation, equilibrium, actuator and timestep tests before controller comparisons.
- [ ] Implement open-loop excitation, **independent IMC/lambda and bounded relay/other tuning**, compare gains and robustness, test anti-windup and disturbances.
- [ ] Separately begin TESPy/CoolProp fluid screening, recording pressure/critical/envelope constraints and process/refrigerant approach differences.
- [ ] Build **every-step LTV** discrete predictor and **joint electrical-power Jacobian**; test each-step refresh, componentwise `(5K,5K,0.15)` locality bounds, nonlinear rollout mismatch thresholds `(1K,1K,5%)`, QP PSD and service-consistent constraints. Treat thresholds as synthetic provisional configuration values.
- [ ] Implement constrained MPC with bounded command/phase envelopes, **bumpless PI handoff with uniform slew clamp** (`0.05/update` provisional), bounded re-solve/fallback, and solver-failure logging.
- [ ] Pre-register scenarios, freeze PI and MPC tuning datasets, and run information-fair and forecast-advantaged comparisons separately.
- [ ] Solve SOC offline economic subproblems over active-set regions, identify candidate CVs and publish complete loss maps, including negative cases.
- [ ] Integrate fluid-anchored map and usability-constrained storage sensitivity; disclose how rankings change relative to provisional model.
- [ ] Complete **three independently testable studies** on one pinned model/codebase, integrated synthesis, CI, independent reproduction, model/claim audits, technical reports, and optional research release with correct ORCID.

### 16.1 Historical red-team review change ledger (Claude v0.1 -> master plan v0.2)

| Issue | Adopted response | Additional independent correction |
|---|---|---|
| QP electrical price term | Single joint Jacobian of nonlinear `P_el` before optimization | Gradient cross-check, PSD/Hessian, nonnegative local power, trust-region approximation and nonlinear rollout |
| OpenSteamOpt reuse | One-shot MILP/RTO and proportional trim, not MPC | Code reuse limited to scaffold and testing methodology |
| ThermoTwin-F reuse | Fortran MPC as design reference only | New Python MPC implementation, no automatic port |
| GridGuardPINN | Surrogate accuracy gate is a different use case | No unnecessary trust-gate module for solver failures |
| TES FMU | Pure Python comparison rather than compiled Windows FMU in Ubuntu CI | Preserve method, not platform dependency |
| High-temperature fluids | TESPy/CoolProp screening becomes a core stage | Separate refrigerant saturation from reservoir temperatures and enforce process-side pressure |
| Storage feasibility | Arithmetic inventory/recharge check is core | Count only heat that meets temperature, approach and service constraints |
| SOC and tariffs | Per-active-set offline economic loss and region selection | Separate real SOC from tariff-scheduled heuristic/constraint-following |
| No calendar constraint | Build full programme by dependencies | No timebox, dated gating, deadline weights or schedule-based kill-list |
| State versus input | Not explicitly flagged in Claude review | Actual compressor modulation `n` distinct from command `u` |
| Fallback logic | No GridGuard-style module | Bounded current-time PI fallback, not indefinite hold of stale command |

**Scientific status:** source and external review establish the *proposal and its rationale*. This document does **not** assert that model equations have been verified numerically, that any controller has been newly implemented, or that results have been measured.

### 16.2 Independent review v0.2 -> master v0.3 response (2 November 2026; no dates used as gates)

| Finding | v0.3 action | Verification to implement |
|---|---|---|
| Plant heat transfer versus service quality | **ADOPT with correction**: physical `Q_proc,transferred` remains in heat balance; explicit `T_proc,out`, `service_met`, qualified/unqualified metrics | Named service-quality consistency test around threshold |
| 120°C service/header conflict | **ADOPT**: coupled HX and `K_hb` calculation gives illustrative header ≈131.05°C, **not** automatically 125–130°C | Nominal feasibility ledger, rated map and phase checks |
| Ambiguous COP test | **ADOPT and clarify**: refrigerant-side Carnot is absolute bound; model `eta_II` ceiling is conditional/calibrated | Independent saturation-temperature and COP tests |
| Frozen MPC approximation | **ADOPT**: state and joint-power Jacobians refreshed each control step, with trust regions and nonlinear rollout | Every-step relinearization test with moving centers |
| SOC paper overclaim | **ADOPT**: steady-state/quadratic citation scope; dynamic/noisy SOC treated as proposed extension | Per-regime loss under noise/dynamics |
| Water pressure provenance | **ADOPT**: cite IAPWS-IF97 and CoolProp IF97 rather than low-authority converter | Property-call reproducibility and version pinning |
| `K_hb` independent from temperature headroom | **ADOPT**: at equilibrium `T_h-T_b=Q_hb/K_hb` | Coupled feasibility table and sensitivity |
| Undefined `T_b,max,physical` | **ADOPT**: min(phase/pressure limit, reachable heat-pump/coupling/capacity envelope) | Root/existence/charge tests before usable-energy claims |
| Fallback switching transient | **ADOPT**: PI integrator initialized from last applied command | Transfer transient and bound tests |
| One PI tuning method | **ADOPT**: independent second method; compare without cherry-picking | Logged gains and held-out performance |
| Three linked studies 93 vs integrated 83 | **MODIFY**: separate *claims and tests* but share **one** source of truth, model, package and CI; numbers are subjective reviewer scores | Each study reproducible independently, plus integrated synthesis |
| Zero physical heat below service specification | **REJECT**: violating energy conservation to improve labels is not acceptable | Track physical transfer independently of specification compliance |

**Unresolved before physically anchored claims:** no selected fluid or actual cycle off-design map is verified, no service point is matched to equipment data, no rated charging margin is measured, no simulation/control code has been executed for HTHP-ControlBench, and neither the 131.05°C pedagogical header nor 135°C hypothetical buffer maximum is a real equipment specification.

### 16.3 Independent review v0.3 -> master v0.4 response (2 November 2026; no calendar gates)

| Finding | Disposition | Evidence required |
|---|---|---|
| H1 single-stream effectiveness invalid without `C_hot≫C_proc` | **ADOPT + strengthen**: use general finite-`C_r` counterflow as the baseline; ideal-hot-loop remains a limit case | `test_hx_effectiveness_assumption.py`, numerical `C_r`/NTU/ε sweep, flow/UA assumptions |
| H2 fixed vs controlled process flow ambiguous | **ADOPT + clarify third mode**: fixed default; exogenous-throughput disturbance; controlled-flow requires new actuator | `test_process_hx_dof.py`, scenario generation consistency |
| Related hidden local heat-delivery actuator | **ADD independent correction**: `min(Q_requested,Q_HXmax)` requires explicit local process-duty limiting/bypass; compare passive/no-bypass | Physical heat, outlet temperature, overdelivery and local-control provenance tests |
| M1 MPC trust region/rollout threshold unspecified | **ADOPT**: synthetic per-stage `(5K,5K,0.15)` locality and `(1K,1K,5% P_el)` nonlinear mismatch, max one retry | Trigger/fallback test, threshold sensitivity, actual QP feasible-set audit |
| M2 fallback misses command slew at handoff | **ADOPT**: integral pre-load plus universal command clamp, initial `0.05/update` | Saturated/noisy handoff tests and log of any residual command discontinuity |
| M3 nominal example has no checkable COP bound | **ADOPT**: source=60°C, evaporator approach 5K, condenser approach 5K; at `T_h≈133.05°C`, refrigerant Carnot ≈4.951 | Algebraic Carnot and provisional efficiency/energy accounting; real-fluid acceptance remains open |
| L1 SOC steady-state scope not in Study II text | **ADOPT**: put limitation in RQ row as well as literature section | Study II standalone report repeats dynamic/noisy-plant novelty boundary |
| L3 hypothetical 135°C maximum never derived | **ADOPT**: arithmetic inventory explicitly conditional; no **accepted** usable-storage capacity until reachable upper T is derived | WP1 numerical feasible maximum from rated/off-design capacity and pressure/phase, then WP8 storage sweep |
| Architecture ≈90 vs ≈75 | **RETAIN WITH CAVEAT**: subjective, correlated rubric—not probability of publication or employment | One tag/pinned shared core; three independently runnable studies |

**v0.4 historical closure status (superseded by v0.5 §16.4):** This master document is still a **design**, not implemented code. The finite-flow nominal ledger and Carnot arithmetic have been independently recomputed for its synthetic input parameters; energy conservation of the *future ODE*, actual compressor/refrigerant feasibility, fluid property calls, and controller verification remain pending. Do not equate a worked worksheet to a tested HTHP controller.

### 16.4 Independent review v0.4 -> master v0.5 response (no calendar constraints)

| New finding | v0.5 disposition | Evidence/remaining limitation |
|---|---|---|
| Scalar `alpha_local*Q_HX_max` not derivable from exchanger topology | **ADOPT**: process-side 3-way bypass, algebraic `f` solved with recomputed `ε(f)` and ideal mixing | `test_local_duty_limiter_physical.py` and passive comparator; **constant-UA-under-bypass remains an unvalidated approximation** |
| Review hand-rounding `ε≈0.7814` vs plan `≈0.78159` | **RESOLVE by double precision** `ε=0.7815902847553592` | Regression test with formula computed independently, not embedded rounded expectation alone |
| Inconsistent constant `c_p=4.18` vs `4.2` in 20 K inventory comparator | **ADOPT** one pedagogical 4.2 and property-based `c_p(T,p)` for real-fluid study | Conditional 116.7 kWh remains arithmetic, not actually deliverable energy |
| Pressure at 133.05°C not displayed near example | **ADOPT** interpolation ≈2.98 bar(a), label as saturation reference | IAPWS computed value and full operating pressure margin are still pending |
| Nonlinear-rollout claim ambiguous | **ADOPT** common forecast checks *linearization fidelity*, not prediction accuracy | Separate out-of-sample forecast-error experiments |
| Command slew vs compressor lag | **ADOPT** separate `u` slew and `n` lag dynamics | Explicit actuator bound/rate tests, no conflation |
| **Additional independently identified issue:** nominal `310 kW` applied to passive `no_bypass` at `T_b=130` | **CORRECT**: 310 kW is for locally bypassed 300 kW transfer; passive case ≈322.636 kW and header ≈133.176°C | Separate mode-specific energy balance, temperatures, COP and price comparisons |
| **Additional scope clarification:** solved bypass `f` called a “new state” in the review | **CORRECT**: algebraic local valve fraction, not dynamic ODE state or MPC decision variable | Separate dynamic valve equation only if its response is modeled |

**Model provenance and unresolved gates:** The accompanying standalone `HTHP_ControlBench_WP1_Feasibility_v0.5.py` evaluates the nominal synthetic algebra in **both** modes and its six `unittest` checks passed on the reference case. This is the *first limited executable WP1 result*; no HTHP dynamic plant, PID/MPC/SOC controller, fluid-calibrated map, hardware measurement or lab validation is claimed. The bypass calculation assumes constant `UA` and ideal instantaneous mixing; it does not establish a physical valve design. A complete WP1 gate still requires bypass `UA(f)` sensitivity, IAPWS full-envelope pressure and refrigerant cycle/rated-capacity screening before physically anchored claims; the six tests do not close those requirements.

### Appendix A — Existing project links

- OpenSteamOpt: <https://github.com/abhijith-sivaprasadan/opensteamopt>
- ThermoTwin-F: <https://github.com/abhijith-sivaprasadan/thermotwin>
- TES Discharge Screen: <https://github.com/abhijith-sivaprasadan/tes-discharge-screen>
- GridGuardPINN: <https://github.com/abhijith-sivaprasadan/GridGuardPINN>
- Owner ORCID: <https://orcid.org/0009-0009-8429-1266>

### Appendix B — Non-goals, openly disclosed

This is **not** a physical HTHP controller, a plant commissioning recipe, an HTHP safety-system design, a validated digital twin of a commercial product, or proof of general real-world MPC superiority. It is an explicitly bounded research demonstrator for modelling, formal controller-tuning, fair comparisons, and the identification of limits where advanced control adds value or unnecessary complexity.