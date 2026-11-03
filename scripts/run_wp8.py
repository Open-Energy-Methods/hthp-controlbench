#!/usr/bin/env python3
"""Generate the WP8 24-hour fully service-gated synthetic tariff comparison.

Run from repository root: python scripts/run_wp8.py [--full]
Dependencies CoolProp (realfluid extra), numpy/scipy; matplotlib for PNG.
No synthetic property fallback. Every real result is stamped equipment-unverified.
"""
from __future__ import annotations
import argparse,csv,json,sys
from dataclasses import asdict,replace
from pathlib import Path

from ht_hp_controlbench.core import Disturbance
from ht_hp_controlbench.realfluid import build_cycle_map,backend_version
from ht_hp_controlbench.thermo_feasibility import HypotheticalEquipmentLimits
from ht_hp_controlbench.storage_flexibility import (
    SyntheticTariff,FlexSettings,scan_reachable_band,compare_flexibility,
    simulate_24h,physical_threshold)

RESULTS=Path(__file__).resolve().parent.parent/'results'


def rows_to_csv(path,rows):
    if not rows:return
    cols=list(dict.fromkeys(k for x in rows for k in x))
    with path.open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader()
        for x in rows:writer.writerow({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in x.items()})


def concise(result):
    return {k:result.get(k) for k in (
       'status','service_qualified_fraction','spec_unserved_kwh','electricity_kwh',
       'condenser_heat_kwh','process_heat_kwh','loss_heat_kwh','cost_eur',
       'final_storage_delta_kwh','max_buffer_k','min_buffer_k',
       'max_command_slew','residual_energy_j','failures','equipment_verified')}


def collect(model,cfg,tariff,label,limits=None,source_k=333.15,plot=False):
    pair=compare_flexibility(model,cfg,tariff,limits=limits,
                             d=Disturbance(t_source=source_k),store_trajectory=plot)
    base=pair['baseline'];flex=pair['flexibility']
    return pair,dict(case=label,mass_kg=cfg.mass_kg,price_high_eur_kwh=tariff.high_eur_kwh,
                     price_low_eur_kwh=tariff.low_eur_kwh,high_duration_minutes=(tariff.high_end_h-tariff.high_start_h)*60.,
                     source_c=source_k-273.15,limit_case='hypothetical_24bar_145C' if limits else 'no_oem_limits',
                     status=pair['status'],reasons=';'.join(pair['reasons']),
                     cost_saving_eligible_eur=pair['eligible_cost_saving_eur'],
                     raw_cost_difference_eur=pair['raw_cost_difference_eur'],
                     electricity_difference_kwh=pair['raw_electricity_difference_kwh'],
                     baseline_cost_eur=base.get('cost_eur'),flex_cost_eur=flex.get('cost_eur'),
                     baseline_electricity_kwh=base.get('electricity_kwh'),flex_electricity_kwh=flex.get('electricity_kwh'),
                     baseline_service_fraction=base.get('service_qualified_fraction'),
                     flex_service_fraction=flex.get('service_qualified_fraction'),
                     baseline_unserved_kwh=base.get('spec_unserved_kwh'),
                     flex_unserved_kwh=flex.get('spec_unserved_kwh'),
                     baseline_final_storage_kwh=base.get('final_storage_delta_kwh'),
                     flex_final_storage_kwh=flex.get('final_storage_delta_kwh'),
                     flex_max_buffer_c=flex.get('max_buffer_k',273.15)-273.15,
                     baseline_status=base['status'],flex_status=flex['status'],
                     equipment_verified=False)


