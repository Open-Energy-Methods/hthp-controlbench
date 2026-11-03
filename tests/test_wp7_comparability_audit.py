"""Independent WP7 v4 sensitivity audit - strict no-credit unit tests."""
import copy
from pathlib import Path
import json
import unittest

from scripts.audit_wp7_comparability import (
    audited_pair, audit, SOURCE, INVENTORY_KWH, ACTUATOR_TOL,
)


class ClaimAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.by={(r["case"],r["controller"]):r for r in cls.source["runs"]}

    def test_source_ledger_rederived_without_importing_original_comparator(self):
        check=audit(self.source)
        self.assertTrue(check["rederived_default_gate_matches_published"])
        self.assertEqual(
            [s["eligible_count"] for s in check["sensitivity"].values()],
            [4,2,1,1,1],
        )
        self.assertEqual(check["sensitivity"]["0.10"]["eligible_cases"],
                         ["nominal|PI_IMC"])
        self.assertFalse(check["source_hardware_validated"])

    def test_default_paired_eligible_but_tighter_inventory_fails(self):
        a=self.by[("nominal","PI_relay")]
        b=self.by[("nominal","MPC_property")]
        original=audited_pair(a,b,inventory_kwh=.5,actuator_tol=.02)
        tighter=audited_pair(a,b,inventory_kwh=.1,actuator_tol=.02)
        self.assertTrue(original["eligible"])
        self.assertFalse(tighter["eligible"])
        self.assertAlmostEqual(original["delta_total_inventory_kWh"],-.18559148289365,places=8)
        self.assertIsNone(tighter["eligible_delta_electricity_kWh"])
        self.assertGreater(original["eligible_delta_electricity_kWh"],0)

    def test_perturbed_service_or_bad_clock_cannot_be_eligible(self):
        a=self.by[("nominal","PI_IMC")]
        b=copy.deepcopy(self.by[("nominal","MPC_property")])
        b["matched_service_gate"]=False
        out=audited_pair(a,b,inventory_kwh=.5,actuator_tol=.02)
        self.assertFalse(out["eligible"])
        self.assertIn("service_failure",out["reasons"])
        b=copy.deepcopy(self.by[("nominal","MPC_property")])
        b["seed"]+=1
        with self.assertRaisesRegex(ValueError,"mismatched physical"):
            audited_pair(a,b,inventory_kwh=.5,actuator_tol=.02)

    def test_fabricated_energy_and_published_flags_rejected(self):
        altered=copy.deepcopy(self.source)
        altered["pairs"][0]["eligible_for_conditional_electricity_comparison"]=False
        with self.assertRaisesRegex(RuntimeError,"published default comparator"):
            audit(altered)
        altered=copy.deepcopy(self.source)
        # Unchanged eligibility label but altered results must be noticed.
        altered["pairs"][0]["delta_electricity_kWh"]+=1.
        with self.assertRaisesRegex(RuntimeError,"published energy delta"):
            audit(altered)

    def test_ineligible_pair_retains_null_energy_credit(self):
        a=self.by[("ua_proc_minus15_source_drop3","PI_IMC")]
        b=self.by[("ua_proc_minus15_source_drop3","MPC_property")]
        out=audited_pair(a,b,inventory_kwh=.5,actuator_tol=.02)
        self.assertFalse(out["complete"])
        self.assertFalse(out["eligible"])
        self.assertIsNone(out["eligible_delta_electricity_kWh"])
        self.assertIsNone(out["delta_electricity_kWh_raw_if_full"])

    def test_negative_and_nonfinite_tolerance_fails_closed(self):
        a=self.by[("nominal","PI_IMC")]
        b=self.by[("nominal","MPC_property")]
        for tol in (0,-1.,float("nan"),float("inf")):
            with self.assertRaises(ValueError):
                audited_pair(a,b,inventory_kwh=tol,actuator_tol=.02)
        with self.assertRaises(ValueError):
            audited_pair(a,b,inventory_kwh=.5,actuator_tol=0.)


if __name__=="__main__":
    unittest.main()
