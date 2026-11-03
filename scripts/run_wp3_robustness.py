"""Reproduce the WP3 synthetic robustness matrix; no hidden case exclusions.

Command: python scripts/run_wp3_robustness.py (after pip install -e .[plots]).
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import os
from ht_hp_controlbench.benchmark import BENCHMARK_ID
import csv
import json
import math
import numpy as np

from ht_hp_controlbench.core import Parameters
from ht_hp_controlbench.pi import identify_step, tune_imc, identify_relay, tune_relay_tyreus_luyben
from ht_hp_controlbench.robustness import declared_cases, simulate_robust_pi


def main() -> None:
    root = Path(os.environ.get('HTHP_RESULTS_DIR','results'))
    root.mkdir(parents=True, exist_ok=True)
    nominal = Parameters(hx_mode='no_bypass')
    step = identify_step(nominal)
    relay = identify_relay(nominal)
    methods = {
        'IMC_lambda_0p5tau': tune_imc(step, 0.5),
        'IMC_lambda_1tau': tune_imc(step, 1.0),
        'IMC_lambda_2tau': tune_imc(step, 2.0),
        'Relay_TyreusLuyben': tune_relay_tyreus_luyben(relay),
    }
    cases = declared_cases(nominal)
    rows = []
    nominal_runs = {}
    severe_runs = {}
    for case in cases:
        for method, config in methods.items():
            try:
                run = simulate_robust_pi(nominal, config, case)
                row = run.summary()
                row['method'] = method
                row['error'] = ''
                if case.name == 'nominal':
                    nominal_runs[method] = run
                if case.name == 'severe_actuator_capacity_minus40pct':
                    severe_runs[method] = run
            except (ValueError, FloatingPointError, OverflowError) as exc:
                # An infeasible run is NOT dropped; recorded as a distinct failure row.
                row = {'case': case.name, 'controller': config.source, 'method': method,
                       'seed': case.seed, 'noise_sd_K': case.noise_sd_k,
                       'delay_updates': case.delay_updates, 'finite': False,
                       'error': f'{type(exc).__name__}: {exc}'}
            rows.append(row)

    with (root/'wp3_robustness_matrix.csv').open('w', newline='') as f:
        cols = list(dict.fromkeys(k for row in rows for k in row))
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)

    # Within-scenario comparison avoids conflating model mismatch with method.
    by_case = defaultdict(list)
    for row in rows:
        by_case[row['case']].append(row)
    wins={method:0 for method in methods}
    losses={method:0 for method in methods}
    for group in by_case.values():
        finite=[r for r in group if r.get('finite') and isinstance(r.get('iae_Ks'),(int,float))]
        if len(finite) == len(methods):
            winner=min(finite,key=lambda r:r['iae_Ks'])['method']
            wins[winner]+=1
        else:
            for r in group:
                if not r.get('finite'):
                    losses[r['method']]+=1

    summary = {
        'scientific_status': 'synthetic uncalibrated numerical PI sensitivity only',
        'benchmark_id': BENCHMARK_ID,
        'nominal_pi_gains': {k: {'kp':v.kp,'ki':v.ki} for k,v in methods.items()},
        'measurement_model': 'Gaussian white noise at control samples; integer-sample delay; no estimator',
        'parameter_model': 'one-at-a-time perturbations with fixed nominal PI gains and bias',
        'controller_tuning_origin': 'all methods identified on nominal no-bypass plant',
        'noise_seed_paired_between_methods': True,
        'integration_step_s': 10., 'control_period_s': 60., 'duration_s': 14_400.,
        'scenario_count': len(cases), 'method_count': len(methods),
        'run_count': len(rows),
        'failure_count': sum(not r.get('finite',False) for r in rows),
        'lowest_iae_wins': wins,
        'failures': [r for r in rows if not r.get('finite',False)],
        'baseline_metrics': {method:{k:float(row[k]) for k in (
            'iae_Ks','rmse_K','service_unserved_kWh','electrical_kWh','max_abs_error_K')}
            for method in methods for row in rows
            if row['case']=='nominal' and row['method']==method and row.get('finite')},
        'worst_case_metrics_by_method': {},
    }
    for method in methods:
        good=[r for r in rows if r['method']==method and r.get('finite')]
        if good:
            summary['worst_case_metrics_by_method'][method]={
                'max_iae_Ks':float(max(r['iae_Ks'] for r in good)),
                'max_rmse_K':float(max(r['rmse_K'] for r in good)),
                'max_service_unserved_kWh':float(max(r['service_unserved_kWh'] for r in good)),
                'max_bound_fraction':float(max(r['sample_fraction_at_command_bounds'] for r in good)),
                'max_iae_case':max(good,key=lambda r:r['iae_Ks'])['case'],
            }
    (root/'wp3_robustness_summary.json').write_text(json.dumps(summary, indent=2,allow_nan=False)+'\n')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        # Paired nominal vs severe capacity-derated response and hard command bounds.
        fig, axes=plt.subplots(2,2,figsize=(12,8),sharex='col')
        for method in methods:
            for col, runs in enumerate((nominal_runs,severe_runs)):
                if method not in runs:continue
                run=runs[method];sim=run.simulation
                axes[0,col].plot(sim.times/3600,sim.states[:,1]-273.15,label=method)
                axes[1,col].plot(sim.times/3600,sim.commands,label=method)
        for col, title in enumerate(('Nominal plant','Capacity derated 40%')):
            axes[0,col].set_title(title)
            axes[0,col].set_ylabel('Actual buffer temperature [°C]')
            axes[1,col].set_ylabel('Applied command [0–1]')
            axes[1,col].set_xlabel('Simulation time [h]')
            axes[1,col].set_ylim(-.02,1.02)
            axes[0,col].grid(alpha=.25); axes[1,col].grid(alpha=.25)
        axes[0,1].legend(fontsize=7,loc='best')
        fig.suptitle('WP3 simulated PI robustness — synthetic, not hardware validation')
        fig.tight_layout()
        fig.savefig(root/'wp3_robustness_comparison.png',dpi=145)
        plt.close(fig)
    except ImportError:
        pass
    print(f'WP3 robustness: {len(cases)} cases x {len(methods)} settings = {len(rows)} rows; '
          f'{summary["failure_count"]} errors; IAE wins={wins}')
    for method,v in summary['worst_case_metrics_by_method'].items():
        print(method, v)


if __name__ == '__main__':
    main()