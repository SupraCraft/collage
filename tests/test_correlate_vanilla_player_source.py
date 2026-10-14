"""OP-3D no-game cheap negative verification of correlation only."""
import copy
import unittest

from tools.correlate_vanilla_player_source import correlate, Refused, PRODUCER

HASH = "da25005e8729e6f013f7108ac5b8869dd46323befc78efdae18221b26cafe5f8"
B = "1"*64
C = "2"*64


def fixture():
    identity = {"producer": PRODUCER, "sha256": HASH,
                "world_id": "lantern-rdte",
                "release_id": "lantern-core-restore-26-3",
                "archive_size": 739,
                "world_save_included": False, "collage_deployed": False}
    client = {"requested_version": "26.3", "negotiated_version": "26.3",
              "protocol": 777, "offline_mode": True,
              "server_join_independently_observed": True,
              "client_saw_air_before": True,
              "client_saw_redstone_after": True,
              "action": "mineflayer.placeBlock"}
    plans = {"schema": "collage.artifact-consumer-source-parity/1",
             "classification": "SOURCE_ARTIFACT_AND_INTENT_PARITY_VALIDATED",
             "common_intent_sha256": "f"*64,
             "candidate": {"producer": PRODUCER, "sha256": HASH,
                           "world_id": identity["world_id"],
                           "release_id": identity["release_id"],
                           "minecraft_version": "26.3", "kind": "datapack",
                           "member_count": 3},
             "audience_receipts": {
                 x: {"source_classification": "SOURCE_VALIDATED",
                     "request_sha256": "b"*64}
                 for x in ("human", "automation", "agent")
             },
             "principal_authenticated": False,
             "real_provider_readback": False, "world_activated": False,
             "mutation_authorized": False}
    player = {
        "schema": "supracraft.op3c-vanilla-client-world-artifact/1",
        "classification": "REAL_OFFLINE_PLAYER_ACTION_CAUSAL_ARTIFACT_AND_ROLLBACK",
        "producer": PRODUCER, "source_artifact_sha256": HASH,
        "world_id": identity["world_id"],
        "release_id": identity["release_id"],
        "source_archive_size": 739, "minecraft_version": "26.3",
        "protocol": 777, "candidate_player": dict(client),
        "postrollback_player": dict(client),
        "mineflayer_offline_protocol_qualified": True,
        "player_caused_datapack_effect": True,
        "same_player_action_without_datapack_no_effect": True,
        "rollback_exact_snapshot_before_restart": True,
        "baseline_world_sha256": B, "candidate_world_sha256": C,
        "restored_world_sha256": B,
        "stock_mojang_client_qualified": False,
        "authenticated_account_qualified": False,
        "collage_deployed": False, "truenas_deployed": False,
        "human_automation_agent_parity_qualified": False,
        "full_two_rivers_world_qualified": False,
        "operational_selection": False,
        "physical_truenas_apply": "HOLD",
    }
    return identity, plans, player


def native_fixture():
    source=copy.deepcopy(fixture()[1])
    source.update({
        "source_native_target_profile": "vanilla263-250426",
        "expected_native_app": "rdte-t6-minecraft-vanilla-263",
        "expected_truenas_version": "25.04.2.6",
        "common_intent_sha256": "e"*64,
        "native_guest_with_this_artifact_qualified": False,
    })
    return source


