"""WP7 v3 mismatch: prove truth-only perturbations, frozen control and fairness."""
from __future__ import annotations
from dataclasses import replace
from unittest import TestCase
import unittest

from ht_hp_controlbench.core import Parameters
from ht_hp_controlbench.mpc import MPCConfig
from ht_hp_controlbench.pi import PISettings
from ht_hp_controlbench.realfluid import CycleAssumptions,build_cycle_map
from ht_hp_controlbench.wp7_control import PropertyControlCase,run_property_controller,compare_property_pair
from test_wp7_control import AnalyticStructuralProperties


class ModelMismatchStructuralTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.props=AnalyticStructuralProperties()
        cls.model=build_cycle_map("Fake",(328.15,333.15,338.15),
            (398.15,403.15,406.20,410.15,413.15),
            (.5,.75,1.),CycleAssumptions(),cls.props)
        cls.nom=replace(Parameters(hx_mode="duty_limiter"),n_min=.5,n_max=1.)
        cls.cfg=MPCConfig(horizon=2,period_s=120.,integration_step_s=20.)
        cls.settings=PISettings(.038,1.2e-5,"Frozen test PI")

    def simulate(self,method="PI_IMC",p_true=None,case=None):
        return run_property_controller(
            self.model,case or PropertyControlCase(),method,
            pi_settings=self.settings,cfg=self.cfg,
            duration_s=360.,step_s=20.,props=self.props,
            observer_backend="property",truth_parameters=p_true,
            benchmark_id="WP7_TruthMismatch_Test",
        )

    def test_no_mismatch_is_exactly_backward_compatible(self):
        prior=self.simulate()
        explicit=self.simulate(p_true=self.nom)
        for key in ("noise_draws","true_states_at_decisions",
                    "estimated_states_at_decisions","sensed_buffer_at_decisions",
                    "applied_commands","iae_Ks","electricity_kWh",
                    "max_energy_residual_J","matched_service_gate"):
            self.assertEqual(prior[key],explicit[key],key)
        self.assertFalse(prior["truth_model_mismatch"])
        self.assertFalse(explicit["truth_model_mismatch"])

    def test_truth_only_dynamics_change_but_nominal_predictor_and_settings_hold(self):
        baseline=self.simulate(method="MPC_property")
        perturbed=self.simulate(method="MPC_property",
                      p_true=replace(self.nom,tau_n=self.nom.tau_n*1.30))
        self.assertEqual(baseline["status"],"complete",baseline["failure_reason"])
        self.assertEqual(perturbed["status"],"complete",perturbed["failure_reason"])
        self.assertTrue(perturbed["truth_model_mismatch"])
        self.assertEqual(perturbed["truth_parameter_ratios_to_nominal"],{"tau_n":1.3})
        self.assertEqual(perturbed["mpc_predictor"],baseline["mpc_predictor"])
        self.assertEqual(perturbed["observer_model"],baseline["observer_model"])
        self.assertEqual(perturbed["noise_draws"],baseline["noise_draws"])
        self.assertNotEqual(perturbed["true_states_at_decisions"],
                            baseline["true_states_at_decisions"])
        for r in (baseline,perturbed):
            self.assertLess(r["max_energy_residual_J"],1.)
            self.assertLessEqual(r["max_applied_command_slew"],.050000001)
            self.assertFalse(r["equipment_verified"])

    def test_all_methods_share_perturbed_truth_and_noise_seed(self):
        p_true=replace(self.nom,ua_proc=self.nom.ua_proc*1.1)
        case=PropertyControlCase("ua_adversarial",sensor_noise_sd_k=.2,
                                 sensor_delay_samples=1,seed=131)
        rows=[self.simulate(method=m,p_true=p_true,case=case)
              for m in ("PI_IMC","PI_relay","MPC_property")]
        self.assertEqual(len(set(r["benchmark_id"] for r in rows)),1)
        self.assertEqual(rows[0]["noise_draws"],rows[1]["noise_draws"])
        self.assertEqual(rows[0]["noise_draws"],rows[2]["noise_draws"])
        self.assertEqual(rows[0]["truth_parameter_ratios_to_nominal"],
                         rows[2]["truth_parameter_ratios_to_nominal"])
        self.assertEqual(rows[0]["true_states_at_decisions"][0],
                         rows[2]["true_states_at_decisions"][0])
        pair=compare_property_pair(rows[0],rows[2])
        self.assertEqual(pair["case"],case.name)
        self.assertEqual(pair["candidate"],"MPC_property")

    def test_comparison_rejects_different_actual_plant_and_actuators(self):
        a=self.simulate()
        b=self.simulate("MPC_property",p_true=replace(
            self.nom,tau_n=self.nom.tau_n*1.30))
        with self.assertRaisesRegex(ValueError,"different truth-plant"):
            compare_property_pair(a,b)
        with self.assertRaisesRegex(ValueError,"actuator"):
            self.simulate(p_true=replace(self.nom,n_min=.55))
        with self.assertRaisesRegex(ValueError,"actuator"):
            self.simulate(p_true=replace(self.nom,max_command_step=.03))

    def test_failed_or_incomplete_run_never_gets_energy_credit(self):
        true=replace(self.nom,khb=self.nom.khb*.9)
        a=self.simulate("PI_IMC",p_true=true)
        b=self.simulate("MPC_property",p_true=true)
        self.assertEqual(a["status"],"complete",a["failure_reason"])
        self.assertEqual(b["status"],"complete",b["failure_reason"])
        failed=dict(b,status="failed_physical_or_numerical_constraint",
                    electricity_kWh=None,iae_Ks=None,
                    matched_service_gate=False)
        result=compare_property_pair(a,failed)
        self.assertFalse(result["eligible_for_conditional_electricity_comparison"])
        self.assertIsNone(result["delta_electricity_kWh"])
        self.assertIn("incomplete",result["ineligibility_reasons"])


if __name__=="__main__":
    unittest.main()
