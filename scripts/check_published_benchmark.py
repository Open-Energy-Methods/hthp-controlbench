"""Numerically compare regenerated synthetic L1 outputs to reviewed v2 snapshot.

This is a regression gate for implementation drift, not experimental validation.
Only compares the specific L1 model revision identified by L1_RelayPeak_v2.
"""
from __future__ import annotations

import csv
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FROZEN = RESULTS / "L1_RelayPeak_v2"
BENCHMARK = "L1_RelayPeak_v2"
NUMERICAL_REL_TOL = 1e-5
NUMERICAL_ABS_TOL = 2e-4
NUMERIC_FIELDS = {
    "wp4_robustness_matrix.csv": (
        "sensor_noise_sd_K", "sensor_delay_s", "seed", "decisions",
        "accepted_mpc", "pi_fallbacks", "fallback_fraction",
        "command_variation", "sample_fraction_at_command_bounds",
        "service_qualified_fraction", "physical_energy_shortfall_kWh",
        "iae_Ks", "rmse_K", "max_abs_error_K", "service_unserved_kWh",
        "electrical_kWh", "max_energy_residual_J", "max_command_slew",
        "max_estimation_header_error_K", "max_estimation_modulation_error",
        "controller_sampling_s",
    ),
    "wp3_pi_comparison.csv": (
        "kp_command_per_K", "ki_command_per_Ks",
        "antiwindup_saturation_events", "antiwindup_slew_events",
        "iae_Ks", "rmse_K", "max_abs_error_K", "service_unserved_kWh",
        "electrical_kWh", "max_energy_residual_J", "max_command_slew",
    ),
    "wp3_robustness_matrix.csv": (
        "iae_Ks", "rmse_K", "max_abs_error_K",
        "service_unserved_kWh", "electrical_kWh",
    ),
}
IDENTITY = {
    "wp4_robustness_matrix.csv": ("case", "method"),
    "wp3_pi_comparison.csv": ("hx_mode", "controller"),
    "wp3_robustness_matrix.csv": ("case", "method"),
}


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def key(row, names):
    return tuple(row[n] for n in names)


def validate_matrix(name: str):
    path = RESULTS / name
    ref = FROZEN / name
    if not (path.exists() and ref.exists()):
        raise RuntimeError(f"Required source/frozen benchmark missing: {name}")
    actual, expected = read_csv(path), read_csv(ref)
    keys = IDENTITY[name]
    a = {key(row, keys): row for row in actual}
    b = {key(row, keys): row for row in expected}
    if len(a) != len(actual) or len(b) != len(expected):
        raise RuntimeError(f"Duplicate case/controller key: {name}")
    if set(a) != set(b):
        raise RuntimeError(f"Benchmark case/controller set changed in {name}")
    checked = 0
    for identity in sorted(a):
        actual_row, expected_row = a[identity], b[identity]
        for n in NUMERIC_FIELDS[name]:
            try:
                va, vb = float(actual_row[n]), float(expected_row[n])
            except (KeyError, TypeError, ValueError) as e:
                raise RuntimeError(f"Missing/invalid {name}/{identity}/{n}") from e
            if not (isfinite(va) and isfinite(vb)):
                raise RuntimeError(f"Nonfinite {name}/{identity}/{n}")
            if not isclose(va, vb, rel_tol=NUMERICAL_REL_TOL,
                           abs_tol=NUMERICAL_ABS_TOL):
                raise RuntimeError(
                    f"Unreviewed L1 numerical drift: {name}/{identity}/{n}: "
                    f"regenerated={va:.12g}, frozen={vb:.12g}. "
                    "Do not overwrite v2; create and review a new benchmark ID."
                )
            checked += 1
        if name == "wp4_robustness_matrix.csv":
            for n in ("finite", "information_mode", "solver", "error",
                      "status_counts"):
                if actual_row[n] != expected_row[n]:
                    raise RuntimeError(f"Unreviewed categorical change {name}/{identity}/{n}")
    return {"rows":len(actual), "numeric_cells_checked":checked,
            "frozen_sha256":hashlib.sha256(ref.read_bytes()).hexdigest(),
            "regenerated_sha256":hashlib.sha256(path.read_bytes()).hexdigest()}


def check_report():
    live = json.loads((RESULTS / "wp5_analysis.json").read_text())
    old = json.loads((FROZEN / "wp5_analysis.json").read_text())
    matrix_bytes = (RESULTS / "wp4_robustness_matrix.csv").read_bytes()
    if live["source_matrix_sha256"] != hashlib.sha256(matrix_bytes).hexdigest():
        raise RuntimeError("WP5 report source SHA does not match regenerated WP4 matrix")
    for field in ("raw_iae_wins", "service_qualified_iae_wins",
                  "mpc_relay_service_matched_cases", "MPC_total_fallback_events",
                  "all_methods_service_pass_cases", "completed_runs", "source_rows"):
        if live[field] != old[field]:
            raise RuntimeError(f"Unreviewed WP5 benchmark summary drift: {field}")
    if live["source_rows"] != 100 or live["completed_runs"] != 100:
        raise RuntimeError("Corrected synthetic L1 benchmark incomplete")
    return {"source_matrix_sha256":live["source_matrix_sha256"],
            "raw_iae_wins":live["raw_iae_wins"],
            "service_qualified_iae_wins":live["service_qualified_iae_wins"]}


def main():
    m = json.loads((FROZEN / "manifest.json").read_text())
    if m.get("benchmark_id") != BENCHMARK:
        raise RuntimeError("Frozen benchmark ID absent/mismatched")
    results = {name:validate_matrix(name) for name in NUMERIC_FIELDS}
    outcome = {"benchmark_id":BENCHMARK, "status":"numerical regression verified only",
               "scope":"synthetic L1, not compressor OEM / measured hardware",
               "files":results, "wp5":check_report()}
    print(json.dumps(outcome,indent=2))
    return outcome


if __name__ == "__main__":
    main()
