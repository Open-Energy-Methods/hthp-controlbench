from __future__ import annotations
from dataclasses import replace
from decimal import Decimal, getcontext
import unittest
import numpy as np
from ht_hp_controlbench import Parameters, State, Disturbance, heat_exchanger, equilibrium, rhs, counterflow_effectiveness, Schedule, simulate


class PhysicsTests(unittest.TestCase):
    def setUp(self):
        self.p = Parameters()
        self.d = Disturbance()

    def test_wp1_nominal_and_bypass(self):
        b=heat_exchanger(403.15,replace(self.p,hx_mode='duty_limiter'),self.d)
        n=heat_exchanger(403.15,replace(self.p,hx_mode='no_bypass'),self.d)
        self.assertAlmostEqual(counterflow_effectiveness(10_000,100_000,16_000),.7815902847553592,12)
        self.assertAlmostEqual(b.fraction,.9314688744432145,10)
        self.assertAlmostEqual(b.q_transferred/1000,300,8)
        self.assertAlmostEqual(n.q_transferred/1000,312.6361139021437,8)
        self.assertAlmostEqual(b.t_proc_out-273.15,120,8)
        self.assertAlmostEqual(n.t_proc_out-273.15,121.26361139021437,8)
        self.assertGreater(abs(b.fraction-b.q_requested/n.q_max),.02)

    def test_near_cr_unity_against_high_precision_decimal(self):
        # Independent high-precision analytic formula; stable expm1 implementation compared.
        getcontext().prec=55
        ntu=Decimal('1.6')
        for gap in (Decimal('1e-3'),Decimal('1e-6'),Decimal('1e-9'),Decimal('1e-11'),Decimal('1e-13')):
            cr=Decimal(1)-gap
            z=(-ntu*gap).exp()
            expected=float((Decimal(1)-z)/(Decimal(1)-cr*z))
            cmin=10000.0
            cmax=float(Decimal(10000)/cr)
            actual=counterflow_effectiveness(cmin,cmax,16000)
            self.assertAlmostEqual(actual,expected,delta=5e-13)
        self.assertAlmostEqual(counterflow_effectiveness(10000,10000,16000),1.6/2.6,13)

    def test_disconnected_and_off_modes_are_explicitly_rejected_by_equilibrium(self):
        # Audit A03: offline dynamic plant is valid (analytic loss test), but
        # the steady solver cannot divide through zero khb / compressor rating.
        for settings in ({'khb':0},{'q_hp_rated':0}):
            with self.assertRaisesRegex(ValueError,'steady equilibrium undefined'):
                equilibrium(replace(self.p,**settings))

    def test_numerical_parameter_domain_rejects_nonfinite_or_negative_inputs(self):
        for kwargs in ({'q_hp_rated':-1},{'c_hot':-1},{'ua_proc':-1},
                       {'c_proc':-1},{'khb':float('nan')},
                       {'q_hp_rated':float('inf')},{'max_command_step':0},
                       {'capacity_factor_min':0}):
            with self.assertRaises(ValueError):replace(self.p,**kwargs)

    def test_nominal_equilibria_both_modes(self):
        for mode in ('duty_limiter','no_bypass'):
            p=replace(self.p,hx_mode=mode)
            x,u,r=equilibrium(p)
            xdot,_=rhs(x,u,p,self.d)
            self.assertAlmostEqual(x.tb,403.15,10)
            self.assertAlmostEqual(r.q_hp, r.hx.q_transferred + r.loss_h + r.loss_b, delta=1e-7)
            if mode == 'duty_limiter':self.assertAlmostEqual(r.q_hp,310_000,delta=1e-7)
            else:self.assertAlmostEqual(r.q_hp,322_641.7026300969,delta=1e-7)
            self.assertAlmostEqual(xdot.th,0,delta=1e-11)
            self.assertAlmostEqual(xdot.tb,0,delta=1e-11)
            self.assertAlmostEqual(xdot.n,0,delta=1e-12)
            self.assertGreater(r.q_source,0)
            self.assertAlmostEqual(r.q_hp,r.q_source+r.p_el,delta=1e-7)

    def test_no_demand_does_not_delete_physical_transfer(self):
        p=replace(self.p,hx_mode='no_bypass')
        cold=heat_exchanger(395.15,p,self.d)
        self.assertGreater(cold.q_transferred,0)
        self.assertFalse(cold.qualified)
        self.assertGreater(cold.q_spec_unserved,0)
        self.assertAlmostEqual(cold.t_proc_out,self.d.t_return+cold.q_transferred/p.c_proc,9)

    def test_constant_fixed_process_flow_and_return_disturbance(self):
        b0=heat_exchanger(403.15,replace(self.p,hx_mode='duty_limiter'),self.d)
        b1=heat_exchanger(403.15,replace(self.p,hx_mode='duty_limiter'),replace(self.d,t_return=368.15))
        self.assertEqual(b0.q_requested,300000)
        self.assertEqual(b1.q_requested,250000)
        with self.assertRaises(ValueError):
            heat_exchanger(403.15,self.p,replace(self.d,c_proc=12_000))
        p=replace(self.p,flow_mode='exogenous')
        alt=heat_exchanger(403.15,p,replace(self.d,c_proc=12_000))
        self.assertEqual(alt.q_requested,360000)
        with self.assertRaises(ValueError):replace(self.p,flow_mode='controlled')

    def test_ua_sensitivity_provisional(self):
        fs=[]
        for exponent in (0.,.6,.7,.8):
            p=replace(self.p,hx_mode='duty_limiter',ua_flow_exponent=exponent)
            hx=heat_exchanger(403.15,p,self.d)
            fs.append(hx.fraction)
            self.assertAlmostEqual(hx.q_transferred,300_000,delta=1e-7)
            self.assertAlmostEqual(hx.t_proc_out-273.15,120.,delta=1e-7)
        self.assertTrue(all(fs[k+1]>=fs[k] for k in range(3)))
        self.assertLess(fs[-1],1.)

    def test_compressor_command_lag_separate_and_slew(self):
        p=replace(self.p,hx_mode='duty_limiter')
        x,u,_=equilibrium(p)
        s=simulate(p,x,Schedule(lambda t:1.0,lambda t:self.d),duration_s=300,step_s=5,control_period_s=60)
        self.assertAlmostEqual(s.commands[0],u+.05,delta=1e-12)
        self.assertGreater(s.commands[0],s.states[0,2])
        self.assertGreater(s.states[1,2],s.states[0,2])
        self.assertLess(s.states[1,2],s.commands[0])
        self.assertLessEqual(max(abs(np.diff(s.commands))),.050000001)
        self.assertTrue(np.all(s.states[:,2]>=0))
        self.assertTrue(np.all(s.states[:,2]<=1))

    def test_energy_conservation_full_transient(self):
        p=replace(self.p,hx_mode='duty_limiter')
        x,u,_=equilibrium(p)
        s=simulate(p,x,Schedule(lambda t:u+.05,lambda t:self.d),duration_s=1800,step_s=5,control_period_s=60)
        # Integral channels are physical (not KPI qualified) and track capacity changes.
        self.assertLess(float(np.max(np.abs(s.energy_residual))), 1e-5)
        self.assertGreater(s.energy_in[-1],0.)
        self.assertGreater(s.energy_process[-1],0.)
        self.assertLessEqual(s.energy_electric[-1],s.energy_in[-1])
        self.assertGreater(abs(s.states[-1,1]-s.states[0,1]),.01)

    def test_refinement_convergence(self):
        p=replace(self.p,hx_mode='duty_limiter')
        x,u,_=equilibrium(p)
        sched=Schedule(lambda t:u+.04,lambda t:self.d)
        a=simulate(p,x,sched,duration_s=300,step_s=10,control_period_s=60)
        b=simulate(p,x,sched,duration_s=300,step_s=5,control_period_s=60)
        c=simulate(p,x,sched,duration_s=300,step_s=2.5,control_period_s=60)
        coarse=np.max(abs(a.states[-1,:2]-b.states[-1,:2]))
        fine=np.max(abs(b.states[-1,:2]-c.states[-1,:2]))
        self.assertLess(coarse,0.005)
        self.assertLess(fine,coarse)

    def test_heat_loss_analytic_when_decoupled_and_off(self):
        p=replace(self.p,khb=0,q_hp_rated=0,ua_proc=0,c_proc=0)
        x0=State(410.15,400.15,0.)
        s=simulate(p,x0,Schedule(lambda t:0.,lambda t:self.d),duration_s=600,step_s=5,control_period_s=60)
        for idx,ua,cap,init in [(0,p.ua_h,p.c_h,x0.th),(1,p.ua_b,p.c_b,x0.tb)]:
            analytic=self.d.t_ambient+(init-self.d.t_ambient)*np.exp(-ua*600/cap)
            self.assertAlmostEqual(s.states[-1,idx],analytic,delta=1e-9)

    def test_service_is_separate_from_conservation_during_undercapacity(self):
        p=replace(self.p,hx_mode='duty_limiter')
        cold=State(401.15,397.15,.7)
        s=simulate(p,cold,Schedule(lambda t:.7,lambda t:self.d),duration_s=120,step_s=5,control_period_s=60)
        self.assertFalse(s.service_met[0])
        self.assertGreater(s.q_process[0],0)
        self.assertGreater(s.q_spec_unserved[0],0)
        self.assertAlmostEqual(s.energy_residual[-1],0,delta=1e-5)


    def test_bypass_capacity_boundary_continuous_but_kinked(self):
        p=replace(self.p,hx_mode='duty_limiter')
        qmax=heat_exchanger(403.15,p,self.d).q_max
        # Switch local demand across passive capacity by changing prescribed service target.
        def by_duty(q):
            d=replace(self.d,t_required=self.d.t_return+q/p.c_proc)
            return heat_exchanger(403.15,p,d)
        h=10.0 # W
        low,mid,high=(by_duty(qmax-h),by_duty(qmax),by_duty(qmax+h))
        self.assertLess(low.fraction,1)
        self.assertAlmostEqual(mid.fraction,1,delta=1e-12)
        self.assertEqual(high.fraction,1)
        self.assertGreater((mid.fraction-low.fraction)/h,0)
        self.assertAlmostEqual((high.fraction-mid.fraction)/h,0,delta=1e-12)
        self.assertLess(abs(low.q_transferred-mid.q_transferred),h+1e-7)
        self.assertGreater(high.q_shortfall,0)

    def test_independent_trapezoid_energy_audit_converges(self):
        # Independently integrate the PHYSICAL rates logged at both endpoints,
        # rather than reusing RK4's integral channels.
        p=replace(self.p,hx_mode='duty_limiter')
        x,u,_=equilibrium(p)
        sched=Schedule(lambda t:u+.04,lambda t:self.d)
        err=[]
        for step in (10.,5.,2.5):
            s=simulate(p,x,sched,duration_s=300,step_s=step,control_period_s=60)
            power=s.q_hp-s.q_process-p.ua_h*(s.states[:,0]-self.d.t_ambient)-p.ua_b*(s.states[:,1]-self.d.t_ambient)
            separate_integral=float(np.trapezoid(power,dx=step))
            storage=float(p.c_h*(s.states[-1,0]-s.states[0,0])+p.c_b*(s.states[-1,1]-s.states[0,1]))
            err.append(abs(separate_integral-storage))
        self.assertLess(err[-1],300.)
        self.assertLess(err[-1],err[1])
        self.assertLess(err[1],err[0])

if __name__=='__main__':unittest.main()
