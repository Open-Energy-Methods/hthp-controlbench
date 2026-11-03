"""WP8 numerical-sensitivity decision logic must fail closed."""
from __future__ import annotations
import copy
import unittest
from scripts.run_wp8_timestep import DTS,record_from_pair,summarize


def fake_records(savings=(.12,.11,.105),eligible=True):
    rows=[]
    for dt, saving in zip(DTS,savings):
        rows.append({
            "dt_s":dt,"creditable_at_this_step":eligible,
            "eligible_cost_saving_eur":saving if eligible else None,
            "ineligibility_reasons":[] if eligible else ["process_service_failed"]})
    return rows


class WP8TimestepScreenTests(unittest.TestCase):
    def test_convergent_small_positive_signal_remains_uncalibrated(self):
        x=summarize(fake_records())
        self.assertEqual(x["numerical_screen"],
            "NUMERICAL_SIGNAL_SCREEN_PASSED__NOT_ECONOMIC_VALIDATION")
        self.assertFalse(x["equipment_financial_saving_claim"])
        self.assertFalse(x["mathematical_convergence_order_established"])
        self.assertTrue(x["conditional_numerical_resolution"])

    def test_unqualified_resolution_blocks_credit(self):
        rows=fake_records()
        rows[1]["creditable_at_this_step"]=False
        rows[1]["eligible_cost_saving_eur"]=None
        x=summarize(rows)
        self.assertFalse(x["all_comparisons_creditable"])
        self.assertFalse(x["conditional_numerical_resolution"])
        self.assertEqual(x["numerical_screen"],
            "NO_CREDIT_UNQUALIFIED_SERVICE_OR_TERMINAL_STATES")

    def test_effect_smaller_than_resolution_change_blocks_signal(self):
        x=summarize(fake_records((.2,.04,.03)))
        self.assertEqual(x["numerical_screen"],
            "NUMERICAL_CHANGE_COMPARABLE_TO_NOMINAL_SAVING")
        self.assertFalse(x["conditional_numerical_resolution"])

    def test_negative_savings_cannot_pass(self):
        x=summarize(fake_records((-.04,-.03,-.025)))
        self.assertFalse(x["conditional_numerical_resolution"])
        self.assertEqual(x["numerical_screen"],
            "NO_POSITIVE_SAVING_AT_EVERY_RESOLUTION")

    def test_nonshrinking_resolution_changes_block_signal(self):
        x=summarize(fake_records((.13,.125,.07)))
        self.assertEqual(x["numerical_screen"],"NUMERICAL_REFINEMENT_NOT_SHRINKING")

    def test_input_shape_is_strict(self):
        with self.assertRaises(ValueError):summarize(fake_records()[:2])
        bad=fake_records()
        bad[-1]["dt_s"]=10.
        with self.assertRaises(ValueError):summarize(bad)

    def test_failed_run_is_never_carried_as_eligible_saving(self):
        pair={"status":"cost_saving_not_creditable","eligible_cost_saving_eur":None,
              "raw_cost_difference_eur":10.,
              "reasons":["terminal_header_inventory_mismatch"],
              "baseline":{"status":"complete","cost_eur":100.},
              "flexibility":{"status":"complete","cost_eur":90.}}
        rec=record_from_pair(60.,pair)
        self.assertFalse(rec["creditable_at_this_step"])
        self.assertIsNone(rec["eligible_cost_saving_eur"])
        self.assertEqual(rec["raw_cost_difference_eur"],10.)
        self.assertFalse(rec["equipment_verified"])

if __name__=="__main__":
    unittest.main()
