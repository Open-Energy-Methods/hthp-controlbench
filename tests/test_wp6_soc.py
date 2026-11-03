"""WP6 scope guards: prevent relabelling constraint control/heuristics as SOC."""
from __future__ import annotations
import unittest
from dataclasses import replace
from itertools import product
import numpy as np
from ht_hp_controlbench.core import Parameters,State,Disturbance,output
from ht_hp_controlbench.soc import (SOCParameters,effective_plant,service_temperature_min,
    evaluate_point,offline_optimum,feasible_interval,evaluate_at_buffer_temperature,
    economic_loss_w,train_piecewise_soc,train_constant_cvs,derive_local_stationarity_cv,
    evaluate_piecewise_cv,evaluate_cv,piecewise_policy_r,baseline_dof_audit)
from ht_hp_controlbench.soc_dynamic import FlowState,rk4_flow_step,run_dynamic_soc
from ht_hp_controlbench.pi import PISettings

P=Parameters(hx_mode='duty_limiter');C=SOCParameters()
TRAIN=[Disturbance(t_return=273.15+ret,t_source=273.15+src) for ret,src in product((85.,90.,95.,100.),(45.,52.5,60.,67.5,75.))]
HOLD=[Disturbance(t_return=273.15+ret,t_source=273.15+src) for ret,src in product((87.5,92.5,97.5),(47.5,57.5,72.5))]

