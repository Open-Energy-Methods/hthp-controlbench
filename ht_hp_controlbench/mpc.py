"""WP4: locally linearized convex-QP receding-horizon control with explicit prediction backends.

No equipment validation. Default prediction remains WP2 nonlinear RK4;
WP7 explicitly injects a separately tested property/enthalpy transition and
power function. The QP uses a local discrete predictor and a JOINT affine
approximation of electrical power (not a ratio of linearized COP and duty).
SLSQP minimizes an explicitly constructed positive-semidefinite QP with linear
constraints. This is *not* a global nonlinear MPC solver or stability proof.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from math import isfinite
from typing import Callable
import numpy as np
from scipy.optimize import minimize, LinearConstraint, Bounds
from .core import Parameters, State, Disturbance, equilibrium, output
from .sim import _rk4_step, simulate, Schedule, Simulation
from .pi import PIController, PISettings, metrics


@dataclass(frozen=True)
class MPCConfig:
    horizon: int = 10
    period_s: float = 120.0
    integration_step_s: float = 10.0
    w_tracking: float = 12.0
    w_movement: float = 25.0
    w_effort: float = 0.05
    w_slack: float = 1200.0
    w_electric_eur: float = 2.0  # dimensionless comparison weight; not EUR itself
    temp_trust_k: float = 5.0
    modulation_trust: float = 0.15
    nonlinear_temp_tolerance_k: float = 1.0
    nonlinear_power_relative_tolerance: float = 0.05
    t_header_max_k: float = 413.15  # 140 C synthetic constraint
    t_buffer_max_k: float = 409.15  # 136 C synthetic constraint
    min_service_slack_k: float = 20.0  # max tolerated hypothetical service deficit in QP
    maxiter: int = 120
    solver_backend: str = "slsqp"  # optional: "osqp", same QP matrices

    def __post_init__(self):
        if self.horizon < 2 or self.period_s <= 0 or self.integration_step_s <= 0:
            raise ValueError('invalid MPC time grid')
        if abs(self.period_s / self.integration_step_s - round(self.period_s/self.integration_step_s)) > 1e-9:
            raise ValueError('MPC period must be multiple of integration step')
        for val in (self.w_tracking, self.w_movement, self.w_effort, self.w_slack, self.w_electric_eur):
            if not isfinite(val) or val < 0:
                raise ValueError('QP weights must be nonnegative and finite')
        if self.w_slack <= 0 or self.temp_trust_k <= 0 or self.modulation_trust <= 0:
            raise ValueError('invalid constraints')
        if self.nonlinear_temp_tolerance_k <= 0 or self.nonlinear_power_relative_tolerance <= 0:
            raise ValueError('invalid nonlinear-rollout tolerances')
        if self.maxiter < 1:
            raise ValueError('maxiter must be positive')
        if self.solver_backend not in ('slsqp', 'osqp'):
            raise ValueError('unknown QP backend')


def _vec(x: State) -> np.ndarray:
    return np.array((x.th,x.tb,x.n),float)


def _state(x: np.ndarray) -> State:
    return State(*[float(z) for z in x])


def _advance(x: State, u: float, p: Parameters, d: Disturbance, period: float, step: float) -> State:
    xx=x
    for _ in range(int(round(period/step))):
        xx,_=_rk4_step(xx,u,p,d,step)
    return xx


def _change_disturbance(d: Disturbance, source_delta=0., return_delta=0.) -> Disturbance:
    return Disturbance(d.t_source+source_delta,d.t_return+return_delta,d.t_ambient,d.t_required,d.c_proc)


@dataclass(frozen=True)
class Linearization:
    x0: np.ndarray
    u0: float
    d0: np.ndarray
    next0: np.ndarray
    A: np.ndarray
    B: np.ndarray
    E: np.ndarray
    p0: float
    power_x: np.ndarray
    power_source: float


def linearize(x: State, u: float, p: Parameters, d: Disturbance, cfg: MPCConfig,
              advance_fn: Callable | None = None,
              power_fn: Callable | None = None) -> Linearization:
    """Central-difference local discrete dynamics and joint electric-power Jacobian.

    E columns: heat-source and process-return temperatures. Finite differencing
    may fail outside a declared thermodynamic envelope: caller must fall back.
    """
    advance_fn=advance_fn or _advance
    power_fn=power_fn or (lambda state,par,dist: output(state,par,dist).p_el)
    x0=_vec(x); d0=np.array([d.t_source,d.t_return]); h=np.array([0.02,0.02,0.0002]);
    f=lambda xx,uu,dd:_vec(advance_fn(_state(xx),uu,p,dd,cfg.period_s,cfg.integration_step_s))
    nx=f(x0,u,d)
    A=np.zeros((3,3))
    for i in range(3):
        delta=np.zeros(3);delta[i]=h[i]
        if i==2:
            # Use a feasible one-sided/central secant at 0<=n<=1.
            # Central differencing previously evaluated n>1 at saturation
            # and caused a spurious "modulation state out of bounds" fallback.
            lo=max(p.n_min,x0[i]-h[i]);hi=min(p.n_max,x0[i]+h[i])
            if hi-lo<1e-12:raise ValueError('cannot difference modulation state')
            xlo=x0.copy();xhi=x0.copy();xlo[i]=lo;xhi[i]=hi
            A[:,i]=(f(xhi,u,d)-f(xlo,u,d))/(hi-lo)
        else:
            A[:,i]=(f(x0+delta,u,d)-f(x0-delta,u,d))/(2*h[i])
    hu=0.0002
    if u-hu < p.n_min or u+hu > p.n_max:
        # Only evaluate feasible perturbed commands.
        hu=min(0.0002,(p.n_max-p.n_min)/1000)
        lo=max(p.n_min,u-hu);hi=min(p.n_max,u+hu)
        B=(f(x0,hi,d)-f(x0,lo,d))/(hi-lo)
    else:
        B=(f(x0,u+hu,d)-f(x0,u-hu,d))/(2*hu)
    E=np.zeros((3,2))
    E[:,0]=(f(x0,u,_change_disturbance(d,source_delta=0.02))-f(x0,u,_change_disturbance(d,source_delta=-0.02)))/0.04
    E[:,1]=(f(x0,u,_change_disturbance(d,return_delta=0.02))-f(x0,u,_change_disturbance(d,return_delta=-0.02)))/0.04
    power=lambda xx,dd:power_fn(_state(xx),p,dd)
    p0=float(power(x0,d));px=np.zeros(3)
    for i in range(3):
        dd=np.zeros(3);dd[i]=h[i]
        if i==2:
            lo=max(p.n_min,x0[i]-h[i]);hi=min(p.n_max,x0[i]+h[i])
            xlo=x0.copy();xhi=x0.copy();xlo[i]=lo;xhi[i]=hi
            px[i]=(power(xhi,d)-power(xlo,d))/(hi-lo)
        else:
            px[i]=(power(x0+dd,d)-power(x0-dd,d))/(2*h[i])
    ps=(power(x0,_change_disturbance(d,source_delta=0.02))-
        power(x0,_change_disturbance(d,source_delta=-0.02)))/0.04
    return Linearization(x0,float(u),d0,nx,A,B,E,p0,px,float(ps))


def _prediction(l: Linearization, sources: list[Disturbance], horizon: int):
    """Eliminate predicted states: x[j]=c[j]+M[j]@U."""
    c=[l.x0.copy()];m=[np.zeros((3,horizon))]
    affine=l.next0-l.A@l.x0-l.B*l.u0
    for j in range(horizon):
        d=np.array([sources[j].t_source,sources[j].t_return])
        cj=l.A@c[-1]+affine+l.E@(d-l.d0)
        mj=l.A@m[-1]
        mj[:,j]+=l.B
        c.append(cj);m.append(mj)
    return np.array(c),np.array(m)


@dataclass(frozen=True)
class MPCSolution:
    accepted: bool
    command: float
    status: str
    linearization: Linearization | None
    predicted: np.ndarray | None
    nonlinear: np.ndarray | None
    max_temp_error_k: float
    max_power_relative_error: float
    objective: float | None
    horizon_used: int
    qp_iterations: int


def solve_mpc(x: State, previous: float, p: Parameters, d: Disturbance,
              cfg: MPCConfig, target_k: float, forecast: list[Disturbance],
              prices_eur_per_kwh: list[float], *, force_failure: bool=False,
              advance_fn: Callable | None=None,
              power_fn: Callable | None=None) -> MPCSolution:
    """Solve an LTV-QP, validate nonlinearly against SAME forecast, never alter plant.

    A feasible QP with local model/constraint mismatch may still be rejected.
    A failure returns previous command; supervisory MPCController replaces it
    with freshly bumpless-initialized bounded PI (never an indefinite stale hold).
    """
    if force_failure:
        return MPCSolution(False,previous,'forced_solver_failure',None,None,None,np.inf,np.inf,None,0,0)
    if len(forecast)<cfg.horizon or len(prices_eur_per_kwh)<cfg.horizon:
        raise ValueError('forecast must cover requested horizon')
    if not all(np.isfinite(q) for q in prices_eur_per_kwh[:cfg.horizon]):
        raise ValueError('prices must be finite')
    try:
        # This version linearizes only source/return disturbances. Explicitly
        # reject variations in process spec, flow, or ambient rather than silently
        # extrapolate a prediction model that omitted their Jacobians.
        if any((z.t_required != d.t_required or z.t_ambient != d.t_ambient or
                z.c_proc != d.c_proc) for z in forecast[:cfg.horizon]):
            return MPCSolution(False,previous,'unsupported_disturbance_forecast',
                               None,None,None,np.inf,np.inf,None,0,0)
        advance_fn=advance_fn or _advance
        power_fn=power_fn or (lambda state,par,dist: output(state,par,dist).p_el)
        l=linearize(x,previous,p,d,cfg,advance_fn=advance_fn,power_fn=power_fn)
        N=cfg.horizon; c,m=_prediction(l,forecast,N)
        dim=2*N;H=np.zeros((dim,dim));g=np.zeros(dim)
        for j in range(N):
            tb=m[j+1,1]; err=c[j+1,1]-target_k
            H[:N,:N]+=2*cfg.w_tracking*np.outer(tb,tb)
            g[:N]+=2*cfg.w_tracking*err*tb
            H[j,j]+=2*cfg.w_effort
            g[j]-=2*cfg.w_effort*previous
            H[N+j,N+j]+=2*cfg.w_slack
            # Price is EUR/kWh, electric power is W, period is seconds:
            # cost(EUR)=price * P_el(W) * period / 3_600_000.
            price=prices_eur_per_kwh[j]
            g[:N]+=cfg.w_electric_eur*price*cfg.period_s/3_600_000*(l.power_x@m[j])
        D=np.eye(N)
        for j in range(1,N):D[j,j-1]=-1
        b=np.zeros(N);b[0]=-previous
        H[:N,:N]+=2*cfg.w_movement*D.T@D
        g[:N]+=2*cfg.w_movement*D.T@b
        H=(H+H.T)/2
        if np.linalg.eigvalsh(H).min() < -1e-8:
            raise RuntimeError('non-PSD QP Hessian')
        rows=[];low=[];high=[]
        def constrain(row,lo=-np.inf,hi=np.inf):
            rows.append(row);low.append(lo);high.append(hi)
        for j in range(N):
            du=np.zeros(dim);du[j]=1
            if j:du[j-1]=-1;constrain(du,-p.max_command_step,p.max_command_step)
            else:constrain(du,previous-p.max_command_step,previous+p.max_command_step)
            for idx,lim in ((0,cfg.temp_trust_k),(1,cfg.temp_trust_k),(2,cfg.modulation_trust)):
                row=np.zeros(dim);row[:N]=m[j+1,idx]
                constrain(row,l.x0[idx]-lim-c[j+1,idx],l.x0[idx]+lim-c[j+1,idx])
            row=np.zeros(dim);row[:N]=m[j+1,0]
            constrain(row,hi=cfg.t_header_max_k-c[j+1,0])
            row=np.zeros(dim);row[:N]=m[j+1,1]
            constrain(row,hi=cfg.t_buffer_max_k-c[j+1,1])
            # Quality constraint derived by same physical HX implementation
            # used by the truth plant, but evaluated at forecast d[j].
            from .core import heat_exchanger
            threshold=heat_exchanger(x.tb,p,forecast[j]).t_b_min_service
            if threshold is not None:
                row=np.zeros(dim);row[:N]=m[j+1,1];row[N+j]=1
                constrain(row,lo=threshold-c[j+1,1])
        ub=np.array([p.n_max]*N+[cfg.min_service_slack_k]*N)
        lb=np.array([p.n_min]*N+[0.]*N)
        z0=np.concatenate((np.full(N,previous),np.full(N,1.0)))
        z0=np.maximum(lb,np.minimum(ub,z0))
        z0=np.array(z0,float)
        if cfg.solver_backend == 'slsqp':
            res=minimize(lambda z:float(.5*z@H@z+g@z),z0,
                  jac=lambda z:H@z+g,method='SLSQP',
                  bounds=Bounds(lb,ub),
                  constraints=[LinearConstraint(np.array(rows),low,high)],
                  options={'maxiter':cfg.maxiter,'ftol':1e-8,'disp':False})
            if not res.success or not np.all(np.isfinite(res.x)):
                return MPCSolution(False,previous,'qp_'+str(res.message),l,None,None,np.inf,np.inf,None,N,int(res.nit))
            z=np.asarray(res.x,float)
            iterations=int(res.nit)
        else:
            # Exact same finite-horizon quadratic programme; OSQP receives
            # upper-triangular sparse Hessian, constraints and variable bounds.
            # OSQP is optional, and its availability is checked by CI.
            import osqp
            from scipy import sparse
            matrix=np.vstack((np.array(rows,float),np.eye(dim)))
            lbound=np.concatenate((np.array(low,float),lb))
            ubound=np.concatenate((np.array(high,float),ub))
            qp=osqp.OSQP()
            qp.setup(P=sparse.triu(sparse.csc_matrix(H),format='csc'),q=g,
                     A=sparse.csc_matrix(matrix),l=lbound,u=ubound,
                     verbose=False,eps_abs=1e-6,eps_rel=1e-6,max_iter=max(4000,cfg.maxiter*40),
                     adaptive_rho=True)
            res=qp.solve()
            iterations=int(res.info.iter)
            if res.x is None or str(res.info.status).lower()!='solved' or not np.all(np.isfinite(res.x)):
                return MPCSolution(False,previous,'qp_osqp_'+str(res.info.status),l,None,None,np.inf,np.inf,None,N,iterations)
            z=np.asarray(res.x,float)
        # A successful solver status is not accepted without *our own* primal
        # box and general linear constraint audit; no backend is privileged.
        if np.max(np.maximum(lb-z,z-ub)) > 1e-5:
            return MPCSolution(False,previous,'qp_variable_bound_violation',l,None,None,np.inf,np.inf,None,N,iterations)
        linear=np.array([c[j]+m[j]@z[:N] for j in range(N+1)])
        check=np.array(rows)@z
        if np.min(check-np.array(low))<-1e-5 or np.min(np.array(high)-check)<-1e-5:
            return MPCSolution(False,previous,'qp_constraint_violation',l,linear,None,np.inf,np.inf,None,N,iterations)
        truth=[x];actual_p=[];affine_p=[]
        for j in range(N):
            real=power_fn(truth[-1],p,forecast[j])
            aff=l.p0+l.power_x@(_vec(truth[-1])-l.x0)+l.power_source*(forecast[j].t_source-d.t_source)
            actual_p.append(real);affine_p.append(aff)
            truth.append(advance_fn(truth[-1],float(z[j]),p,forecast[j],cfg.period_s,cfg.integration_step_s))
        true=np.array([_vec(xx) for xx in truth]);
        err=float(np.max(abs(true[:,0:2]-linear[:,0:2])))
        perr=float(np.max(abs(np.array(actual_p)-np.array(affine_p))/np.maximum(np.abs(np.array(actual_p)),1000.)))
        if np.any(true[1:,0] > cfg.t_header_max_k+1e-6) or np.any(true[1:,1]>cfg.t_buffer_max_k+1e-6):
            return MPCSolution(False,previous,'nonlinear_state_constraint_violation',l,linear,true,err,perr,None,N,iterations)
        if err>cfg.nonlinear_temp_tolerance_k or perr>cfg.nonlinear_power_relative_tolerance:
            return MPCSolution(False,previous,'nonlinear_rollout_mismatch',l,linear,true,err,perr,None,N,iterations)
        return MPCSolution(True,float(z[0]),'accepted',l,linear,true,err,perr,float(.5*z@H@z+g@z),N,iterations)
    except (ValueError,RuntimeError,OverflowError,FloatingPointError,ImportError) as exc:
        return MPCSolution(False,previous,'prediction_error:'+str(exc),None,None,None,np.inf,np.inf,None,0,0)


@dataclass
class MPCController:
    p_model: Parameters
    cfg: MPCConfig
    setpoint_k: float
    backup_pi: PISettings
    bias_command: float
    price_forecast: Callable[[float],float]=lambda t:0.16
    disturbance_forecast: Callable[[float,Disturbance],Disturbance] | None=None
    always_fail: bool=False
    state_transition: Callable | None=None
    electric_power: Callable | None=None
    decisions: list[MPCSolution]=field(default_factory=list)
    fallback_events: int=0
    pi: PIController | None=None

    def command(self,t:float,x:State,d:Disturbance,previous:float,p_plant:Parameters)->float:
        cfg=self.cfg
        sources=[];prices=[]
        for j in range(cfg.horizon):
            tj=t+j*cfg.period_s
            sources.append(self.disturbance_forecast(tj,d) if self.disturbance_forecast else d)
            prices.append(float(self.price_forecast(tj)))
        solution=solve_mpc(x,previous,self.p_model,d,cfg,self.setpoint_k,sources,prices,
                           force_failure=self.always_fail,
                           advance_fn=self.state_transition,power_fn=self.electric_power)
        if not solution.accepted and cfg.horizon>2 and not self.always_fail:
            shorter=MPCConfig(**{**cfg.__dict__,'horizon':max(2,cfg.horizon//2)})
            retry=solve_mpc(x,previous,self.p_model,d,shorter,self.setpoint_k,sources,prices,
                            advance_fn=self.state_transition,power_fn=self.electric_power)
            solution=retry if retry.accepted else solution
        self.decisions.append(solution)
        if solution.accepted:
            self.pi=None
            return solution.command
        self.fallback_events+=1
        if self.pi is None:
            self.pi=PIController(self.backup_pi,self.setpoint_k,self.bias_command,cfg.period_s)
        self.pi.setpoint_k=self.setpoint_k
        # PIController initializes its integral from the LAST ACTUALLY APPLIED command;
        # simulate() separately enforces slew and box bounds at handoff.
        return self.pi.command(t,x,d,previous,p_plant)


def closed_loop_mpc(p:Parameters, cfg:MPCConfig, pi_backup:PISettings,
                    duration_s:float=7200., *, advance_forecast:bool=False,
                    force_failure:bool=False, mismatch:Parameters|None=None):
    """Comparable synthetic schedule: equal current information (persistence)
    or separate forecast-advantaged experiment. Disturbance changes at t=3600s
    and t=4800s; PI benchmark must use the same period and plant.
    """
    design_x,design_u,_=equilibrium(p)
    plant=mismatch if mismatch is not None else p
    ctrl=MPCController(p,cfg,design_x.tb+0.4,pi_backup,design_u,always_fail=force_failure)
    def disturb(t):
        return Disturbance(t_return=363.15 if t<3600 else 365.15,
                           t_source=333.15 if t<4800 else 328.15)
    if advance_forecast:
        ctrl.disturbance_forecast=lambda future,current:disturb(future)
    sched=Schedule(lambda t:design_u,disturb,
          feedback=lambda t,x,d,previous:ctrl.command(t,x,d,previous,plant))
    run=simulate(plant,design_x,sched,duration_s,cfg.integration_step_s,cfg.period_s)
    tgt=np.full_like(run.times,ctrl.setpoint_k)
    return run,ctrl,tgt