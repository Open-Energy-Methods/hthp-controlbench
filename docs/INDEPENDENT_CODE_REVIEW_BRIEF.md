# Independent code audit brief — WP2 L1 model v0.1

You are reviewing **executed synthetic software**, not a proposed controller or calibrated HTHP. Treat the frozen v0.5 master plan and Claude's v0.5 review as scope references, not authoritative evidence. Run the code/tests and independently reconstruct at least two numbers from first principles. The results in `results/` are illustrative, not laboratory data.

## Task

1. Run `PYTHONPATH=. python -m unittest discover -s tests -v`, `PYTHONPATH=. python -m ht_hp_controlbench`, and `PYTHONPATH=. python scripts/make_report.py` from the ZIP root. Inspect source and tests, not only output logs.
2. Independently check ODE conservation, units, compressor rate vs commanded slew, heat pump boundary/COP assumptions, the two HX service modes, edge handling at `Cr=1`, and the bypass active-set kink. Compare independent rate integration against temperature-capacity energy changes.
3. Verify separate equilibrium points for `no_bypass` and `duty_limiter`. Explain why the dynamic passive steady-state HP duty is approximately 322.641703 kW instead of the older fixed-loss WP1 result 322.636114 kW.
4. Check whether `UA(f)=UA0*f^a` is defensible as a **sensitivity hypothesis only**, and whether the 2.53% valve-position shift exceeds the assumed 1% screening threshold. Check if other parameter uncertainties dominate.
5. Attempt to break the implementation with realistic tests: non-integer sampling ratios, source and return disturbances coinciding with RK4 endpoints, near-thermal-reversal, zero-flow shutdown, large command steps, positive/negative ambient heat loss, bypass saturation, `Cr` near 1 from either capacity-rate side, and temperature/pressure outside plausible water/refrigerant ranges.
6. Evaluate whether the `service_met`/`q_spec_qualified` KPI remains meaningful under excess transfer, tiny numerical shortfall and service-threshold crossing. Propose precision/anti-chatter rules if necessary.
7. Review the actual thermodynamic model's limitations: no real-fluid refrigerant map, fixed thermal capacities, lumped header-buffer exchange, no hot-loop mass-flow/thermal inertia state, and local bypass assumed instantaneous.
8. Report **critical, high, medium, low**, distinguishing errors in already-run nominal results from untested extrapolations and future-stage features.
9. Suggest concrete targeted test/code fixes. Do **not** call the synthetic plant hardware-validated, claim a tuned PID/MPC/SOC already exists, or propose another master-plan rewrite unless a fundamental modelling contradiction demands it.

## Requested response format

- Executive verdict: retain / repair before WP3 / re-architect.
- Independently reproduced numerical values, with code or algebra.
- Failure cases with minimal reproductions.
- Patch recommendations sorted by scientific impact.
- Readiness gates for WP3 and WP4, explicitly separating what is implemented now from what isn't.

The existing v0.5 planning baseline is intentionally frozen; issues discovered in implementation should become code changes, tests, and an evidence/change log rather than an uncontrolled planning version loop.