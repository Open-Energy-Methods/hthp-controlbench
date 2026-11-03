"""Regression tests for A04 corrected source identification and truthful reporting."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from ht_hp_controlbench.benchmark import BENCHMARK_ID, nominal_tunings, tuning_manifest
from scripts.run_wp5 import report

ROOT = Path(__file__).resolve().parents[1]


class CorrectedBenchmarkTests(unittest.TestCase):
    def test_nominal_relay_is_peak_based_not_stale_hardcoded_gain(self):
        tunings, step, relay = nominal_tunings()
        self.assertEqual(set(tunings), {
            "IMC_lambda_0p5tau", "IMC_lambda_1tau", "IMC_lambda_2tau", "relay_PI"
        })
        self.assertEqual(BENCHMARK_ID, "L1_RelayPeak_v2")
        self.assertGreater(relay.temperature_amplitude_k, 0.07)
        self.assertLess(relay.temperature_amplitude_k, 0.12)
        self.assertAlmostEqual(
            tunings["relay_PI"].kp, relay.ultimate_gain_u_per_k / 3.2, places=12)
        self.assertLess(tunings["relay_PI"].kp, 0.3)
        self.assertGreater(tunings["relay_PI"].kp, 0.15)
        self.assertEqual(tuning_manifest(tunings, step, relay)["benchmark_id"],
                         BENCHMARK_ID)

    def test_report_does_not_copy_historical_fallback_and_energy_numbers(self):
        data = json.loads((ROOT / "results" / "wp5_analysis.json").read_text())
        data["benchmark_id"] = "test_modified_benchmark"
        data["MPC_total_fallback_events"] = 7
        data["per_case"] = copy.deepcopy(data["per_case"])
        nominal = next(r for r in data["per_case"] if r["case"] == "nominal")
        nominal["MPC_minus_relay_electricity_kWh"] = 2.125
        text = report(data)
        self.assertIn("test_modified_benchmark", text)
        self.assertIn("7 actual fallbacks", text)
        self.assertIn("2.125 kWh", text)
        self.assertNotIn("48 actual fallbacks", text)
        self.assertNotIn("approximately 0.67 kWh", text)


if __name__ == "__main__":
    unittest.main()
