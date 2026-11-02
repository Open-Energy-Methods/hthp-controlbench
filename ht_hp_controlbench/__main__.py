from pathlib import Path
import csv
import numpy as np
from .core import Parameters, Disturbance, equilibrium
from .sim import Schedule,simulate


def main():
    p=Parameters(hx_mode='duty_limiter')
    x0,u0,r=equilibrium(p)
    def d(t):
        return Disturbance(t_return=363.15 if t<1200 else 368.15,
                           t_source=333.15 if t<2400 else 328.15)
    s=Schedule(command=lambda t:u0 if t<1800 else min(u0+0.04,1),disturbance=d)
    sim=simulate(p,x0,s,duration_s=3600,step_s=5,control_period_s=60)
    out=Path('results');out.mkdir(exist_ok=True)
    with (out/'wp2_illustrative_timeseries.csv').open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['t_s','header_C','buffer_C','n_actual','u_applied','q_hp_kW','p_el_kW','q_process_kW','q_spec_unserved_kW','process_out_C','bypass_fraction','service_met','energy_residual_J'])
        for k,t in enumerate(sim.times):
            writer.writerow([f'{t:.1f}',f'{sim.states[k,0]-273.15:.7f}',f'{sim.states[k,1]-273.15:.7f}',f'{sim.states[k,2]:.8f}',f'{sim.commands[k]:.8f}',f'{sim.q_hp[k]/1000:.7f}',f'{sim.p_el[k]/1000:.7f}',f'{sim.q_process[k]/1000:.7f}',f'{sim.q_spec_unserved[k]/1000:.7f}',f'{sim.t_process_out[k]-273.15:.7f}',f'{sim.f_bypass[k]:.9f}',int(sim.service_met[k]),f'{sim.energy_residual[k]:.7g}'])
    print(f'Nominal: T_h={x0.th-273.15:.5f}°C, T_b={x0.tb-273.15:.5f}°C, n={x0.n:.7f}')
    print(f'Final:   T_h={sim.states[-1,0]-273.15:.5f}°C, T_b={sim.states[-1,1]-273.15:.5f}°C, n={sim.states[-1,2]:.7f}')
    print('Max |energy integral residual| [J]:',float(np.max(np.abs(sim.energy_residual))))
    print('CSV: results/wp2_illustrative_timeseries.csv (synthetic, NOT calibrated)')

if __name__=='__main__':main()
