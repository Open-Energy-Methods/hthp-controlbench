# WP4 — Constrained receding-horizon MPC, synthetic research prototype

**State:** implemented and benchmarked against WP3 PI. **Validation:** numerical checks only; no measured refrigerant/heat-pump/hardware controller evidence.

## Plant and model separation

The independent nonlinear **WP2 L1 plant** integrates the physical energy balances and the algebraic process HX/bypass model. WP4 relinearizes a **local discrete predictor** on each control sample using numerical derivatives of a single 120-second plant map. The QP predicts `x=[T_header,T_buffer,n_actual]`, while its decision variable is the **compressor command** `u=n_cmd` (not an instantaneous state `n`). Full plant integration remains 10 seconds per RK4 step.

The MPC uses `horizon=10` and `period=120 s` (20-minute synthetic prediction horizon). Temperature and compressor-modulation trust-region bounds are `±5K, ±5K, ±0.15`. Upper bounds `T_header<=140°C`, `T_buffer<=136°C` are **invented study constraints**, not manufacturer limits. Commands are bounded `[0,1]` with `0.05` maximum change per control update. Service temperature is a *soft constraint* through nonnegative penalized slack (up to `20K`), so a mathematically feasible QP does not certify service.

The *joint* finite-difference derivative of physical electrical power `P_el(x,T_source)` is computed directly; no division of separately-linearized heating duty and COP is performed. Power is affine within the QP, with a price term in EUR/kWh converted by `dt/3_600_000` to match W and seconds. Quadratic tracking/slew/effort/slack terms have nonnegative weights and PSD Hessian. **SLSQP** (SciPy) solves this convex quadratic subproblem against affine constraints; its stopping status and primal constraint residuals are checked. This is a **QP-structured numerical baseline**, not an OSQP-supported certificate of global optimality, nor a nonlinear MPC stability guarantee. The listed weights mix dimensionless tuning objectives with an electricity-cost coefficient and are not a real industrial economic valuation.

## Re-linearization, forecasts and safety

The predictor and power Jacobians are re-derived at every sample (`linearize`). The model currently includes disturbance Jacobians only for **source temperature** and **process return temperature**. Other future changes (service temperature, flow capacity rate, ambient temperature) explicitly reject the MPC forecast, not silently extrapolate missing derivatives.

A candidate QP solution is nonlinear-rolled out through the separate L1 model under the **same supplied forecast** as the QP. Rejection limits: `1K` maximum header/buffer prediction error and `5%` maximum relative electrical-power error (with a 1000 W denominator floor). Independently reject nonlinear violations of the synthetic maximum header/buffer temperature. The test establishes local model fidelity under those *forecast inputs*, **not** future disturbance prediction quality.

Solver failure, infeasible constraints, unsupported forecasts, active-set mismatch or a failed rollout triggers **one shorter-horizon retry**, then a freshly bumpless-initialized **IMC PI** fallback with actuator bounds and slew. This fallback is a *bounded command mechanism*, **not** a certified process safety system: state constraints may still become physically infeasible under plant mismatch, actuator limits or capacity shortage.

## Comparison protocol and results

`python scripts/run_wp4.py` reproduces a predeclared **4 physical cases × 4 controllers = 16 run matrix**. PI baselines: nominal FOPDT/IMC lambda=0.5tau and relay-derived Tyreus–Luyben; their previously published WP3 gains are **fixed** across mismatched plant cases. WP4 MPC uses the *same* plant, initial state, sample period, integration timestep, setpoint `T_buffer,nominal+0.4K` and disturbance steps. MPC's nominal model is **not secretly changed** to match a perturbed plant.

Two MPC information variants are reported **separately**:

1. **MPC_persistence** — knows present disturbance inputs but assumes they persist over the prediction horizon; it has no future information beyond the present. PI reacts to the current measured state; neither controller has an advance disturbance trajectory.
2. **MPC_advance_forecast** — is handed the true programmed future disturbance trajectory; this is **perfect foresight** and its advantage must never be described as an equal-information result or as a realistic forecast.

The scenarios are passive nominal, passive buffer thermal-capacity −20%, passive compressor thermal-capacity −20%, and bypass with an assumed `UA(f)` exponent 0.8. Neither sensor noise nor measurement delay is included in this WP4 numerical comparison. WP3's richer noise/delay tests have **not** yet been repeated for MPC. A constant assumed electricity price (€0.16/kWh) means these results **cannot** demonstrate tariff arbitrage or price responsiveness in operating data.

The CSV contains tracking IAE, RMSE, energy use, physical heat shortfall, qualified-service fraction, command variation, fallback/rejected solves and energy residuals. **All runs**, including counterexamples, are retained. The high-capacity-reduction and bypass cases may favor PI; an apparent MPC win in nominal conditions is not a robust superiority claim.

## Explicit unverified assumptions

- Synthetic compressor capacity map and second-law COP fraction; no real-fluid TESPy/CoolProp calibration (WP7 remains undone).
- Single local Jacobian held across each *one* horizon, renewed only at the next control update. A large active-set crossing can reject the QP, not produce a guaranteed valid prediction.
- SLSQP is an approximate numerical solver and QP Hessian positivity alone does not prove closed-loop stability.
- No independent measurements, experimental PID tuning, hardware-in-the-loop, startup/shutdown regimes, flow-actuator dynamics, robust invariant-set verification, or actual thermal-storage tariff shifting.
- Synthetic temperature-limit choices, objective weights and controller horizon have not been optimized across plants.

## Test evidence

`tests/test_wp4_mpc.py` includes joint power-Jacobian tests; local discrete predictor fidelity; per-step relinearization; strict trust-region rejection; infeasible solver status; price-weight command sensitivity; bounded PI fallback; full closed-loop energy/slew validation; parameter-mismatch without retuning; zero-tolerance rollout rejection; unsupported disturbance guard; and a deliberate mid-horizon bypass saturation crossing (`f<1` to `f=1`) that is rejected by the nonlinear-rollout check.

This is the first WP4 iteration, **not** completion of WP4's full uncertainty, solver-certification and closed-loop invariance research programme. Before treating MPC as a research comparison baseline, extend WP3's sensing/uncertainty test matrix to WP4 and critically inspect optimization quality and model-validity envelopes.