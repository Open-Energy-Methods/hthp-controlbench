# WP6 — Self-optimising control, degrees of freedom and active-set economics

**Study II: first executable, falsifiable SOC investigation.** Status: *synthetic steady-state active-set and economic-loss screening, plus an exploratory dynamic/noisy-plant pilot*. This is not a fluid-calibrated industrial heat pump, a commissioned flow controller, a proof of robust stability, or an implementation of the complete Manum–Skogestad algorithm.

## 1. Central question and decisive negative result

> When can holding a measurable economic controlled variable at a fixed setpoint preserve heat service at low economic loss across process disturbances—and when is there no suitable unconstrained degree of freedom?

The **original WP2–WP5 HTHP plant has one controllable input**, compressor command `u=n_cmd`. Its process-side bypass fraction `f` is a local *algebraic* service mechanism and cannot be assigned to the HTHP supervisory optimizer. At the economic minimum that qualifies required process delivery, service lies at its active threshold; after the steady heat balances determine `n`, **no nontrivial free steady-state economic DOF remains**. This is a regime-specific *negative result*, not a claim that SOC can never be used in heat-pump systems. We will not call this a tariff-scheduled or fixed-temperature “SOC” controller.

In order to study a genuine residual choice, WP6 adds a **separate hypothetical hot-loop circulation actuator** with ratio `r`. The two supervisory inputs are then compressor modulation and hot-side pump flow. This new actuator is **not present** in the earlier plant configuration and is never retroactively attributed to WP2–WP5 benchmarks. The process-side bypass remains automatic and distinct from the added hot-side pump control.

## 2. Added physical assumptions — all synthetic, not measured

- Hot-loop heat-capacity rate: `C_hot(r)=r C_hot,nominal`, with nominal `100 kW/K`.
- At full process-side flow, hot-film resistance occupies a declared fraction `R_hot=0.4` of nominal HX thermal resistance. The model assumes `UA(r)=UA_0/[(1-R_hot)+R_hot/r^0.8]`. For partial process-side bypass the original WP2 `UA(f)` factor is additionally applied; it is a **separable provisional** model, not a calibrated two-film exchanger.
- Hot-side pump electrical power: `P_pump(r)=P_pump,nominal r^3`, with nominal pump electrical power **2.5 kW** at `r=1`, independent of compressor electrical power. The pump affinity-style exponent is a proposed operating-region approximation; pump efficiency, pressure-drop curve and fluid properties are unverified.
- `r∈[0.35,1.02]`, hot-loop command change at most `0.08` each 120 s sample, pump-flow first-order lag `75 s` in the dynamic pilot.
- Synthetic operating limits: buffer no hotter than `135°C`, header no hotter than `146°C`, compressor `n∈[0,1]`. The baseline compressor performance model is unchanged. These are illustrative limits, **not** a pressure or manufacturer operating-envelope approval.
- Fixed process-side capacity rate `C_process=10 kW/K`; process return temperature and heat-source temperature are exogenous, known to the steady optimizer. `T_required=120°C` is constant.

For the reference point `T_return=90°C` and `T_source=60°C`, specified process service is **300 kW thermal**. `P_pump` is included when comparing the two-actuator system's electrical cost. It is **not** part of the original one-actuator WP5 electrical accounting; cross-study energy claims must explicitly respect the architecture difference.

## 3. Complete steady-state economic problem

For a declared disturbance `d=(T_source,T_return,T_ambient,T_required)` and pump ratio `r`, we solve the same synthetic heat-exchanger physics as WP2:

\[
Q_{\mathrm{req}}=C_{\mathrm{proc}}(T_{\mathrm{required}}-T_{\mathrm{return}}),\qquad
\varepsilon=\varepsilon_{\mathrm{counterflow}}(C_{\mathrm{proc}},C_{\mathrm{hot}}(r),UA(r)).
\]

\[
T_{b,\min}(r,d)=T_{\mathrm{return}}+
\frac{Q_{\mathrm{req}}}{\varepsilon\,\min(C_{\mathrm{proc}},C_{\mathrm{hot}}(r))}.
\]

At the active temperature boundary, the process-side bypass is full flow and the required outlet is reached to numerical tolerance; above that boundary, the existing algebraic bypass fraction is solved, holding process service rather than inventing another supervisory actuator. Thermal balances determine header temperature, required compressor heat and the actual steady-state compressor modulation `n`.

The objective is the **total synthetic electrical power**:

\[
\min_{r,T_b,n}\quad J=P_{\mathrm{compressor}}(n,T_h,T_{\mathrm{source}})+P_{\mathrm{pump,nom}}r^3
\]

