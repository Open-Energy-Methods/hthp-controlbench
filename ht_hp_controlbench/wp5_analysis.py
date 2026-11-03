"""WP5 pre-specified, service-gated and source-audited PI/MPC comparison.

Input is the saved synthetic WP4 20-case x 5-method CSV. This module does NOT
rerun, recalibrate, or adjust the nonlinear plant or controller. Rankings are
conditional descriptive statistics, not probability estimates or certifications.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import csv
import json
import statistics

from .core import Parameters
from .robustness import declared_cases

MPC = "MPC_persistence_120s"
RELAY = "relay_PI"
IMC_FAST = "IMC_lambda_0p5tau"
METHODS = ("IMC_lambda_0p5tau", "IMC_lambda_1tau", "IMC_lambda_2tau", RELAY, MPC)
METRICS = ("iae_Ks", "rmse_K", "max_abs_error_K", "electrical_kWh", "command_variation",
           "service_unserved_kWh", "physical_energy_shortfall_kWh", "service_qualified_fraction",
           "sample_fraction_at_command_bounds", "max_command_slew", "max_energy_residual_J")
MINIMIZE = ("iae_Ks", "electrical_kWh", "command_variation")
# This is a declared reporting gate, NOT an equipment guarantee or legal threshold.
# It distinguishes floating-point quadrature residue from process-service failure.
QUALIFIED_SERVICE_EPS_KWH = 1e-6
QUALIFIED_SERVICE_FRACTION = 1 - 1e-9


def category(case: str) -> str:
    if case == 'nominal': return 'nominal'
    if case.startswith('noise_'): return 'seeded sensor noise'
    if case.startswith('measurement_delay_'): return 'sensor delay'
    if case.startswith('buffer_mass_') or case.startswith('header_buffer_') or case.startswith('process_UA_'):
        return 'thermal parameter change'
    if case in ('heatpump_capacity_minus20pct', 'heatpump_capacity_plus20pct',
                'severe_actuator_capacity_minus40pct'): return 'capacity change'
    if case.startswith('combined_'): return 'combined disturbance'
    if case.startswith('temporary_setpoint_'): return 'setpoint excursion'
    if case.startswith('bypass_'): return 'bypass and UA'
    raise ValueError(f'unknown case category: {case}')


def load_matrix(path: Path) -> list[dict]:
    with Path(path).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def finite_float(row: dict, key: str) -> float:
    try: x = float(row[key])
    except (KeyError, ValueError, TypeError) as e: raise ValueError(f'invalid {key} for {row.get("case")}/{row.get("method")}') from e
    if not isfinite(x): raise ValueError(f'nonfinite {key} for {row.get("case")}/{row.get("method")}')
    return x


def validate_matrix(rows: list[dict], *, expected_cases: tuple[str, ...] | None = None) -> list[dict]:
    """Reject missing, duplicate, mismatched-information and fabricated success rows."""
    if expected_cases is None:
        expected_cases = tuple(c.name for c in declared_cases(Parameters(hx_mode='no_bypass')))
    pairs={(c,m) for c in expected_cases for m in METHODS}
    if len(rows) != len(pairs):
        raise ValueError(f'expected {len(pairs)} rows but received {len(rows)}')
    if len({(r.get('case'),r.get('method')) for r in rows}) != len(rows):
        raise ValueError('duplicate case/method pair')
    if {(r.get('case'),r.get('method')) for r in rows} != pairs:
        raise ValueError('missing or unexpected case/method pair')
    clean=[]
    for row in rows:
        r=dict(row)
        if row.get('finite') not in (True,False,'True','False'):
            raise ValueError('finite must be a strict boolean, not a truthy string')
        r['finite']=row['finite'] in (True,'True')
        r['category']=category(r['case'])
        if not r['finite']:
            if not str(row.get('error','')).strip():
                raise ValueError('failed numerical run must include its error description')
            r['service_pass']=False
            clean.append(r)
            continue
        for key in METRICS: r[key]=finite_float(row,key)
        for key in ('decisions','accepted_mpc','pi_fallbacks','controller_sampling_s','seed','sensor_delay_s'):
            try: r[key] = int(row[key])
            except (KeyError,ValueError,TypeError) as e: raise ValueError(f'invalid {key}') from e
        r['sensor_noise_sd_K']=finite_float(row,'sensor_noise_sd_K')
        r['fallback_fraction']=finite_float(row,'fallback_fraction')
        if str(row.get('error','')).strip() not in ('','nan'):
            raise ValueError('finite run contains unexplained error')
        if r['controller_sampling_s']!=120 or r['decisions']!=120:
            raise ValueError('unmatched controller clock or run length')
        if r['seed']<0 or r['sensor_noise_sd_K']<0 or r['sensor_delay_s']<0:
            raise ValueError('invalid sensor scenario')
        if not (0<=r['fallback_fraction']<=1) or not (0<=r['service_qualified_fraction']<=1):
            raise ValueError('fraction outside [0,1]')
        if min(r[k] for k in ('iae_Ks','rmse_K','electrical_kWh','command_variation','service_unserved_kWh','physical_energy_shortfall_kWh'))< -1e-8:
            raise ValueError('negative physical or objective metric')
        if r['accepted_mpc']<0 or r['pi_fallbacks']<0:
            raise ValueError('negative decision counts')
        if r['method']==MPC:
            if r['accepted_mpc']+r['pi_fallbacks']!=r['decisions']:
                raise ValueError('MPC decisions do not reconcile')
        elif r['accepted_mpc']!=0 or r['pi_fallbacks']!=0:
            raise ValueError('PI incorrectly reports MPC decision counts')
        if abs(r['fallback_fraction']-r['pi_fallbacks']/r['decisions'])>1e-9:
            raise ValueError('fallback fraction inconsistent with counts')
        if not isinstance(r.get('information_mode'),str) or 'one delayed/noisy buffer-temperature measurement' not in r['information_mode']:
            raise ValueError('information-mode mismatch')
        r['service_pass']=(r['service_qualified_fraction']>=QUALIFIED_SERVICE_FRACTION
            and r['service_unserved_kWh']<=QUALIFIED_SERVICE_EPS_KWH
            and r['physical_energy_shortfall_kWh']<=QUALIFIED_SERVICE_EPS_KWH)
        clean.append(r)
    for case in expected_cases:
        rr=[r for r in clean if r['case']==case]
        if any(not r['finite'] for r in rr):
            continue  # failures stay in the dataset, never silently imputed
        for k in ('seed','sensor_noise_sd_K','sensor_delay_s','controller_sampling_s','information_mode'):
            if len({str(r[k]) for r in rr})!=1:
                raise ValueError(f'unmatched {k} for case {case}')
    return clean


def _median(values): return float(statistics.median(values)) if values else None


def safe_pct(numerator: float, baseline: float) -> float | None:
    """Percentage difference, negative means MPC has lower error/cost."""
    return None if abs(baseline)<1e-12 else 100.0*(numerator-baseline)/baseline


def dominates(a: dict,b: dict,tol: float=1e-9) -> bool:
    """Strict multi-objective dominance among service-compliant runs only."""
    if not (a['service_pass'] and b['service_pass']): return False
    better_or_equal=all(a[k]<=b[k]+tol*max(1.,abs(b[k])) for k in MINIMIZE)
    at_least_one=any(a[k]<b[k]-tol*max(1.,abs(b[k])) for k in MINIMIZE)
    return better_or_equal and at_least_one


def analyze(rows: list[dict], *, expected_cases: tuple[str,...] | None=None) -> dict:
    if expected_cases is None: expected_cases=tuple(c.name for c in declared_cases(Parameters(hx_mode='no_bypass')))
    rr=validate_matrix(rows,expected_cases=expected_cases)
    by_case={c:{r['method']:r for r in rr if r['case']==c} for c in expected_cases}
    outcome=[];pairs=[];category_stats=defaultdict(list)
    tracking_wins=Counter(); qualified_wins=Counter(); pareto_counts=Counter()
    compliant_all=0; eligible_pairs=0
    for name in expected_cases:
        group=by_case[name]; every=list(group.values()); cat=category(name)
        complete=all(r['finite'] for r in every)
        raw=min(every,key=lambda r:r['iae_Ks'])['method'] if complete else None
        if raw is not None: tracking_wins[raw]+=1
        eligible=[r for r in every if r['finite'] and r['service_pass']]
        gate_all=len(eligible)==len(METHODS)
        if gate_all:compliant_all+=1
        winner=min(eligible,key=lambda r:r['iae_Ks'])['method'] if eligible else None
        if winner is not None and complete:qualified_wins[winner]+=1
        frontier=[r['method'] for r in eligible if not any(dominates(o,r) for o in eligible if o is not r)]
        for method in frontier:pareto_counts[method]+=1
        mpc=group[MPC];relay=group[RELAY]
        eligible_pair=mpc['service_pass'] and relay['service_pass'];eligible_pairs+=int(eligible_pair)
        if not complete:
            outcome.append({'case':name,'category':cat,'numerical_complete':False,
                'failed_methods':';'.join(r['method'] for r in every if not r['finite']),
                'all_five_service_pass':False,'service_pass_count':len(eligible),
                'raw_iae_winner':None,'eligible_iae_winner':winner,
                'pareto_service_pass_methods':';'.join(frontier),
                'MPC_qualified_for_energy_comparison':False})
            # Do not manufacture comparisons or wins from incomplete source data.
            category_stats[cat].append(outcome[-1])
            continue
        comparison={
            'case':name,'category':cat,'numerical_complete':True,'failed_methods':'','all_five_service_pass':gate_all,
            'service_pass_count':len(eligible), 'raw_iae_winner':raw,
            'eligible_iae_winner':winner,'pareto_service_pass_methods':';'.join(frontier),
            'MPC_iae_Ks':mpc['iae_Ks'],'relay_iae_Ks':relay['iae_Ks'],
            'MPC_service_pass':mpc['service_pass'],'relay_service_pass':relay['service_pass'],
            'MPC_minus_relay_iae_Ks':mpc['iae_Ks']-relay['iae_Ks'],
            'MPC_minus_relay_iae_pct':safe_pct(mpc['iae_Ks'],relay['iae_Ks']),
            'MPC_minus_relay_electricity_kWh':mpc['electrical_kWh']-relay['electrical_kWh'],
            'MPC_minus_relay_command_variation':mpc['command_variation']-relay['command_variation'],
            'MPC_pi_fallbacks':mpc['pi_fallbacks'],
            'MPC_unserved_kWh':mpc['service_unserved_kWh'],
            'relay_unserved_kWh':relay['service_unserved_kWh'],
            'MPC_qualified_for_energy_comparison':eligible_pair,
            'MPC_energy_interpretation':('same service quality gate passed' if eligible_pair
                                         else 'DO NOT interpret as efficiency gain: non-compliant service'),
        }
        outcome.append(comparison);category_stats[cat].append(comparison)
        for pi in METHODS:
            if pi==MPC:continue
            baseline=group[pi]
            paired_ok=mpc['service_pass'] and baseline['service_pass']
            pairs.append({
                'case':name,'category':cat,'baseline':pi,'candidate':MPC,
                'both_service_pass':paired_ok,
                'iae_candidate_Ks':mpc['iae_Ks'],'iae_baseline_Ks':baseline['iae_Ks'],
                'delta_iae_Ks':mpc['iae_Ks']-baseline['iae_Ks'],
                'delta_iae_pct':safe_pct(mpc['iae_Ks'],baseline['iae_Ks']),
                'delta_electrical_kWh':mpc['electrical_kWh']-baseline['electrical_kWh'],
                'delta_command_variation':mpc['command_variation']-baseline['command_variation'],
                'candidate_service_unserved_kWh':mpc['service_unserved_kWh'],
                'baseline_service_unserved_kWh':baseline['service_unserved_kWh'],
                'candidate_physical_shortfall_kWh':mpc['physical_energy_shortfall_kWh'],
                'baseline_physical_shortfall_kWh':baseline['physical_energy_shortfall_kWh'],
                'conditional_energy_comparison':paired_ok,
                'candidate_fallback_events':mpc['pi_fallbacks'],
            })
    medians=[]
    for m in METHODS:
        meth=[r for r in rr if r['method']==m and r['finite']]
        medians.append({'method':m,'cases':len(meth),'service_pass_cases':sum(r['service_pass'] for r in meth),
                        'median_iae_Ks':_median([r['iae_Ks'] for r in meth]),
                        'median_electrical_kWh':_median([r['electrical_kWh'] for r in meth]),
                        'median_command_variation':_median([r['command_variation'] for r in meth]),
                        'max_service_unserved_kWh':max(r['service_unserved_kWh'] for r in meth),
                        'total_fallback_events':sum(r['pi_fallbacks'] for r in meth),
                        'raw_iae_wins':tracking_wins[m],
                        'eligible_iae_wins':qualified_wins[m],
                        'service_qualified_pareto_cases':pareto_counts[m]})
    grouped=[]
    for cat,cs in sorted(category_stats.items()):
        eligible=[c for c in cs if c['MPC_qualified_for_energy_comparison']]
        grouped.append({'category':cat,'cases':len(cs),'qualifying_MPC_relay_pairs':len(eligible),
            'MPC_lower_IAE_cases':sum(c.get('MPC_minus_relay_iae_Ks',0)<0 for c in cs),
            'median_paired_IAE_pct_all_cases':_median([c['MPC_minus_relay_iae_pct'] for c in cs if c.get('MPC_minus_relay_iae_pct') is not None]),
            'median_energy_delta_only_compliant_kWh':_median([c['MPC_minus_relay_electricity_kWh'] for c in eligible])})
    mp=[r for r in rr if r['method']==MPC]
    valid_mpc=[r for r in mp if r['service_pass']]
    failed=[{'case':r['case'],'method':r['method'],'error':r['error']} for r in rr if not r['finite']]
    return {'methods':METHODS,'cases':expected_cases,'source_rows':len(rr),
            'raw_iae_wins':dict(tracking_wins),'service_qualified_iae_wins':dict(qualified_wins),
            'all_methods_service_pass_cases':compliant_all,'mpc_relay_service_matched_cases':eligible_pairs,
            'MPC_total_fallback_events':sum(r['pi_fallbacks'] for r in mp if r['finite']),
            'MPC_total_decisions':sum(r['decisions'] for r in mp if r['finite']),
            'MPC_fallback_cases':[r['case'] for r in mp if r['finite'] and r['pi_fallbacks']>0],
            'MPC_service_pass_cases':len(valid_mpc),
            'MPC_service_fail_cases':[r['case'] for r in mp if r['finite'] and not r['service_pass']],
            'failed_runs':failed,'completed_runs':sum(r['finite'] for r in rr),
            'per_case':outcome,'paired':pairs,'controller_summary':medians,'categories':grouped,
            'metadata':{'quality_gate':{'min_quality_fraction':QUALIFIED_SERVICE_FRACTION,
                 'max_unserved_kWh':QUALIFIED_SERVICE_EPS_KWH,'max_physical_shortfall_kWh':QUALIFIED_SERVICE_EPS_KWH},
                'descriptive_only':'20 deliberately selected synthetic scenarios are not an independent random sample',
                'cost':'electricity kWh, no price series or verified service-value function',
                'complexity':'solver CPU time absent from input; report separate platform-specific execution benchmark',
                'physical_status':'unvalidated synthetic HTHP plant, no real-fluid compressor calibration'}}
