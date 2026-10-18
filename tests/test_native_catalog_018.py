"""OP4K-018 source-only red/blue tests for native readback catalog pin.

Synthetic sanitized provider documents are NOT proof of a live TrueNAS guest.
No credentials, mutating provider operations, or physical deployment.
"""
import copy
import unittest

from tools.collage_deploy_plan import Refused
from tools.collage_native_readback import compare_native
from tests.test_collage_native_readback import (
    REALM, MANAGER, FLEET, source, sanitized_readback,
)


def vanilla():
    req = source()
    req["target"].update(deployment_id="rdte-t6-minecraft-vanilla-263",
                         world_id="lantern-rdte", minecraft_version="26.3")
    req["artifact"].update(world_id="lantern-rdte", minecraft_version="26.3",
                           kind="datapack")
    observed = sanitized_readback()
    observed.update(truenas_version="TrueNAS-25.04.2.6",
                    app_name="rdte-t6-minecraft-vanilla-263")
    observed["collage_metadata"]["SUPRACRAFT_COLLAGE_WORLD_ID"] = "lantern-rdte"
    return req, observed


class OP4KReadbackCatalogTests(unittest.TestCase):
    def compare(self, request, observed, profile="vanilla263-11530"):
        return compare_native(request, observed, REALM, MANAGER, FLEET,
                              native_catalog_profile=profile)

    def reject(self, req, obs, profile, reason):
        with self.assertRaises(Refused) as result:
            self.compare(req, obs, profile)
        self.assertEqual(result.exception.code, reason)

    def test_original_11530_still_accepted_only_under_original_pin(self):
        request, observed = vanilla()
        observed["app_version"] = "1.15.30"
        self.assertEqual(self.compare(request, observed)["native_app_version"], "1.15.30")
        self.reject(request, observed, "vanilla263-11531",
                    "NATIVE_VANILLA263_GUEST_PROFILE_DRIFT")

    def test_current_11531_requires_explicit_pin(self):
        request, observed = vanilla()
        observed["app_version"] = "1.15.31"
        self.reject(request, observed, "vanilla263-11530",
                    "NATIVE_VANILLA263_GUEST_PROFILE_DRIFT")
        match = self.compare(request, observed, "vanilla263-11531")
        self.assertEqual(match["native_app_version"], "1.15.31")
        self.assertEqual(match["ownership_fields_matched"], 6)
        self.assertEqual(match["truenas_version"], "25.04.2.6")

    def test_no_latest_or_foreign_catalog_pin(self):
        request, observed = vanilla()
        observed["app_version"] = "1.15.31"
        for profile in ("latest", "1.15.31", "vanilla263-11532", "", None, True):
            with self.subTest(profile=profile):
                self.reject(request, observed, profile,
                            "NATIVE_VANILLA263_CATALOG_PROFILE_REFUSED")
        for version in ("1.15.30", "1.15.32", "1.15.31-rc1", "latest"):
            with self.subTest(version=version):
                altered = copy.deepcopy(observed)
                altered["app_version"] = version
                self.reject(request, altered, "vanilla263-11531",
                            "NATIVE_VANILLA263_GUEST_PROFILE_DRIFT")

    def test_wrong_product_cannot_consume_vanilla_upgrade_profile(self):
        self.reject(source(), sanitized_readback(), "vanilla263-11531",
                    "NATIVE_CATALOG_PROFILE_WRONG_PRODUCT")
        match = self.compare(source(), sanitized_readback())
        self.assertEqual(match["native_app"], "rdte-t6-minecraft-paper")

    def test_11531_does_not_bypass_world_service_owner_or_host(self):
        request, observed = vanilla()
        observed["app_version"] = "1.15.31"
        for field, bad, reason in (
            ("app_name", "foreign", "NATIVE_APP_READBACK_INVALID"),
            ("truenas_version", "TrueNAS-25.04.2.7",
             "NATIVE_VANILLA263_GUEST_PROFILE_DRIFT"),
            ("app_state", "STOPPED", "NATIVE_APP_NOT_RUNNING"),
            ("metadata_required", False, "NATIVE_APP_READBACK_INVALID"),
        ):
            altered = copy.deepcopy(observed)
            altered[field] = bad
            with self.subTest(field=field):
                self.reject(request, altered, "vanilla263-11531", reason)
        altered = copy.deepcopy(observed)
        altered["collage_metadata"]["SUPRACRAFT_COLLAGE_WORLD_ID"] = "foreign"
        self.reject(request, altered, "vanilla263-11531",
                    "PROVIDER_OWNERSHIP_MISMATCH")


if __name__ == "__main__":
    unittest.main()
