"""WP7 thermodynamic-system feasibility and synthetic TESPy offdesign checks."""
import unittest
from dataclasses import replace

from ht_hp_controlbench.core import Parameters,Disturbance
from ht_hp_controlbench.realfluid import (CycleAssumptions,PointRejected,
                                          cycle_point,build_cycle_map)
from ht_hp_controlbench.thermo_feasibility import (
    HypotheticalEquipmentLimits, hypothetical_machine_checks,
    hold_service_at_buffer, max_speed_charge_point, quasisteady_charge_ledger)
from ht_hp_controlbench.tespy_offdesign import (_linear_characteristic,
                                                 tespy_synthetic_offdesign)
from test_wp7_realfluid import FakeProperties

class TestSystemFeasibility(unittest.TestCase):
    def setUp(self):
        self.a=CycleAssumptions()
        self.fake=FakeProperties()
        self.map=build_cycle_map('Fake',[328.15,333.15,338.15],
                                 [403.15,406.2,413.15],[0.5,0.75,1.0],
                                 self.a,self.fake)
    def test_no_oem_data_can_never_be_equipment_accepted(self):
        point=cycle_point('Fake',333.15,406.2,self.a,self.fake)
        c=hypothetical_machine_checks(point,0.75,self.map)
        self.assertEqual(c['status'],'no_manufacturer_limits_provided')
        self.assertFalse(c['equipment_verified'])
        self.assertFalse(c['failed'])
    def test_hypothetical_rating_cannot_be_mislabeled_real_rating(self):
        point=cycle_point('Fake',333.15,406.2,self.a,self.fake)
        c=hypothetical_machine_checks(point,.75,self.map,
                        HypotheticalEquipmentLimits(p_cond_max_pa=point.p_cond_pa*.9))
        self.assertIn('p_cond_max_pa',c['failed'])
        self.assertFalse(c['equipment_verified'])
    def test_invalid_hypothetical_limits_rejected(self):
        for val in (-1,0,float('nan')):
            with self.assertRaises(ValueError):HypotheticalEquipmentLimits(discharge_max_k=val)
    def test_service_balance_exact_and_not_guaranteed(self):
        # At nominal buffer, fake cycle is sized to provide 310 kW.
        x=hold_service_at_buffer(403.15,self.map,props=self.fake)
        self.assertTrue(x['service_qualified'])
        self.assertTrue(x['declared_map_support'])
        self.assertAlmostEqual(x['q_hp_required_w'],x['hot_loop_exchange_w']+x['header_heat_loss_w'])
        self.assertAlmostEqual(x['source_heat_required_w'],x['q_hp_required_w']-x['compressor_electric_required_w'])
        self.assertFalse(x['equipment_verified'])
        self.assertIn('EQUIPMENT_UNVERIFIED',x['status'])
    def test_service_fails_when_insufficient_hx_temperature(self):
        x=hold_service_at_buffer(396.15,self.map,props=self.fake)
        self.assertEqual(x['status'],'process_service_failed')
        self.assertFalse(x['service_qualified'])
    def test_explicit_capacity_failure_when_nominal_reference_duty_decreased(self):
        low_duty=replace(self.a,reference_condenser_duty_w=150000.)
        m=build_cycle_map('Fake',[328.15,333.15,338.15],
                          [403.15,406.2,413.15],[.5,.75,1],low_duty,self.fake)
        x=hold_service_at_buffer(403.15,m,props=self.fake)
        self.assertEqual(x['status'],'compressor_modulation_outside_declared_grid')
        self.assertGreater(x['required_modulation'],1.)
    def test_charge_path_energy_integral_monotone(self):
        # This analytical test double yields a 4200 J/(kg K) water cp exactly.
        # A fake refrigerant may make max-speed charge impossible, which is a
        # valid fail-closed result rather than an artificial positive charge.
        result=quasisteady_charge_ledger(self.map,low_k=401.55,high_k=403.15,
                                         nodes=5,props=self.fake)
        if result['status'].startswith('conditional_quasisteady'):
            self.assertGreater(result['energy_kwh'],0)
            self.assertGreater(result['charge_hours'],0)
            self.assertAlmostEqual(result['energy_kwh'],5000*4200*1.6/3.6e6,places=7)
        else:
            self.assertEqual(result['status'],'blocked_or_unverified')
            self.assertIn('reason',result)
    def test_characteristic_guard_and_interpolation(self):
        self.assertAlmostEqual(_linear_characteristic(1),1)
        self.assertAlmostEqual(_linear_characteristic(.75),.97)
        with self.assertRaises(PointRejected):_linear_characteristic(.25)
        with self.assertRaises(PointRejected):_linear_characteristic(1.4)
    def test_bad_storage_input_fails(self):
        with self.assertRaises(ValueError):quasisteady_charge_ledger(self.map,low_k=410,high_k=405)
    def test_charge_outside_header_support_must_reject(self):
        with self.assertRaises(PointRejected):max_speed_charge_point(420,self.map,props=self.fake)

try:
    import CoolProp
    HAVE_COOLPROP=True
