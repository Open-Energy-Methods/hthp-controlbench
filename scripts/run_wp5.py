"""Produce WP5 paper-style tables and figures from the *unchanged* WP4 result ledger.

Reproduction: python scripts/run_wp5.py
No model fitting, parameter search or reclassification after reading the outcomes.
"""
from __future__ import annotations
from pathlib import Path
import csv
import json

from ht_hp_controlbench.wp5_analysis import analyze, load_matrix, METHODS, MPC, RELAY

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'results'
SOURCE=RESULTS/'wp4_robustness_matrix.csv'


def csv_save(path, rows):
    if not rows:raise ValueError('cannot write empty result set')
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def fmt(value, digits=2):
    if value is None:return 'n/a'
    return f'{value:,.{digits}f}'


def report(data):
    cs={r['method']:r for r in data['controller_summary']}
    n=len(data['cases']);miss=len(data['failed_runs'])
    lines=['# WP5 — Comparative assessment: PI versus constrained MPC', '',
      '**Scope:** synthetic, uncalibrated HTHP-shaped thermal plant; versioned WP4 scenario matrix. No industrial validation, real-fluid-cycle calibration or formal stability certificate.', '',
      '## Protocol and scope of the comparison','',
      '- **Input:** exactly 20 declared WP3/WP4 scenarios × 5 fixed controllers, with a common nonlinear truth plant, one noisy/delayed buffer-temperature observation, 60-s sensing and 120-s command interval. MPC uses a nominal-model predictor for unmeasured states; PI does not need this additional model.',
      '- **Future information:** this primary 100-run dataset uses disturbance persistence for MPC, not perfect future disturbance forecasts. Perfect-forecast sensitivity belongs in a separate analysis.',
      '- **Tuning:** the four PI gains and MPC weights are carried over from WP3/WP4. They are *not* retuned or re-optimised using the cases here.',
      '- **Primary outcome:** IAE in K·s; secondary outcomes are electrical energy (kWh), total command variation, specification-qualified service, physical thermal shortfall, actual MPC fallback events and solver acceptance.',
      '- **Predeclared service gate for conditional electricity comparison:** quality fraction ≥ 1−10⁻⁹, unserved specification energy ≤10⁻⁶ kWh and physical heat shortfall ≤10⁻⁶ kWh for **both** controllers. These are analytical bookkeeping tolerances, not industrial process or safety acceptance limits.',
      '- **Missing/failing runs:** failures are preserved and explicitly reported. No finite-error comparison is imputed for an incomplete case. There are no such failures in this saved matrix.',
      '- **Statistical status:** this is a deliberately selected, correlated set of deterministic scenarios and three noise seeds per noise level. Case counts and group medians are descriptive, **not** empirical probabilities, confidence intervals or significance tests.',
      '- **Energy is not cost:** no measured tariffs, emission factors, or equivalent service-value accounting exist in the matrix. No economic ranking is claimed.',
      '', '## Headline results', '',
      f'- **Complete runs:** {data["completed_runs"]}/{data["source_rows"]} ({miss} failed).',
      f'- **Raw lowest IAE:** MPC {data["raw_iae_wins"].get(MPC,0)}/{n}, relay PI {data["raw_iae_wins"].get(RELAY,0)}/{n}. These raw counts include scenarios where *nobody* met service.',
      f'- **Service-qualified lowest IAE:** MPC {data["service_qualified_iae_wins"].get(MPC,0)}, relay PI {data["service_qualified_iae_wins"].get(RELAY,0)} across {n-len([r for r in data["per_case"] if r["service_pass_count"]==0])} cases with at least one qualified method.',
      f'- **MPC versus relay PI, both meeting service gate:** {data["mpc_relay_service_matched_cases"]}/{n} cases.',
      f'- **All five controllers meet service gate:** {data["all_methods_service_pass_cases"]}/{n} cases.',
      f'- **MPC accepted/fallback decisions:** {data["MPC_total_decisions"]-data["MPC_total_fallback_events"]}/{data["MPC_total_decisions"]} accepted updates, {data["MPC_total_fallback_events"]} PI fallback events, all in '+(', '.join(data['MPC_fallback_cases']) or 'no case')+'.',
      '', '### Controller summary (case-wise descriptive medians)', '',
      '| Controller | Qualified cases | Median IAE (K·s) | Median electricity (kWh) | Median command TV | Raw IAE wins | Service-qualified Pareto appearances |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for m in METHODS:
        r=cs[m]
        lines.append(f'| `{m}` | {r["service_pass_cases"]}/{n} | {fmt(r["median_iae_Ks"])} | {fmt(r["median_electrical_kWh"])} | {fmt(r["median_command_variation"],3)} | {r["raw_iae_wins"]} | {r["service_qualified_pareto_cases"]} |')
    lines += ['', '### Selected paired cases: MPC minus relay-derived PI', '',
      'Negative ΔIAE means less tracking error for MPC; positive Δelectricity means higher electrical use. Electrical deltas are **not** efficiency claims when service is not equivalent.', '',
      '| Case | ΔIAE (%) | Δelectricity (kWh) | Δcommand TV | Service compliant for both? | MPC fallback count |',
      '|---|---:|---:|---:|---|---:|']
    selected=['nominal','measurement_delay_180s','noise_0.30K_seed_23',
              'heatpump_capacity_minus20pct','process_UA_minus20pct',
              'severe_actuator_capacity_minus40pct','combined_noise_0.3K_delay_180s_capacity_minus20pct',
              'combined_noise_0.3K_delay_180s_bypass','bypass_UA_flow_exponent_0.8']
    idx={r['case']:r for r in data['per_case']}
    for name in selected:
        r=idx[name]
        lines.append(f'| `{name}` | {fmt(r["MPC_minus_relay_iae_pct"],1)} | {fmt(r["MPC_minus_relay_electricity_kWh"],2)} | {fmt(r["MPC_minus_relay_command_variation"],2)} | {"yes" if r["MPC_qualified_for_energy_comparison"] else "NO — noncompliant"} | {r["MPC_pi_fallbacks"]} |')
    lines += ['', '### Failure modes and conditional interpretation', '',
      '1. **Loss of process heat-transfer UA (`process_UA_minus20pct`):** despite successful numerical completion, process service fails across the controller set. Lower electricity would be uninterpretable as an efficiency improvement. Temperature tracking (buffer setpoint IAE) and process service are different objectives; a controller may achieve one without the other.',
      '2. **Severe compressor derating (`severe_actuator_capacity_minus40pct`):** physical supply is insufficient. The MPC reports 48 PI fallback events out of 120 decisions; other methods also fail required service. This is an equipment-feasibility limit, not controller success.',
      '3. **Moderate capacity model mismatch:** relay PI outperforms MPC in IAE for ±20% compressor-capacity cases. No claim of globally superior predictive control is supported.',
      '4. **Measurement delay/noise:** MPC performs better on IAE in the isolated delay and seeded noise cases, but it is not universally superior under combined noise, delay and capacity mismatch.',
      '5. **Actuator effort and electrical energy:** nominal MPC consumes approximately 0.67 kWh more than relay PI over the simulated four-hour horizon. Lower IAE does not establish electricity savings. The actuator TV proxy is not a calibrated wear metric.',
      '6. **Prediction/observer limits:** model-state reconstruction is open-loop nominal propagation with sampled buffer-temperature correction, not a statistically consistent estimator or proof of detection of bias, outage or drifting noise.',
      '', '### Scenario categories (unweighted, descriptive only)', '',
      '| Category | Cases | Paired qualified MPC vs relay | MPC lower IAE (raw) | Median paired ΔIAE (%) |',
      '|---|---:|---:|---:|---:|']
    for r in data['categories']:
        lines.append(f'| {r["category"]} | {r["cases"]} | {r["qualifying_MPC_relay_pairs"]} | {r["MPC_lower_IAE_cases"]} | {fmt(r["median_paired_IAE_pct_all_cases"],1)} |')
    lines+=['', '## Disturbance-forecast information sensitivity (separate from equal-information rankings)', '',
       '| Case | Persistence IAE (K·s) | Perfect-future IAE (K·s) | Perfect-future minus persistence (K·s) |',
       '|---|---:|---:|---:|']
    for r in data['forecast_sensitivity']:
        lines.append(f'| `{r["case"]}` | {fmt(r["persistence_iae_Ks"])} | {fmt(r["advance_iae_Ks"])} | {fmt(r["delta_iae_Ks"])} |')
    lines += ['', 'This is a **two-case information sensitivity**, not a different entry in the equal-information 100-run benchmark. Perfect future disturbances are extra information unavailable to the PI baselines. Better forecasts do not guarantee better tracking when the internal plant model is inaccurate.', '']
    lines+=['', '## Complexity and reproducibility', '',
      '- The simulated plant has **3 physical states** (`T_h`, `T_b`, `n`) and one commanded input `u`; nominal MPC uses a six-step prediction horizon, **6 command variables + 6 service-slack variables = 12 QP variables** per update. The PI baseline uses proportional/integral feedback with documented gains and anti-windup.',
      '- The 100-run matrix contains **2,400 MPC update decisions** in total, with 48 actual fallbacks. Controller solve times are **not** contained in the saved robustness CSV; the optional `scripts/benchmark_wp5_runtime.py` measures wall-clock *end-to-end simulation runtime* on an explicitly identified machine, not QP solve latency.',
      '- OSQP/SLSQP agreement at three predeclared QP operating points is verified in `scripts/run_wp4_solver_audit.py`. That check is not a general execution-time, optimality or industrial real-time proof.',
      '- The Pareto set is computed only among service-eligible methods using (IAE, electricity, command TV) in each case. A controller is Pareto-undominated if no eligible controller is at least as good in all three and strictly better in one. This is **not** an economic optimum.',
      '- Run `python scripts/run_wp4_robustness.py` then `python scripts/run_wp5.py` to reconstruct the input matrix and report. One version-pinned commit must bind the source, parameters and derived outputs; changes to the WP4 matrix invalidate the previously generated WP5 report.',
    ]
    if data.get('runtime_pilot'):
        bench=data['runtime_pilot']
        lines += ['', '### Optional end-to-end runtime pilot (machine-dependent)', '',
          f'- Environment: `{bench["platform"]}`; Python {bench["python"]}, NumPy {bench["numpy"]}, SciPy {bench["scipy"]}; {bench["repeats"]} repetitions of {bench["duration_s"]} simulated seconds each.',
          '- These figures include numerical integration, simulated sensing, observer updates, QP assembly, solver and Python interpreter overhead. They are **not per-solve MPC execution times**, worst-case execution times or proof of real-time readiness.',
          '', '| Case | Method | Median full-simulation wall time (s) | Range (s) |',
          '|---|---|---:|---:|']
        for r in bench['records']:
            lines.append(f'| `{r["case"]}` | `{r["method"]}` | {fmt(r["median_wall_s"],3)} | {fmt(r["min_wall_s"],3)}–{fmt(r["max_wall_s"],3)} |')
    lines += ['', '## What this study cannot establish', '', 
      '- No manufacturer data, real refrigerant cycle, commissioned controller, physically measured process duty or calibrated HX `UA(f)`; no conclusion generalises to a particular industrial HTHP.',
      '- No economic savings, absolute cost, guaranteed heat delivery, formal closed-loop stability, delay margin, safety integrity level, sample-based failure probability or statistically independent uncertainty estimate.',
      '- No dedicated sensor-bias, sensor dropout, correlated-noise or externally validated forecast-error benchmark yet. The price scenarios, storage tariff flexibility and SOC active-set economic loss remain separate future research stages.',
      '- The 20 scenarios are not a representative probabilistic distribution; counting scenario wins does not measure employment, publication or industrial deployment probabilities.',
      '', '## Source data and result artifacts', '',
      '- `results/wp4_robustness_matrix.csv` — source 100 runs (20 scenarios × 5 methods).',
      '- `results/wp4_robustness_summary.json` — provenance and perfect-future-forecast exploratory rows.',
      '- `results/wp5_case_comparison.csv` — 20 source-linked case-level comparisons, including the service gate.',
      '- `results/wp5_paired_comparisons.csv` — all 80 MPC-versus-PI raw paired effects.',
      '- `results/wp5_controller_summary.csv` — controller summary and Pareto appearances.',
      '- `results/wp5_category_summary.csv` — declared grouped descriptive analysis.',
      '- `results/wp5_forecast_sensitivity.csv` — two additional-information scenarios; never included in equal-information rankings.',
      '- `results/wp5_runtime_local.json` — optional platform-specific end-to-end benchmarking, not MPC solver-only timing.',
      '- `results/wp5_analysis.json` — machine-readable full audit, metadata and failures.',
      '- `results/wp5_paired_tracking.png` and `results/wp5_eligible_energy.png` — visual summaries; infeasible pairs excluded from conditional electricity comparison.',
      '', '**WP5 stage outcome:** a reproducible *comparative analysis of the existing synthetic benchmark*. The broader research plan’s real-fluid and price-service-validity tasks remain outstanding; WP5 is not evidence of a calibrated thermal control product.', '']
    return '\n'.join(lines)


def plots(data):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return
    rows=data['per_case']
    order=sorted(rows,key=lambda r:r['MPC_minus_relay_iae_pct'] if r.get('MPC_minus_relay_iae_pct') is not None else 0)
    labels=[r['case'].replace('_',' ') for r in order]
    vals=[r['MPC_minus_relay_iae_pct'] for r in order]
    fig,ax=plt.subplots(figsize=(10,10))
    ax.barh(labels,vals)
    ax.axvline(0,linewidth=1)
    ax.set_xscale('symlog',linthresh=110)
    ax.set_xlabel('MPC minus relay PI, IAE (%) — symlog beyond ±110%; negative favours MPC')
    ax.set_title('WP5: paired synthetic tracking contrast\n(raw error, infeasible cases retained)')
    ax.invert_yaxis()
    fig.tight_layout();fig.savefig(RESULTS/'wp5_paired_tracking.png',dpi=140);plt.close(fig)
    eligible=[r for r in order if r['MPC_qualified_for_energy_comparison']]
    fig,ax=plt.subplots(figsize=(10,max(5,0.4*len(eligible))))
    ax.barh([r['case'].replace('_',' ') for r in eligible],[r['MPC_minus_relay_electricity_kWh'] for r in eligible])
    ax.axvline(0,linewidth=1)
    ax.set_xlabel('MPC minus relay PI, electrical kWh (negative = MPC uses less)')
    ax.set_title('WP5: electricity comparison\n(only pairs with the same service-compliance status: both qualified)')
    ax.invert_yaxis()
    fig.tight_layout();fig.savefig(RESULTS/'wp5_eligible_energy.png',dpi=140);plt.close(fig)


def main():
    RESULTS.mkdir(parents=True,exist_ok=True)
    data=analyze(load_matrix(SOURCE))
    import hashlib
    data['source_matrix_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    source_summary=json.loads((RESULTS/'wp4_robustness_summary.json').read_text(encoding='utf-8'))
    extras=source_summary['forecast_assisted_extras']
    if len(extras)!=2 or {e['case'] for e in extras}!={'nominal','heatpump_capacity_minus20pct'}:
        raise ValueError('changed forecast-assisted evidence: update review before reporting')
    originals={r['case']:r for r in data['per_case']}
    forecast=[]
    for e in extras:
        case=e['case']
        if e.get('method') not in ('mpc','MPC_perfect_future_disturbance') or e.get('pi_fallbacks')!=0:
            raise ValueError('forecast extra does not match the expected MPC information experiment')
        if e.get('service_unserved_kWh',0)>1e-6 or not e.get('finite',False):
            raise ValueError('noncompliant or failed forecast run')
        x=originals[case]
        forecast.append({'case':case,'persistence_iae_Ks':x['MPC_iae_Ks'],
            'advance_iae_Ks':e['iae_Ks'],'delta_iae_Ks':e['iae_Ks']-x['MPC_iae_Ks'],
            'persistence_electricity_kWh':next(r for r in load_matrix(SOURCE) if r['case']==case and r['method']==MPC)['electrical_kWh'],
            'advance_electricity_kWh':e['electrical_kWh'],
            'distinct_information_mode':'advance sees actual future disturbances; persistence does not'})
    data['forecast_sensitivity']=forecast
    runtime_path=RESULTS/'wp5_runtime_local.json'
    if runtime_path.exists():
        data['runtime_pilot']=json.loads(runtime_path.read_text(encoding='utf-8'))
    csv_save(RESULTS/'wp5_forecast_sensitivity.csv',forecast)
    csv_save(RESULTS/'wp5_case_comparison.csv',data['per_case'])
    csv_save(RESULTS/'wp5_paired_comparisons.csv',data['paired'])
    csv_save(RESULTS/'wp5_controller_summary.csv',data['controller_summary'])
    csv_save(RESULTS/'wp5_category_summary.csv',data['categories'])
    (RESULTS/'wp5_analysis.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (RESULTS/'wp5_comparative_report.md').write_text(report(data),encoding='utf-8')
    plots(data)
    print('WP5:',data['source_rows'],'rows validated;',len(data['paired']),'paired MPC-vs-PI effects;'
          ,data['mpc_relay_service_matched_cases'],'service-compliant MPC/relay pairs;'
          ,data['MPC_total_fallback_events'],'logged MPC fallbacks')
    print('Raw IAE wins:',data['raw_iae_wins'],'qualified wins:',data['service_qualified_iae_wins'])


if __name__=='__main__':main()
