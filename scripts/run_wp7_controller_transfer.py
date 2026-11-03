"""Reproduce WP7 property-truth controller-transfer pilot (not industrial validation).

Produces only observed numerical results. Failed map/service cases keep NULL
differences and cannot become controller wins.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ht_hp_controlbench.realfluid import build_cycle_map, backend_version
from ht_hp_controlbench.storage_flexibility import WP3_IMC
from ht_hp_controlbench.property_controller_transfer import (
    PropertyTransferCase, matched_transfer_pilot
)

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results"


def main():
    OUT.mkdir(exist_ok=True)
    model=build_cycle_map("R1233zd(E)", [328.15,333.15,338.15],
                          [403.15,406.2,413.15],[.5,.75,1.])
    cases=(PropertyTransferCase("nominal"),
           PropertyTransferCase("source_drop_1K",source_step_k=-1.),
           PropertyTransferCase("noise_0p1K_seed23",sensor_noise_sd_k=.1,seed=23))
    outcome=matched_transfer_pilot(model,WP3_IMC,cases=cases,duration_s=2400.,dt_s=20.)
    outcome["coolprop_version"]=backend_version()
    outcome["pilot_parameters"]={
        "fluid":model.fluid,"duration_s":2400.,"integration_dt_s":20.,
        "sensor_period_s":60.,"control_period_s":120.,
        "pi_tune":"fixed nominal WP3 IMC 0.5tau",
        "mpc_nominal_predictor":"fixed WP2 synthetic dynamics, NOT a WP7 property-map predictor",
        "equipment_rated":False,
        "source_and_sink_flow_measured":False}
    (OUT/"wp7_controller_transfer_pilot.json").write_text(
        json.dumps(outcome,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    with (OUT/"wp7_controller_transfer_paired.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(outcome["paired"][0]))
        writer.writeheader();writer.writerows(outcome["paired"])
    with (OUT/"wp7_controller_transfer_runs.csv").open("w",newline="",encoding="utf-8") as f:
        selected=("case","method","status","error","completed_steps",
                  "requested_steps","iae_Ks","electrical_kWh",
                  "service_qualified_fraction","spec_unserved_kWh",
                  "energy_residual_J","pi_fallback_events",
                  "mpc_accepted","controller_decisions",
                  "max_estimated_header_error_K","max_estimated_modulation_error")
        writer=csv.DictWriter(f,fieldnames=selected)
        writer.writeheader()
        writer.writerows({k:r.get(k) for k in selected} for r in outcome["runs"])
    print("WP7 property truth vs WP2-designed controllers",len(outcome["runs"]),"runs")
    for row in outcome["paired"]:
        print(row)
    return outcome


if __name__=="__main__":
    main()
