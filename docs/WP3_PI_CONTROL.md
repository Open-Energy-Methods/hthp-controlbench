# WP3 — independently tuned PI control of a synthetic HTHP thermal plant

**Status:** numerical control-method demonstrator, **not experimental PID tuning**. The underlying compressor capacity, refrigerant COP, UA and two-capacitance thermal dynamics remain synthetic and uncalibrated. There is no hardware, no measured operational data, and no MPC or SOC implementation here.

## Scope and controlled variable

The *actual* compressor modulation `n` follows the bounded, slew-limited command `u` through the WP2 first-order lag (`tau_n=90 s`). WP3 implements a sampled PI temperature controller regulating the **buffer thermal state `T_b`**, using ideal noiseless simulated state measurements. The sample period is 60 s. The default setpoint is the selected synthetic 130°C nominal buffer temperature plus a +0.4 K commanded tracking change. The process fluid's outlet temperature, quality-qualified heat and physical transferred heat are separately evaluated using the unchanged WP2 energy model.

The passive full-flow HX (`no_bypass`) provides a reference process on which both PI identification methods are performed. The more nonlinear, locally bypass-regulated HX is a **transfer/stress test using the very same gains**, not a claim that the passive-plant tuning is universally valid.

## Two independent identification routes

1. **Finite-step FOPDT/IMC:** start from the non-bypass steady state, apply a +0.025 command step (within the 0.05/update slew), simulate until a near-steady plateau is reached, and identify steady gain `K`, the 28.3% and 63.2% rise times, first-order time constant `tau` and apparent dead time `theta`. The 30,000 s identification length is an experiment horizon, *not a project deadline*. Reject un-converged or nonmonotone response. Tune `Kp = tau / [K (lambda + theta)]`, `Ti = tau + theta/2`, `Ki = Kp/Ti`. Evaluate `lambda/tau` in `{0.5, 1, 2}` rather than presenting a deliberately slow IMC reference as the unique optimum.
2. **Sampled relay auto-tuning:** independent nonlinear-plant relay experiment using +/-0.045 command excursion and +/-0.04 K hysteresis. Estimate the period from the final repeated same-direction switches, and approximate `Ku=4d/(pi a)` from observed temperature amplitude `a`; conservatively derive PI via Tyreus–Luyben `Kp=Ku/3.2`, `Ti=2.2 Pu`. This is a sampled-hysteresis **describing-function approximation**; it is **not** a measured ultimate-gain or hardware oscillation test. Hysteresis and sampling may bias `Ku`.

Both gain estimates are logged in `results/wp3_identification.txt`, with units command fraction per kelvin and per kelvin-second. Both methods use the *same* WP2 nonlinear plant; neither is tuned to make MPC look better.

## Controller, safeguards and comparator

Sampled positional PI uses `u_raw=u_ff+Kp(T_b,set-T_b)+I` and `I_next=I+Ki dt e + (dt/tau_track)(u_applied-u_raw)` (`tau_track=360 s` in the initial synthetic test). `u_applied` includes **both magnitude clamp `[0,1]` and slew clamp `0.05/update`**; the initialization is bumpless, `I_0=u_previous-u_ff-Kp e_0`. The *same* command bounds are applied again by the WP2 simulation engine. This anti-windup is a defined strategy, not evidence that all actuator faults are handled.

For each tuning, execute a 4-hour simulated run with the same initial non-bypass steady state, a +0.4 K buffer setpoint change, process return-temperature disturbance at 1h (90 to 92°C; fixed process capacity rate), and source-temperature disturbance at 2h (60 to 55°C). Report IAE [K s], RMSE [K], peak absolute error [K], energy [kWh] and service shortage [kWh] for each tuning. The process bypass mode, with provisional `UA(f)~f^0.8`, is evaluated separately as **cross-mode transfer**, not independent plant calibration.

The first comparison deliberately uses perfect-state feedback and no cost/price optimisation. The energy figures reflect the synthetic heat-pump model. Different physical operating modes transfer different amounts of heat; **do not interpret mode-to-mode electricity figures as controlled efficiency gains**. With identical input scenarios, within-mode comparisons are meaningful as simulation comparisons only.

## Acceptance evidence

- WP2 physics tests remain passing; new tests exercise identification, tuning formulas, PID sign/units, anti-windup, bumpless initialization, hard input/slew limits, energy conservation, closed-loop disturbances and cross-mode transfer.
- CSV and results report are reproducible using `python scripts/run_wp3.py` after `pip install -e '.[plots]'` or `PYTHONPATH=.`.
- WP3 is a **PI** implementation (derivative action has not been implemented); it does not close the actual experimental PID-tuning requirement of the SINTEF vacancy.
- These are initial synthetic demonstrations, not proof of robust control: no measurement noise, sensor dropout, controller delay, actuator uncertainty, multiple plant-parameter sweeps, real process setpoints or experimental validation have been established.

## Next WP3 validation before comparison to MPC

Evaluate tuning under a specified envelope of thermal capacitance, HX UA, compressor lag and source temperature; add measurement-noise/dead-time variants using a distinct observation layer; report control effort, saturation counts, and a stability/robustness margin study. Freeze a fair tuned baseline using those results, rather than assuming the relay tuning that wins the present scenario is optimal for every disturbance.