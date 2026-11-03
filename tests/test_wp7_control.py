"""WP7 transfer pilot: sensor parity, fail-closed real-fluid truth and service gates."""
from __future__ import annotations

from math import exp, log
import copy
from unittest import TestCase, skipUnless
from unittest.mock import patch
import unittest

from ht_hp_controlbench.benchmark import nominal_tunings
from ht_hp_controlbench.core import Disturbance
from ht_hp_controlbench.mpc import MPCConfig
from ht_hp_controlbench.pi import PISettings
from ht_hp_controlbench.realfluid import CycleAssumptions, build_cycle_map
from ht_hp_controlbench.wp7_control import (
    PropertyControlCase, declared_property_cases, run_property_controller, compare_property_pair
)


class AnalyticStructuralProperties:
    """NOT fluid measurements: deterministic test double for plumbing only."""
    def __init__(self):
        self.h1=290000.
    def __call__(self,key,*args):
        if len(args)==1:
            if key=="Tcrit":return 470.
            if key=="Tmin":return 200.
            if key=="Tmax":return 600.
            raise AssertionError((key,args))
        v1,x1,v2,x2,fluid=args
        if fluid in ("IF97::Water","Water"):
            if key=="P" and v1=="T" and v2=="Q":
                return (1.003 if fluid=="Water" else 1.)*300000.*exp((x1-406.2)/45.)
            if key=="H" and v1=="T" and v2=="P":
                return 4200.*(x1-273.15)
            if key=="T" and v1=="P" and v2=="H":
                return 273.15+x2/4200.
            raise AssertionError((key,args))
        if key=="P" and v1=="T" and v2=="Q":return 50000.*exp((x1-300.)/60.)
        if key=="H" and v1=="T" and v2=="P":
            tsat=300.+60.*log(x2/50000.)
            h=(200000.+1500.*(x1-273.15)) if x1>=tsat else 1000.*(x1-273.15)
            if x1>=tsat:self.h1=h
            return h
        if key=="S" and v1=="T" and v2=="P":return 1200.
        if key=="D" and v1=="T" and v2=="P":return 16.*(300./x1)
        if key=="H" and v1=="P" and v2=="S":return self.h1+130000.
        if key=="H" and v1=="P" and v2=="Q":
            tsat=300.+60.*log(x1/50000.)
            return 200000.+1500.*(tsat-273.15)
        if key=="T" and v1=="P" and v2=="H":return (x2-200000.)/1500.+273.15
        if key=="Q" and v1=="P" and v2=="H":return .4
        raise AssertionError((key,args))


