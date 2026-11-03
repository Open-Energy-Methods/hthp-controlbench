"""WP8: temperature-qualified, finite-enthalpy HTHP thermal storage and tariff experiments.

Synthetic tariff and compressor displacement/eta/UA; CoolProp IF97 water enthalpy.
Neither an industrial equipment rating nor an SOC controller. Existing WP2-WP7
implementations remain frozen. All costs EUR; prices EUR/kWh, rates W, time s.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Callable
import numpy as np

from .core import Parameters, Disturbance, State, heat_exchanger
from .pi import PIController, PISettings
from .realfluid import CycleMap, PointRejected, _prop, coolprop_backend, cycle_point, water_loop_state
from .thermo_feasibility import (HypotheticalEquipmentLimits, hold_service_at_buffer,
                                 max_speed_charge_point, hypothetical_machine_checks)

# Mathematically identical PI coefficients to the WP3 frozen IMC-0.5tau reference.
WP3_IMC = PISettings(0.03842421355656901, 1.2387208598348781e-5,
                     'WP3_FOPDT_IMC_0p5tau_fixed')


@dataclass(frozen=True)
class SyntheticTariff:
    """Synthetic day: 00-04 medium; 04-06 low; 06-06:15 high; 06:15-24 medium.

    The short high-price event is intentional given the small thermal inventory.
    All switches are exact multiples of the simulation step; no real-world spot
    price, taxes, grid tariffs, timezone, bidding zone or DST is implied.
    """
    low_start_h: float = 4.0
    high_start_h: float = 6.0
    high_end_h: float = 6.25
    low_eur_kwh: float = 0.06
    high_eur_kwh: float = 0.40
    regular_eur_kwh: float = 0.16
    def __post_init__(self):
        if not (0 <= self.low_start_h < self.high_start_h < self.high_end_h <= 24):
            raise ValueError('tariff intervals must be increasing within 24h')
        if not all(isfinite(x) and x >= 0 for x in
                   (self.low_eur_kwh, self.high_eur_kwh, self.regular_eur_kwh)):
            raise ValueError('finite nonnegative tariffs required')
    def price(self, t_s: float) -> float:
        h=t_s/3600
        if self.low_start_h<=h<self.high_start_h:return self.low_eur_kwh
        if self.high_start_h<=h<self.high_end_h:return self.high_eur_kwh
        return self.regular_eur_kwh


@dataclass(frozen=True)
class FlexSettings:
    mass_kg: float = 5000.0
    initial_buffer_k: float = 403.15
    nominal_buffer_k: float = 403.15
    charge_target_k: float = 407.15  # illustrative 134C; NOT guaranteed reachable
    discharge_target_k: float = 401.95 # illustrative 128.8C; service guard is independent
    duration_s: float = 86400.0
    dt_s: float = 20.0
    control_period_s: float = 120.0
    model_verified: bool = False
    def __post_init__(self):
        if self.mass_kg<=0 or self.dt_s<=0 or self.control_period_s<=0 or self.duration_s<=0:
            raise ValueError('positive mass, time step and horizon required')
        if not (self.discharge_target_k < self.nominal_buffer_k < self.charge_target_k):
            raise ValueError('require ordered discharge, nominal and charge targets')
        if any(abs(round(x/self.dt_s)-x/self.dt_s)>1e-8 for x in
               (self.duration_s,self.control_period_s)):
            raise ValueError('duration and control period must align with time step')
        if self.duration_s!=86400:
            raise ValueError('WP8 24-hour tariff experiment requires 86400 s')


def physical_threshold(p:Parameters|None=None, d:Disturbance|None=None) -> float:
    p=p or Parameters(hx_mode='duty_limiter');d=d or Disturbance()
    threshold=heat_exchanger(403.15,p,d).t_b_min_service
    if threshold is None or not isfinite(threshold):raise PointRejected('no_valid_service_temperature_threshold')
    return threshold


def scan_reachable_band(model:CycleMap, mass_kg:float=5000.,
                        proposed_upper_k:float=408.15, nodes:int=31,
                        p:Parameters|None=None,d:Disturbance|None=None,
                        limits:HypotheticalEquipmentLimits|None=None,
                        props=None)->dict:
    """Scan full charge path: not just a single upper-temperature property point.

    The lower endpoint is finite-flow service T+0.02K, not 120C.
    A valid upper must have positive n=1 charging surplus at every sampled point,
    liquid water under loop pressure and no provided illustrative limit breaches.
    *Equipment validation remains false even if every computed sample passes*.
    """
    if nodes<3 or mass_kg<=0:raise ValueError('nodes>=3 and mass>0')
    p=p or Parameters(hx_mode='duty_limiter');d=d or Disturbance()
    props=props if props is not None else coolprop_backend()
    low=physical_threshold(p,d)+0.02
    if proposed_upper_k<=low:raise ValueError('proposed upper must exceed service threshold')
    samples=[];last=low;reason=''
    for tb in np.linspace(low,proposed_upper_k,nodes):
        try:
            wp=water_loop_state(float(tb),model.assumptions,props)
            point=max_speed_charge_point(float(tb),model,p,d,limits,props)
            if point['status']!='conditional_charge_surplus__EQUIPMENT_UNVERIFIED':
                reason=point['status'];samples.append(dict(buffer_k=float(tb),status=reason));break
            samples.append(dict(buffer_k=float(tb),status=point['status'],surplus_w=point['surplus_w'],
                                header_k=point['t_header_k'],p_cond_pa=point['p_cond_pa'],
                                discharge_k=point['discharge_k'],water_psat_pa=wp['saturation_pressure_if97_pa']))
            last=float(tb)
        except (PointRejected,ValueError) as exc:
            reason='property_or_map_rejection:'+str(exc);samples.append(dict(buffer_k=float(tb),status=reason));break
    pressure=model.assumptions.service_header_pressure_pa
    hlow=_prop(props,'H','IF97::Water','T',low,'P',pressure)
    hlast=_prop(props,'H','IF97::Water','T',last,'P',pressure)
    energy=max(0.,mass_kg*(hlast-hlow)/3.6e6)
    return dict(status='conditional_full_path__EQUIPMENT_UNVERIFIED' if not reason else 'path_blocked',
                lower_k=low,highest_checked_usable_k=last,proposed_upper_k=proposed_upper_k,
                stopped_reason=reason,enthalpy_kwh=energy,full_path_checked=(not reason),
                max_uninterrupted_full_duty_minutes=energy/300.*60.,
                equipment_verified=False,samples=samples,fluid=model.fluid,
                illustrative_limit_inputs=asdict(limits) if limits else None)


def _limit_status(model:CycleMap,source_k:float,header_k:float,n:float,
                  limits:HypotheticalEquipmentLimits|None, props=None)->list[str]:
    if limits is None:return []
    # In idealized WP7 cycle the pressure and discharge conditions depend on
    # source/header, not modulation; this is explicitly an assumed topology.
    if n < 0.5-1e-9 or n>1+1e-9:return ['modulation_outside_supported_map']
    pt=cycle_point(model.fluid,source_k,header_k,model.assumptions,props)
    return hypothetical_machine_checks(pt,n,model,limits)['failed']


def _stage(y:np.ndarray,u:float,model:CycleMap, mass:float,p:Parameters,
           d:Disturbance, props,limits=None) -> np.ndarray:
    th,hb,n=y[:3]
    if not model.modulations[0]-1e-9<=n<=model.modulations[-1]+1e-9:
        raise PointRejected('compressor_actual_speed_outside_declared_map')
    tb=_prop(props,'T','IF97::Water','P',model.assumptions.service_header_pressure_pa,'H',float(hb))
    if limits is not None and _limit_status(model,d.t_source,th,n,limits,props):
        raise PointRejected('declared_hypothetical_equipment_constraint_failed')
    water_loop_state(max(th,tb),model.assumptions,props)
    qhp,pel,_=model.evaluate(float(n),d.t_source,float(th))
    hx=heat_exchanger(tb,p,d)
    qhb=p.khb*(th-tb)
    lh=p.ua_h*(th-d.t_ambient);lb=p.ua_b*(tb-d.t_ambient)
    return np.array([(qhp-qhb-lh)/p.c_h,
                     (qhb-hx.q_transferred-lb)/mass,
                     (u-n)/p.tau_n,
                     qhp,pel,hx.q_transferred,lh,lb],float)


def _validate_accepted_storage_endpoint(y:np.ndarray,model:CycleMap,
                                        d:Disturbance,props,limits=None)->None:
    """Validate the actual RK4 ACCEPTED endpoint, not just its substages.

    Four physically valid intermediate RK4 stages can produce a weighted
    endpoint outside the refrigerant Q/P interpolation grid, the declared
    liquid water/pressure envelope or the optional hypothetical limits.
    Such a step must not commit state, electricity, tariff cash or service.
    """
    if not np.all(np.isfinite(y)):
        raise PointRejected("nonfinite_storage_accepted_endpoint")
    th,hb,n=map(float,y[:3])
    if not model.modulations[0]-1e-9<=n<=model.modulations[-1]+1e-9:
        raise PointRejected("storage_accepted_modulation_outside_declared_map")
    tb=_prop(props,'T','IF97::Water','P',
             model.assumptions.service_header_pressure_pa,'H',hb)
    water_loop_state(max(th,tb),model.assumptions,props)
    model.evaluate(n,d.t_source,th)
    if limits is not None and _limit_status(model,d.t_source,th,n,limits,props):
        raise PointRejected("storage_accepted_hypothetical_equipment_constraint_failed")


def simulate_24h(model:CycleMap, policy:str='baseline_pi',settings:FlexSettings|None=None,
                 tariff:SyntheticTariff|None=None, props=None,
                 limits:HypotheticalEquipmentLimits|None=None,
                 p:Parameters|None=None,d:Disturbance|None=None,
                 store_trajectory:bool=False)->dict:
    """Nonlinear three-state energy-conserving replay and tariff cost evaluation.

    `tariff_heuristic` is a scheduled setpoint heuristic, not SOC/MPC. It has
    explicitly advance knowledge of low and high event times. No optimization,
    electricity exports, perfect plant foreknowledge, or OEM validation.
    Rejected simulations preserve failure status and cannot earn savings.
    """
    if policy not in ('baseline_pi','tariff_heuristic'):
        raise ValueError('unknown policy')
    cfg=settings or FlexSettings();tariff=tariff or SyntheticTariff()
    if any(abs(round(h*3600/cfg.dt_s)-h*3600/cfg.dt_s)>1e-8 for h in
           (tariff.low_start_h,tariff.high_start_h,tariff.high_end_h)):
        raise ValueError('all tariff switch times must align with simulation step')
    p=p or replace(Parameters(hx_mode='duty_limiter'),n_min=0.5)
    d=d or Disturbance()
    props=props if props is not None else coolprop_backend()
    init=hold_service_at_buffer(cfg.initial_buffer_k,model,p,d,limits,props)
    if not init['status'].startswith('same_service_property_feasible'):
        return dict(status='initial_service_or_equipment_infeasible',reason=init['status'],policy=policy,
                    equipment_verified=False)
    pressure=model.assumptions.service_header_pressure_pa
    h0=_prop(props,'H','IF97::Water','T',cfg.initial_buffer_k,'P',pressure)
    y=np.array([init['t_header_k'],h0,init['required_modulation'],0,0,0,0,0],float)
    n0=y[2];u=float(n0)
    ctrl=PIController(WP3_IMC,cfg.nominal_buffer_k,n0,cfg.control_period_s)
    nsteps=int(round(cfg.duration_s/cfg.dt_s));period_steps=int(round(cfg.control_period_s/cfg.dt_s))
    qual_count=0; unserved_j=0.;steps_ok=0;max_slew=0.;sat_count=0;cash=0.
    price_elec={'low':0.,'high':0.,'regular':0.}
    start=np.array(y[:3]);max_tb=float(cfg.initial_buffer_k);min_tb=float(cfg.initial_buffer_k)
    trajectory=[];violations=[]
    for k in range(nsteps):
        t=k*cfg.dt_s;pr=tariff.price(t)
        try:
            tb=_prop(props,'T','IF97::Water','P',pressure,'H',float(y[1]))
            hx=heat_exchanger(tb,p,d)
            # Sampled service belongs to a completed integration interval only.
            # In particular, a rejected RK4 step must never increase the
            # service numerator while leaving completed_steps unchanged.
            qualified_this_step=int(hx.qualified)
            # This integrated KPI covers completed physical steps ONLY;
            # a truncated future is separately a failure of the 24-hour gate.
            unserved_this_step=max(0.,hx.q_requested-(hx.q_transferred if hx.qualified else 0.))*cfg.dt_s
            max_tb=max(max_tb,tb);min_tb=min(min_tb,tb)
            if k%period_steps==0:
                if policy=='baseline_pi':target=cfg.nominal_buffer_k
                elif tariff.low_start_h*3600<=t<tariff.high_start_h*3600:
                    target=cfg.charge_target_k
                elif tariff.high_start_h*3600<=t<tariff.high_end_h*3600:
                    target=cfg.discharge_target_k
                else:target=cfg.nominal_buffer_k
                ctrl.setpoint_k=target
                raw=ctrl.command(t,State(float(y[0]),tb,float(y[2])),d,u,p)
                nxt=max(model.modulations[0],min(model.modulations[-1],raw))
                nxt=max(u-p.max_command_step,min(u+p.max_command_step,nxt))
                max_slew=max(max_slew,abs(nxt-u))
                sat_count+=int(nxt<=model.modulations[0]+1e-7 or nxt>=model.modulations[-1]-1e-7)
                u=nxt
            k1=_stage(y,u,model,cfg.mass_kg,p,d,props,limits)
            k2=_stage(y+0.5*cfg.dt_s*k1,u,model,cfg.mass_kg,p,d,props,limits)
            k3=_stage(y+0.5*cfg.dt_s*k2,u,model,cfg.mass_kg,p,d,props,limits)
            k4=_stage(y+cfg.dt_s*k3,u,model,cfg.mass_kg,p,d,props,limits)
            increment=cfg.dt_s*(k1+2*k2+2*k3+k4)/6.
            candidate=y+increment
            _validate_accepted_storage_endpoint(candidate,model,d,props,limits)
            # Only a fully accepted RK4 endpoint may add electricity,
            # monetary cost, heat, physical inventory or qualified service.
            y=candidate
            # Price is piecewise constant and aligned to dt.
            e_kwh=increment[4]/3.6e6;cash+=pr*e_kwh
            # Bucket by the declared *time interval*, not floating-point price.
            # Flat or repeated numerical tariff values must retain distinct
            # low/high/regular time-window energy accounting.
            hour=t/3600.
            key=('low' if tariff.low_start_h<=hour<tariff.high_start_h else
                 'high' if tariff.high_start_h<=hour<tariff.high_end_h else 'regular')
            price_elec[key]+=e_kwh
            steps_ok+=1
            qual_count+=qualified_this_step
            unserved_j+=unserved_this_step
            if store_trajectory and (k%period_steps==0 or k==nsteps-1):
                trajectory.append(dict(time_h=t/3600.,buffer_c=tb-273.15,
                                       header_c=float(y[0]-273.15),command=u,n_actual=float(y[2]),
                                       tariff_eur_kwh=pr,service_qualified=hx.qualified,
                                       cumulative_cost_eur=cash))
        except (PointRejected,ValueError,FloatingPointError) as exc:
            violations.append(dict(time_h=t/3600.,reason=str(exc)))
            break
    end_h=float(y[1]);start_h=h0
    energy_deviation_j=p.c_h*(y[0]-start[0])+cfg.mass_kg*(end_h-start_h)-(y[3]-y[5]-y[6]-y[7])
    q_service=max(0.,heat_exchanger(_prop(props,'T','IF97::Water','P',pressure,'H',float(y[1])),p,d).q_requested)
    return dict(policy=policy,status='complete' if not violations and steps_ok==nsteps else 'failed_physical_or_property_constraint',
                completed_steps=steps_ok,steps=nsteps,failures=violations,
                duration_s=cfg.duration_s,
                # Full requested horizon: aborted steps are not qualified.
                service_qualified_fraction=qual_count/max(nsteps,1),
                # Separate conditional diagnostic, never used to claim 24-h success.
                service_qualified_fraction_completed=qual_count/max(steps_ok,1),
                completed_fraction=steps_ok/max(nsteps,1),
                spec_unserved_kwh=unserved_j/3.6e6,service_required_w=q_service,
                electricity_kwh=float(y[4]/3.6e6),condenser_heat_kwh=float(y[3]/3.6e6),
                process_heat_kwh=float(y[5]/3.6e6),loss_heat_kwh=float((y[6]+y[7])/3.6e6),
                cost_eur=float(cash),tariff_bucket_electricity_kwh=price_elec,
                initial_buffer_k=cfg.initial_buffer_k,initial_header_k=float(start[0]),
                final_header_k=float(y[0]),final_buffer_k=float(_prop(props,'T','IF97::Water','P',pressure,'H',end_h)),
                final_storage_delta_kwh=cfg.mass_kg*(end_h-start_h)/3.6e6,
                # Header and buffer are distinct thermal stores. Equal buffer
                # enthalpy alone does not guarantee equal terminal resources.
                final_header_energy_delta_kwh=p.c_h*(y[0]-start[0])/3.6e6,
                final_total_thermal_energy_delta_kwh=(cfg.mass_kg*(end_h-start_h)+
                                                       p.c_h*(y[0]-start[0]))/3.6e6,
                initial_modulation=float(start[2]),final_modulation=float(y[2]),
                final_applied_command=float(u),
                max_buffer_k=max_tb,min_buffer_k=min_tb,
                max_command_slew=max_slew,saturation_updates=sat_count,
                residual_energy_j=float(energy_deviation_j),
                equipment_verified=False,assumed_limits=asdict(limits) if limits else None,
                trajectory=trajectory if store_trajectory else None)


def compare_flexibility(model:CycleMap,settings:FlexSettings|None=None,
                        tariff:SyntheticTariff|None=None,props=None,
                        limits:HypotheticalEquipmentLimits|None=None,
                        p:Parameters|None=None,d:Disturbance|None=None,
                        store_trajectory:bool=False)->dict:
    """Strict gate: matched service, model feasibility and terminal inventory.

    Cost savings are *conditional simulated only* (never equipment-verified).
    Final header and buffer energy inventories AND compressor lag/command must
    be comparable; false savings from unmatched terminal states are rejected.
    A lower electricity bill from missed process duty is expressly not a saving.
    """
    cfg=settings or FlexSettings();tariff=tariff or SyntheticTariff()
    props=props if props is not None else coolprop_backend()
    base=simulate_24h(model,'baseline_pi',cfg,tariff,props,limits,p,d,store_trajectory)
    flex=simulate_24h(model,'tariff_heuristic',cfg,tariff,props,limits,p,d,store_trajectory)
    reasons=[]
    if base['status']!='complete' or flex['status']!='complete':reasons.append('simulation_or_envelope_failed')
    if base.get('service_qualified_fraction',0)<1 or flex.get('service_qualified_fraction',0)<1:
        reasons.append('process_service_failed')
    if base.get('spec_unserved_kwh',1)>1e-7 or flex.get('spec_unserved_kwh',1)>1e-7:
        reasons.append('some_specification_heat_unserved')
    # A matched buffer end-state is not enough: the header stores C_h*T_h,
    # and the lagged compressor state can differ even when thermal inventories
    # happen to match. Compare both *components* and their sum, so compensating
    # header/buffer changes cannot pass an energy-only equality check.
    thermal_keys=('final_storage_delta_kwh','final_header_energy_delta_kwh',
                  'final_total_thermal_energy_delta_kwh')
    if all(k in base and k in flex and isfinite(base[k]) and isfinite(flex[k])
           for k in thermal_keys):
        buffer_delta=base['final_storage_delta_kwh']-flex['final_storage_delta_kwh']
        header_delta=base['final_header_energy_delta_kwh']-flex['final_header_energy_delta_kwh']
        total_delta=base['final_total_thermal_energy_delta_kwh']-flex['final_total_thermal_energy_delta_kwh']
        if abs(buffer_delta)>0.5:
            reasons.append('terminal_buffer_inventory_mismatch')
        if abs(header_delta)>0.5:
            reasons.append('terminal_header_inventory_mismatch')
        if abs(total_delta)>0.5:
            reasons.append('terminal_total_thermal_energy_mismatch')
    else:
        reasons.append('terminal_inventory_unavailable')
    # Explicitly guard hidden compressor lag/command differences. Tolerances
    # are synthetic benchmark eligibility choices, not physical certification.
    for field in ('final_modulation','final_applied_command'):
        if field not in base or field not in flex or not (isfinite(base[field]) and isfinite(flex[field])):
            reasons.append('terminal_actuator_state_unavailable')
            break
        if abs(base[field]-flex[field])>0.02:
            reasons.append('terminal_'+field+'_mismatch')
    if not(tariff.high_eur_kwh>tariff.low_eur_kwh):reasons.append('no_strict_high_low_price_spread')
    eligible=not reasons
    complete_horizon=(base['status']=='complete' and flex['status']=='complete')
    raw_cost_delta=(base['cost_eur']-flex['cost_eur']) if complete_horizon else None
    raw_elec_delta=(base['electricity_kwh']-flex['electricity_kwh']) if complete_horizon else None
    delta_cost=raw_cost_delta if eligible else None
    return dict(status=('conditional_model_comparison_eligible__NOT_EQUIPMENT_VERIFIED' if eligible else
                        'cost_saving_not_creditable'),reasons=reasons,
                baseline=base,flexibility=flex,
                eligible_cost_saving_eur=delta_cost,
                raw_cost_difference_eur=raw_cost_delta,
                raw_electricity_difference_kwh=raw_elec_delta,
                price_schedule=asdict(tariff),equipment_verified=False,
                policy_is_SOC=False)
