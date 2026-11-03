"""Reproduce WP7 research closure: fluid/process coupling, charge path and offdesign.

Run with CoolProp 8.x and TESPy 0.11.x; no property/model substitutions.
All machine performance and charge results remain unverified until OEM data.
"""
from __future__ import annotations
import csv
import json
from dataclasses import asdict
from pathlib import Path

from ht_hp_controlbench.core import Parameters, Disturbance
from ht_hp_controlbench.realfluid import CycleAssumptions, build_cycle_map, backend_version
from ht_hp_controlbench.thermo_feasibility import (
    HypotheticalEquipmentLimits, hold_service_at_buffer,
    quasisteady_charge_ledger)
from ht_hp_controlbench.fluid_dynamics import fluid_pi_simulation
from ht_hp_controlbench.pi import PISettings
from ht_hp_controlbench.tespy_offdesign import tespy_synthetic_offdesign

ROOT=Path('results')


def csv_write(path,rows):
    if not rows:raise ValueError('refuse empty WP7 output')
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys)
        w.writeheader();w.writerows(rows)


def main():
    ROOT.mkdir(exist_ok=True)
    a=CycleAssumptions()
    # This is a *post-hoc* hypothetical reference displacement, defined by
    # imposing 310 kW at n=0.75, not an identified compressor characteristic.
    m=build_cycle_map('R1233zd(E)',(328.15,333.15,338.15),
                      (403.15,406.20,413.15),(.5,.75,1),a)
    p=Parameters(hx_mode='duty_limiter')
    held=[]
    for source in (328.15,333.15,338.15):
        d=Disturbance(t_source=source)
        for t in (401.55,403.15,405.15,408.15):
            try:
                r=hold_service_at_buffer(t,m,p,d)
                r.pop('equipment_checks',None)
                held.append(dict(status=r.pop('status'),**r))
            except Exception as exc:
                # Preserve invalid points instead of imputing performance.
                from ht_hp_controlbench.realfluid import PointRejected
                if not isinstance(exc,PointRejected):raise
                held.append(dict(status='rejected',t_buffer_k=t,source_k=source,reason=str(exc)))
    csv_write(ROOT/'wp7_system_service_screen.csv',held)
    nominal=next(x for x in held if x['source_k']==333.15 and x['t_buffer_k']==403.15)
    if nominal['status']!='same_service_property_feasible__EQUIPMENT_UNVERIFIED':
        raise RuntimeError('nominal same-service property-coupled equilibrium rejected: '+str(nominal))
    charge=quasisteady_charge_ledger(m,p,low_k=401.55,high_k=408.15,nodes=21)
    hypo=HypotheticalEquipmentLimits(p_cond_max_pa=2.4e6,discharge_max_k=418.15)
    charge_with_hypothetical_limits=quasisteady_charge_ledger(
        m,p,low_k=401.55,high_k=408.15,nodes=21,limits=hypo)
    compact_charge={k:v for k,v in charge.items() if k!='samples'}
    compact_hypo={k:v for k,v in charge_with_hypothetical_limits.items() if k!='samples'}
    if charge.get('samples'):
        rows=[]
        for row in charge['samples']:
            row=row.copy();row.pop('equipment_checks',None);rows.append(row)
        csv_write(ROOT/'wp7_charge_profile.csv',rows)
    baseline=[]
    with (ROOT/'wp3_pi_comparison.csv').open('r',encoding='utf-8') as f:
        baseline=list(csv.DictReader(f))
    tunings=[]
    for mode in ('FOPDT_IMC_lambda_0p5tau','Relay_TyreusLuyben'):
        rr=next(row for row in baseline if row['hx_mode']=='no_bypass' and row['controller']==mode)
        tunings.append(PISettings(float(rr['kp_command_per_K']),float(rr['ki_command_per_Ks']),mode))
    dynamic=[]
    for settings in tunings:
        try:
            row=asdict(fluid_pi_simulation(m,settings,duration_s=7200.,step_s=10.))
        except Exception as exc:
            from ht_hp_controlbench.realfluid import PointRejected
            if not isinstance(exc,PointRejected):raise
            row=dict(controller=settings.source,status='rejected_no_extrapolation',reason=str(exc),equipment_verified=False)
        dynamic.append(row)
    csv_write(ROOT/'wp7_realfluid_PI_pilot.csv',dynamic)
    # TESPy design->offdesign network carries an EXPLICITLY HYPOTHETICAL eta(m).
    tespy=tespy_synthetic_offdesign((.75,1,1.1))
    csv_write(ROOT/'wp7_actual_TESPy_offdesign.csv',tespy)
    if len(tespy)!=3 or not all(row['tespy_mode']=='offdesign' for row in tespy):
        raise RuntimeError('TESPy design->offdesign cross-check did not execute')
    result={
        'status':'WP7_NUMERICAL_RESEARCH_COMPLETE__NOT_EQUIPMENT_VALIDATED',
        'model':'R1233zd(E) CoolProp HEOS + IF97 water; TESPy same CoolProp EOS',
        'coolprop_version':backend_version(),
        'tespy_version':tespy[0]['tespy_version'],
        'nominal_same_service':nominal,
        'assumptions':asdict(a),
        'reference_full_speed_suction_volume_m3_s':m.equivalent_full_speed_suction_volume_m3_s,
        'quasisteady_charge_without_equipment_ratings':compact_charge,
        'quasisteady_charge_with_HYPOTHETICAL_24bar_145C_limits':compact_hypo,
        'fluid_PI_dynamic_2hour_pilot':dynamic,
        'tespy_design_to_offdesign_test_count':len(tespy),
        'tespy_characteristic':'hypothetical eta_s vs m/m_design, NOT manufacturer data',
        'excluded_model_validation':[
            'OEM displacement and compressor efficiency/speed/discharge envelope',
            'hydraulic pressure rating and pressure safety standard compliance',
            'refrigerant-oil/materials/lifetime compatibility and safety classification',
            'measured duty, COP, HX UA, evaporator and condenser pressure losses',
            'system-specific transient/stratified storage and measured charging time',
            'fluid-based retuning and independent fair PI/MPC/SOC ranking',
            'experimental, operational and manufacturer validation'],
        'sources':[
            'https://coolprop.org/coolprop/HighLevelAPI.html',
            'https://coolprop.org/fluid_properties/IF97.html',
            'https://coolprop.org/fluid_properties/fluids/R1233zd%28E%29.html',
            'https://tespy.readthedocs.io/en/stable/building_blocks/networks.html',
            'https://tespy.readthedocs.io/en/stable/building_blocks/components.html']}
    (ROOT/'wp7_completion_summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    lines=['# WP7 — Numerical thermodynamic research closeout','',
        '> **Status: numerical research completed under assumptions; equipment feasibility UNVERIFIED.**',
        '', 'This is a separate property-backed model; WP2–WP6 plant and published controller rankings are unchanged.',
        '', '## Nominal same-service closure', '',
        f"- Process qualification: **{nominal['service_qualified']}** at buffer {nominal['t_buffer_k']-273.15:.2f} °C.",
        f"- Actual heat delivered to process: **{nominal['q_process_w']/1000:.3f} kW**; compressor condenser duty required **{nominal['q_hp_required_w']/1000:.3f} kW**.",
        f"- Implied reference compressor command: **{nominal['required_modulation']:.5f}**, with no manufacturer envelope established.",
        f"- Calculated cycle compressor electricity at this operating point: **{nominal['compressor_electric_required_w']/1000:.3f} kW** (no motor/auxiliary losses).",
        f"- Condensing pressure **{nominal['p_cond_pa']/1e5:.3f} bar(a)**; discharge **{nominal['discharge_k']-273.15:.2f} °C**; these are NOT rated limits.",
        '', '## Water buffer charging','',
        f"- No-OEM-limits scenario: **{charge['status']}**.",
        f"- Hypothetical pressure/discharge cap scenario (24 bar(a), 145°C): **{charge_with_hypothetical_limits['status']}**."]
    if charge.get('charge_hours') is not None:
        lines.extend([f"- Under optimistic quasisteady assumptions, {charge['energy_kwh']:.3f} kWh enthalpy from 128.40 to 135°C at 6 bar(a) requires **{charge['charge_hours']*60:.1f} min**.",
                      f"- Charge-surplus range {charge['surplus_min_w']/1000:.1f}–{charge['surplus_max_w']/1000:.1f} kW, still *not a device charging-time estimate*."])
    else:lines.append(f"- Charging path blocked at {charge.get('blocked_at_k','unknown')} K: {charge.get('reason','unknown')}. No charge-time estimate is published.")
    lines.extend(['', '## TESPy genuine design → offdesign', '',
        'TESPy saved one nominal design state and solved three offdesign mass-flow points via a declared, artificial efficiency characteristic. It uses CoolProp internally and is **not** a manufacturer-calibrated compressor map.',
        '', '| Mass ratio | Assumed efficiency | TESPy COP | Direct same-EOS COP |', '|---|---:|---:|---:|'])
    for x in tespy:
        lines.append(f"| {x['mass_ratio']:.2f} | {x['eta_assumed']:.4f} | {x['tespy_cop']:.5f} | {x['direct_cop']:.5f} |")
    lines.extend(['','## Real-fluid PI dynamic pilot','',
         'Original WP3 PI gains were **frozen**, while the simulated plant uses a CoolProp-dependent Q/P map and integrates water specific enthalpy. A pilot is not a full repeated WP4 MPC study.',
         '', '| Controller | Status | IAE (K·s) | Electric (kWh) | Process service fraction | Energy residual J |',
         '|---|---|---:|---:|---:|---:|'])
    for x in dynamic:
        if x['status'].startswith('completed'):
            lines.append(f"| {x['controller']} | completed | {x['iae_Ks']:.1f} | {x['electricity_kwh']:.3f} | {x['fraction_service_qualified']:.3f} | {x['max_energy_residual_J']:.4g} |")
        else:lines.append(f"| {x['controller']} | {x['status']}: {x.get('reason','')} | — | — | — | — |")
    lines.extend(['','## Hard scientific limits','',
        'The reference displacement is **inferred by forcing 310 kW at 75% modulation**. Neither its capacity nor its efficiency is measured. The 6 bar water pressure is an assumption, not an equipment rating. A CoolProp state PASS cannot certify pressure equipment, compressor thermal survival, refrigerant/oil suitability or chargeability.',
        '', 'The charging path assumes an infinitely fast header thermal equilibration, no rate ramp and no stratification, making its time an **illustrative optimistic model output**, not an operational claim. Failure under hypothetical limits is a sensitivity result, not evidence about any existing compressor.',
        '', 'System dynamic controller comparisons are pilot sensitivity checks, NOT proof of superiority of PI, MPC or SOC with a real fluid.',
        '', 'Sources: CoolProp high-level API, IF97 documentation and R1233zd(E) EOS; TESPy network/design-offdesign documentation. Exact links and versions in `wp7_completion_summary.json`.',
        '', 'Final classification: **WP7 research-software closure achieved; manufacturer/hardware verification open external dependency.**'])
    (ROOT/'wp7_completion_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('WP7 closure:',result['status'])
    print('Nominal Q required kW:',round(nominal['q_hp_required_w']/1000,4),'n=',round(nominal['required_modulation'],5))
    print('Conditional charging:',compact_charge.get('status'),'time_h=',compact_charge.get('charge_hours'))
    print('TESPy design-offdesign rows:',len(tespy),'PI dynamics:',[(x['controller'],x['status']) for x in dynamic])

if __name__=='__main__':main()
