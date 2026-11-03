"""Optional WP7 TESPy component-network cross-check of the CoolProp cycle.

TESPy shares the CoolProp EOS, so it is a network/equation cross-check,
NOT independent thermophysical data, manufacturer part-load or validation.
Requires Python>=3.11 and tespy>=0.11.
"""
from __future__ import annotations
from math import isfinite
from .realfluid import CyclePoint, PointRejected


def tespy_same_cycle(reference: CyclePoint, condenser_duty_w: float=310_000.) -> dict:
    """Solve an idealised TESPy heat-pump network using reference p/T and m.

    Re-solves the exact *same* thermodynamic assumptions as the direct
    four-state enthalpy equations, with no HX pressure loss. TESPy component
    equations are independent code, but CoolProp properties are shared.
    """
    try:
        import tespy
        from tespy.components import CycleCloser, Compressor, SimpleHeatExchanger, Valve
        from tespy.connections import Connection
        from tespy.networks import Network
    except ImportError as e:
        raise RuntimeError('TESPy missing: install the optional [tespy] extra on Python>=3.11') from e
    if not isfinite(condenser_duty_w) or condenser_duty_w<=0:
        raise ValueError('positive condenser duty required')
    if reference.discharge_vapor_enthalpy_margin_j_kg<=0:
        raise PointRejected('TESPy_not_attempted_for_wet_compressor_discharge')
    nw=Network()
    nw.set_attr(iterinfo=False)
    nw.units.set_defaults(temperature='degC',pressure='bar',heat='kW',power='kW',enthalpy='kJ/kg')
    cc=CycleCloser('refrigerant cycle closer')
    ev=SimpleHeatExchanger('evaporator')
    cp=Compressor('compressor')
    co=SimpleHeatExchanger('condenser')
    va=Valve('expansion valve')
    c1=Connection(cc,'out1',ev,'in1',label='valve to evaporator')
    c2=Connection(ev,'out1',cp,'in1',label='compressor suction')
    c3=Connection(cp,'out1',co,'in1',label='compressor discharge')
    c4=Connection(co,'out1',va,'in1',label='condenser liquid exit')
    c0=Connection(va,'out1',cc,'in1',label='valve discharge')
    nw.add_conns(c1,c2,c3,c4,c0)
    # Fix the same target states as direct CoolProp: no pressure drops,
    # evaporator exit superheated by 5 K and condenser exit subcooled 4 K.
    ev.set_attr(pr=1.)
    co.set_attr(pr=1.)
    # compressor isentropic efficiency already embedded in source point's h2.
    eta=(reference.h2s_j_kg-reference.h1_j_kg)/(reference.h2_j_kg-reference.h1_j_kg)
    cp.set_attr(eta_s=eta)
    mass=condenser_duty_w/reference.condenser_specific_j_kg
    c2.set_attr(m=mass,p=reference.p_evap_pa/1e5,
                T=reference.t_suction_k-273.15,fluid={reference.fluid:1.})
    c4.set_attr(p=reference.p_cond_pa/1e5,T=reference.t_cond_out_k-273.15)
    # Unlike steady-cycle equations, TESPy solves the full component network.
    nw.solve('design')
    if not nw.converged:
        raise PointRejected('tespy_network_failed_to_converge')
    condenser_heat_w=abs(float(co.Q.val))*1000
    compressor_power_w=float(cp.P.val)*1000
    evaporator_heat_w=float(ev.Q.val)*1000
    if not all(isfinite(x) for x in (condenser_heat_w,compressor_power_w,evaporator_heat_w)):
        raise PointRejected('tespy_nonfinite_network_output')
    if compressor_power_w <=0 or evaporator_heat_w <=0:
        raise PointRejected('tespy_invalid_positive_energy_flows')
    direct_p=mass*reference.compressor_specific_j_kg
    direct_ev=mass*reference.evaporator_specific_j_kg
    return dict(fluid=reference.fluid,tsource_k=reference.t_source_k,header_k=reference.t_header_k,
                tespy_version=getattr(tespy,'__version__','unknown'),
                network_mode='design_equations_with_fixed_mass_and_temperatures',
                reference_mass_kg_s=mass,
                tespy_condenser_w=condenser_heat_w,direct_condenser_w=condenser_duty_w,
                tespy_compressor_w=compressor_power_w,direct_compressor_w=direct_p,
                tespy_evaporator_w=evaporator_heat_w,direct_evaporator_w=direct_ev,
                tespy_cop=condenser_heat_w/compressor_power_w,
                direct_cop=reference.cop_heating,
                condenser_fractional_disagreement=(condenser_heat_w-condenser_duty_w)/condenser_duty_w,
                compressor_fractional_disagreement=(compressor_power_w-direct_p)/direct_p,
                energy_balance_residual_w=condenser_heat_w-compressor_power_w-evaporator_heat_w,
                shared_eos='CoolProp: TESPy uses CoolProp internally, not independent property measurement')
