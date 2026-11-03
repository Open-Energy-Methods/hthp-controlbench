"""WP7 acceptance: conservation, rejection, provenance and property-EOS integration."""
import unittest
from dataclasses import replace
from math import exp, log

from ht_hp_controlbench.realfluid import (
    CycleAssumptions, PointRejected, PropertyBackendMissing, cycle_point,
    coolprop_backend, map_exact, build_cycle_map, map_holdout_error,
    water_loop_state, screen_point, conditional_water_inventory,
)

class FakeProperties:
    """Analytic test double. NOT a refrigerant; used only for structural unit tests."""
    def __init__(self):
        self.h1 = 290000.0
    def __call__(self, key, *args):
        if len(args)==1:
            fluid=args[0]
            if key == 'Tcrit': return 470.
            if key == 'Tmin': return 200.
            if key == 'Tmax': return 600.
            raise AssertionError(key)
        v1,x1,v2,x2,fluid=args
        if fluid in ('IF97::Water','Water'):
            if key=='P' and v1=='T' and v2=='Q':
                return (1.003 if fluid=='Water' else 1)*300000*exp((x1-406.2)/45.)
            if key=='H' and v1=='T' and v2=='P':return 4200*(x1-273.15)
            raise AssertionError((key,args))
        if key=='P' and v1=='T' and v2=='Q':return 50000*exp((x1-300.)/60.)
        if key=='H' and v1=='T' and v2=='P':
            tsat=300+60*log(x2/50000.)
            h=(200000+1500*(x1-273.15)) if x1>=tsat else 1000*(x1-273.15)
            if x1>=tsat:self.h1=h
            return h
        if key=='S' and v1=='T' and v2=='P':return 1200.
        if key=='D' and v1=='T' and v2=='P':return 16.*(300/x1)
        if key=='H' and v1=='P' and v2=='S':return self.h1+130000
        if key=='H' and v1=='P' and v2=='Q':
            tsat=300+60*log(x1/50000.)
            return 200000+1500*(tsat-273.15)
        if key=='T' and v1=='P' and v2=='H':return (x2-200000.)/1500+273.15
        if key=='Q' and v1=='P' and v2=='H':return .4
        raise AssertionError((key,args))

