"""WP7: equal-sensing PI / synthetic-predictor MPC on ONE property-backed truth plant.

Both controllers actuate the identical CoolProp-derived heat/power-map and
IF97-water-enthalpy dynamic process. The MPC forecast stays the *frozen WP2
synthetic model*, deliberately testing structural mismatch rather than claiming
a property-matched MPC model. No true header or modulation states are leaked
to either controller after initialization. No real compressor, controller
stability or equipment viability is validated.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
import numpy as np

from .core import Parameters, State, Disturbance, heat_exchanger
from .benchmark import nominal_tunings
from .pi import PIController, PISettings
from .mpc import MPCConfig, MPCController, _advance
from .realfluid import CycleMap, PointRejected, coolprop_backend, _prop, water_loop_state
from .thermo_feasibility import hold_service_at_buffer

WATER_MASS_KG = 5000.0
BENCHMARK = "WP7_PropertyTruth_SyntheticPredictor_Pilot_v1"


@dataclass(frozen=True)
class PropertyControlCase:
    name: str = "nominal"
    sensor_noise_sd_k: float = 0.0
    sensor_delay_samples: int = 0
    seed: int = 23
    source_drop_k: float = 0.0
    return_rise_k: float = 0.0

    def __post_init__(self):
        if not self.name or not all(isfinite(x) and x >= 0 for x in (
            self.sensor_noise_sd_k, self.source_drop_k, self.return_rise_k)):
            raise ValueError("invalid WP7 case name/noise/disturbance")
        if isinstance(self.sensor_delay_samples, bool) or not isinstance(self.sensor_delay_samples, int) or self.sensor_delay_samples < 0:
            raise ValueError("sensor_delay_samples must be nonnegative integer")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")


def declared_property_cases() -> tuple[PropertyControlCase, ...]:
    """Predeclare these held-out scenarios; do not search controller gains on them."""
    return (
        PropertyControlCase("nominal"),
        PropertyControlCase("source_minus3K", source_drop_k=3.0),
        PropertyControlCase("sensor_noise_0p20K", sensor_noise_sd_k=.20),
        PropertyControlCase("sensor_delay_60s", sensor_delay_samples=1),
        PropertyControlCase("combined_noise_delay_source", sensor_noise_sd_k=.20, sensor_delay_samples=1, source_drop_k=3.0, return_rise_k=1.0),
    )


def _disturbance(t: float, case: PropertyControlCase) -> Disturbance:
    return Disturbance(
        t_return=363.15 if t < 2400.0 else 363.15 + case.return_rise_k,
        t_source=333.15 if t < 4500.0 else 333.15 - case.source_drop_k,
    )


def run_property_controller(
    model: CycleMap, case: PropertyControlCase, method: str,
    *, pi_settings: PISettings | None = None, cfg: MPCConfig | None = None,
    duration_s: float = 7200.0, step_s: float = 20.0,
    sensor_period_s: float = 60.0, control_period_s: float = 120.0,
    props=None, force_mpc_failure: bool = False,
) -> dict:
    """Run a fixed-gain PI or MPC against the exact same property-map dynamic truth.

    The only feedback observation is temperature of the buffer, with specified
    sensor sample/noise/delay. The open-loop WP2 observer predicts header and
    actuator states from known commands. Initial state is a common design prior
    and is the only point where the experiment grants both true unmeasured states.
    Unreachable property states fail closed and disqualify the ENTIRE run.
    """
    if method not in ("PI_IMC", "PI_relay", "MPC_persistence"):
        raise ValueError("unknown WP7 controller")
    cfg = cfg or MPCConfig(horizon=6, period_s=control_period_s,
                           integration_step_s=step_s)
    if abs(cfg.period_s-control_period_s) > 1e-9:
        raise ValueError("controller and MPC period mismatch")
    if not all(isfinite(x) and x > 0 for x in (duration_s, step_s, sensor_period_s, control_period_s)):
        raise ValueError("positive finite time grid required")
    if (abs(duration_s/step_s-round(duration_s/step_s)) > 1e-9 or
        abs(sensor_period_s/step_s-round(sensor_period_s/step_s)) > 1e-9 or
        abs(control_period_s/sensor_period_s-round(control_period_s/sensor_period_s)) > 1e-9 or
        abs(duration_s/control_period_s-round(duration_s/control_period_s)) > 1e-9 or
        abs(cfg.integration_step_s/step_s-round(cfg.integration_step_s/step_s)) > 1e-9):
        raise ValueError("integration, sensing and control grids must align")
    if model.modulations[0] >= model.modulations[-1]:
        raise ValueError("invalid property-map modulation envelope")
    # Control bounds match the declared property map; extrapolation is never
    # emulated by evaluating a zero-speed or unsupported condenser state.
    p = replace(Parameters(hx_mode="duty_limiter"),
                n_min=max(0., model.modulations[0]),
                n_max=min(1., model.modulations[-1]))
    props = props if props is not None else coolprop_backend()
    nominal_tunings_dict, _, _ = nominal_tunings()
    setting = pi_settings if pi_settings is not None else (
        nominal_tunings_dict["relay_PI"] if method == "PI_relay"
        else nominal_tunings_dict["IMC_lambda_0p5tau"]
    )
    d0 = _disturbance(0., case)
    initial = hold_service_at_buffer(403.15, model, p, d0, props=props)
    if not initial["status"].startswith("same_service_property_feasible"):
        raise PointRejected("no_property_backed_initial_equilibrium:" + initial["status"])
    x0 = State(initial["t_header_k"],403.15,initial["required_modulation"])
    q0, _, _ = model.evaluate(x0.n,d0.t_source,x0.th)
    if not np.isfinite(q0) or q0 <= 0:
        raise PointRejected("invalid_initial_cycle_heat")
    pressure = model.assumptions.service_header_pressure_pa
    # Water inventory uses a pressure-specific IF97 enthalpy, not fixed cp.
    water_loop_state(x0.tb,model.assumptions,props)
    h0 = _prop(props,"H","IF97::Water","T",x0.tb,"P",pressure)
    # State: header K, water enthalpy J/kg, n, and FIVE integrated energy flows.
    y = np.array([x0.th,h0,x0.n,0.,0.,0.,0.,0.], dtype=float)
    target = x0.tb + 0.4
    pi = PIController(setting,target,x0.n,control_period_s)
    mpc = MPCController(p,cfg,target,setting,x0.n,always_fail=force_mpc_failure) if method=="MPC_persistence" else None
    rng = np.random.default_rng(case.seed)
    fifo = [x0.tb] * case.sensor_delay_samples
    estimator = x0
    previous_d = d0
    applied = x0.n
    noise_draws = []
    decisions = []
    truth_at_decisions = []
    estimates_at_decisions = []
    sensed_at_decisions = []
    energy_spec_unserved = 0.0
    energy_physical_shortfall = 0.0
    passed_steps = 0
    iae = 0.0
    max_sensor_error = 0.0
    max_header_estimation_error = 0.0
    max_modulation_estimation_error = 0.0
    max_slew = 0.0
    failure = None
    finished_steps = 0
    sensor_steps = int(round(sensor_period_s/step_s))
    control_steps = int(round(control_period_s/step_s))

    def tb_of(v):
        return _prop(props, "T", "IF97::Water", "P", pressure, "H", float(v[1]))

    def stage(v, u, d):
        header, enthalpy, n = v[:3]
        if n < p.n_min-1e-8 or n > p.n_max+1e-8:
            raise PointRejected("physical_modulation_outside_declared_grid")
        tb = tb_of(v)
        # Enforce IF97 liquid margin at each physical integrator stage.
        water_loop_state(tb,model.assumptions,props)
        qhp,pel,_ = model.evaluate(float(n),d.t_source,float(header))
        hx = heat_exchanger(tb,p,d)
        qhb = p.khb*(header-tb)
        lh = p.ua_h*(header-d.t_ambient)
        lb = p.ua_b*(tb-d.t_ambient)
        return np.array([(qhp-qhb-lh)/p.c_h,
                         (qhb-hx.q_transferred-lb)/WATER_MASS_KG,
                         (u-n)/p.tau_n,
                         qhp,pel,hx.q_transferred,lh,lb],float)

    times = int(round(duration_s/step_s))
    for k in range(times):
        t = k*step_s
        d = _disturbance(t,case)
        try:
            true_tb = tb_of(y)
            if k % sensor_steps == 0:
                if k:
                    # Deliberately model-only propagation for unmeasured states.
                    estimator = _advance(estimator,applied,p,previous_d,
                                         sensor_period_s,cfg.integration_step_s)
                estimator = State(estimator.th,estimator.tb,
                                  float(np.clip(estimator.n,p.n_min,p.n_max)))
                noise = float(rng.normal(0,case.sensor_noise_sd_k))
                noise_draws.append(noise)
                fifo.append(true_tb+noise)
                seen = float(fifo.pop(0))
                estimator = State(estimator.th,seen,estimator.n)
                previous_d = d
                if k % control_steps == 0:
                    truth_at_decisions.append((y[0],true_tb,y[2]))
                    estimates_at_decisions.append((estimator.th,estimator.tb,estimator.n))
                    sensed_at_decisions.append(seen)
                    max_sensor_error=max(max_sensor_error,abs(seen-true_tb))
                    max_header_estimation_error=max(max_header_estimation_error,abs(estimator.th-y[0]))
                    max_modulation_estimation_error=max(max_modulation_estimation_error,abs(estimator.n-y[2]))
                    proposed = (mpc.command(t,estimator,d,applied,p) if mpc
                                else pi.command(t,estimator,d,applied,p))
                    # Same physical hard bounds and slew for every controller.
                    bounded = float(np.clip(proposed,p.n_min,p.n_max))
                    next_applied = float(np.clip(bounded,applied-p.max_command_step,
                                                applied+p.max_command_step))
                    max_slew = max(max_slew,abs(next_applied-applied))
                    applied = next_applied
                    decisions.append((t,applied))
            hx = heat_exchanger(true_tb,p,d)
            passed_steps += int(hx.qualified)
            energy_spec_unserved += hx.q_spec_unserved * step_s
            energy_physical_shortfall += max(0.,hx.q_requested-hx.q_transferred)*step_s
            iae += abs(true_tb-target)*step_s
            k1=stage(y,applied,d)
            k2=stage(y+.5*step_s*k1,applied,d)
            k3=stage(y+.5*step_s*k2,applied,d)
            k4=stage(y+step_s*k3,applied,d)
            y = y + (step_s/6.)*(k1+2*k2+2*k3+k4)
            if not np.all(np.isfinite(y)):
                raise PointRejected("nonfinite_property_trajectory")
            finished_steps += 1
        except (PointRejected,ValueError,FloatingPointError,OverflowError) as exc:
            failure = f"{type(exc).__name__}:{exc}"
            break

    statuses = {}
    if mpc:
        for decision in mpc.decisions:
            statuses[decision.status] = statuses.get(decision.status,0)+1
    complete = failure is None and finished_steps == times
    # Full-horizon metrics must be null on failure; partial runs cannot win.
    residual = (p.c_h*(y[0]-x0.th) + WATER_MASS_KG*(y[1]-h0)
                - y[3] + y[5] + y[6] + y[7])
    if complete and abs(residual)>1.0:
        complete = False
        failure = "integrated_energy_balance_residual_exceeds_1J"
    eligible = bool(complete and passed_steps == times
                    and energy_spec_unserved <= 3.6
                    and energy_physical_shortfall <= 3.6)
    return {
        "benchmark_id": BENCHMARK, "case":case.name, "controller":method,
        "plant":"WP7 CoolProp condenser Q/P map + IF97 enthalpy; UNCALIBRATED",
        "mpc_predictor":"WP2 synthetic nominal model (not WP7 property-derived)",
        "measurement":"one sampled noisy/delayed buffer temperature; current known disturbances",
        "equipment_verified":False,
        "status":"complete" if complete else "failed_physical_or_numerical_constraint",
        "failure_reason":failure or "",
        "completed_time_s":finished_steps*step_s,
        "duration_s":duration_s,
        "sensor_noise_sd_k":case.sensor_noise_sd_k,
        "sensor_delay_s":case.sensor_delay_samples*sensor_period_s,
        "seed":case.seed, "sample_period_s":sensor_period_s,
        "control_period_s":control_period_s,
        "decisions":len(decisions),
        "accepted_mpc":sum(s.accepted for s in mpc.decisions) if mpc else 0,
        "pi_fallbacks":mpc.fallback_events if mpc else 0,
        "solver_statuses":statuses,
        "iae_Ks":float(iae) if complete else None,
        "electricity_kWh":float(y[4]/3.6e6) if complete else None,
        "process_heat_kWh":float(y[5]/3.6e6) if complete else None,
        "physical_heat_shortfall_kWh":float(energy_physical_shortfall/3.6e6) if complete else None,
        "unserved_spec_heat_kWh":float(energy_spec_unserved/3.6e6) if complete else None,
        "qualified_fraction":passed_steps/times if complete else None,
        "matched_service_gate":eligible,
        "max_energy_residual_J":float(abs(residual)) if complete else None,
        "max_applied_command_slew":max_slew,
        "max_sensor_error_K":max_sensor_error,
        "max_header_observer_error_K":max_header_estimation_error,
        "max_modulation_observer_error":max_modulation_estimation_error,
        "noise_draws":noise_draws,
        "true_states_at_decisions":truth_at_decisions,
        "estimated_states_at_decisions":estimates_at_decisions,
        "sensed_buffer_at_decisions":sensed_at_decisions,
        "applied_commands":decisions,
    }
