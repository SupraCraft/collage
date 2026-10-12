"""Negative qualification for source-plan/real-world evidence correlation."""
import copy
import unittest

from tools.correlate_vanilla_runtime_source import (
    Refused, PRODUCER, EXPECTED_STEPS, correlate
)

SHA = "da25005e8729e6f013f7108ac5b8869dd46323befc78efdae18221b26cafe5f8"
INTENT = "a"*64

def fixture():
    manifest = {
        "producer": PRODUCER, "sha256": SHA,
        "world_id": "lantern-rdte", "release_id": "lantern-core-restore-26-3",
        "world_save_included": False, "collage_deployed": False,
    }
    source = {
        "schema": "collage.artifact-consumer-source-parity/1",
        "classification": "SOURCE_ARTIFACT_AND_INTENT_PARITY_VALIDATED",
        "common_intent_sha256": INTENT,
        "candidate": {
            "sha256": SHA, "producer": PRODUCER, "world_id": "lantern-rdte",
            "release_id": "lantern-core-restore-26-3", "minecraft_version": "26.3",
            "kind": "datapack", "member_count": 3
        },
        "audience_receipts": {
            kind: {"source_classification": "SOURCE_VALIDATED",
                   "request_sha256": "b"*64}
            for kind in ("human", "automation", "agent")
        },
        "principal_authenticated": False, "real_provider_readback": False,
        "mutation_authorized": False, "world_activated": False,
    }
    runtime = {
        "schema": "supracraft.op3-disposable-world-activation/1",
        "classification": "REAL_VANILLA_DATAPACK_ACTIVATION_AND_FAULT_ROLLBACK",
        "source_artifact_sha256": SHA, "producer": PRODUCER,
        "world_id": "lantern-rdte", "release_id": "lantern-core-restore-26-3",
        "minecraft_version": "26.3", "protocol": 777,
        "steps": EXPECTED_STEPS[:], "baseline_world_hash": "1"*64,
        "candidate_world_hash": "2"*64, "restored_world_hash": "1"*64,
        "independent_server_trigger_pass": True,
        "fault_injection_rollback_pass": True,
        "rollback_absence_of_datapack_behavior_pass": True,
        "world_restored_exact_bytes_before_restart": True,
        "collage_deployed": False, "truenas_deployed": False,
        "human_automation_agent_parity_qualified": False,
        "client_gameplay_qualified": False, "full_two_rivers_world_qualified": False,
        "operational_selection": False, "physical_truenas_apply": "HOLD",
    }
    return manifest, source, runtime


class JoinTests(unittest.TestCase):
    def test_positive_correlation_keeps_authority_narrow(self):
        r = correlate(*fixture())
        self.assertEqual(r["artifact_sha256"], SHA)
        self.assertEqual(set(r["source_plan_audiences"]),
                         {"human", "automation", "agent"})
        for flag in ("collage_deployment_performed", "truenas_provider_observed",
                     "principal_authentication_verified",
                     "human_automation_agent_mutation_parity_qualified",
                     "operational_selection"):
            self.assertFalse(r[flag])
        self.assertTrue(r["independent_vanilla_rollback_pass"])

    def test_wrong_artifact_and_realm_refused(self):
        for owner, name, value in (
            (0, "sha256", "f"*64),
            (1, "candidate", dict(fixture()[1]["candidate"], world_id="wrong")),
            (2, "world_id", "wrong"),
            (2, "release_id", "different"),
            (2, "protocol", 776),
        ):
            items = list(copy.deepcopy(fixture()))
            items[owner][name] = value
            with self.subTest(name=name), self.assertRaises(Refused):
                correlate(*items)

    def test_missing_audience_or_forged_delegation_claim_refused(self):
        items = list(fixture())
        items[1]["audience_receipts"].pop("agent")
        with self.assertRaisesRegex(Refused, "THREE_AUDIENCE"):
            correlate(*items)
        items = list(fixture())
        items[1]["mutation_authorized"] = True
        with self.assertRaisesRegex(Refused, "PRIVILEGE"):
            correlate(*items)

    def test_failed_activation_and_rollback_refused(self):
        for field, value in (
            ("independent_server_trigger_pass", False),
            ("rollback_absence_of_datapack_behavior_pass", False),
            ("restored_world_hash", "4"*64),
            ("steps", EXPECTED_STEPS[:-1]),
        ):
            items = list(copy.deepcopy(fixture()))
            items[2][field] = value
            with self.subTest(field=field), self.assertRaises(Refused):
                correlate(*items)

    def test_fake_provider_or_operational_promotion_refused(self):
        for field, value in (
            ("truenas_deployed", True),
            ("collage_deployed", True),
            ("client_gameplay_qualified", True),
            ("physical_truenas_apply", "APPLY"),
        ):
            items = list(copy.deepcopy(fixture()))
            items[2][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                    Refused, "PROMOTION"):
                correlate(*items)


if __name__ == "__main__":
    unittest.main()
