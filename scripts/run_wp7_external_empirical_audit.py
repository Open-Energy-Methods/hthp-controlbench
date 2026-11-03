"""Reproduce external WP7 experimental-data relevance and physical-evidence gates.

Every published experimental aggregation is computed directly from checksum-
verified CC-BY files; none uses synthetic surrogate data as measured evidence.
If the remote data are inaccessible or changed, this command FAILS rather
than substituting invented numbers. No raw dataset is re-distributed.
"""
from __future__ import annotations

from datetime import date,timezone,datetime
from hashlib import md5,sha256
from pathlib import Path
import argparse
import csv
import json

from ht_hp_controlbench.realfluid import CycleAssumptions,cycle_point,build_cycle_map,backend_version
from ht_hp_controlbench.wp7_external_evidence import (
    WIDMAIER,LECLERCQ,REQUIRED_ASSET_EVIDENCE,
    get_public_bytes,parse_verified_csv,audit_widmaier,audit_leclercq,
    evidence_gate,observer_record_gate,finite_source_bound,
)

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results"
EXPERIMENT="WP7_Independent_Experimental_Evidence_Screen_v1"


def load_dataset(spec, directory:Path|None):
    if directory is None:
        payload=get_public_bytes(spec)
    else:
        path=directory/spec.filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing independently obtained dataset {path}")
        payload=path.read_bytes()
    if md5(payload).hexdigest()!=spec.md5_checksum:
        raise RuntimeError("published Zenodo MD5 mismatch: "+spec.key)
    records=parse_verified_csv(payload,spec)
    return records,{
        "doi":spec.doi,"source_url":spec.source_url,"file_url":spec.file_url,
        "filename":spec.filename,"license":spec.license,"source_description":spec.origin,
        "published_md5":spec.md5_checksum,"raw_sha256":sha256(payload).hexdigest(),
        "bytes":len(payload),"data_content_verified":True,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-dir",type=Path,default=None,
                help="Use local copies of verified CC-BY originals instead of downloading")
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    rows_a,meta_a=load_dataset(WIDMAIER,args.data_dir)
    rows_b,meta_b=load_dataset(LECLERCQ,args.data_dir)
    a=audit_widmaier(rows_a)
    b=audit_leclercq(rows_b)
    # Freeze the external evidence corpus. Provenance drift must be reviewed.
    if (a["all_records"]!=32073 or
        a["generated_EN12900_records_not_measured"]!=31702 or
        a["experimentally_measured_records"]!=371 or
        a["pure_R1233zd_experimental_records"]!=22 or
        b["experimentally_measured_records"]!=67):
        raise RuntimeError("external data row counts changed: audit and source again")
    props=None  # CyclePoint requires real CoolProp and raises if unavailable.
    assumed=CycleAssumptions()
    nominal=cycle_point("R1233zd(E)",333.15,406.2,assumed)
    qcond=assumed.reference_condenser_duty_w
    power=qcond/nominal.cop_heating
    source=qcond-power
    displacement=(qcond/nominal.condenser_specific_j_kg) / (
           nominal.rho_suction_kg_m3*assumed.reference_modulation)
    # This is a reference implied by the requested nominal DUTY, never a
    # manufacturer compressor size, measured volumetric capacity or rating.
    equipment=evidence_gate(None,asset_id=None)
    observer=observer_record_gate(None,asset_id=None,evidence=None)
    source_bound=finite_source_bound(source)
    illustrative_flow={}
    for delta_k in (5,10,15):
        illustrative_flow[f"source_delta_{delta_k}K"] = {
            "water_cp_assumed_j_kgK":4200.,
            "minimum_flow_kg_s_ideal_no_pinches":source/(4200*delta_k),
            "interpretation":"ARITHMETIC_ONLY; actual fluid/flow/approaches unknown",
        }
    out={
        "audit_id":EXPERIMENT,
        "audit_date_utc":date.today().isoformat(),
        "status":"EXTERNAL_DATA_VERIFIED__TARGET_EQUIPMENT_AND_OBSERVER_NOT_VALIDATED",
        "external_datasets":{
            WIDMAIER.key:{"source":meta_a,"observations":a},
            LECLERCQ.key:{"source":meta_b,"observations":b},
        },
        "independent_sources_not_automatically_ingested":[
            {
                "doi":"10.17632/56m3dd55zf.1",
                "url":"https://data.mendeley.com/datasets/56m3dd55zf/1",
                "title":"Jeßberger et al. 2026 measured 37kW R1233zd(E) full HTHP",
                "value":"More applicable to complete heat-pump calibration than bare compressor tests",
                "availability":"META_VERIFIED; raw Mendeley API returned 401 without authorization",
                "status":"NOT_INGESTED__NO_NUMERIC_VALIDATION",
            },
            {
                "url":"https://www.bitzer.de/mv/en/products/screw-compressors/csh2t/",
                "title":"BITZER CSH2T published product family",
                "scope":"R1233zd(E) compressor; published useful output up to 120C",
                "reference_WP7_nominal_header_C":nominal.t_header_k-273.15,
                "status":"NOT_A_133C_MACHINE_PROOF__SPECIFIC_OEM_MAP_UNAVAILABLE",
            },
            {
                "doi":"10.1016/j.applthermaleng.2024.122961",
                "title":"Ramirez et al. 2024 R1233zd(E) prototype measured 38.6kW at 148.5C",
                "status":"LITERATURE_PROOF_OF_OTHER_RIG_OPERATION__NOT_TARGET_ASSET",
            },
        ],
        "reference_model":{
            "origin":"same unchanged hypothetical WP7 nominal calculation; NOT measured",
            "fluid":"R1233zd(E)","source_K":333.15,"header_K":406.2,
            "condensing_duty_w_requested":qcond,
            "compressor_efficiency_is_assumed":assumed.eta_isentropic,
            "cop_ideal_compression_eos":nominal.cop_heating,
            "electrical_input_w_ideal_without_motor_losses":power,
            "required_evaporator_w":source,
            "implied_fullspeed_suction_volume_m3_s_NOT_OEM":displacement,
            "coolprop_version":backend_version(),
            "potential_external_comparison":"not direct: model eta_is reflects internal idealization; measured overall eta_is uses electric input",
            "reference_capacity_not_independently_validated":True,
            "source_temperature_drop_sensitivity":illustrative_flow,
        },
        "finite_source_test":source_bound,
        "equipment_evidence_gate":equipment,
        "observer_evidence_gate":observer,
        "unmet_evidence_requirements":REQUIRED_ASSET_EVIDENCE,
        "prohibited_conclusions":[
            "310kW reference equipment exists or is rated for 133C service",
            "different measured compressor is the reference compressor",
            "EN12900 polynomial rows constitute measured hardware observations",
            "two-phase oil-mixed scroll evidence validates dry-vapor compressor",
            "nominal motor electricity or source/sink HX design is independently known",
            "property-matched numerical observer is validated by real measured truth",
            "MPC performance and energy costs generalize to a commercial machine",
        ],
    }
    (OUT/"wp7_external_empirical_evidence_v1.json").write_text(
        json.dumps(out,indent=2,allow_nan=False,ensure_ascii=False)+"\n",encoding="utf-8")
    with (OUT/"wp7_external_empirical_source_counts_v1.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(("doi","data_origin","records","claim"))
        for label,n in a["source_counts"].items():
            w.writerow((WIDMAIER.doi,label,n,
                        "MEASURED_ON_OTHER_COMPRESSOR" if label.startswith("Experimental ") else
                        "GENERATED_POLYNOMIAL_NOT_MEASURED"))
        w.writerow((LECLERCQ.doi,"Experimental two-phase scroll with oil",
                    b["experimentally_measured_records"],"MEASURED_OUT_OF_DOMAIN"))
    format_number=lambda x:f"{x:,.3f}"
    lines=[
        "# WP7 — independent empirical evidence and verification gate v1","",
        "**Current target system/equipment:** NOT VALIDATED. **Current independent",
        "instrumented observer:** NOT VALIDATED. Nothing about this external",
        "data transfers physical capacity, design pressure or controller safety to WP7.","",
        "## Source-provenance audit (actual checksum-verified raw CSVs)","",
        f"- [Widmaier et al. 2026]({meta_a['source_url']}), DOI `{meta_a['doi']}`: "
        f"**{a['all_records']:,} records**; **{a['generated_EN12900_records_not_measured']:,}** "
        f"EN12900 manufacturer-model **generated** rows; "
        f"**{a['experimentally_measured_records']}** independent measured rows; "
        f"only **{a['pure_R1233zd_experimental_records']}** measured pure R1233zd(E). "
        f"Measured overall compressor η_is median **{a['pure_refrigerant_eta_is_overall_electrical']['median']:.3f}** "
        f"(range {a['pure_refrigerant_eta_is_overall_electrical']['min']:.3f}–"
        f"{a['pure_refrigerant_eta_is_overall_electrical']['max']:.3f}). "
        "**DO NOT interpret this as a calibrated WP7 compressor:** it is a different",
        "machine and overall *electrical* efficiency is not the WP7 assumed internal η_is.","",
        f"- [Leclercq experimental two-phase/oil scroll]({meta_b['source_url']}), "
        f"DOI `{meta_b['doi']}`: **{b['experimentally_measured_records']}** "
        f"independent R1233zd(E) measured records; reported η_is median "
        f"**{b['reported_isentropic_efficiency']['median']:.3f}** "
        f"(range {b['reported_isentropic_efficiency']['min']:.3f}–"
        f"{b['reported_isentropic_efficiency']['max']:.3f}). "
        "This is two-phase/oil compressor research, **out of scope** for direct",
        "validation of WP7's dry-vapor reference cycle.","",
        "Both source raw-file MD5 checksums must match Zenodo's published metadata.",
        "The report includes their SHA-256 digests and versioned DOIs; no source",
        "rows are copied into the repository. License CC BY 4.0; give attribution.","",
        "## Reference model: conditional arithmetic, not measured equipment","",
        f"- Nominal condenser request: **{qcond/1000:.1f} kW**; predicted ideal EOS COP **{nominal.cop_heating:.3f}**.",
        f"- Ideal compressor power without auxiliary/motor losses: **{power/1000:.2f} kW**.",
        f"- Ideal evaporator thermal input: **{source/1000:.2f} kW**.",
        f"- Compressor equivalent full-speed displacement **{displacement:.5f} m³/s** "
        "**IMPLIED FROM OUTPUT, NOT OEM MEASURED**.",
        "- Illustrative heat-source mass-flow minimums assume water at",
        "4200 J/(kg K) and a completely usable heat-source temperature drop;",
        "**no pinch/UA, hydraulic or fluid compatibility check exists**:",
        "",
        "| Assumed available source drop | Ideal necessary source flow |",
        "|---:|---:|",
    ]
    for delta in (5,10,15):
        v=illustrative_flow[f"source_delta_{delta}K"]
        lines.append(f"| {delta} K | {v['minimum_flow_kg_s_ideal_no_pinches']:.3f} kg/s |")
    lines.extend(["","## What blocks actual equipment and observer acceptance","",
        f"- **{len(equipment['missing_sections'])}/{equipment['section_count']} required "
        "asset-matched evidence sections missing**: no nominated OEM compressor,",
        "independent efficiency/displacement/pressure envelope, source/sink mass",
        "flow and heat-exchanger capacities, instrument calibration, safety basis.",
        "- Independent source/sink flow was **not supplied**, so the necessary",
        "energy bound itself is UNVERIFIED, despite the illustrative flow table.",
        "- No independent, time-aligned HEADER-temperature and ACTUAL modulation",
        "trace from a configured matching HTHP; v2 observer validation currently",
        "tests two numerical formulations sharing assumptions, not measured truth.",
        "- Independent datasets at other scales/topologies test external",
        "plausibility and limitations; they cannot prove 310 kW at 133C.",
        "- The [Bayreuth 37 kW R1233zd(E) HTHP dataset](https://data.mendeley.com/datasets/56m3dd55zf/1)",
        "is a promising full-cycle *external* test set, but its downloadable",
        "files were **not obtained** through the public API (401). It is listed",
        "as NOT_INGESTED, not as a computed validation.",
        "- BITZER CSH2T documents useful heat output up to **120C**, not the",
        "higher hypothetical 133C reference. That family cannot serve as",
        "the missing model-specific 133C certification without further OEM evidence.","",
        "## Actionable external-data requests","",
        "1. Identify the actual or proposed **manufacturer model, serial/configuration,",
        "   refrigerant/oil and VSD speed limits** with signed datasheet and Q/P map.",
        "2. Obtain continuous measured evaporator-side source and sink flow,",
        "   temperatures, pressures, HX design/UA, pinch and permissible temperature drops.",
        "3. Acquire a separate excitation/validation time series with timestamped",
        "   applied command, actual compressor modulation and independently",
        "   measured header/buffer/source/return temperatures, including calibration",
        "   certificates and uncertainties.",
        "4. Predeclare held-out conditions, validate time alignment and sensor delay;",
        "   compute estimator residuals using the **unmodified frozen model**.",
        "5. Add reviewed pressure-equipment compliance and industrial safety evidence;",
        "   numerical EOS feasibility is never equivalent to a certified asset.",
        "",
        "Reproduce against the original public files without network:",
        "`python scripts/run_wp7_external_empirical_audit.py --data-dir /path/to/verified/csvs`.",
        "For live original downloads use:",
        "`python scripts/run_wp7_external_empirical_audit.py`.",
        "Requires CoolProp for the separate *assumed-model arithmetic*; CSV parsing uses stdlib.","",
        "Evidence integrity is enforced in `tests/test_wp7_external_evidence.py`.","",
    ])
    (OUT/"wp7_external_empirical_evidence_v1.md").write_text("\n".join(lines),encoding="utf-8")
    print("External evidence verified: 2 independent Zenodo CSVs;",
          a["experimentally_measured_records"],"measured mixed-dataset rows;",
          a["pure_R1233zd_experimental_records"],"pure-R1233zd experimental rows;",
          b["experimentally_measured_records"],"out-of-domain scroll records; "
          "reference OEM and physical observer NOT validated.")
    return out


if __name__=="__main__":
    main()
