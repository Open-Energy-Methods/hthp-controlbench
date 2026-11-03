"""Numeric v2 benchmark gate: tampered results must not masquerade as replay."""
from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_published_benchmark as checker


class BenchmarkSnapshotGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.frozen = self.root / checker.BENCHMARK
        self.frozen.mkdir()
        self.file = "wp4_robustness_matrix.csv"
        self.fields = ["case", "method", "finite", "information_mode",
                       "solver", "error", "status_counts",
                       *checker.NUMERIC_FIELDS[self.file]]
        self.row = {key: "1" for key in self.fields}
        self.row.update(case="nominal", method="relay_PI", finite="True",
                        information_mode="one noisy/delayed buffer-temperature measurement",
                        solver="none", error="", status_counts="{}",
                        iae_Ks="975.0", electrical_kWh="584.2",
                        max_energy_residual_J="0.00001")
        self.write(self.frozen / self.file, self.row)
        self.write(self.root / self.file, self.row)

    def write(self, path, row):
        with path.open("w",newline="",encoding="utf-8") as stream:
            writer=csv.DictWriter(stream,fieldnames=self.fields)
            writer.writeheader()
            writer.writerow(row)

    def run_gate(self):
        with patch.object(checker, "RESULTS", self.root), \
             patch.object(checker, "FROZEN", self.frozen):
            return checker.validate_matrix(self.file)

    def test_unchanged_replay_passes(self):
        got=self.run_gate()
        self.assertEqual(got["rows"],1)
        self.assertEqual(got["numeric_cells_checked"],
                         len(checker.NUMERIC_FIELDS[self.file]))

    def test_numerical_drift_fails(self):
        altered=dict(self.row, iae_Ks="990.0")
        self.write(self.root / self.file,altered)
        with self.assertRaisesRegex(RuntimeError,"Unreviewed L1 numerical drift"):
            self.run_gate()

    def test_information_budget_drift_fails(self):
        altered=dict(self.row, information_mode="full observed plant states")
        self.write(self.root / self.file,altered)
        with self.assertRaisesRegex(RuntimeError,"categorical change"):
            self.run_gate()

    def test_nonfinite_metric_fails(self):
        altered=dict(self.row, electrical_kWh="nan")
        self.write(self.root / self.file,altered)
        with self.assertRaisesRegex(RuntimeError,"Nonfinite"):
            self.run_gate()

    def test_missing_controller_fails(self):
        with (self.root / self.file).open("w",encoding="utf-8") as stream:
            stream.write(",".join(self.fields)+"\n")
        with self.assertRaisesRegex(RuntimeError,"case/controller set changed"):
            self.run_gate()


if __name__ == "__main__":
    unittest.main()
