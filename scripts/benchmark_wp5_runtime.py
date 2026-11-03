"""Optional platform-specific timing benchmark; not a controller solve-time guarantee.

Measures *complete simulated-case wall time*, including RK4 plant integration,
observer propagation, QP assembly, solver and Python overhead. Use median/range
across repetitions; CPU and software versions must be logged. Do not pool with
WP5 performance metrics or claim industrial real-time readiness.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import json
import platform
import statistics
import sys
import time
import numpy as np
import scipy
from ht_hp_controlbench.core import Parameters
from ht_hp_controlbench.robustness import declared_cases
from ht_hp_controlbench.pi import identify_step, tune_imc, identify_relay, tune_relay_tyreus_luyben
from ht_hp_controlbench.mpc_robustness import run_robust_mpc_case
from ht_hp_controlbench.mpc import MPCConfig


def main():
    p=argparse.ArgumentParser();p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--duration-s',type=int,default=7200)
    p.add_argument('--out',type=Path,default=Path('results/wp5_runtime_local.json'))
    a=p.parse_args()
    if a.repeats<1 or a.duration_s<3600 or a.duration_s%120:raise ValueError('invalid test budget')
    model=Parameters(hx_mode='no_bypass')
    cases={c.name:c for c in declared_cases(model)}
    gains={'IMC_0p5':tune_imc(identify_step(model),.5),
           'relay_PI':tune_relay_tyreus_luyben(identify_relay(model))}
    methods=(('IMC_0p5','imc_pi'),('relay_PI','relay_pi'),('MPC_persistence','mpc'))
    records=[]
    for case in ('nominal','noise_0.30K_seed_11','heatpump_capacity_minus20pct'):
        for method,mode in methods:
            timings=[]
            for _ in range(a.repeats):
                start=time.perf_counter()
                res=run_robust_mpc_case(model,cases[case],method=mode,
                    pi_settings=gains[method] if method in gains else gains['IMC_0p5'],
                    cfg=MPCConfig(horizon=6,period_s=120.,integration_step_s=20.),
                    duration_s=a.duration_s,integration_step_s=20.)
                elapsed=time.perf_counter()-start
                if not res.summary()['finite']:raise RuntimeError('nonfinite timing run')
                timings.append(elapsed)
            records.append({'case':case,'method':method,'runs':timings,
                'median_wall_s':statistics.median(timings),
                'min_wall_s':min(timings),'max_wall_s':max(timings),
                'controller_updates':int(a.duration_s/120)})
    result={'interpretation':'end-to-end Python simulated-run timing, NOT median QP solve-time or real-time guarantee',
        'platform':platform.platform(),'python':sys.version.split()[0],
        'cpu_logical_count':__import__('os').cpu_count(), 'numpy':np.__version__,
        'scipy':scipy.__version__,'repeats':a.repeats,'duration_s':a.duration_s,
        'records':records}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Runtime benchmark records',len(records),'output',a.out)

if __name__=='__main__':main()
