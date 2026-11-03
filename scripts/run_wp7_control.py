"""Generate a REVIEWABLE, synthetic-assumption WP7 controller pilot.

No HW claim; every run uses exactly one property-backed truth plant. WP2 gains
are frozen and no scenario tuning is permitted. Results remain ineligible for
control superiority statements unless BOTH controllers provide full service.
"""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import csv
import json

from ht_hp_controlbench.benchmark import nominal_tunings, tuning_manifest
from ht_hp_controlbench.realfluid import CycleAssumptions, build_cycle_map, backend_version
from ht_hp_controlbench.wp7_control import (
    BENCHMARK, declared_property_cases, run_property_controller
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results"
METHODS = ("PI_IMC", "PI_relay", "MPC_persistence")


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    tuning,step,relay=nominal_tunings()
    model=build_cycle_map(
        "R1233zd(E)",
        sources=(328.15,333.15,338.15),
        headers=(398.15,403.15,406.2,410.15,413.15),
        modulations=(.5,.75,1.0),
        assumptions=CycleAssumptions(),
    )
    cases=declared_property_cases()
    runs=[]
    for case in cases:
        for method in METHODS:
            setting = tuning["relay_PI"] if method=="PI_relay" else tuning["IMC_lambda_0p5tau"]
            result=run_property_controller(model,case,method,pi_settings=setting)
            runs.append(result)
            print(case.name,method,result["status"],"IAE",result["iae_Ks"],
                  "unserved",result["unserved_spec_heat_kWh"],
                  "fallbacks",result["pi_fallbacks"],flush=True)
    pairs=[]
    for case in cases:
        entry={r["controller"]:r for r in runs if r["case"]==case.name}
        for method in ("PI_IMC","PI_relay"):
            base=entry[method];candidate=entry["MPC_persistence"]
            complete=base["status"]=="complete" and candidate["status"]=="complete"
            qualified=complete and base["matched_service_gate"] and candidate["matched_service_gate"]
            pairs.append({
                "case":case.name,"baseline":method,"candidate":"MPC_persistence",
                "both_numerically_complete":complete,
                "both_service_eligible":qualified,
                "delta_IAE_Ks":candidate["iae_Ks"]-base["iae_Ks"] if complete else None,
                "delta_electricity_kWh":candidate["electricity_kWh"]-base["electricity_kWh"] if qualified else None,
                "interpretation":("conditional_same_service_comparison" if qualified else
                                 "NOT_ELIGIBLE_FOR_ENERGY_SAVING_CLAIM"),
            })
    if len(runs)!=len(cases)*len(METHODS):
        raise RuntimeError("incomplete WP7 scenario-method enumeration")
    ledger={
        "benchmark_id":BENCHMARK,
        "scientific_status":"UNCALIBRATED PROPERTY-BACKED TRUTH, SYNTHETIC WP2 PREDICTOR; NO EQUIPMENT VALIDATION",
        "fluid":model.fluid,
        "coolprop_version":backend_version(),
        "water_pressure_assumed_pa":model.assumptions.service_header_pressure_pa,
        "reference_volume_m3_s_inferred_from_310kW":model.equivalent_full_speed_suction_volume_m3_s,
        "property_grid":{"source_K":model.t_sources_k,"header_K":model.t_headers_k,"modulation":model.modulations},
        "sampling":{"integration_s":20,"sensor_s":60,"control_s":120,"horizon_steps":6,"duration_s":7200},
        "controller_tuning":tuning_manifest(tuning,step,relay),
        "scenarios":[asdict(c) for c in cases],
        "run_count":len(runs),
        "completed_runs":sum(r["status"]=="complete" for r in runs),
        "failed_runs":[{"case":r["case"],"controller":r["controller"],"reason":r["failure_reason"]}
                       for r in runs if r["status"]!="complete"],
        "service_eligible_pairs":sum(p["both_service_eligible"] for p in pairs),
        "runs":runs,"paired":pairs,
        "claim_boundary":"not an independently calibrated compressor, formal MPC design, robust stability proof, tariff saving, or process safety certification",
    }
    (OUT/"wp7_control_pilot.json").write_text(json.dumps(ledger,indent=2,allow_nan=False)+"\n")
    fields=["benchmark_id","case","controller","status","failure_reason","completed_time_s",
            "duration_s","sensor_noise_sd_k","sensor_delay_s","seed","decisions","accepted_mpc",
            "pi_fallbacks","iae_Ks","electricity_kWh","process_heat_kWh",
            "physical_heat_shortfall_kWh","unserved_spec_heat_kWh","qualified_fraction",
            "matched_service_gate","max_energy_residual_J","max_applied_command_slew",
            "max_sensor_error_K","max_header_observer_error_K","max_modulation_observer_error"]
    with (OUT/"wp7_control_pilot.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        writer.writeheader();writer.writerows(runs)
    with (OUT/"wp7_control_pairs.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    lines=[
        "# WP7: matched property-backed PI/MPC control pilot", "",
        f"**Benchmark:** `{BENCHMARK}`. **{ledger['completed_runs']}/{len(runs)} full-horizon runs completed**.",
        f"**{ledger['service_eligible_pairs']}/{len(pairs)} comparisons** pass the strict full-service eligibility gate.",
        "",
        "## What is and is not matched", "",
        "- PI and MPC use the SAME property-derived refrigerant heat/electricity lookup, IF97 water enthalpy, thermal conductances, actuator lag, numerical timestep and process heat demand.",
        "- Both use a single sampled buffer-temperature sensor, paired noise seed, identical delay, current known disturbances and 120-second command clock.",
        "- MPC predicts on the older, uncalibrated WP2 *synthetic* model. The observer propagates its unmeasured states using that model without accessing the true header temperature or compressor modulation after initialization.",
        "- PI gains are fixed from the WP3 nominal identification. MPC QP structure/weights are frozen before these scenarios; no calibration on the 5 cases.",
        "- Every property-map extrapolation or water-pressure phase failure stops that run. Such incomplete runs cannot be ranked.",
        "- A zero heat shortage in a simplified synthetic process does not establish guaranteed commercial heat service.",
        "", "## Run ledger", "",
        "| Scenario | Controller | Status | IAE (K s) | Electricity (kWh) | Spec-unserved (kWh) | Fallbacks |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in runs:
        def fmt(k):
            x=r[k]
            return "—" if x is None else f"{x:.3f}"
        lines.append(f"| {r['case']} | {r['controller']} | {r['status']} | {fmt('iae_Ks')} | "
                     f"{fmt('electricity_kWh')} | {fmt('unserved_spec_heat_kWh')} | {r['pi_fallbacks']} |")
    lines.extend(["","## Matched paired interpretations","",
                  "Electricity comparisons are reported only when both runs are numerically complete and meet the full simulated service gate. No tariff, OEM capacity or statistical confidence claim is made.","",
                  "| Scenario | PI baseline | Both service eligible? | ΔIAE (K s) | Conditional Δelectricity (kWh) |",
                  "|---|---|---|---:|---:|"])
    for row in pairs:
        da=row["delta_IAE_Ks"];de=row["delta_electricity_kWh"]
        lines.append(f"| {row['case']} | {row['baseline']} | {row['both_service_eligible']} | "
                     f"{'—' if da is None else f'{da:.3f}'} | "
                     f"{'—' if de is None else f'{de:.3f}'} |")
    lines.extend(["","## Limits and next experiments","",
                  "This is a **limited numerical transfer test**, not a validated property-predictor MPC: the MPC uses the same historical synthetic WP2 predictor. The property map itself is a hypothetical displacement/efficiency surrogate derived from the target 310 kW reference output, not manufacturer data.",
                  "Before credible controller conclusions: introduce a property-consistent predictive model, independent observer validation, tighter holds, multiple out-of-training sensor/actuator disturbances, explicit constraint and solver logging, a finite source/sink hydraulic model and measured OEM envelopes.",
                  "",
                  "Reproduce: `python scripts/run_wp7_control.py` with CoolProp/OSQP extras; run the WP7 controller unit/integration tests first.",
                  ""])
    (OUT/"wp7_control_pilot_report.md").write_text("\n".join(lines))
    print("WP7 property-backed control pilot written:",ledger["completed_runs"],"complete,",ledger["service_eligible_pairs"],"qualified pairs")


if __name__=="__main__":
    main()
