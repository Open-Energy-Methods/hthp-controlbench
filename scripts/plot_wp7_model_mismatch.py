"""Render the reviewed WP7 v3 ledger as a self-contained, accessible SVG.

Source: results/wp7_model_mismatch_v3.json ONLY. Failed/ineligible values are
not plotted as zero. All colours and axis scales are just presentation aids.
"""
from __future__ import annotations

from pathlib import Path
from html import escape
import json
import math

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"results/wp7_model_mismatch_v3.json"
OUTPUT=ROOT/"results/wp7_model_mismatch_v3_summary.svg"
M={
    "PI_IMC":("#526A84","IMC PI"),
    "PI_relay":("#9EAAB8","Relay PI"),
    "MPC_property":("#167783","Property MPC"),
}
LABELS={
    "nominal":"Nominal",
    "ua_proc_minus15_source_drop3":"HX UA -15% + source drop",
    "ua_proc_plus15_noisy_delayed":"HX UA +15% + noisy/delayed sensor",
    "compressor_lag_plus30_source_drop3":"Compressor lag +30% + source drop",
    "header_buffer_khb_minus15_combined":"Header/buffer conductance -15% + combined",
}


def text_at(x,y,value,*,size=15,color="#26384C",weight=400,anchor=None):
    extra=f' text-anchor="{anchor}"' if anchor else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'font-family="Arial, Helvetica, sans-serif" font-weight="{weight}"'
            f'{extra}>{escape(str(value))}</text>')


