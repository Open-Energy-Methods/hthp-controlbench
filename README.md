# HTHP-ControlBench

**Research software for the comparative study of PI/PID, model-predictive and self-optimising control of industrial high-temperature heat pumps.**

**Current release: WP2 synthetic nonlinear thermal plant v0.1.** Only the open-loop plant and numerical tests are implemented; PI/PID, MPC, SOC and real-fluid calibration are planned, **not** implemented or validated.

![Example synthetic open-loop thermal response](results/wp2_illustrative_thermal_response.png)

> **Scientific status:** This is an illustrative computational research model. All operating-point parameters and performance values are synthetic. Do not use it to design, operate or certify real heat-pump equipment.

The [research plan v0.5](docs/RESEARCH_PLAN_v0.5.md) is the frozen proposal; it contains intended work packages, not a claim that those components are already built. The [independent WP2 review brief](docs/INDEPENDENT_CODE_REVIEW_BRIEF.md) describes planned verification.

## Research organisation

The planned programme shares one plant model across three independently testable research studies: (I) PI/PID versus MPC; (II) self-optimising control with active-set economics; (III) fluid feasibility and thermal-storage flexibility. These are future studies; their existence in the plan does not imply completed simulations or results.

---

## WP2 model (implemented)



**Status:** executable research prototype; *not* a calibrated heat pump, digital twin, plant controller, or claim of equipment feasibility. **Planning baseline:** `HTHP_ControlBench_Master_Research_and_Implementation_Plan_v0.5.md` (not edited by this deliverable). Independent review: `HTHP_ControlBench_Independent_Review_v0.5.md`.

## What is implemented

- Three-state nonlinear, lumped ODE `x=[T_header(K), T_buffer(K), n_actual]`, applied command `u=n_cmd`, first-order compressor lag, 60-second controller updates, per-update slew limit.
- Separate physical header/buffer energy balances in J/K, W and s, with temperature-dependent ambient losses. `Q_hp(n,T_source,T_header)` is a **declared synthetic derating map** (not calibrated to a compressor); `P_el=Q_hp/(eta_II*COP_Carnot,refrigerant)` uses finite hot/cold approaches and is only a thermodynamic sanity approximation.
- General counterflow HX with two finite stream capacity rates; stable effectiveness calculation based on `expm1` even for `Cr -> 1`. Unit tests cross-check high-precision Decimal evaluation.
- Process-side bypass solved by bisection **algebraically at each ODE evaluation**, not as an independent compressor controller state or manipulated variable; alternate no-bypass passive case.
- Provisional `UA(f)=UA_nominal * f^a`, with `a=0,0.6,0.7,0.8` sensitivity. This is an exploratory correlation *not validated against any HX geometry or operating regime*.
- Separate actual physical heat, quality-qualified heat and unmet service. Any actual physical heat transfer remains inside conservation law even if below specification.
- RK4 integration of temperature/modulation **and physical energy integrals**; independent endpoint-trapezoid energy audit and timestepping tests.
- A *pre-programmed open-loop* disturbance experiment; **no PI, PID, SOC, MPC, or closed-loop heat-pump controller has been implemented here.** The planned active-set-crossing MPC-predictor/fallback test remains WP4 work; WP2 tests only establish the bypass kink in the physical model.

## Execute

Requires Python 3.10+ and `numpy`; `matplotlib` is optional and used only for plotting. From this folder:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
PYTHONPATH=. python -m ht_hp_controlbench
PYTHONPATH=. python scripts/make_report.py
```

Outputs: `results/wp2_illustrative_timeseries.csv`, `results/ua_sensitivity.csv`, `results/wp2_illustrative_thermal_response.png`, `results/verification.txt`.

**Caution:** The example simulates scripted changes at 20 min (process return), 30 min (open-loop compressor command), and 40 min (source temperature). It does not establish tracking, stability under a real controller, or comparative controller performance.

## Nominal physics and differences from WP1

The plan's synthetic duty-limiter equilibrium remains `T_buffer=130°C`, `T_header=133.05°C`, `Q_hp=310 kW`, actual modulation `n=0.75`. With `no_bypass`, physically transferred heat at the same buffer temperature is `312.636114 kW`; **the dynamic temperature-dependent header heat loss makes steady Q_hp = 322.641703 kW, not the earlier constant-5-kW worksheet's 322.636114 kW**. This ~5.59 W difference is a consequence of moving from a fixed-loss worksheet to a state-dependent loss law. Tests explicitly expect the physically self-consistent dynamic equilibrium, rather than concealing the discrepancy.

With buffer fixed at 130°C and service duty held at 300 kW, the UA exponent affects the necessary valve through-flow fraction but **not the header temperature or heat-pump duty** (because the required thermal duty, fixed losses, and chosen buffer state have not changed). This does **not** mean UA uncertainty is dynamically irrelevant: it affects actuator margins and whether the local valve saturates.

## Verification boundary

The 13 executable tests check the nominated synthetic algebra, high-precision HX stability, equilibria for both modes, flow degrees of freedom, physical service classification, the bypass active-set kink, command/actual lag, slew, analytic heat-loss-only decay, timestep convergence, energy integrals and an independently computed trapezoidal energy audit. Tests do **not** establish measured plant fidelity or temperature/pressure/refrigerant validity. All parameter values are assumed, not equipment specifications; real-fluid WP7 is outstanding.

## Project organization

- `ht_hp_controlbench/core.py`: model, finite-flow HX, synthetic cycle, algebraic bypass, RHS and equilibrium solver
- `ht_hp_controlbench/sim.py`: bounded open-loop command schedule, RK4 and energy integrals
- `tests/test_wp2.py`: independent numerical/physics assertions
- `scripts/make_report.py`: reproducible UA study, figure and verification summary
- `reference/WP1_Feasibility_v0.5.py`: frozen earlier standalone worksheet for provenance
- `results/`: generated synthetic results

## Next scientific tasks, not delivered here

1. Confirm a complete WP2 operating-envelope test matrix beyond the single nominal point; consider numeric stiffness and adaptive solver cross-check.
2. Define sensor/measurement noise in a separate observation layer (not injected into conservation equations).
3. WP3: identify and independently tune an honest PI baseline using two methods with anti-windup.
4. WP4: implement LTV/QP MPC with explicit trust region, rollout-error monitoring, and controlled PI fallback; **only then** add a specific mid-horizon bypass active-set test.
5. WP7: replace assumed compressor/fluid map with real-fluid property and pressure-feasibility work; parameter identification or hardware validation are separate requirements.

## Licence and citation

Code is published under the MIT License; see [LICENSE](LICENSE). Citation metadata, including the author’s verified ORCID, is in [CITATION.cff](CITATION.cff). No paper, published journal result or experimental validation is implied.