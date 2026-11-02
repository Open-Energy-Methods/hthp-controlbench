"""Piecewise-constant disturbances/commands with RK4 and energy-integral diagnostics.

WP3 optionally supplies feedback through Schedule.feedback; the same RK4 plant is reused.
Command slew imposed once per control interval.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import numpy as np
from .core import Parameters, State, Disturbance, output, rhs


@dataclass(frozen=True)
class Schedule:
    command: Callable[[float], float]
    disturbance: Callable[[float], Disturbance]
    feedback: Callable[[float, State, Disturbance, float], float] | None = None


@dataclass(frozen=True)
class Simulation:
    times: np.ndarray
    states: np.ndarray     # K,K,fraction
    commands: np.ndarray   # applied u, at t[k] through next interval
    q_hp: np.ndarray
    p_el: np.ndarray
    q_process: np.ndarray
    q_spec_unserved: np.ndarray
    t_process_out: np.ndarray
    f_bypass: np.ndarray
    service_met: np.ndarray
    energy_in: np.ndarray     # accumulative J, integral of actual HP output
    energy_process: np.ndarray
    energy_loss_h: np.ndarray
    energy_loss_b: np.ndarray
    energy_electric: np.ndarray
    energy_residual: np.ndarray


def _rk4_step(state: State, u: float, p: Parameters, d: Disturbance, dt: float):
    # Integrate thermal states, actuator and physical energy terms with SAME RK4 stages.
    def grad(s):
        z,r=rhs(s,u,p,d)
        return np.array((z.th,z.tb,z.n,r.q_hp,r.hx.q_transferred,r.loss_h,r.loss_b,r.p_el),float)
    y=np.array([state.th,state.tb,state.n,0,0,0,0,0],float)
    def state_of(v):return State(*v[:3])
    k1=grad(state_of(y))
    k2=grad(state_of(y+dt*k1/2))
    k3=grad(state_of(y+dt*k2/2))
    k4=grad(state_of(y+dt*k3))
    yn=y+dt*(k1+2*k2+2*k3+k4)/6
    return State(*yn[:3]),yn[3:]


def simulate(p: Parameters, x0: State, schedule: Schedule, duration_s: float=3600.,
             step_s: float=5., control_period_s: float=60.) -> Simulation:
    if step_s<=0 or duration_s<=0 or control_period_s<=0:
        raise ValueError('positive times needed')
    if abs(round(duration_s/step_s)-duration_s/step_s)>1e-9 or abs(round(control_period_s/step_s)-control_period_s/step_s)>1e-9:
        raise ValueError('duration and control period must be integer multiples of integration timestep')
    steps=int(round(duration_s/step_s)); control_steps=int(round(control_period_s/step_s))
    times=np.linspace(0,duration_s,steps+1)
    states=np.zeros((steps+1,3)); states[0]=[x0.th,x0.tb,x0.n]
    commands=np.zeros(steps+1); u_prev=x0.n
    rates=np.zeros((steps+1,6)); service=np.zeros(steps+1,dtype=bool)
    energy=np.zeros((steps+1,5))
    for k,t in enumerate(times):
        # Disturbance evaluated at START of integration interval. At sample points
        # reports right-hand values (post scheduled disturbance change).
        d=schedule.disturbance(float(t))
        x=State(*states[k]); r=output(x,p,d)
        rates[k,:]=[r.q_hp,r.p_el,r.hx.q_transferred,r.hx.q_spec_unserved,
                    r.hx.t_proc_out,r.hx.fraction]
        service[k]=r.hx.qualified
        if k==steps:commands[k]=u_prev; break
        if k%control_steps==0:
            u_requested=float(schedule.feedback(float(t),x,d,u_prev) if schedule.feedback is not None
                              else schedule.command(float(t)))
            u_target=min(p.n_max,max(p.n_min,u_requested))
            u_prev=max(p.n_min,min(p.n_max,u_prev+max(-p.max_command_step,min(p.max_command_step,u_target-u_prev))))
        commands[k]=u_prev
        xf,de=_rk4_step(x,u_prev,p,d,step_s)
        states[k+1]=[xf.th,xf.tb,xf.n]
        energy[k+1]=energy[k]+de
    residual=energy[:,0]-energy[:,1]-energy[:,2]-energy[:,3]-p.c_h*(states[:,0]-states[0,0])-p.c_b*(states[:,1]-states[0,1])
    return Simulation(times,states,commands,*rates.T,service,
                      *energy.T,residual)