def render(data:dict)->str:
    if data["benchmark_id"]!="WP7_NominalPredictor_TruthParameterMismatch_Holdout_v3":
        raise ValueError("figure requires the predeclared WP7 v3 benchmark")
    if len(data["cases"])!=5 or len(data["runs"])!=15 or len(data["pairs"])!=10:
        raise ValueError("incomplete source ledger")
    by_run={(r["case"],r["controller"]):r for r in data["runs"]}
    for name in LABELS:
        for method in M:
            if (name,method) not in by_run:
                raise ValueError("missing expected controller/case")
    all_iae=[r["iae_Ks"] for r in data["runs"] if r["iae_Ks"] is not None]
    ceiling=math.ceil(max(all_iae)/1000)*1000
    width=1140;height=900;x0=438;usable=620
    svg=[
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-label="WP7 v3 property-MPC versus PI tracking and conditional electricity. '
        f'An unqualified HX case is shown as not evaluated, not zero.">',
        '<rect width="1140" height="900" fill="#FFFFFF"/>',
        '<rect x="0" y="0" width="1140" height="6" fill="#167783"/>',
        text_at(32,48,"WP7 v3  |  Frozen-control model/plant-mismatch study",size=23,weight=700),
        text_at(32,75,"Uncalibrated CoolProp/IF97 simulations · 2-hour cases · same sensor and controller constraints",size=14,color="#5B6673"),
        text_at(32,114,"A. Temperature tracking, integrated absolute error (K·s) — lower is better",size=17,weight=700),
    ]
    for j,(key,(color,label)) in enumerate(M.items()):
        x=435+j*165
        svg.append(f'<rect x="{x}" y="126" width="15" height="12" rx="2" fill="{color}"/>')
        svg.append(text_at(x+22,137,label,size=13,color="#5B6673"))
    # tracking area: each scenario group has three individually labelled bars.
    for tick in range(0,ceiling+1,1000):
        xx=x0+tick*usable/ceiling
        svg.append(f'<line x1="{xx:.2f}" y1="161" x2="{xx:.2f}" y2="585" stroke="#E6EAEE"/>')
        svg.append(text_at(xx,157,str(tick),size=11,color="#6F7D89",anchor="middle"))
    for idx,case in enumerate(data["cases"]):
        name=case["case"]["name"]
        y=180+idx*83
        svg.append(text_at(30,y+19,LABELS[name],size=13,color="#344252"))
        rows=[by_run[(name,m)] for m in M]
        if all(r["iae_Ks"] is None for r in rows):
            svg.append(f'<rect x="{x0}" y="{y+3}" width="580" height="49" rx="5" fill="#FFF4F2"/>')
            svg.append(text_at(x0+12,y+32,"UNQUALIFIED INITIAL SERVICE — no controller ranking or energy score",size=12,color="#9D4E42",weight=700))
        else:
            for j,(method,(color,label)) in enumerate(M.items()):
                r=by_run[(name,method)]
                val=r["iae_Ks"]
                if val is None:
                    svg.append(text_at(x0+8,y+13+j*17,"NOT ELIGIBLE",size=12,color="#9D4E42"))
                    continue
                if not math.isfinite(val) or val<0:
                    raise ValueError("invalid plotted IAE")
                length=val*usable/ceiling
                svg.append(f'<rect x="{x0}" y="{y+3+j*17}" width="{length:.2f}" height="12" rx="2" fill="{color}"/>')
                svg.append(text_at(min(x0+length+7,1100),y+14+j*17,f"{val:,.0f}",size=12,color="#344252"))
        svg.append(f'<line x1="30" y1="{y+67}" x2="1105" y2="{y+67}" stroke="#EFF2F4"/>')
    svg.extend([
        text_at(32,630,"B. Electricity difference, MPC minus PI (kWh)",size=17,weight=700),
        text_at(32,653,"Only pairs with equal process service AND matched final thermal inventories/actuators",size=13,color="#5B6673"),
    ])
    eligible=[p for p in data["pairs"] if p["eligible_for_conditional_electricity_comparison"]]
    if len(eligible)!=data["terminal_electricity_comparable_pairs"]:
        raise ValueError("electricity eligibility count drift")
    if len(eligible)>5:raise ValueError("SVG layout supports up to five qualified energy pairs")
    x1=570;w=460;max_kwh=max(1.,max((abs(p["delta_electricity_kWh"]) for p in eligible),default=0))
    for t in (0.,.25,.5,.75,1.):
        xx=x1+t*w/max_kwh
        svg.append(f'<line x1="{xx:.2f}" y1="677" x2="{xx:.2f}" y2="842" stroke="#E6EAEE"/>')
        svg.append(text_at(xx,674,f"{t:.2f}",size=11,color="#6F7D89",anchor="middle"))
    for i,p in enumerate(eligible):
        label=f"{LABELS[p['case']]}  |  {M[p['baseline']][1]}"
        y=694+i*36
        v=p["delta_electricity_kWh"]
        if v is None or not math.isfinite(v):
            raise ValueError("missing eligible electricity delta")
        svg.append(text_at(30,y+11,label,size=12,color="#344252"))
        length=abs(v)*w/max_kwh
        color="#A05940" if v>0 else "#167783"
        svg.append(f'<rect x="{x1}" y="{y}" width="{length:.2f}" height="17" rx="2" fill="{color}"/>')
        svg.append(text_at(min(x1+length+8,1092),y+13,f"{v:+.3f}",size=12,color=color,weight=700))
    svg.extend([
        text_at(32,862,f"Eligibility: {data['complete_runs']}/15 runs complete; "
                       f"{data['service_eligible_pairs']}/10 service pairs; "
                       f"{len(eligible)}/10 terminal-comparable electricity pairs",size=13,weight=700),
        text_at(32,884,"Other pairs are NOT evaluated for energy savings. Neither this model nor the observer is hardware validated.",size=12,color="#5B6673"),
        '</svg>'
    ])
    return "\n".join(svg)+"\n"


def main():
    data=json.loads(SOURCE.read_text(encoding="utf-8"))
    image=render(data)
    OUTPUT.write_text(image,encoding="utf-8")
    print("Wrote",OUTPUT.relative_to(ROOT),f"({len(image)} bytes)")
    return OUTPUT


if __name__=="__main__":
    main()
