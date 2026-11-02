"""WP3 robust simulated PI study (synthetic, uncalibrated HTHP plant).

Controllers are identified/tuned ONCE on the nominal passive-HX plant; gain and
bias are frozen across all mismatched-plant, noise, delay, and saturation cases.
Noise affects only controller observations, never the ground-truth state.
The simulator integrates the same nonlinear dynamics and energy conservation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import numpy as np

from .core import Parameters, Disturbance, State, equilibrium
from .pi import PISettings, PIController, metrics
from .sim import Simulation, Schedule, simulate


@dataclass(frozen=True)
class RobustnessCase:
    name: str
    plant: Parameters
    noise_sd_k: float = 0.0
    delay_updates: int = 0
    seed: int = 0
    initial_return_k: float = 363.15
    return_after_step_k: float = 365.15
    source_after_step_k: float = 328.15
    note: str = ''
    excursion_setpoint_k: float = 0.0
    excursion_start_s: float = 1200.0
    excursion_end_s: float = 3000.0

    def __post_init__(self) -> None:
        if self.noise_sd_k < 0 or not math.isfinite(self.noise_sd_k):
            raise ValueError('sensor noise standard deviation must be finite and >= 0')
        if not isinstance(self.delay_updates, int) or self.delay_updates < 0:
            raise ValueError('delay_updates must be nonnegative integer')
        if self.excursion_setpoint_k < 0 or self.excursion_end_s <= self.excursion_start_s:
            raise ValueError('invalid setpoint excursion')
        if not all(map(math.isfinite, (self.initial_return_k, self.return_after_step_k,
                                       self.source_after_step_k, self.excursion_setpoint_k))):
            raise ValueError('disturbance temperatures must be finite')


@dataclass(frozen=True)
class RobustnessRun:
    case: RobustnessCase
    controller: PIController
    simulation: Simulation
    target: np.ndarray
    measurement_times_s: np.ndarray
    sensed_buffer_k: np.ndarray
    true_buffer_at_sample_k: np.ndarray
    sampled_control_s: float
    return_step_s: float

    def summary(self) -> dict[str, float | int | str | bool]:
        m = metrics(self.simulation, self.target, self.sampled_control_s)
        sim = self.simulation
        u = sim.commands
        # A command near its bound is not always evidence of constraint-induced
        # performance loss; report it descriptively, not as a failed run.
        sample_stride = int(round(self.sampled_control_s/(sim.times[1]-sim.times[0])))
        sample_u = u[::sample_stride]
        near_limit = np.isclose(sample_u, self.case.plant.n_min, atol=1e-4) | np.isclose(
            sample_u, self.case.plant.n_max, atol=1e-4)
        finite = bool(np.all(np.isfinite(sim.states)) and np.all(np.isfinite(u)))
        actual_required = np.where(sim.times < self.return_step_s,
            self.case.plant.c_proc * max(0.0, self.case.plant.t_required - self.case.initial_return_k),
            self.case.plant.c_proc * max(0.0, self.case.plant.t_required - self.case.return_after_step_k))
        physical_shortfall_kwh = float(np.trapezoid(np.maximum(actual_required-sim.q_process,0.0),
                                                   x=sim.times) / 3_600_000.0)
        command_total_variation = float(np.sum(np.abs(np.diff(sample_u))))
        # Stable recovery: remain within 1 K for at least 600 s after the
        # commanded excursion returns to the normal reference. No recovery => None.
        recovery = None
        if self.case.excursion_setpoint_k > 0:
            from_idx = int(np.searchsorted(sim.times, self.case.excursion_end_s))
            samples_needed = int(round(600.0/(sim.times[1]-sim.times[0])))
            err = np.abs(self.target-sim.states[:,1])
            for idx in range(from_idx, len(sim.times)-samples_needed):
                if np.all(err[idx:idx+samples_needed+1] <= 1.0):
                    recovery = float(sim.times[idx]-self.case.excursion_end_s)
                    break
        return {
            'case': self.case.name,
            'controller': self.controller.settings.source,
            'seed': self.case.seed,
            'noise_sd_K': self.case.noise_sd_k,
            'delay_updates': self.case.delay_updates,
            'iae_Ks': m['iae_Ks'],
            'rmse_K': m['rmse_K'],
            'max_abs_error_K': m['max_abs_error_K'],
            'service_unserved_kWh': m['service_unserved_kWh'],
            'electrical_kWh': m['electrical_kWh'],
            'physical_energy_shortfall_kWh': physical_shortfall_kwh,
            'command_total_variation': command_total_variation,
            'recovery_within_1K_s': recovery,
            'max_energy_residual_J': m['max_energy_residual_J'],
            'max_command_slew': m['max_command_slew'],
            'saturation_events': self.controller.saturation_events,
            'slew_events': self.controller.slew_events,
            'sample_fraction_at_command_bounds': float(np.mean(near_limit)),
            'min_command': float(np.min(u)),
            'max_command': float(np.max(u)),
            'min_buffer_C': float(np.min(sim.states[:, 1])-273.15),
            'max_buffer_C': float(np.max(sim.states[:, 1])-273.15),
            'service_qualified_sample_fraction': float(np.mean(sim.service_met)),
            'finite': finite,
        }


def simulate_robust_pi(
    nominal: Parameters,
    config: PISettings,
    case: RobustnessCase,
    *,
    duration_s: float = 14_400.0,
    integration_step_s: float = 10.0,
    control_period_s: float = 60.0,
    setpoint_step_k: float = 0.4,
    return_step_s: float = 3600.0,
    source_step_s: float = 7200.0,
) -> RobustnessRun:
    """Execute a noise/delay/plant-uncertainty case without reidentifying PI.

    The design bias and initial temperatures are from the nominal plant. Model
    mismatch therefore legitimately induces steady-state errors; the actual
    plant equilibrium and tuned gains are NOT provided to the controller.

    Delay is an integer number of *control updates*, with a seeded prehistory.
    This is a sample-and-hold measurement delay, not a continuous sensor model.
    """
    if control_period_s <= 0 or integration_step_s <= 0:
        raise ValueError('positive sample and integration periods required')
    x0, u0, _ = equilibrium(nominal)
    ctrl = PIController(config, x0.tb+setpoint_step_k, u0, control_period_s)
    rng = np.random.default_rng(case.seed)
    # Prehistory is initially steady at nominal point. Add measurement noise on
    # arrival of each sample, *then* delay transmission to the controller.
    history = [float(x0.tb)] * case.delay_updates
    observations: list[float] = []
    sample_times: list[float] = []
    true_samples: list[float] = []

    def disturbances(t: float) -> Disturbance:
        return Disturbance(
            t_return=case.initial_return_k if t < return_step_s else case.return_after_step_k,
            t_source=333.15 if t < source_step_s else case.source_after_step_k,
        )

    def feedback(t: float, x: State, d: Disturbance, last: float) -> float:
        ctrl.setpoint_k = x0.tb + setpoint_step_k + (case.excursion_setpoint_k
            if case.excursion_start_s <= t < case.excursion_end_s else 0.0)
        sample = float(x.tb + rng.normal(0.0, case.noise_sd_k))
        history.append(sample)
        sensed = history.pop(0)
        observed = State(x.th, sensed, x.n)
        sample_times.append(t)
        observations.append(sensed)
        true_samples.append(x.tb)
        return ctrl.command(t, observed, d, last, case.plant)

    schedule = Schedule(lambda t: u0, disturbances, feedback)
    sim = simulate(case.plant, x0, schedule, duration_s, integration_step_s, control_period_s)
    target = np.full_like(sim.times, x0.tb + setpoint_step_k)
    if case.excursion_setpoint_k > 0:
        active = (sim.times >= case.excursion_start_s) & (sim.times < case.excursion_end_s)
        target[active] += case.excursion_setpoint_k
    return RobustnessRun(case, ctrl, sim, target,
                         np.array(sample_times), np.array(observations),
                         np.array(true_samples), control_period_s, return_step_s)


def declared_cases(nominal: Parameters) -> list[RobustnessCase]:
    """Predeclared synthetic stress scenarios; no post-hoc selection of winners.

    Explicit parameter variations isolate uncertainty mechanisms. Some
    combinations could create actuator-limited service and are included rather
    than filtered out. Sensor seeds are paired for every controller.
    """
    result = [RobustnessCase('nominal', nominal)]
    for sd in (0.10, 0.30):
        for seed in (11, 23, 47):
            result.append(RobustnessCase(f'noise_{sd:.2f}K_seed_{seed}', nominal,
                                         noise_sd_k=sd, seed=seed))
    for delay in (1, 3):
        result.append(RobustnessCase(f'measurement_delay_{delay*60}s', nominal,
                                     delay_updates=delay))
    for name, change in [
        ('buffer_mass_minus20pct', {'c_b': nominal.c_b * 0.8}),
        ('buffer_mass_plus20pct', {'c_b': nominal.c_b * 1.2}),
        ('header_buffer_coupling_minus20pct', {'khb': nominal.khb * 0.8}),
        ('process_UA_minus20pct', {'ua_proc': nominal.ua_proc * 0.8}),
        ('heatpump_capacity_minus20pct', {'q_hp_rated': nominal.q_hp_rated * 0.8}),
        ('heatpump_capacity_plus20pct', {'q_hp_rated': nominal.q_hp_rated * 1.2}),
    ]:
        result.append(RobustnessCase(name, replace(nominal, **change)))
    result.append(RobustnessCase('severe_actuator_capacity_minus40pct',
                                 replace(nominal, q_hp_rated=nominal.q_hp_rated * 0.6),
                                 note='Deliberately infeasible/saturated envelope; not a normal design point'))
    result.append(RobustnessCase('combined_noise_0.3K_delay_180s_capacity_minus20pct',
                                 replace(nominal,q_hp_rated=nominal.q_hp_rated*0.8),
                                 noise_sd_k=0.30,delay_updates=3,seed=11,
                                 note='Combined uncertainty is explicitly separate from one-at-a-time screen'))
    result.append(RobustnessCase('combined_noise_0.3K_delay_180s_bypass',
                                 replace(nominal,hx_mode='duty_limiter',ua_flow_exponent=0.8),
                                 noise_sd_k=0.30,delay_updates=3,seed=23))
    result.append(RobustnessCase('temporary_setpoint_plus12K_saturation_recovery',
                                 nominal, excursion_setpoint_k=12.0,
                                 note='Recovery from temporary constrained setpoint spike; not a service requirement'))
    result.append(RobustnessCase('bypass_UA_flow_exponent_0.8',
                                 replace(nominal, hx_mode='duty_limiter', ua_flow_exponent=0.8),
                                 note='Unidentified plant-mode transfer from passive baseline'))
    return result