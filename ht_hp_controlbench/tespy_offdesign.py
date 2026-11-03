"""Genuine TESPy design -> offdesign *synthetic characteristic* experiment.

This executes TESPy's network.solve('offdesign', design_path=...), rather than
re-solving unrelated design points. The compressor efficiency characteristic
is deliberately invented and declared; there is NO OEM part-load validation.
Both the independent-network solution and direct cycle use CoolProp EOS.
"""
from __future__ import annotations
from dataclasses import asdict, replace
from math import isfinite
from .realfluid import CycleAssumptions, PointRejected, cycle_point

# Entirely illustrative manufacturer-UNVALIDATED compressor mass-flow characteristic.
# Factor relative to eta_is_design; x = m_dot/m_dot_design.
CHAR_X=(0.50,0.75,1.0,1.25)
CHAR_Y=(0.88,0.97,1.0,0.985)


def _linear_characteristic(x:float)->float:
    if not CHAR_X[0]<=x<=CHAR_X[-1]:
        raise PointRejected('hypothetical_TESPy_compressor_characteristic_extrapolation_forbidden')
    import numpy as np
    return float(np.interp(x,CHAR_X,CHAR_Y))


def tespy_synthetic_offdesign(mass_ratios=(0.75, 1.0, 1.10),
                              source_k=333.15, header_k=406.20,
                              fluid='R1233zd(E)',
                              a:CycleAssumptions|None=None)->list[dict]:
    """Design once, then solve offdesign at changed mass-flow ratios in TESPy.

    TESPy component equations and same-EOS direct cycle must agree to 2%; this
    tests engineering implementation, not real machine characteristics.
    """
    try:
        import tespy
        from tespy.components import CycleCloser,Compressor,SimpleHeatExchanger,Valve
        from tespy.connections import Connection
        from tespy.networks import Network
        from tespy.tools.characteristics import CharLine
    except ImportError as exc:
        raise RuntimeError('TESPy optional dependency missing (install [tespy])') from exc
    a=a or CycleAssumptions()
    base=cycle_point(fluid,source_k,header_k,a)
    for ratio in mass_ratios:
        if not isfinite(ratio) or not CHAR_X[0]<=ratio<=CHAR_X[-1]:
            raise PointRejected('offdesign_ratio_outside_declared_synthetic_characteristic')
    nw=Network()
    nw.set_attr(iterinfo=False)
    nw.units.set_defaults(temperature='degC',pressure='bar',pressure_difference='bar',
                          heat='kW',power='kW',enthalpy='kJ/kg')
    cc=CycleCloser('cycle closer offdesign')
    ev=SimpleHeatExchanger('evaporator offdesign')
    cp=Compressor('compressor offdesign')
    co=SimpleHeatExchanger('condenser offdesign')
    va=Valve('valve offdesign')
    c1=Connection(cc,'out1',ev,'in1',label='throttled refrigerant')
    c2=Connection(ev,'out1',cp,'in1',label='suction refrigerant')
    c3=Connection(cp,'out1',co,'in1',label='discharge refrigerant')
    c4=Connection(co,'out1',va,'in1',label='subcooled refrigerant')
    c0=Connection(va,'out1',cc,'in1',label='expansion refrigerant')
    nw.add_conns(c1,c2,c3,c4,c0)
    ev.set_attr(pr=1.0)
    co.set_attr(pr=1.0)
    line=CharLine(x=list(CHAR_X),y=list(CHAR_Y),extrapolate=False)
    cp.set_attr(eta_s=a.eta_isentropic,
                design=['eta_s'],offdesign=['eta_s_char'])
    cp.set_attr(eta_s_char={'char_func':line,'param':'m'})
    mass_ref=a.reference_condenser_duty_w/base.condenser_specific_j_kg
    c2.set_attr(m=mass_ref,p=base.p_evap_pa/1e5,
                T=base.t_suction_k-273.15,fluid={fluid:1.0})
    c4.set_attr(p=base.p_cond_pa/1e5,T=base.t_cond_out_k-273.15)
    nw.solve('design')
    if not nw.converged:raise PointRejected('tespy_design_failed_to_converge')
    design_state=nw.save(as_dict=True)
    rows=[]
    for ratio in mass_ratios:
        c2.set_attr(m=mass_ref*ratio)
        nw.solve('offdesign',design_path=design_state)
        if not nw.converged:raise PointRejected(f'tespy_offdesign_failed_to_converge_at_mass_ratio_{ratio}')
        eta=a.eta_isentropic*_linear_characteristic(ratio)
        reference=cycle_point(fluid,source_k,header_k,replace(a,eta_isentropic=eta))
        direct_compressor=mass_ref*ratio*reference.compressor_specific_j_kg
        direct_condenser=mass_ref*ratio*reference.condenser_specific_j_kg
        compressor_w=float(cp.P.val)*1000
        condenser_w=abs(float(co.Q.val))*1000
        evap_w=float(ev.Q.val)*1000
        if not all(isfinite(v) for v in (compressor_w,condenser_w,evap_w)):
            raise PointRejected('tespy_offdesign_nonfinite')
        if compressor_w<=0 or condenser_w<=0 or evap_w<=0:
            raise PointRejected('tespy_offdesign_nonphysical_sign')
        residual=condenser_w-compressor_w-evap_w
        if abs(residual)>max(1.0,1e-6*condenser_w):
            raise PointRejected('tespy_offdesign_energy_balance_failed')
        error_p=(compressor_w-direct_compressor)/direct_compressor
        error_q=(condenser_w-direct_condenser)/direct_condenser
        if max(abs(error_p),abs(error_q))>.02:
            raise PointRejected('tespy_offdesign_not_consistent_with_same_EOS_direct_cycle')
        rows.append(dict(fluid=fluid,mass_ratio=ratio,source_k=source_k,header_k=header_k,
                         tespy_mode='offdesign',design_saved=True,model_kind='SYNTHETIC_ETA_CHARACTERISTIC',
                         eta_assumed=eta,eta_tespy=float(cp.eta_s.val),
                         nominal_reference_mass_kg_s=mass_ref,
                         offdesign_mass_kg_s=mass_ref*ratio,
                         tespy_condenser_w=condenser_w,direct_condenser_w=direct_condenser,
                         tespy_compressor_w=compressor_w,direct_compressor_w=direct_compressor,
                         tespy_cop=condenser_w/compressor_w,direct_cop=reference.cop_heating,
                         q_relative_disagreement=error_q,p_relative_disagreement=error_p,
                         energy_balance_residual_w=residual,
                         tespy_version=getattr(tespy,'__version__','unknown'),
                         equipment_verified=False))
    return rows
