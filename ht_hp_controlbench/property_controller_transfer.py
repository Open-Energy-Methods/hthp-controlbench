"""Matched PI/MPC transfer pilot on an explicitly uncalibrated WP7 property truth.

The MPC predictor remains WP2 synthetic; the TRUTH plant uses WP7 CoolProp Q/P
map and IF97 buffer enthalpy. This is an out-of-model controller-transfer test,
not property-model-based MPC design, hardware verification or robust stability.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Callable
import numpy as np

from .core import Disturbance, Parameters, State, heat_exchanger
from .mpc import MPCConfig, MPCController, _advance
from .pi import PIController, PISettings
from .realfluid import CycleMap, PointRejected, _prop, coolprop_backend, water_loop_state
from .storage_flexibility import _stage
from .thermo_feasibility import hold_service_at_buffer


@dataclass(frozen=True)
class PropertyTransferCase:
    name: str
    source_step_k: float = 0.
    return_step_k: float = 0.
    sensor_noise_sd_k: float = 0.
    sensor_delay_samples: int = 0
    seed: int = 11

    def __post_init__(self):
        if not self.name or self.sensor_delay_samples < 0 or self.seed < 0:
            raise ValueError("invalid case name, delay or seed")
        if not all(isfinite(v) for v in (
                self.source_step_k, self.return_step_k, self.sensor_noise_sd_k)):
            raise ValueError("non-finite transfer scenario")
        if self.sensor_noise_sd_k < 0:
            raise ValueError("sensor noise must be nonnegative")


TRANSFER_CASES = (
    PropertyTransferCase("nominal"),
    PropertyTransferCase("source_drop_1K", source_step_k=-1.),
    PropertyTransferCase("return_rise_1K", return_step_k=1.),
    PropertyTransferCase("noise_0p1K_seed23", sensor_noise_sd_k=0.1, seed=23),
    PropertyTransferCase("delay_60s", sensor_delay_samples=1),
)


def run_transfer(model: CycleMap, method: str, case: PropertyTransferCase,
                 settings: PISettings, *, props=None,
                 p: Parameters | None = None, cfg: MPCConfig | None = None,
                 duration_s: float = 3600., dt_s: float = 20.,
                 sensor_period_s: float = 60.,
                 buffer_initial_k: float = 403.15,
                 setpoint_step_k: float = 0.4) -> dict:
    """Run matched scenario on the WP7 truth plant with a one-sensor budget.

    Both controllers get only noisy/delayed buffer temperature, current
    source/return conditions and applied command. MPC unmeasured states are
    propagated with the fixed WP2 nominal model; true header/modulation values
    are logged for post-hoc observer diagnostics ONLY, never sent to MPC.
    The true plant is the common WP7 enthalpy model for both methods.
    """
    if method not in ("pi", "mpc"):
        raise ValueError("method must be pi or mpc")
    cfg = cfg or MPCConfig(horizon=3, period_s=120., integration_step_s=20.)
    if cfg.solver_backend not in ("slsqp", "osqp"):
        raise ValueError("unknown solver")
    if min(duration_s, dt_s, sensor_period_s) <= 0:
        raise ValueError("time intervals must be positive")
    for ratio in (duration_s/dt_s, sensor_period_s/dt_s,
                  cfg.period_s/dt_s, cfg.period_s/sensor_period_s):
        if abs(ratio-round(ratio)) > 1e-8:
            raise ValueError("plant, observation and control clocks must align")
    if duration_s < 2*cfg.period_s:
        raise ValueError("pilot requires at least two controller intervals")
    p = p or replace(Parameters(hx_mode="duty_limiter"), n_min=model.modulations[0],
                     n_max=model.modulations[-1])
    if (p.n_min != model.modulations[0] or
            p.n_max != model.modulations[-1]):
        raise ValueError("predictor/actuator must share WP7 map modulation bounds")
    props = props if props is not None else coolprop_backend()
    pressure = model.assumptions.service_header_pressure_pa
    d0 = Disturbance()
    init = hold_service_at_buffer(buffer_initial_k, model, p, d0, props=props)
    if not init["status"].startswith("same_service_property_feasible"):
        raise PointRejected("no_valid_common_property_plant_initial_condition: " + init["status"])
    th0=float(init["t_header_k"])
    n0=float(init["required_modulation"])
    h0=float(_prop(props,"H","IF97::Water","T",buffer_initial_k,"P",pressure))
    y=np.array([th0,h0,n0,0.,0.,0.,0.,0.],float)
    u=n0
    target=buffer_initial_k+setpoint_step_k
    predictor=p  # fixed uncalibrated WP2 predictor: deliberately NOT property backed
    pi=PIController(settings,target,n0,cfg.period_s)
    mpc=(MPCController(predictor,cfg,target,settings,n0) if method=="mpc" else None)
    observer=State(th0,buffer_initial_k,n0)  # known matching INITIAL state only
    last_sensor_t=0.
    last_disturbance=d0
    last_observer_command=u
    delay_fifo=[buffer_initial_k]*case.sensor_delay_samples
    rng=np.random.default_rng(case.seed)
    sensor_innovations=[]
    observer_header_errors=[]
    observer_modulation_errors=[]
    times=[]
    applied=[]
    states=[]
    service_steps=0
    unserved_j=0.
    iae=0.
    completed=0
    failure=None
    step_count=int(round(duration_s/dt_s))
    sensor_stride=int(round(sensor_period_s/dt_s))
    controller_stride=int(round(cfg.period_s/dt_s))

    def disturb(t):
        step=t >= duration_s/2.
        return Disturbance(t_source=d0.t_source+(case.source_step_k if step else 0.),
                           t_return=d0.t_return+(case.return_step_k if step else 0.))

    def water_temp(h):
        return float(_prop(props,"T","IF97::Water","P",pressure,"H",float(h)))

    for k in range(step_count):
        t=k*dt_s
        d=disturb(t)
        try:
            tb=water_temp(y[1])
            hx=heat_exchanger(tb,p,d)
            if k%sensor_stride == 0:
                if t>last_sensor_t:
                    # The observer may use only earlier applied input and known
                    # disturbance; no true th/n is passed after initialization.
                    observer=_advance(observer,last_observer_command,predictor,
                                      last_disturbance,t-last_sensor_t,dt_s)
                n_observed=float(np.clip(observer.n,p.n_min,p.n_max))
                noise=float(rng.normal(0.,case.sensor_noise_sd_k))
                sensor_innovations.append(noise)
                delay_fifo.append(tb+noise)
                sensed=float(delay_fifo.pop(0))
                observer=State(observer.th,sensed,n_observed)
                last_sensor_t=t
                last_disturbance=d
                last_observer_command=u
                if k%controller_stride == 0:
                    # Physical truth is only used in offline error diagnostics.
                    observer_header_errors.append(abs(observer.th-float(y[0])))
                    observer_modulation_errors.append(abs(observer.n-float(y[2])))
                    desired=(mpc.command(t,observer,d,u,p) if mpc is not None
                             else pi.command(t,observer,d,u,p))
                    bounded=float(np.clip(desired,p.n_min,p.n_max))
                    u=float(np.clip(bounded,u-p.max_command_step,u+p.max_command_step))
            k1=_stage(y,u,model,5000.,p,d,props)
            k2=_stage(y+dt_s*k1/2,u,model,5000.,p,d,props)
            k3=_stage(y+dt_s*k2/2,u,model,5000.,p,d,props)
            k4=_stage(y+dt_s*k3,u,model,5000.,p,d,props)
            candidate=y+dt_s*(k1+2*k2+2*k3+k4)/6.
            # Fail CLOSED: confirm every newly accepted state is inside the
            # water phase and property Q/P map, not only the RK4 substages.
            next_tb=water_temp(candidate[1])
            water_loop_state(max(float(candidate[0]),next_tb),model.assumptions,props)
            model.evaluate(float(candidate[2]),d.t_source,float(candidate[0]))
            if not np.all(np.isfinite(candidate)):
                raise PointRejected("nonfinite_property_truth_state")
            # Commit only accepted steps and their physical-service evidence.
            y=candidate
            completed+=1
            service_steps+=int(hx.qualified)
            unserved_j+=hx.q_spec_unserved*dt_s
            iae+=abs(tb-target)*dt_s
            times.append(t)
            applied.append(u)
            states.append((float(y[0]),next_tb,float(y[2])))
        except (ValueError,RuntimeError,FloatingPointError,OverflowError,PointRejected) as exc:
            failure=type(exc).__name__+": "+str(exc)
            break

    decision_count=len(mpc.decisions) if mpc is not None else int(np.ceil(completed*dt_s/cfg.period_s))
    status_counts={}
    if mpc is not None:
        for decision in mpc.decisions:
            status_counts[decision.status]=status_counts.get(decision.status,0)+1
    inventory_j=p.c_h*(y[0]-th0)+5000.*(y[1]-h0)
    flows_j=y[3]-y[5]-y[6]-y[7]
    return {
        "case":case.name, "method":method,
        "status":"complete" if completed==step_count and failure is None else "rejected_property_envelope",
        "error":failure, "completed_steps":completed,"requested_steps":step_count,
        "duration_s":duration_s,"dt_s":dt_s,"sensor_period_s":sensor_period_s,
        "control_period_s":cfg.period_s, "noise_sd_K":case.sensor_noise_sd_k,
        "sensor_delay_s":case.sensor_delay_samples*sensor_period_s,"seed":case.seed,
        "information_mode":"one delayed/noisy buffer sensor; WP2 nominal observer; current exogenous disturbances",
        "truth":"WP7 Q/P property map and IF97 enthalpy; hardware map assumed, not measured",
        "predictor":"WP2 synthetic model; intentionally out of model; NOT WP7-optimized MPC",
        "iae_Ks":float(iae) if completed==step_count else None,
        "electrical_kWh":float(y[4]/3.6e6) if completed==step_count else None,
        "physical_process_heat_kWh":float(y[5]/3.6e6) if completed==step_count else None,
        "service_qualified_fraction":service_steps/step_count,
        "spec_unserved_kWh":float(unserved_j/3.6e6),
        "energy_residual_J":float(inventory_j-flows_j),
        "pi_fallback_events":mpc.fallback_events if mpc is not None else 0,
        "mpc_accepted":sum(int(q.accepted) for q in mpc.decisions) if mpc is not None else 0,
        "controller_decisions":decision_count,
        "mpc_status_counts":status_counts,
        "max_estimated_header_error_K":max(observer_header_errors,default=None),
        "max_estimated_modulation_error":max(observer_modulation_errors,default=None),
        "noise_draws_K":sensor_innovations,
        "initial_modulation":n0,
        "final_modulation":float(y[2]),
        "equipment_verified":False,
        "trace":states,
        "control_trace":applied,
        "times_s":times,
    }


def matched_transfer_pilot(model: CycleMap, settings: PISettings, *, props=None,
                           cases: tuple[PropertyTransferCase,...]=TRANSFER_CASES,
                           duration_s:float=3600., dt_s:float=20.,
                           cfg:MPCConfig|None=None) -> dict:
    """Matched scenarios; preserve all failed runs and do not force a winner."""
    cfg=cfg or MPCConfig(horizon=3,period_s=120.,integration_step_s=20.)
    props=props if props is not None else coolprop_backend()
    rows=[]
    pairs=[]
    for case in cases:
        group=[]
        for method in ("pi","mpc"):
            r=run_transfer(model,method,case,settings,props=props,
                           duration_s=duration_s,dt_s=dt_s,cfg=cfg)
            rows.append(r);group.append(r)
        pi,mpc=group
        eligible=all(r["status"]=="complete" and
                     r["service_qualified_fraction"]==1. and
                     r["spec_unserved_kWh"]<=1e-6 for r in group)
        pairs.append({
            "case":case.name,
            "both_complete":all(r["status"]=="complete" for r in group),
            "both_service_qualified":eligible,
            "delta_iae_mpc_minus_pi_Ks":(
                mpc["iae_Ks"]-pi["iae_Ks"] if eligible else None),
            "delta_electricity_mpc_minus_pi_kWh":(
                mpc["electrical_kWh"]-pi["electrical_kWh"] if eligible else None),
            "qualified_winner":(
                min(group,key=lambda r:r["iae_Ks"])["method"] if eligible else None),
            "comparison_status":"conditional_synthetic_property_transfer" if eligible
                                else "not_comparable_due_to_failure_or_service",
        })
    return {"status":"research_pilot_not_equipment_validated",
            "truth_model":"WP7 property map: uncalibrated compressor assumptions",
            "controller_design_model":"WP2 synthetic predictor fixed on nominal",
            "cases":len(cases),"runs":rows,"paired":pairs,
            "warnings":["Not property-model-based MPC","No source/sink finite-flow verification",
                        "No OEM compressor map or robust stability proof",
                        "No economic savings inference from differing service states"]}
