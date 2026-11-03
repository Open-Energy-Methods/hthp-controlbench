"""Audit OSQP versus SLSQP on precisely the same LTV-QP, synthetic inputs only.

Requires `pip install -e '.[qp]'`. Both solvers retain the SAME nonlinear
rollout and hard feasibility audit. No claims about hardware or real-time speed.
"""
from __future__ import annotations
import json
from pathlib import Path
from dataclasses import replace
from ht_hp_controlbench.core import Parameters,Disturbance,State,equilibrium
from ht_hp_controlbench.mpc import MPCConfig,solve_mpc


def main():
    try:import osqp
    except ImportError as e:raise SystemExit('OSQP dependency missing: pip install -e ".[qp]"') from e
    p=Parameters()
    x,u,_=equilibrium(p)
    d=Disturbance()
    cases={
      'nominal':(x,d,x.tb+.4),
      'temperature_deviation':(State(x.th+.2,x.tb-.1,x.n),d,x.tb+.4),
      'source_cooler':(x,replace(d,t_source=d.t_source-1.),x.tb+.2),
    }
    results=[]
    for name,(state,disturb,target) in cases.items():
        comp=[]
        for backend in ('slsqp','osqp'):
            cfg=MPCConfig(horizon=6,solver_backend=backend)
            r=solve_mpc(state,u,p,disturb,cfg,target,[disturb]*cfg.horizon,[.17]*cfg.horizon)
            comp.append(dict(backend=backend,accepted=r.accepted,status=r.status,
                first_command=r.command,objective=r.objective,
                iterations=r.qp_iterations,nonlinear_temp_error_k=r.max_temp_error_k))
        both_ok=all(z['accepted'] for z in comp)
        command_diff=abs(comp[0]['first_command']-comp[1]['first_command'])
        objective_diff=(abs(comp[0]['objective']-comp[1]['objective']) if both_ok else None)
        row=dict(case=name,solvers=comp,both_accepted=both_ok,
                 abs_first_command_difference=command_diff,
                 abs_qp_objective_difference=objective_diff)
        results.append(row)
        if not both_ok or command_diff>.02 or objective_diff>.5:
            raise RuntimeError('dedicated QP comparison fails predeclared threshold: '+str(row))
    root=Path('results');root.mkdir(exist_ok=True)
    (root/'wp4_solver_audit.json').write_text(json.dumps({
        'osqp_version':getattr(osqp,'__version__','unknown'),
        'status':'synthetic QP numerical cross-check only; not runtime guarantee',
        'method':'identical QP, independent primal constraints and nonlinear rollout',
        'experiments':results},indent=2,allow_nan=False)+'\n')
    for row in results:
        print(row['case'],'|δcommand|',row['abs_first_command_difference'],
              '|δobjective|',row['abs_qp_objective_difference'])

if __name__=='__main__':main()