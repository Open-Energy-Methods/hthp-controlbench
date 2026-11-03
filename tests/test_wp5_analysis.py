"""WP5 audit regression: never turn infeasibility, data loss or unequal information into wins."""
from __future__ import annotations
import copy
import json
import unittest
from pathlib import Path
from ht_hp_controlbench.wp5_analysis import (
    load_matrix, validate_matrix, analyze, dominates, safe_pct, MPC, RELAY, METHODS)

DATA=Path(__file__).resolve().parents[1]/'results/wp4_robustness_matrix.csv'

class WP5AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=load_matrix(DATA)
        cls.cases=('nominal','measurement_delay_60s')
    def subset(self):
        return [copy.deepcopy(x) for x in self.rows if x['case'] in self.cases]
    def test_real_source_completeness(self):
        x=analyze(self.rows)
        self.assertEqual(x['source_rows'],100)
        self.assertEqual(x['completed_runs'],100)
        self.assertEqual(len(x['paired']),80)
        self.assertEqual(len(x['per_case']),20)
        self.assertEqual(len(x['failed_runs']),0)
    def test_raw_and_service_qualified_are_separate(self):
        x=analyze(self.rows)
        self.assertEqual(x['raw_iae_wins'],{MPC:14,RELAY:6})
        self.assertEqual(x['service_qualified_iae_wins'],{MPC:13,RELAY:5})
        self.assertEqual(x['mpc_relay_service_matched_cases'],18)
        self.assertEqual(x['all_methods_service_pass_cases'],16)
    def test_severe_has_fallback_and_is_not_qualified(self):
        x=analyze(self.rows)
        self.assertEqual(x['MPC_total_fallback_events'],48)
        self.assertEqual(x['MPC_fallback_cases'],['severe_actuator_capacity_minus40pct'])
        severe=next(r for r in x['per_case'] if r['case']=='severe_actuator_capacity_minus40pct')
        self.assertFalse(severe['MPC_qualified_for_energy_comparison'])
        self.assertIsNone(severe['eligible_iae_winner'])
    def test_process_ua_failure_not_ranked_for_energy(self):
        x=analyze(self.rows)
        row=next(r for r in x['per_case'] if r['case']=='process_UA_minus20pct')
        self.assertFalse(row['MPC_qualified_for_energy_comparison'])
        self.assertEqual(row['service_pass_count'],0)
        self.assertIsNone(row['eligible_iae_winner'])
    def test_reject_missing_case_method_pair(self):
        with self.assertRaises(ValueError):validate_matrix(self.subset()[:-1],expected_cases=self.cases)
    def test_reject_duplicate_even_if_count_matches(self):
        rr=self.subset();rr[-1]=copy.deepcopy(rr[0])
        with self.assertRaises(ValueError):validate_matrix(rr,expected_cases=self.cases)
    def test_reject_changed_sensor_seed_within_paired_case(self):
        rr=self.subset();rr[0]['seed']='1000'
        with self.assertRaisesRegex(ValueError,'unmatched seed'):
            validate_matrix(rr,expected_cases=self.cases)
    def test_reject_unmatched_control_clock(self):
        rr=self.subset();rr[0]['controller_sampling_s']='60'
        with self.assertRaisesRegex(ValueError,'clock'):
            validate_matrix(rr,expected_cases=self.cases)
    def test_reject_nonfinite_iae(self):
        rr=self.subset();rr[0]['iae_Ks']='nan'
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            validate_matrix(rr,expected_cases=self.cases)
    def test_reject_reconciliation_of_qp_fallback_counts(self):
        rr=self.subset()
        m=next(x for x in rr if x['method']==MPC)
        m['pi_fallbacks']='1'
        with self.assertRaisesRegex(ValueError,'decisions do not reconcile'):
            validate_matrix(rr,expected_cases=self.cases)
    def test_reject_unequal_information_mode(self):
        rr=self.subset();rr[0]['information_mode']='full true plant states'
        with self.assertRaisesRegex(ValueError,'information-mode mismatch'):
            validate_matrix(rr,expected_cases=self.cases)
    def test_numerical_failure_retained_and_never_imputed(self):
        rr=self.subset()
        rr[0]['finite']='False';rr[0]['iae_Ks']='';rr[0]['error']='RuntimeError: injected plant divergence'
        x=analyze(rr,expected_cases=self.cases)
        self.assertEqual(len(x['failed_runs']),1)
        self.assertEqual(x['completed_runs'],9)
        self.assertEqual(len(x['paired']),4)
        affected=next(r for r in x['per_case'] if r['case']==rr[0]['case'])
        self.assertFalse(affected['numerical_complete'])
        self.assertIsNone(affected['raw_iae_winner'])
    def test_failed_run_must_describe_failure(self):
        rr=self.subset();rr[0]['finite']='False';rr[0]['error']=''
        with self.assertRaisesRegex(ValueError,'error description'):
            validate_matrix(rr,expected_cases=self.cases)
    def test_service_gate_checks_transfer_and_temperature_separately(self):
        rr=self.subset(); m=next(x for x in rr if x['method']==MPC and x['case']=='nominal')
        m['service_qualified_fraction']='1';m['service_unserved_kWh']='0.0'
        m['physical_energy_shortfall_kWh']='1.2'
        x=analyze(rr,expected_cases=self.cases)
        case=next(x for x in x['per_case'] if x['case']=='nominal')
        self.assertFalse(case['MPC_qualified_for_energy_comparison'])
    def test_dominance_requires_qualified_service(self):
        a={'service_pass':True,'iae_Ks':1.,'electrical_kWh':4.,'command_variation':2.}
        b={'service_pass':True,'iae_Ks':2.,'electrical_kWh':4.,'command_variation':2.}
        self.assertTrue(dominates(a,b));self.assertFalse(dominates(b,a))
        a['service_pass']=False;self.assertFalse(dominates(a,b))
    def test_percentage_zero_baseline_not_invented(self):
        self.assertIsNone(safe_pct(1.,0.))
        self.assertAlmostEqual(safe_pct(80.,100.),-20.)
    def test_all_rows_have_correct_grouping(self):
        x=analyze(self.rows)
        self.assertEqual(sum(a['cases'] for a in x['categories']),20)
        self.assertEqual(len(x['methods']),5)
    def test_negative_energy_does_not_hide_unserved_service(self):
        x=analyze(self.rows)
        for r in x['per_case']:
            if not r['MPC_qualified_for_energy_comparison']:
                self.assertIn('DO NOT',r['MPC_energy_interpretation'])
    def test_scenario_provenance_is_synthetic(self):
        x=analyze(self.rows)
        self.assertIn('synthetic',x['metadata']['physical_status'])
        self.assertIn('not',x['metadata']['descriptive_only'])

if __name__=='__main__': unittest.main()
