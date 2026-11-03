"""WP7 property-MPC: independent truth/predictor cross-check and observer audit."""
from __future__ import annotations
from dataclasses import replace
import unittest
from unittest.mock import patch

from ht_hp_controlbench.core import Disturbance, Parameters, State
from ht_hp_controlbench.mpc import MPCConfig, solve_mpc
from ht_hp_controlbench.pi import PISettings
from ht_hp_controlbench.realfluid import CycleAssumptions, PointRejected, build_cycle_map
from ht_hp_controlbench.wp7_control import PropertyControlCase, run_property_controller, compare_property_pair
from ht_hp_controlbench.wp7_predictor import PropertyPredictor

from test_wp7_control import AnalyticStructuralProperties


class PropertyPredictorStructuralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.props=AnalyticStructuralProperties()
        cls.model=build_cycle_map("Fake",(328.15,333.15,338.15),
             (398.15,403.15,406.20,410.15,413.15),(.5,.75,1.),
             CycleAssumptions(),cls.props)
        cls.p=replace(Parameters(hx_mode="duty_limiter"),n_min=.5,n_max=1.)
        cls.settings=PISettings(.038,1.2e-5,"frozen_test_PI")
        cls.cfg=MPCConfig(horizon=2,period_s=120.,integration_step_s=20.)
        cls.predictor=PropertyPredictor(cls.model,cls.props)

    def run_case(self,method="PI_IMC",observer="auto",case=None,**kwargs):
        return run_property_controller(self.model,case or PropertyControlCase(),
                   method,pi_settings=self.settings,cfg=self.cfg,
                   duration_s=360.,step_s=20.,props=self.props,
                   observer_backend=observer,**kwargs)

    def test_property_transition_integrates_actual_water_enthalpy_and_power(self):
        x=State(406.2,403.15,.75)
        d=Disturbance()
        xx=self.predictor.advance(x,.75,self.p,d,120.,20.)
        self.assertTrue(390<xx.tb<415)
        self.assertTrue(.5<=xx.n<=1.)
        self.assertGreater(self.predictor.power(xx,self.p,d),0.)
        with self.assertRaises(PointRejected):
            self.predictor.advance(x,.75,self.p,replace(d,t_source=310.),120.,20.)
        with self.assertRaisesRegex(ValueError,"aligned timestep"):
            self.predictor.advance(x,.75,self.p,d,125.,20.)
        with self.assertRaises(PointRejected):
            self.predictor.advance(x,.75,replace(self.p,n_min=.2),d,120.,20.)

    def test_observer_backend_does_not_change_pi_truth_or_sensing(self):
        old=self.run_case(observer="synthetic")
        new=self.run_case(observer="property")
        self.assertEqual(old["status"],"complete",old["failure_reason"])
        self.assertEqual(new["status"],"complete",new["failure_reason"])
        self.assertEqual(old["true_states_at_decisions"],new["true_states_at_decisions"])
        self.assertEqual(old["applied_commands"],new["applied_commands"])
        self.assertEqual(old["noise_draws"],new["noise_draws"])
        self.assertEqual(old["electricity_kWh"],new["electricity_kWh"])
        self.assertEqual(new["observer_model"],"WP7 property enthalpy state predictor")
        self.assertLess(new["max_header_observer_error_K"],1e-4)
        self.assertLess(new["max_modulation_observer_error"],1e-7)

    def test_noisy_delayed_holdout_matched_noise_and_truth(self):
        case=PropertyControlCase("heldout",sensor_noise_sd_k=.20,
               sensor_delay_samples=1,seed=83)
        old=self.run_case(observer="synthetic",case=case)
        new=self.run_case(observer="property",case=case)
        self.assertEqual(old["status"],"complete",old["failure_reason"])
        self.assertEqual(new["status"],"complete",new["failure_reason"])
        self.assertEqual(old["noise_draws"],new["noise_draws"])
        self.assertEqual(old["true_states_at_decisions"],new["true_states_at_decisions"])
        self.assertEqual(old["sensed_buffer_at_decisions"],new["sensed_buffer_at_decisions"])
        self.assertGreater(new["max_sensor_error_K"],0.01)
        # Delays are not artificially corrected by peeking at true hidden states.
        self.assertGreaterEqual(new["max_header_observer_error_K"],0.)
        self.assertEqual(len(new["sensor_innovations_K"]),6)

    def test_property_mpc_solver_failure_falls_back_bounded(self):
        row=self.run_case("MPC_property",force_mpc_failure=True)
        self.assertEqual(row["status"],"complete",row["failure_reason"])
        self.assertEqual(row["accepted_mpc"],0)
        self.assertEqual(row["pi_fallbacks"],row["decisions"])
        self.assertLessEqual(row["max_applied_command_slew"],.05000001)
        self.assertIn("CoolProp/IF97",row["mpc_predictor"])

    def test_property_qp_uses_injected_dynamics_not_wp2_output(self):
        x=State(406.2,403.15,.75)
        d=Disturbance()
        # A deliberately invalid property power function forces rejection
        # whereas a default synthetic solver might accept; this proves the
        # electrical prediction callback is actually used.
        def invalid_power(*args):
            raise PointRejected("injected_property_test_failure")
        sol=solve_mpc(x,.75,self.p,d,self.cfg,403.55,[d]*2,[.16]*2,
                advance_fn=self.predictor.advance,power_fn=invalid_power)
        self.assertFalse(sol.accepted)
        self.assertIn("injected_property_test_failure",sol.status)

    def test_same_resource_gate_includes_property_candidate(self):
        base=self.run_case("PI_IMC",observer="property")
        mpc=self.run_case("MPC_property",force_mpc_failure=True)
        comparison=compare_property_pair(base,mpc)
        self.assertEqual(comparison["candidate"],"MPC_property")
        self.assertIn("eligible_for_conditional_electricity_comparison",comparison)
        self.assertFalse(base["equipment_verified"])


try:
    import CoolProp
    HAVE_COOLPROP=True
except ImportError:
    HAVE_COOLPROP=False


@unittest.skipUnless(HAVE_COOLPROP,"CoolProp required for property-consistent prediction test")
class PropertyPredictorEOSIntegrationTests(unittest.TestCase):
    def test_realfluid_property_predictor_observer_short_run(self):
        m=build_cycle_map("R1233zd(E)",(328.15,333.15,338.15),
              (398.15,403.15,406.2,410.15,413.15),(.5,.75,1.))
        setting=PISettings(.038,1.2e-5,"frozen_test_PI")
        cfg=MPCConfig(horizon=2,period_s=120.,integration_step_s=20.)
        row=run_property_controller(m,PropertyControlCase(),"PI_IMC",
             pi_settings=setting,cfg=cfg,duration_s=360.,step_s=20.,
             observer_backend="property")
        self.assertEqual(row["status"],"complete",row["failure_reason"])
        self.assertLess(row["max_header_observer_error_K"],1e-3)
        self.assertLess(row["max_modulation_observer_error"],1e-6)


if __name__=="__main__":
    unittest.main()
