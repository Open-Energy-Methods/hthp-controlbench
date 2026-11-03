"""WP8: thermodynamic service and tariff flexibility regression, no OEM claims."""
import unittest
import numpy as np
from dataclasses import replace
from unittest.mock import patch

import ht_hp_controlbench.storage_flexibility as flexmod
from ht_hp_controlbench.realfluid import PointRejected

from ht_hp_controlbench.core import Disturbance, Parameters
from ht_hp_controlbench.realfluid import build_cycle_map
from ht_hp_controlbench.thermo_feasibility import HypotheticalEquipmentLimits
from ht_hp_controlbench.storage_flexibility import (SyntheticTariff, FlexSettings,
    physical_threshold, scan_reachable_band, simulate_24h, compare_flexibility)
from test_wp7_realfluid import FakeProperties

class InvertibleFake(FakeProperties):
    def __call__(self,key,*args):
        if len(args)==5 and args[-1]=='IF97::Water' and key=='T' and args[0]=='P' and args[2]=='H':
            return args[3]/4200.+273.15
        return super().__call__(key,*args)

class TestWP8(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.props=InvertibleFake()
        cls.map=build_cycle_map('Fake',[328.15,333.15,338.15],
                                [403.15,406.2,413.15],[.5,.75,1],props=cls.props)
        cls.cfg=FlexSettings(dt_s=60.)

    def test_tariff_units_and_exact_boundary(self):
        t=SyntheticTariff()
        self.assertEqual(t.price(3.999*3600),t.regular_eur_kwh)
        self.assertEqual(t.price(4*3600),t.low_eur_kwh)
        self.assertEqual(t.price(6*3600),t.high_eur_kwh)
        self.assertEqual(t.price(6.25*3600),t.regular_eur_kwh)
        for kw in ({'high_start_h':4}, {'low_eur_kwh':-1}, {'high_end_h':26}):
            with self.assertRaises(ValueError):replace(t,**kw)

    def test_bad_schedule_and_storage_inputs_fail(self):
        for kw in ({'mass_kg':0},{'dt_s':-1},{'duration_s':7200},
                   {'discharge_target_k':410},{'control_period_s':101}):
            with self.assertRaises(ValueError):replace(self.cfg,**kw)
        with self.assertRaises(ValueError):simulate_24h(self.map,'unknown',self.cfg,props=self.props)
        with self.assertRaises(ValueError):simulate_24h(self.map,settings=self.cfg,tariff=SyntheticTariff(high_end_h=6.26),props=self.props)
        with self.assertRaises(ValueError):scan_reachable_band(self.map,proposed_upper_k=400,props=self.props)

    def test_temperature_boundary_is_finite_hx_service_not_process_spec(self):
        low=physical_threshold()
        self.assertGreater(low,393.15)
        self.assertTrue(400<low<404)

    def test_water_enthalpy_band_and_300kw_naive_autonomy(self):
        r=scan_reachable_band(self.map,props=self.props,nodes=15)
        if r['full_path_checked']:
            self.assertAlmostEqual(r['enthalpy_kwh'],
                5000.*4200*(408.15-r['lower_k'])/3.6e6,places=5)
        self.assertFalse(r['equipment_verified'])
        self.assertAlmostEqual(r['max_uninterrupted_full_duty_minutes'],
                               r['enthalpy_kwh']/300*60)
        self.assertFalse(any(x.get('status')=='equipment_verified' for x in r['samples']))

    def test_mass_inventory_is_linear_under_same_water_properties(self):
        a=scan_reachable_band(self.map,mass_kg=2500,nodes=9,props=self.props)
        b=scan_reachable_band(self.map,mass_kg=5000,nodes=9,props=self.props)
        self.assertAlmostEqual(b['enthalpy_kwh'],2*a['enthalpy_kwh'],places=6)

    def test_declared_hypothetical_limit_blocks_charge_path(self):
        x=scan_reachable_band(self.map,props=self.props,nodes=11,
            limits=HypotheticalEquipmentLimits(p_cond_max_pa=1.e5))
        self.assertEqual(x['status'],'path_blocked')
        self.assertFalse(x['equipment_verified'])
        self.assertLess(x['enthalpy_kwh'],1.)

    def test_storage_policy_vs_baseline_same_truth_plant(self):
        a=simulate_24h(self.map,'baseline_pi',self.cfg,props=self.props)
        b=simulate_24h(self.map,'tariff_heuristic',self.cfg,props=self.props)
        for x in (a,b):
            self.assertEqual(x['status'],'complete',x['failures'])
            self.assertAlmostEqual(x['service_qualified_fraction'],1.)
            self.assertLess(x['spec_unserved_kwh'],1e-6)
            self.assertLess(abs(x['residual_energy_j']),1e-2)
            self.assertLessEqual(x['max_command_slew'],.05+1e-10)
            self.assertFalse(x['equipment_verified'])
            self.assertAlmostEqual(x['condenser_heat_kwh'],x['process_heat_kwh']+
                x['loss_heat_kwh']+x['final_storage_delta_kwh']+
                5e6*(x['final_header_k']-x['initial_header_k'])/3.6e6,delta=1e-4)
        self.assertGreater(b['max_buffer_k'],a['max_buffer_k']+.1)
        self.assertGreater(b['electricity_kwh'],0)

    def test_aborted_integrator_step_cannot_create_service_fraction_over_one(self):
        # Force failure during the second step with an otherwise feasible
        # analytic property double. Only the FIRST completed interval may
        # count as qualified; all remaining 24-hour intervals are unserved.
        stage=flexmod._stage
        calls=[0]
        def fail_on_second_step(*args, **kwargs):
            calls[0]+=1
            if calls[0]==5:
                raise PointRejected('deliberately_aborted_RK4_step')
            return stage(*args, **kwargs)
        with patch.object(flexmod, '_stage', side_effect=fail_on_second_step):
            result=simulate_24h(self.map,'baseline_pi',self.cfg,props=self.props)
        self.assertEqual(result['status'],'failed_physical_or_property_constraint')
        self.assertEqual(result['completed_steps'],1)
        self.assertEqual(result['steps'],1440)
        self.assertAlmostEqual(result['completed_fraction'],1/1440)
        self.assertAlmostEqual(result['service_qualified_fraction'],1/1440)
        self.assertAlmostEqual(result['service_qualified_fraction_completed'],1.0)
        self.assertLessEqual(result['service_qualified_fraction'],1.)
        self.assertFalse(result['equipment_verified'])

    def test_valid_rk4_substages_cannot_commit_invalid_weighted_endpoint(self):
        # Four individually valid stage *inputs*: k1..k3 zero, and k4
        # evaluated at original feasible state. The RK4 accepted endpoint
        # alone exceeds the tabulated property-map header temperatures.
        calls=[0]
        def forced_stage(*args,**kwargs):
            calls[0]+=1
            arr=np.zeros(8,float)
            if calls[0]==4:
                arr[0]=2.0  # dt=60 s, weighted endpoint header +20 K
            return arr
        with patch.object(flexmod,"_stage",side_effect=forced_stage):
            result=simulate_24h(self.map,"baseline_pi",self.cfg,props=self.props)
        self.assertEqual(calls[0],4)
        self.assertEqual(result["status"],"failed_physical_or_property_constraint")
        self.assertEqual(result["completed_steps"],0)
        self.assertTrue(result["failures"])
        self.assertAlmostEqual(result["electricity_kwh"],0.)
        self.assertAlmostEqual(result["cost_eur"],0.)
        self.assertAlmostEqual(result["condenser_heat_kwh"],0.)
        self.assertAlmostEqual(result["process_heat_kwh"],0.)
        self.assertAlmostEqual(result["service_qualified_fraction"],0.)
        self.assertAlmostEqual(result["residual_energy_j"],0.)
        self.assertFalse(result["equipment_verified"])

    def test_no_credit_when_service_fails_even_if_cash_is_lower(self):
        # Pure outcome gate: deliberately violated during 45-min event for small mass.
        cfg=replace(self.cfg,mass_kg=2500)
        tar=replace(SyntheticTariff(),high_end_h=6.75)
        r=compare_flexibility(self.map,cfg,tar,self.props)
        if r['flexibility']['service_qualified_fraction']<1:
            self.assertIsNone(r['eligible_cost_saving_eur'])
            self.assertIn('process_service_failed',r['reasons'])
        else:
            self.assertEqual(r['status'],'conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED')
        self.assertFalse(r['equipment_verified'])
        self.assertFalse(r['policy_is_SOC'])

    def test_flat_tariff_cannot_be_claimed_as_arbitrage(self):
        t=replace(SyntheticTariff(),high_eur_kwh=.16,low_eur_kwh=.16)
        r=compare_flexibility(self.map,self.cfg,t,self.props)
        self.assertIsNone(r['eligible_cost_saving_eur'])
        self.assertIn('no_strict_high_low_price_spread',r['reasons'])

    def test_declared_hypothetical_limits_not_masquerading_as_OEM(self):
        lim=HypotheticalEquipmentLimits(p_cond_max_pa=1e5)
        x=compare_flexibility(self.map,self.cfg,props=self.props,limits=lim)
        self.assertIsNone(x['eligible_cost_saving_eur'])
        self.assertIn('simulation_or_envelope_failed',x['reasons'])
        self.assertIsNone(x['raw_cost_difference_eur'])
        self.assertIsNone(x['raw_electricity_difference_kwh'])

    def test_final_header_energy_mismatch_cannot_be_called_a_saving(self):
        # Audit A02: equal buffer enthalpy does not mean equal total resources.
        base=dict(status='complete',service_qualified_fraction=1.,
                  spec_unserved_kwh=0.,cost_eur=100.,electricity_kwh=1000.,
                  final_storage_delta_kwh=0.,final_header_energy_delta_kwh=0.,
                  final_total_thermal_energy_delta_kwh=0.,final_modulation=.75,
                  final_applied_command=.75)
        flex=base.copy()
        flex.update(cost_eur=90.,final_header_energy_delta_kwh=5e6*7/3.6e6,
                    final_total_thermal_energy_delta_kwh=5e6*7/3.6e6)
        with patch.object(flexmod,'simulate_24h',side_effect=[base,flex]):
            comparison=compare_flexibility(self.map,self.cfg,props=self.props)
        self.assertIsNone(comparison['eligible_cost_saving_eur'])
        self.assertIn('terminal_header_inventory_mismatch',comparison['reasons'])
        self.assertIn('terminal_total_thermal_energy_mismatch',comparison['reasons'])
        self.assertAlmostEqual(comparison['raw_cost_difference_eur'],10.)

    def test_terminal_compressor_modulation_mismatch_prevents_saving(self):
        base=dict(status='complete',service_qualified_fraction=1.,
                  spec_unserved_kwh=0.,cost_eur=100.,electricity_kwh=1000.,
                  final_storage_delta_kwh=0.,final_header_energy_delta_kwh=0.,
                  final_total_thermal_energy_delta_kwh=0.,final_modulation=.75,
                  final_applied_command=.75)
        flex=dict(base,cost_eur=90.,final_modulation=.91)
        with patch.object(flexmod,'simulate_24h',side_effect=[base,flex]):
            comparison=compare_flexibility(self.map,self.cfg,props=self.props)
        self.assertIsNone(comparison['eligible_cost_saving_eur'])
        self.assertIn('terminal_final_modulation_mismatch',comparison['reasons'])

    def test_equal_price_windows_still_have_distinct_energy_buckets(self):
        tariff=replace(SyntheticTariff(),low_eur_kwh=.16,
                       high_eur_kwh=.16,regular_eur_kwh=.16)
        run=simulate_24h(self.map,'baseline_pi',self.cfg,tariff,self.props)
        self.assertEqual(run['status'],'complete')
        e=run['tariff_bucket_electricity_kwh']
        self.assertTrue(all(e[x]>0 for x in ('low','high','regular')))
        self.assertAlmostEqual(sum(e.values()),run['electricity_kwh'],places=7)

    def test_cost_eligible_case_distinguishes_euros_and_kwh(self):
        r=compare_flexibility(self.map,self.cfg,props=self.props)
        if r['status'].startswith('conditional_model_comparison_eligible'):
            self.assertAlmostEqual(r['eligible_cost_saving_eur'],
                                   r['baseline']['cost_eur']-r['flexibility']['cost_eur'])
            self.assertLess(abs(r['baseline']['final_storage_delta_kwh']-
                                r['flexibility']['final_storage_delta_kwh']),.5)
        self.assertFalse(r['equipment_verified'])

    def test_temperature_and_energy_mass_scaling_in_baseline(self):
        # Different masses should all hold the exact nominal equilibrium.
        for mass in (2500,10000):
            r=simulate_24h(self.map,'baseline_pi',replace(self.cfg,mass_kg=mass),props=self.props)
            self.assertEqual(r['status'],'complete')
            self.assertLess(abs(r['final_storage_delta_kwh']),1e-4)
            self.assertGreater(r['electricity_kwh'],0)

try:
 import CoolProp
 HAVE_REAL=True
except ImportError:HAVE_REAL=False

@unittest.skipUnless(HAVE_REAL,'Actual IF97/CoolProp WP8 required; CI installs realfluid')
class TestRealFluidStorage(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    cls.model=build_cycle_map('R1233zd(E)',[328.15,333.15,338.15],
                              [403.15,406.2,413.15],[.5,.75,1])
 def test_real_full_band_finite_and_phase_checked(self):
    r=scan_reachable_band(self.model,nodes=11)
    self.assertFalse(r['equipment_verified'])
    self.assertGreaterEqual(r['enthalpy_kwh'],0)
    self.assertLess(r['enthalpy_kwh'],100)
 def test_real_24h_benchmark_energy_and_failure_accounting(self):
    # Runs on GitHub with real CoolProp; no synthetic fallback permitted.
    r=compare_flexibility(self.model,FlexSettings(dt_s=60.))
    self.assertIn(r['status'],('conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED',
                               'cost_saving_not_creditable'))
    self.assertFalse(r['equipment_verified'])
    if r['status']=='conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED':
       self.assertAlmostEqual(r['flexibility']['service_qualified_fraction'],1.)
       self.assertLess(abs(r['baseline']['final_storage_delta_kwh']-
                           r['flexibility']['final_storage_delta_kwh']),.5)

if __name__=='__main__':unittest.main()