subject to both header and buffer energy balances, specification-qualified process heat, rated heat-pump capability, declared temperature limits and admissible pump flow. The tested model has increasing electrical objective for buffer backoff at fixed `r`; this is independently checked at multiple points in `test_steady_service_boundary_economic_choice_2d`. We therefore use `T_b=T_b,min(r,d)` **only for the investigated envelope**, reducing the nonlinear steady optimisation to one-dimensional constrained minimisation over `r`. The solver also checks interval endpoints and infeasible regions and is compared with a dense independent flow grid in `test_offline_optimum_better_than_explicit_dense_grid`.

A **positive** electricity tariff simply multiplies the two electrical terms. With no storage/discharge time coupling, this steady-state formulation has *no independently meaningful tariff-driven switching or energy arbitrage*. `results/wp6_summary.json` contains an explicit three-price invariance demonstration. Any subsequent variable-price dispatch requires a distinct dynamic storage/recharge formulation (WP8).

## 4. Active sets and degrees of freedom

The verified training ledger has 20 exogenous operating points. At eight, the **upper pump-flow bound** is active; at 12, pump flow is an **interior free economic DOF**. All feasible optimum points in this tested grid also require the active minimum-process-service constraint. At the pump upper bound, holding `r=r_max` is **active constraint control**, not a newly derived self-optimising variable. In the interior, one free economic DOF exists, so it is meaningful to search for a CV that remains near-optimal when held fixed.

The active set is calculated from the actual constrained offline optimum at each grid point. The *CV policies* do not consult that optimum on held-out conditions; this distinction is tested. Active-set selection from measured disturbances may itself be uncertain, and its accuracy has **not** been proven beyond this deliberately simple envelope.

## 5. Three genuinely different policies, with frozen training

The **training grid** is the Cartesian product of source temperatures `{45,52.5,60,67.5,75}°C` and process returns `{85,90,95,100}°C` (20 points). The **held-out grid**, never used to fit candidate coefficients, uses source `{47.5,57.5,72.5}°C` and return `{87.5,92.5,97.5}°C` (nine points). These points are *deterministic and close to the training range*, not independent plant data or a probability sample.

1. **Fixed-circulation CV:** optimize one common `r_setpoint` across all training conditions; hold the same `r` for the entire held-out grid, or report an infeasible point, **never silently clip it**.
2. **Empirical per-region CV:** fit a linear combination of measurable/computable variables to training optima, `CV=r+β_return(T_return−90°C)+β_source(T_source−60°C)`; hold one fixed CV value in the interior. Switch to explicit `r=r_max` constraint control where the *trained* unconstrained prediction crosses `r_max`. This is an empirical candidate; calling it the nullspace-optimal solution would be incorrect.
3. **Stationarity-derived per-region CV:** start from the economic first-order condition `J_r=0` at a separate feasible interior anchor (`T_return=95°C`, `T_source=60°C`). For small disturbance variation,
   \[
   \frac{dr^*}{dd}\approx -\frac{J_{rd}}{J_{rr}},\qquad
   CV=r+\frac{J_{r,T_{\mathrm{return}}}}{J_{rr}}(T_{\mathrm{return}}-90°C)
      +\frac{J_{r,T_{\mathrm{source}}}}{J_{rr}}(T_{\mathrm{source}}-60°C).
   \]
   Numerically estimate the Hessian and mixed derivative using the complete nonlinear economic function, including pump power; hold the resulting linear CV setpoint in the interior and explicitly switch to `r=r_max` where that constraint is active. The Hessian positivity and directional derivative are independently tested. This is **local stationarity**, not a full Manum–Skogestad parametric-QP/nullspace implementation.

Each policy is evaluated over every held-out disturbance *without adjusting its coefficients or setpoints*; only the offline optimum is recomputed as an **evaluation reference**. Equal process service and other feasibility constraints are enforced. Unserved or infeasible cases are not assigned a zero or finite “economic loss”; they are counted separately. `L=J_policy−J_opt` in W and `% J_opt` are the key verified metrics. The near-zero loss of fitted/Hessian CVs reflects this smooth synthetic landscape and limited disturbance domain, not demonstrated industrial savings.

## 6. Parameter-mismatch challenge

The fixed nominal policies are then tested **without refitting** under six distinct synthetic equipment assumptions: ±30% nominal pump electricity, hot-film resistance share `0.25` and `0.55`, and hot-side UA flow exponent `0.6` or `1.0` (nominal `0.8`). Each has nine held-out cases and three policies, yielding 162 additional policy–disturbance combinations. The counterfactual offline optimum uses the *actual varied model*, as would an ideal calibration-aware RTO. The CV policy receives no access to the true variant beyond measurements already named in the model.

This is a deterministic sensitivity analysis, **not** stochastic robust optimisation or a certified chance constraint. Record loss and feasibility separately, including unfavorable results.

