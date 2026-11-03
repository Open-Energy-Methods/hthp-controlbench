"""WP7 v2: side-by-side, no-retune test of property-consistent MPC.

Reproduces the prepublished v1 PI controls with a different (property)
observer using the SAME actual truth plant, sensor draws and gains. Then
compares v1 synthetic-predictor MPC and v2 property-predictor MPC against
identical v1 PI baselines. Original v1 results remain immutable.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import csv
import json
from math import isclose

from ht_hp_controlbench.benchmark import nominal_tunings
from ht_hp_controlbench.realfluid import CycleAssumptions, build_cycle_map, backend_version
from ht_hp_controlbench.wp7_control import (
    PropertyControlCase, compare_property_pair, declared_property_cases,
    run_property_controller,
)

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results"
SOURCE=OUT/"wp7_control_pilot.json"
BENCHMARK_V2="WP7_PropertyPredictor_MPC_Observer_v2"


def _check_reproduced_pi(previous:dict,current:dict):
    for key in ("case","controller","seed","duration_s","sensor_noise_sd_k",
                "sensor_delay_s","noise_draws","true_states_at_decisions",
                "sensed_buffer_at_decisions","applied_commands","status",
                "accepted_mpc","pi_fallbacks"):
        if previous[key]!=current[key]:
            raise RuntimeError(f"WP7 v1 baseline changed unexpectedly: {key}")
    for key in ("iae_Ks","electricity_kWh","process_heat_kWh",
                "unserved_spec_heat_kWh","qualified_fraction",
                "final_total_energy_delta_kWh","final_header_energy_delta_kWh",
                "final_buffer_energy_delta_kWh","final_compressor_modulation"):
        x,y=previous[key],current[key]
        if x is None or y is None:
            if x!=y:raise RuntimeError(f"WP7 v1 missing baseline mismatch: {key}")
        elif not isclose(x,y,abs_tol=1e-8,rel_tol=1e-12):
            raise RuntimeError(f"WP7 v1 KPI drift: {key}: {x} vs {y}")


def main():
    if not SOURCE.exists():
        raise FileNotFoundError("Published WP7 v1 ledger is required to freeze reference results")
    old_bytes=SOURCE.read_bytes()
    old=json.loads(old_bytes)
    if old["benchmark_id"]!="WP7_PropertyTruth_SyntheticPredictor_Pilot_v1":
        raise RuntimeError("wrong reference benchmark")
    old_by={(r["case"],r["controller"]):r for r in old["runs"]}
    if len(old_by)!=15:
        raise RuntimeError("v1 published 15-run case matrix is incomplete")
    tuning,_,_=nominal_tunings()
    model=build_cycle_map(
        "R1233zd(E)",
        sources=(328.15,333.15,338.15),
        headers=(398.15,403.15,406.2,410.15,413.15),
        modulations=(.5,.75,1.0),
        assumptions=CycleAssumptions(),
    )
    cases=declared_property_cases()
    new_runs=[];pairs=[];transfers=[]
    for case in cases:
        baseline={}
        for method in ("PI_IMC","PI_relay"):
            settings=tuning["relay_PI"] if method=="PI_relay" else tuning["IMC_lambda_0p5tau"]
            row=run_property_controller(model,case,method,pi_settings=settings,
                                        observer_backend="property")
            _check_reproduced_pi(old_by[(case.name,method)],row)
            baseline[method]=row
            new_runs.append(row)
        property_mpc=run_property_controller(
            model,case,"MPC_property",pi_settings=tuning["IMC_lambda_0p5tau"],
            observer_backend="property")
        new_runs.append(property_mpc)
        old_mpc=old_by[(case.name,"MPC_persistence")]
        for method in ("PI_IMC","PI_relay"):
            bp=baseline[method]
            pair=compare_property_pair(bp,property_mpc)
            pairs.append(pair)
        # Preserve old MPC published results exactly, report the unqualified
        # raw change separately from any service/inventory-qualified claim.
        transfers.append({
            "case":case.name,
            "old_mpc_status":old_mpc["status"],
            "property_mpc_status":property_mpc["status"],
            "old_mpc_iae_Ks":old_mpc["iae_Ks"],
            "property_mpc_iae_Ks":property_mpc["iae_Ks"],
            "old_mpc_electricity_kWh":old_mpc["electricity_kWh"],
            "property_mpc_electricity_kWh":property_mpc["electricity_kWh"],
            "old_mpc_fallbacks":old_mpc["pi_fallbacks"],
            "property_mpc_fallbacks":property_mpc["pi_fallbacks"],
            "old_mpc_accepted":old_mpc["accepted_mpc"],
            "property_mpc_accepted":property_mpc["accepted_mpc"],
            "property_mpc_header_observer_mae_K":property_mpc["mean_absolute_header_observer_error_K"],
            "property_mpc_modulation_observer_mae":property_mpc["mean_absolute_modulation_observer_error"],
            "status":"descriptive_transfer_only__NOT_independent_machine_validation",
        })
        print(case.name,property_mpc["status"],
              "IAE",property_mpc["iae_Ks"],
              "fallback",property_mpc["pi_fallbacks"],flush=True)
    if len(new_runs)!=15 or len(pairs)!=10:
        raise RuntimeError("WP7 v2 5x3 experiment matrix is incomplete")
    ledger={
        "benchmark_id":BENCHMARK_V2,
        "reference_benchmark_id":old["benchmark_id"],
        "reference_file":str(SOURCE.relative_to(ROOT)),
        "reference_sha256":sha256(old_bytes).hexdigest(),
        "fixed_model":"WP7 R1233zd(E) condenser Q/P map + IF97 enthalpy, same as v1 truth",
        "predictor":"WP7 property-backed RK4 enthalpy in WP4 locally linearized MPC QP",
        "observer":"property-backed open-loop observer, 60s buffer samples only, no truth-header/actuator access",
        "property_model_verified_against_hardware":False,
        "property_backend_version":backend_version(),
        "model_origin":"assumed 310kW/75% displacement, constant eta_is, 6 bar reference water",
        "scenarios":[asdict(x) for x in cases],
        "freeze":"same v1 case matrix, gains, solver weights and 120s update clock; no holdout tuning",
        "reference_matched_pi_checks":"all original PI trajectories/noise/sensors/energy metrics reproduce exactly",
        "run_count":len(new_runs),
        "complete_run_count":sum(r["status"]=="complete" for r in new_runs),
        "service_eligible_pairs":sum(r["both_service_eligible"] for r in pairs),
        "terminal_comparable_pairs":sum(r["eligible_for_conditional_electricity_comparison"] for r in pairs),
        "runs":new_runs,"pairs":pairs,"old_vs_new_mpc":transfers,
    }
    OUT.mkdir(exist_ok=True)
    (OUT/"wp7_property_predictor_v2.json").write_text(json.dumps(ledger,indent=2,allow_nan=False)+"\n")
    with (OUT/"wp7_property_predictor_v2_pairs.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(pairs[0]))
        writer.writeheader();writer.writerows(pairs)
    with (OUT/"wp7_property_predictor_v2_transfer.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(transfers[0]))
        writer.writeheader();writer.writerows(transfers)
    lines=[
        "# WP7 v2: property-consistent predictive control and observer cross-check",
        "",
        f"**{ledger['complete_run_count']}/15 complete**, **{ledger['service_eligible_pairs']}/10 service-qualified pairs**,",
        f"**{ledger['terminal_comparable_pairs']}/10 also terminal-inventory/actuator matched**.",
        "",
        "## Protocol",
        "",
        "Same uncalibrated WP7 physical truth, setpoints, noise seeds, disturbance history,",
        "fixed nominal WP3 PI gains and WP4 MPC QP weights/solver as v1.",
        "The v1 15-run published source is SHA-256 frozen and all 10 PI physical",
        "trajectories, sampled observations and energy KPIs are reproduced before",
        "any result is written.",
        "",
        "**Changed variable:** the observer and MPC's state/power predictor both",
        "use the property-backed IF97 enthalpy and CoolProp condenser map,",
        "rather than the WP2 synthetic surrogate. The QP remains local and",
        "may reject infeasible/nonlinear rollouts or fall back to PI.",
        "",
        "| Scenario | Old MPC IAE (K s) | New MPC IAE (K s) | Old fallbacks | New fallbacks | New header observer MAE (K) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for t in transfers:
        def n(v):
            return "—" if v is None else f"{v:.4f}"
        lines.append(f"| {t['case']} | {n(t['old_mpc_iae_Ks'])} | {n(t['property_mpc_iae_Ks'])} | "
                     f"{t['old_mpc_fallbacks']} | {t['property_mpc_fallbacks']} | "
                     f"{n(t['property_mpc_header_observer_mae_K'])} |")
    lines.extend(["","## Electricity-comparison eligibility", "",
          "Numerical completeness and simulated full service are *insufficient* for electricity savings;",
          "the final header thermal energy, IF97 buffer inventory, total inventory and final",
          "compressor modulation/command must also match within declared numerical limits.",
          "Ineligible entries are left null; no forced ranking.", "",
          "| Scenario | PI baseline | Complete? | Service? | Terminal match? | ΔIAE new MPC–PI (K s) | Eligible Δelectricity (kWh) |",
          "|---|---|---|---|---|---:|---:|"])
    for x in pairs:
        def n(v):return "—" if v is None else f"{v:.4f}"
        lines.append(f"| {x['case']} | {x['baseline']} | {x['both_numerically_complete']} | "
                     f"{x['both_service_eligible']} | {x['terminal_equivalent']} | "
                     f"{n(x['delta_IAE_Ks'])} | {n(x['delta_electricity_kWh'])} |")
    lines.extend(["","## Evidence boundaries","",
          "This is an internal numerical agreement and model-transfer study, not",
          "an independent measured observer dataset or calibrated industrial model.",
          "Both physical truth and model are derived from the same assumed CoolProp",
          "and IF97 physics; matching a model to its own equations is not empirical validation.",
          "No OEM compressor, finite source/sink, oil envelope, pressure rating,",
          "robust MPC stability or financial savings claim.",
          "Adverse solver fallbacks and nonqualified cases remain in the ledger.",""])
    (OUT/"wp7_property_predictor_v2_report.md").write_text("\n".join(lines))
    print("WP7 property-predictor transfer:",ledger["complete_run_count"],
          "complete,",ledger["terminal_comparable_pairs"],"electricity comparable pairs")
    return ledger


if __name__=="__main__":
    main()