class TestWP7Structure(unittest.TestCase):
    def setUp(self):self.p=FakeProperties();self.a=CycleAssumptions()

    def test_missing_coolprop_never_uses_fake_properties(self):
        try:coolprop_backend()
        except PropertyBackendMissing:pass
        else:self.assertTrue(callable(coolprop_backend()))

    def test_nominal_analytic_enthalpy_closure(self):
        x=cycle_point('Fake',333.15,406.2,self.a,self.p)
        self.assertGreater(x.cop_heating,1.)
        self.assertLess(x.cop_heating,x.cop_carnot_refrigerant)
        self.assertAlmostEqual(x.condenser_specific_j_kg,
                               x.compressor_specific_j_kg+x.evaporator_specific_j_kg,places=8)
        self.assertAlmostEqual(x.pressure_ratio,x.p_cond_pa/x.p_evap_pa)
        self.assertGreater(x.t_discharge_k,x.t_cond_sat_k)
        self.assertGreater(x.discharge_vapor_enthalpy_margin_j_kg,0)
        self.assertGreater(x.volumetric_heat_capacity_j_m3,0.)
        self.assertAlmostEqual(x.t_evap_sat_k,328.15)
        self.assertAlmostEqual(x.t_cond_sat_k,411.2)

    def test_wet_compressor_discharge_rejected_even_if_temperature_flash_misleads(self):
        class FakeWet(FakeProperties):
            def __call__(self,key,*args):
                if len(args)==5 and key=='H' and args[0]=='P' and args[2]=='Q':
                    return 1e6  # Above actual compressor discharge enthalpy
                return super().__call__(key,*args)
        with self.assertRaisesRegex(PointRejected,'discharge_wet'):
            cycle_point('Fake',333.15,406.2,self.a,FakeWet())

    def test_critical_gate_rejects_and_never_extrapolates(self):
        a=replace(self.a,critical_margin_k=70.)
        with self.assertRaisesRegex(PointRejected,'subcritical'):
            cycle_point('Fake',333.15,406.2,a,self.p)

    def test_transcritical_CO2_cannot_be_silently_drop_in(self):
        with self.assertRaisesRegex(PointRejected,'transcritical'):
            cycle_point('CarbonDioxide',333.15,406.2,self.a,self.p)

    def test_bad_compressor_assumptions_rejected(self):
        for kwargs in ({'eta_isentropic':0.}, {'eta_isentropic':1.2},
                       {'superheat_k':0.}, {'cond_approach_k':-3.},
                       {'reference_modulation':0.}, {'service_header_pressure_pa':0.}):
            with self.assertRaises(ValueError):replace(self.a,**kwargs)

    def test_water_properties_are_not_ambient_pressure_shortcut(self):
        w=water_loop_state(406.2,self.a,self.p)
        self.assertAlmostEqual(w['saturation_pressure_if97_pa'],300000.)
        self.assertAlmostEqual(w['enthalpy_difference_from_120C_j_kg'],4200*(406.2-393.15))
        self.assertGreater(w['relative_pressure_margin'],.15)
        with self.assertRaisesRegex(PointRejected,'pressure_fails'):
            water_loop_state(406.2,replace(self.a,service_header_pressure_pa=340000.),self.p)

    def test_storage_enthalpy_is_conditional_and_phase_checked(self):
        r=conditional_water_inventory(5000.,401.53,408.15,self.a,self.p)
        expected=5000*4200*(408.15-401.53)/3.6e6
        self.assertAlmostEqual(r['conditional_energy_kwh'],expected,places=9)
        self.assertIn('conditional',r['capacity_status'])
        with self.assertRaises(ValueError):conditional_water_inventory(-1.,401.53,408.15,self.a,self.p)
        with self.assertRaises(PointRejected):
            conditional_water_inventory(5000.,401.53,420.,replace(self.a,service_header_pressure_pa=400000.),self.p)

    def test_screen_rejected_point_instead_of_fake_cop(self):
        row=screen_point('CarbonDioxide',333.15,406.2,self.a,self.p)
        self.assertEqual(row['status'],'rejected')
        self.assertNotIn('cop_heating',row)
        other=screen_point('Fake',333.15,406.2,self.a,self.p)
        self.assertEqual(other['status'],'property_cycle_pass')

    def test_design_map_massflow_and_energy_at_reference(self):
        m=build_cycle_map('Fake',[328.15,333.15,338.15],[403.15,406.20,413.15],
                          [.5,.75,1.0],self.a,self.p)
        q,p,source=m.evaluate(.75,333.15,406.2)
        self.assertAlmostEqual(q,310000.,places=7)
        self.assertAlmostEqual(p,310000./m.reference_cycle.cop_heating,places=6)
        self.assertAlmostEqual(q,p+source,places=8)
        self.assertGreater(m.equivalent_full_speed_suction_volume_m3_s,0.)

    def test_map_extrapolation_hard_rejected(self):
        m=build_cycle_map('Fake',[328.15,333.15,338.15],[403.15,406.20,413.15],
                          [.5,.75,1.],self.a,self.p)
        for query in ((.1,333.15,406.2),(.75,323.,406.2),(.75,333.15,419.)):
            with self.assertRaisesRegex(PointRejected,'extrapolation'):
                m.evaluate(*query)

    def test_holdout_not_training_grid_and_finite(self):
        m=build_cycle_map('Fake',[328.15,333.15,338.15],[403.15,406.20,413.15],
                          [.5,.75,1.],self.a,self.p)
        rows=map_holdout_error(m,[(.625,330.65,404.675),(.875,335.65,409.675)],self.p)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(abs(x['relative_q_error'])<.06 for x in rows))
        self.assertTrue(all(abs(x['relative_p_error'])<.06 for x in rows))

    def test_capacity_map_does_not_claim_manufacturer_compressor(self):
        m=build_cycle_map('Fake',[328.15,333.15,338.15],[403.15,406.20,413.15],
                          [.5,.75,1.],self.a,self.p)
        a=cycle_point('Fake',330.65,404.675,self.a,self.p)
        v=map_exact(a,.75,m)
        self.assertAlmostEqual(v[0],v[1]+v[2])
        self.assertIn('uncalibrated',m.reference_cycle.property_origin)

try:
    import CoolProp
    _HAVE_CP=True
except ImportError:
    _HAVE_CP=False

@unittest.skipUnless(_HAVE_CP,'CoolProp unavailable offline; GitHub CI installs realfluid extra')
class TestWP7CoolProp(unittest.TestCase):
    def test_nominal_refrigerant_property_screen(self):
        # Property eligibility, NOT equipment acceptance.
        rows=[screen_point(f,333.15,406.20) for f in
              ('R1233zd(E)','R1336mzz(Z)','R134a','Ammonia','CarbonDioxide')]
        self.assertEqual(rows[-1]['status'],'rejected')
        self.assertEqual(rows[2]['status'],'rejected')
        self.assertEqual(rows[3]['status'],'rejected')
        self.assertGreaterEqual(sum(x['status']=='property_cycle_pass' for x in rows[:2]),1)

    def test_water_6bar_IF97_vs_HEOS_and_saturation_reference(self):
        w=water_loop_state(406.20)
        self.assertAlmostEqual(w['saturation_pressure_if97_pa']/1e5,2.98,delta=.10)
        self.assertLess(abs(w['sat_backend_fractional_difference']),.005)
        self.assertGreater(w['relative_pressure_margin'],.15)

    def test_real_cycle_energy_and_carnot(self):
        rows=[screen_point(x,333.15,406.20) for x in ('R1233zd(E)','R1336mzz(Z)')]
        valid=[x for x in rows if x['status']=='property_cycle_pass']
        self.assertTrue(valid,rows)
        for r in valid:
            self.assertAlmostEqual(r['condenser_specific_j_kg'],
                r['compressor_specific_j_kg']+r['evaporator_specific_j_kg'],delta=1e-6)
            self.assertTrue(1<r['cop_heating']<r['cop_carnot_refrigerant'])
            self.assertGreater(r['t_discharge_k'],r['t_cond_sat_k'])

if __name__=='__main__':unittest.main()