def native_guest_fixture():
    manifest,_,_=fixture()
    digest=manifest["sha256"]
    return {
        "contract":"gha-kvm-system-lab/v1",
        "classification":"SUPPORTED",
        "oracleSatisfied":True,
        "phase":"foundry-materialization",
        "target":{"product":"truenas","version":"25.04.2.6","rung":"T6"},
        "foundry_materialization":{
            "schema":"truenas-minecraft-vanilla263-t6/v1",
            "classification":"SUPPORTED","oracleSatisfied":True,
            "control_sha256":"c1d6d9bd6306de55b12072ea9d0d6411fa7d7f106a6a87bdbe1913c0d82c0615",
            "foundry_ref":"29ec6cba7df51e316b0329926aa85807805dd07b",
            "lantern_artifact_stage":{
                "schema":"supracraft.native-vanilla263-lantern-artifact-stage/1",
                "classification":"REAL_NATIVE_GUEST_ARTIFACT_BYTES_STAGED",
                "artifact_sha256":digest,
                "download_readback_sha256":digest,
                "artifact_size":manifest["archive_size"],
                "world_id":manifest["world_id"],
                "release_id":manifest["release_id"],
                "native_app":"rdte-t6-minecraft-vanilla-263",
                "native_truenas_version":"25.04.2.6",
                "app_quiesced_before_write":True,
                "persisted_on_restart":True,
                "persisted_on_reinstall":True,
                "artifact_gameplay_effect_verified":False,
                "collage_managed_deployment":False,
                "principal_authorized_to_apply":False,
                "physical_truenas_apply":"HOLD",
            },
            "collage_readback":{
                "classification":"PROVIDER_READBACK_MATCH",
                "source_profile":"vanilla263",
                "source_sha":"2b6abe1141e65b8c6872eeba6c8ae39f5a9635f8",
                "native_app":"rdte-t6-minecraft-vanilla-263",
                "world_id":"lantern-rdte",
                "credential_scope":"APPS_READ",
                "transport":"isolated_guest_tls_verified",
                "observation_mutation_count":0,
                "ownership_fields_matched":6,
                "world_activated":False,
                "physical_true_nas_mutated":False,
            },
            "cleanup":{
                "attempted":True,"zero_residue":True,
                "app_absent":True,"owned_world_dataset_absent":True,
            },
        },
    }


