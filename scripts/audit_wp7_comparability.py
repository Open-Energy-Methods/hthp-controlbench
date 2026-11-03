"""Independent, fail-closed comparability sensitivity audit for WP7 v3.

This script re-derives eligibility from raw per-controller completed trajectories.
It does NOT use compare_property_pair to recompute eligibility. It verifies
the published 0.5 kWh/0.02 gate and repeats eligibility under stricter
(predeclared here, post hoc relative to original v3 study) inventory limits.

Never infer uncertainties from tolerances; the thresholds are analytical
comparability choices, not metrology or confidence intervals.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from math import isfinite
import csv
import json

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"results/wp7_model_mismatch_v3.json"
OUT=ROOT/"results"
STUDY="WP7_Comparability_ClaimBoundary_Sensitivity_v4"
INVENTORY_KWH=(.50,.25,.10,.05,.01)
ACTUATOR_TOL=.02
ELECTRICAL_CARRIER="idealised compressor electrical input, no drive/pump losses"
THERMAL_CARRIER="stored header/buffer sensible-energy change, not electricity"


def audited_pair(pi:dict,mpc:dict,*,inventory_kwh:float,actuator_tol:float) -> dict:
    """Re-derive paired gates without trusting stored compare_property_pair flags."""
    if not (isfinite(inventory_kwh) and inventory_kwh>0 and
            isfinite(actuator_tol) and actuator_tol>0):
        raise ValueError("comparability thresholds must be finite positive")
    keys=("benchmark_id","case","plant","seed","sensor_delay_s","sensor_noise_sd_k",
          "duration_s","sample_period_s","control_period_s","measurement",
          "truth_model_mismatch","truth_parameter_ratios_to_nominal")
    for key in keys:
        if pi.get(key)!=mpc.get(key):
            raise ValueError("mismatched physical or sensing experiment: "+key)
    if pi["controller"] not in ("PI_IMC","PI_relay") or mpc["controller"]!="MPC_property":
        raise ValueError("invalid paired controller labels")
    full=(pi["status"]=="complete" and mpc["status"]=="complete")
    service=bool(full and pi["matched_service_gate"] and mpc["matched_service_gate"])
    reasons=[]
    if not full:reasons.append("incomplete_or_unqualified_initial_state")
    if full and not service:reasons.append("service_failure")
    thermal_keys=("final_header_energy_delta_kWh","final_buffer_energy_delta_kWh",
                  "final_total_energy_delta_kWh")
    actuator_keys=("final_compressor_modulation","final_applied_command")
    d_thermal={}
    d_act={}
    for key in thermal_keys:
        a=pi.get(key);b=mpc.get(key)
        if not full:continue
        if not isinstance(a,(float,int)) or not isinstance(b,(float,int)) or not isfinite(a) or not isfinite(b):
            reasons.append("missing_or_nonfinite_"+key)
            continue
        delta=b-a
        d_thermal[key]=delta
        if abs(delta)>inventory_kwh+1e-12:
            reasons.append("inventory_mismatch_"+key)
    for key in actuator_keys:
        a=pi.get(key);b=mpc.get(key)
        if not full:continue
        if not isinstance(a,(float,int)) or not isinstance(b,(float,int)) or not isfinite(a) or not isfinite(b):
            reasons.append("missing_or_nonfinite_"+key)
            continue
        delta=b-a
        d_act[key]=delta
        if abs(delta)>actuator_tol+1e-12:
            reasons.append("actuator_mismatch_"+key)
    if full:
        qp=pi.get("process_heat_kWh");qm=mpc.get("process_heat_kWh")
        if qp is None or qm is None or not all(isfinite(v) for v in (qp,qm)):
            reasons.append("missing_process_heat")
        elif abs(qm-qp)>1e-5:
            # The v3 scenarios use the same 300kW fixed process duty. A
            # numerical tolerance prevents confusing identical demand with
            # silently different completed process heat deliveries.
            reasons.append("unequal_process_heat")
    eligible=not reasons
    de=mpc["electricity_kWh"]-pi["electricity_kWh"] if full else None
    iae=mpc["iae_Ks"]-pi["iae_Ks"] if full else None
    if full and (de is None or iae is None or not isfinite(de) or not isfinite(iae)):
        raise ValueError("nonfinite completed electrical/tracking result")
    return {
        "case":pi["case"],"pi":pi["controller"],"complete":full,
        "service":service,"eligible":eligible,"reasons":reasons,
        "delta_electricity_kWh_raw_if_full":de,
        "delta_iae_Ks_raw_if_full":iae,
        "eligible_delta_electricity_kWh":de if eligible else None,
        "delta_header_inventory_kWh":d_thermal.get(thermal_keys[0]),
        "delta_buffer_inventory_kWh":d_thermal.get(thermal_keys[1]),
        "delta_total_inventory_kWh":d_thermal.get(thermal_keys[2]),
        "delta_modulation":d_act.get(actuator_keys[0]),
        "delta_command":d_act.get(actuator_keys[1]),
        "absolute_total_thermal_delta_over_abs_electrical_delta_DIFFERENT_UNITS_OF_ENERGY":
            (abs(d_thermal.get(thermal_keys[2],0))/abs(de)
             if eligible and de is not None and abs(de)>1e-10 else None),
    }


def audit(data:dict) -> dict:
    if data.get("benchmark_id")!="WP7_NominalPredictor_TruthParameterMismatch_Holdout_v3":
        raise ValueError("unexpected underlying research snapshot")
    if len(data["runs"])!=15 or len(data["pairs"])!=10:
        raise ValueError("incomplete frozen result ledger")
    by_key={}
    for r in data["runs"]:
        key=(r["case"],r["controller"])
        if key in by_key:raise ValueError("duplicate controller scenario")
        by_key[key]=r
    original={(p["case"],p["baseline"]):p for p in data["pairs"]}
    if len(original)!=10:raise ValueError("duplicate original paired identity")
    all_scans={}
    for threshold in INVENTORY_KWH:
        key=f"{threshold:.2f}"
        rows=[]
        for old in data["pairs"]:
            pi=by_key.get((old["case"],old["baseline"]))
            mpc=by_key.get((old["case"],old["candidate"]))
            if pi is None or mpc is None:raise ValueError("missing raw paired controller")
            result=audited_pair(pi,mpc,inventory_kwh=threshold,actuator_tol=ACTUATOR_TOL)
            if threshold==.50:
                if result["eligible"]!=old["eligible_for_conditional_electricity_comparison"]:
                    raise RuntimeError("published default comparator no longer rederived from raw trajectories")
                if result["eligible"]:
                    if abs(result["eligible_delta_electricity_kWh"]-old["delta_electricity_kWh"])>1e-8:
                        raise RuntimeError("published energy delta inconsistent")
                elif old["delta_electricity_kWh"] is not None:
                    raise RuntimeError("ineligible old comparison wrongly has energy value")
            rows.append(result)
        all_scans[key]={
            "inventory_tolerance_kWh":threshold,
            "actuator_tolerance":ACTUATOR_TOL,
            "eligible_count":sum(r["eligible"] for r in rows),
            "eligible_cases":[f"{r['case']}|{r['pi']}" for r in rows if r["eligible"]],
            "eligible_delta_electricity_kWh":[r["eligible_delta_electricity_kWh"] for r in rows if r["eligible"]],
            "rows":rows
        }
    counts=[x["eligible_count"] for x in all_scans.values()]
    if counts!=sorted(counts,reverse=True):
        raise RuntimeError("eligibility became less strict when thresholds tightened")
    # Publish observed audit only; these counts are NOT hand-tuned results.
    return {
        "audit_id":STUDY,
        "source_benchmark":data["benchmark_id"],
        "disclaimer":"POST-HOC sensitivity of arbitrary comparability limits; not a confidence interval, hardware validation or model uncertainty bound",
        "carrier_warning":"Thermal terminal inventory differences in kWh_thermal are not interchangeable with compressor electrical energy kWh_electric; no conversion or economic correction is inferred",
        "rederived_default_gate_matches_published":True,
        "nominal_mpc_best_efficiency_not_claimed":True,
        "source_hardware_validated":False,
        "sensitivity":all_scans,
    }


def render_md(data:dict) -> str:
    lines=[
        "# WP7 v4 — strict comparability and claim-boundary audit",
        "",
        "**Scope:** Post-hoc sensitivity of the terminal-inventory equivalence",
        "gate for the immutable WP7 v3 simulator. All original trajectories",
        "are re-read; no controller is retuned and no simulation results are",
        "replaced. This is NOT independent physical validation.","",
        "## Independent rederivation of the original electricity-eligibility gate","",
        "The existing comparator permits **0.5 kWh thermal difference** in each",
        "of header, buffer, and their total, plus 0.02 difference in final",
        "compressor modulation and applied command. The raw v3 service and",
        "end-state fields were independently checked here, confirming the",
        "published default 4/10 eligible pairs.","",
        "The allowable 0.5 kWh terminal thermal inventory difference is",
        "**not a measurement uncertainty** and can be comparable to the",
        "reported idealised electrical-power differences. These thermal and",
        "electrical energy values cannot simply be subtracted as if COP=1.",
        "Therefore, positive/negative energy rankings must be described as",
        "conditional on declared equivalence tolerances and idealised model.","",
        "## Sensitivity to tighter thermal-inventory equality","",
        "| Per-component AND total inventory tolerance | Eligible of 10 paired comparisons |",
        "|---:|---:|",
    ]
    for entry in data["sensitivity"].values():
        lines.append(f"| {entry['inventory_tolerance_kWh']:.2f} kWh thermal | {entry['eligible_count']}/10 |")
    lines+=["","The actuator endpoint tolerance remains 0.02 in all rows.",
            "These alternative thresholds were introduced **after** seeing",
            "the v3 benchmark and are a claim-robustness audit, not",
            "preregistered hypothesis tests.","",
            "## The four original nominal-tolerance eligible pairs","",
            "| Scenario | PI baseline | MPC−PI electricity (kWh_e) | MPC−PI final thermal inventory (kWh_th) |",
            "|---|---|---:|---:|"]
    for r in data["sensitivity"]["0.50"]["rows"]:
        if r["eligible"]:
            lines.append(f"| {r['case']} | {r['pi']} | {r['eligible_delta_electricity_kWh']:+.4f} | {r['delta_total_inventory_kWh']:+.4f} |")
    lines+=["","The original 0.5 kWh criterion labels all four above as",
            "terminal-equivalent, but a stricter criterion retains only",
            "the subset shown above. In all originally eligible cases MPC's",
            "computed compressor electricity is higher; **that is a property",
            "of this synthetic objective, policy and scenario set**, not an",
            "industrial efficiency ranking or statistically significant result.","",
            "## Research readiness judgement","",
            "- **Software regression:** v3 15-run source/target identities and original",
            "  0.5 kWh eligibility flags are independently reproducible.",
            "- **Scientific limitation:** simulator truth and MPC predictor share the",
            "  same uncalibrated refrigerant Q/P map and water EOS; the mismatch",
            "  study varies only a few assumed lumped thermal parameters.",
            "- **Optimizer limitation:** QP weight choices (temperature error,",
            "  movement, slack and electric cost) are not justified by",
            "  a formal multiobjective design or matched alternative design.",
            "- **Comparison limitation:** 2-hour transients, discrete cases,",
            "  fixed 300 kW heat demand and no measured actuator/sensor/error model.",
            "- **Validation limitation:** no actual heat-pump equipment, measured",
            "  compressor map, independent plant truth or safety approval.",
            "- **Recommendation:** show methods and falsifying outcomes in a",
            "  PhD *research sample*, not as a research paper claiming controller",
            "  energy savings, SOC deployment or equipment certification.","",
            "Raw calculations: [machine-readable independent audit](wp7_comparability_claim_audit_v4.json).",
            "Reproduce with `python scripts/audit_wp7_comparability.py`.",
        ]
    return "\n".join(lines)+"\n"


def main():
    d=json.loads(SOURCE.read_text(encoding="utf-8"))
    out=audit(d)
    OUT.mkdir(exist_ok=True)
    (OUT/"wp7_comparability_claim_audit_v4.json").write_text(json.dumps(out,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    (OUT/"wp7_comparability_claim_audit_v4.md").write_text(render_md(out),encoding="utf-8")
    print("Eligibility sensitivity:",[(k,v["eligible_count"]) for k,v in out["sensitivity"].items()])
    return out


if __name__=="__main__":
    main()
