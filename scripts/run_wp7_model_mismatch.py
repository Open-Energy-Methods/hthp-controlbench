"""WP7 v3: frozen-controller model/plant mismatch stress test for SINTEF sample.

Physics and baseline are explicitly uncalibrated. This experiment perturbs
only TRUTH thermal conductance/process UA/compressor lag; the nominal
property-MPC predictor, observer, PI gains, QP weights, motor bounds and
sensing remain frozen. No real failure probability or equipment validation.
Results never overwrite v1/v2.
"""
from __future__ import annotations

from dataclasses import dataclass,asdict,replace
from hashlib import sha256
from math import isclose
from pathlib import Path
import csv
import json

from ht_hp_controlbench.benchmark import nominal_tunings
from ht_hp_controlbench.core import Parameters
from ht_hp_controlbench.realfluid import CycleAssumptions,build_cycle_map,backend_version,PointRejected
from ht_hp_controlbench.wp7_control import (
    PropertyControlCase,compare_property_pair,run_property_controller,
)

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results"
PRIOR=OUT/"wp7_property_predictor_v2.json"
ID="WP7_NominalPredictor_TruthParameterMismatch_Holdout_v3"
METHODS=("PI_IMC","PI_relay","MPC_property")


@dataclass(frozen=True)
class MismatchSpec:
    case: PropertyControlCase
    truth_parameter: str|None
    truth_scale: float

    def __post_init__(self):
        if self.truth_parameter not in (None,"ua_proc","khb","tau_n"):
            raise ValueError("undeclared truth parameter mismatch")
        if self.truth_parameter is None and self.truth_scale!=1.:
            raise ValueError("nominal anchor requires unit scale")
        if not (.5<=self.truth_scale<=1.5):
            raise ValueError("out of declared exploratory perturbation envelope")


def declared_holdout() -> tuple[MismatchSpec,...]:
    """Frozen *design-of-experiments*, not a search for favourable rankings."""
    return (
        MismatchSpec(PropertyControlCase("nominal"),None,1.),
        MismatchSpec(PropertyControlCase("ua_proc_minus15_source_drop3",
                    source_drop_k=3.),"ua_proc",.85),
        MismatchSpec(PropertyControlCase("ua_proc_plus15_noisy_delayed",
                    sensor_noise_sd_k=.20,sensor_delay_samples=1,seed=71),
                    "ua_proc",1.15),
        MismatchSpec(PropertyControlCase("compressor_lag_plus30_source_drop3",
                    source_drop_k=3.,seed=83),"tau_n",1.30),
        MismatchSpec(PropertyControlCase("header_buffer_khb_minus15_combined",
                    sensor_noise_sd_k=.20,sensor_delay_samples=1,
                    source_drop_k=3.,return_rise_k=1.,seed=97),
                    "khb",.85),
    )


