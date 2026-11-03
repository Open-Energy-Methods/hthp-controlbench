"""WP7 numerical closure: coupled HTHP/process service, compressor and water storage.

This module provides *conditional* property-based results only. Its swept volume,
compressor efficiency, thermal conductances and 6 bar water pressure are assumed,
not equipment specifications. Never treat a property PASS as a rated-machine PASS.

All calculations are steady/quasi-steady; charging neglects finite header inertia,
control transients, compressor cycling and water stratification. No equipment data.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Callable

import numpy as np
from scipy.optimize import brentq

from .core import Parameters, Disturbance, heat_exchanger
from .realfluid import (CycleAssumptions, CycleMap, PointRejected, cycle_point,
                         water_loop_state, _prop)


@dataclass(frozen=True)
class HypotheticalEquipmentLimits:
    """User-supplied *illustrative* thresholds; never inferred from EOS or OEM data."""
    p_cond_max_pa: float | None = None
    pressure_ratio_max: float | None = None
    discharge_max_k: float | None = None
    suction_volume_max_m3_s: float | None = None
    def __post_init__(self):
        for name, limit in asdict(self).items():
            if limit is not None and (not isfinite(limit) or limit <= 0):
                raise ValueError(f'{name} must be finite and positive, or None')


def hypothetical_machine_checks(point, n: float, model: CycleMap,
                                limits: HypotheticalEquipmentLimits | None = None) -> dict:
    """Evaluate only declared limits. Missing OEM data -> *unverified*, not pass."""
    lim = limits or HypotheticalEquipmentLimits()
    vals = dict(p_cond_max_pa=point.p_cond_pa,
                pressure_ratio_max=point.pressure_ratio,
                discharge_max_k=point.t_discharge_k,
                suction_volume_max_m3_s=model.equivalent_full_speed_suction_volume_m3_s*n)
    provided = {name: limit for name, limit in asdict(lim).items() if limit is not None}
    failed = [name for name, limit in provided.items() if vals[name] > limit + 1e-9]
    return dict(status='hypothetical_limit_exceeded' if failed else
                      'no_manufacturer_limits_provided' if not provided else
                      'hypothetical_limit_check_pass__NOT_OEM_validated',
                checked=provided, calculated=vals, failed=failed,
                equipment_verified=False)


def _process_balance(t_buffer_k: float, p: Parameters, d: Disturbance):
    """At fixed T_buffer, solve the *actual* WP2 exchanger and header energy balance."""
    if p.khb <= 0: raise PointRejected('hot_loop_thermal_link_must_be_positive')
    hx = heat_exchanger(t_buffer_k, p, d)
    loss_buffer = p.ua_b*(t_buffer_k-d.t_ambient)
    q_hb = hx.q_transferred + loss_buffer
    t_header = t_buffer_k + q_hb/p.khb
    loss_header = p.ua_h*(t_header-d.t_ambient)
    q_needed = q_hb + loss_header
    return hx, q_needed, t_header, q_hb, loss_buffer, loss_header


def hold_service_at_buffer(t_buffer_k:float, model:CycleMap,
                           p:Parameters|None=None, d:Disturbance|None=None,
                           limits:HypotheticalEquipmentLimits|None=None,
                           props=None)->dict:
    """Required n to hold a *same-service*, steady buffer temperature.

    Derives n from a synthetic reference volume and an actual CoolProp cycle,
    not the original nominal synthetic COP map. n>1 or n<declared map floor
    is a failed result; no extrapolation or emulated capacity is substituted.
    """
    p = p or Parameters(hx_mode='duty_limiter')
    d = d or Disturbance()
    hx, q_needed, th, q_hb, loss_b, loss_h = _process_balance(t_buffer_k,p,d)
    point = cycle_point(model.fluid,d.t_source,th,model.assumptions,props)
    q_one = model.equivalent_full_speed_suction_volume_m3_s*point.rho_suction_kg_m3*point.condenser_specific_j_kg
    if q_one <= 0 or not isfinite(q_one): raise PointRejected('invalid_full_modulation_heat_rate')
    n=q_needed/q_one
    inside_map = (model.modulations[0] <= n <= model.modulations[-1] and
                  model.t_sources_k[0] <= d.t_source <= model.t_sources_k[-1] and
                  model.t_headers_k[0] <= th <= model.t_headers_k[-1])
    equipment = hypothetical_machine_checks(point,n,model,limits)
    qualified = bool(hx.qualified)
    status = ('process_service_failed' if not qualified else
              'compressor_modulation_outside_declared_grid' if not inside_map else
              'hypothetical_equipment_limit_exceeded' if equipment['failed'] else
              'same_service_property_feasible__EQUIPMENT_UNVERIFIED')
    return dict(status=status,source_k=d.t_source,t_buffer_k=t_buffer_k,t_header_k=th,
                process_outlet_k=hx.t_proc_out,service_qualified=qualified,
                hx_bypass_fraction=hx.fraction,q_process_w=hx.q_transferred,
                q_hp_required_w=q_needed,required_modulation=n,
                q_hp_max_assumed_w=q_one,
                compressor_electric_required_w=n*q_one/point.cop_heating,
                source_heat_required_w=q_needed*(1-1/point.cop_heating),
                p_cond_pa=point.p_cond_pa,pressure_ratio=point.pressure_ratio,
                discharge_k=point.t_discharge_k,hot_loop_exchange_w=q_hb,
                buffer_heat_loss_w=loss_b,header_heat_loss_w=loss_h,
                declared_map_support=inside_map,equipment_checks=equipment,
                equipment_verified=False)


def max_speed_charge_point(t_buffer_k:float,model:CycleMap,
                           p:Parameters|None=None,d:Disturbance|None=None,
                           limits:HypotheticalEquipmentLimits|None=None,
                           props=None)->dict:
    """Quasi-steady header balance at n=1, with finite process HX and losses.

    We solve Q_hp(T_h, n=1) = K_hb(T_h-T_b)+Q_loss_h(T_h).
    Surplus into the buffer then equals K_hb*DeltaT-Q_process-Q_loss_b.
    If no physically valid root inside the *declared map domain*, reject.
    """
    p=p or Parameters(hx_mode='duty_limiter')
    d=d or Disturbance()
    if p.khb<=0:raise PointRejected('hot_loop_thermal_link_must_be_positive')
    if not model.t_sources_k[0]<=d.t_source<=model.t_sources_k[-1]:
        raise PointRejected('charge_source_outside_declared_map')
    lo=max(model.t_headers_k[0],t_buffer_k)
    hi=model.t_headers_k[-1]
    if hi<=lo:raise PointRejected('charge_buffer_above_declared_header_domain')
    def residual(th):
        pt=cycle_point(model.fluid,d.t_source,th,model.assumptions,props)
        q=model.equivalent_full_speed_suction_volume_m3_s*pt.rho_suction_kg_m3*pt.condenser_specific_j_kg
        return q - p.khb*(th-t_buffer_k) - p.ua_h*(th-d.t_ambient)
    f_lo,f_hi=residual(lo),residual(hi)
    if f_lo*f_hi>0:raise PointRejected('no_quasisteady_charge_balance_in_declared_header_domain')
    th=brentq(residual,lo,hi,xtol=1e-9)
    hx=heat_exchanger(t_buffer_k,p,d)
    point=cycle_point(model.fluid,d.t_source,th,model.assumptions,props)
    qhp=model.equivalent_full_speed_suction_volume_m3_s*point.rho_suction_kg_m3*point.condenser_specific_j_kg
    q_hb=p.khb*(th-t_buffer_k)
    surplus=q_hb-hx.q_transferred-p.ua_b*(t_buffer_k-d.t_ambient)
    # Check water phase at both buffer/header temperatures under assumed water loop p.
    water_loop_state(max(th,t_buffer_k),model.assumptions,props)
    equip=hypothetical_machine_checks(point,1.,model,limits)
    status=('process_service_failed' if not hx.qualified else
            'hypothetical_equipment_limit_exceeded' if equip['failed'] else
            'no_surplus_for_charge' if surplus<=0 else
            'conditional_charge_surplus__EQUIPMENT_UNVERIFIED')
    return dict(status=status,t_buffer_k=t_buffer_k,t_header_k=th,
                service_qualified=bool(hx.qualified),q_hp_w=qhp,
                p_el_w=qhp/point.cop_heating,q_source_w=qhp*(1-1/point.cop_heating),
                process_q_w=hx.q_transferred,surplus_w=surplus,
                compressor_modulation=1.,p_cond_pa=point.p_cond_pa,
                discharge_k=point.t_discharge_k,pressure_ratio=point.pressure_ratio,
                equipment_checks=equip,equipment_verified=False)


def quasisteady_charge_ledger(model:CycleMap,p:Parameters|None=None,
                               d:Disturbance|None=None, low_k:float=401.55,
                               high_k:float=408.15,mass_kg:float=5000.,
                               nodes:int=17,
                               limits:HypotheticalEquipmentLimits|None=None,
                               props=None)->dict:
    """Optimistic *model-conditional* charge path: IF97 dh, not constant cp.

    dt = m dh_w(T,p) / surplus(T), integrated with trapezoid over enthalpy.
    Header energy accumulation, motor ramp, stratification & losses outside
    the WP2 model are excluded. So do NOT treat time as real guaranteed minimum.
    """
    if high_k<=low_k or mass_kg<=0 or nodes<3:
        raise ValueError('positive mass, increasing temperature, >=3 nodes required')
    p=p or Parameters(hx_mode='duty_limiter'); d=d or Disturbance()
    props = props if props is not None else __import__('ht_hp_controlbench.realfluid',fromlist=['coolprop_backend']).coolprop_backend()
    temps=np.linspace(low_k,high_k,nodes)
    rows=[];enthalpies=[]
    for t in temps:
        row=max_speed_charge_point(float(t),model,p,d,limits,props)
        if row['status']!='conditional_charge_surplus__EQUIPMENT_UNVERIFIED':
            return dict(status='blocked_or_unverified',blocked_at_k=float(t),reason=row['status'],
                        samples=rows+[row],equipment_verified=False)
        row['water_h_j_kg']=_prop(props,'H','IF97::Water','T',float(t),'P',model.assumptions.service_header_pressure_pa)
        rows.append(row); enthalpies.append(row['water_h_j_kg'])
    h=np.array(enthalpies);surplus=np.array([row['surplus_w'] for row in rows]);
    if np.any(np.diff(h)<=0):raise PointRejected('nonmonotonic_IF97_charge_path')
    charge_s=float(np.sum(mass_kg*np.diff(h)*.5*(1/surplus[1:]+1/surplus[:-1])))
    e_kwh=mass_kg*(h[-1]-h[0])/3.6e6
    return dict(status='conditional_quasisteady_charge_path__EQUIPMENT_UNVERIFIED',
                low_k=low_k,high_k=high_k,mass_kg=mass_kg,nodes=nodes,
                energy_kwh=float(e_kwh),charge_hours=float(charge_s/3600),
                surplus_min_w=float(min(surplus)),surplus_max_w=float(max(surplus)),
                max_p_cond_pa=max(x['p_cond_pa'] for x in rows),
                max_discharge_k=max(x['discharge_k'] for x in rows),
                max_header_k=max(x['t_header_k'] for x in rows),
                samples=rows,equipment_verified=False,
                no_hardware_validation='hypothetical swept volume, compression efficiency, pressure/discharge ratings, HX UA and 6 bar water loop')
