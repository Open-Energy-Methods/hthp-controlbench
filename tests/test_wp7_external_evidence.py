"""Independent WP7 data provenance, no-fabricated-observer and source-bound gates."""
from __future__ import annotations

from dataclasses import replace
from hashlib import md5
import unittest

from ht_hp_controlbench.wp7_external_evidence import (
    WIDMAIER, LECLERCQ, PublicDataset, get_public_bytes, parse_verified_csv,
    audit_widmaier, audit_leclercq, evidence_gate, finite_source_bound,
    observer_record_gate, REQUIRED_ASSET_EVIDENCE,
)


WIDMAIER_FIXTURE=(
    "source,compressor,refrigerant,T_ev_C,T_co_C,T_suc_C,p_suc_bar,"
    "p_dis_bar,eta_is,eta_vol,DeltaT_sh_K\n"
    "Bitzer EN12900,sim,R1233zd(E),20,55,28,1.2,3,0.95,0.95,8\n"
    "Bock EN12900,sim,R1233zd(E),25,65,37,1.5,4,0.90,0.89,12\n"
    "Experimental OST (London 2023),lab,R1233zd(E),50,,65,2.1,9,0.62,0.79,15\n"
    "Experimental OST (London 2023),lab,R1233zd(E),55,,70,2.3,10,0.66,0.82,15\n"
    "Experimental OST (Purdue 2024 HFO),lab,R1336mzz(Z),40,,55,2,8,0.54,0.75,15\n"
).encode()
LECLERCQ_FIXTURE=(
    "eps_is;eps_v;P_ratio;x_ref_in;Speed_m;P_su_cp;P_ex_cp\n"
    "0.42;0.68;3.2;0.40;1100;1.1;3.5\n"
    "0.58;0.82;4.1;0.90;1560;1.2;4.9\n"
).encode()


def local_spec(source,payload):
    return replace(source,md5_checksum=md5(payload).hexdigest())


