"""WP6 exploratory dynamic demonstration: 4-state HTHP with pump flow lag.

A hypothetical controlled hot-side circulation pump is added to the WP2 thermal
states, with synthetic affinity-law pump electrical power and flow-dependent UA.
The original WP2 model, its actuators and all WP3/4/5 results are unchanged.
No dynamic or noisy-plant SOC optimality theorem is claimed here.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from collections import deque
import numpy as np
from .core import Parameters,Disturbance,State,rhs,output
from .soc import SOCParameters,effective_plant,service_temperature_min,offline_optimum,policy_r,piecewise_policy_r
from .pi import PIController,PISettings


@dataclass(frozen=True)
class FlowState:
    th: float
    tb: float
    n: float
    r: float


@dataclass(frozen=True)
class DynamicSummary:
    policy: str
    price_eur_per_kwh: float
    electrical_kwh: float
    compressor_kwh: float
    pump_kwh: float
    missing_physical_kwh: float
    spec_unserved_kwh: float
    service_compliant_fraction: float
    buffer_error_integral_ks: float
    flow_total_variation: float
    max_energy_residual_j: float
    max_temperature_k: float
    saturated_flow_steps: int
    steps: int


def rk4_flow_step(x:FlowState,u_n:float,u_r:float,p:Parameters,c:SOCParameters,d:Disturbance,dt:float):
    """Thermal, compressor, pump-flow, electrical and energy terms use same RK4 quadrature."""
    def g(y):
        s=FlowState(*y[:4]);pp=effective_plant(p,c,s.r)
        derivatives,rate=rhs(State(s.th,s.tb,s.n),u_n,pp,d)
        if not (c.r_min-1e-9<=s.r<=c.r_max+1e-9):
            raise ValueError('pump flow outside declared envelope during RK4 stage')
        return np.array([derivatives.th,derivatives.tb,derivatives.n,(u_r-s.r)/c.tau_r,
                         rate.p_el,c.pump_nominal_w*s.r**3,rate.q_hp,
                         rate.hx.q_transferred,rate.loss_h,rate.loss_b,
                         rate.hx.q_shortfall,rate.hx.q_spec_unserved])
    y=np.zeros(12);y[:4]=[x.th,x.tb,x.n,x.r]
    k1=g(y);k2=g(y+dt*k1*.5);k3=g(y+dt*k2*.5);k4=g(y+dt*k3)
    vec=y+dt*(k1+2*k2+2*k3+k4)/6
    s=FlowState(*vec[:4]);return s,vec[4:]


def run_dynamic_soc(p:Parameters,c:SOCParameters,model:dict|None,
                    reference_disturbances:list[tuple[float,Disturbance]],
                    settings:PISettings,policy_name:str,
                    duration_s:float=14400.,integration_s:float=10.,control_s:float=120.,
                    sensor_noise_k:float=0.,sensor_delay_s:float=0.,seed:int=0,
                    price_eur_per_kwh:float=.2,initial_r:float|None=None,
                    observer_p:Parameters|None=None) -> tuple[DynamicSummary,dict]:
    """Compare held-constant SOC-CV policy to current-disturbance offline RTO oracle.

    Both get the same noisy/delayed buffer-temperature observation and measured
    exogenous process return/source conditions. Only the oracle reoptimizes the
    pump flow for every disturbance. The pump-flow sensor is assumed perfect.
    No privileged future disturbance is used by either controller.
    """
    if policy_name not in ('constant_soc','regime_soc','offline_rto'):
        raise ValueError('unsupported policy')
    if not reference_disturbances or reference_disturbances[0][0]!=0.:
        raise ValueError('disturbances must begin at t=0')
    if control_s % integration_s or duration_s % control_s or sensor_delay_s % control_s:
        raise ValueError('sample timings must be exact multiples')
    if sensor_noise_k<0 or sensor_delay_s<0 or price_eur_per_kwh<=0:
        raise ValueError('invalid noise/price')
    nominal=observer_p or p
    def disturbance(t):
        d=reference_disturbances[0][1]
        for at,new in reference_disturbances:
            if t>=at:d=new
            else:break
        return d
    d0=disturbance(0.)
    r0=initial_r if initial_r is not None else offline_optimum(p,c,d0).r
    # All comparator policies use the *same* initial state and compressor bias.
    pp=effective_plant(p,c,r0)
    tb0=service_temperature_min(p,c,d0,r0)+c.buffer_margin_k
    from .core import equilibrium
    state0,n0,_=equilibrium(pp,t_buffer=tb0,d=d0)
    x=FlowState(state0.th,state0.tb,state0.n,r0)
    ctrl=PIController(settings,tb0,n0,control_s)
    rng=np.random.default_rng(seed)
    delay_count=int(round(sensor_delay_s/control_s))
    obs_queue=deque()
    command_n=n0;command_r=r0
    integration_energy=np.zeros(8)
    nsteps=int(round(duration_s/integration_s));sub=int(round(control_s/integration_s))
    history=[];service_samples=0;temp_error=0.;flow_tv=0.;residual_max=0.
    saturated_steps=0;max_th=state0.th
    for k in range(nsteps):
        t=k*integration_s;d=disturbance(t)
        if k%sub==0:
            measured=x.tb+rng.normal(0.,sensor_noise_k)
            obs_queue.append(measured)
            observation=obs_queue[0] if len(obs_queue)<=delay_count else obs_queue.popleft()
            if policy_name=='offline_rto':
                opt=offline_optimum(p,c,d)
                if opt is None:raise ValueError('current disturbance infeasible for oracle')
                target_r=opt.r
            else:
                if model is None or not model.get('valid'):raise ValueError('SOC policy missing')
                target_r=policy_r(model,d)
                if policy_name=='regime_soc':
                    target_r,_=piecewise_policy_r(model,c,d)
                # If a constant CV yields infeasible/unbounded actuation, reject rather than silently clamp.
                if not c.r_min<=target_r<=c.r_max:raise ValueError('SOC-CV infeasible pump setpoint')
            command_r=np.clip(target_r,command_r-c.max_r_step,command_r+c.max_r_step)
            # Use actual measured flow (assumed sensor), declared nominal HX map,
            # and present measured process return only, not future disturbances.
            desired=service_temperature_min(nominal,c,d,float(x.r))+c.buffer_margin_k
            ctrl.setpoint_k=desired
            fake_state=State(float('nan'),float(observation),float('nan')) # PI has no access to hidden plant states
            command_n=ctrl.command(t,fake_state,d,command_n,p)
            history.append((t,float(command_r),float(command_n),float(observation),desired,d.t_return))
            if abs(command_r-c.r_max)<1e-7 or abs(command_r-c.r_min)<1e-7:saturated_steps+=1
        prior=x
        x,energies=rk4_flow_step(x,float(command_n),float(command_r),p,c,d,integration_s)
        integration_energy+=energies
        residual=(p.c_h*(x.th-prior.th)+p.c_b*(x.tb-prior.tb))-(energies[2]-energies[3]-energies[4]-energies[5])
        residual_max=max(residual_max,abs(residual))
        rate=output(State(x.th,x.tb,x.n),effective_plant(p,c,x.r),d)
        service_samples+=int(rate.hx.qualified)
        temp_error+=abs(x.tb-(service_temperature_min(nominal,c,d,x.r)+c.buffer_margin_k))*integration_s
        max_th=max(max_th,x.th)
    flow_tv=float(sum(abs(history[i][1]-history[i-1][1]) for i in range(1,len(history))))
    total=integration_energy[0]+integration_energy[1]
    summary=DynamicSummary(policy_name,price_eur_per_kwh,total/3.6e6,
        integration_energy[0]/3.6e6,integration_energy[1]/3.6e6,
        integration_energy[6]/3.6e6,integration_energy[7]/3.6e6,
        service_samples/nsteps,temp_error,flow_tv,residual_max,max_th,saturated_steps,len(history))
    return summary,{'controls':history,'final':[x.th,x.tb,x.n,x.r]}
