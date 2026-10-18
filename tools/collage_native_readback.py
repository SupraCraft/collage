#!/usr/bin/env python3
"""Read-only COLLAGE source-plan -> genuine native TrueNAS App readback join.

Invokes the already-qualified TLS-verified Go app.query probe directly.
This process DOES NOT implement lifecycle mutation, authenticate the invoking
human/agent, or establish that an opaque world artifact is valid or activated.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

if __package__:
    from .collage_deploy_plan import Refused, plan, read_json
else:
    from collage_deploy_plan import Refused, plan, read_json

SCHEMA = "collage.native-readback/1"
MAX_PROBE_OUTPUT = 32768
# Trusted caller selects an exact source-qualified native App catalog version.
# The historical default preserves the accepted G2 1.15.30 observer; G4
# 1.15.31 requires an explicit bounded profile, never a floating latest.
NATIVE_VANILLA263_PROFILES = {
    "vanilla263-11530": "1.15.30",
    "vanilla263-11531": "1.15.31",
}


def compare_native(request: dict, observed: object,
                   trusted_realm: str, manager_id: str, fleet_id: str, *,
                   native_catalog_profile: str = "vanilla263-11530") -> dict:
    """Pure comparison, NOT independent evidence that the probe was executed."""
    target = request["target"]
    artifact = request["artifact"]
    if target.get("service_id") is None:
        raise Refused("SERVICE_ID_REQUIRED_FOR_PROVIDER_READBACK")
    if request["realm_id"] != trusted_realm:
        raise Refused("REALM_NOT_IN_ADMITTED_SITE_BOUNDARY")
    expected = {
        "SUPRACRAFT_COLLAGE_MANAGED": "true",
        "SUPRACRAFT_COLLAGE_SCHEMA": "1",
        "SUPRACRAFT_COLLAGE_MANAGER_ID": manager_id,
        "SUPRACRAFT_COLLAGE_FLEET_ID": fleet_id,
        "SUPRACRAFT_COLLAGE_SERVICE_ID": target["service_id"],
        "SUPRACRAFT_COLLAGE_WORLD_ID": target["world_id"],
    }
    if type(observed) is not dict:
        raise Refused("INVALID_PROVIDER_REPORT")
    required = {"schema_version", "result", "truenas_version", "app_name",
                "app_state", "custom_app", "app_version", "config_present",
                "container_count", "collage_metadata", "metadata_required"}
    if not required <= observed.keys():
        raise Refused("INVALID_PROVIDER_REPORT")
    if (observed["result"] != "PASS" or type(observed["schema_version"]) is not int
            or observed["schema_version"] != 1
            or observed["metadata_required"] is not True
            or observed["config_present"] is not True
            or observed["custom_app"] is not False
            or observed["app_name"] != target["deployment_id"]):
        raise Refused("NATIVE_APP_READBACK_INVALID")
    if observed["app_state"] != "RUNNING":
        raise Refused("NATIVE_APP_NOT_RUNNING")
    if observed["collage_metadata"] != expected:
        raise Refused("PROVIDER_OWNERSHIP_MISMATCH")
    if (artifact["world_id"] != target["world_id"]
            or artifact["minecraft_version"] != target["minecraft_version"]):
        raise Refused("ARTIFACT_TARGET_DRIFT")
    native_vanilla263 = target["deployment_id"] == "rdte-t6-minecraft-vanilla-263"
    if native_vanilla263:
        if native_catalog_profile not in NATIVE_VANILLA263_PROFILES:
            raise Refused("NATIVE_VANILLA263_CATALOG_PROFILE_REFUSED")
        # The exact pinned Go truenas-go v0.5.0 WS client exposes
        # ws.Version().Raw == system.version, e.g. TrueNAS-25.04.2.6,
        # NOT the unprefixed numeric target version. Check exact raw bytes
        # before normalizing the result for COLLAGE's source target schema.
        # Do not accept suffixes, alternate products, or fuzzy version ranges.
        # This concrete native T6 target was actually qualified separately
        # (Agent Dispatch public run 38489327594, 25.04.2.6/1.15.30).
        # Source identity and native App ownership may not silently drift,
        # even when six environment markers are otherwise self-consistent.
        if (target["world_id"] != "lantern-rdte"
                or target["service_id"] !=
                "11111111-1111-4111-8111-111111111111"
                or target["minecraft_version"] != "26.3"
                or artifact.get("kind") != "datapack"):
            raise Refused("NATIVE_VANILLA263_TARGET_PROFILE_DRIFT")
        if (observed["truenas_version"] != "TrueNAS-25.04.2.6"
                or observed["app_version"] != NATIVE_VANILLA263_PROFILES[native_catalog_profile]
                or type(observed["container_count"]) is not int
                or observed["container_count"] < 1):
            raise Refused("NATIVE_VANILLA263_GUEST_PROFILE_DRIFT")
    elif native_catalog_profile != "vanilla263-11530":
        # A vanilla-only 1.15.31 profile must never loosen legacy Paper readback.
        raise Refused("NATIVE_CATALOG_PROFILE_WRONG_PRODUCT")
    return {
        "native_app": target["deployment_id"],
        "native_app_version": observed["app_version"],
        "truenas_version": "25.04.2.6" if native_vanilla263 else observed["truenas_version"],
        "world_id": target["world_id"],
        "service_id": target["service_id"],
        "ownership_fields_matched": len(expected),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--trusted-realm-id", required=True)
    parser.add_argument("--manager-id", required=True)
    parser.add_argument("--fleet-id", required=True)
    parser.add_argument("--native-catalog-profile",
                        choices=sorted(NATIVE_VANILLA263_PROFILES),
                        default="vanilla263-11530")
    args = parser.parse_args()
    try:
        request = read_json(args.request)
        source = plan(request, args.artifact_root)
        if "service_id" not in request["target"]:
            raise Refused("SERVICE_ID_REQUIRED_FOR_PROVIDER_READBACK")
        if request["realm_id"] != args.trusted_realm_id:
            raise Refused("REALM_NOT_IN_ADMITTED_SITE_BOUNDARY")
        if not os.getenv("TRUENAS_API_KEY"):
            raise Refused("MISSING_BOUNDED_API_AUTHORITY")
        cmd = ["go", "run", ".", "-host", args.host, "-username", args.username,
               "-app", request["target"]["deployment_id"],
               "-require-collage-metadata", "-timeout", "40s"]
        # No API key on argv. Go probe itself enforces TLS verification and has
        # no TrueNAS mutation API surface. Its stderr/raw config are never emitted.
        probe_dir = pathlib.Path(__file__).resolve().parent / "truenas-readonly-probe"
        cp = subprocess.run(cmd, cwd=probe_dir, capture_output=True, text=True,
                            timeout=180, check=False)
        if cp.returncode != 0:
            raise Refused("NATIVE_READONLY_PROBE_FAILED")
        if len(cp.stdout.encode("utf-8")) > MAX_PROBE_OUTPUT:
            raise Refused("PROBE_OUTPUT_OVERSIZED")
        try:
            observed = json.loads(cp.stdout)
        except ValueError:
            raise Refused("PROBE_OUTPUT_NOT_JSON") from None
        match = compare_native(request, observed, args.trusted_realm_id,
                               args.manager_id, args.fleet_id,
                               native_catalog_profile=args.native_catalog_profile)
        result = {
            "schema": SCHEMA,
            "classification": "PROVIDER_READBACK_MATCH",
            "source_plan_sha256": source["intent_sha256"],
            **match,
            "provider_observed": True,
            "independent_probe": "collage/truenas-readonly-probe (TLS verified)",
            "declared_actor_authenticated": False,
            "provider_credential_grants_actor_authority": False,
            "realm_cryptographic_binding_proven": False,
            "minecraft_version_or_protocol_observed": False,
            "world_artifact_format_verified": False,
            "world_activated": False,
            "cloudnet_adoption_executed": False,
            "mutation_authorized": False,
        }
        status = 0
    except Refused as exc:
        result = {"schema": SCHEMA, "classification": "REFUSED",
                  "reason": exc.code, "mutation_authorized": False,
                  "provider_observed": False}
        status = 2
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        result = {"schema": SCHEMA, "classification": "INCONCLUSIVE",
                  "reason": "PROBE_EXECUTION_UNAVAILABLE",
                  "mutation_authorized": False, "provider_observed": False}
        status = 3
    print(json.dumps(result, sort_keys=True, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
