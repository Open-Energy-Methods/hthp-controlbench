"""Optional TESPy network cross-check. No claims of manufacturer's offdesign map."""
from pathlib import Path
import csv
import json
from ht_hp_controlbench.realfluid import cycle_point,backend_version
from ht_hp_controlbench.tespy_check import tespy_same_cycle


def main():
    out=Path('results');out.mkdir(exist_ok=True)
    rows=[]
    for source,header in ((333.15,406.20),(328.15,403.15),(338.15,413.15)):
        point=cycle_point('R1233zd(E)',source,header)
        row=tespy_same_cycle(point)
        if max(abs(row['condenser_fractional_disagreement']),abs(row['compressor_fractional_disagreement']))>0.02:
            raise RuntimeError('TESPy-vs-direct-cycle disagreement >2%; independent review needed')
        if abs(row['energy_balance_residual_w'])>max(1.0,1e-5*row['tespy_condenser_w']):
            raise RuntimeError('TESPy steady-state heat/work balance fails')
        rows.append(row)
    with (out/'wp7_tespy_crosscheck.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
    (out/'wp7_tespy_crosscheck.json').write_text(json.dumps(dict(
        status='TESPy network solves vs direct CoolProp cycle, SHARED EOS',
        comparison_count=len(rows),backend_version=backend_version(),results=rows,
        limitations=['TESPy model uses CoolProp EOS, hence not an independent property validation',
                     'Parametric steady design-mode checks only, NOT calibrated TESPy offdesign component characteristic curves',
                     'No manufacturer compressor characteristic, oil safety, or real HTHP rig evidence']),indent=2)+'\n')
    for r in rows:
        print(f"TESPy CHECK: {r['fluid']} source={r['tsource_k']-273.15:.2f}C header={r['header_k']-273.15:.2f}C "
              f"direct COP={r['direct_cop']:.5f}, TESPy COP={r['tespy_cop']:.5f}, "
              f"|dP|={abs(r['compressor_fractional_disagreement']):.4%}")
    print('Scope: three steady-state design re-solves using SHARED CoolProp EOS, not manufacturer offdesign validation.')

if __name__=='__main__':main()
