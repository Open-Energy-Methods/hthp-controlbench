"""Evaluate a genuinely instrumented WP7 observer trace — NO synthetic default data.

A valid CSV and provenance manifest from the same named equipment are
required. Only the buffer sensor, prior applied command, known disturbances
and initial hidden states reach the predictor. Later measured header and
actual compressor modulation are post-hoc held-out SCORE channels ONLY.

The WP7 reference compressor remains hypothetical. Even a successful
numerical residual run is NOT an equipment-approved physical validation.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

from ht_hp_controlbench.realfluid import CycleAssumptions,build_cycle_map
from ht_hp_controlbench.wp7_external_evidence import provisional_measured_observer_holdout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv",type=Path,required=True,
                        help="External instrumented time series (never generated automatically)")
    parser.add_argument("--manifest",type=Path,required=True,
                        help="Independent asset, sensor, timebase and nonoverlapping split provenance")
    parser.add_argument("--output",type=Path,default=Path("wp7_observer_holdout_local.json"),
                        help="Local output; not automatically committed due operational privacy")
    parser.add_argument("--dt",type=float,default=20.,help="Property predictor RK4 integration step (s)")
    args=parser.parse_args()
    raw=args.csv.read_bytes()
    manifest=json.loads(args.manifest.read_text(encoding="utf-8"))
    expected=manifest.get("raw_data_sha256")
    digest=sha256(raw).hexdigest()
    if not isinstance(expected,str) or len(expected)!=64 or expected.lower()!=digest:
        raise ValueError("instrument manifest SHA-256 does not match exact source CSV bytes")
    with args.csv.open("r",encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):
            raise ValueError("invalid instrumented CSV field names")
        rows=list(reader)
        if not rows:
            raise ValueError("cannot validate without real instrument readings")
    # No model calibration is fabricated. Actual OEM data must be independently
    # collected before results can be interpreted beyond provisional residuals.
    m=build_cycle_map("R1233zd(E)",(328.15,333.15,338.15),
                      (398.15,403.15,406.2,410.15,413.15),
                      (.5,.75,1.0),CycleAssumptions())
    evaluation=provisional_measured_observer_holdout(
        rows,manifest,m,dt_s=args.dt)
    output={
        "origin":"external user-supplied independent instrumentation; authenticity NOT automatically verified",
        "data_sha256":digest,
        "model":"WP7 assumed compressor reference (NOT OEM-calibrated)",
        "research_only":True,
        "equipment_validated":False,
        "sensor_calibration_externally_reviewed":False,
        "evaluation":evaluation,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("Observer evaluation:",evaluation["status"])
    return output


if __name__=="__main__":
    main()
