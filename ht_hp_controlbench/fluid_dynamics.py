"""WP7 experimental property-map dynamic plant, distinct from frozen WP2 model.

Buffer state is specific water enthalpy h(T,p) at an *assumed* fixed loop
pressure; this makes the energy balance exact under the specified WP2 geometry
without using a constant water heat capacity. Compressor Q and P use the
joint CoolProp-based surrogate map; no extrapolation or uncalibrated equipment
safety/rating is implied. Fixed WP3 PI gains are used unchanged.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .core import Disturbance, Parameters, State, heat_exchanger
from .realfluid import CycleMap, PointRejected, coolprop_backend, _prop
from .pi import PIController, PISettings
from .thermo_feasibility import hold_service_at_buffer


@dataclass(frozen=True)
class FluidSimulationSummary:
    controller: str
    status: str
    duration_s: float
    iae_Ks: float
    electricity_kwh: float
    condenser_heat_kwh: float
    process_heat_kwh: float
    fraction_service_qualified: float
    max_energy_residual_J: float
    max_abs_buffer_deviation_k: float
    max_actuator_slew: float
    equipment_verified: bool = False


def fluid_pi_simulation(model:CycleMap,settings:PISettings,
                        p:Parameters|None=None,duration_s:float=7200.,
                        step_s:float=10.,control_period_s:float=120.,
                        props=None)->FluidSimulationSummary:
    """Quasi-research *dynamic* PI rerun with a real-fluid-based Q/P map.

    No model tuning; PI gains are from WP3's synthetic model. Actuator lag,
    buffer enthalpy and WP2 energy losses are maintained. The experiment fails
    closed if any intermediate refrigerant-map state leaves verified grid.
    """
    p=p or Parameters(hx_mode='duty_limiter')
    props=props if props is not None else coolprop_backend()
    if (step_s<=0 or duration_s<=0 or control_period_s<=0 or
        abs(round(duration_s/step_s)-duration_s/step_s)>1e-9 or
        abs(round(control_period_s/step_s)-control_period_s/step_s)>1e-9):
        raise ValueError('duration/control period must be multiples of positive dt')
    mass_kg=5000.0
    pressure=model.assumptions.service_header_pressure_pa
    d0=Disturbance()
    eq=hold_service_at_buffer(403.15,model,p,d0,props=props)
    if not eq['status'].startswith('same_service_property_feasible'):
        raise PointRejected('fluid_dynamics_has_no_valid_initial_equilibrium')
    th0=eq['t_header_k']; tb0=403.15;n0=eq['required_modulation']
    hw0=_prop(props,'H','IF97::Water','T',tb0,'P',pressure)
    # y=(T_header, specific-water-h, compressor-modulation, E_hp, E_el,
    # E_process, E_header_loss, E_buffer_loss)
    y=np.array([th0,hw0,n0,0,0,0,0,0],float)
    period_steps=int(round(control_period_s/step_s));steps=int(round(duration_s/step_s))
    control=PIController(settings,tb0,n0,control_period_s)
    u=n0;u_max_step=0.;quality_count=0;iae=0.;deviate=0.
    def disturb(t):
        return Disturbance(t_return=363.15 if t<2400 else 364.15,
                           t_source=333.15 if t<4500 else 330.15)
    def temp(h):return _prop(props,'T','IF97::Water','P',pressure,'H',float(h))
    def stage(v,command,d):
        th,hw,n=v[:3];tb=temp(hw)
        if not 0<=n<=1:raise PointRejected('physical_compressor_modulation_out_of_bounds')
        qhp,pel,source=model.evaluate(n,d.t_source,th)
        hx=heat_exchanger(tb,p,d)
        qhb=p.khb*(th-tb)
        lh=p.ua_h*(th-d.t_ambient);lb=p.ua_b*(tb-d.t_ambient)
        return np.array([(qhp-qhb-lh)/p.c_h,
                         (qhb-hx.q_transferred-lb)/mass_kg,
                         (command-n)/p.tau_n,
                         qhp,pel,hx.q_transferred,lh,lb],float)
    for k in range(steps):
        t=k*step_s; d=disturb(t)
        tb=temp(y[1]);hx=heat_exchanger(tb,p,d)
        quality_count+=int(hx.qualified)
        iae+=abs(tb-tb0)*step_s
        deviate=max(deviate,abs(tb-tb0))
        if k%period_steps==0:
            x=State(y[0],tb,y[2])
            desired=control.command(t,x,d,u,p)
            proposed=min(p.n_max,max(p.n_min,desired))
            proposed=min(u+p.max_command_step,max(u-p.max_command_step,proposed))
            u_max_step=max(u_max_step,abs(proposed-u));u=proposed
        k1=stage(y,u,d)
        k2=stage(y+step_s*k1/2,u,d)
        k3=stage(y+step_s*k2/2,u,d)
        k4=stage(y+step_s*k3,u,d)
        y+=step_s*(k1+2*k2+2*k3+k4)/6
    # Full physical energy balance from water enthalpy, not synthetic m cp*DT
    lhs=p.c_h*(y[0]-th0)+mass_kg*(y[1]-hw0)
    rhs=y[3]-y[5]-y[6]-y[7]
    err=abs(lhs-rhs)
    return FluidSimulationSummary(
        settings.source,'completed_property_map_PI_test__EQUIPMENT_UNVERIFIED',
        duration_s,float(iae),float(y[4]/3.6e6),float(y[3]/3.6e6),
        float(y[5]/3.6e6),float(quality_count/steps),float(err),
        float(deviate),float(u_max_step))
