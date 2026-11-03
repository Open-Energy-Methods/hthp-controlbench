"""Freeze corrected relay-peak L1 results without replacing historical WP3–WP5 data.

Run ONLY after run_wp3.py, run_wp3_robustness.py,
run_wp4_robustness.py, and run_wp5.py on the same checkout.
This script does not claim calibration or property-plant equivalence.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import csv
import hashlib
import json
import os
import shutil

from ht_hp_controlbench.core import Parameters
from ht_hp_controlbench.pi import identify_relay, tune_relay_tyreus_luyben

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'results'
BENCHMARK = 'L1_RelayPeak_v2'
DEST = SRC / BENCHMARK
FILES = (
    'wp3_pi_comparison.csv', 'wp3_identification.txt',
    'wp3_robustness_matrix.csv', 'wp3_robustness_summary.json',
    'wp3_robustness_comparison.png', 'wp3_pi_comparison.png',
    'wp4_robustness_matrix.csv', 'wp4_robustness_summary.json',
    'wp4_robustness_comparison.png',
    'wp5_analysis.json', 'wp5_case_comparison.csv',
    'wp5_paired_comparisons.csv', 'wp5_controller_summary.csv',
    'wp5_category_summary.csv', 'wp5_forecast_sensitivity.csv',
    'wp5_comparative_report.md', 'wp5_paired_tracking.png',
    'wp5_eligible_energy.png',
)

def read_csv(name: str) -> list[dict]:
    with (SRC / name).open(newline='') as f:
        return list(csv.DictReader(f))

def main() -> None:
    wp3=read_csv('wp3_pi_comparison.csv')
    wp4=read_csv('wp4_robustness_matrix.csv')
    if len(wp3)!=8:
        raise ValueError('expected exactly two HX modes × four PI gains')
    if len(wp4)!=100:
        raise ValueError('expected exactly 20 scenarios × five controllers')
    by_case=Counter(r['case'] for r in wp4)
    if len(by_case)!=20 or set(by_case.values())!={5}:
        raise ValueError('WP4 source comparison has missing or duplicate cases')
    with (SRC/'wp5_analysis.json').open() as f:
        wp5=json.load(f)
    if wp5.get('source_rows')!=100:
        raise ValueError('WP5 source rows do not match WP4')
    matrix_sha=hashlib.sha256((SRC/'wp4_robustness_matrix.csv').read_bytes()).hexdigest()
    if wp5.get('source_matrix_sha256')!=matrix_sha:
        raise ValueError('WP5 derived analysis does not correspond to latest WP4 data')
    relay=identify_relay(Parameters(hx_mode='no_bypass'))
    pi=tune_relay_tyreus_luyben(relay)
    if not (0.075 < relay.temperature_amplitude_k < .12):
        raise ValueError('WP3 relay is not the corrected peak-amplitude identifier')
    if not 0.15 < pi.kp < .25:
        raise ValueError('WP3 relay tune is outside corrected simulated envelope')
    observed=[r for r in wp3 if r['controller']=='Relay_TyreusLuyben']
    if len(observed)!=2 or any(abs(float(r['kp_command_per_K'])-pi.kp)>1e-10
                               for r in observed):
        raise ValueError('WP3 reported gain does not match newly identified relay')
    # Independent, one-scenario nonlinear replay ensures the 100-run WP4
    # ledger was regenerated using the *new* relay tune, not merely paired
    # with a corrected WP3 table and stale old-MPC/PI comparisons.
    from ht_hp_controlbench.robustness import declared_cases
    from ht_hp_controlbench.mpc import MPCConfig
    from ht_hp_controlbench.mpc_robustness import run_robust_mpc_case
    p0=Parameters(hx_mode='no_bypass')
    nominal_case=next(x for x in declared_cases(p0) if x.name=='nominal')
    mpc_cfg=MPCConfig(horizon=6,period_s=120,integration_step_s=20,
                      solver_backend='slsqp')
    check=run_robust_mpc_case(p0,nominal_case,method='relay_pi',
                    pi_settings=pi,cfg=mpc_cfg,integration_step_s=20.)
    nominal_saved=next(row for row in wp4 if row['case']=='nominal'
                       and row['method']=='relay_PI')
    if abs(check.summary()['iae_Ks']-float(nominal_saved['iae_Ks']))>1e-5:
        raise ValueError('WP4 nominal relay result does not match corrected PI gain')
    missing=[name for name in FILES if not (SRC/name).is_file()]
    if missing:raise FileNotFoundError(f'cannot snapshot missing inputs: {missing}')
    DEST.mkdir(parents=True,exist_ok=True)
    record=[]
    for name in FILES:
        dst=DEST/name
        shutil.copyfile(SRC/name,dst)
        record.append({'path':str(Path('results')/BENCHMARK/name),
                       'bytes':dst.stat().st_size,
                       'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()})
    manifest={
        'benchmark_id':BENCHMARK,
        'status':'CORRECTED_RELAY__SYNTHETIC_L1__NOT_EQUIPMENT_VALIDATED',
        'git_source_commit':os.getenv('GITHUB_SHA','local_not_pinned'),
        'historical_comparison':'Root results/wp3_*,wp4_robustness_*,wp5_* were produced before the A01 peak correction. These remain historical L1 values.',
        'relay_temperature_peak_k':relay.temperature_amplitude_k,
        'relay_period_s':relay.period_s,
        'relay_ku_approx':relay.ultimate_gain_u_per_k,
        'relay_kp_command_per_k':pi.kp,
        'relay_ki_command_per_ks':pi.ki,
        'wp4_run_count':len(wp4),
        'wp4_scenarios':len(by_case),
        'claim_boundary':'Same synthetic WP2 L1 plant, not WP7 real-fluid truth; no hardware PID/MPC performance certification.',
        'files':record,
    }
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    print(f'{BENCHMARK}: {len(record)} files, 100 WP4 simulations; relay Kp {pi.kp:.8f}')

if __name__ == '__main__':main()
