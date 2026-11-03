"""WP3 controller tests: independent tuning, robust PI execution and fairness."""
import unittest
from dataclasses import replace
import numpy as np
from ht_hp_controlbench.core import Parameters, State, Disturbance, equilibrium
from ht_hp_controlbench.sim import Schedule, simulate
from ht_hp_controlbench.pi import (
    PISettings, PIController, StepIdentification, RelayIdentification,
    identify_step, identify_relay, tune_imc, tune_relay_tyreus_luyben,
    closed_loop, metrics,
)

class PIControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=Parameters(hx_mode='no_bypass')
        cls.fit=identify_step(cls.p)
        cls.relay=identify_relay(cls.p)
        cls.imc=tune_imc(cls.fit)
        cls.relay_pi=tune_relay_tyreus_luyben(cls.relay)

    def test_step_response_fopdt_is_finite_positive_and_converged(self):
        a=self.fit
        self.assertGreater(a.gain_k_per_u,0)
        self.assertGreater(a.tau_s,0)
        self.assertGreaterEqual(a.delay_s,0)
        self.assertGreater(a.t63_s,a.t28_s)
        self.assertLess(a.last_slope_k,.01*a.gain_k_per_u*a.delta_command)
        self.assertAlmostEqual(a.gain_k_per_u,47.894,delta=.1)

    def test_imc_formula_and_units(self):
        a=self.fit; cfg=self.imc
        expected=a.tau_s/(a.gain_k_per_u*(2*a.tau_s+a.delay_s))
        self.assertAlmostEqual(cfg.kp,expected)
        self.assertAlmostEqual(cfg.ki,cfg.kp/(a.tau_s+a.delay_s/2))
        self.assertLess(cfg.kp,.1)

    def test_relay_is_independent_of_step_identifier(self):
        r=self.relay
        self.assertGreaterEqual(r.observed_cycles,6)
        self.assertGreater(r.ultimate_gain_u_per_k,0)
        self.assertGreater(r.temperature_amplitude_k,0.04)
        self.assertAlmostEqual(r.period_s,780,delta=60)
        self.assertAlmostEqual(self.relay_pi.kp,r.ultimate_gain_u_per_k/3.2)
        self.assertAlmostEqual(self.relay_pi.ki,self.relay_pi.kp/(2.2*r.period_s))
        self.assertNotAlmostEqual(self.relay_pi.kp,self.imc.kp,delta=.1)

    def test_relay_amplitude_is_limit_cycle_peak_not_switch_threshold(self):
        # Regression for audit A01: finite compressor lag produces peaks beyond
        # the hysteresis switching threshold. The old implementation reported
        # approximately 0.052 K using only values at switching instants.
        measured = self.relay.temperature_amplitude_k
        self.assertGreater(measured, 0.075)
        self.assertLess(measured, 0.12)
        self.assertGreater(measured, 1.7*0.04)
        self.assertLess(self.relay_pi.kp, 0.25)
        self.assertGreater(self.relay_pi.kp, 0.15)

    def test_relay_peak_estimate_stable_to_halved_integration_step(self):
        finer = identify_relay(self.p, step_s=5., sample_s=30.)
        self.assertAlmostEqual(finer.temperature_amplitude_k,
                               self.relay.temperature_amplitude_k, delta=0.008)
        self.assertAlmostEqual(finer.period_s, self.relay.period_s, delta=60.)

    def test_invalid_control_parameters_rejected(self):
        for kp,ki,tracking in [(-.1,.01,360),(.1,0,360),(.1,.01,0),(.1,float('nan'),360)]:
            with self.assertRaises(ValueError):PISettings(kp,ki,'invalid',tracking)
        with self.assertRaises(ValueError):identify_step(replace(self.p,hx_mode='duty_limiter'))
        with self.assertRaises(ValueError):identify_relay(replace(self.p,hx_mode='duty_limiter'))

    def test_bumpless_initialization(self):
        x,u,_=equilibrium(self.p)
        ctrl=PIController(PISettings(.1,.00001,'test'),x.tb+1,u,60)
        cmd=ctrl.command(0,x,Disturbance(),u,self.p)
        self.assertAlmostEqual(cmd,u,delta=1e-12)
        self.assertAlmostEqual(ctrl.last_raw_command,u,delta=1e-12)

    def test_antiwindup_tracks_actual_command_after_saturation_and_slew(self):
        x,u,_=equilibrium(self.p)
        cfg=PISettings(.9,.002,'test',tracking_time_s=120)
        ctrl=PIController(cfg,x.tb,u,60,initialized=True,integral_command=0)
        ctrl.setpoint_k=x.tb+15
        raw=ctrl.bias_command+cfg.kp*15
        ctrl.command(0,x,Disturbance(),u,self.p)
        self.assertEqual(ctrl.saturation_events,1)
        self.assertEqual(ctrl.slew_events,1)
        self.assertAlmostEqual(ctrl.last_applied_command,u+self.p.max_command_step)
        plain=cfg.ki*60*15
        self.assertLess(ctrl.integral_command,plain)
        self.assertLess(ctrl.integral_command,0)
        self.assertGreater(raw,self.p.n_max)

    def test_command_slew_and_bounds_same_as_wp2_plant(self):
        x,u,_=equilibrium(self.p)
        ctr=PIController(self.relay_pi,x.tb+10,u,60)
        s=simulate(self.p,x,Schedule(lambda t:u,lambda t:Disturbance(),
                    feedback=lambda t,x,d,prev:ctr.command(t,x,d,prev,self.p)),
                    duration_s=3600,step_s=10,control_period_s=60)
        cmd=s.commands[::6]
        self.assertTrue(np.all(cmd>=self.p.n_min-1e-12))
        self.assertTrue(np.all(cmd<=self.p.n_max+1e-12))
        self.assertLessEqual(float(np.max(abs(np.diff(cmd)))),self.p.max_command_step+1e-12)
        self.assertGreater(ctr.slew_events,0)
        self.assertLess(float(np.max(abs(s.energy_residual))),.001)

    def test_two_methods_same_nonlinear_plant_and_disturbances(self):
        summaries=[]
        for cfg in (self.imc,self.relay_pi):
            s,ctrl,target=closed_loop(self.p,cfg)
            m=metrics(s,target)
            summaries.append((s,m))
            self.assertLess(m['max_abs_error_K'],2.0)
            self.assertLess(m['max_energy_residual_J'],.001)
            self.assertLessEqual(m['max_command_slew'],self.p.max_command_step+1e-9)
            self.assertAlmostEqual(float(s.times[-1]),14_400)
            self.assertAlmostEqual(float(s.states[0,1]),403.15,delta=1e-10)
            self.assertEqual(m['service_unserved_kWh'],0.)
        self.assertEqual(len(summaries[0][0].states),len(summaries[1][0].states))
        self.assertNotAlmostEqual(summaries[0][1]['iae_Ks'],summaries[1][1]['iae_Ks'],delta=100)

    def test_existing_open_loop_schedule_still_works(self):
        x,u,_=equilibrium(self.p)
        s=simulate(self.p,x,Schedule(lambda t:u,lambda t:Disturbance()),
                   duration_s=600,step_s=10,control_period_s=60)
        self.assertAlmostEqual(s.states[-1,1],x.tb,delta=1e-8)
        self.assertLess(float(np.max(abs(s.energy_residual))),.001)

    def test_transfer_to_bypass_mode_reported_not_hidden(self):
        p=replace(self.p,hx_mode='duty_limiter',ua_flow_exponent=.8)
        s,ctrl,target=closed_loop(p,self.imc,duration_s=7200,
                                    return_step_s=3600,source_step_s=6000)
        self.assertGreater(float(np.max(abs(s.states[:,1]-target))),0)
        self.assertLess(float(np.max(abs(s.energy_residual))),.001)
        self.assertLessEqual(metrics(s,target)['max_command_slew'],p.max_command_step+1e-9)

if __name__=='__main__':unittest.main()
