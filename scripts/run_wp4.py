"""WP4 synthetic, equal-sampling PI-vs-MPC study; never claim equipment validation."""
from __future__ import annotations
import csv, json
from dataclasses import replace
from pathlib import Path
import numpy as np
from ht_hp_controlbench.core import Parameters, Disturbance, equilibrium
from ht_hp_controlbench.pi import PIController, PISettings, metrics
from ht_hp_controlbench.mpc import MPCConfig, closed_loop_mpc
from ht_hp_controlbench.sim import Schedule, simulate

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'
OUT.mkdir(exist_ok=True)
IMC=PISettings(0.03842421355656901,1.2387208598348781e-05,'FOPDT_IMC_lambda_0p5tau')
RELAY=PISettings(0.3451917157008826,0.00020116067348536278,'Relay_TyreusLuyben')


def disturbance(t):
    return Disturbance(t_return=363.15 if t < 3600 else 365.15,
                       t_source=333.15 if t < 4800 else 328.15)


def pi_comparison(nominal, actual, config, setting, duration=7200.):
    x0,u0,_=equilibrium(nominal)
    pi=PIController(setting,x0.tb+0.4,u0,config.period_s)
    schedule=Schedule(lambda t:u0,disturbance,
            feedback=lambda t,x,d,last:pi.command(t,x,d,last,actual))
    sim=simulate(actual,x0,schedule,duration,config.integration_step_s,config.period_s)
    return sim,np.full_like(sim.times,pi.setpoint_k),0,0


def measure(sim,target,period):
    met=metrics(sim,target,period)
    stride=int(round(period/(sim.times[1]-sim.times[0])))
    met['command_total_variation']=float(np.sum(abs(np.diff(sim.commands[::stride]))))
    met['qualified_fraction']=float(np.mean(sim.service_met))
    met['physical_shortfall_kWh']=float(np.trapezoid(
        np.maximum(np.where(sim.times<3600,300000.,280000.)-sim.q_process,0.),
        x=sim.times)/3_600_000)
    return met


def main():
    nominal=Parameters()
    cfg=MPCConfig(horizon=10)
    scenarios={
        'passive_nominal':nominal,
        'passive_buffer_capacity_minus20pct':replace(nominal,c_b=nominal.c_b*.8),
        'passive_compressor_capacity_minus20pct':replace(nominal,q_hp_rated=nominal.q_hp_rated*.8),
        'bypass_flow_UA_exponent_0p8':replace(nominal,hx_mode='duty_limiter',ua_flow_exponent=.8),
    }
    rows=[]; sampled={}
    for name,actual in scenarios.items():
        for source,variant in ((IMC,'PI_IMC'),(RELAY,'PI_relay')):
            sim,target,fallbacks,rejected=pi_comparison(nominal,actual,cfg,source)
            record=dict(scenario=name,controller=variant,information='current measurement only',
                        mpc_fallbacks=fallbacks,mpc_rejected=rejected,**measure(sim,target,cfg.period_s))
            rows.append(record)
            if name=='passive_nominal':sampled[variant]=(sim,target)
        for advanced in (False,True):
            sim,ctrl,target=closed_loop_mpc(nominal,cfg,IMC,7200,advance_forecast=advanced,mismatch=actual)
            variant='MPC_advance_forecast' if advanced else 'MPC_persistence'
            record=dict(scenario=name,controller=variant,information='future perfect scenario' if advanced else 'current persistence',
                    mpc_fallbacks=ctrl.fallback_events,
                    mpc_rejected=sum(not s.accepted for s in ctrl.decisions),
                    **measure(sim,target,cfg.period_s))
            rows.append(record)
            if name=='passive_nominal':sampled[variant]=(sim,target)
    with (OUT/'wp4_control_comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0].keys()));writer.writeheader();writer.writerows(rows)
    (OUT/'wp4_control_summary.json').write_text(json.dumps({'assumptions':{
       'model':'synthetic uncalibrated HTHP model','control_period_s':cfg.period_s,
       'horizon':cfg.horizon,'horizon_minutes':cfg.horizon*cfg.period_s/60,
       'electricity_price_EUR_per_kWh':.16,
       'comparison':'equal current information reported separately from future-known disturbances',
       'service':'physical heat and specification service remain separately tracked'},
       'results':rows},indent=2))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(2,1,figsize=(11,8),sharex=True)
        for name,(sim,target) in sampled.items():
            axs[0].plot(sim.times/3600,sim.states[:,1]-273.15,label=name)
            stride=int(cfg.period_s/(sim.times[1]-sim.times[0]))
            axs[1].step(sim.times[::stride]/3600,sim.commands[::stride],where='post',label=name)
        axs[0].plot(sim.times/3600,target-273.15,'k--',label='buffer reference')
        axs[0].set_ylabel('Buffer temperature (°C)');axs[1].set_ylabel('Compressor command fraction')
        axs[1].set_xlabel('Elapsed hours');axs[0].legend(ncol=2,fontsize=9)
        axs[1].legend(ncol=2,fontsize=9);axs[0].grid(alpha=.25);axs[1].grid(alpha=.25)
        fig.suptitle('WP4 synthetic PI–MPC comparison: passive-HX nominal case')
        fig.tight_layout();fig.savefig(OUT/'wp4_control_comparison.png',dpi=170);plt.close(fig)
    except ImportError:
        pass
    for row in rows:
        print(f"{row['scenario']:37s} {row['controller']:20s} IAE={row['iae_Ks']:.1f}"
              f" el={row['electrical_kWh']:.2f}kWh fallback={row['mpc_fallbacks']}")
    print('Completed',len(rows),'runs')
    return rows

if __name__=='__main__':main()