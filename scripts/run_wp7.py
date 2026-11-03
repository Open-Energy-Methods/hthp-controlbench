"""WP7 reproducible CoolProp steady-state property / cycle screening.

Run only with actual CoolProp. Missing backend and absent eligible cycles fail loudly.
Outputs: CSV, JSON, Markdown and optional illustration. NOT calibration/validation.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, replace
from pathlib import Path

from ht_hp_controlbench.core import Disturbance, Parameters, State, output
from ht_hp_controlbench.realfluid import (
    CycleAssumptions, PointRejected, backend_version, build_cycle_map,
    cycle_point, map_holdout_error, screen_point, water_loop_state, conditional_water_inventory,
)

OUT=Path('results')
FLUIDS=('R1233zd(E)','R1336mzz(Z)','R134a','Ammonia','CarbonDioxide')
SOURCES=(328.15,333.15,338.15)   # 55, 60, 65C bulk heat source
HEADERS=(403.15,406.20,413.15)   # 130, 133.05, 140C actual header
N=(.5,.75,1.0)
HOLDOUT=((.625,330.65,404.675),(.875,335.65,409.675),
         (.625,335.65,404.675),(.875,330.65,409.675))


def csvwrite(path,rows):
    if not rows:
        raise ValueError(f'refusing to publish empty dataset: {path}')
    fields=[]
    for row in rows:
        for k in row:
            if k not in fields:fields.append(k)
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    version=backend_version()  # fails immediately if no backend; no replacement values
    a=CycleAssumptions()
    nominal=[screen_point(f,333.15,406.2,a) for f in FLUIDS]
    fluids_pass=[r['fluid'] for r in nominal if r['status']=='property_cycle_pass']
    if not fluids_pass:
        raise RuntimeError('WP7 NEGATIVE RESULT: no nominated fluid meets even property-cycle screen')
    if not all(x['status']=='rejected' for x in nominal if x['fluid'] in ('R134a','Ammonia','CarbonDioxide')):
        raise RuntimeError('Subcritical invalid candidates were unexpectedly permitted: check cycle topology')
    csvwrite(OUT/'wp7_nominal_fluid_screen.csv',nominal)

    # Screen the whole Tsource/Theader property envelope without inventing values
    envelope=[screen_point(f,ts,th,a) for f in FLUIDS for ts in SOURCES for th in HEADERS]
    csvwrite(OUT/'wp7_envelope.csv',envelope)

    # Loop water pressure is an assumed numerical value for phase screening, NOT design guidance.
    water=[]
    for t in (393.15,403.15,406.20,413.15,418.15):
        try:water.append(dict(status='property_water_pass',reason='',**water_loop_state(t,a)))
        except PointRejected as e:water.append(dict(t_hot_k=t,status='rejected',reason=str(e)))
    csvwrite(OUT/'wp7_water_if97.csv',water)

    maps=[];hold=[];map_fail=[]
    for f in fluids_pass:
        try:
            m=build_cycle_map(f,SOURCES,HEADERS,N,a)
            hs=map_holdout_error(m,HOLDOUT)
            hold.extend(hs)
            maps.append(dict(fluid=f,reference_heat_w=a.reference_condenser_duty_w,
                             reference_n=a.reference_modulation,
                             equivalent_full_speed_suction_m3_s=m.equivalent_full_speed_suction_volume_m3_s,
                             nominal_suction_density_kg_m3=m.reference_cycle.rho_suction_kg_m3,
                             nominal_compressor_electrical_w=a.reference_condenser_duty_w/m.reference_cycle.cop_heating,
                             max_holdout_q_relative_error=max(abs(x['relative_q_error']) for x in hs),
                             max_holdout_p_relative_error=max(abs(x['relative_p_error']) for x in hs),
                             note='implied volumetric flow at a forced 310kW nominal duty, NOT equipment calibration'))
        except PointRejected as e:
            map_fail.append(dict(fluid=f,status='masked_map',reason=str(e)))
    if not maps:
        raise RuntimeError('Nominal candidates passed but none permits a full non-extrapolating L3 map')
    csvwrite(OUT/'wp7_map_reference.csv',maps)
    csvwrite(OUT/'wp7_map_holdout.csv',hold)
    if map_fail:csvwrite(OUT/'wp7_map_rejections.csv',map_fail)

    # Report 4 operating-point sensitivity calculations for each passing nominal fluid.
    sensitivity=[]
    for f in fluids_pass:
        for eta in (.65,.75,.85):
            for cond_app in (5.,8.):
                aa=replace(a,eta_isentropic=eta,cond_approach_k=cond_app)
                r=screen_point(f,333.15,406.20,aa)
                if r['status']=='property_cycle_pass':
                    sensitivity.append(dict(fluid=f,eta_isentropic=eta,cond_approach_k=cond_app,
                                            status='property_cycle_pass',
                                            cop_heating=r['cop_heating'],
                                            compressor_electrical_w=a.reference_condenser_duty_w/r['cop_heating'],
                                            condenser_pressure_pa=r['p_cond_pa'],
                                            discharge_temperature_k=r['t_discharge_k'],reason=''))
                else:
                    sensitivity.append(dict(fluid=f,eta_isentropic=eta,cond_approach_k=cond_app,
                                            status='rejected',reason=r['reason']))
    csvwrite(OUT/'wp7_efficiency_approach_sensitivity.csv',sensitivity)

    # A same-duty contrast only. No retrofit of WP2 controller performance claims.
    p=Parameters(hx_mode='duty_limiter');d=Disturbance()
    synthetic=output(State(406.20,403.15,.75),p,d)
    syn_cop=synthetic.q_hp/synthetic.p_el
    comparison=[]
    for r in nominal:
        if r['status']!='property_cycle_pass':continue
        comparison.append(dict(fluid=r['fluid'],t_source_k=333.15,t_header_k=406.2,
            heat_w=310000.,synthetic_electrical_w=310000./syn_cop,
            property_cycle_electrical_w=310000./r['cop_heating'],
            synthetic_cop=syn_cop,property_cycle_cop=r['cop_heating'],
            difference_electrical_w=310000./r['cop_heating']-310000./syn_cop,
            comparison_qualifier='different not-calibrated compressor maps at imposed same condenser duty'))
    csvwrite(OUT/'wp7_synthetic_vs_cycle.csv',comparison)

    storage=conditional_water_inventory(5000.,401.53,408.15,a)
    summary=dict(wp='WP7 property-only and idealized 4-state cycle screen',
                 coolprop_version=version,property_library='CoolProp HEOS refrigerants and IF97/HEOS Water',
                 model_status='uncalibrated, no manufacturer compressor/discharge limits; equipment feasibility NOT established',
                 candidate_fluids=list(FLUIDS),nominal_passing=fluids_pass,
                 nominal_rejected={r['fluid']:r['reason'] for r in nominal if r['status']=='rejected'},
                 map_success=[r['fluid'] for r in maps],map_failed=map_fail,
                 water_pressure_assumed_pa=a.service_header_pressure_pa,
                 source_grid_k=list(SOURCES),header_grid_k=list(HEADERS),n_grid=list(N),
                 ref_cycle_duty_w=a.reference_condenser_duty_w,
                 storage_conditional=storage,
                 assumptions=asdict(a),
                 max_heldout_q_relative_error=max(abs(x['relative_q_error']) for x in hold),
                 max_heldout_p_relative_error=max(abs(x['relative_p_error']) for x in hold),
                 water_if97_nominal_pa=next(x['saturation_pressure_if97_pa'] for x in water if x.get('t_hot_k')==406.2),
                 missing_evidence=['manufacturer-calibrated TESPy compressor and HX offdesign characteristics',
                                   'manufacturer compressor displacement/efficiency and envelopes',
                                   'refrigerant/pressure hardware design, approvals, leak safety',
                                   'real equipment COP and field calibration',
                                   'dynamic controller reruns with this property cycle instead of synthetic WP2 map'])
    (OUT/'wp7_summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    lines=[
        '# WP7 — Thermodynamic property/cycle feasibility screen (not hardware validation)','',
        f'**CoolProp:** {version}. Refrigerants HEOS; water IF97 with HEOS saturation cross-check.','',
        '## Nominal 60°C bulk source / 133.05°C header',
        'The refrigerant evaporates at 55°C and condenses at 138.05°C under **assumed 5 K** approaches.',
        'Compressor efficiency 0.75, suction superheat 5 K, condenser subcooling 4 K are **illustrative**, not calibrated.','',
        '| Refrigerant | Property cycle status | COP | Electrical for 310 kW heat | Condensing pressure (bar abs) | Discharge (°C) | Reason |',
        '|---|---|---:|---:|---:|---:|---|'
    ]
    for r in nominal:
        if r['status']=='property_cycle_pass':
            lines.append(f"| {r['fluid']} | property-screen pass | {r['cop_heating']:.3f} | {310/r['cop_heating']:.1f} kW | {r['p_cond_pa']/1e5:.2f} | {r['t_discharge_k']-273.15:.1f} | — |")
        else:lines.append(f"| {r['fluid']} | rejected | — | — | — | — | {r['reason']} |")
    lines+=['','## Water pressure and enthalpy','',
            f"At 133.05°C, IF97 water saturation pressure is {summary['water_if97_nominal_pa']/1e5:.3f} bar absolute.",
            'The 6 bar absolute liquid-loop pressure is only a numerical *assumption*, not an equipment design specification.',
            'Pressure design, phase margin during transients, and material certification are unverified.','',
            '## Conditional water energy inventory (not validated storage)','',
            f"At the assumed 6 bar absolute, 5000 kg of water between the hypothetical 128.38°C lower service limit and the unproven 135°C upper charging limit stores {storage['conditional_energy_kwh']:.2f} kWh of enthalpy difference by IF97.",
            'The upper charging state has NOT been shown achievable by any selected compressor/map; the figure MUST NOT be counted as usable flexible storage.','',
            '## Assumed compressor/flow reference' ,'',
            'The map forces 310 kW condenser heat at n=0.75 for each candidate and infers an equivalent suction volume flow.',
            'Offdesign flow scales with modulation and suction density, **not an EN12900/manufacturer displacement map**.',
            'A point is excluded when the underlying cycle fails. No out-of-grid extrapolation is allowed.','',
            '## Held-out interpolation errors','',
            '| Fluid | Max absolute thermal relative error | Max absolute electrical relative error |',
            '|---|---:|---:|']
    for r in maps:lines.append(f"| {r['fluid']} | {r['max_holdout_q_relative_error']:.4%} | {r['max_holdout_p_relative_error']:.4%} |")
    lines+=['', '## Hard scientific limitations','',
            '- A CoolProp equilibrium point is not proof of commercial availability, compressor compatibility, oil return, lubricant/material stability, allowable discharge temperature, refrigerant charge, safe pressure design or equipment performance.',
            '- A separate TESPy component-network and hypothetical-characteristic offdesign check runs in `run_wp7_completion.py`; it shares CoolProp EOS and is not manufacturer calibration.',
            '- Reference COP and electricity are steady-state cycle arithmetic; the legacy WP2–WP6 plant and its controller rankings are **unchanged**.',
            '- Extreme envelope failures remain in `wp7_envelope.csv`, not imputed or relabelled as passing.',
            '- The nominal required 310 kW was borrowed as a **synthetic heat duty** from WP2; nominal inferred compressor volume is not measured.',
            '', '## Source references','',
            '- [CoolProp high-level API](https://coolprop.org/coolprop/HighLevelAPI.html)',
            '- [CoolProp IF97 water](https://coolprop.org/fluid_properties/IF97.html)',
            '- [R1233zd(E) property model](https://coolprop.org/fluid_properties/fluids/R1233zd%28E%29.html)',
            '- [R1336mzz(Z) property model](https://coolprop.github.io/devdocs/fluid_properties/fluids/R1336mzz%28Z%29.html)',
            '- [TESPy design/offdesign network documentation](https://tespy.readthedocs.io/en/stable/building_blocks/networks.html)',
            '', 'Generated by `python scripts/run_wp7.py` from actual CoolProp, not hardcoded outputs.','']
    (OUT/'wp7_scientific_report.md').write_text('\n'.join(lines),encoding='utf-8')

    try:
        import matplotlib;matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(8,4.2))
        for fluid in fluids_pass:
            rows=[screen_point(fluid,333.15,x,a) for x in HEADERS]
            ax.plot([r['t_header_k']-273.15 for r in rows if r['status']=='property_cycle_pass'],
                    [r['cop_heating'] for r in rows if r['status']=='property_cycle_pass'],
                    marker='o',label=fluid)
        ax.set(xlabel='Actual hot-loop header temperature (°C)',ylabel='Idealized cycle COP (-)',
               title='WP7: property-calculated subcritical cycle (assumed efficiencies)')
        ax.legend();ax.grid(alpha=.25);fig.tight_layout()
        fig.savefig(OUT/'wp7_cop_temperature.png',dpi=150);plt.close(fig)
    except ImportError:
        pass
    print('WP7 CoolProp',version)
    print('NOMINAL PROPERTY SCREEN:')
    for r in nominal:
        if r['status']=='property_cycle_pass':
            print(f"  {r['fluid']}: PASS COP={r['cop_heating']:.5f} P_cond={r['p_cond_pa']/1e5:.3f} bar(a) T_discharge={r['t_discharge_k']-273.15:.2f} C")
        else:print(f"  {r['fluid']}: REJECT {r['reason']}")
    print(f'WATER IF97 saturation at 133.05C: {summary["water_if97_nominal_pa"]/1e5:.4f} bar(a), assumed loop=6 bar(a)')
    print('OFFDESIGN MAPS:',[r['fluid'] for r in maps],'held-out tests',len(hold),'max relative errors',
          summary['max_heldout_q_relative_error'],summary['max_heldout_p_relative_error'])
    print('SCIENTIFIC STATUS: property anchored, assumed compressor map, NOT equipment calibrated; separate TESPy follow-on experiment available')

if __name__=='__main__':main()
