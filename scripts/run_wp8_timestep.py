"""Audit A08: actual CoolProp WP8 24-hour integration time-step sensitivity.

This quantifies a numerical error component under the SAME hypothetical
equipment/tariff assumptions. It does not measure compressor uncertainty or
establish an economic investment return.
"""
from __future__ import annotations
from dataclasses import replace
from math import isfinite
from pathlib import Path
import json

from ht_hp_controlbench.realfluid import build_cycle_map,backend_version
from ht_hp_controlbench.storage_flexibility import (
    FlexSettings, SyntheticTariff, compare_flexibility
)

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"results"
BENCHMARK_ID="WP8_Timestep_Sensitivity_v1"
DTS=(60.,30.,15.)


def as_float(v):
    if v is None:
        return None
    n=float(v)
    return n if isfinite(n) else None


def _metric(run,field):
    return as_float(run.get(field)) if isinstance(run,dict) else None


def record_from_pair(dt_s,pair):
    base=pair.get("baseline",{})
    flex=pair.get("flexibility",{})
    return {
        "dt_s":float(dt_s),
        "comparison_status":pair.get("status"),
        "base_status":base.get("status"),
        "flex_status":flex.get("status"),
        "creditable_at_this_step":pair.get("eligible_cost_saving_eur") is not None,
        "ineligibility_reasons":pair.get("reasons",[]),
        "raw_cost_difference_eur":as_float(pair.get("raw_cost_difference_eur")),
        "eligible_cost_saving_eur":as_float(pair.get("eligible_cost_saving_eur")),
        "baseline":{key:_metric(base,key) for key in (
            "cost_eur","electricity_kwh","spec_unserved_kwh",
            "service_qualified_fraction","residual_energy_j",
            "final_storage_delta_kwh","final_header_energy_delta_kwh",
            "final_total_thermal_energy_delta_kwh","final_modulation",
            "final_applied_command")},
        "flexibility":{key:_metric(flex,key) for key in (
            "cost_eur","electricity_kwh","spec_unserved_kwh",
            "service_qualified_fraction","residual_energy_j",
            "final_storage_delta_kwh","final_header_energy_delta_kwh",
            "final_total_thermal_energy_delta_kwh","final_modulation",
            "final_applied_command")},
        "equipment_verified":False,
    }


def summarize(records):
    """Conservative v1 gate: reject unqualified, negative or unresolved savings.

    Three dt levels allow a numerical sensitivity signal. This is NOT a
    Richardson extrapolation, proven asymptotic order or uncertainty interval;
    events, controller sample periods and service classification are nonlinear.
    """
    if len(records)!=3 or [r["dt_s"] for r in records]!=list(DTS):
        raise ValueError("require 60, 30 and 15 s full-horizon records")
    base={"benchmark_id":BENCHMARK_ID,"records":records,
          "all_comparisons_creditable":all(r["creditable_at_this_step"] for r in records),
          "hardware_evidence":"NONE: assumed compressor and water/source/sink limits",
          "numerical_test":"three nested time steps on the same 24-hour scenario",
          "model_status":"WP7 map property-calculated, uncalibrated"}
    if not base["all_comparisons_creditable"]:
        return dict(base,numerical_screen="NO_CREDIT_UNQUALIFIED_SERVICE_OR_TERMINAL_STATES",
                    savings_deltas_eur=None,smallest_saving_eur=None,
                    shrinking_resolution_differences=None,
                    conditional_numerical_resolution=False)
    values=[as_float(r["eligible_cost_saving_eur"]) for r in records]
    if any(v is None for v in values):
        raise ValueError("creditable run with unavailable saving")
    changes=(abs(values[0]-values[1]),abs(values[1]-values[2]))
    narrowing=changes[1]<changes[0] if changes[0]>0 else changes[1]==0
    sign_consistency=all(v>0 for v in values)
    effect_dominates_numerical_delta=(
        values[-1]>max(changes) if sign_consistency else False)
    passed=bool(narrowing and sign_consistency and effect_dominates_numerical_delta)
    if not sign_consistency:
        label="NO_POSITIVE_SAVING_AT_EVERY_RESOLUTION"
    elif not narrowing:
        label="NUMERICAL_REFINEMENT_NOT_SHRINKING"
    elif not effect_dominates_numerical_delta:
        label="NUMERICAL_CHANGE_COMPARABLE_TO_NOMINAL_SAVING"
    else:
        label="NUMERICAL_SIGNAL_SCREEN_PASSED__NOT_ECONOMIC_VALIDATION"
    return dict(base,numerical_screen=label,
                savings_deltas_eur=list(changes),
                smallest_saving_eur=min(values),
                finest_saving_eur=values[-1],
                shrinking_resolution_differences=narrowing,
                conditional_numerical_resolution=passed,
                mathematical_convergence_order_established=False,
                equipment_financial_saving_claim=False)


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    model=build_cycle_map("R1233zd(E)",[328.15,333.15,338.15],
        [403.15,406.2,413.15],[.5,.75,1.])
    tariff=SyntheticTariff()
    base=FlexSettings(dt_s=60.)
    records=[]
    for dt in DTS:
        cfg=replace(base,dt_s=dt)
        print(f"24-hour WP8 property-plant integration at dt={dt:.0f} s",flush=True)
        result=compare_flexibility(model,cfg,tariff)
        records.append(record_from_pair(dt,result))
    outcome=summarize(records)
    outcome["coolprop_version"]=backend_version()
    outcome["fluid"]="R1233zd(E)"
    outcome["tariff_eur_per_kwh"]={"low":tariff.low_eur_kwh,
        "high":tariff.high_eur_kwh,"regular":tariff.regular_eur_kwh}
    outcome["description"]="Actual IF97/CoolProp numerical time-step sensitivity; no OEM data"
    (OUTPUT/"wp8_timestep_sensitivity_v1.json").write_text(
        json.dumps(outcome,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    md=[
        "# WP8 — 24-hour integration-step sensitivity (unvalidated reference plant)",
        "",
        "Three actual CoolProp/IF97 runs of the same nominal synthetic tariff:",
        "",
        "| dt (s) | Baseline €/day | Scheduled €/day | Eligible saving €/day | Eligible? | Reasons |",
        "|---:|---:|---:|---:|---|---|",
    ]
    def val(x):
        return "n/a" if x is None else f"{x:.6f}"
    for r in records:
        md.append(f'| {r["dt_s"]:.0f} | {val(r["baseline"]["cost_eur"])} | '
          f'{val(r["flexibility"]["cost_eur"])} | '
          f'{val(r["eligible_cost_saving_eur"])} | '
          f'{"yes" if r["creditable_at_this_step"] else "NO"} | '
          f'{"; ".join(r["ineligibility_reasons"])} |')
    md.extend(["",f'**Numerical screen:** {outcome["numerical_screen"]}.',
       "", "This is sensitivity to the integration time step only, not a",
       "reliable uncertainty bound for assumed compressor displacement,",
       "efficiency, source/sink flow, pressure envelope, tariff, auxiliaries,",
       "compressor cycling, CAPEX or maintenance costs.",
       "Even a numerically stable positive daily difference does not justify",
       "an investment or real industrial savings claim.",""])
    (OUTPUT/"wp8_timestep_sensitivity_v1.md").write_text(
        "\n".join(md),encoding="utf-8")
    print("Numerical screen:",outcome["numerical_screen"],flush=True)
    return outcome


if __name__=="__main__":
    main()