class WP7MatchedControlStructuralTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.props=AnalyticStructuralProperties()
        cls.model=build_cycle_map("Fake",(328.15,333.15,338.15),
                     (398.15,403.15,406.2,410.15,413.15),
                     (.5,.75,1.0),CycleAssumptions(),cls.props)
        cls.settings=PISettings(.038,1.2e-5,"frozen_test_PI")
        cls.cfg=MPCConfig(horizon=2,period_s=120.,integration_step_s=20.)

    def run_case(self,method,case=None,**kwargs):
        return run_property_controller(
            self.model,case or PropertyControlCase(),method,
            pi_settings=self.settings,cfg=self.cfg,
            duration_s=360.,step_s=20.,props=self.props,**kwargs)

    def test_scenarios_are_explicit_and_distinct(self):
        cases=declared_property_cases()
        self.assertEqual(len(cases),len({c.name for c in cases}))
        self.assertEqual(cases[0].source_drop_k,0)
        self.assertGreater(cases[1].source_drop_k,0)
        self.assertEqual(cases[-1].sensor_delay_samples,1)
        with self.assertRaises(ValueError):PropertyControlCase(sensor_delay_samples=-1)
        with self.assertRaises(ValueError):PropertyControlCase(sensor_noise_sd_k=float("nan"))

    def test_one_truth_plant_both_methods_and_energy_balance(self):
        pi=self.run_case("PI_IMC")
        mpc=self.run_case("MPC_persistence")
        for row in (pi,mpc):
            self.assertEqual(row["status"],"complete",row["failure_reason"])
            self.assertEqual(row["completed_time_s"],360.)
            self.assertEqual(row["decisions"],3)
            self.assertFalse(row["equipment_verified"])
            self.assertGreaterEqual(row["electricity_kWh"],0.)
            self.assertLess(row["max_energy_residual_J"],1.)
            self.assertLessEqual(row["max_applied_command_slew"],.05000001)
            self.assertEqual(len(row["true_states_at_decisions"]),3)
            self.assertEqual(len(row["estimated_states_at_decisions"]),3)
            self.assertEqual(row["noise_draws"],[0.]*6)
        self.assertIn("WP2 synthetic",mpc["mpc_predictor"])
        self.assertEqual(pi["measurement"],mpc["measurement"])

    def test_pair_uses_same_seeded_noise_but_not_hidden_truth(self):
        case=PropertyControlCase("sensor",sensor_noise_sd_k=.2,sensor_delay_samples=1,seed=44)
        pi=self.run_case("PI_IMC",case)
        mpc=self.run_case("MPC_persistence",case)
        self.assertEqual(pi["noise_draws"],mpc["noise_draws"])
        self.assertGreater(max(abs(x-y) for x,y in zip(
            [s[1] for s in pi["true_states_at_decisions"]],
            pi["sensed_buffer_at_decisions"])),1e-4)
        self.assertEqual(pi["sensor_delay_s"],60.)

    def test_failure_is_not_silently_ranked(self):
        original=__import__("ht_hp_controlbench.wp7_control",fromlist=["_disturbance"])._disturbance
        def adversarial(t,case):
            if t>=120.:
                return Disturbance(t_source=300.)
            return original(t,case)
        with patch("ht_hp_controlbench.wp7_control._disturbance",side_effect=adversarial):
            result=self.run_case("PI_IMC")
        self.assertEqual(result["status"],"failed_physical_or_numerical_constraint")
        self.assertIsNone(result["iae_Ks"])
        self.assertIsNone(result["electricity_kWh"])
        self.assertFalse(result["matched_service_gate"])
        self.assertTrue(result["failure_reason"])

    def test_no_energy_saving_credit_for_unmatched_terminal_resources(self):
        pi=self.run_case("PI_IMC")
        mpc=self.run_case("MPC_persistence")
        # The nominal physical-control pilot can be compared descriptively,
        # but resource equivalence is always checked before electricity credit.
        group=compare_property_pair(pi,mpc)
        self.assertIn("eligible_for_conditional_electricity_comparison",group)
        adversarial=copy.deepcopy(mpc)
        adversarial["final_header_energy_delta_kWh"] = pi["final_header_energy_delta_kWh"]+9.72
        adversarial["final_total_energy_delta_kWh"] = pi["final_total_energy_delta_kWh"]+9.72
        pair=compare_property_pair(pi,adversarial)
        self.assertFalse(pair["eligible_for_conditional_electricity_comparison"])
        self.assertIsNone(pair["delta_electricity_kWh"])
        self.assertIn("terminal_header_inventory_mismatch",pair["ineligibility_reasons"])
        self.assertIn("terminal_total_thermal_energy_mismatch",pair["ineligibility_reasons"])
        different=copy.deepcopy(mpc)
        different["final_compressor_modulation"] = pi["final_compressor_modulation"]+0.1
        pair=compare_property_pair(pi,different)
        self.assertFalse(pair["eligible_for_conditional_electricity_comparison"])
        self.assertIn("terminal_compressor_modulation_mismatch",pair["ineligibility_reasons"])
        biased=copy.deepcopy(mpc)
        biased["seed"] += 1
        with self.assertRaisesRegex(ValueError,"unequal scenario"):
            compare_property_pair(pi,biased)

    def test_mpc_solver_failure_has_bounded_pi_fallback(self):
        row=self.run_case("MPC_persistence",force_mpc_failure=True)
        self.assertEqual(row["status"],"complete",row["failure_reason"])
        self.assertEqual(row["pi_fallbacks"],row["decisions"])
        self.assertEqual(row["accepted_mpc"],0)
        self.assertLessEqual(row["max_applied_command_slew"],.05000001)

try:
    import CoolProp
    HAVE_COOLPROP=True
except ImportError:
    HAVE_COOLPROP=False


@skipUnless(HAVE_COOLPROP,"real CoolProp needed for EOS-backed control integration")
class WP7MatchedControlCoolPropTests(TestCase):
    def test_real_property_nominal_control_short_run(self):
        model=build_cycle_map("R1233zd(E)",(328.15,333.15,338.15),
                   (398.15,403.15,406.2,410.15,413.15),(.5,.75,1.0))
        settings,_,_=nominal_tunings()
        row=run_property_controller(model,PropertyControlCase(),
             "PI_IMC",pi_settings=settings["IMC_lambda_0p5tau"],
             duration_s=360.,step_s=20.)
        self.assertEqual(row["status"],"complete",row["failure_reason"])
        self.assertLess(row["max_energy_residual_J"],1.)
        self.assertFalse(row["equipment_verified"])


if __name__=="__main__":
    unittest.main()
