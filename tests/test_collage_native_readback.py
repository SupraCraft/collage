"""Read-only provider joining policy tests.

These use synthetic sanitized provider *documents* only to test fail-closed
comparison; they do NOT claim a live TrueNAS App, credential, world or actor.
The live proof must invoke the Go probe in a real disposable TrueNAS guest.
"""
import copy
import unittest

from tools.collage_deploy_plan import Refused
from tools.collage_native_readback import compare_native

REALM = "d68a14b9-2a1c-4e83-a452-e3b569cdf93e"
SERVICE = "11111111-1111-4111-8111-111111111111"
MANAGER = "manager-rdte"
FLEET = "rdte"


def source():
    return {
        "realm_id": REALM,
        "target": {
            "deployment_id": "rdte-t6-minecraft-paper",
            "service_id": SERVICE,
            "world_id": "world-rdte-001",
            "minecraft_version": "1.21.11",
        },
        "artifact": {"world_id": "world-rdte-001", "minecraft_version": "1.21.11"},
    }


def sanitized_readback():
    return {
        "schema_version": 1,
        "result": "PASS",
        "truenas_version": "25.04.1",
        "app_name": "rdte-t6-minecraft-paper",
        "app_state": "RUNNING",
        "custom_app": False,
        "app_version": "1.15.29",
        "config_present": True,
        "container_count": 1,
        "metadata_required": True,
        "collage_metadata": {
            "SUPRACRAFT_COLLAGE_MANAGED": "true",
            "SUPRACRAFT_COLLAGE_SCHEMA": "1",
            "SUPRACRAFT_COLLAGE_MANAGER_ID": MANAGER,
            "SUPRACRAFT_COLLAGE_FLEET_ID": FLEET,
            "SUPRACRAFT_COLLAGE_SERVICE_ID": SERVICE,
            "SUPRACRAFT_COLLAGE_WORLD_ID": "world-rdte-001",
        },
    }


class ComparisonTests(unittest.TestCase):
    def reject(self, req, obs, reason, trusted_realm=REALM):
        with self.assertRaises(Refused) as caught:
            compare_native(req, obs, trusted_realm, MANAGER, FLEET)
        self.assertEqual(caught.exception.code, reason)

    def test_exact_native_ownership_match(self):
        matched = compare_native(source(), sanitized_readback(), REALM, MANAGER, FLEET)
        self.assertEqual(matched["ownership_fields_matched"], 6)
        self.assertEqual(matched["service_id"], SERVICE)
        self.assertEqual(matched["world_id"], "world-rdte-001")
        self.assertNotIn("player_authenticated", matched)
        self.assertNotIn("world_activated", matched)

    def test_missing_stable_uuid_refuses(self):
        req = source()
        del req["target"]["service_id"]
        self.reject(req, sanitized_readback(), "SERVICE_ID_REQUIRED_FOR_PROVIDER_READBACK")

    def test_cross_realm_refuses_before_readback(self):
        self.reject(source(), sanitized_readback(),
                    "REALM_NOT_IN_ADMITTED_SITE_BOUNDARY",
                    "b482ec5f-8c2a-49a1-9a9e-a49f32de323b")

    def test_wrong_app_and_non_native_refuse(self):
        obs = sanitized_readback()
        obs["app_name"] = "different-app"
        self.reject(source(), obs, "NATIVE_APP_READBACK_INVALID")
        obs = sanitized_readback()
        obs["custom_app"] = True
        self.reject(source(), obs, "NATIVE_APP_READBACK_INVALID")

    def test_stopped_app_refuses_running_claim(self):
        obs = sanitized_readback()
        obs["app_state"] = "STOPPED"
        self.reject(source(), obs, "NATIVE_APP_NOT_RUNNING")

    def test_ownership_field_drift_refuses(self):
        for key in sanitized_readback()["collage_metadata"]:
            obs = sanitized_readback()
            obs["collage_metadata"][key] = "foreign-value"
            with self.subTest(key=key):
                self.reject(source(), obs, "PROVIDER_OWNERSHIP_MISMATCH")

    def test_incomplete_or_spoofed_readback_refuses(self):
        self.reject(source(), {}, "INVALID_PROVIDER_REPORT")
        obs = sanitized_readback()
        obs["schema_version"] = True
        self.reject(source(), obs, "NATIVE_APP_READBACK_INVALID")
        obs = sanitized_readback()
        obs["result"] = "FAIL"
        self.reject(source(), obs, "NATIVE_APP_READBACK_INVALID")
        obs = sanitized_readback()
        obs["metadata_required"] = False
        self.reject(source(), obs, "NATIVE_APP_READBACK_INVALID")

    def test_artifact_version_and_world_drift_refuse(self):
        req = source()
        req["artifact"]["world_id"] = "different-world"
        self.reject(req, sanitized_readback(), "ARTIFACT_TARGET_DRIFT")
        req = source()
        req["artifact"]["minecraft_version"] = "26.3"
        self.reject(req, sanitized_readback(), "ARTIFACT_TARGET_DRIFT")


if __name__ == "__main__":
    unittest.main()
