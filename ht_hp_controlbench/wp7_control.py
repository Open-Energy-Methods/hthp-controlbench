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
from .wp7_predictor import PropertyPredictor

WATER_MASS_KG = 5000.0
BENCHMARK = "WP7_PropertyTruth_SyntheticPredictor_Pilot_v1"


def _validate_accepted_endpoint(v,model:CycleMap,d:Disturbance,props,pressure:float):
    """Fail closed on the *accepted* RK4 state, not only its four substages.

    The RK4 weighted candidate need not coincide with any intermediate stage.
    Endpoint property and interpolation checks catch a possible step crossing
    the phase or declared compressor-map envelope.
    """
    if not np.all(np.isfinite(v)):
        raise PointRejected("nonfinite_property_trajectory")
    tb=_prop(props,"T","IF97::Water","P",pressure,"H",float(v[1]))
    water_loop_state(max(float(v[0]),float(tb)),model.assumptions,props)
    model.evaluate(float(v[2]),d.t_source,float(v[0]))
    return float(tb)


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
    observer_backend: str = "auto",
    truth_parameters: Parameters | None = None,
    benchmark_id: str = BENCHMARK,
) -> dict:
    """Run a fixed-gain PI or MPC against the exact same property-map dynamic truth.

    The only feedback observation is temperature of the buffer, with specified
    sensor sample/noise/delay. The open-loop WP2 observer predicts header and
    actuator states from known commands. Initial state is a common design prior
    and is the only point where the experiment grants both true unmeasured states.
    Optional truth_parameters changes only the physical truth balances and HX,
    while the observer/controller retain nominal p. This tests declared
    synthetic model/plant mismatch, not equipment-identified uncertainty.
    Unreachable property states fail closed and disqualify the ENTIRE run.
    """
    if not isinstance(benchmark_id,str) or not benchmark_id.strip():
        raise ValueError("nonempty benchmark identifier required")
    if method not in ("PI_IMC", "PI_relay", "MPC_persistence", "MPC_property"):
        raise ValueError("unknown WP7 controller")
    if observer_backend not in ("auto","synthetic","property"):
        raise ValueError("unknown WP7 observer backend")
    if method == "MPC_property" and observer_backend == "synthetic":
        raise ValueError("property-MPC comparison requires its declared property observer")
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
    p_truth = truth_parameters if truth_parameters is not None else p
    # Keep the actual compressor command, rate limits and declared map domain
    # identical across the nominal observer and perturbed truth plant.
    # This extension tests dynamics/HX model errors, NOT actuator/OEM limits.
    if (p_truth.hx_mode != p.hx_mode or
        p_truth.n_min != p.n_min or p_truth.n_max != p.n_max or
        p_truth.max_command_step != p.max_command_step or
        p_truth.flow_mode != p.flow_mode):
        raise ValueError("WP7 mismatch experiment cannot alter actuator, flow mode, or service architecture")
    props = props if props is not None else coolprop_backend()
    if pi_settings is not None:
        setting = pi_settings
    else:
        nominal_tunings_dict, _, _ = nominal_tunings()
        setting = (nominal_tunings_dict["relay_PI"] if method == "PI_relay"
                   else nominal_tunings_dict["IMC_lambda_0p5tau"])
    d0 = _disturbance(0., case)
    initial = hold_service_at_buffer(403.15, model, p_truth, d0, props=props)
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
    property_predictor = PropertyPredictor(model,props,mass_kg=WATER_MASS_KG)
    use_property_observer = (observer_backend=="property" or
        (observer_backend=="auto" and method=="MPC_property"))
    mpc = None
    if method in ("MPC_persistence","MPC_property"):
        mpc = MPCController(p,cfg,target,setting,x0.n,
                            always_fail=force_mpc_failure,
                            state_transition=property_predictor.advance if method=="MPC_property" else None,
                            electric_power=property_predictor.power if method=="MPC_property" else None)
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
    header_estimation_error_sum = 0.0
    modulation_estimation_error_sum = 0.0
    sensor_innovations = []
    max_slew = 0.0
    failure = None
    finished_steps = 0
    sensor_steps = int(round(sensor_period_s/step_s))
    control_steps = int(round(control_period_s/step_s))

    def tb_of(v):
        return _prop(props, "T", "IF97::Water", "P", pressure, "H", float(v[1]))

    def stage(v, u, d):
        header, enthalpy, n = v[:3]
        if n < p_truth.n_min-1e-8 or n > p_truth.n_max+1e-8:
            raise PointRejected("physical_modulation_outside_declared_grid")
        tb = tb_of(v)
        # Enforce IF97 liquid margin at each physical integrator stage.
        water_loop_state(tb,model.assumptions,props)
        qhp,pel,_ = model.evaluate(float(n),d.t_source,float(header))
        hx = heat_exchanger(tb,p_truth,d)
        qhb = p_truth.khb*(header-tb)
        lh = p_truth.ua_h*(header-d.t_ambient)
        lb = p_truth.ua_b*(tb-d.t_ambient)
        return np.array([(qhp-qhb-lh)/p_truth.c_h,
                         (qhb-hx.q_transferred-lb)/WATER_MASS_KG,
                         (u-n)/p_truth.tau_n,
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
                    estimator = (
                        property_predictor.advance(estimator,applied,p,previous_d,
                                                   sensor_period_s,cfg.integration_step_s)
                        if use_property_observer else
                        _advance(estimator,applied,p,previous_d,
                                 sensor_period_s,cfg.integration_step_s))
                estimator = State(estimator.th,estimator.tb,
                                  float(np.clip(estimator.n,p.n_min,p.n_max)))
                noise = float(rng.normal(0,case.sensor_noise_sd_k))
                noise_draws.append(noise)
                fifo.append(true_tb+noise)
                seen = float(fifo.pop(0))
                sensor_innovations.append(seen-estimator.tb)
                estimator = State(estimator.th,seen,estimator.n)
                previous_d = d
                if k % control_steps == 0:
                    truth_at_decisions.append((y[0],true_tb,y[2]))
                    estimates_at_decisions.append((estimator.th,estimator.tb,estimator.n))
                    sensed_at_decisions.append(seen)
                    max_sensor_error=max(max_sensor_error,abs(seen-true_tb))
                    header_error=abs(estimator.th-y[0])
                    modulation_error=abs(estimator.n-y[2])
                    max_header_estimation_error=max(max_header_estimation_error,header_error)
                    max_modulation_estimation_error=max(max_modulation_estimation_error,modulation_error)
                    header_estimation_error_sum+=header_error
                    modulation_estimation_error_sum+=modulation_error
                    proposed = (mpc.command(t,estimator,d,applied,p) if mpc
                                else pi.command(t,estimator,d,applied,p))
                    # Same physical hard bounds and slew for every controller.
                    bounded = float(np.clip(proposed,p.n_min,p.n_max))
                    next_applied = float(np.clip(bounded,applied-p.max_command_step,
                                                applied+p.max_command_step))
                    max_slew = max(max_slew,abs(next_applied-applied))
                    applied = next_applied
                    decisions.append((t,applied))
            hx = heat_exchanger(true_tb,p_truth,d)
            k1=stage(y,applied,d)
            k2=stage(y+.5*step_s*k1,applied,d)
            k3=stage(y+.5*step_s*k2,applied,d)
            k4=stage(y+step_s*k3,applied,d)
            candidate=y+(step_s/6.)*(k1+2*k2+2*k3+k4)
            _validate_accepted_endpoint(candidate,model,d,props,pressure)
            # Accounting and state are committed only after all stages AND the
            # exact new endpoint pass property/phase/envelope checks.
            y=candidate
            passed_steps += int(hx.qualified)
            energy_spec_unserved += hx.q_spec_unserved * step_s
            energy_physical_shortfall += max(0.,hx.q_requested-hx.q_transferred)*step_s
            iae += abs(true_tb-target)*step_s
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
    residual = (p_truth.c_h*(y[0]-x0.th) + WATER_MASS_KG*(y[1]-h0)
                - y[3] + y[5] + y[6] + y[7])
    if complete and abs(residual)>1.0:
        complete = False
        failure = "integrated_energy_balance_residual_exceeds_1J"
    eligible = bool(complete and passed_steps == times
                    and energy_spec_unserved <= 3.6
                    and energy_physical_shortfall <= 3.6)
    return {
        "benchmark_id": benchmark_id, "case":case.name, "controller":method,
        "plant":("WP7 CoolProp condenser Q/P map + IF97 enthalpy; UNCALIBRATED" +
                 (" | truth-only HX/actuator-dynamics mismatch" if p_truth != p else "")),
        "truth_model_mismatch":p_truth != p,
        "truth_parameter_ratios_to_nominal":{
            key:float(getattr(p_truth,key)/getattr(p,key))
            for key in ("ua_proc","khb","tau_n","c_h","ua_h","ua_b","c_hot")
            if getattr(p_truth,key)!=getattr(p,key)
        },
        "mpc_predictor":("WP7 CoolProp/IF97 enthalpy and condenser map" if method=="MPC_property"
                         else "WP2 synthetic nominal model (not WP7 property-derived)"), 
        "observer_model":("WP7 property enthalpy state predictor" if use_property_observer
                          else "WP2 synthetic nominal model"),
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
        # Final inventories MUST be matched for a valid paired energy claim:
        # an identical process service alone can consume stored heat instead.
        "final_header_energy_delta_kWh":float(p_truth.c_h*(y[0]-x0.th)/3.6e6) if complete else None,
        "final_buffer_energy_delta_kWh":float(WATER_MASS_KG*(y[1]-h0)/3.6e6) if complete else None,
        "final_total_energy_delta_kWh":float((p_truth.c_h*(y[0]-x0.th)+WATER_MASS_KG*(y[1]-h0))/3.6e6) if complete else None,
        "final_compressor_modulation":float(y[2]) if complete else None,
        "final_applied_command":float(applied) if complete else None,
        "max_energy_residual_J":float(abs(residual)) if complete else None,
        "max_applied_command_slew":max_slew,
        "max_sensor_error_K":max_sensor_error,
        "max_header_observer_error_K":max_header_estimation_error,
        "max_modulation_observer_error":max_modulation_estimation_error,
        "mean_absolute_header_observer_error_K":header_estimation_error_sum/max(1,len(decisions)),
        "mean_absolute_modulation_observer_error":modulation_estimation_error_sum/max(1,len(decisions)),
        "sensor_innovations_K":sensor_innovations,
        "noise_draws":noise_draws,
        "true_states_at_decisions":truth_at_decisions,
        "estimated_states_at_decisions":estimates_at_decisions,
        "sensed_buffer_at_decisions":sensed_at_decisions,
        "applied_commands":decisions,
    }


def compare_property_pair(pi: dict, mpc: dict,
                          *, inventory_tolerance_kwh: float = 0.5,
                          actuator_tolerance: float = 0.02) -> dict:
    """No electricity credit without same service, final stores AND actuator state.

    Each store and their sum are independently matched. No compensating header
    charge is allowed to mask a depleted IF97 buffer. The tolerances are
    prespecified *numerical comparability* limits, not calibrated uncertainty.
    """
    if pi["case"] != mpc["case"] or pi["controller"] not in ("PI_IMC","PI_relay") or mpc["controller"] not in ("MPC_persistence","MPC_property"):
        raise ValueError("invalid WP7 paired comparison identity")
    if pi.get("truth_parameter_ratios_to_nominal",{}) != mpc.get("truth_parameter_ratios_to_nominal",{}):
        raise ValueError("different truth-plant parameter scenarios cannot be compared")
    for key in ("duration_s","sample_period_s","control_period_s","sensor_delay_s",
                "sensor_noise_sd_k","seed","plant","measurement","benchmark_id"):
        if pi[key] != mpc[key]:
            raise ValueError("unequal scenario/observation/plant budget: " + key)
    if (not isfinite(inventory_tolerance_kwh) or inventory_tolerance_kwh <= 0 or
        not isfinite(actuator_tolerance) or actuator_tolerance <= 0):
        raise ValueError("positive finite numerical comparison tolerances required")
    complete = pi["status"] == "complete" and mpc["status"] == "complete"
    reasons=[]
    if not complete:
        reasons.append("incomplete_physical_or_numerical_run")
    if complete and not (pi["matched_service_gate"] and mpc["matched_service_gate"]):
        reasons.append("unmatched_or_unqualified_process_service")
    for key,label in (
        ("final_header_energy_delta_kWh","terminal_header_inventory_mismatch"),
        ("final_buffer_energy_delta_kWh","terminal_buffer_inventory_mismatch"),
        ("final_total_energy_delta_kWh","terminal_total_thermal_energy_mismatch"),
    ):
        if complete and abs(pi[key]-mpc[key]) > inventory_tolerance_kwh:
            reasons.append(label)
    for key,label in (
        ("final_compressor_modulation","terminal_compressor_modulation_mismatch"),
        ("final_applied_command","terminal_applied_command_mismatch"),
    ):
        if complete and abs(pi[key]-mpc[key]) > actuator_tolerance:
            reasons.append(label)
    eligible = complete and not reasons
    return {
        "case":pi["case"],
        "baseline":pi["controller"],
        "candidate":mpc["controller"],
        "both_numerically_complete":complete,
        "both_service_eligible":bool(complete and pi["matched_service_gate"] and mpc["matched_service_gate"]),
        "terminal_equivalent":bool(complete and not any("terminal_" in x for x in reasons)),
        "eligible_for_conditional_electricity_comparison":eligible,
        "ineligibility_reasons":";".join(reasons),
        "delta_IAE_Ks":mpc["iae_Ks"]-pi["iae_Ks"] if complete else None,
        "delta_electricity_kWh":mpc["electricity_kWh"]-pi["electricity_kWh"] if eligible else None,
        "raw_delta_electricity_kWh_diagnostic":mpc["electricity_kWh"]-pi["electricity_kWh"] if complete else None,
        "interpretation":("conditional_matched_service_and_terminal_inventory" if eligible else
                          "NOT_ELIGIBLE_FOR_ELECTRICITY_SAVING_CLAIM"),
    }
