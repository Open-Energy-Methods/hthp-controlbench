"""WP6: explicit steady-state SOC/active-constraint screening for a synthetic HTHP.

IMPORTANT: The WP2 baseline has only one compressor actuator and active service
constraint. This module adds an EXPLORATORY second actuator (hot-loop pump flow).
It does not retrofit or imply control authority over the WP2 local bypass valve.
The hot-side film UA and pump affinity laws are uncalibrated assumptions.
All offline objective values assume the same fully qualified heat service.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from math import isfinite
from scipy.optimize import brentq, minimize_scalar, minimize
import numpy as np
from .core import Parameters, Disturbance, State, counterflow_effectiveness, output, rhs


@dataclass(frozen=True)
class SOCParameters:
    pump_nominal_w: float = 2500.0
    hot_film_resistance_fraction: float = 0.4
    hot_film_flow_exponent: float = 0.8
    r_min: float = 0.35
    r_max: float = 1.02
    max_r_step: float = 0.08
    tau_r: float = 75.0
    tb_max_k: float = 408.15  # 135C illustrative absolute boundary
    th_max_k: float = 419.15  # 146C illustrative absolute boundary
    buffer_margin_k: float = 1.0  # optional real-time backoff, not offline SOC optimum
    active_tol: float = 0.003
    
    def __post_init__(self):
        if not (self.pump_nominal_w > 0 and self.hot_film_flow_exponent > 0 and
                0 < self.hot_film_resistance_fraction < 1 and
                0 < self.r_min < self.r_max and self.max_r_step > 0 and self.tau_r > 0 and
                self.tb_max_k > 0 and self.th_max_k > self.tb_max_k and
                self.buffer_margin_k >= 0 and self.active_tol > 0):
            raise ValueError('invalid synthetic SOC/pump assumptions')


def effective_plant(p: Parameters, c: SOCParameters, r: float) -> Parameters:
    """Flow r modifies *hot-side* capacity and hot-side film resistance only.

    UA(r)/UA_nom = 1 / [(1-Rhot)+Rhot / r**0.8] at f=1.
    Process-side bypass inside core retains its independently declared UA(f) rule.
    """
    if not (isfinite(r) and r > 0):
        raise ValueError('hot-loop flow ratio must be positive/finite')
    rh=c.hot_film_resistance_fraction
    ua=p.ua_proc/((1-rh)+rh/(r**c.hot_film_flow_exponent))
    return replace(p,c_hot=p.c_hot*r,ua_proc=ua,hx_mode='duty_limiter')


@dataclass(frozen=True)
class SteadyPoint:
    r: float
    tb_k: float
    th_k: float
    n: float
    q_service_w: float
    p_compressor_w: float
    p_pump_w: float
    p_total_w: float
    c_margin_k: float
    active: tuple[str,...]


def service_temperature_min(p: Parameters,c: SOCParameters,d: Disturbance,r: float) -> float:
    pp=effective_plant(p,c,r)
    cp=pp.c_proc if pp.flow_mode=='fixed' else d.c_proc
    if cp is None or cp<=0 or d.t_return>=d.t_required:
        raise ValueError('WP6 study assumes strictly positive heat demand')
    q=cp*(d.t_required-d.t_return)
    eps=counterflow_effectiveness(cp,pp.c_hot,pp.ua_proc)
    return d.t_return + q/(eps*min(cp,pp.c_hot))


def evaluate_point(p: Parameters,c: SOCParameters,d: Disturbance,r: float,
                   buffer_margin_k: float=0.0) -> SteadyPoint:
    """Feasible steady operation with active service constraint + optional backoff.

    Compressor n is uniquely required by thermal energy balance, rather than
    counted as an independent unconstrained DOF. Infeasible points fail loudly.
    """
    if r<c.r_min-1e-10 or r>c.r_max+1e-10: raise ValueError('r violates pump bounds')
    pp=effective_plant(p,c,r)
    tb=service_temperature_min(p,c,d,r)+buffer_margin_k
    cp=pp.c_proc if pp.flow_mode=='fixed' else d.c_proc
    assert cp is not None
    q=cp*(d.t_required-d.t_return)
    from .core import heat_exchanger
    hx=heat_exchanger(tb,pp,d)
    if hx.q_transferred<q-1e-3 or hx.t_proc_out<d.t_required-1e-7:
        raise ValueError('unqualified service, cannot price as served')
    qhb=hx.q_transferred+pp.ua_b*(tb-d.t_ambient)
    th=tb+qhb/pp.khb
    qhp=qhb+pp.ua_h*(th-d.t_ambient)
    rated=output(State(th,tb,1.0),pp,d).q_hp
    n=qhp/rated
    if tb>c.tb_max_k+1e-8 or th>c.th_max_k+1e-8 or n>pp.n_max+1e-8 or n<pp.n_min-1e-8:
        raise ValueError('synthetic thermal, command or capacity constraint infeasible')
    pel=output(State(th,tb,n),pp,d).p_el
    pump=c.pump_nominal_w*r**3
    active=[]
    if abs(r-c.r_min)<c.active_tol: active.append('pump_min')
    if abs(r-c.r_max)<c.active_tol: active.append('pump_max')
    if abs(tb-c.tb_max_k)<0.03: active.append('buffer_max')
    if abs(th-c.th_max_k)<0.03: active.append('header_max')
    if abs(n-pp.n_max)<0.003: active.append('compressor_max')
    if buffer_margin_k<=1e-9: active.insert(0,'service')
    return SteadyPoint(r,tb,th,n,q,pel,pump,pel+pump,buffer_margin_k,tuple(active))


def feasible_interval(p: Parameters,c: SOCParameters,d: Disturbance) -> tuple[float,float] | None:
    """Find interval for the declared monotone nominal envelope; audit grid assumptions.

    In more complex fluid maps feasible sets may be disconnected: this method
    must then be replaced by explicit interval enumeration, not silently reused.
    """
    grid=np.linspace(c.r_min,c.r_max,150)
    ok=[]
    for r in grid:
        try: evaluate_point(p,c,d,float(r));ok.append(True)
        except ValueError:ok.append(False)
    ix=np.flatnonzero(ok)
    if len(ix)==0:return None
    if np.any(np.diff(ix)>1):raise ValueError('nonconnected feasible region; revise solver')
    low=float(grid[ix[0]]); high=float(grid[ix[-1]])
    if ix[0]>0:
        # Bisect between unfeasible lower point and feasible upper point.
        a=float(grid[ix[0]-1]);b=low
        for _ in range(45):
            mid=(a+b)/2
            try:evaluate_point(p,c,d,mid);b=mid
            except ValueError:a=mid
        low=b+1e-8
    # In the illustrative parameter envelope r_max is feasible, so no upper bisection needed.
    if ix[-1]<len(grid)-1:
        a=high;b=float(grid[ix[-1]+1])
        for _ in range(45):
            mid=(a+b)/2
            try:evaluate_point(p,c,d,mid);a=mid
            except ValueError:b=mid
        high=a-1e-8
    return low,high


def offline_optimum(p: Parameters,c: SOCParameters,d: Disturbance) -> SteadyPoint | None:
    interval=feasible_interval(p,c,d)
    if interval is None:return None
    lo,hi=interval
    if hi-lo<1e-7:return evaluate_point(p,c,d,(lo+hi)/2)
    def obj(r):return evaluate_point(p,c,d,float(r)).p_total_w
    result=minimize_scalar(obj,bounds=(lo,hi),method='bounded',options={'xatol':1e-9})
    candidates=[lo,hi,float(result.x)]
    return min((evaluate_point(p,c,d,float(x)) for x in candidates),key=lambda x:x.p_total_w)


def fixed_r_point(p: Parameters,c: SOCParameters,d: Disturbance,r: float) -> SteadyPoint | None:
    try:return evaluate_point(p,c,d,float(r))
    except ValueError:return None


def economic_loss_w(policy: SteadyPoint | None,optimum:SteadyPoint|None) -> float | None:
    if policy is None or optimum is None:return None
    value=policy.p_total_w-optimum.p_total_w
    if value < -1e-2:raise ValueError('economic policy allegedly beats offline optimum; optimizer invalid')
    return max(0.,value)


def train_constant_cvs(p: Parameters,c: SOCParameters, disturbances:list[Disturbance],
                       use_return_compensation: bool=False) -> dict:
    """Choose fixed CV setpoint on training disturbances ONLY.

    Candidate A: CV=r held at one constant.
    Candidate B: CV=r + beta*(T_return-90C) held at a constant.
    Both are measurable/computable CVs; candidate B is empirical, NOT a
    Manum-Skogestad nullspace-optimal combination or proof of closed-loop SOC.
    """
    if not disturbances:raise ValueError('empty training dataset')
    opts=[offline_optimum(p,c,d) for d in disturbances]
    if any(o is None for o in opts):raise ValueError('training set includes infeasible disturbance')
    opt_r=np.array([o.r for o in opts])
    tr=np.array([d.t_return-363.15 for d in disturbances])
    if use_return_compensation:
        M=np.column_stack([np.ones(len(tr)),tr])
        co=np.linalg.lstsq(M,opt_r,rcond=None)[0]
        r0,beta=float(co[0]),float(-co[1])
    else:
        def aggregate(r):
            pts=[fixed_r_point(p,c,d,r) for d in disturbances]
            if any(x is None for x in pts):return 1e12+abs(r)*1e4
            return sum(x.p_total_w for x in pts)
        interval=(max(feasible_interval(p,c,d)[0] for d in disturbances),
                  min(feasible_interval(p,c,d)[1] for d in disturbances))
        if interval[0]>interval[1]:return {'valid':False,'reason':'no shared feasible fixed-r across training disturbances'}
        sol=minimize_scalar(aggregate,bounds=interval,method='bounded',options={'xatol':1e-10})
        r0,beta=float(min([interval[0],interval[1],float(sol.x)],key=aggregate)),0.0
    return {'valid':True,'cv_name':'r + beta*(T_return-363.15)' if use_return_compensation else 'r',
            'cv_setpoint':r0,'beta_per_kelvin':beta,
            'training_count':len(disturbances),'fitted_to_offline_optima':bool(use_return_compensation)}


def policy_r(model:dict,d:Disturbance)->float:
    if not model.get('valid'):raise ValueError('invalid candidate')
    return model['cv_setpoint']-model['beta_per_kelvin']*(d.t_return-363.15)


def evaluate_cv(p: Parameters,c:SOCParameters,disturbances:list[Disturbance],model:dict)->list[dict]:
    rows=[]
    for d in disturbances:
        opt=offline_optimum(p,c,d)
        proposed=policy_r(model,d)
        trial=fixed_r_point(p,c,d,proposed)
        loss=economic_loss_w(trial,opt)
        rows.append({'t_source_c':round(d.t_source-273.15,3),'t_return_c':round(d.t_return-273.15,3),
                     'r_opt':opt.r if opt else None,'opt_active':';'.join(opt.active) if opt else 'infeasible',
                     'r_candidate':proposed,'candidate_feasible':trial is not None,'loss_w':loss,
                     'loss_pct':100*loss/opt.p_total_w if loss is not None else None,
                     'opt_p_total_w':opt.p_total_w if opt else None,'candidate_p_total_w':trial.p_total_w if trial else None})
    return rows


def train_piecewise_soc(p:Parameters,c:SOCParameters,disturbances:list[Disturbance])->dict:
    """Empirical *candidate* active-set SOC: one constant linear CV per free region.

    Interior r is predicted by maintaining the constant measurable combination
        CV = r + beta_return*(T_return-90C) + beta_source*(T_source-60C).
    When that prediction exceeds r_max, the *active constraint* r=r_max applies.
    Both CV coefficients and the active-set selector are frozen using training
    data; held-out disturbances are NEVER used to refit or select coefficients.
    This is not a proof of a nullspace-optimal CV or global SOC performance.
    """
    if len(disturbances)<5:raise ValueError('insufficient training data')
    optimum=[offline_optimum(p,c,d) for d in disturbances]
    if any(x is None for x in optimum):raise ValueError('infeasible training point')
    interior=[(d,o) for d,o in zip(disturbances,optimum) if not 'pump_max' in o.active and not 'pump_min' in o.active]
    boundary=[(d,o) for d,o in zip(disturbances,optimum) if 'pump_max' in o.active]
    if len(interior)<4 or not boundary:raise ValueError('lack of both interior and bound regimes')
    A=np.asarray([[1.0,d.t_return-363.15,d.t_source-333.15] for d,o in interior])
    y=np.asarray([o.r for d,o in interior])
    if np.linalg.matrix_rank(A)<3:raise ValueError('nonidentifiable CV measurement combination')
    coef=np.linalg.lstsq(A,y,rcond=None)[0]
    return {'valid':True,'cv_name':'r + beta_return*(T_return-363.15) + beta_source*(T_source-333.15)',
            'cv_setpoint':float(coef[0]),'beta_per_kelvin':float(-coef[1]),
            'beta_source_per_kelvin':float(-coef[2]),'training_count':len(disturbances),
            'interior_training_count':len(interior),'pump_max_training_count':len(boundary),
            'selection':'active pump_max when unconstrained candidate exceeds pump ceiling; otherwise hold CV',
            'trained_only_on_train':True}


def piecewise_policy_r(model:dict,c:SOCParameters,d:Disturbance)->tuple[float,str]:
    if not model.get('valid'):raise ValueError('invalid piecewise SOC policy')
    raw=(model['cv_setpoint']-model['beta_per_kelvin']*(d.t_return-363.15)
         -model['beta_source_per_kelvin']*(d.t_source-333.15))
    if raw>=c.r_max:return c.r_max,'pump_max_constraint'
    return raw,'interior_constant_CV'


def evaluate_piecewise_cv(p:Parameters,c:SOCParameters,disturbances:list[Disturbance],model:dict)->list[dict]:
    rows=[]
    for d in disturbances:
        optimal=offline_optimum(p,c,d)
        r,region=piecewise_policy_r(model,c,d)
        candidate=fixed_r_point(p,c,d,r)
        loss=economic_loss_w(candidate,optimal)
        rows.append({'t_source_c':d.t_source-273.15,'t_return_c':d.t_return-273.15,
                     'opt_r':optimal.r if optimal else None,
                     'opt_active':';'.join(optimal.active) if optimal else 'infeasible',
                     'policy_r':r,'selected_regime':region,'policy_feasible':candidate is not None,
                     'loss_w':loss,'loss_pct':100*loss/optimal.p_total_w if loss is not None else None,
                     'opt_p_total_w':optimal.p_total_w if optimal else None,
                     'policy_p_total_w':candidate.p_total_w if candidate else None})
    return rows


def derive_local_stationarity_cv(p:Parameters,c:SOCParameters,anchor:Disturbance,
                                 dr:float=0.002,dt:float=0.25)->dict:
    """Build a locally stationary CV using the economic Hessian and mixed derivatives.

    J_r=0 at interior reference point. For a disturbance delta-d,
    0 ≈ J_rr delta-r + J_rd delta-d, so beta_d=J_rd/J_rr and
    CV = r + beta_d*delta-d holds constant to FIRST ORDER.
    This is nonlinear-plant local sensitivity, not a published global SOC guarantee.
    """
    optimum=offline_optimum(p,c,anchor)
    if optimum is None or 'pump_max' in optimum.active or 'pump_min' in optimum.active:
        raise ValueError('stationarity CV requires strictly interior optimum')
    r0=optimum.r
    def cost(r,d):return evaluate_point(p,c,d,r).p_total_w
    h=(cost(r0+dr,anchor)-2*cost(r0,anchor)+cost(r0-dr,anchor))/(dr*dr)
    if not np.isfinite(h) or h<=0:raise ValueError('nonpositive local economic Hessian')
    betas={}
    for name in ('t_return','t_source'):
        dplus=replace(anchor,**{name:getattr(anchor,name)+dt})
        dminus=replace(anchor,**{name:getattr(anchor,name)-dt})
        mixed=(cost(r0+dr,dplus)-cost(r0-dr,dplus)-cost(r0+dr,dminus)+cost(r0-dr,dminus))/(4*dr*dt)
        betas[name]=mixed/h
    bret=betas['t_return'];bsrc=betas['t_source']
    c0=r0+bret*(anchor.t_return-363.15)+bsrc*(anchor.t_source-333.15)
    return {'valid':True,'cv_name':'stationarity-derived r+beta_return*dTreturn+beta_source*dTsource',
            'cv_setpoint':float(c0),'beta_per_kelvin':float(bret),
            'beta_source_per_kelvin':float(bsrc),
            'anchor_r':float(r0),'anchor_t_return_c':anchor.t_return-273.15,
            'anchor_t_source_c':anchor.t_source-273.15,
            'H_rr_W_per_r2':float(h),'derivation':'implicit stationarity sensitivity at interior optimum',
            'trained_only_on_train':True}


def evaluate_at_buffer_temperature(p:Parameters,c:SOCParameters,d:Disturbance,
                                   r:float,tb:float)->SteadyPoint:
    """Independent full-2D objective used to audit eliminating buffer temperature.

    At fixed r, any feasible positive buffer-temperature backoff is allowed;
    compressor n is eliminated via both steady thermal balances. This prevents
    the one-variable study from silently assuming the active service constraint.
    """
    tmin=service_temperature_min(p,c,d,r)
    if tb<tmin-1e-8:raise ValueError('temperature below service requirement')
    return evaluate_point(p,c,d,r,max(0.0,tb-tmin))


def baseline_dof_audit()->dict:
    return {'model':'original WP2 single-compressor-command plant',
            'declared_manipulated_variables':['compressor_command_u'],
            'non_manipulated_local_variables':['local_process_bypass_fraction_f'],
            'active_constraints_at_qualifying_economic_optimum':['process_service_temperature'],
            'unconstrained_steady_economic_dof':0,
            'decision':'no nontrivial free steady-state SOC degree of freedom in this tested regime; label constraint-following, not SOC',
            'caveat':'not a global proof for all possible equipment, unconstrained operating states, or modified objectives'}