def plot_trace(base,flex,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,4))
    for a,n in ((base,'Fixed WP3 PI'),(flex,'Tariff-scheduled PI (heuristic)')):
        t=[r['time_h'] for r in a['trajectory']]
        ax.plot(t,[r['buffer_c'] for r in a['trajectory']],label=n)
    ax.axhline(128.4,color='0.4',linestyle='--',label='Approx. service threshold')
    ax.set(xlabel='Hour of synthetic 24-h day',ylabel='Buffer temperature (°C)',
           title='Finite mixed-water buffer: conditional model only')
    ax.legend(loc='best',fontsize=8);ax.grid(alpha=.25)
    fig.tight_layout();fig.savefig(path,dpi=160);plt.close(fig)


def plot_cost(base,flex,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7,4))
    names=['Fixed WP3 PI','Scheduled PI heuristic']
    costs=[base['cost_eur'],flex['cost_eur']]
    bars=ax.bar(names,costs)
    ax.bar_label(bars,labels=[f'€{c:.2f}' for c in costs],padding=3)
    ax.set(ylabel='Electricity cost (EUR), synthetic prices',
           title='Only credit a difference if service and terminal storage match')
    ax.grid(axis='y',alpha=.25);ax.set_ylim(0,max(costs)*1.15)
    fig.tight_layout();fig.savefig(path,dpi=160);plt.close(fig)