## 7. Dynamic/noisy-plant extension — separate hypothesis

A new 4-state model `x=[T_header,T_buffer,n_actual,r_actual]` adds pump-flow lag to the original WP2 thermal model. At every Runge–Kutta integration stage, the flow-dependent exchanger map and compressor energy balance are evaluated at that stage's *actual* hot-loop flow. Compressor command and pump-flow command are bounded separately. The dynamic pilot adds an explicit **2 K temperature backoff** to help maintain service; this is not part of the ideal steady economic optimum and is logged as implementation cost. Integrated compressor electricity, pump electricity, physically untransferred heat, quality-unserved service and an independent header-plus-buffer energy residual are all tracked.

The supervisory policies use a buffer-temperature PI loop and a named flow setpoint policy. The PI is deliberately passed `NaN` for unobserved header temperature and modulation, to make it impossible for the PI code to consume these hidden simulation truths. The buffer-temperature measurement has reproducible Gaussian noise and a FIFO delay. Actual hot-loop flow is assumed measured, and current source/return temperatures are assumed known. The comparison `offline_rto` solves the **current** steady economic problem at each update; it does **not** receive future demand, nor is it claimed to be a dynamically optimal controller.

Two deterministic four-hour disturbance schedules are each run with no sensor noise/delay and with `0.2 K` Gaussian noise plus `120 s` delay using a declared seed. Fixed CV, Hessian-regime CV and current-disturbance RTO are all tested: **12 complete numerical trials**. A physical heat shortfall and a binary specification-quality shortfall are distinct metrics. No economic winner is declared when one method fails the required service. The dynamic electricity *difference* need not be nonnegative, even if steady `J_SOC−J_opt` is nonnegative, because transient trajectories differ.

**Scope caveat:** steady-state/quadratic active-set SOC literature is not a dynamic-plant optimality theorem. This work is a toy nonlinear extension with modeled sensor error, not an industrial validation of SOC, an independent full state estimator, or a guaranteed disturbance-rejection result.

## 8. Audits and reproducibility

Run `python scripts/run_wp6.py` to reproduce the offline optimum grid, frozen CV parameters, held-out and mismatch loss tables, dynamic trial outcomes, machine-readable summary and report. The source manifest belongs to the same Git commit as results. The workflow executes `python -m unittest discover -s tests -v` on Python 3.10/3.11/3.12 and regenerates WP6 results. Earlier WP2–WP5 code and results are not changed by WP6.

Important test assertions: the reference baseline has no hidden pump actuator, service and HX energy balance are conserved, infeasible points are not assigned loss, active sets switch, the Hessian candidate holds its exact CV within regions, the local gradient matches an independent shifted offline optimum, the constrained optimum beats a dense grid, positive tariffs do not alter this static optimum, the pump actuator has inertia, noisy measurements are deterministic, delayed observations genuinely use previous samples and the physical thermal energy residual remains small.

Published output files: `results/wp6_offline_optima.csv`, `results/wp6_heldout_losses.csv`, `results/wp6_assumption_sensitivity.csv`, `results/wp6_dynamic_scenarios.csv`, `results/wp6_summary.json`, `results/wp6_scientific_report.md`, `results/wp6_active_set_map.png`, `results/wp6_heldout_loss.png`.

## 9. Primary methodological sources and explicit limit

- Skogestad, S. (2000), *Plantwide control: the search for the self-optimizing control structure*, Journal of Process Control, DOI [`10.1016/S0959-1524(00)00023-8`](https://doi.org/10.1016/S0959-1524(00)00023-8). This motivates DOF counting, active constraints, CV selection and economic loss.
- Manum, H. & Skogestad, S. (2012), *Self-optimizing control with active set changes*, Journal of Process Control, DOI [`10.1016/j.jprocont.2012.02.015`](https://doi.org/10.1016/j.jprocont.2012.02.015). It derives a parametric-QP/linear-measurement approach for **steady-state quadratic** problems. WP6 does **not** claim to have implemented or validated that entire method.
- The current pump affinity and hot-film expressions are **assumptions**, not cited as specific validated equipment models. They must be replaced/anchored in WP7 or an independent pump/heat-exchanger calibration before any physical or generalised economic claim.

## 10. Next evidence needed

Before publishing a broader “SOC works” claim, test independent process/pump maps, two-variable CV controllability and measurement noise, more disturbance/active-set regions, pump operating limits, economically meaningful *time-coupled* tariffs/storage, and independently validated physical temperatures and COP. A new WP6 experiment can also apply the full nullspace/parametric-QP construction and compare its selected CV against these simpler stationarity candidates—provided the scope of the quadratic approximation is stated.
