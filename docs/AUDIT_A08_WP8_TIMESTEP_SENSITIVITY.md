# Audit A08 — WP8 numerical convergence screening

WP8's previously reported nominal daily synthetic tariff difference is
extremely small compared with a 24-hour electricity bill. No real-world
economic claim is justified until sensitivity to simulation accuracy,
equipment uncertainties, tariff conditions and compressor cycling has been
studied independently.

This focused revision repeats the **actual 24-hour CoolProp/IF97 simulation**
at 60, 30 and 15 seconds, with the identical 120-second controller update,
15-minute price event and model settings. All event boundaries are divisible
by each step. The script records both policies' costs, electric energy,
unserved service, final buffer/header inventories and compressor command
state at each step. All independent WP8 service/terminal gates remain in force.

A numerical screening signal is accepted only if:
- Each paired comparison satisfies service, full-horizon, state and tariff gates
- All three eligible savings are positive
- Absolute changes in the saving shrink from 60→30 to 30→15 seconds
- The refined saving exceeds the largest observed discretisation change

This screen is a **necessary diagnostic only**. It is not a Richardson
convergence proof, confidence interval, economic forecast or equipment
performance validation. Physical uncertainty may be much larger than any
numerical error, and the compressor map and 310 kW reference duty remain
hypothetical.

Results are generated and committed only after the dedicated verification
workflow completes; a failed/negative screen is retained rather than erased.
Run locally with `pip install -e ".[realfluid]"` then
`python scripts/run_wp8_timestep.py`. This does not close issue #14;
compressor on/off cycling, dispatch optimisation, robust SOC, realistic
tariffs and cost modelling, source/sink and OEM verification remain open.
