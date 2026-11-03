"""Reproduce the WP3 closed-loop PI study; all values synthetic, not hardware validated."""
from pathlib import Path
import os
from ht_hp_controlbench.benchmark import BENCHMARK_ID
import csv
from ht_hp_controlbench.core import Parameters
from ht_hp_controlbench.pi import (
    identify_step, identify_relay, tune_imc, tune_relay_tyreus_luyben,
    closed_loop, metrics,
)

def main():
    root=Path(os.environ.get('HTHP_RESULTS_DIR','results')); root.mkdir(parents=True,exist_ok=True)
    p=Parameters(hx_mode='no_bypass')
    fit=identify_step(p)
    relay=identify_relay(p)
    candidates={'FOPDT_IMC_lambda_0p5tau':tune_imc(fit,0.5),
                'FOPDT_IMC_lambda_1tau':tune_imc(fit,1.0),
                'FOPDT_IMC_lambda_2tau':tune_imc(fit,2.0),
                'Relay_TyreusLuyben':tune_relay_tyreus_luyben(relay)}
    rows=[]; series={}
    for mode in ('no_bypass','duty_limiter'):
      plant=Parameters(hx_mode=mode,ua_flow_exponent=.8)
      for name,setting in candidates.items():
        s,ctrl,target=closed_loop(plant,setting)
        m=metrics(s,target)
        row={'hx_mode':mode,'controller':name,'kp_command_per_K':setting.kp,'ki_command_per_Ks':setting.ki,
             'antiwindup_saturation_events':ctrl.saturation_events,
             'antiwindup_slew_events':ctrl.slew_events,**m}
        rows.append(row)
        if mode=='no_bypass':series[name]=(s,target)
    with (root/'wp3_pi_comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    with (root/'wp3_identification.txt').open('w') as f:
        f.write(f'Benchmark: {BENCHMARK_ID}; WP3 independent simulated PI identification (no_bypass only; synthetic, not calibrated)\n')
        f.write('FOPDT step response: '+repr(fit)+'\n')
        f.write('Symmetric-relay describing-function approximation: '+repr(relay)+'\n')
        f.write('Relay Ku approximate: finite hysteresis and sampled slew-limited actuation.\n')
        f.write('IMC lambda factors: 0.5, 1.0 and 2.0 tau. No method singled out as an optimized baseline.\n')
        f.write('Relay tuning estimated Ku from nonlinear limit cycle; no measured hardware data.\n')
        f.write('Transfer to bypass plant is an out-of-model robustness check, NOT retuning.\n')
        for row in rows:f.write(str(row)+'\n')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(3,1,figsize=(10,9),sharex=True)
        for name,(s,target) in series.items():
            t=s.times/3600
            axs[0].plot(t,s.states[:,1]-273.15,label=name)
            axs[1].plot(t,s.commands,label=name)
            axs[2].plot(t,s.q_spec_unserved/1000,label=name)
        axs[0].plot(t,target-273.15,'k--',alpha=.55,label='Buffer target')
        axs[0].set_ylabel('Buffer temperature [°C]');axs[1].set_ylabel('Applied command [0–1]')
        axs[2].set_ylabel('Unserved specified heat [kW]');axs[2].set_xlabel('Time [h]')
        for ax in axs:ax.grid(alpha=.25);ax.legend(loc='best',fontsize=8)
        fig.suptitle('WP3 synthetic PI tuning comparison — NOT hardware validation')
        fig.tight_layout();fig.savefig(root/'wp3_pi_comparison.png',dpi=150);plt.close(fig)
    except ImportError:
        print('matplotlib not available: CSV and identification report still generated')
    print('FOPDT:',fit)
    print('Relay:',relay)
    for row in rows:print(row)
    print('Wrote results/wp3_pi_comparison.csv and wp3_identification.txt')

if __name__=='__main__':main()