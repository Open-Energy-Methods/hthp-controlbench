"""WP2 L1 three-state lumped HTHP thermal plant, synthetic research demonstrator.

SI units throughout: K, W, J/K, W/K, s. The compressor heat-output map
and the constant/flow-dependent-UA process exchanger are NOT calibrated.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from math import exp, expm1, isfinite

K0 = 273.15


def counterflow_effectiveness(c1: float, c2: float, ua: float) -> float:
    """Numerically stable counterflow epsilon-NTU, including Cr≈1.

    Uses expm1 to avoid catastrophic cancellation. Continuously approaches
    NTU/(1+NTU) for equal positive capacity rates.
    """
    if min(c1, c2, ua) <= 0 or not all(map(isfinite, (c1, c2, ua))):
        raise ValueError("HX: positive finite capacity rates and UA required")
    cmin, cmax = min(c1, c2), max(c1, c2)
    cr = cmin / cmax
    ntu = ua / cmin
    d = 1.0 - cr
    if d == 0.0:
        return ntu / (1.0 + ntu)
    a = -expm1(-ntu*d)  # stable as Cr->1; 1-exp(-NTU*d)
    return a / (d + cr*a)


@dataclass(frozen=True)
class Parameters:
    c_h: float = 5_000_000.0      # J/K, illustrative
    c_b: float = 21_000_000.0     # J/K, 5000 kg * 4200 J/(kg K)
    khb: float = 100_000.0       # W/K
    ua_proc: float = 16_000.0    # W/K at f=1, assumed
    c_proc: float = 10_000.0     # W/K, fixed process flow (unless disturbance overrides)
    c_hot: float = 100_000.0     # W/K, hot recirculation through HX
    ua_h: float = 5_000.0 / (133.05-20.0)  # W/K, nominal 5 kW header loss
    ua_b: float = 5_000.0 / (130.0-20.0)   # W/K, nominal 5 kW buffer loss
    t_ambient: float = 293.15    # K
    t_required: float = 393.15   # K, process qualification threshold
    q_hp_rated: float = 413_333.3333333333  # Wth at full n; synthetic, not rated equipment
    tau_n: float = 90.0          # s compressor modulation first-order response
    n_min: float = 0.0
    n_max: float = 1.0
    t_src_reference: float = 333.15  # K, 60 C
    t_header_reference: float = 406.20 # K, 133.05 C
    capacity_source_slope: float = 0.003 # 1/K, synthetic
    capacity_header_slope: float = 0.002 # 1/K, synthetic
    capacity_factor_min: float = 0.4
    capacity_factor_max: float = 1.3
    eta_second_law: float = 0.45
    approach_evap: float = 5.0    # K
    approach_cond: float = 5.0    # K
    ua_flow_exponent: float = 0.0 # provisional UA(f)=UA0*f^a, NOT measured
    hx_mode: str = 'no_bypass'   # or 'duty_limiter'
    flow_mode: str = 'fixed'     # or 'exogenous' (disturbance supplies c_proc)
    max_command_step: float = 0.05   # per control update

    def __post_init__(self):
        if self.hx_mode not in ('no_bypass', 'duty_limiter'):
            raise ValueError('hx_mode must be no_bypass or duty_limiter')
        if self.flow_mode not in ('fixed', 'exogenous'):
            raise ValueError('controlled process flow is not implemented')
        if self.ua_flow_exponent < 0 or self.ua_flow_exponent > 1:
            raise ValueError('ua_flow_exponent must be in [0, 1]')
        if self.c_h <= 0 or self.c_b <= 0 or self.tau_n <= 0:
            raise ValueError('positive thermal capacities and compressor time constant required')
        if self.khb < 0 or self.ua_h < 0 or self.ua_b < 0:
            raise ValueError('nonnegative conductances required')
        if not 0 <= self.n_min < self.n_max <= 1:
            raise ValueError('invalid modulation interval')
        if not (0 < self.eta_second_law <= 1):
            raise ValueError('eta_II in (0, 1] required')


@dataclass(frozen=True)
class State:
    th: float
    tb: float
    n: float


@dataclass(frozen=True)
class Disturbance:
    t_source: float = 333.15
    t_return: float = 363.15
    t_ambient: float = 293.15
    t_required: float = 393.15
    c_proc: float | None = None # W/K, exogenous-throughput mode only


@dataclass(frozen=True)
class HxResult:
    fraction: float
    effectiveness: float
    q_transferred: float
    q_max: float
    q_requested: float
    t_proc_out: float
    t_hx_out: float
    t_hot_out: float
    q_shortfall: float
    q_excess: float
    qualified: bool
    q_spec_qualified: float
    q_spec_unserved: float
    t_b_min_service: float | None


@dataclass(frozen=True)
class Rates:
    q_hp: float
    p_el: float
    q_source: float
    q_hb: float
    loss_h: float
    loss_b: float
    hx: HxResult


def _capacity_rate(p: Parameters, d: Disturbance) -> float:
    if p.flow_mode == 'fixed':
        if d.c_proc is not None:
            raise ValueError('fixed process flow cannot be changed by disturbance or controller')
        return p.c_proc
    if d.c_proc is None:
        raise ValueError('exogenous flow requires c_proc disturbance')
    if d.c_proc < 0:
        raise ValueError('negative process capacity rate')
    return d.c_proc


def _q_at_fraction(f: float, tb: float, tr: float, cp: float, p: Parameters) -> tuple[float, float]:
    if not 0 <= f <= 1:
        raise ValueError('HX bypass fraction outside [0,1]')
    if f == 0 or cp <= 0 or p.c_hot <= 0 or tb <= tr or p.ua_proc <= 0:
        return 0.0, 0.0
    c = f * cp
    ua = p.ua_proc * f ** p.ua_flow_exponent
    eff = counterflow_effectiveness(c, p.c_hot, ua)
    return eff * min(c, p.c_hot) * (tb - tr), eff


def heat_exchanger(tb: float, p: Parameters, d: Disturbance) -> HxResult:
    cp = _capacity_rate(p,d)
    if cp < 0:
        raise ValueError('negative capacity rate')
    if min(tb, d.t_return, d.t_required) <= 0:
        raise ValueError('absolute temperatures must be positive')
    requested = max(0.0, cp * (d.t_required - d.t_return))
    qmax, full_eff = _q_at_fraction(1.0, tb, d.t_return, cp, p)
    if p.hx_mode == 'no_bypass':
        f = 1.0 if cp > 0 else 0.0
    elif requested <= 0:
        f = 0.0
    elif requested >= qmax:
        f = 1.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) * 0.5
            qmid, _ = _q_at_fraction(mid, tb, d.t_return, cp, p)
            if qmid < requested: lo = mid
            else: hi = mid
        f = (lo + hi) * 0.5
    q, eff = _q_at_fraction(f, tb, d.t_return, cp, p)
    t_out = d.t_return + q/cp if cp else d.t_return
    t_hx_out = d.t_return + q/(f*cp) if f*cp else d.t_return
    t_hot_out = tb-q/p.c_hot if p.c_hot else tb
    shortfall, excess = max(0.0, requested-q), max(0.0, q-requested)
    tol = 1e-6
    qualified = (requested > 0 and t_out >= d.t_required-tol and q >= requested-1e-3)
    t_min = d.t_return + requested/(full_eff*min(cp,p.c_hot)) if full_eff > 0 and cp else None
    # q_spec_qualified retained as the source plan's KPI; cap served demand separately in reporting.
    q_spec_qualified = q if qualified else 0.0
    return HxResult(f, eff, q, qmax, requested, t_out, t_hx_out, t_hot_out, shortfall, excess,
                    qualified, q_spec_qualified, max(0.0,requested-q_spec_qualified), t_min)


def _hp_rates(x: State, p: Parameters, d: Disturbance) -> tuple[float,float,float]:
    if not (0 <= x.n <= 1):
        raise ValueError('modulation state out of bounds')
    if min(x.th, x.tb, d.t_source) <= 0:
        raise ValueError('non-positive absolute temperature')
    capacity_factor = 1 + p.capacity_source_slope*(d.t_source-p.t_src_reference) \
        - p.capacity_header_slope*(x.th-p.t_header_reference)
    capacity_factor = min(p.capacity_factor_max,max(p.capacity_factor_min,capacity_factor))
    qhp = p.q_hp_rated*x.n*capacity_factor
    tev = d.t_source - p.approach_evap
    tcond = x.th + p.approach_cond
    if tev <= 0 or tcond <= tev:
        raise ValueError('outside declared heating-cycle thermodynamic envelope')
    cop = p.eta_second_law*tcond/(tcond-tev)
    if cop <= 1.0:
        raise ValueError('COP<=1: illustrative source-heat balance invalid in this envelope')
    pel = qhp/cop if qhp else 0.0
    return qhp,pel,qhp-pel


def output(x: State, p: Parameters, d: Disturbance) -> Rates:
    hx=heat_exchanger(x.tb,p,d)
    qhp,pel,qsrc=_hp_rates(x,p,d)
    qhb=p.khb*(x.th-x.tb)
    return Rates(qhp,pel,qsrc,qhb,p.ua_h*(x.th-d.t_ambient),p.ua_b*(x.tb-d.t_ambient),hx)


def rhs(x: State, u_applied: float, p: Parameters, d: Disturbance) -> tuple[State, Rates]:
    if not p.n_min-1e-12 <= u_applied <= p.n_max+1e-12:
        raise ValueError('applied compressor command out of bounds')
    r=output(x,p,d)
    return State((r.q_hp-r.q_hb-r.loss_h)/p.c_h,
                 (r.q_hb-r.hx.q_transferred-r.loss_b)/p.c_b,
                 (u_applied-x.n)/p.tau_n),r


def equilibrium(p: Parameters, mode: str | None=None, t_buffer: float=403.15,
                d: Disturbance | None=None) -> tuple[State, float, Rates]:
    """Solve synthetic steady state at chosen buffer temperature and disturbances.

    No compressor-hardware capacity proof is implied. Outputs actual required n.
    """
    if mode is not None:
        p=replace(p,hx_mode=mode)
    d=d or Disturbance()
    hx=heat_exchanger(t_buffer,p,d)
    qhb=hx.q_transferred+p.ua_b*(t_buffer-d.t_ambient)
    th=t_buffer+qhb/p.khb
    q_required=qhb+p.ua_h*(th-d.t_ambient)
    capacity=output(State(th,t_buffer,1.0),p,d).q_hp
    n=q_required/capacity
    if not p.n_min<=n<=p.n_max:
        raise ValueError('synthetic equilibrium requires n outside admissible range')
    x=State(th,t_buffer,n)
    return x,n,output(x,p,d)
