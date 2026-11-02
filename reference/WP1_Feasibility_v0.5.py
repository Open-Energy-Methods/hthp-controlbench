"""HTHP-ControlBench v0.5 — synthetic WP1 steady-state feasibility worksheet.

Usage: python HTHP_ControlBench_WP1_Feasibility_v0.5.py

This is deliberately NOT a dynamic HTHP model, equipment calibration, or controller.
For a provisional counterflow process HX with constant effective UA and ideal
instantaneous process-side bypass mixing, it checks algebraic energy/service
closure under two explicitly separate modes.

SI-derived units in this *worksheet* are kW, kW/K, and °C differences. Cycle
Carnot calculations use Kelvin. Future dynamic modules must use SI W,J,K,s.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import exp, isclose
import unittest

@dataclass(frozen=True)
class Nominal:
    c_proc: float = 10.0      # kW/K, full total process throughput
    c_hot: float = 100.0      # kW/K, through HX
    ua: float = 16.0          # kW/K, CONDITIONAL constant effective UA
    t_process_return: float = 90.0
    t_process_required: float = 120.0
    t_buffer: float = 130.0
    khb: float = 100.0        # kW/K, header-buffer exchange conductance
    loss_buffer: float = 5.0 # kW
    loss_header: float = 5.0 # kW
    t_source: float = 60.0   # degC bulk, illustrative
    evap_approach: float = 5.0   # K
    cond_approach: float = 5.0   # K
    eta_second_law: float = .45


def epsilon_counterflow(cold: float, hot: float, ua: float) -> float:
    """Counterflow effectiveness, for strictly positive two-stream capacity rates."""
    if min(cold, hot, ua) <= 0:
        raise ValueError("positive heat-capacity rates and conductance required")
    cmin, cmax = min(cold, hot), max(cold, hot)
    cr = cmin / cmax
    ntu = ua / cmin
    if isclose(cr, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return ntu / (1.0 + ntu)
    z = exp(-ntu*(1-cr))
    return (1-z)/(1-cr*z)


def physical_heat_at_bypass(p: Nominal, f: float) -> float:
    """Heat to through-HX process stream; f is process flow fraction into HX."""
    if not 0 <= f <= 1:
        raise ValueError("bypass through-HX fraction must lie within [0,1]")
    if f == 0 or p.t_buffer <= p.t_process_return:
        return 0.0
    c_through = f*p.c_proc
    eff=epsilon_counterflow(c_through,p.c_hot,p.ua)
    return eff*min(c_through,p.c_hot)*(p.t_buffer-p.t_process_return)


def solve_local_bypass(p: Nominal, target_kw: float, tol_kw: float=1e-10):
    """Solve algebraic process bypass; not a dynamic state or an MPC decision.

    If maximum passive transfer is insufficient, f=1 and shortfall is reported.
    Bisection assumes monotonicity for this declared nominal envelope; any
    expansion to different flow arrangements must verify that assumption.
    """
    if target_kw <= 0:
        return 0.0
    if target_kw >= physical_heat_at_bypass(p,1):
        return 1.0
    lo,hi=0.0,1.0
    for _ in range(100):
        mid=(lo+hi)/2
        if physical_heat_at_bypass(p,mid)<target_kw:lo=mid
        else:hi=mid
        if physical_heat_at_bypass(p,mid)-target_kw == 0 or hi-lo<1e-15:
            break
    f=(lo+hi)/2
    assert abs(physical_heat_at_bypass(p,f)-target_kw)<tol_kw
    return f


def worksheet(p: Nominal, mode: str) -> dict:
    required=p.c_proc*(p.t_process_required-p.t_process_return)
    if mode == "duty_limiter":f=solve_local_bypass(p, required)
    elif mode == "no_bypass":f=1.0
    else:raise ValueError(mode)
    q=physical_heat_at_bypass(p,f)
    eff=epsilon_counterflow(f*p.c_proc,p.c_hot,p.ua) if f else None
    proc_mixed_out=p.t_process_return+q/p.c_proc
    proc_hx_out=p.t_process_return+q/(f*p.c_proc) if f else p.t_process_return
    hot_out=p.t_buffer-q/p.c_hot
    header=p.t_buffer+(q+p.loss_buffer)/p.khb
    hp=q+p.loss_buffer+p.loss_header
    t_evap=p.t_source-p.evap_approach+273.15
    t_cond=header+p.cond_approach+273.15
    carnot=t_cond/(t_cond-t_evap)
    cop=p.eta_second_law*carnot
    electrical=hp/cop
    q_source=hp-electrical
    pass_temp=proc_mixed_out>=p.t_process_required-1e-9
    q_max=physical_heat_at_bypass(p,1)
    return dict(mode=mode, target_kw=required, full_flow_epsilon=epsilon_counterflow(p.c_proc,p.c_hot,p.ua),
                q_max_kw=q_max, t_buffer_min_service=p.t_process_return+required/(epsilon_counterflow(p.c_proc,p.c_hot,p.ua)*min(p.c_proc,p.c_hot)),
                f=f, hx_epsilon=eff, q_transferred_kw=q, t_proc_out=proc_mixed_out,
                t_proc_hx_out=proc_hx_out, t_hot_out=hot_out, header_c=header,
                hp_kw=hp, carnot=carnot, model_cop=cop, electrical_kw=electrical,
                source_kw=q_source, qualified=pass_temp and q>=required-1e-9,
                shortfall_kw=max(0,required-q), excess_kw=max(0,q-required))

class PhysicsTests(unittest.TestCase):
    def setUp(self):self.p=Nominal()

    def test_counterflow_reference_and_limits(self):
        self.assertAlmostEqual(epsilon_counterflow(10,100,16),0.7815902847553592,places=13)
        self.assertAlmostEqual(epsilon_counterflow(10,1e12,16),1-exp(-1.6),places=10)
        self.assertAlmostEqual(epsilon_counterflow(10,10,16),1.6/2.6,places=13)

    def test_solved_bypass_is_not_linear_scalar(self):
        r=worksheet(self.p,'duty_limiter')
        self.assertAlmostEqual(r['f'],0.9314688744432148,places=10)
        self.assertAlmostEqual(r['q_transferred_kw'],300,places=8)
        self.assertAlmostEqual(r['hx_epsilon'],0.8051798837060575,places=9)
        self.assertAlmostEqual(r['t_proc_out'],120,places=9)
        self.assertGreater(abs(r['f']-r['target_kw']/r['q_max_kw']),0.02)
        self.assertAlmostEqual(r['header_c'],133.05,places=9)
        self.assertAlmostEqual(r['hp_kw'],310,places=9)

    def test_passive_not_identical_to_bypass(self):
        b=worksheet(self.p,'no_bypass')
        self.assertAlmostEqual(b['q_transferred_kw'],312.6361139021437,places=8)
        self.assertAlmostEqual(b['t_proc_out'],121.26361139021437,places=8)
        self.assertAlmostEqual(b['header_c'],133.17636113902142,places=8)
        self.assertAlmostEqual(b['hp_kw'],322.6361139021437,places=8)
        self.assertGreater(b['excess_kw'],12)

    def test_energy_conservation_and_mixing(self):
        for mode in ('duty_limiter','no_bypass'):
            r=worksheet(self.p,mode)
            q=r['q_transferred_kw']
            self.assertAlmostEqual(q,self.p.c_proc*(r['t_proc_out']-self.p.t_process_return),places=8)
            self.assertAlmostEqual(q,self.p.c_hot*(self.p.t_buffer-r['t_hot_out']),places=8)
            if r['f']:
                mixed=r['f']*r['t_proc_hx_out']+(1-r['f'])*self.p.t_process_return
                self.assertAlmostEqual(mixed,r['t_proc_out'],places=8)
            self.assertAlmostEqual(r['source_kw']+r['electrical_kw'],r['hp_kw'],places=8)
            self.assertAlmostEqual(r['hp_kw'],q+self.p.loss_buffer+self.p.loss_header,places=8)

    def test_unmet_service_does_not_delete_heat(self):
        cold=Nominal(t_buffer=122)
        r=worksheet(cold,'duty_limiter')
        self.assertEqual(r['f'],1)
        self.assertGreater(r['q_transferred_kw'],0)
        self.assertGreater(r['shortfall_kw'],0)
        self.assertFalse(r['qualified'])

    def test_off_and_tiny_load(self):
        self.assertEqual(physical_heat_at_bypass(self.p,0),0)
        self.assertEqual(solve_local_bypass(self.p,0),0)
        f=solve_local_bypass(self.p,0.1)
        self.assertGreater(f,0)
        self.assertLess(f,0.001)
        self.assertAlmostEqual(physical_heat_at_bypass(self.p,f),0.1,places=8)

if __name__=='__main__':
    p=Nominal()
    for mode in ('duty_limiter','no_bypass'):
        print(f'\n--- {mode} (SYNTHETIC algebra; no calibrated HTHP) ---')
        for k,v in worksheet(p,mode).items():
            if isinstance(v,float):print(f'{k:25s} {v:.11f}')
            else:print(f'{k:25s} {v}')
    print('\n--- Independent worksheet tests ---')
    unittest.main(argv=['ht_hp_feasibility'],exit=False,verbosity=2)