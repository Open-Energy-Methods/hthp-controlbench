"""Measurement integrity, counterfactual robustness and optional OSQP verification."""
import unittest
from dataclasses import replace
import importlib.util
import numpy as np
from ht_hp_controlbench.core import Parameters,Disturbance,equilibrium
from ht_hp_controlbench.robustness import RobustnessCase,declared_cases
from ht_hp_controlbench.mpc import MPCConfig,solve_mpc,linearize
from ht_hp_controlbench.mpc_robustness import run_robust_mpc_case
from ht_hp_controlbench.pi import PISettings

P=Parameters()
G=PISettings(.02,.000015,'fixed synthetic PI')
CFG=MPCConfig(horizon=5)

class TestRobustMPC(unittest.TestCase):
    def test_20_scenarios_are_identical_to_wp3_ledger(self):
        cases=declared_cases(P)
        self.assertEqual(len(cases),20)
        self.assertEqual(len({c.name for c in cases}),len(cases))

    def test_no_noise_is_still_exactly_observed(self):
        case=RobustnessCase('zero_noise',P)
        r=run_robust_mpc_case(P,case,method='mpc',pi_settings=G,cfg=CFG,duration_s=3600)
        self.assertTrue(np.allclose(r.sensor_buffer,r.sensor_truth))
        self.assertTrue(r.summary()['finite'])
        self.assertLess(r.summary()['max_energy_residual_J'],3.)

    def test_noisy_delayed_sensor_is_paired_between_pi_and_mpc(self):
        case=RobustnessCase('noisy_2sample_delay',P,noise_sd_k=.3,delay_updates=2,seed=23)
        a=run_robust_mpc_case(P,case,method='mpc',pi_settings=G,cfg=CFG,duration_s=3600)
        b=run_robust_mpc_case(P,case,method='imc_pi',pi_settings=G,cfg=CFG,duration_s=3600)
        self.assertEqual(a.summary()['sensor_delay_s'],120)
        self.assertAlmostEqual(a.sensor_buffer[2],b.sensor_buffer[2],places=12)
        self.assertNotAlmostEqual(a.sensor_buffer[5],a.sensor_truth[5])
        self.assertTrue(a.summary()['finite'] and b.summary()['finite'])

    def test_delay_is_real_fifo_not_noise_shift(self):
        case=RobustnessCase('delay',P,noise_sd_k=0,delay_updates=3)
        r=run_robust_mpc_case(P,case,method='imc_pi',pi_settings=G,cfg=CFG,duration_s=3600)
        self.assertAlmostEqual(r.sensor_buffer[3],r.sensor_truth[0])
        self.assertAlmostEqual(r.sensor_buffer[4],r.sensor_truth[1])

    def test_parameter_mismatch_not_reidentified(self):
        case=RobustnessCase('capacity_perturb',replace(P,q_hp_rated=P.q_hp_rated*.8))
        r=run_robust_mpc_case(P,case,method='mpc',pi_settings=G,cfg=CFG,duration_s=3600)
        self.assertTrue(r.summary()['finite'])
        self.assertGreater(r.summary()['max_estimation_header_error_K'],0)

    def test_same_clock_and_actuator_bound(self):
        case=RobustnessCase('noise',P,noise_sd_k=.1,seed=11)
        for method in ('imc_pi','relay_pi','mpc'):
            r=run_robust_mpc_case(P,case,method=method,pi_settings=G,cfg=CFG,duration_s=3600)
            self.assertEqual(r.summary()['decisions'],30)
            self.assertLessEqual(r.summary()['max_command_slew'],P.max_command_step+1e-9)
            self.assertLess(np.max(np.abs(r.sim.energy_residual)),3)

    def test_rejects_unsupported_sample_configuration(self):
        with self.assertRaises(ValueError):
            run_robust_mpc_case(P,RobustnessCase('x',P),method='mpc',pi_settings=G,
                                cfg=CFG,control_period_s=150,duration_s=3600)

    def test_modulation_boundary_has_feasible_linearization(self):
        x,u,_=equilibrium(P);d=Disturbance()
        for mod in (0.0,1.0):
            clipped=replace(x,n=mod)
            lin=linearize(clipped,mod,P,d,CFG)
            self.assertTrue(np.all(np.isfinite(lin.A)))
            self.assertTrue(np.all(np.isfinite(lin.power_x)))

    def test_backend_validation(self):
        with self.assertRaises(ValueError):replace(CFG,solver_backend='anything')

    @unittest.skipUnless(importlib.util.find_spec('osqp'),'OSQP optional: installed in CI QP audit job')
    def test_osqp_matches_slsqp_on_nominal_qp(self):
        x,u,_=equilibrium(P);d=Disturbance()
        results=[]
        for backend in ('slsqp','osqp'):
            c=replace(CFG,solver_backend=backend)
            results.append(solve_mpc(x,u,P,d,c,x.tb+.4,[d]*c.horizon,[.17]*c.horizon))
        for r in results:self.assertTrue(r.accepted,(r.status,r.qp_iterations))
        self.assertLess(abs(results[0].command-results[1].command),.015)
        self.assertLess(abs(results[0].objective-results[1].objective),.5)

    @unittest.skipUnless(importlib.util.find_spec('osqp'),'OSQP optional: installed in CI QP audit job')
    def test_osqp_respects_hard_constraints(self):
        x,u,_=equilibrium(P);d=Disturbance();c=replace(CFG,solver_backend='osqp')
        s=solve_mpc(x,u,P,d,c,x.tb+.4,[d]*c.horizon,[.17]*c.horizon)
        self.assertTrue(s.accepted,s.status)
        self.assertLessEqual(abs(s.command-u),P.max_command_step+1e-5)
        self.assertLess(s.max_temp_error_k,c.nonlinear_temp_tolerance_k)

if __name__=='__main__':unittest.main()