"""Reproduce WP4 robustness study with paired single-sensor evidence.

Command: python scripts/run_wp4_robustness.py
The 20 scenario names mirror WP3 but PI is re-run at MPC's 120-s update
period. This is a new fair clock, NOT a comparison to WP3's 60-s CSV.
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import csv,json
import numpy as np
from ht_hp_controlbench.core import Parameters
from ht_hp_controlbench.pi import identify_step,tune_imc,identify_relay,tune_relay_tyreus_luyben
from ht_hp_controlbench.robustness import declared_cases
from ht_hp_controlbench.mpc import MPCConfig
from ht_hp_controlbench.mpc_robustness import run_robust_mpc_case


def main():
    root=Path('results');root.mkdir(exist_ok=True)
    nominal=Parameters(hx_mode='no_bypass')
    step=identify_step(nominal)
    relay=identify_relay(nominal)
    pi={
       'IMC_lambda_0p5tau':tune_imc(step,.5),
       'IMC_lambda_1tau':tune_imc(step,1.),
       'IMC_lambda_2tau':tune_imc(step,2.),
       'relay_PI':tune_relay_tyreus_luyben(relay)
    }
    cases=declared_cases(nominal)
    cfg=MPCConfig(horizon=6,period_s=120,integration_step_s=20,
                  solver_backend='slsqp')
    methods=[*pi,'MPC_persistence_120s']
    results=[]
    for case in cases:
        for method in methods:
            gains=pi.get(method,pi['IMC_lambda_0p5tau'])
            strategy='mpc' if method.startswith('MPC_') else 'relay_pi' if method=='relay_PI' else 'imc_pi'
            try:
                run=run_robust_mpc_case(nominal,case,method=strategy,pi_settings=gains,cfg=cfg,integration_step_s=20.)
                row=run.summary();row['method']=method;row['error']='';row['controller_sampling_s']=120
            except (ValueError,RuntimeError,FloatingPointError,OverflowError) as exc:
                row={'case':case.name,'method':method,'finite':False,
                     'error':type(exc).__name__+': '+str(exc)}
            result=row.copy()
            result['status_counts']=json.dumps(result.get('status_counts',{}),sort_keys=True)
            results.append(result)
    # Predeclared extra information experiment, never blended into fair ranking.
    future_runs=[]
    for name in ('nominal','heatpump_capacity_minus20pct'):
        case=next(c for c in cases if c.name==name)
        run=run_robust_mpc_case(nominal,case,method='mpc',pi_settings=pi['IMC_lambda_0p5tau'],
                                cfg=cfg,advance_forecast=True,integration_step_s=20.)
        future_runs.append({'case':name,'method':'MPC_perfect_future_disturbance',
                             **run.summary()})
    with (root/'wp4_robustness_matrix.csv').open('w',newline='') as f:
        cols=list(dict.fromkeys(k for r in results for k in r))
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(results)
    by_case=defaultdict(list)
    for row in results:by_case[row['case']].append(row)
    wins={m:0 for m in methods}
    for case,group in by_case.items():
        finite=[r for r in group if r.get('finite')]
        if len(finite)==len(methods):
            wins[min(finite,key=lambda r:r['iae_Ks'])['method']]+=1
    summary={
       'scientific_status':'synthetic partial-observation robustness, not certified robust MPC',
       'measurement_budget':'one noisy/delayed buffer-temperature sensor shared by all methods; MPC other states predicted from nominal model',
       'disturbance_budget':'MPC persistence of current source/return; separately report perfect-future advantage',
       'sampling':{'sensor_period_s':60,'controller_period_s':120,'duration_s':14400,'integration_step_s':20},
       'cases':[c.name for c in cases],'method_names':methods,
       'case_count':len(cases),'runs':len(results),'failed':sum(not r.get('finite',False) for r in results),
       'lowest_iae_case_wins':wins,
       'nominal':{r['method']:r for r in results if r['case']=='nominal'},
       'severe_capacity':{r['method']:r for r in results if r['case']=='severe_actuator_capacity_minus40pct'},
       'complete_set':all(len(group)==len(methods) for group in by_case.values()),
       'forecast_assisted_extras':future_runs,
       'controller_failures':[r for r in results if not r.get('finite')],
       'source_parameters':'synthetic WP2 default parameters; no hardware calibration',
    }
    (root/'wp4_robustness_summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    # No best-controller assertion here; reports rankings + fallback incidence.
    print(f'WP4 robustness: {len(cases)} cases × {len(methods)} methods = {len(results)} runs; '
          f'{summary["failed"]} failed; wins {wins}')
    for name in ('nominal','measurement_delay_180s','combined_noise_0.3K_delay_180s_capacity_minus20pct',
                 'severe_actuator_capacity_minus40pct'):
        print(name)
        for r in by_case[name]:
            print('  ',r['method'], 'IAE',round(r.get('iae_Ks',float('nan')),2),
                  'fallback',r.get('pi_fallbacks'), 'TV',round(r.get('command_variation',float('nan')),2))
    try:
        import matplotlib;matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        labels=('nominal','measurement_delay_180s','heatpump_capacity_minus20pct',
                'combined_noise_0.3K_delay_180s_capacity_minus20pct')
        fig,axes=plt.subplots(1,2,figsize=(13,5))
        for method in ('IMC_lambda_0p5tau','relay_PI','MPC_persistence_120s'):
            vals=[];moves=[]
            for case in labels:
                r=next(r for r in by_case[case] if r['method']==method)
                vals.append(r.get('iae_Ks',float('nan')))
                moves.append(r.get('command_variation',float('nan')))
            x=np.arange(len(labels));offset={'IMC_lambda_0p5tau':-.25,'relay_PI':0.,'MPC_persistence_120s':.25}[method]
            axes[0].bar(x+offset,vals,.24,label=method)
            axes[1].bar(x+offset,moves,.24,label=method)
        for ax in axes:
            ax.set_xticks(np.arange(len(labels)),[l.replace('_','\n') for l in labels],fontsize=6)
            ax.grid(axis='y',alpha=.25)
        axes[0].set_ylabel('IAE [K s] (lower better)')
        axes[1].set_ylabel('Total command variation (dimensionless)')
        axes[0].legend(fontsize=8)
        fig.suptitle('Synthetic one-sensor PI vs MPC robustness; same 120-s controller period')
        fig.tight_layout();fig.savefig(root/'wp4_robustness_comparison.png',dpi=150);plt.close(fig)
    except ImportError:
        pass

if __name__=='__main__':main()