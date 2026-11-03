"""WP7 external-evidence audit: testable provenance, not equipment certification.

Downloads independent CC-BY experimental compressor records and checks their
published hashes. The Zenodo Widmaier dataset explicitly MIXES experimental
rows with EN12900 manufacturer-polynomial GENERATED rows: never call the
latter measurements. Leclercq records include two-phase/oil compression and
are OUT OF DOMAIN for the dry-vapour WP7 compressor surrogate.

Other rigs' data must NEVER mark the hypothetical 310 kW WP7 system valid.
Observer validation requires an independent instrumented trace from the SAME
configured asset, including true header and applied modulation, and is
UNAVAILABLE until supplied. No placeholder values are filled in.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
from hashlib import md5, sha256
from io import StringIO
from math import isfinite
from statistics import median
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PublicDataset:
    key: str
    doi: str
    source_url: str
    file_url: str
    filename: str
    md5_checksum: str
    delimiter: str
    license: str
    origin: str

    def __post_init__(self):
        if self.delimiter not in (",",";"):
            raise ValueError("CSV delimiter must be declared")
        if len(self.md5_checksum)!=32 or any(c not in "0123456789abcdef" for c in self.md5_checksum):
            raise ValueError("published MD5 required")


WIDMAIER = PublicDataset(
    key="widmaier_2026",doi="10.5281/zenodo.17599603",
    source_url="https://zenodo.org/records/17599603",
    file_url="https://zenodo.org/api/records/17599603/files/compressor_performance_data.csv/content",
    filename="compressor_performance_data.csv",
    md5_checksum="680dd400cfb39b2fa0a1dd22a09c731f",
    delimiter=",",license="CC BY 4.0",
    origin="Widmaier et al.; 31,702 manufacturer-polynomial GENERATED + 371 measured compressor records",
)
LECLERCQ = PublicDataset(
    key="leclercq_2026",doi="10.5281/zenodo.20445833",
    source_url="https://zenodo.org/records/20445833",
    file_url="https://zenodo.org/api/records/20445833/files/proto.csv/content",
    filename="proto.csv",
    md5_checksum="ad79afb7265de1c3ee954d5ce2e094c3",
    delimiter=";",license="CC BY 4.0",
    origin="Leclercq; 200 cm^3 two-phase/oil-mixed R1233zd(E) scroll compressor laboratory data",
)
EXPECTED_KNOWN_SHA = {item.key:item.md5_checksum for item in (WIDMAIER,LECLERCQ)}


def get_public_bytes(item: PublicDataset, opener=urlopen) -> bytes:
    """Actual HTTP fetch only; never replace a failed retrieval with fake data."""
    request=Request(item.file_url,headers={"User-Agent":"hthp-controlbench-research/1.0"})
    with opener(request,timeout=80) as response:
        data=response.read(8_000_001)
    if len(data)>8_000_000:
        raise ValueError("external evidence file exceeds 8MB bounded ingestion")
    if md5(data).hexdigest()!=item.md5_checksum:
        raise ValueError("external evidence MD5 checksum mismatch: "+item.key)
    return data


def parse_verified_csv(data: bytes,item:PublicDataset) -> list[dict[str,str]]:
    """MD5 protected, duplicate-field rejecting strict numeric/data ingestion."""
    if md5(data).hexdigest()!=item.md5_checksum:
        raise ValueError("unverified external data: checksum mismatch")
    s=data.decode("utf-8-sig",errors="strict")
    reader=csv.DictReader(StringIO(s,newline=""),delimiter=item.delimiter,strict=True)
    if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):
        raise ValueError("absent or duplicate external data column names")
    records=[]
    for i,row in enumerate(reader,2):
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f"ragged external CSV row {i}")
        records.append(row)
    if not records:
        raise ValueError("external CSV is empty")
    return records


def finite_column(records:list[dict[str,str]],column:str) -> list[float]:
    result=[]
    for i,row in enumerate(records,1):
        if column not in row:
            raise ValueError("missing measured channel: "+column)
        raw=row[column].strip()
        if not raw or raw.lower() in ("nan","n/a","na"):
            continue
        try: value=float(raw)
        except ValueError as e: raise ValueError(f"bad numeric measurement {column} row {i}") from e
        if not isfinite(value):
            raise ValueError("nonfinite measured data not allowed")
        result.append(value)
    return result


def statistics(values:list[float]) -> dict[str,float|int]|None:
    if not values:return None
    vals=sorted(values)
    return {"n":len(vals),"min":vals[0],"median":median(vals),"max":vals[-1]}


def audit_widmaier(records:list[dict[str,str]]) -> dict[str,Any]:
    """Use source labels; EN12900 curves are explicitly NOT measured tests."""
    required={"source","compressor","refrigerant","T_ev_C","T_co_C","T_suc_C",
              "p_suc_bar","p_dis_bar","eta_is","eta_vol","DeltaT_sh_K"}
    if not required<=set(records[0]):
        raise ValueError("incomplete Widmaier schema")
    modeled=[r for r in records if r["source"] in ("Bitzer EN12900","Bock EN12900")]
    measured=[r for r in records if r["source"].startswith("Experimental ")]
    if len(measured)+len(modeled)!=len(records):
        raise ValueError("unrecognized compressor source; refuse classification")
    pure=[r for r in measured if r["refrigerant"]=="R1233zd(E)"]
    if not pure:raise ValueError("no independent pure-R1233zd(E) compressor evidence")
    by_source={}
    for r in records:by_source[r["source"]]=by_source.get(r["source"],0)+1
    out={
        "source_doi":WIDMAIER.doi,"all_records":len(records),
        "generated_EN12900_records_not_measured":len(modeled),
        "experimentally_measured_records":len(measured),
        "pure_R1233zd_experimental_records":len(pure),
        "source_counts":by_source,
        "pure_refrigerant_eta_is_overall_electrical":statistics(finite_column(pure,"eta_is")),
        "pure_refrigerant_eta_vol":statistics(finite_column(pure,"eta_vol")),
        "pure_refrigerant_suction_pressure_bar":statistics(finite_column(pure,"p_suc_bar")),
        "pure_refrigerant_discharge_pressure_bar":statistics(finite_column(pure,"p_dis_bar")),
        "pure_refrigerant_T_ev_C":statistics(finite_column(pure,"T_ev_C")),
        "pure_refrigerant_T_suc_C":statistics(finite_column(pure,"T_suc_C")),
        "pure_refrigerant_T_co_C":statistics(finite_column(pure,"T_co_C")),
        "pure_refrigerant_superheat_K":statistics(finite_column(pure,"DeltaT_sh_K")),
        "asset_matching_reference_WP7":False,
        "model_compatibility":"EXTERNAL_COMPRESSOR_CONTEXT_ONLY",
        "why_not_direct_validation":(
            "Different compressor and reference displacement; experimental overall "
            "isentropic efficiency is defined using ELECTRICAL input, while WP7 "
            "idealized h2s-h1/eta uses assumed internal compression efficiency "
            "and omits motor and auxiliary power. Measured pressure/speed/geometry "
            "and heat-pump system topology are not matched. EN12900 rows are generated."
        ),
    }
    return out


def audit_leclercq(records:list[dict[str,str]]) -> dict[str,Any]:
    required={"eps_is","eps_v","P_ratio","x_ref_in","Speed_m","P_su_cp","P_ex_cp"}
    if not required<=set(records[0]):
        raise ValueError("incomplete Leclercq two-phase compressor schema")
    quality=finite_column(records,"x_ref_in")
    if not quality or any(x<0 or x>1.000001 for x in quality):
        raise ValueError("experimental inlet-quality channel not physically bounded")
    return {
        "source_doi":LECLERCQ.doi,"experimentally_measured_records":len(records),
        "inlet_refrigerant_vapour_quality":statistics(quality),
        "reported_isentropic_efficiency":statistics(finite_column(records,"eps_is")),
        "reported_volumetric_efficiency":statistics(finite_column(records,"eps_v")),
        "pressure_ratio":statistics(finite_column(records,"P_ratio")),
        "speed_rpm":statistics(finite_column(records,"Speed_m")),
        "asset_matching_reference_WP7":False,
        "model_compatibility":"OUT_OF_DOMAIN_TWO_PHASE_WITH_OIL",
        "why_not_direct_validation":(
            "Two-phase inlet and lubricating oil mixture in 200cm3 scroll unit; "
            "WP7 assumes dry superheated suction and a separate implied compressor displacement. "
            "Use only for conditional context on variability, not 310kW design calibration."
        ),
    }


REQUIRED_ASSET_EVIDENCE = {
    "asset_identity":"Same named 310kW installation, manufacturer model/serial and approved configuration",
    "manufacturer_application_envelope":"Dated compressor model-specific suction/discharge, oil, motor and discharge temperature limits",
    "manufacturer_capacity_map":"Independent measured/OEM condenser duty and input power as function of speed/source/sink",
    "compressor_swept_volume":"Independent OEM swept volume; NOT back-calculated from 310kW target",
    "isentropic_and_volumetric_maps":"Same compressor efficiency/volumetric curves with uncertainties",
    "fluid_lubricant_compatibility":"OEM-approved R1233zd(E) and oil combinations at nominated conditions",
    "heat_source_supply":"Measured mass flow, inlet/outlet temperature, pressure losses and minimum outlet bound",
    "heat_sink_service":"Measured water/heat-transfer loop mass flow, inlet/outlet temperatures and allowable pressures",
    "heat_exchangers":"Independent process/evaporator/condenser UA, pinch, pressure loss and flow-pressure ranges",
    "motor_and_auxiliaries":"Measured motor/drive/auxiliary electrical input and calibrated metering",
    "instrumentation_calibration":"Traceable sensor locations, uncertainty budgets and sample timestamps",
    "observer_training_data":"Instrumented excitation history with measured command and process/ambient disturbances",
    "observer_heldout_validation":"Nonoverlapping, time-aligned reference measurements of HEADER T and ACTUAL compressor modulation",
    "pressure_safety_basis":"Pressure rating, relief, alarm/interlocks and jurisdiction-specific design review",
}


def evidence_gate(evidence:dict[str,dict]|None=None, *, asset_id:str|None=None) -> dict:
    """Never promote public measurements from other rigs to WP7 validation.

    Even supported evidence must be for a NAMED matching asset. This is a
    conservative readiness gate, not an automatic certification procedure.
    """
    evidence=evidence or {}
    supplied=[]
    missing=[]
    mismatched=[]
    for key,description in REQUIRED_ASSET_EVIDENCE.items():
        entry=evidence.get(key)
        if entry is None:
            missing.append(key)
            continue
        if not isinstance(entry,dict):
            raise ValueError("evidence entry must be a provenance-bearing object")
        origin=entry.get("origin")
        item_asset=entry.get("asset_id")
        url=entry.get("reference_uri")
        if (not asset_id or item_asset!=asset_id or
            origin not in ("measured","manufacturer","certified_lab") or
            not isinstance(url,str) or not url.startswith(("https://","doi:"))):
            mismatched.append(key)
        else:
            supplied.append(key)
    status="NOT_EQUIPMENT_VALIDATED"
    return {
        "status":status,
        "asset_id":asset_id,
        "matched_evidence_sections":supplied,
        "missing_sections":missing,
        "nonqualifying_sections":mismatched,
        "section_count":len(REQUIRED_ASSET_EVIDENCE),
        "matched_section_count":len(supplied),
        "claim_boundary":"Supporting URL strings and supplied data cannot substitute independent OEM/safety and instrument review",
    }


def finite_source_bound(q_evaporator_required_w:float, *,
                        mass_flow_kg_s:float|None=None,
                        cp_j_kgk:float|None=None,
                        inlet_k:float|None=None,
                        minimum_outlet_k:float|None=None,
                        max_evaporator_approach_k:float|None=None)->dict[str,Any]:
    """Necessary heat-source energy bound; never conclude HX feasibility from it.

    Actual source outlet MIN temperature must come from independent measurement,
    process criteria or an OEM design limit. Max approach does NOT certify UA.
    """
    if not isfinite(q_evaporator_required_w) or q_evaporator_required_w<=0:
        raise ValueError("positive finite evaporator requirement")
    vals=(mass_flow_kg_s,cp_j_kgk,inlet_k,minimum_outlet_k)
    if any(v is None for v in vals):
        return {
            "status":"UNVERIFIED_SOURCE_FLOW_OR_TEMPERATURE",
            "required_evaporator_w":q_evaporator_required_w,
            "necessary_source_heat_upper_bound_w":None,
            "minimum_flow_kg_s_given_temperature_range":None,
            "heat_exchanger_verified":False,
        }
    if not all(isfinite(float(v)) for v in vals):
        raise ValueError("finite measured source-flow assumptions required")
    m,cp,ti,to=[float(v) for v in vals]
    if m<=0 or cp<=0 or ti<=to or to<=0:
        raise ValueError("positive finite source enthalpy/temperature drop required")
    if max_evaporator_approach_k is not None and (
        not isfinite(max_evaporator_approach_k) or max_evaporator_approach_k<=0):
        raise ValueError("approach threshold must be positive when given")
    upper=m*cp*(ti-to)
    margin=upper-q_evaporator_required_w
    return {
        "status":("NECESSARY_SOURCE_ENERGY_BOUND_FAIL" if margin < -1e-8 else
                  "NECESSARY_SOURCE_ENERGY_BOUND_ONLY__HX_AND_EQUIPMENT_UNVERIFIED"),
        "required_evaporator_w":q_evaporator_required_w,
        "necessary_source_heat_upper_bound_w":upper,
        "minimum_flow_kg_s_given_temperature_range":q_evaporator_required_w/(cp*(ti-to)),
        "heat_margin_w":margin,
        "heat_exchanger_verified":False,
    }


def observer_record_gate(records:list[dict]|None, *,
                         asset_id:str|None=None, evidence:dict|None=None)->dict:
    """Require genuine matched-asset measured unobserved states for any observer claim.

    This is an EVIDENCE gate only. True prediction residuals, time-alignment,
    hysteresis, sensor uncertainty, calibration and held-out statistics must be
    evaluated separately AFTER an authenticated measured dataset is supplied.
    Synthetic WP7 numerics and other labs' data can never pass this gate.
    """
    ev=evidence or {}
    keys=("raw_data_sha256","measurement_reference_uri","sensor_calibration_uri",
          "instrumented_asset_id","train_interval","heldout_interval")
    missing=[k for k in keys if not ev.get(k)]
    if not records:
        return {"status":"NO_MATCHED_INSTRUMENTED_OBSERVER_DATA",
                "records":0,"missing_evidence":missing,
                "claim":"observer empirical validity UNKNOWN"}
    columns={"time_s","buffer_measured_k","header_measured_k","modulation_measured",
             "command_applied","source_measured_k","return_measured_k"}
    if not all(columns <= set(row) for row in records):
        return {"status":"INSUFFICIENT_OBSERVER_CHANNELS",
                "records":len(records),"missing_channels":sorted(columns-set.intersection(*(set(x) for x in records))),
                "claim":"observer empirical validity UNKNOWN"}
    if not asset_id or asset_id!=ev.get("instrumented_asset_id"):
        return {"status":"MISMATCHED_OR_UNIDENTIFIED_OBSERVER_ASSET",
                "records":len(records),"claim":"observer empirical validity UNKNOWN"}
    if missing:
        return {"status":"OBSERVER_PROVENANCE_INCOMPLETE","records":len(records),
                "missing_evidence":missing,"claim":"observer empirical validity UNKNOWN"}
    time=[float(x["time_s"]) for x in records]
    if not all(isfinite(v) for v in time) or any(b<=a for a,b in zip(time,time[1:])):
        return {"status":"OBSERVER_TIMEBASE_INVALID","records":len(records),
                "claim":"observer empirical validity UNKNOWN"}
    for k in columns-{"time_s"}:
        if not all(isfinite(float(x[k])) for x in records):
            return {"status":"OBSERVER_INVALID_MEASUREMENT","channel":k,
                    "claim":"observer empirical validity UNKNOWN"}
    train=ev["train_interval"];held=ev["heldout_interval"]
    if not isinstance(train,(tuple,list)) or not isinstance(held,(tuple,list)) or len(train)!=2 or len(held)!=2:
        return {"status":"OBSERVER_SPLIT_INVALID","claim":"observer empirical validity UNKNOWN"}
    if not (float(train[0]) < float(train[1]) < float(held[0]) < float(held[1])):
        return {"status":"OBSERVER_SPLIT_LEAKAGE_OR_OVERLAP","claim":"observer empirical validity UNKNOWN"}
    return {"status":"INSTRUMENTED_TRACE_PRESENT__INDEPENDENT_REVIEW_REQUIRED",
            "records":len(records),
            "claim":"not yet an observer performance validation: sensor metrology and held-out predictor must be independently assessed",
            "train_interval":train,"heldout_interval":held,
            "raw_sha256":ev["raw_data_sha256"],
    }


def finite_sink_bound(q_condenser_required_w:float, *,
                      mass_flow_kg_s:float|None=None,
                      cp_j_kgk:float|None=None,
                      inlet_k:float|None=None,
                      maximum_outlet_k:float|None=None)->dict[str,Any]:
    """Independent necessary hot-sink enthalpy/flow check, NOT HX/OEM acceptance.

    Source requires an admissible cooling range, sink requires heating range.
    An insufficient finite sink FLOW is a real necessary-condition failure;
    a sufficient flow is NEVER sufficient for a real heat-exchanger rating.
    """
    if not isfinite(q_condenser_required_w) or q_condenser_required_w<=0:
        raise ValueError("positive finite condenser requirement")
    vals=(mass_flow_kg_s,cp_j_kgk,inlet_k,maximum_outlet_k)
    if any(v is None for v in vals):
        return {
            "status":"UNVERIFIED_SINK_FLOW_OR_TEMPERATURE",
            "required_condenser_w":q_condenser_required_w,
            "necessary_sink_heat_upper_bound_w":None,
            "minimum_flow_kg_s_given_temperature_range":None,
            "heat_exchanger_verified":False,
        }
    if not all(isfinite(float(v)) for v in vals):
        raise ValueError("finite sink measurements required")
    m,cp,ti,to=map(float,vals)
    if m<=0 or cp<=0 or to<=ti or ti<=0:
        raise ValueError("positive finite hot sink enthalpy rise required")
    upper=m*cp*(to-ti)
    margin=upper-q_condenser_required_w
    return {
        "status":("NECESSARY_SINK_ENERGY_BOUND_FAIL" if margin < -1e-8 else
                  "NECESSARY_SINK_ENERGY_BOUND_ONLY__HX_AND_EQUIPMENT_UNVERIFIED"),
        "required_condenser_w":q_condenser_required_w,
        "necessary_sink_heat_upper_bound_w":upper,
        "minimum_flow_kg_s_given_temperature_range":q_condenser_required_w/(cp*(to-ti)),
        "heat_margin_w":margin,
        "heat_exchanger_verified":False,
    }


def provisional_measured_observer_holdout(records:list[dict], evidence:dict, model,
                                          *, props=None, p=None, dt_s:float=20.) -> dict:
    """Compute held-out MODEL residuals from independent channels if supplied.

    The predictor's only live correction is buffer_measured_k; true header
    and actual modulation are used at INITIALIZATION and later for SCORING,
    never passed to advance(). All gains/assumptions are frozen in the caller.
    This output remains provisional until raw trace, sensor calibration and
    asset identity have been verified externally by a qualified reviewer.
    """
    from dataclasses import replace
    from math import sqrt
    from .core import Parameters,State,Disturbance
    from .wp7_predictor import PropertyPredictor
    from .realfluid import coolprop_backend,PointRejected

    asset=evidence.get("instrumented_asset_id")
    gate=observer_record_gate(records,asset_id=asset,evidence=evidence)
    if gate["status"]!="INSTRUMENTED_TRACE_PRESENT__INDEPENDENT_REVIEW_REQUIRED":
        return dict(status="NO_PROVISIONAL_OBSERVER_SCORE",evidence_status=gate,
                    physical_validation=False)
    if not isfinite(dt_s) or dt_s<=0:
        raise ValueError("positive finite observer model integration timestep required")
    if evidence.get("sensor_delay_s") is None or evidence.get("time_sync_uncertainty_s") is None:
        return dict(status="SENSOR_CLOCK_METADATA_INCOMPLETE",physical_validation=False)
    delay=float(evidence["sensor_delay_s"])
    clock_error=float(evidence["time_sync_uncertainty_s"])
    if not isfinite(delay) or delay!=0 or not isfinite(clock_error) or clock_error<0:
        return dict(status="SENSOR_DELAY_OR_CLOCK_NOT_ALIGNED__NO_SCORE",
                    physical_validation=False)
    p=p or replace(Parameters(hx_mode="duty_limiter"),
                    n_min=model.modulations[0],n_max=model.modulations[-1])
    props=props if props is not None else coolprop_backend()
    predictor=PropertyPredictor(model,props)
    first=records[0]
    previous=State(float(first["header_measured_k"]),
                   float(first["buffer_measured_k"]),
                   float(first["modulation_measured"]))
    previous_d=Disturbance(t_source=float(first["source_measured_k"]),
                           t_return=float(first["return_measured_k"]))
    previous_command=float(first["command_applied"])
    last_t=float(first["time_s"])
    validation_start,validation_end=map(float,evidence["heldout_interval"])
    traces=[];h_errors=[];n_errors=[]
    for row in records[1:]:
        t=float(row["time_s"])
        time_delta=t-last_t
        if abs(time_delta/dt_s-round(time_delta/dt_s))>1e-8:
            return dict(status="OBSERVER_UNALIGNED_INTEGRATION_CLOCK",
                        failure_time_s=t,physical_validation=False)
        try:
            prediction=predictor.advance(previous,previous_command,p,
                                         previous_d,time_delta,dt_s)
        except (PointRejected,ValueError,OverflowError,FloatingPointError) as exc:
            return dict(status="OBSERVER_PROPERTY_ENVELOPE_REJECTED",
                        failure_time_s=t,failure_reason=str(exc),
                        physical_validation=False)
        observed_tb=float(row["buffer_measured_k"])
        estimated=State(prediction.th,observed_tb,prediction.n)
        # Truth held-out channels are read ONLY here, never fed into predictor.
        if validation_start<=t<=validation_end:
            eh=estimated.th-float(row["header_measured_k"])
            en=estimated.n-float(row["modulation_measured"])
            h_errors.append(eh);n_errors.append(en)
            traces.append({
                "time_s":t,
                "estimated_header_k":estimated.th,
                "estimated_modulation":estimated.n,
                "measured_header_k_scoring_only":float(row["header_measured_k"]),
                "measured_modulation_scoring_only":float(row["modulation_measured"]),
                "buffer_innovation_k":observed_tb-prediction.tb,
                "header_residual_k":eh,"modulation_residual":en,
            })
        previous=estimated
        previous_d=Disturbance(t_source=float(row["source_measured_k"]),
                               t_return=float(row["return_measured_k"]))
        previous_command=float(row["command_applied"])
        last_t=t
    if len(h_errors)<2:
        return dict(status="OBSERVER_INSUFFICIENT_HELDOUT_SAMPLES",
                    samples=len(h_errors),physical_validation=False)

    def summary(errors):
        return {
            "n":len(errors),
            "mae":sum(abs(x) for x in errors)/len(errors),
            "rmse":sqrt(sum(x*x for x in errors)/len(errors)),
            "signed_bias":sum(errors)/len(errors),
            "maximum_absolute_error":max(abs(x) for x in errors),
        }

    return {
        "status":"DESCRIPTIVE_MEASURED_HOLDOUT_RESIDUALS__INDEPENDENT_REVIEW_REQUIRED",
        "physical_validation":False,
        "asset_id_as_supplied":asset,
        "data_provenance_not_cryptographically_authenticated_to_an_instrument":True,
        "observer_header_kelvin":summary(h_errors),
        "observer_modulation_fraction":summary(n_errors),
        "hidden_states_never_fed_back_after_initialization":True,
        "heldout_interval_s":[validation_start,validation_end],
        "traces":traces,
        "warning":"Other physical limitations still apply: assumed 310kW compressor and HX cannot be validated from a trace manifest alone",
    }
