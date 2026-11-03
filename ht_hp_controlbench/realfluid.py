"""WP7: independently screened, *uncalibrated* CoolProp steady-state HTHP cycle.

This is an idealized four-state subcritical vapour-compression *reference*,
not a manufacturer compressor model, TESPy network, dynamic refrigerant model,
or permission to operate pressure equipment. Property values are never invented:
CoolProp absence raises an explicit exception. Units: K, Pa, J/kg, kg/s, W.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Callable, Sequence

import numpy as np
from scipy.interpolate import RegularGridInterpolator


class PropertyBackendMissing(RuntimeError):
    """CoolProp unavailable; a real-fluid calculation cannot be claimed."""


class PointRejected(ValueError):
    """Explicit feasibility rejection, never a substituted synthetic number."""


def coolprop_backend():
    try:
        from CoolProp.CoolProp import PropsSI
    except ImportError as e:
        raise PropertyBackendMissing('Install `pip install -e ".[realfluid]"` to run WP7; no synthetic substitute.') from e
    return PropsSI


def backend_version() -> str:
    try:
        import CoolProp
    except ImportError as e:
        raise PropertyBackendMissing('CoolProp not installed') from e
    return CoolProp.__version__


def _check(name: str, x: float) -> float:
    if not isfinite(float(x)):
        raise PointRejected(f'nonfinite_property:{name}')
    return float(x)


def _prop(props, output, fluid, *inputs):
    try:
        if inputs:
            v = props(output, *inputs, fluid)
        else:
            v = props(output, fluid)
    except Exception as exc:
        raise PointRejected(f'property_failure:{fluid}:{output}:{type(exc).__name__}:{str(exc)[:100]}') from exc
    return _check(output, v)


@dataclass(frozen=True)
class CycleAssumptions:
    eta_isentropic: float = 0.75  # ASSUMED, not a measured compressor efficiency
    evap_approach_k: float = 5.0
    cond_approach_k: float = 5.0
    superheat_k: float = 5.0
    subcool_k: float = 4.0
    critical_margin_k: float = 5.0  # voluntary screening buffer; not a manufacturer limit
    service_header_pressure_pa: float = 600000.0  # synthetic loop assumption, NOT a design pressure
    water_saturation_margin_fraction: float = 0.15
    reference_condenser_duty_w: float = 310000.0
    reference_modulation: float = 0.75

    def __post_init__(self):
        if not 0 < self.eta_isentropic <= 1:
            raise ValueError('compressor efficiency outside (0,1]')
        if min(self.evap_approach_k, self.cond_approach_k, self.superheat_k,
               self.subcool_k, self.critical_margin_k) <= 0:
            raise ValueError('approaches, superheat, subcool, and critical margin must be positive')
        if self.reference_condenser_duty_w <= 0 or not 0 < self.reference_modulation <= 1:
            raise ValueError('bad illustrative design load/modulation')
        if self.service_header_pressure_pa <= 0 or self.water_saturation_margin_fraction < 0:
            raise ValueError('invalid illustrative loop-pressure assumptions')


@dataclass(frozen=True)
class CyclePoint:
    fluid: str
    t_source_k: float
    t_header_k: float
    t_evap_sat_k: float
    t_cond_sat_k: float
    t_suction_k: float
    t_discharge_k: float
    t_cond_out_k: float
    t_critical_k: float
    p_evap_pa: float
    p_cond_pa: float
    pressure_ratio: float
    rho_suction_kg_m3: float
    h1_j_kg: float
    h2s_j_kg: float
    h2_j_kg: float
    h_discharge_sat_vapor_j_kg: float
    discharge_vapor_enthalpy_margin_j_kg: float
    h3_j_kg: float
    throttle_quality: float
    compressor_specific_j_kg: float
    condenser_specific_j_kg: float
    evaporator_specific_j_kg: float
    cop_heating: float
    cop_carnot_refrigerant: float
    second_law_ratio: float
    volumetric_heat_capacity_j_m3: float
    property_origin: str = 'CoolProp HEOS property-calculated; uncalibrated assumed compressor parameters'


def cycle_point(fluid: str, t_source_k: float, t_header_k: float,
                assumptions: CycleAssumptions | None = None, props=None) -> CyclePoint:
    """Single-stage subcritical cycle: 1 suction, 2 discharge, 3 liquid, 4 valve.

    h2=h1+(h2s-h1)/eta_is; h4=h3; Q_cond=m*(h2-h3);
    W_comp=m*(h2-h1); Q_evap=m*(h1-h3).
    The model assumes no pressure losses, motor losses or auxiliary pump power.
    """
    a = assumptions or CycleAssumptions()
    props = props if props is not None else coolprop_backend()
    if fluid == 'CarbonDioxide':
        raise PointRejected('transcritical_CO2_requires_different_cycle_topology')
    if min(t_source_k, t_header_k) <= 0 or t_header_k <= t_source_k:
        raise PointRejected('nonphysical_source_sink_temperatures')
    te = t_source_k - a.evap_approach_k
    tc = t_header_k + a.cond_approach_k
    tcrit = _prop(props, 'Tcrit', fluid)
    tmin = _prop(props, 'Tmin', fluid)
    tmax = _prop(props, 'Tmax', fluid)
    if te <= tmin + 0.01:
        raise PointRejected('evaporating_temperature_below_EOS_limit')
    if tc >= tcrit - a.critical_margin_k:
        raise PointRejected('subcritical_condensing_temperature_above_critical_guard')
    if tc >= tmax - 0.1:
        raise PointRejected('condensing_temperature_above_EOS_maximum')
    t1 = te + a.superheat_k
    t3 = tc - a.subcool_k
    if not t3 > te:
        raise PointRejected('condenser_liquid_must_be_hotter_than_evaporator')
    p1 = _prop(props, 'P', fluid, 'T', te, 'Q', 1)
    p2 = _prop(props, 'P', fluid, 'T', tc, 'Q', 0)
    if p1 <= 0 or p2 <= p1:
        raise PointRejected('nonpositive_or_inverted_cycle_pressures')
    h1 = _prop(props, 'H', fluid, 'T', t1, 'P', p1)
    s1 = _prop(props, 'S', fluid, 'T', t1, 'P', p1)
    rho = _prop(props, 'D', fluid, 'T', t1, 'P', p1)
    h2s = _prop(props, 'H', fluid, 'P', p2, 'S', s1)
    h2 = h1 + (h2s-h1)/a.eta_isentropic
    # A P,H flash can return T=T_sat even for a *wet* discharge.
    # Check enthalpy against saturated vapour explicitly before interpreting T2.
    h_g_cond = _prop(props, 'H', fluid, 'P', p2, 'Q', 1)
    if h2 <= h_g_cond + 1.0:  # explicit 1 J/kg dry-vapour numerical guard
        raise PointRejected('compressor_discharge_wet_or_not_superheated_vapor')
    t2 = _prop(props, 'T', fluid, 'P', p2, 'H', h2)
    if t2 >= tmax - 0.1:
        raise PointRejected('compressor_discharge_above_EOS_maximum')
    if t2 < tc-0.005:
        raise PointRejected('discharge_not_superheated_at_condenser_pressure')
    h3 = _prop(props, 'H', fluid, 'T', t3, 'P', p2)
    # The throttling state must be liquid-vapour two-phase in this topology.
    x4 = _prop(props, 'Q', fluid, 'P', p1, 'H', h3)
    if not -1e-8 <= x4 <= 1+1e-8:
        raise PointRejected('throttle_outlet_not_two_phase')
    w = h2-h1
    qh = h2-h3
    qe = h1-h3
    if min(w, qh, qe, rho) <= 0:
        raise PointRejected('nonpositive_specific_cycle_energies_or_suction_density')
    cop = qh/w
    carnot = tc/(tc-te)
    if cop <= 1 or cop > carnot*(1+1e-6):
        raise PointRejected('COP_outside_physically_possible_heat_pump_envelope')
    if abs(qh-w-qe)>max(1e-5,abs(qh)*1e-9):
        raise PointRejected('energy_balance_inconsistent')
    return CyclePoint(fluid,t_source_k,t_header_k,te,tc,t1,t2,t3,tcrit,p1,p2,p2/p1,
                      rho,h1,h2s,h2,h_g_cond,h2-h_g_cond,h3,x4,w,qh,qe,cop,carnot,cop/carnot,rho*qh)


def water_loop_state(t_hot_k: float, assumptions: CycleAssumptions | None = None,
                     props=None, t_reference_k: float = 393.15) -> dict:
    """Pressurised water screening at an *assumed* 6 bar(a), not a design limit.

    IF97 water is compared with HEOS Water for a cross-backend discrepancy;
    they share CoolProp implementation and do not constitute lab validation.
    """
    a = assumptions or CycleAssumptions()
    props = props if props is not None else coolprop_backend()
    if t_hot_k <= 273.15 or t_reference_k <= 273.15:
        raise PointRejected('water_temperature_outside_IF97_range')
    psat = _prop(props, 'P', 'IF97::Water', 'T', t_hot_k, 'Q', 0)
    if a.service_header_pressure_pa <= psat*(1+a.water_saturation_margin_fraction):
        raise PointRejected('illustrative_water_loop_pressure_fails_liquid_phase_margin')
    p = a.service_header_pressure_pa
    h_hot = _prop(props, 'H', 'IF97::Water', 'T', t_hot_k, 'P', p)
    h_reference = _prop(props, 'H', 'IF97::Water', 'T', t_reference_k, 'P', p)
    p_heos = _prop(props, 'P', 'Water', 'T', t_hot_k, 'Q', 0)
    return dict(t_hot_k=t_hot_k, loop_pressure_assumed_pa=p, saturation_pressure_if97_pa=psat,
                saturation_pressure_heos_pa=p_heos, relative_pressure_margin=(p/psat-1),
                enthalpy_difference_from_120C_j_kg=h_hot-h_reference,
                sat_backend_fractional_difference=(p_heos-psat)/psat,
                water_property_origin='CoolProp IF97 and HEOS; uncalibrated assumed loop pressure')


def screen_point(fluid, t_source_k, t_header_k, assumptions=None, props=None) -> dict:
    """Failed states remain visible with explicit status/reason; no fake COP."""
    try:
        c = cycle_point(fluid,t_source_k,t_header_k,assumptions,props)
        return dict(fluid=fluid,t_source_k=t_source_k,t_header_k=t_header_k,
                    status='property_cycle_pass', reason='',**{k:v for k,v in asdict(c).items()
                    if k not in ('fluid','t_source_k','t_header_k')})
    except PointRejected as e:
        return dict(fluid=fluid,t_source_k=t_source_k,t_header_k=t_header_k,status='rejected',reason=str(e))


@dataclass(frozen=True)
class CycleMap:
    fluid: str
    t_sources_k: tuple[float,...]
    t_headers_k: tuple[float,...]
    modulations: tuple[float,...]
    thermal_w: np.ndarray
    electrical_w: np.ndarray
    reference_cycle: CyclePoint
    equivalent_full_speed_suction_volume_m3_s: float
    assumptions: CycleAssumptions

    def evaluate(self,n:float,t_source_k:float,t_header_k:float) -> tuple[float,float,float]:
        axes=(self.modulations,self.t_sources_k,self.t_headers_k)
        pos=(float(n),float(t_source_k),float(t_header_k))
        if any(v<ax[0]-1e-12 or v>ax[-1]+1e-12 for v,ax in zip(pos,axes)):
            raise PointRejected('offdesign_map_extrapolation_forbidden')
        q=float(RegularGridInterpolator(axes,self.thermal_w,bounds_error=True)(pos))
        p=float(RegularGridInterpolator(axes,self.electrical_w,bounds_error=True)(pos))
        if q < -1e-8 or p < -1e-8 or q < p-1e-6:
            raise PointRejected('nonphysical_interpolated_thermal_power')
        return max(0.,q),max(0.,p),max(0.,q-p)


def map_exact(point:CyclePoint,n:float,m:CycleMap)->tuple[float,float,float]:
    if not 0<=n<=1:
        raise ValueError('modulation outside [0,1]')
    # Assumed constant equivalent swept volume, not measured compressor displacement.
    mdot=point.rho_suction_kg_m3*m.equivalent_full_speed_suction_volume_m3_s*n
    q=mdot*point.condenser_specific_j_kg
    p=mdot*point.compressor_specific_j_kg
    return q,p,q-p


def build_cycle_map(fluid: str, sources:Sequence[float], headers:Sequence[float],
                    modulations:Sequence[float], assumptions=None, props=None,
                    reference_source_k:float=333.15,reference_header_k:float=406.20)->CycleMap:
    a=assumptions or CycleAssumptions()
    props=props if props is not None else coolprop_backend()
    axes=tuple(tuple(float(x) for x in row) for row in (modulations,sources,headers))
    if any(len(row)<2 or any(y<=x for x,y in zip(row,row[1:])) for row in axes):
        raise ValueError('strictly increasing axes, at least two points per axis')
    if any(n<0 or n>1 for n in axes[0]):
        raise ValueError('modulations outside physical interval')
    if not (axes[1][0]<=reference_source_k<=axes[1][-1] and
            axes[2][0]<=reference_header_k<=axes[2][-1]):
        raise ValueError('nominal source/header must lie within grid')
    cp=cycle_point(fluid,reference_source_k,reference_header_k,a,props)
    mdot=a.reference_condenser_duty_w/cp.condenser_specific_j_kg
    vdot=mdot/(cp.rho_suction_kg_m3*a.reference_modulation)
    shape=(len(axes[0]),len(axes[1]),len(axes[2]))
    heat,power=np.zeros(shape),np.zeros(shape)
    # Cache properties by (source,header), independent of speed in this explicit idealization.
    for i,ts in enumerate(axes[1]):
        for j,th in enumerate(axes[2]):
            pt=cycle_point(fluid,ts,th,a,props)
            for k,n in enumerate(axes[0]):
                mass=vdot*n*pt.rho_suction_kg_m3
                heat[k,i,j]=mass*pt.condenser_specific_j_kg
                power[k,i,j]=mass*pt.compressor_specific_j_kg
    return CycleMap(fluid,axes[1],axes[2],axes[0],heat,power,cp,vdot,a)


def map_holdout_error(m:CycleMap,positions,props=None)->list[dict]:
    props=props if props is not None else coolprop_backend()
    out=[]
    for n,ts,th in positions:
        point=cycle_point(m.fluid,ts,th,m.assumptions,props)
        exact_q,exact_p,_=map_exact(point,n,m)
        pred_q,pred_p,_=m.evaluate(n,ts,th)
        out.append(dict(fluid=m.fluid,n=n,source_k=ts,header_k=th,
                        actual_q_w=exact_q,pred_q_w=pred_q,
                        relative_q_error=(pred_q-exact_q)/exact_q,
                        actual_p_w=exact_p,pred_p_w=pred_p,
                        relative_p_error=(pred_p-exact_p)/exact_p))
    return out


def conditional_water_inventory(mass_kg:float=5000.,low_k:float=401.53,
                                high_k:float=408.15,
                                assumptions:CycleAssumptions|None=None,props=None)->dict:
    """Water enthalpy inventory above service boundary, conditional on reachability.

    This is NOT available storage until a rated compressor can charge to high_k,
    pressure limits, HX approaches and recharge feasibility all pass separately.
    """
    a=assumptions or CycleAssumptions()
    props=props if props is not None else coolprop_backend()
    if mass_kg<=0 or high_k<=low_k:
        raise ValueError('positive water mass and increasing temperatures required')
    water_loop_state(low_k,a,props)
    water_loop_state(high_k,a,props)
    hlo=_prop(props,'H','IF97::Water','T',low_k,'P',a.service_header_pressure_pa)
    hhi=_prop(props,'H','IF97::Water','T',high_k,'P',a.service_header_pressure_pa)
    if hhi<=hlo:raise PointRejected('IF97_water_enthalpy_not_monotonic')
    return dict(mass_kg=mass_kg,minimum_service_temperature_k=low_k,
                hypothetical_high_temperature_k=high_k,
                enthalpy_difference_j_kg=hhi-hlo,
                conditional_energy_kwh=mass_kg*(hhi-hlo)/3.6e6,
                capacity_status='conditional_arithmetic_ONLY__high_temperature_unproven')
