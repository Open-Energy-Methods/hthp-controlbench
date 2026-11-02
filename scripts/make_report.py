"""Generate reproducible WP2 synthetic sensitivity data and evidence summary."""
from pathlib import Path
from dataclasses import replace
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ht_hp_controlbench import Parameters, Disturbance, heat_exchanger, equilibrium


def main():
    out=Path('results');out.mkdir(exist_ok=True)
    p=Parameters(hx_mode='duty_limiter')
    rows=[]
    for exponent in (0.,.6,.7,.8):
        model=replace(p,ua_flow_exponent=exponent)
        hx=heat_exchanger(403.15,model,Disturbance())
        x,u,r=equilibrium(model)
        rows.append({'exponent':exponent,'fraction':hx.fraction,'epsilon':hx.effectiveness,
                     'ua_effective_kW_per_K':model.ua_proc*hx.fraction**exponent/1000,
                     'process_out_C':hx.t_proc_out-273.15,'header_C':x.th-273.15,
                     'heat_pump_kW':r.q_hp/1000})
    with (out/'ua_sensitivity.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    data=np.genfromtxt(out/'wp2_illustrative_timeseries.csv',delimiter=',',names=True)
    fig,ax=plt.subplots(figsize=(9,4.6))
    ax.plot(data['t_s']/60,data['header_C'],label='Header temperature')
    ax.plot(data['t_s']/60,data['buffer_C'],label='Buffer temperature')
    ax.plot(data['t_s']/60,data['process_out_C'],label='Process outlet temperature')
    for minute,label in [(20,'Return change'),(30,'Command change'),(40,'Source change')]:
        ax.axvline(minute,linestyle=':',alpha=.5)
        ax.annotate(label,(minute,ax.get_ylim()[0]),xytext=(minute+1,ax.get_ylim()[0]+1),fontsize=8,rotation=90)
    ax.set_xlabel('Elapsed time (minutes)');ax.set_ylabel('Temperature (°C)')
    ax.set_title('Illustrative nonlinear heat-pump plant: open-loop changes (not calibrated)')
    ax.legend(loc='upper left');fig.tight_layout()
    fig.savefig(out/'wp2_illustrative_thermal_response.png',dpi=150)
    plt.close(fig)
    biggest=max(abs(data['energy_residual_J']))
    drift=(rows[-1]['fraction']-rows[0]['fraction'])/rows[0]['fraction']*100
    with (out/'verification.txt').open('w') as f:
        f.write('HTHP-ControlBench WP2 synthetic research evidence; NOT hardware validated\n')
        f.write('Unit tests: run `PYTHONPATH=. python -m unittest discover -s tests -v`\n')
        f.write(f'UA exponent sweep: baseline f={rows[0]["fraction"]:.9f}, exponent 0.8 f={rows[-1]["fraction"]:.9f}\n')
        f.write(f'Bypass fraction change: {drift:.4f}% relative; exceeds suggested 1% screening threshold\n')
        f.write('Header/HP duty unchanged in this sweep BY DESIGN: duty and buffer state fixed.\n')
        f.write(f'Illustrative 3600 s max integrated energy balance residual: {biggest:.8g} J\n')
        f.write('This is the roundoff-sized residual of shared RK4 integral states; an independent trapezoid test also exists.\n')
        f.write('NOT TESTED: dynamic PI/MPC/SOC performance, hardware, certified heat pump or real-fluid COP.\n')
    print('UA flow-sensitivity fraction drift: %.4f %% relative'%drift)
    print('Saved results/ua_sensitivity.csv, results/wp2_illustrative_thermal_response.png, results/verification.txt')

if __name__=='__main__':main()