class PlayerCorrelationTests(unittest.TestCase):
    def test_native_guest_exact_artifact_join_is_not_same_guest_client_or_authority(self):
        result=correlate(*fixture(),native_source=native_fixture(),
                         native_guest=native_guest_fixture())
        self.assertTrue(result["native_guest_same_zip_staged_and_read_back"])
        self.assertTrue(result["native_guest_app_lifecycle_and_cleanup_correlated"])
        self.assertFalse(result["same_native_guest_real_client_gameplay_verified"])
        self.assertFalse(result["collage_managed_deployment"])
        self.assertFalse(result["principal_authorization_verified"])

    def test_actual_native_guest_anti_forgery_integrity_role_cleanup(self):
        baseline=native_guest_fixture()
        for path,bad in (
            (("classification",),"ORACLE_FAILURE"),
            (("target","version"),"25.04.1"),
            (("foundry_materialization","foundry_ref"),"f"*40),
            (("foundry_materialization","lantern_artifact_stage","artifact_sha256"),"a"*64),
            (("foundry_materialization","lantern_artifact_stage","download_readback_sha256"),"a"*64),
            (("foundry_materialization","lantern_artifact_stage","persisted_on_reinstall"),False),
            (("foundry_materialization","lantern_artifact_stage","artifact_gameplay_effect_verified"),True),
            (("foundry_materialization","collage_readback","credential_scope"),"FULL_ADMIN"),
            (("foundry_materialization","collage_readback","observation_mutation_count"),1),
            (("foundry_materialization","collage_readback","transport"),"insecure"),
            (("foundry_materialization","cleanup","zero_residue"),False),
        ):
            guest=copy.deepcopy(baseline)
            node=guest
            for field in path[:-1]:node=node[field]
            node[path[-1]]=bad
            with self.subTest(path=path),self.assertRaises(Refused):
                correlate(*fixture(),native_source=native_fixture(),native_guest=guest)
        with self.assertRaisesRegex(Refused,"NATIVE_GUEST_NEEDS_EXACT_SOURCE_PLAN"):
            correlate(*fixture(),native_guest=baseline)

    def test_same_real_artifact_across_generic_native_source_and_player_oracle(self):
        result=correlate(*fixture(),native_source=native_fixture())
        self.assertTrue(result["native_app_artifact_source_intent_bound"])
        self.assertEqual(result["native_app_expected"],"rdte-t6-minecraft-vanilla-263")
        self.assertEqual(result["native_app_source_plan_intent_sha256"],"e"*64)
        self.assertTrue(result["offline_client_action_independently_verified"])
        self.assertFalse(result["native_guest_with_artifact_qualified"])
        self.assertFalse(result["native_artifact_activation_performed"])
        self.assertFalse(result["collage_managed_deployment"])

    def test_native_source_anti_promotion_identity_and_three_audience_negatives(self):
        for key,value in (
            ("candidate",dict(native_fixture()["candidate"],sha256="a"*64)),
            ("expected_native_app","rdte-t6-minecraft-paper"),
            ("expected_truenas_version","25.04.1"),
            ("source_native_target_profile","unbounded"),
            ("common_intent_sha256","f"*64),
            ("real_provider_readback",True),
            ("world_activated",True),
            ("mutation_authorized",True),
            ("native_guest_with_this_artifact_qualified",True),
        ):
            candidate=native_fixture()
            candidate[key]=value
            with self.subTest(key=key),self.assertRaises(Refused):
                correlate(*fixture(),native_source=candidate)
        candidate=native_fixture()
        candidate["audience_receipts"].pop("agent")
        with self.assertRaises(Refused):
            correlate(*fixture(),native_source=candidate)

    def test_positive_still_makes_no_managed_deployment_claim(self):
        result = correlate(*fixture())
        self.assertTrue(result["offline_client_action_independently_verified"])
        self.assertEqual(result["audience_kinds"], ["agent","automation","human"])
        self.assertFalse(result["collage_managed_deployment"])
        self.assertFalse(result["principal_authorization_verified"])

    def test_wrong_producer_world_version_archive_and_hash_refused(self):
        for i,k,v in (
            (0,"sha256","0"*64),
            (1,"candidate",dict(fixture()[1]["candidate"],world_id="wrong")),
            (2,"source_artifact_sha256","0"*64),
            (2,"minecraft_version","26.4"),
            (2,"source_archive_size",50),
            (2,"protocol",776),
        ):
            triplet=copy.deepcopy(fixture())
            triplet[i][k]=v
            with self.subTest(field=k),self.assertRaises(Refused):
                correlate(*triplet)

    def test_missing_actor_and_forbidden_deployment_authority(self):
        d=copy.deepcopy(fixture())
        d[1]["audience_receipts"].pop("agent")
        with self.assertRaises(Refused):
            correlate(*d)
        d=copy.deepcopy(fixture())
        d[1]["mutation_authorized"]=True
        with self.assertRaises(Refused):
            correlate(*d)

    def test_bot_login_join_and_placement_cannot_be_claimed(self):
        for player_kind in ("candidate_player","postrollback_player"):
            for key,value in (
                ("server_join_independently_observed",False),
                ("client_saw_redstone_after",False),
                ("protocol",774),
                ("action","claimed_player_action"),
                ("offline_mode",False),
            ):
                d=copy.deepcopy(fixture())
                d[2][player_kind][key]=value
                with self.subTest(kind=player_kind,field=key),self.assertRaises(Refused):
                    correlate(*d)

    def test_rollback_and_unauthorized_promotion_refused(self):
        for key,value in (
            ("same_player_action_without_datapack_no_effect",False),
            ("baseline_world_sha256","3"*64),
            ("stock_mojang_client_qualified",True),
            ("authenticated_account_qualified",True),
            ("collage_deployed",True),
            ("truenas_deployed",True),
            ("operational_selection",True),
            ("physical_truenas_apply","APPLY"),
        ):
            d=copy.deepcopy(fixture())
            d[2][key]=value
            with self.subTest(key=key),self.assertRaises(Refused):
                correlate(*d)


if __name__ == "__main__":
    unittest.main()
