"""WP3 robustness acceptance tests: measurement, delay, uncertainty and actuator limits."""
import unittest
from dataclasses import replace
import numpy as np
from ht_hp_controlbench.core import Parameters
from ht_hp_controlbench.pi import closed_loop, identify_step, tune_imc, tune_relay_tyreus_luyben, identify_relay
from ht_hp_controlbench.robustness import RobustnessCase, simulate_robust_pi, declared_cases


class RobustPIAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nominal = Parameters(hx_mode='no_bypass')
        fit = identify_step(cls.nominal)
        cls.imc = tune_imc(fit, 0.5)
        cls.relay = tune_relay_tyreus_luyben(identify_relay(cls.nominal))

    def run_case(self, case, method=None, duration_s=3600):
        return simulate_robust_pi(self.nominal, method or self.imc, case,
                                  duration_s=duration_s)

    def test_ideal_measurement_matches_previous_wp3_reference(self):
        run = self.run_case(RobustnessCase('nominal', self.nominal), duration_s=3600)
        old, _, _ = closed_loop(self.nominal, self.imc, duration_s=3600)
        self.assertTrue(np.array_equal(run.simulation.states, old.states))
        self.assertTrue(np.array_equal(run.simulation.commands, old.commands))

    def test_same_seed_produces_bitwise_reproducible_noise_trajectories(self):
        case=RobustnessCase('noise', self.nominal, noise_sd_k=.25, seed=31)
        a=self.run_case(case)
        b=self.run_case(case)
        self.assertTrue(np.array_equal(a.sensed_buffer_k,b.sensed_buffer_k))
        self.assertTrue(np.array_equal(a.simulation.states,b.simulation.states))
        c=self.run_case(replace(case,seed=32))
        self.assertFalse(np.array_equal(a.simulation.states,c.simulation.states))
        self.assertGreater(np.max(abs(a.sensed_buffer_k-a.true_buffer_at_sample_k)),0.05)

    def test_same_sensor_noise_innovations_paired_across_controller_methods(self):
        case=RobustnessCase('paired_noise',self.nominal,noise_sd_k=.3,seed=47)
        a=self.run_case(case,method=self.imc,duration_s=1200)
        b=self.run_case(case,method=self.relay,duration_s=1200)
        noise_a=a.sensed_buffer_k-a.true_buffer_at_sample_k
        noise_b=b.sensed_buffer_k-b.true_buffer_at_sample_k
        np.testing.assert_allclose(noise_a,noise_b,atol=1e-12,rtol=0)
        self.assertFalse(np.array_equal(a.simulation.states,b.simulation.states))

    def test_saturation_recovery_has_no_integrator_runaway(self):
        case=RobustnessCase('temporary_excursion',self.nominal,excursion_setpoint_k=12.0)
        run=self.run_case(case,method=self.relay,duration_s=14_400)
        m=run.summary()
        self.assertGreater(m['saturation_events'],0)
        self.assertGreater(m['command_total_variation'],0)
        self.assertIsNotNone(m['recovery_within_1K_s'])
        self.assertLess(m['recovery_within_1K_s'],3600)
        self.assertLessEqual(m['max_command_slew'],self.nominal.max_command_step+1e-12)
        self.assertLess(m['max_energy_residual_J'],.01)

    def test_physical_shortfall_distinct_from_quality_deficit(self):
        p=replace(self.nominal,q_hp_rated=self.nominal.q_hp_rated*.8)
        run=self.run_case(RobustnessCase('derated',p),method=self.imc,duration_s=14_400)
        m=run.summary()
        # Service-quality failure is a threshold; physical shortfall is energy.
        self.assertGreater(m['service_unserved_kWh'],0)
        self.assertGreater(m['physical_energy_shortfall_kWh'],0)
        self.assertNotAlmostEqual(m['service_unserved_kWh'],m['physical_energy_shortfall_kWh'],delta=1.)

    def test_delay_is_real_historical_sample_not_current_truth(self):
        base=self.run_case(RobustnessCase('base',self.nominal),duration_s=900)
        delayed=self.run_case(RobustnessCase('delay',self.nominal,delay_updates=2),duration_s=900)
        self.assertEqual(len(delayed.sensed_buffer_k),len(base.sensed_buffer_k))
        self.assertAlmostEqual(delayed.sensed_buffer_k[0],delayed.true_buffer_at_sample_k[0])
        self.assertAlmostEqual(delayed.sensed_buffer_k[1],delayed.true_buffer_at_sample_k[0])
        self.assertAlmostEqual(delayed.sensed_buffer_k[2],delayed.true_buffer_at_sample_k[0])
        self.assertAlmostEqual(delayed.sensed_buffer_k[3],delayed.true_buffer_at_sample_k[1])
        self.assertNotEqual(delayed.simulation.states[-1,1],base.simulation.states[-1,1])

    def test_plant_mismatch_not_retuned_or_bias_oracle(self):
        p=replace(self.nominal,q_hp_rated=self.nominal.q_hp_rated*0.8)
        run=self.run_case(RobustnessCase('uncertain_hp',p),duration_s=1800)
        nominal=self.run_case(RobustnessCase('nominal',self.nominal),duration_s=1800)
        self.assertAlmostEqual(run.controller.bias_command,nominal.controller.bias_command)
        self.assertAlmostEqual(run.controller.settings.kp,nominal.controller.settings.kp)
        self.assertTrue(np.array_equal(run.simulation.states[0],nominal.simulation.states[0]))
        self.assertNotAlmostEqual(run.simulation.states[-1,1],nominal.simulation.states[-1,1])

    def test_noise_and_delay_do_not_corrupt_truth_energy_balance(self):
        run=self.run_case(RobustnessCase('bad_sensing',self.nominal,noise_sd_k=.3,
                                        delay_updates=3,seed=19),duration_s=3600)
        self.assertLess(np.max(abs(run.simulation.energy_residual)),0.01)
        self.assertLessEqual(run.summary()['max_command_slew'],self.nominal.max_command_step+1e-9)
        self.assertTrue(run.summary()['finite'])

    def test_actuator_capacity_shortage_is_retained_and_reported(self):
        p=replace(self.nominal,q_hp_rated=self.nominal.q_hp_rated*0.6)
        run=self.run_case(RobustnessCase('severe',p),method=self.relay,duration_s=14_400)
        s=run.summary()
        self.assertLessEqual(s['max_command'],p.n_max+1e-12)
        self.assertGreater(s['saturation_events'],0)
        self.assertGreater(s['sample_fraction_at_command_bounds'],0.01)
        self.assertGreater(s['service_unserved_kWh'],0)
        self.assertLess(s['max_energy_residual_J'],0.01)

    def test_parameter_sweep_includes_both_signs_and_bypass(self):
        cases=declared_cases(self.nominal)
        names=[c.name for c in cases]
        self.assertEqual(len(names),len(set(names)))
        for name in ('buffer_mass_minus20pct','buffer_mass_plus20pct',
                     'heatpump_capacity_minus20pct','heatpump_capacity_plus20pct',
                     'bypass_UA_flow_exponent_0.8','severe_actuator_capacity_minus40pct'):
            self.assertIn(name,names)

    def test_invalid_sensor_scenarios_are_rejected(self):
        for kw in ({'noise_sd_k':-0.1},{'noise_sd_k':float('nan')},{'delay_updates':-1},
                   {'delay_updates':1.5}):
            with self.assertRaises(ValueError):RobustnessCase('bad',self.nominal,**kw)

if __name__=='__main__':unittest.main()