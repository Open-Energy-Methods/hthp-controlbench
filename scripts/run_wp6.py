"""Reproduce WP6 source-linked synthetic active-set/SOC research outputs."""
from __future__ import annotations
import csv,json,hashlib
from pathlib import Path
from itertools import product
from dataclasses import asdict,replace
import numpy as np
from ht_hp_controlbench.core import Parameters,Disturbance
from ht_hp_controlbench.soc import (SOCParameters,offline_optimum,baseline_dof_audit,
    train_constant_cvs,train_piecewise_soc,derive_local_stationarity_cv,
    evaluate_cv,evaluate_piecewise_cv,service_temperature_min,
    evaluate_at_buffer_temperature)
from ht_hp_controlbench.soc_dynamic import run_dynamic_soc
from ht_hp_controlbench.pi import identify_step,tune_imc
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results';OUT.mkdir(exist_ok=True)


def write_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(rows)


def run():
    p=Parameters(hx_mode='duty_limiter');c=SOCParameters()
    train=[Disturbance(t_return=273.15+ret,t_source=273.15+src) for ret,src in product((85.,90.,95.,100.),(45.,52.5,60.,67.5,75.))]
    hold=[Disturbance(t_return=273.15+ret,t_source=273.15+src) for ret,src in product((87.5,92.5,97.5),(47.5,57.5,72.5))]
    fixed=train_constant_cvs(p,c,train)
    fitted=train_piecewise_soc(p,c,train)
    hessian=derive_local_stationarity_cv(p,c,Disturbance(t_source=333.15,t_return=368.15))
    policies={'global_constant_r':fixed,'piecewise_empirical_CV':fitted,'piecewise_stationarity_CV':hessian}
    rows=[]
    for name,model in policies.items():
        sample=(evaluate_cv(p,c,hold,model) if name=='global_constant_r' else evaluate_piecewise_cv(p,c,hold,model))
        for item in sample:
            obj=dict(item);obj['candidate']=name
            # Uniform schema, including failed/infeasible policies.
            obj['policy_feasible']=obj.pop('candidate_feasible',obj.get('policy_feasible'))
            obj['opt_r']=obj.pop('r_opt',obj.get('opt_r'))
            obj['policy_r']=obj.pop('r_candidate',obj.get('policy_r'))
            rows.append(obj)
    feasible={name:[r for r in rows if r['candidate']==name and r['policy_feasible']] for name in policies}
    summary={name:{'count':len(part),'failed':len(hold)-len(part),
          'mean_loss_w':float(np.mean([r['loss_w'] for r in part])) if part else None,
          'max_loss_w':max((r['loss_w'] for r in part),default=None),
          'max_loss_pct':max((r['loss_pct'] for r in part),default=None)} for name,part in feasible.items()}
    grid=[]
    for d in train+hold:
        opt=offline_optimum(p,c,d)
        grid.append({'partition':'training' if d in train else 'held_out',
                     't_return_c':d.t_return-273.15,'t_source_c':d.t_source-273.15,
                     'r_opt':opt.r if opt else None,'active_constraints':';'.join(opt.active) if opt else 'infeasible',
                     'unconstrained_economic_dof':int(opt is not None and 'pump_max' not in opt.active and 'pump_min' not in opt.active),
                     'service_w':opt.q_service_w if opt else None,
                     'compressor_w':opt.p_compressor_w if opt else None,
                     'pump_w':opt.p_pump_w if opt else None,
                     'total_electric_w':opt.p_total_w if opt else None})
    # WP6 model-uncertainty challenge: keep the *trained nominal* controlled variables
    # frozen while the true synthetic equipment coefficients change. Reoptimise
    # only the oracle to obtain equal-service economic losses for each actual model.
    sensitivity=[]
    changed=[('pump_power_minus30pct',replace(c,pump_nominal_w=.7*c.pump_nominal_w)),
             ('pump_power_plus30pct',replace(c,pump_nominal_w=1.3*c.pump_nominal_w)),
             ('hot_film_resistance_0.25',replace(c,hot_film_resistance_fraction=.25)),
             ('hot_film_resistance_0.55',replace(c,hot_film_resistance_fraction=.55)),
             ('hot_UA_flow_exponent_0.6',replace(c,hot_film_flow_exponent=.6)),
             ('hot_UA_flow_exponent_1.0',replace(c,hot_film_flow_exponent=1.0))]
    for variant,actual_c in changed:
        for name,model in policies.items():
            records=(evaluate_cv(p,actual_c,hold,model) if name=='global_constant_r'
                     else evaluate_piecewise_cv(p,actual_c,hold,model))
            for record in records:
                sensitivity.append({'variant':variant,'candidate':name,**record})
    # Price multiplies steady electricity use; no storage/time coordination here.
    d_nom=Disturbance();o=offline_optimum(p,c,d_nom)
    tariffs=[{'electricity_price_eur_per_kwh':pr,'optimal_r':o.r,
              'cost_eur_per_hour':o.p_total_w*pr/1000.} for pr in (.08,.2,.5)]
    # Verify full-2D formulation agrees with buffer-bound active reduction on a small deterministic grid.
    audits=[]
    for d in hold[:4]:
        o=offline_optimum(p,c,d)
        vals=[]
        for bump in (0.,0.25,0.5,1.):
            try:vals.append(evaluate_at_buffer_temperature(p,c,d,o.r,o.tb_k+bump).p_total_w)
            except ValueError:pass
        audits.append({'t_source_c':d.t_source-273.15,'t_return_c':d.t_return-273.15,
                       'J_at_min_w':o.p_total_w,'J_at_backoffs_w':vals,
                       'positive_backoff_raises_cost':all(v>=o.p_total_w-1e-5 for v in vals)})
    # Dynamic/noisy tests are explicitly distinct from the classic steady-state SOC theory.
    dyn_p=Parameters(hx_mode='duty_limiter');dyn_c=replace(c,buffer_margin_k=2.)
    settings=tune_imc(identify_step(Parameters()),.5)
    schedules={
      'mild_steps':[(0.,Disturbance()),(3600.,Disturbance(t_return=365.15)),
                    (7200.,Disturbance(t_return=364.15)),(10800.,Disturbance(t_return=366.15))],
      'stress_return_jump':[(0.,Disturbance()),(3600.,Disturbance(t_return=365.15)),
                            (7200.,Disturbance(t_return=368.15)),(10800.,Disturbance())],
    }
    dyn_rows=[]
    for name,seq in schedules.items():
        for noise,delay,seed in ((0.,0.,0),(.2,120.,23)):
            for policy in ('offline_rto','regime_soc','constant_soc'):
                model=hessian if policy=='regime_soc' else fixed
                try:
                    result,_=run_dynamic_soc(dyn_p,dyn_c,model,seq,settings,policy,
                         sensor_noise_k=noise,sensor_delay_s=delay,seed=seed)
                    row=asdict(result)
                    row.update({'scenario':name,'noise_k':noise,'delay_s':delay,'seed':seed,'status':'completed'})
                except ValueError as ex:
                    row={'scenario':name,'noise_k':noise,'delay_s':delay,'seed':seed,'policy':policy,
                         'status':'infeasible','reason':str(ex)}
                dyn_rows.append(row)
    # Dynamic differences cannot be called economic losses without equal service;
    # record explicit compliance test before considering any comparison.
    for row in dyn_rows:
        if row['status']!='completed':continue
        ref=next((r for r in dyn_rows if r['scenario']==row['scenario'] and r['noise_k']==row['noise_k']
                 and r['delay_s']==row['delay_s'] and r['policy']=='offline_rto'),None)
        row['equal_service_eligible']=bool(ref and ref['status']=='completed' and
             ref['spec_unserved_kwh']<1e-5 and row['spec_unserved_kwh']<1e-5)
        row['signed_dynamic_electric_delta_kwh']=row['electrical_kwh']-ref['electrical_kwh'] if ref and ref['status']=='completed' else None
    source={'status':'synthetic offline steady-state SOC screening + exploratory dynamic noisy pilot',
         'baseline_dof':baseline_dof_audit(), 'pump_extension':asdict(c),
         'study_design':{'train_d_source_c':[45,52.5,60,67.5,75],'train_d_return_c':[85,90,95,100],
                         'heldout_source_c':[47.5,57.5,72.5], 'heldout_return_c':[87.5,92.5,97.5],
                         'predeclared_split':True, 'training_points':len(train),'heldout_points':len(hold),
                         'tariff_note':'positive price scalar cannot change steady optimal r when all consumption is multiplied and no time coupling exists'},
         'CV_models':policies,'heldout_summary':summary,
         'assumption_sensitivity':{'variants':[name for name,_ in changed],
                                  'records':len(sensitivity),
                                  'max_feasible_loss_w_by_policy':{name:max((r['loss_w'] for r in sensitivity if r['candidate']==name and r['loss_w'] is not None),default=None) for name in policies},
                                  'infeasible_policy_counts':{name:sum(r['candidate']==name and not r.get('policy_feasible',r.get('candidate_feasible',False)) for r in sensitivity) for name in policies}},
         'active_count_training':{key:sum(key in (r['active_constraints'] or '') for r in grid if r['partition']=='training') for key in ('pump_max','service')},
         'tariff_sweep':tariffs,'buffer_elimination_audit':audits,
         'dynamic_scope':'PI regulation + hypothetical pump-flow lag, matched initial conditions; offline RTO is current-disturbance optimiser, not future-optimal dynamic control',
         'dynamic_results':dyn_rows,
         'limitations':['No equipment pump curves or HX calibration','Hot-side pump flow actuator is hypothetical and adds new authority',
              'Steady economic policy assumes zero storage/time coupling and positive prices','CV is based on local Hessian or training fit; not proven globally optimum',
              'Dynamic tests use selected deterministic schedules; no dynamic/noisy SOC guarantee','Reported cost comparison only if both methods meet service specification',
              'Hardware, fluids, pump operating envelope and economic tariffs remain synthetic']}
    write_csv(OUT/'wp6_offline_optima.csv',grid)
    write_csv(OUT/'wp6_assumption_sensitivity.csv',sensitivity)
    write_csv(OUT/'wp6_heldout_losses.csv',rows)
    write_csv(OUT/'wp6_dynamic_scenarios.csv',dyn_rows)
    (OUT/'wp6_summary.json').write_text(json.dumps(source,indent=2,allow_nan=False,default=float)+'\n')
    report=['# WP6: Self-optimising-control screening and active constraints', '',
       '**Status:** Executed synthetic steady-state study and exploratory dynamic/noisy-plant pilot. NOT physical validation.', '',
       '## Two separate actuator models', '',
       'The published WP2 reference has just one manipulated compressor command. At the qualifying economic optimum, minimum service is active, so the residual free steady-state economic DOF is **zero**. Its local process bypass is an *algebraic service valve*, not an HTHP optimiser DOF. This is a defensible negative SOC result for the original tested configuration.', '',
       'The optional WP6 study explicitly introduces hot-loop circulation ratio `r` as a **second hypothetical actuator**, with an assumed pump electricity `P_pump(r)=2500 r^3 W`, a hot-side film-resistance share of 0.4, and a `r^0.8` hot-side heat-transfer correlation. These are research assumptions, NOT measured pump/HX curves. Process-side bypass remains local to service; the HTHP optimiser controls `r`, **not** the bypass fraction.', '',
       '## Economic problem and active constraints', '',
       '`min_{r,T_b,n} J=P_compressor(n,T_h,T_src)+P_pump(r)` subject to `Q_process>=Q_requested`, `T_proc,out>=T_required`, two steady thermal balances, hot-loop flow/temperature and compressor bounds. For a fixed feasible `r`, the tested synthetic objective rises with buffer-temperature backoff; hence `T_b=T_b,min,service(r,d)` and `n` is determined by energy balance, leaving **one** economic DOF `r` in interior regions. The reduction is tested against the 2D objective, not assumed globally.', '',
       'Positive electricity price simply scales the steady objective. With no thermal storage scheduling or time coupling, the optimal steady `r` is unchanged by tariff level. This project does **not** claim demand-response savings from static SOC.', '',
       f'**Training grid:** {len(train)} points. **Held-out grid:** {len(hold)} points. Synthetic settings fully declared in `SOCParameters` and JSON.', '',
       '## Candidate controlled variables (CV)', '',
       '1. `CV=r` fixed at a training-selected constant (no on-line reoptimisation).',
       '2. Per-active-region empirical `CV=r+β_return ΔT_return+β_source ΔT_source` constant, with separate `r=r_max` constraint control; coefficients fitted to **training** offline optima.',
       '3. Per-active-region *stationarity-derived* linear CV with `β_d=J_{rd}/J_{rr}` at an interior anchor and a separately selected pump-upper constraint. This follows the local first-order optimality condition; it is not an implementation or proof of the Manum–Skogestad nullspace result.', '',
       'Candidates are held at constant CV setpoints within regions. Setpoint/active-region switching is explicit, with no hidden online RTO for policies under test. The offline optimum is recomputed for each held-out point only as a **counterfactual** to quantify loss.', '',
       '### Held-out synthetic steady-state economic loss', '',
       '| CV policy | Feasible / 9 | Mean loss (W) | Max loss (W) | Max relative loss (%) |',
       '|---|---:|---:|---:|---:|']
    for name,r in summary.items():
        report.append(f'| {name} | {r["count"]}/9 | {r["mean_loss_w"]:.3f} | {r["max_loss_w"]:.3f} | {r["max_loss_pct"]:.7f}% |' if r['count'] else f'| {name} | 0/9 | n/a | n/a | n/a |')
    report+=['', '### Model-mismatch uncertainty (fixed policy; reoptimised oracle)', '',
             'The nominal CVs are **not refitted** when pump power, hot-side film resistance, or the hot-flow UA exponent changes. Six synthetic equipment variants × nine held-out disturbances × three policies are evaluated. All missing feasibility is retained explicitly in the CSV.', '',
             '| Policy | Maximum feasible loss across uncertainty variants (W) | Infeasible policy trials |',
             '|---|---:|---:|']
    for name in policies:
        mx=source['assumption_sensitivity']['max_feasible_loss_w_by_policy'][name]
        fails=source['assumption_sensitivity']['infeasible_policy_counts'][name]
        report.append(f'| {name} | {mx:.3f} | {fails} / 54 |' if mx is not None else f'| {name} | n/a | {fails} / 54 |')
    report+=['','All electric powers are steady-state synthetic W. Loss is **J_policy − J_opt** at the **same process service**, and never assigned to infeasible points. Relative loss uses the positive total-electric-power objective, not a tariff-weighted saving estimate. The training/held-out split is artificial and not a probabilistic population sample.', '',
             '### Active sets', '',
             f'Of {len(train)} training operating points, {source["active_count_training"]["pump_max"]} bind the upper hot-loop pump limit; the remaining {len(train)-source["active_count_training"]["pump_max"]} have an interior economic circulation optimum. All feasible steady economic optima bind the minimum service requirement. This is an explicit constraint-following region plus a separately evaluated free economic DOF, rather than relabelling a tariff schedule as SOC.', '',
             '## Exploratory dynamic/noisy-plant pilot', '',
             'The flow actuator has a first-order lag (`tau_r=75s`) and command-step limit, while compressor modulation and the two thermal states retain WP2 dynamics. A **single measured buffer temperature** controls the PI compressor loop; flow measurement, process return and source temperatures are assumed available. Noise and FIFO measurement delay are applied identically to compared policies. The `offline_rto` reference reoptimises using the **current** measured disturbance and does not know the future. Dynamic trials use a 2 K quality backoff not present in the ideal steady economic optimum.', '',
             '| Disturbance schedule | Noise / measurement delay | Policy | Electric energy (kWh) | Spec-unserved heat (kWh) | Service-compliant fraction |',
             '|---|---|---|---:|---:|---:|']
    for row in dyn_rows:
        if row['status']=='completed':
            report.append(f'| {row["scenario"]} | {row["noise_k"]} K / {row["delay_s"]} s | {row["policy"]} | {row["electrical_kwh"]:.3f} | {row["spec_unserved_kwh"]:.3f} | {row["service_compliant_fraction"]:.3f} |')
        else:report.append(f'| {row["scenario"]} | {row["noise_k"]} K / {row["delay_s"]} s | {row["policy"]} | **INFEASIBLE** | n/a | n/a |')
    report+=['','A difference in electricity use under **unequal heat service** is not an economic saving. The ideal-steady offline-optimal result and the dynamic online-RTO comparator are separate reference quantities; signed dynamic electricity differences need not be nonnegative. The Hessian-based CV is only locally stationarity-preserving, and service quality under disturbances must be independently demonstrated.', '',
              '## Reproducibility and limitations', '',
              '- Run `python scripts/run_wp6.py` and `python -m unittest discover -s tests`. The WP6 script emits the complete WP6 tables, JSON, figures and report and never edits the earlier WP2–WP5 datasets.',
              '- `results/wp6_offline_optima.csv`: full training and hold-out active-constraint ledger.',
              '- `results/wp6_assumption_sensitivity.csv`: 162 fixed-policy out-of-envelope synthetic equipment checks.',
              '- `results/wp6_heldout_losses.csv`: every policy/heldout pair including infeasible flags.',
              '- `results/wp6_dynamic_scenarios.csv`: paired dynamic cases, quality compliance and energy balance.',
              '- `results/wp6_summary.json`: parameter/provenance ledger, CVs, loss summary, excluded results.',
              '- Quality-defined unserved heat treats a below-specification outlet as an unqualified process interval even when a small amount of physical heat is missing; these are deliberately separate metrics and must not be conflated.',
              '- `results/wp6_active_set_map.png` and `results/wp6_heldout_loss.png` are descriptive figures generated by the same script.',
              '- This is a synthetic model extension with no pump manufacturer curves, fluid screening, lab data or calibrated UA/pressure envelope; it does not establish real thermal performance or formal closed-loop robust stability.',
              '- Skogestad (2000), DOI `10.1016/S0959-1524(00)00023-8` and Manum & Skogestad (2012), DOI `10.1016/j.jprocont.2012.02.015` establish classic steady-state SOC principles. The latter presents a **steady-state/quadratic** active-set formulation; the dynamic/noisy nonlinear case here is independent exploratory work, not validated by that citation.', '']
    (OUT/'wp6_scientific_report.md').write_text('\n'.join(report)+'\n')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(9,5))
        by_source=sorted(set(x['t_source_c'] for x in grid))
        for src in by_source:
            pts=sorted([x for x in grid if x['partition']=='training' and x['t_source_c']==src],key=lambda x:x['t_return_c'])
            ax.plot([x['t_return_c'] for x in pts],[x['r_opt'] for x in pts],marker='o',label=f'Source {src:g}°C')
        ax.axhline(c.r_max,linestyle='--',linewidth=1,label='Hot-loop pump upper constraint')
        ax.set(xlabel='Process return temperature (°C)',ylabel='Optimal synthetic hot-loop flow ratio',title='WP6: offline active-set transition in synthetic circulation economics')
        ax.legend(loc='best',fontsize=8);fig.tight_layout();fig.savefig(OUT/'wp6_active_set_map.png',dpi=150);plt.close(fig)
        fig,ax=plt.subplots(figsize=(9,5))
        names=list(summary)
        ax.bar(range(len(names)),[summary[n]['max_loss_w'] for n in names])
        ax.set_xticks(list(range(len(names))),['Constant flow','Empirical CV','Stationarity CV'])
        ax.set(ylabel='Maximum held-out economic loss (W)',title='WP6: held-out loss, equal-service feasible points only')
        ax.set_yscale('symlog',linthresh=.01);fig.tight_layout();fig.savefig(OUT/'wp6_heldout_loss.png',dpi=150);plt.close(fig)
    except ImportError:
        pass
    print('WP6:',len(train),'training',len(hold),'held-out',len(rows),'loss rows',len(dyn_rows),'dynamic runs')
    print('CV outcomes',summary)
    print('Dynamic status',{k:sum(r.get('status')==k for r in dyn_rows) for k in ('completed','infeasible')})
    return source

if __name__=='__main__':run()