class ExternalDataAuditTests(unittest.TestCase):
    def test_widmaier_rejects_en12900_rows_as_measurements(self):
        spec=local_spec(WIDMAIER,WIDMAIER_FIXTURE)
        rows=parse_verified_csv(WIDMAIER_FIXTURE,spec)
        result=audit_widmaier(rows)
        self.assertEqual(result["all_records"],5)
        self.assertEqual(result["experimentally_measured_records"],3)
        self.assertEqual(result["pure_R1233zd_experimental_records"],2)
        self.assertEqual(result["generated_EN12900_records_not_measured"],2)
        self.assertAlmostEqual(result["pure_refrigerant_eta_is_overall_electrical"]["median"],.64)
        self.assertIsNone(result["pure_refrigerant_T_co_C"])
        self.assertFalse(result["asset_matching_reference_WP7"])
        self.assertIn("ELECTRICAL",result["why_not_direct_validation"])

    def test_unknown_data_provenance_is_not_silently_accepted(self):
        fixture=WIDMAIER_FIXTURE.replace(b"Bitzer EN12900",b"anonymous")
        rows=parse_verified_csv(fixture,local_spec(WIDMAIER,fixture))
        with self.assertRaisesRegex(ValueError,"unrecognized"):
            audit_widmaier(rows)

    def test_two_phase_lubricated_compressor_is_not_dry_suction_validation(self):
        spec=local_spec(LECLERCQ,LECLERCQ_FIXTURE)
        out=audit_leclercq(parse_verified_csv(LECLERCQ_FIXTURE,spec))
        self.assertEqual(out["experimentally_measured_records"],2)
        self.assertEqual(out["model_compatibility"],"OUT_OF_DOMAIN_TWO_PHASE_WITH_OIL")
        self.assertAlmostEqual(out["reported_isentropic_efficiency"]["median"],.5)
        self.assertFalse(out["asset_matching_reference_WP7"])

    def test_source_integrity_check_rejects_even_one_byte_modified(self):
        spec=local_spec(WIDMAIER,WIDMAIER_FIXTURE)
        with self.assertRaisesRegex(ValueError,"checksum mismatch"):
            parse_verified_csv(WIDMAIER_FIXTURE+b"\n",spec)
        # An exact fixture must pass provenance checksum and strict parsing.
        self.assertEqual(len(parse_verified_csv(WIDMAIER_FIXTURE,spec)),5)

    def test_raw_csv_missing_or_duplicate_fields_rejected(self):
        bad=b"a,a\n1,2\n"
        with self.assertRaisesRegex(ValueError,"duplicate"):
            parse_verified_csv(bad,local_spec(WIDMAIER,bad))
        ragged=b"a,b\n1,2,3\n"
        with self.assertRaisesRegex(ValueError,"ragged"):
            parse_verified_csv(ragged,local_spec(WIDMAIER,ragged))

    def test_no_source_flow_never_becomes_a_physical_capacity_pass(self):
        x=finite_source_bound(186500.)
        self.assertEqual(x["status"],"UNVERIFIED_SOURCE_FLOW_OR_TEMPERATURE")
        self.assertIsNone(x["necessary_source_heat_upper_bound_w"])
        self.assertFalse(x["heat_exchanger_verified"])
        insufficient=finite_source_bound(186500.,mass_flow_kg_s=4.,
                          cp_j_kgk=4200.,inlet_k=333.15,minimum_outlet_k=323.15)
        self.assertEqual(insufficient["status"],"NECESSARY_SOURCE_ENERGY_BOUND_FAIL")
        self.assertLess(insufficient["heat_margin_w"],0)
        sufficient=finite_source_bound(186500.,mass_flow_kg_s=5.,
                          cp_j_kgk=4200.,inlet_k=333.15,minimum_outlet_k=323.15)
        self.assertIn("ONLY",sufficient["status"])
        self.assertFalse(sufficient["heat_exchanger_verified"])
        with self.assertRaises(ValueError):
            finite_source_bound(186500.,mass_flow_kg_s=-1.,
                cp_j_kgk=4200.,inlet_k=333.15,minimum_outlet_k=323.15)

    def test_oem_other_machine_data_cannot_greenlight_reference(self):
        out=evidence_gate()
        self.assertEqual(out["status"],"NOT_EQUIPMENT_VALIDATED")
        self.assertEqual(out["matched_section_count"],0)
        self.assertEqual(len(out["missing_sections"]),len(REQUIRED_ASSET_EVIDENCE))
        other={"manufacturer_capacity_map":{
            "origin":"manufacturer","asset_id":"different_125kW_unit",
            "reference_uri":"https://example.org/test"}}
        result=evidence_gate(other,asset_id="target_310kW")
        self.assertIn("manufacturer_capacity_map",result["nonqualifying_sections"])
        self.assertEqual(result["status"],"NOT_EQUIPMENT_VALIDATED")
        # Even all supposedly "matching" URLs cannot automatically certify.
        refs={key:{"origin":"manufacturer","asset_id":"target_310kW",
                    "reference_uri":"https://example.org/nominal-doc"}
                    for key in REQUIRED_ASSET_EVIDENCE}
        result=evidence_gate(refs,asset_id="target_310kW")
        self.assertEqual(result["matched_section_count"],len(REQUIRED_ASSET_EVIDENCE))
        self.assertEqual(result["status"],"NOT_EQUIPMENT_VALIDATED")

    def test_no_observer_ground_truth_or_sensor_calibration_means_not_validated(self):
        self.assertEqual(observer_record_gate(None)["status"],
                         "NO_MATCHED_INSTRUMENTED_OBSERVER_DATA")
        # Fake numerical traces cannot be automatically stamped as measured.
        rows=[{"time_s":t,"buffer_measured_k":403.15,
               "header_measured_k":406.2,"modulation_measured":.75,
               "command_applied":.75,"source_measured_k":333.15,
               "return_measured_k":363.15} for t in (0.,60.,120.,180.)]
        self.assertEqual(observer_record_gate(rows)["status"],
                         "MISMATCHED_OR_UNIDENTIFIED_OBSERVER_ASSET")
        supplied={
            "raw_data_sha256":"a"*64,"measurement_reference_uri":"https://example.org/data",
            "sensor_calibration_uri":"https://example.org/calibration",
            "instrumented_asset_id":"target_310kW",
            "train_interval":[0,60],"heldout_interval":[120,180],
        }
        report=observer_record_gate(rows,asset_id="target_310kW",evidence=supplied)
        self.assertEqual(report["status"],"INSTRUMENTED_TRACE_PRESENT__INDEPENDENT_REVIEW_REQUIRED")
        self.assertIn("not yet",report["claim"])
        supplied["heldout_interval"]=[60,180]
        report=observer_record_gate(rows,asset_id="target_310kW",evidence=supplied)
        self.assertEqual(report["status"],"OBSERVER_SPLIT_LEAKAGE_OR_OVERLAP")


if __name__=="__main__":
    unittest.main()
