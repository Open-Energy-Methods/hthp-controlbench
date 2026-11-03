"""WP3 synthetic PI-controller identification, relay-tuning and bounded closed-loop tests.

This is a simulation baseline, NOT hardware PID tuning or a validated heat pump.
Gains use dimensionless compressor command per kelvin and per kelvin-second.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import log, pi, isfinite
import numpy as np

from .core import Parameters, State, Disturbance, equilibrium
from .sim import Schedule, Simulation, simulate, _rk4_step


@dataclass(frozen=True)
class PISettings:
    kp: float  # command fraction / K
    ki: float  # command fraction / (K s)
    source: str
    tracking_time_s: float = 360.0

    def __post_init__(self):
        if not (self.kp > 0 and self.ki > 0 and self.tracking_time_s > 0):
            raise ValueError('PI settings must be strictly positive')
        if not all(map(isfinite, (self.kp, self.ki, self.tracking_time_s))):
            raise ValueError('non-finite PI settings')


@dataclass(frozen=True)
class StepIdentification:
    gain_k_per_u: float
    tau_s: float
    delay_s: float
    t28_s: float
    t63_s: float
    delta_command: float
    last_slope_k: float


@dataclass(frozen=True)
class RelayIdentification:
    ultimate_gain_u_per_k: float
    period_s: float
    temperature_amplitude_k: float
    relay_amplitude_u: float
    observed_cycles: int


@dataclass
class PIController:
    settings: PISettings
    setpoint_k: float
    bias_command: float
    period_s: float
    integral_command: float = 0.0
    initialized: bool = False
    last_raw_command: float = 0.0
    last_applied_command: float = 0.0
    saturation_events: int = 0
    slew_events: int = 0

    def command(self, t: float, x: State, d: Disturbance, previous_command: float,
                p: Parameters) -> float:
        """One sample: bumpless initialization, slew-limited actuation and back-calculation.

        Uses the ACTUALLY applied command to back-calculate integrator state;
        Schedule/simulate enforces the same hard bounds as a second guard.
        """
        error = self.setpoint_k - x.tb
        if not self.initialized:
            self.integral_command = previous_command - self.bias_command - self.settings.kp * error
            self.initialized = True
        raw = self.bias_command + self.settings.kp * error + self.integral_command
        bounded = min(p.n_max, max(p.n_min, raw))
        applied = min(previous_command + p.max_command_step,
                      max(previous_command - p.max_command_step, bounded))
        applied = min(p.n_max, max(p.n_min, applied))
        if abs(raw-bounded) > 1e-12:
            self.saturation_events += 1
        if abs(bounded-applied) > 1e-12:
            self.slew_events += 1
        # Back-calculation tracks BOTH magnitude and slew saturation, preventing windup.
        self.integral_command += self.settings.ki * self.period_s * error \
            + (self.period_s / self.settings.tracking_time_s) * (applied - raw)
        self.last_raw_command = raw
        self.last_applied_command = applied
        return applied


def _crossing(times: np.ndarray, ys: np.ndarray, target: float) -> float:
    idx=int(np.searchsorted(ys,target))
    if not 0 < idx < len(ys):
        raise ValueError('step response has no target crossing')
    fraction=(target-ys[idx-1])/(ys[idx]-ys[idx-1])
    return float(times[idx-1]+fraction*(times[idx]-times[idx-1]))


def identify_step(p: Parameters, delta_u: float=0.025, duration_s: float=30_000.,
                  integration_step_s: float=10.) -> StepIdentification:
    """Finite-step FOPDT fit using t28.3/t63.2, only if plateau is observed.

    For the initial WP3 reference, a passive/no-bypass exchanger is required;
    the bypass-limited plant can be far slower and is separately tested.
    """
    if p.hx_mode != 'no_bypass':
        raise ValueError('initial FOPDT tuning restricted to no_bypass baseline')
    x0,u0,_=equilibrium(p)
    if not (0 < delta_u <= p.max_command_step and u0+delta_u<=p.n_max):
        raise ValueError('step command outside hard limits')
    sim=simulate(p,x0,Schedule(lambda t:u0+delta_u,lambda t:Disturbance()),
                 duration_s=duration_s,step_s=integration_step_s,control_period_s=60.)
    yy=sim.states[:,1]-x0.tb
    change=float(yy[-1])
    slope=float(yy[-1]-yy[int(len(yy)*0.90)])
    if change <= 0 or slope > 0.01*change or np.any(np.diff(yy)<-1e-7):
        raise ValueError('step experiment did not reach a monotone near-steady plateau')
    t28=_crossing(sim.times,yy,change*0.283)
    t63=_crossing(sim.times,yy,change*0.632)
    a=-log(1.0-0.283); b=-log(1.0-0.632)
    tau=(t63-t28)/(b-a)
    delay=max(0.,t28-a*tau)
    return StepIdentification(change/delta_u,tau,delay,t28,t63,delta_u,slope)


def tune_imc(result: StepIdentification, closed_loop_factor: float=2.0) -> PISettings:
    """Conservative lambda/IMC FOPDT PI: Kc=tau/[K(lambda+theta)], Ti=tau+theta/2.

    lambda = factor*tau; units of controller gains documented at module level.
    """
    if closed_loop_factor <= 0:
        raise ValueError('positive lambda factor required')
    tau,theta,k=result.tau_s,result.delay_s,result.gain_k_per_u
    lam=closed_loop_factor*tau
    kp=tau/(k*(lam+theta))
    ti=tau+theta/2
    return PISettings(kp,kp/ti,source='FOPDT/IMC lambda=%.1f tau'%closed_loop_factor,
                      tracking_time_s=360.)


def identify_relay(p: Parameters, amplitude_u: float=0.045,
                   hysteresis_k: float=0.04, run_s: float=16000.,
                   step_s: float=10., sample_s: float=30.) -> RelayIdentification:
    """Symmetric-relay describing-function approximation with hysteresis.

    Uses actual oscillations of the independent nonlinear plant, not its FOPDT fit.
    The Ku estimate is approximate because finite relay hysteresis/actuator lag
    and the control sample interval affect the limit cycle.
    """
    if p.hx_mode != 'no_bypass':
        raise ValueError('relay tuning restricted to passive reference case')
    if min(amplitude_u,hysteresis_k,run_s,step_s,sample_s)<=0:
        raise ValueError('positive relay experiment parameters required')
    if abs(round(sample_s/step_s)-sample_s/step_s)>1e-9:
        raise ValueError('relay sample must be multiple of integration step')
    x,u0,_=equilibrium(p)
    setpoint=x.tb
    if amplitude_u>p.max_command_step or u0-amplitude_u<p.n_min or u0+amplitude_u>p.n_max:
        raise ValueError('relay command would violate actuator limits')
    state=1
    high_times=[]; low_times=[]
    # Track the *actual* process excursions, not the values sampled at the
    # hysteresis thresholds where the relay changes sign. A full high-to-high
    # period includes both a maximum and a minimum after actuation dynamics.
    trajectory_time=[]; trajectory_error=[]
    steps=int(round(run_s/step_s)); ns=int(round(sample_s/step_s))
    for k in range(steps):
        e=x.tb-setpoint
        trajectory_time.append(k*step_s)
        trajectory_error.append(e)
        if k%ns==0:
            if state==1 and e>=hysteresis_k:
                high_times.append(k*step_s)
                state=-1
            elif state==-1 and e<=-hysteresis_k:
                low_times.append(k*step_s)
                state=1
        x,_=_rk4_step(x,u0+state*amplitude_u,p,Disturbance(),step_s)
    if len(high_times)<6 or len(low_times)<6:
        raise ValueError('too few relay cycles to identify ultimate period')
    periods=np.diff(high_times[-6:]); period=float(np.mean(periods))
    if np.std(periods)>0.05*period:
        raise ValueError('relay oscillation has not reached stationary period')
    trace_t=np.asarray(trajectory_time, dtype=float)
    trace_e=np.asarray(trajectory_error, dtype=float)
    # Use the last five *complete* high-to-high periods. The relay may switch
    # after crossing a threshold, so switch values are systematically smaller
    # than true peaks and must never be used for the describing-function gain.
    amplitudes=[]
    for t_start,t_end in zip(high_times[-6:-1],high_times[-5:]):
        within=(trace_t>=t_start)&(trace_t<t_end)
        cycle=trace_e[within]
        if len(cycle)<4:
            raise ValueError('relay period underresolved by integration step')
        amplitudes.append(0.5*(float(np.max(cycle))-float(np.min(cycle))))
    a=float(np.mean(amplitudes))
    if not np.isfinite(a) or a<=hysteresis_k:
        raise ValueError('relay limit cycle insufficiently resolved beyond hysteresis')
    if float(np.std(amplitudes))>0.05*a:
        raise ValueError('relay amplitude has not reached stationary period')
    # Finite hysteresis and compressor lag mean Ku is an approximate describing-
    # function estimate, NOT a certified stability margin or a hardware tune.
    ku=4*amplitude_u/(pi*a)
    return RelayIdentification(ku,period,a,amplitude_u,min(len(high_times),len(low_times)))


def tune_relay_tyreus_luyben(result: RelayIdentification) -> PISettings:
    """Conservative Tyreus-Luyben PI, Kp=Ku/3.2, Ti=2.2 Pu."""
    kp=result.ultimate_gain_u_per_k/3.2
    ki=kp/(2.2*result.period_s)
    return PISettings(kp,ki,'relay/approx. Tyreus-Luyben',tracking_time_s=360.)


def closed_loop(p: Parameters, settings: PISettings, duration_s: float=14_400.,
                step_s: float=10., period_s: float=60., setpoint_step_k: float=0.4,
                return_step_s: float=3600., source_step_s: float=7200.) -> tuple[Simulation,PIController,np.ndarray]:
    """Same scheduled disturbances / integration for every candidate PI tuning.

    Service reporting is independent of controller tracking. The process-return
    disturbance changes duty consistently at fixed process flow.
    """
    x0,u0,_=equilibrium(p)
    ctrl=PIController(settings,x0.tb+setpoint_step_k,u0,period_s)
    def disturbances(t):
        return Disturbance(t_return=363.15 if t<return_step_s else 365.15,
                           t_source=333.15 if t<source_step_s else 328.15)
    sched=Schedule(command=lambda t:u0,disturbance=disturbances,
                   feedback=lambda t,x,d,last:ctrl.command(t,x,d,last,p))
    result=simulate(p,x0,sched,duration_s=duration_s,step_s=step_s,control_period_s=period_s)
    target=np.full_like(result.times,ctrl.setpoint_k)
    return result,ctrl,target


def metrics(sim: Simulation, target: np.ndarray, control_period_s:float=60.) -> dict[str,float]:
    dt=float(sim.times[1]-sim.times[0])
    error=target-sim.states[:,1]
    return {
        'iae_Ks':float(np.trapezoid(np.abs(error),dx=dt)),
        'rmse_K':float(np.sqrt(np.mean(error**2))),
        'max_abs_error_K':float(np.max(abs(error))),
        'service_unserved_kWh':float(np.trapezoid(sim.q_spec_unserved,dx=dt)/3_600_000),
        'electrical_kWh':float(sim.energy_electric[-1]/3_600_000),
        'max_energy_residual_J':float(np.max(np.abs(sim.energy_residual))),
        'max_command_slew':float(np.max(abs(np.diff(sim.commands[::int(round(control_period_s/dt))])))),
    }
