"""Versioned simulated controller identification for the L1 WP3–WP5 benchmark.

The nominal gains are always IDENTIFIED from the current WP2 equations; never
copied from a historical CSV or source-code literal. This is an uncalibrated
synthetic baseline, not an equipment-validated controller.
"""
from __future__ import annotations

from .core import Parameters
from .pi import (identify_step, identify_relay, tune_imc,
                 tune_relay_tyreus_luyben)

BENCHMARK_ID = "L1_RelayPeak_v2"


def nominal_tunings():
    """Return fixed-on-nominal PI gains plus their independently measured origins.

    Identification must be performed once on the unchanged no-bypass nominal
    plant, then the same gains carried to each scenario (no test-set retuning).
    """
    nominal = Parameters(hx_mode="no_bypass")
    step = identify_step(nominal)
    relay = identify_relay(nominal)
    settings = {
        "IMC_lambda_0p5tau": tune_imc(step, 0.5),
        "IMC_lambda_1tau": tune_imc(step, 1.0),
        "IMC_lambda_2tau": tune_imc(step, 2.0),
        "relay_PI": tune_relay_tyreus_luyben(relay),
    }
    return settings, step, relay


def tuning_manifest(settings, step, relay):
    """Serialize the exact tunings and source identification for provenance."""
    return {
        "benchmark_id": BENCHMARK_ID,
        "controller_origin": "same synthetic nominal no-bypass plant, no scenario retuning",
        "relay_amplitude_definition": "mean of half peak-to-peak true temperature excursions, five complete cycles",
        "relay_temperature_amplitude_K": relay.temperature_amplitude_k,
        "relay_period_s": relay.period_s,
        "relay_ultimate_gain_approx": relay.ultimate_gain_u_per_k,
        "step_gain_K_per_command": step.gain_k_per_u,
        "step_tau_s": step.tau_s,
        "step_delay_s": step.delay_s,
        "gains": {
            key: {"kp_command_per_K": setting.kp,
                  "ki_command_per_Ks": setting.ki,
                  "tracking_time_s": setting.tracking_time_s}
            for key, setting in settings.items()
        },
        "physical_status": "simulation-only, no compressor or rig calibration",
    }