def strict_nominal_reproduction(old:dict, new:dict) -> dict:
    """Explicitly audit nominal reproducibility, never retune controller.

    The first cross-environment run found ~5.6e-6 K difference in MPC
    trajectory under SLSQP (PI was bitwise identical). Hence MPC numerical
    outputs have explicit, conservative absolute thresholds, reported as
    maximum observed drift; method/solver decisions MUST match exactly.
    These tolerances were set AFTER diagnosing this observed drift and are
    not advertised as preregistered scientific acceptance intervals.
    """
    import numpy as np

    method=new["controller"]
    fields=("case","controller","duration_s","sensor_noise_sd_k",
            "sensor_delay_s","seed","noise_draws","true_states_at_decisions",
            "estimated_states_at_decisions","sensed_buffer_at_decisions",
            "applied_commands","status","pi_fallbacks","accepted_mpc",
            "solver_statuses")
    trace_tols={
        "true_states_at_decisions":[1e-4,1e-4,1e-5],
        "estimated_states_at_decisions":[1e-4,1e-4,1e-5],
        "sensed_buffer_at_decisions":[1e-4],
        "applied_commands":[0.,1e-5],
    }
    metric_tols={
        "iae_Ks":.1,
        "electricity_kWh":.0001,
        "process_heat_kWh":.0001,
        "unserved_spec_heat_kWh":.0001,
        "final_total_energy_delta_kWh":.0001,
        "final_header_energy_delta_kWh":.0001,
        "final_buffer_energy_delta_kWh":.0001,
        "max_header_observer_error_K":.0001,
        "max_modulation_observer_error":1e-5,
    }
    differences={}
    for key in fields:
        # v2 persisted Python tuples as JSON arrays; normalization is lossless.
        normalized=json.loads(json.dumps(new[key],allow_nan=False))
        if old[key]==normalized:
            differences[key]=0.
            continue
        if method!="MPC_property" or key not in trace_tols:
            raise RuntimeError(f"WP7 v2 nominal structural/PI regression: method={method} key={key}")
        av=np.asarray(old[key],dtype=float)
        bv=np.asarray(normalized,dtype=float)
        if av.shape!=bv.shape:
            raise RuntimeError(f"WP7 v2 nominal MPC shape changed: {key}")
        delta=np.abs(av-bv)
        if not np.all(np.isfinite(delta)):
            raise RuntimeError(f"nonfinite nominal reproducibility delta: {key}")
        tolerances=np.asarray(trace_tols[key],dtype=float)
        if delta.ndim==1:
            allowed=tolerances[0]
        else:
            if len(tolerances)!=delta.shape[1]:
                raise RuntimeError("invalid nominal comparison tolerance shape")
            allowed=tolerances[None,:]
        if np.any(delta>allowed):
            raise RuntimeError(f"WP7 v2 nominal MPC trace drift exceeds tolerance "
                f"key={key} max_abs={float(np.max(delta))}")
        differences[key]=float(np.max(delta))
    for key, tolerance in metric_tols.items():
        a,b=old[key],new[key]
        if a is None or b is None:
            if a!=b:
                raise RuntimeError(f"WP7 v2 nominal missing metric mismatch: {key}")
            differences[key]=0.
            continue
        delta=abs(float(a)-float(b))
        if method!="MPC_property" and delta!=0:
            raise RuntimeError(f"WP7 v2 nominal PI KPI not bitwise reproduced: {key}, delta={delta}")
        if delta>tolerance:
            raise RuntimeError(f"WP7 v2 nominal MPC KPI drift outside tolerance: {key}, delta={delta}, limit={tolerance}")
        differences[key]=delta
    return {"method":method,"max_observed_absolute_drift_by_field":differences,
            "MPC_tolerances_selected_after_diagnosed_solver_drift":method=="MPC_property"}


def unqualified_initial_state(spec:MismatchSpec,method:str,reason:str) -> dict:
    """Structured rejection, NOT a partial/zero-energy physical simulation.

    Only documented no-service starting-equilibrium rejections are mapped to
    this record. Every other unexpected solver/property exception fails CI.
    """
    if not reason.startswith("no_property_backed_initial_equilibrium:"):
        raise RuntimeError("unexpected initial failure must not be hidden: "+reason)
    return {
        "benchmark_id":ID,
        "case":spec.case.name,
        "controller":method,
        "plant":"WP7 CoolProp condenser Q/P map + IF97 enthalpy; UNCALIBRATED"
                " | truth-only HX/actuator-dynamics mismatch",
        "measurement":"one sampled noisy/delayed buffer temperature; current known disturbances",
        "equipment_verified":False,
        "truth_model_mismatch":True,
        "truth_parameter_ratios_to_nominal":{spec.truth_parameter:spec.truth_scale},
        "status":"unqualified_initial_design_state",
        "failure_reason":reason,
        "duration_s":7200.,
        "sample_period_s":60.,
        "control_period_s":120.,
        "sensor_delay_s":spec.case.sensor_delay_samples*60.,
        "sensor_noise_sd_k":spec.case.sensor_noise_sd_k,
        "seed":spec.case.seed,
        "completed_time_s":0.,
        "matched_service_gate":False,
        "decisions":0,
        "accepted_mpc":0,
        "pi_fallbacks":0,
        "solver_statuses":{},
        "iae_Ks":None,
        "electricity_kWh":None,
        "process_heat_kWh":None,
        "unserved_spec_heat_kWh":None,
        "physical_heat_shortfall_kWh":None,
        "qualified_fraction":None,
        "final_header_energy_delta_kWh":None,
        "final_buffer_energy_delta_kWh":None,
        "final_total_energy_delta_kWh":None,
        "final_compressor_modulation":None,
        "final_applied_command":None,
        "max_energy_residual_J":None,
        "max_applied_command_slew":0.,
        "max_sensor_error_K":None,
        "max_header_observer_error_K":None,
        "max_modulation_observer_error":None,
        "mean_absolute_header_observer_error_K":None,
        "mean_absolute_modulation_observer_error":None,
        "sensor_innovations_K":[],
        "noise_draws":[],
        "true_states_at_decisions":[],
        "estimated_states_at_decisions":[],
        "sensed_buffer_at_decisions":[],
        "applied_commands":[],
    }


