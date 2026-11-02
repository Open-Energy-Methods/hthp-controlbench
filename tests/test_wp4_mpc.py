"""WP4 independent physics/QP/controller checks; all inputs are synthetic."""
import unittest
from dataclasses import replace
import numpy as np
from ht_hp_controlbench.core import Parameters, Disturbance, State, equilibrium, output
from ht_hp_controlbench.mpc import (MPCConfig, MPCController, linearize,
     _advance, solve_mpc, closed_loop_mpc)
from ht_hp_controlbench.pi import PISettings, metrics


class TestMPC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=Parameters()
        cls.x,cls.u,_=equilibrium(cls.p)
        cls.d=Disturbance()
        cls.cfg=MPCConfig(horizon=8)
        cls.backup=PISettings(0.02,0.00001,'IMC backup')

    def _solve(self,**kwargs):
        cfg=kwargs.pop('cfg',self.cfg)
        d=kwargs.pop('d',self.d)
        return solve_mpc(self.x,self.u,self.p,d,cfg,self.x.tb+0.4,
                         [d]*cfg.horizon,[0.17]*cfg.horizon,**kwargs)

    def test_local_discrete_jacobian_agrees_with_nonlinear_perturbations(self):
        l=linearize(self.x,self.u,self.p,self.d,self.cfg)
        dx=np.array([.3,-.25,.01]);du=.015
        truth=_advance(State(*(l.x0+dx)),self.u+du,self.p,self.d,
                       self.cfg.period_s,self.cfg.integration_step_s)
        prediction=l.next0+l.A@dx+l.B*du
        self.assertLess(np.max(abs(np.array((truth.th,truth.tb,truth.n))-prediction)),.002)

    def test_joint_electrical_power_jacobian_is_affine_to_first_order(self):
        l=linearize(self.x,self.u,self.p,self.d,self.cfg)
        xx=State(self.x.th+.2,self.x.tb+.1,self.x.n+.01)
        dd=replace(self.d,t_source=self.d.t_source+1.)
        actual=output(xx,self.p,dd).p_el
        pred=l.p0+l.power_x@(np.array([xx.th,xx.tb,xx.n])-l.x0)+l.power_source
        self.assertLess(abs(actual-pred)/actual,.002)

    def test_solve_accepts_and_is_receding_horizon(self):
        a=self._solve()
        self.assertTrue(a.accepted,a.status)
        self.assertEqual(a.horizon_used,self.cfg.horizon)
        self.assertLessEqual(abs(a.command-self.u),self.p.max_command_step+1e-6)
        self.assertLess(a.max_temp_error_k,self.cfg.nonlinear_temp_tolerance_k)
        self.assertLess(a.max_power_relative_error,self.cfg.nonlinear_power_relative_tolerance)
        updated=State(self.x.th+.1,self.x.tb-.1,self.x.n)
        b=solve_mpc(updated,self.u,self.p,self.d,self.cfg,self.x.tb+0.4,
                    [self.d]*self.cfg.horizon,[.17]*self.cfg.horizon)
        self.assertTrue(b.accepted,b.status)
        self.assertNotAlmostEqual(a.linearization.x0[0],b.linearization.x0[0])
        self.assertGreater(np.max(np.abs(a.linearization.A-b.linearization.A)),1e-8)
        # Both first commands may legitimately hit the same +0.05 slew bound.

    def test_forced_solver_failure_returns_no_fake_success(self):
        a=self._solve(force_failure=True)
        self.assertFalse(a.accepted)
        self.assertEqual(a.status,'forced_solver_failure')

    def test_bounds_and_strict_trust_region(self):
        cfg=replace(self.cfg,temp_trust_k=1e-7,modulation_trust=1e-7)
        d=replace(self.d,t_return=self.d.t_return+4)
        a=solve_mpc(self.x,self.u,self.p,d,cfg,self.x.tb+0.4,[d]*cfg.horizon,[.17]*cfg.horizon)
        self.assertFalse(a.accepted)
        self.assertNotEqual(a.status,'accepted')

    def test_qp_weight_validation(self):
        with self.assertRaises(ValueError):replace(self.cfg,w_slack=-1)
        with self.assertRaises(ValueError):replace(self.cfg,w_electric_eur=-1)
        with self.assertRaises(ValueError):replace(self.cfg,period_s=17)

    def test_controller_bumpless_pi_fallback_and_slew(self):
        c=MPCController(self.p,self.cfg,self.x.tb+.4,self.backup,self.u,always_fail=True)
        prev=self.u
        for k in range(5):
            out=c.command(k*self.cfg.period_s,self.x,self.d,prev,self.p)
            self.assertLessEqual(abs(out-prev),self.p.max_command_step+1e-12)
            self.assertGreaterEqual(out,self.p.n_min)
            self.assertLessEqual(out,self.p.n_max)
            prev=out
        self.assertEqual(c.fallback_events,5)
        self.assertEqual(len(c.decisions),5)
        self.assertTrue(all(not s.accepted for s in c.decisions))

    def test_closed_loop_nominal_and_forced_fallback_conserve_energy(self):
        for failed in (False,True):
            run,ctrl,goal=closed_loop_mpc(self.p,self.cfg,self.backup,duration_s=1200,force_failure=failed)
            self.assertEqual(len(ctrl.decisions),10)
            self.assertEqual(ctrl.fallback_events,10 if failed else 0)
            self.assertLess(np.max(abs(run.energy_residual)),3.)
            self.assertTrue(np.all(np.isfinite(run.states)))
            self.assertGreater(metrics(run,goal,self.cfg.period_s)['iae_Ks'],0)
            commands=run.commands[::int(self.cfg.period_s/self.cfg.integration_step_s)]
            self.assertLessEqual(np.max(abs(np.diff(commands))),self.p.max_command_step+1e-9)

    def test_forecast_vs_persistence_only_changes_future_inputs(self):
        p=self.p
        def actual(t):return Disturbance(t_return=363.15 if t<3600 else 365.15)
        c=MPCController(p,self.cfg,self.x.tb+.4,self.backup,self.u,
               disturbance_forecast=lambda future,current:actual(future))
        future=[c.disturbance_forecast(3500+j*self.cfg.period_s,actual(3500)) for j in range(self.cfg.horizon)]
        persistence=[actual(3500)]*self.cfg.horizon
        self.assertEqual(future[0],persistence[0])
        self.assertNotEqual(future[-1],persistence[-1])

    def test_model_mismatch_does_not_reidentify_controller(self):
        plant=replace(self.p,c_b=self.p.c_b*.8)
        run,ctrl,_=closed_loop_mpc(self.p,self.cfg,self.backup,1200,mismatch=plant)
        self.assertTrue(np.all(np.isfinite(run.states)))
        self.assertEqual(ctrl.p_model,self.p)
        self.assertNotEqual(ctrl.p_model,plant)

    def test_nonlinear_rollout_rejects_tiny_tolerance(self):
        cfg=replace(self.cfg,nonlinear_temp_tolerance_k=1e-8,nonlinear_power_relative_tolerance=1e-10)
        a=solve_mpc(self.x,self.u,self.p,self.d,cfg,self.x.tb+0.4,[self.d]*cfg.horizon,[.17]*cfg.horizon)
        self.assertFalse(a.accepted)
        self.assertEqual(a.status,'nonlinear_rollout_mismatch')

    def test_price_gradient_changes_command_without_claiming_real_savings(self):
        # Identical physical state/reference, only synthetic objective price weight changes.
        cfg0=replace(self.cfg,w_electric_eur=0.)
        cfg1=replace(self.cfg,w_electric_eur=30.)
        no_cost=solve_mpc(self.x,self.u,self.p,self.d,cfg0,self.x.tb,
                          [self.d]*cfg0.horizon,[0.2]*cfg0.horizon)
        with_cost=solve_mpc(self.x,self.u,self.p,self.d,cfg1,self.x.tb,
                            [self.d]*cfg1.horizon,[0.2]*cfg1.horizon)
        self.assertTrue(no_cost.accepted)
        self.assertTrue(with_cost.accepted)
        self.assertLess(with_cost.command,no_cost.command-0.001)

    def test_unsupported_future_process_spec_is_not_silently_ignored(self):
        forecast=[self.d]*4+[replace(self.d,t_required=self.d.t_required+2.)]*4
        r=solve_mpc(self.x,self.u,self.p,self.d,self.cfg,self.x.tb+.4,forecast,[.16]*8)
        self.assertFalse(r.accepted)
        self.assertEqual(r.status,'unsupported_disturbance_forecast')

    def test_bypass_saturation_boundary_crossing_detected_by_nonlinear_rollout(self):
        # Forecast switches mid-horizon from duty-limited f<1 to saturated f=1.
        from ht_hp_controlbench.core import heat_exchanger
        plant=replace(self.p,hx_mode='duty_limiter',ua_flow_exponent=.8)
        x,u,_=equilibrium(plant)
        d0=Disturbance();d1=replace(d0,t_return=356.15)
        self.assertLess(heat_exchanger(x.tb,plant,d0).fraction,1.)
        self.assertEqual(heat_exchanger(x.tb,plant,d1).fraction,1.)
        cfg=replace(MPCConfig(horizon=10),nonlinear_temp_tolerance_k=.01)
        future=[d0]*3+[d1]*7
        r=solve_mpc(x,u,plant,d0,cfg,x.tb+.4,future,[.16]*10)
        self.assertFalse(r.accepted)
        self.assertEqual(r.status,'nonlinear_rollout_mismatch')
        self.assertGreater(r.max_temp_error_k,.01)

if __name__=='__main__':unittest.main()