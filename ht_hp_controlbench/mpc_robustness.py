"""WP4 controlled synthetic robust-MPC comparison with the WP3 scenario ledger.

Both PI and MPC receive the same *one* sampled noisy/delayed process-temperature
measurement, the same current exogenous disturbances, and the same 120-second
command-update clock. MPC's unmeasured header/modulation states come from its
nominal model predictor, NOT the truth plant. This is a minimal open-loop
observer, not a calibrated or statistically optimal state estimator.

This is a reproducible synthetic sensitivity screen, not robust stability proof.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
import numpy as np
from .core import Parameters, Disturbance, State, equilibrium
from .sim import simulate, Schedule, Simulation
from .pi import PIController, PISettings, metrics
from .robustness import RobustnessCase
from .mpc import MPCConfig, MPCController, _advance


@dataclass
class RobustMPCResult:
    case: RobustnessCase
    method: str
    sim: Simulation
    target: np.ndarray
    sensor_times: np.ndarray
    sensor_buffer: np.ndarray
    sensor_truth: np.ndarray
    estimated_states: np.ndarray
    sensor_period_s: float
    controller_period_s: float
    fallback_events: int
    statuses: dict[str, int]
    accepted_solutions: int
    total_decisions: int
    solver_backend: str
    info_mode: str

    def summary(self) -> dict:
        dt=self.sim.times[1]-self.sim.times[0]
        m=metrics(self.sim,self.target,self.controller_period_s)
        u=self.sim.commands[::int(round(self.controller_period_s/dt))]
        result={
            'case':self.case.name, 'method':self.method,
            'sensor_noise_sd_K':self.case.noise_sd_k,
            'sensor_delay_s':int(self.case.delay_updates*self.sensor_period_s),
            'seed':self.case.seed, 'solver':self.solver_backend,
            'information_mode':self.info_mode,
            'decisions':self.total_decisions,
            'accepted_mpc':self.accepted_solutions,
            'pi_fallbacks':self.fallback_events,
            'fallback_fraction':self.fallback_events/max(1,self.total_decisions),
            'status_counts':self.statuses,
            'command_variation':float(np.sum(np.abs(np.diff(u)))),
            'sample_fraction_at_command_bounds':float(np.mean(
                np.isclose(u,self.case.plant.n_min,atol=1e-4) |
                np.isclose(u,self.case.plant.n_max,atol=1e-4))),
            'service_qualified_fraction':float(np.mean(self.sim.service_met)),
            'finite':bool(np.all(np.isfinite(self.sim.states)) and np.all(np.isfinite(u))),
        }
        required = np.where(self.sim.times < 3600.,
                self.case.plant.c_proc*max(0,self.case.plant.t_required-self.case.initial_return_k),
                self.case.plant.c_proc*max(0,self.case.plant.t_required-self.case.return_after_step_k))
        result['physical_energy_shortfall_kWh']=float(np.trapezoid(
            np.maximum(required-self.sim.q_process,0),x=self.sim.times)/3_600_000)
        result.update(m)
        # With direct sample correction, estimated Tb intentionally equals the
        # delayed/noisy sensed Tb; measure errors in unmeasured physical states.
        true_at_decisions=self.sim.states[::int(round(self.controller_period_s/dt))][:len(self.estimated_states)]
        result['max_estimation_header_error_K']=float(np.max(np.abs(
            self.estimated_states[:,0]-true_at_decisions[:,0])))
        result['max_estimation_modulation_error']=float(np.max(np.abs(
            self.estimated_states[:,2]-true_at_decisions[:,2])))
        return result


def run_robust_mpc_case(
    nominal:Parameters, case:RobustnessCase, *, method:str,
    pi_settings:PISettings, cfg:MPCConfig|None=None,
    duration_s:float=14_400., integration_step_s:float=10.,
    sensor_period_s:float=60., control_period_s:float=120.,
    setpoint_step_k:float=0.4,
    # Requires explicit opt-in for the additional *future* disturbance information.
    advance_forecast:bool=False,
    ) -> RobustMPCResult:
    """Run a case without retuning PI or adapting nominal plant parameters.

    Measurement delay is defined in seconds, not MPC-update counts. The sensor
    samples each 60s; controls update at 120s, all from the exact same FIFO.
    Unmeasured states are purely propagated by a nominal-model predictor. No
    true header/modulation data are passed to MPC after initialization.
    """
    if cfg is None:cfg=MPCConfig(horizon=6)
    if method not in ('imc_pi','relay_pi','mpc'):
        raise ValueError('unknown method')
    if abs(control_period_s/cfg.period_s-1)>1e-9:
        raise ValueError('MPC period must match control-update period')
    if abs(control_period_s/sensor_period_s-round(control_period_s/sensor_period_s))>1e-9:
        raise ValueError('sensor period must divide control period')
    if abs(sensor_period_s/integration_step_s-round(sensor_period_s/integration_step_s))>1e-9:
        raise ValueError('integration step must divide sensor period')
    if duration_s<3600. or abs(duration_s/control_period_s-round(duration_s/control_period_s))>1e-9:
        raise ValueError('duration must contain whole controller updates')
    x0,u0,_=equilibrium(nominal)
    target_base=x0.tb+setpoint_step_k
    pi=PIController(pi_settings,target_base,u0,control_period_s)
    ctrl=MPCController(nominal,cfg,target_base,pi_settings,u0) if method=='mpc' else None
    rng=np.random.default_rng(case.seed)
    # No current-model parameter disclosure when plant changes.
    estimator=x0
    last_t=0.
    prev_d=Disturbance(t_return=case.initial_return_k)
    delayed=[x0.tb]*case.delay_updates
    sensed_trace=[];times_trace=[];truth_trace=[];estimated_trace=[]

    def disturb(t:float)->Disturbance:
        return Disturbance(
            t_return=case.initial_return_k if t<3600. else case.return_after_step_k,
            t_source=333.15 if t<7200. else case.source_after_step_k)

    def feedback(t:float,x:State,d:Disturbance,previous:float)->float:
        nonlocal estimator,last_t,prev_d
        if t>last_t:
            # Propagate the unmeasured states from LAST available estimate using
            # the applied input; do not read truth x.th or x.n here.
            estimator=_advance(estimator,previous,nominal,prev_d,
                               t-last_t,integration_step_s)
        # Project harmless floating-point drift to the known physical
        # compressor-modulation interval, without using plant truth.
        estimator=State(estimator.th,estimator.tb,
                        float(np.clip(estimator.n,nominal.n_min,nominal.n_max)))
        observation=x.tb+rng.normal(0,case.noise_sd_k)
        delayed.append(float(observation))
        seen=float(delayed.pop(0))
        estimator=State(estimator.th,seen,estimator.n)
        times_trace.append(t)
        sensed_trace.append(seen)
        truth_trace.append(x.tb)
        last_t=t
        prev_d=d
        if not (int(round(t/sensor_period_s)) % int(round(control_period_s/sensor_period_s))==0):
            return previous
        if case.excursion_setpoint_k>0 and case.excursion_start_s<=t<case.excursion_end_s:
            target=target_base+case.excursion_setpoint_k
        else:
            target=target_base
        estimated_trace.append((estimator.th,estimator.tb,estimator.n))
        if method=='mpc':
            ctrl.setpoint_k=target
            if advance_forecast:
                ctrl.disturbance_forecast=lambda future,current:disturb(future)
            return ctrl.command(t,estimator,d,previous,case.plant)
        pi.setpoint_k=target
        return pi.command(t,estimator,d,previous,case.plant)

    run=simulate(case.plant,x0,Schedule(lambda t:u0,disturb,feedback),
                 duration_s,integration_step_s,sensor_period_s)
    target=np.full_like(run.times,target_base)
    if case.excursion_setpoint_k>0:
        mask=(run.times>=case.excursion_start_s)&(run.times<case.excursion_end_s)
        target[mask]+=case.excursion_setpoint_k
    statuses={}
    if ctrl is not None:
        for s in ctrl.decisions:statuses[s.status]=statuses.get(s.status,0)+1
    return RobustMPCResult(case,method,run,target,
        np.asarray(times_trace),np.asarray(sensed_trace),np.asarray(truth_trace),
        np.asarray(estimated_trace,float).reshape(-1,3),
        sensor_period_s,control_period_s,
        ctrl.fallback_events if ctrl else 0,statuses,
        sum(s.accepted for s in ctrl.decisions) if ctrl else 0,
        len(ctrl.decisions) if ctrl else int(round(duration_s/control_period_s)),
        cfg.solver_backend if ctrl else 'none',
        'one delayed/noisy buffer-temperature measurement + nominal-model observer'
    )