def plot_case_savings(rows,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names=[x['case'].replace('_',' ') for x in rows]
    savings=[x['cost_saving_eligible_eur'] for x in rows]
    fig,ax=plt.subplots(figsize=(9,max(3,0.55*len(rows)+1)))
    y=list(range(len(rows)))
    ax.barh(y,[0 if v is None else v for v in savings])
    for i,v in enumerate(savings):
        ax.text(0.04 if v is None else v + (0.03 if v>=0 else -0.03),i,
                'Not creditable' if v is None else f'€{v:+.2f}',
                ha=('left' if v is None or v>=0 else 'right'),va='center',fontsize=8)
    ax.set_yticks(y,names);ax.invert_yaxis();ax.axvline(0,color='0.4',linewidth=.8)
    ax.set(xlabel='Conditional 24-h cost saving (EUR); negative = extra cost',
           title='Same-service, terminal-matched cases only')
    ax.grid(axis='x',alpha=.2)
    all_valid=[v for v in savings if v is not None]
    rng=max((abs(v) for v in all_valid),default=.5)
    ax.set_xlim(-max(.6,rng*.6),max(.8,rng*1.4))
    fig.tight_layout();fig.savefig(path,dpi=160);plt.close(fig)


def main(full=False):
    RESULTS.mkdir(exist_ok=True)
    model=build_cycle_map('R1233zd(E)',[328.15,333.15,338.15],
                          [403.15,406.2,413.15],[.5,.75,1.0])
    nominal=FlexSettings(dt_s=60.)
    tariff=SyntheticTariff()
    stringent=HypotheticalEquipmentLimits(p_cond_max_pa=2.4e6,discharge_max_k=418.15)
    inventory=[]
    for mass in (2500.,5000.,10000.):
        for label,limits in (('EOS_only__NO_OEM',None),('hypothetical_24bar_145C',stringent)):
            b=scan_reachable_band(model,mass_kg=mass,nodes=31,limits=limits)
            inventory.append(dict(mass_kg=mass,case=label,status=b['status'],
                                  proposed_upper_k=b['proposed_upper_k'],lower_k=b['lower_k'],
                                  max_usable_k=b['highest_checked_usable_k'],
                                  conditional_storage_kwh=b['enthalpy_kwh'],
                                  ideal_300kw_minutes=b['max_uninterrupted_full_duty_minutes'],
                                  stopped_reason=b['stopped_reason'],equipment_verified=False))
    rows=[]
    pair,record=collect(model,nominal,tariff,'reference_15min_event',plot=True)
    if pair['baseline']['status']!='complete':
        raise RuntimeError('WP8 baseline reference did not complete 24 hours; no reference comparison possible')
    rows.append(record)
    if full:
        cases=[
         ('small_buffer_2500kg',replace(nominal,mass_kg=2500.),tariff,None,333.15),
         ('large_buffer_10000kg',replace(nominal,mass_kg=10000.),tariff,None,333.15),
         ('long_peak_45min',nominal,replace(tariff,high_end_h=6.75),None,333.15),
         ('flat_tariff',nominal,replace(tariff,low_eur_kwh=.16,high_eur_kwh=.16),None,333.15),
         ('hypothetical_ratings_24bar_145C',nominal,tariff,stringent,333.15),
         ('cold_source_55C',nominal,tariff,None,328.15),
        ]
        for label,cfg,price,lim,source in cases:
            _,record=collect(model,cfg,price,label,lim,source)
            rows.append(record)
            print(label,record['status'],record['reasons'],record['cost_saving_eligible_eur'],flush=True)
    rows_to_csv(RESULTS/'wp8_storage_bands.csv',inventory)
    rows_to_csv(RESULTS/'wp8_price_scenarios.csv',rows)
    rows_to_csv(RESULTS/'wp8_reference_trace.csv',[
        dict(policy=policy,**r) for policy,result in
        (('baseline_PI',pair['baseline']),('scheduled_PI',pair['flexibility']))
        for r in (result.get('trajectory') or [])])
    plot_trace(pair['baseline'],pair['flexibility'],RESULTS/'wp8_buffer_trace.png')
    plot_case_savings(rows,RESULTS/'wp8_scenario_savings.png')
    if pair['baseline']['status']=='complete' and pair['flexibility']['status']=='complete':
        plot_cost(pair['baseline'],pair['flexibility'],RESULTS/'wp8_cost_comparison.png')
    summary=dict(work_package='WP8',status='conditional_numerical_research__NOT_EQUIPMENT_VALIDATED',
        refrigerant='R1233zd(E)',coolprop_version=backend_version(),
        model_reference='WP7 uncalibrated CoolProp compressor map and WP2 finite-flow HX',
        price_kind='transparent synthetic EUR/kWh, not actual Nordic prices or tariffs',
        schema='same-service and terminal inventory strict credit gate',
        settings=asdict(nominal),tariff=asdict(tariff),
        service_threshold_k=physical_threshold(),
        reference=dict(status=pair['status'],reasons=pair['reasons'],
                       creditable_cost_saving_eur=pair['eligible_cost_saving_eur'],
                       raw_cost_difference_eur=pair['raw_cost_difference_eur'],
                       raw_electricity_difference_kwh=pair['raw_electricity_difference_kwh'],
                       baseline=concise(pair['baseline']),flex=concise(pair['flexibility'])),
        inventory_sensitivity=inventory,scenarios=rows,
        scope_limits=[
            'No manufacturer compressor characteristic, rating, or real pressure equipment certification',
            'No measured price series, tax, grid tariff, demand charge, oil, stratification or motor auxiliary power',
            'No actual financial return; all € values are synthetic conditional model outputs',
            'Price-scheduled PI heuristic is not self-optimising control or economic MPC',
            'A full 24h run does not constitute long-term lifetime, maintenance or cycling assessment',
            'Numerical integration assumes well-mixed constant-pressure water and 5 MJ/K header capacity',
            'If simulated physical service fails, savings are withheld even if the bill falls'])
    (RESULTS/'wp8_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# WP8 — Storage and tariff flexibility (synthetic, equipment unverified)','',
           '## Thermodynamic and scope gates','',
           f'- CoolProp {summary["coolprop_version"]}, R1233zd(E), nominal source 60°C, 6 bar(a) assumed water loop.',
           '- Finite process HX service threshold is **'+f'{summary["service_threshold_k"]-273.15:.2f}°C'+'**, not 120°C.',
           '- Storage enthalpy uses IF97 h(T,p); every counted cost benefit requires 100% specification service,',
           '  no declared property/rating constraint failure, and final inventory agreement within 0.5 kWh.',
           '- Compressor electrical power depends on water-header temperature through the WP7 property map;',
           '  high-temperature precharge may **increase total electricity** even if a synthetic tariff bill decreases.',
           '', '## 24-h reference comparison','',
           f'- Outcome: **{pair["status"]}**; reasons: {pair["reasons"]}.',
           f'- Baseline electricity: **{pair["baseline"].get("electricity_kwh",float("nan")):.3f} kWh**; scheduled: **{pair["flexibility"].get("electricity_kwh",float("nan")):.3f} kWh**.',
           f'- Baseline synthetic cost: **€{pair["baseline"].get("cost_eur",float("nan")):.3f}**; scheduled: **€{pair["flexibility"].get("cost_eur",float("nan")):.3f}**.',
           f'- Additional scheduled electricity versus baseline: **{-pair["raw_electricity_difference_kwh"]:.3f} kWh** (positive means more kWh) if both runs completed.',
           f'- Conditionally creditable saving: **{pair["eligible_cost_saving_eur"]} EUR**, if eligible; otherwise NONE.',
           '- Neither a reduced bill nor an acceptable service fraction constitutes an *actual industrial* saving.',
           '', '## Disclosed scenarios','',
           '| Case | Status | Eligible simulated saving (EUR) | Service fraction (schedule) | Note |',
           '|---|---|---:|---:|---|']
    for x in rows:
        eligible=x['cost_saving_eligible_eur']
        lines.append(f'| {x["case"]} | {x["status"]} | {"—" if eligible is None else f"{eligible:.3f}"} | '+
                     (f'{x["flex_service_fraction"]:.4f}' if x['flex_service_fraction'] is not None else '—')+
                     f' | {x["reasons"] or "conditional only"} |')
    lines+=['','## Storage sensitivity','',
             '| Mass (kg) | Constraint gate | Conditional inventory (kWh) | Reachability |',
             '|---:|---|---:|---|']
    for x in inventory:
        lines.append(f'| {x["mass_kg"]:.0f} | {x["case"]} | {x["conditional_storage_kwh"]:.3f} | {x["status"]}: {x["stopped_reason"]} |')
    lines+=['','## Scientific interpretation','',
       '- An *unlimited-rating conditional model* and a *hypothetically capped scenario* are not evidence of actual equipment reachability.',
       '- There is no demonstrated equipment-verified electricity-price arbitrage without a manufacturer capacity and pressure/discharge map.',
       '- Small buffer energy relative to 300 kW process heat restricts the peak event length; larger tanks can help only with finite recharge capacity.',
       '- A flat price or a long service-failing peak is a falsification control; no monetary saving is credited.',
       '- The scheduled PI policy uses advance knowledge of synthetic tariff events and must not be relabelled SOC.',
       '', '### External scientific provenance', '',
       '- IAPWS IF97 revised industrial water formulation: https://iapws.org/technical-guidance/release/IF97-Rev',
       '- CoolProp 8.0 IF97 backend: https://coolprop.org/fluid_properties/IF97.html',
       '- Previous WP7 physical-service, CoolProp compressor and TESPy offdesign results: docs/WP7_RESEARCH_CLOSEOUT.md',
       '', '### Reproduction','',
       '`python scripts/run_wp8.py --full` (requires `pip install -e ".[plots,realfluid]"`).',
       'Generated figures: `results/wp8_buffer_trace.png`, `results/wp8_cost_comparison.png`, and `results/wp8_scenario_savings.png`.','']
    (RESULTS/'wp8_scientific_report.md').write_text('\n'.join(lines))
    print('WP8 reference:',pair['status'],'creditable_saving_eur=',pair['eligible_cost_saving_eur'],flush=True)
    print('WP8 inventory mass/limit combinations',len(inventory),'tariff scenarios',len(rows),flush=True)
    return summary

if __name__=='__main__':
    pa=argparse.ArgumentParser();pa.add_argument('--full',action='store_true')
    args=pa.parse_args()
    main(args.full)