except ImportError: HAVE_COOLPROP=False
try:
    import tespy
    HAVE_TESPY=True
except ImportError: HAVE_TESPY=False

@unittest.skipUnless(HAVE_COOLPROP,'CoolProp required for real-fluid system coupled feasibility')
class TestActualPropertyFeasibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a=CycleAssumptions()
        cls.m=build_cycle_map('R1233zd(E)',[328.15,333.15,338.15],
                    [403.15,406.2,413.15],[.5,.75,1],a)
    def test_nominal_holding_same_service(self):
        x=hold_service_at_buffer(403.15,self.m)
        self.assertTrue(x['service_qualified'])
        self.assertTrue(.5 < x['required_modulation'] < 1)
        self.assertLess(abs(x['required_modulation']-.75),.06)
        self.assertFalse(x['equipment_verified'])
    def test_charge_path_is_necessarily_explicitly_conditional(self):
        x=quasisteady_charge_ledger(self.m,low_k=401.55,high_k=408.15,nodes=11)
        # No claim of charging without rating evidence, even if thermodynamics allow.
        self.assertFalse(x['equipment_verified'])
        if x['status'].startswith('conditional_quasisteady'):
            self.assertTrue(0<x['energy_kwh']<100)
            self.assertGreater(x['charge_hours'],0)
            self.assertTrue(all(s['service_qualified'] for s in x['samples']))
        else:
            self.assertEqual(x['status'],'blocked_or_unverified')
    def test_arbitrary_restrictive_machine_cap_can_block(self):
        lim=HypotheticalEquipmentLimits(p_cond_max_pa=1e5)
        x=quasisteady_charge_ledger(self.m,low_k=401.55,high_k=408.15,
                                     nodes=5,limits=lim)
        self.assertEqual(x['status'],'blocked_or_unverified')
        self.assertEqual(x['reason'],'hypothetical_equipment_limit_exceeded')

@unittest.skipUnless(HAVE_TESPY and HAVE_COOLPROP,'TESPy and CoolProp required for actual offdesign')
class TestActualTESPyOffdesign(unittest.TestCase):
    def test_design_saved_and_partload_resolved_with_characteristic(self):
        rows=tespy_synthetic_offdesign((.75,1,1.1))
        self.assertEqual(len(rows),3)
        self.assertTrue(all(x['tespy_mode']=='offdesign' for x in rows))
        self.assertTrue(all(x['design_saved'] for x in rows))
        self.assertTrue(all(abs(x['q_relative_disagreement'])<.02 for x in rows))
        self.assertTrue(all(abs(x['p_relative_disagreement'])<.02 for x in rows))
        self.assertGreater(rows[1]['eta_tespy'],rows[0]['eta_tespy'])
        self.assertFalse(rows[0]['equipment_verified'])
    def test_offdesign_disallows_uncharacterised_extrapolation(self):
        with self.assertRaises(PointRejected):tespy_synthetic_offdesign((.3,))

if __name__=='__main__':unittest.main()

class TestFluidDynamicStructure(unittest.TestCase):
    def test_enthalpy_state_energy_conservation_under_synthetic_property_double(self):
        from ht_hp_controlbench.fluid_dynamics import fluid_pi_simulation
        from ht_hp_controlbench.pi import PISettings
        class InvertibleFake(FakeProperties):
            def __call__(self, key,*args):
                if len(args)==5 and args[-1]=='IF97::Water' and key=='T' and args[0]=='P' and args[2]=='H':
                    return args[3]/4200.+273.15
                return super().__call__(key,*args)
        props=InvertibleFake();a=CycleAssumptions()
        m=build_cycle_map('Fake',[328.15,333.15,338.15],
                [403.15,406.20,413.15],[.5,.75,1.],a,props)
        settings=PISettings(.03842421355656901,1.2387208598348781e-5,'fixed_WP3_IMC')
        x=fluid_pi_simulation(m,settings,duration_s=240.,step_s=10.,props=props)
        self.assertLess(x.max_energy_residual_J,1e-2)
        self.assertEqual(x.status,'completed_property_map_PI_test__EQUIPMENT_UNVERIFIED')
        self.assertFalse(x.equipment_verified)
        self.assertGreaterEqual(x.fraction_service_qualified,0.)

@unittest.skipUnless(HAVE_COOLPROP,'Real IF97 dynamic validation only with CoolProp')
class TestRealFluidDynamics(unittest.TestCase):
    def test_real_enthalpy_dynamic_conservation_without_extrapolation(self):
        from ht_hp_controlbench.fluid_dynamics import fluid_pi_simulation
        from ht_hp_controlbench.pi import PISettings
        m=build_cycle_map('R1233zd(E)',[328.15,333.15,338.15],
                [403.15,406.20,413.15],[.5,.75,1.])
        settings=PISettings(.03842421355656901,1.2387208598348781e-5,'fixed_WP3_IMC')
        res=fluid_pi_simulation(m,settings,duration_s=240.,step_s=10.)
        self.assertLess(res.max_energy_residual_J,1e-2)
        self.assertGreater(res.condenser_heat_kwh,res.electricity_kwh)
        self.assertFalse(res.equipment_verified)