class TestWP6SOC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=train_piecewise_soc(P,C,TRAIN)
        cls.hessian=derive_local_stationarity_cv(P,C,Disturbance(t_return=368.15))
        cls.constant=train_constant_cvs(P,C,TRAIN)

    def test_original_dof_is_zero_and_bypass_not_an_actuator(self):
        a=baseline_dof_audit()
        self.assertEqual(a['unconstrained_steady_economic_dof'],0)
        self.assertEqual(a['declared_manipulated_variables'],['compressor_command_u'])
        self.assertIn('local_process_bypass_fraction_f',a['non_manipulated_local_variables'])

    def test_separate_hypothetical_pump_authority(self):
        self.assertEqual(P.c_hot,100000.)
        ep=effective_plant(P,C,.8)
        self.assertAlmostEqual(ep.c_hot,80000.)
        self.assertNotEqual(ep.ua_proc,P.ua_proc)
        self.assertEqual(P.c_hot,100000.)
        self.assertEqual(ep.hx_mode,'duty_limiter')
        self.assertRaises(ValueError,effective_plant,P,C,0.)

    def test_invalid_assumptions_rejected(self):
        for kwargs in ({'pump_nominal_w':0.},{'r_min':1.5},{'r_max':.25},
                       {'hot_film_resistance_fraction':0.},{'hot_film_flow_exponent':0.},
                       {'buffer_margin_k':-1.},{'tau_r':0.}):
            with self.assertRaises(ValueError):replace(C,**kwargs)

    def test_service_quality_is_required_not_assumed(self):
        o=offline_optimum(P,C,Disturbance())
        self.assertIsNotNone(o)
        self.assertAlmostEqual(o.q_service_w,300000.,places=2)
        self.assertAlmostEqual(o.tb_k,service_temperature_min(P,C,Disturbance(),o.r),places=8)
        self.assertRaises(ValueError,evaluate_at_buffer_temperature,P,C,Disturbance(),o.r,o.tb_k-.05)

    def test_hx_power_accounting_matches_full_energy_balance(self):
        d=Disturbance(t_return=368.15,t_source=325.15)
        o=offline_optimum(P,C,d)
        r=output(State(o.th_k,o.tb_k,o.n),effective_plant(P,C,o.r),d)
        self.assertAlmostEqual(r.q_hp-r.q_hb-r.loss_h,0.,delta=1e-5)
        self.assertAlmostEqual(r.q_hb-r.hx.q_transferred-r.loss_b,0.,delta=1e-5)
        self.assertAlmostEqual(o.p_total_w,r.p_el+C.pump_nominal_w*o.r**3,delta=1e-7)
        self.assertTrue(r.hx.qualified)

    def test_steady_service_boundary_economic_choice_2d(self):
        for d in HOLD[::2]:
            o=offline_optimum(P,C,d)
            for margin in (.1,.25,.5,1.):
                try: pt=evaluate_at_buffer_temperature(P,C,d,o.r,o.tb_k+margin)
                except ValueError:continue
                self.assertGreater(pt.p_total_w,o.p_total_w)

    def test_offline_optimum_better_than_explicit_dense_grid(self):
        d=Disturbance(t_source=328.15,t_return=368.15)
        opt=offline_optimum(P,C,d)
        a,b=feasible_interval(P,C,d)
        for r in np.linspace(a+1e-5,b-1e-5,151):
            if r<=C.r_min or r>=C.r_max:continue
            pt=evaluate_point(P,C,d,float(r))
            self.assertGreaterEqual(pt.p_total_w,opt.p_total_w-1e-3)

    def test_service_and_pump_constraint_active_sets_differ(self):
        hi=offline_optimum(P,C,Disturbance(t_return=358.15)) # 85C, high duty
        lo=offline_optimum(P,C,Disturbance(t_return=373.15)) # 100C, lower duty
        self.assertIn('pump_max',hi.active)
        self.assertNotIn('pump_max',lo.active)
        self.assertIn('service',hi.active);self.assertIn('service',lo.active)

    def test_no_fabricated_SOC_loss_for_infeasible(self):
        o=offline_optimum(P,C,Disturbance())
        self.assertIsNone(economic_loss_w(None,o))
        self.assertRaises(ValueError,economic_loss_w,replace(o,p_total_w=o.p_total_w-1.),o)

    def test_training_heldout_not_overlapping(self):
        self.assertTrue(set((x.t_return,x.t_source) for x in TRAIN).isdisjoint(
                        set((x.t_return,x.t_source) for x in HOLD)))
        self.assertEqual(self.model['training_count'],20)
        self.assertEqual(self.model['interior_training_count'],12)
        self.assertEqual(self.model['pump_max_training_count'],8)

    def test_empirical_and_stationarity_cvs_held_constant(self):
        for model in (self.model,self.hessian):
            for d in HOLD:
                r,regime=piecewise_policy_r(model,C,d)
                self.assertTrue(C.r_min<=r<=C.r_max)
                if regime=='interior_constant_CV':
                    measured_cv=r+model['beta_per_kelvin']*(d.t_return-363.15)+model['beta_source_per_kelvin']*(d.t_source-333.15)
                    self.assertAlmostEqual(measured_cv,model['cv_setpoint'],places=12)
                else:self.assertAlmostEqual(r,C.r_max)
            pts=evaluate_piecewise_cv(P,C,HOLD,model)
            self.assertTrue(all(x['policy_feasible'] for x in pts))
            self.assertTrue(all(x['loss_w']>=0 for x in pts))
            self.assertLess(max(x['loss_pct'] for x in pts),.001)

    def test_stationarity_gradient_matches_independent_optimal_shift(self):
        d=Disturbance(t_return=368.15,t_source=333.15)
        o=offline_optimum(P,C,d)
        self.assertGreater(self.hessian['H_rr_W_per_r2'],0)
        rshift=offline_optimum(P,C,replace(d,t_return=d.t_return+.25)).r
        derivative=(rshift-o.r)/.25
        self.assertAlmostEqual(derivative,-self.hessian['beta_per_kelvin'],delta=.0003)

    def test_piecewise_constraint_switch_is_explicit_and_constant_infeasibility_preserved(self):
        dummy={'valid':True,'cv_setpoint':2.,'beta_per_kelvin':0.,'beta_source_per_kelvin':0.}
        v=piecewise_policy_r(dummy,C,Disturbance())
        self.assertEqual(v,(C.r_max,'pump_max_constraint'))
        self.assertIsNone(__import__('ht_hp_controlbench.soc',fromlist=['fixed_r_point']).fixed_r_point(P,C,Disturbance(),2.))

    def test_positive_tariff_does_not_change_static_optimum(self):
        o=offline_optimum(P,C,Disturbance())
        for tariff in (.08,.2,.5):
            self.assertAlmostEqual(o.r,min((evaluate_point(P,C,Disturbance(),r).p_total_w*tariff,r)
                for r in np.linspace(.48,C.r_max,200))[1],delta=.006)

    def test_optimizer_reports_infeasible_envelope(self):
        c=replace(C,tb_max_k=396.15,th_max_k=415.15)
        self.assertIsNone(offline_optimum(P,c,Disturbance(t_return=353.15)))

    def test_pump_affinity_at_halved_flow(self):
        self.assertAlmostEqual(C.pump_nominal_w*(.5**3),312.5)

    def test_dynamic_rk4_conserves_thermal_energy(self):
        d=Disturbance();o=offline_optimum(P,C,d)
        x=FlowState(o.th_k,o.tb_k,o.n,o.r)
        y,e=rk4_flow_step(x,o.n,o.r,P,C,d,10.)
        residual=P.c_h*(y.th-x.th)+P.c_b*(y.tb-x.tb)-e[2]+e[3]+e[4]+e[5]
        self.assertLess(abs(residual),1e-3)
        self.assertAlmostEqual(e[1],10*C.pump_nominal_w*x.r**3,delta=.01)

    def test_dynamic_flow_lag_and_command_not_instantaneous(self):
        d=Disturbance();o=offline_optimum(P,C,d)
        x=FlowState(o.th_k,o.tb_k,o.n,o.r)
        y,_=rk4_flow_step(x,o.n,.8,P,C,d,10.)
        self.assertGreater(y.r,.8)
        self.assertLess(y.r,x.r)

    def test_dynamic_comparator_same_information_and_deterministic_noise(self):
        d=Disturbance()
        model=self.model
        # Deliberately tiny 240 s pilot for test speed, not an economic conclusion.
        settings=PISettings(kp=.038,ki=.00002,source='synthetic_test')
        seq=[(0.,d)]
        s1,a1=run_dynamic_soc(P,replace(C,buffer_margin_k=2.),model,seq,settings,'regime_soc',
            duration_s=240.,sensor_noise_k=.2,sensor_delay_s=120.,seed=7)
        s2,a2=run_dynamic_soc(P,replace(C,buffer_margin_k=2.),model,seq,settings,'regime_soc',
            duration_s=240.,sensor_noise_k=.2,sensor_delay_s=120.,seed=7)
        self.assertEqual(a1['controls'],a2['controls'])
        self.assertAlmostEqual(s1.electrical_kwh,s2.electrical_kwh)
        self.assertLess(s1.max_energy_residual_j,.001)
        self.assertRaises(ValueError,run_dynamic_soc,P,C,model,seq,settings,'fake_policy',duration_s=240.)

    def test_dynamic_sensor_delay_uses_past_sample(self):
        model=self.model;settings=PISettings(kp=.038,ki=.00002,source='synthetic_test')
        seq=[(0.,Disturbance())]
        _,data=run_dynamic_soc(P,replace(C,buffer_margin_k=2.),model,seq,settings,'regime_soc',
           duration_s=360.,sensor_noise_k=.3,sensor_delay_s=120.,seed=5)
        hs=data['controls']
        self.assertAlmostEqual(hs[0][3],hs[1][3],places=12)
        self.assertNotAlmostEqual(hs[1][3],hs[2][3],places=7)

if __name__=='__main__':unittest.main()
