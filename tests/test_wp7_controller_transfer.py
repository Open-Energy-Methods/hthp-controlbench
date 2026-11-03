"""WP7 truth / WP2 controller transfer pilot: independent setup and failure gates."""
from __future__ import annotations

import unittest
from ht_hp_controlbench.mpc import MPCConfig
from ht_hp_controlbench.realfluid import build_cycle_map
from ht_hp_controlbench.storage_flexibility import WP3_IMC
from ht_hp_controlbench.property_controller_transfer import (
    PropertyTransferCase, TRANSFER_CASES, run_transfer, matched_transfer_pilot
)
from test_wp8_storage import InvertibleFake


class TransferPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.props=InvertibleFake()
        cls.model=build_cycle_map("Fake",[328.15,333.15,338.15],
                                  [403.15,406.2,413.15],[.5,.75,1],
                                  props=cls.props)
        cls.cfg=MPCConfig(horizon=3,period_s=120.,integration_step_s=20.)

    def test_common_property_truth_and_no_hidden_sensor_advantage(self):
        case=PropertyTransferCase("noise",sensor_noise_sd_k=.01,seed=47)
        results=[run_transfer(self.model,m,case,WP3_IMC,props=self.props,
                              duration_s=1200.,cfg=self.cfg)
                 for m in ("pi","mpc")]
        self.assertEqual([x["method"] for x in results],["pi","mpc"])
        for result in results:
            self.assertEqual(result["status"],"complete",result["error"])
            self.assertEqual(result["completed_steps"],60)
            self.assertEqual(result["sensor_delay_s"],0)
            self.assertFalse(result["equipment_verified"])
            self.assertIn("WP7",result["truth"])
            self.assertIn("WP2",result["predictor"])
            self.assertGreater(result["electrical_kWh"],0)
            self.assertLess(abs(result["energy_residual_J"]),0.02)
            self.assertLessEqual(result["service_qualified_fraction"],1.)
        self.assertEqual(results[0]["noise_draws_K"],results[1]["noise_draws_K"])
        self.assertGreaterEqual(results[1]["pi_fallback_events"],0)
        self.assertEqual(results[0]["pi_fallback_events"],0)
        self.assertEqual(results[1]["controller_decisions"],
                         results[1]["mpc_accepted"]+results[1]["pi_fallback_events"])

    def test_outside_property_map_fails_closed_and_cannot_be_ranked(self):
        case=PropertyTransferCase("invalid_source",source_step_k=40.)
        bad=run_transfer(self.model,"pi",case,WP3_IMC,props=self.props,
                         duration_s=1200.,cfg=self.cfg)
        self.assertEqual(bad["status"],"rejected_property_envelope")
        self.assertLess(bad["completed_steps"],bad["requested_steps"])
        self.assertIsNone(bad["iae_Ks"])
        summary=matched_transfer_pilot(self.model,WP3_IMC,
                     cases=(case,),duration_s=1200.,cfg=self.cfg,props=self.props)
        self.assertFalse(summary["paired"][0]["both_complete"])
        self.assertFalse(summary["paired"][0]["both_service_qualified"])
        self.assertIsNone(summary["paired"][0]["qualified_winner"])
        self.assertIsNone(summary["paired"][0]["delta_electricity_mpc_minus_pi_kWh"])

    def test_invalid_observation_settings_rejected(self):
        for case in (
            lambda:PropertyTransferCase("x",sensor_delay_samples=-1),
            lambda:PropertyTransferCase("x",sensor_noise_sd_k=-0.1),
            lambda:PropertyTransferCase("x",source_step_k=float("nan")),
        ):
            with self.assertRaises(ValueError):case()
        with self.assertRaises(ValueError):
            run_transfer(self.model,"unknown",TRANSFER_CASES[0],WP3_IMC,props=self.props)


if __name__=="__main__":
    unittest.main()