def main():
    source_bytes=PRIOR.read_bytes()
    old=json.loads(source_bytes)
    if old["benchmark_id"]!="WP7_PropertyPredictor_MPC_Observer_v2":
        raise RuntimeError("v3 requires specifically the published v2 ledger")
    by_old={(r["case"],r["controller"]):r for r in old["runs"]}
    if len(by_old)!=15:
        raise RuntimeError("incomplete published v2 controller/case matrix")
    tuning,_,_=nominal_tunings()
    model=build_cycle_map("R1233zd(E)",sources=(328.15,333.15,338.15),
        headers=(398.15,403.15,406.2,410.15,413.15),
        modulations=(.5,.75,1.0),assumptions=CycleAssumptions())
    nominal_p=replace(Parameters(hx_mode="duty_limiter"),
                      n_min=model.modulations[0],n_max=model.modulations[-1])
    runs=[];pairs=[];records=[];anchor_audits=[]
    for spec in declared_holdout():
        p_truth=(
            replace(nominal_p,**{spec.truth_parameter:
                getattr(nominal_p,spec.truth_parameter)*spec.truth_scale})
            if spec.truth_parameter is not None else None
        )
        for method in METHODS:
            setting=tuning["relay_PI"] if method=="PI_relay" else tuning["IMC_lambda_0p5tau"]
            try:
                row=run_property_controller(model,spec.case,method,
                    pi_settings=setting,observer_backend="property",
                    truth_parameters=p_truth,benchmark_id=ID)
            except PointRejected as exc:
                # The -15% UA condition cannot deliver qualified service at
                # the fixed initial buffer temperature. The paper must report
                # this negative feasibility result, not lower the workload
                # or synthesize a controller performance score.
                row=unqualified_initial_state(spec,method,str(exc))
            if spec.truth_parameter is None:
                anchor_audits.append(strict_nominal_reproduction(by_old[("nominal",method)],row))
            if row["status"]=="complete":
                if row["max_energy_residual_J"]>=1.:
                    raise RuntimeError("invalid accepted conservation residual")
                if row["max_applied_command_slew"]>nominal_p.max_command_step+1e-8:
                    raise RuntimeError("command slew violation")
            else:
                if row["iae_Ks"] is not None or row["electricity_kWh"] is not None:
                    raise RuntimeError("partial failed trajectory incorrectly ranked")
            runs.append(row)
            print(f"{spec.case.name:<42} {method:<14} status={row['status']} "
                  f"IAE={row['iae_Ks']} fallbacks={row['pi_fallbacks']}",flush=True)
        group={r["controller"]:r for r in runs[-3:]}
        for method in ("PI_IMC","PI_relay"):
            pair=compare_property_pair(group[method],group["MPC_property"])
            pairs.append(pair)
            records.append({
                "case":spec.case.name,
                "truth_parameter":spec.truth_parameter or "nominal",
                "truth_scale":spec.truth_scale,
                "pi_method":method,
                "pi_status":group[method]["status"],
                "mpc_status":group["MPC_property"]["status"],
                "mpc_solver_fallbacks":group["MPC_property"]["pi_fallbacks"],
                "mpc_header_observer_mae_K":group["MPC_property"]["mean_absolute_header_observer_error_K"],
                "mpc_max_header_observer_error_K":group["MPC_property"]["max_header_observer_error_K"],
                "pair_complete":pair["both_numerically_complete"],
                "pair_service_qualified":pair["both_service_eligible"],
                "pair_terminal_equivalent":pair["terminal_equivalent"],
                "electricity_comparison_eligible":pair["eligible_for_conditional_electricity_comparison"],
                "delta_tracking_iae_Ks":pair["delta_IAE_Ks"],
                "eligible_delta_electricity_kWh":pair["delta_electricity_kWh"],
                "ineligibility_reasons":pair["ineligibility_reasons"],
            })
    if len(runs)!=15 or len(pairs)!=10:
        raise RuntimeError("expected 5 truth variants x 3 controllers x 2 PI comparisons")
    data={
        "benchmark_id":ID,
        "reference_v2_sha256":sha256(source_bytes).hexdigest(),
        "reference_v2":str(PRIOR.relative_to(ROOT)),
        "assumptions":"Uncalibrated truth property map, nominal synthetic control gains, "
                      "lumped truth-only UA or lag perturbation; NOT OEM uncertainty distributions",
        "model_truth_independence":"Only UA/khb/tau_n differs. Both models share an uncalibrated "
                      "CoolProp condenser map, IF97 EOS and assumed fluid/device envelope.",
        "no_model_or_gain_retuning":True,
        "same_sensing_same_command_limits":True,
        "property_model_verified_against_hardware":False,
        "coolprop_version":backend_version(),
        "nominal_anchor_v2_reproduced_with_tolerances":True,
        "nominal_anchor_v2_audit":anchor_audits,
        "cases":[{"case":asdict(s.case),"truth_parameter":s.truth_parameter,
                  "truth_scale":s.truth_scale} for s in declared_holdout()],
        "runs":runs,"pairs":pairs,"rows":records,
        "complete_runs":sum(r["status"]=="complete" for r in runs),
        "service_eligible_pairs":sum(p["both_service_eligible"] for p in pairs),
        "terminal_electricity_comparable_pairs":
            sum(p["eligible_for_conditional_electricity_comparison"] for p in pairs),
    }
    OUT.mkdir(exist_ok=True)
    (OUT/"wp7_model_mismatch_v3.json").write_text(
        json.dumps(data,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    with (OUT/"wp7_model_mismatch_v3_pairs.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
    lines=[
        "# WP7 v3 — model/plant mismatch: frozen PI versus property MPC",
        "",
        "**Exploratory numerical model mismatch — NOT measured equipment uncertainty, "
        "not independent OEM data, not evidence of robust stability.**","",
        f"All {len(runs)} frozen-controller runs evaluated. "
        f"**{data['complete_runs']}/15 numerically complete**, "
        f"**{data['service_eligible_pairs']}/10 service-qualified pairs**, "
        f"**{data['terminal_electricity_comparable_pairs']}/10 also terminal-equivalent "
        "for conditional electricity comparison.**","",
        "## Protocol","",
        "Identical CoolProp/IF97 property map, actuator bounds/slew, setpoint, "
        "single buffer sensor, sampled noise and delay (same seed per pair), "
        "120s control updates, frozen WP3 PI gains, frozen WP4 local-QP MPC "
        "settings and property-model observer. The **truth** alone uses the "
        "declared alternate HX process UA, header–buffer conductance, or compressor "
        "lag; predictor remains nominal. All variants have their own equal-service "
        "reference initialization. The nominal case must reproduce *every* "
        "published v2 PI physical/control trace and KPI exactly; the MPC "
        "is compared with explicit strict float tolerances. The first cross-"
        "environment replay exposed a 5.6e-6 K nominal MPC trajectory "
        "difference. Tolerances were introduced after diagnosing that "
        "difference; they are not preregistered physical error margins. "
        "All solver statuses and accepted step counts must still match.","",
        "These ±15% / +30% perturbations are **chosen illustrative errors**, "
        "not manufacturer tolerances or confidence intervals. The error family "
        "does not include a perturbed compressor Q/P map, compressor oil, finite "
        "water source/sink, or calibrated sensor bias.","",
        "## Paired results (MPC minus PI)","",
        "| True plant scenario | PI comparator | Complete | Same qualified service | Terminal match | ΔIAE K·s | Δelectricity kWh if eligible | MPC fallbacks |",
        "|---|---|---|---|---|---:|---:|---:|",
    ]
    fmt=lambda x:"—" if x is None else f"{x:.3f}"
    for x in records:
        lines.append(
            f"| {x['case']} | {x['pi_method']} | {x['pair_complete']} | "
            f"{x['pair_service_qualified']} | {x['pair_terminal_equivalent']} | "
            f"{fmt(x['delta_tracking_iae_Ks'])} | "
            f"{fmt(x['eligible_delta_electricity_kWh'])} | "
            f"{x['mpc_solver_fallbacks']} |"
        )
    lines.extend(["","The electricity eligibility gate is unchanged from WP7 v2: both "
        "controllers must finish the *entire* run, deliver qualified service, "
        "and have final header/buffer/total thermal inventories (0.5 kWh) "
        "and actual/final commanded modulation (0.02) within the same tolerances. "
        "Pairs that fail any gate receive **null**, not zero savings.",
        "No tuning or scenario selection was based on these outcomes.","",
        "## Interpretation","",
        "This test demonstrates sensitivity to deliberately perturbed "
        "lumped-parameter physics, not predictive accuracy on a real HTHP. "
        "Neither nominal nor perturbed model has independent OEM calibration. "
        "Small tracking errors do not imply a lower electricity bill. "
        "Instrumented validation, additional out-of-sample source/sink bounds, "
        "model identification, uncertainty intervals and pilot trials are "
        "requirements for any industrial claim.","",
        "Raw machine-readable histories, controller fallback statuses and exact "
        "comparator gates are in [the v3 JSON](wp7_model_mismatch_v3.json). "
        "Reproduce with `python scripts/run_wp7_model_mismatch.py` "
        "after `pip install -e '.[realfluid,qp]'`.","",
    ])
    (OUT/"wp7_model_mismatch_v3_report.md").write_text("\n".join(lines),encoding="utf-8")
    print("WP7 mismatch:",data["complete_runs"],"complete;",
          data["service_eligible_pairs"],"service pairs;",
          data["terminal_electricity_comparable_pairs"],"electricity-eligible pairs")
    return data


if __name__=="__main__":
    main()
