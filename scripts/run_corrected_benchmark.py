"""Generate the corrected L1_RelayPeak_v2 controller benchmark in isolation.

python scripts/run_corrected_benchmark.py

This regenerates into a scratch directory without modifying published v2 or
historic v1 results. It checks the regenerated matrix against the reviewed v2
matrix and reports provenance; it does not claim new controller validation.
"""
from __future__ import annotations

import hashlib
import json
import os
import numpy as np
from pathlib import Path
import platform
import subprocess
import sys

from ht_hp_controlbench.benchmark import BENCHMARK_ID

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / ("_recomputed_" + BENCHMARK_ID)
PUBLISHED = ROOT / "results" / BENCHMARK_ID
PIPELINE = (
    "run_wp3.py",
    "run_wp3_robustness.py",
    "run_wp4.py",
    "run_wp4_robustness.py",
    "run_wp5.py",
)
SOURCE_FILES = (
    "ht_hp_controlbench/benchmark.py", "ht_hp_controlbench/pi.py",
    "ht_hp_controlbench/core.py", "ht_hp_controlbench/sim.py",
    "ht_hp_controlbench/robustness.py", "ht_hp_controlbench/mpc.py",
    "ht_hp_controlbench/mpc_robustness.py",
    "ht_hp_controlbench/wp5_analysis.py", "pyproject.toml",
    *(f"scripts/{name}" for name in PIPELINE),
)


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(out: Path) -> dict:
    from importlib.metadata import version
    from ht_hp_controlbench.wp5_analysis import load_matrix, analyze
    from ht_hp_controlbench.benchmark import nominal_tunings, tuning_manifest

    matrix = out / "wp4_robustness_matrix.csv"
    summary = json.loads((out / "wp4_robustness_summary.json").read_text())
    if summary.get("benchmark_id") != BENCHMARK_ID:
        raise RuntimeError("WP4 source matrix lacks corrected benchmark identifier")
    report = json.loads((out / "wp5_analysis.json").read_text())
    if report.get("benchmark_id") != BENCHMARK_ID:
        raise RuntimeError("WP5 output is not linked to corrected WP4 benchmark")
    if report.get("source_matrix_sha256") != checksum(matrix):
        raise RuntimeError("WP5 source hash does not match regenerated WP4 matrix")
    validated = analyze(load_matrix(matrix))
    # Independent replay must preserve every case/method metric from the
    # reviewed CI snapshot; timestamps, report prose and plotting files are
    # deliberately NOT used as numerical-equivalence evidence.
    published_matrix = PUBLISHED / "wp4_robustness_matrix.csv"
    if not published_matrix.exists():
        raise RuntimeError("Reviewed v2 source matrix missing: cannot verify replay")
    expected = load_matrix(published_matrix)
    current = load_matrix(matrix)
    key = lambda r: (r["case"], r["method"])
    if {key(r) for r in current} != {key(r) for r in expected}:
        raise RuntimeError("Replayed matrix has missing or unexpected scenarios")
    from ht_hp_controlbench.wp5_analysis import METRICS
    original_by_key = {key(r): r for r in expected}
    for row in current:
        reference = original_by_key[key(row)]
        for metric in METRICS:
            a, b = float(row[metric]), float(reference[metric])
            if not (np.isfinite(a) and np.isfinite(b)):
                raise RuntimeError(f"Nonfinite replay value: {key(row)} {metric}")
            if abs(a - b) > 1e-4 * max(1., abs(b)):
                raise RuntimeError(f"V2 numerical replay differs: {key(row)} {metric}: {a} versus {b}")
    if validated["source_rows"] != 100:
        raise RuntimeError("incomplete 20-case x 5-method corrected benchmark")
    if report["raw_iae_wins"] != validated["raw_iae_wins"]:
        raise RuntimeError("WP5 IAE report was not generated from supplied matrix")
    tunings, step, relay = nominal_tunings()
    recorded = summary["nominal_tuning"]["gains"]["relay_PI"]
    if abs(recorded["kp_command_per_K"] - tunings["relay_PI"].kp) > 1e-12:
        raise RuntimeError("WP4 stored relay tune differs from independent nominal tune")
    return {
        "benchmark_id": BENCHMARK_ID,
        "status": "synthetic only; no compressor-map or real-fluid dynamic control validation",
        "note": "Historical flat results/wp3*, wp4*, wp5* remain the uncorrected L1 benchmark v1.",
        "source_sha256": {p: checksum(ROOT / p) for p in SOURCE_FILES},
        "result_sha256": {p.name: checksum(p) for p in sorted(out.iterdir()) if p.is_file()
                          and p.name not in ("manifest.json", "BENCHMARK_README.md")},
        "environment": {"python": platform.python_version(), "numpy": version("numpy"),
                        "scipy": version("scipy")},
        "scenario_runs": validated["source_rows"],
        "failed_runs": len(validated["failed_runs"]),
        "raw_iae_wins": validated["raw_iae_wins"],
        "service_qualified_iae_wins": validated["service_qualified_iae_wins"],
        "mpc_fallback_events": validated["MPC_total_fallback_events"],
        "source_matrix_sha256": checksum(matrix),
        "nominal_tuning": tuning_manifest(tunings, step, relay),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HTHP_RESULTS_DIR=str(OUTPUT))
    for script in PIPELINE:
        print(f"Regenerating {script} into {OUTPUT.relative_to(ROOT)}", flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)],
                       env=env, cwd=ROOT, check=True)
    result = manifest(OUTPUT)
    (OUTPUT / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (OUTPUT / "BENCHMARK_README.md").write_text(
        "# Corrected L1 controller benchmark — " + BENCHMARK_ID + "\n\n"
        "These results were regenerated from the current nominal-plant identification. "
        "The relay amplitude uses actual steady-cycle temperature peaks rather than relay "
        "switch values. The same fixed nominal PI gains are carried into every PI/MPC "
        "scenario, with one shared noisy/delayed buffer measurement per case.\n\n"
        "The historical files immediately under results/ AND the reviewed v2 snapshot were intentionally preserved. "
        "Refer to manifest.json for source hashes, gains and metric counts, and to "
        "wp5_comparative_report.md for service-gated findings. "
        "No manufacturer compressor map, real-fluid dynamic benchmark, investment saving "
        "or formal stability guarantee is established.\n")
    print("Verified independent replay of corrected benchmark:", result["benchmark_id"],
          result["scenario_runs"], "runs,", result["failed_runs"], "failures")


if __name__ == "__main__":
    main()
