#!/usr/bin/env python3
"""Bind one REAL pinned vanilla26.3 datapack export to existing COLLAGE source plans.

One immutable artifact, three caller presentations, one equal-intent hash.
No extra schema/manager/scheduler, native guest, permission or APPLY.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

if __package__:
    from .collage_deploy_plan import Refused, plan, read_json
else:
    from collage_deploy_plan import Refused, plan, read_json

MANIFEST_SCHEMA = "supracraft-vanilla-datapack-candidate/1"
SOURCE_REF = "SupraCraft/mc-server-images@7f888b5829f4e5576d5ce512d86327348c43f01e"
WORLD = "lantern-rdte"
RELEASE = "lantern-core-restore-26-3"
SERVICE = "11111111-1111-4111-8111-111111111111"
REALM = "d68a14b9-2a1c-4e83-a452-e3b569cdf93e"
APP = "rdte-t6-minecraft-vanilla-263"
MEMBERS = {
    "pack.mcmeta",
    "data/minecraft/tags/function/tick.json",
    "data/supracraft_core_restore/function/tick.mcfunction",
}
SCHEMA = "collage.real-vanilla263-artifact-source-parity/1"


def refuse(ok: bool, code: str) -> None:
    if not ok:
        raise Refused(code)


def check_export(m: dict) -> None:
    """Verify exact producer intent and bounded digest; not ZIP format or runtime."""
    refuse(type(m) is dict and
           m.get("schema") == MANIFEST_SCHEMA and
           m.get("classification") == "SOURCE_ARTIFACT_EXPORTED" and
           m.get("kind") == "datapack" and
           m.get("backend") == "vanilla" and
           m.get("producer") == SOURCE_REF and
           m.get("minecraft_version") == "26.3" and
           m.get("world_id") == WORLD and
           m.get("release_id") == RELEASE and
           m.get("pack_format") == [121, 0],
           "EXACT_ARTIFACT_PRODUCER_OR_VERSION_DRIFT")
    refuse(m.get("world_save_included") is False and
           m.get("collage_deployed") is False and
           m.get("full_two_rivers_world_qualified") is False and
           m.get("minecraft_runtime_verified_by_this_export") is False,
           "ARTIFACT_SOURCE_SCOPE_ESCALATED")
    name = m.get("relative_path")
    refuse(name == "lantern-restoration-26.3.zip", "ARTIFACT_PATH_DRIFT")
    refuse(isinstance(m.get("sha256"), str) and
           re.fullmatch("[0-9a-f]{64}", m["sha256"]) is not None and
           type(m.get("archive_size")) is int and
           0 < m["archive_size"] <= 1024 * 1024,
           "ARTIFACT_DIGEST_OR_SIZE_INVALID")
    members = m.get("members")
    refuse(type(members) is list and len(members) == 3 and
           all(type(row) is dict and
               type(row.get("path")) is str and row.get("path") in MEMBERS and
               isinstance(row.get("sha256"), str) and
               re.fullmatch("[0-9a-f]{64}", row["sha256"]) and
               type(row.get("bytes")) is int and 0 < row["bytes"] <= 1024 * 1024
               for row in members) and
           {row["path"] for row in members} == MEMBERS,
           "ARTIFACT_MEMBER_DECLARATION_DRIFT")


def request_for(m: dict, kind: str, *, now: dt.datetime) -> dict:
    refuse(kind in {"human", "automation", "agent"}, "CALLER_KIND_UNSUPPORTED")
    principal = {"kind": kind, "issuer": "urn:supracraft:rdte:source",
                 "subject": "collage-source-parity-" + kind}
    if kind == "agent":
        principal["delegation"] = {
            "sponsor": "rdte-source-controller",
            "expires_at": (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "claimed_scopes": ["deploy:plan"],
        }
    return {
        "schema": "collage.deployment-request/1",
        "request_id": "lantern-core-restore-source-" + kind,
        "realm_id": REALM, "environment": "rdte", "ttl_seconds": 3600,
        "principal": principal,
        "authorization": {"audience_realm_id": REALM, "claimed_scopes": ["deploy:plan"]},
        "target": {"provider": "truenas", "deployment_id": APP,
                   "service_id": SERVICE, "world_id": WORLD,
                   "minecraft_version": "26.3", "backend": "vanilla",
                   "purpose": "generic"},
        "artifact": {"kind": "datapack", "relative_path": m["relative_path"],
                     "sha256": m["sha256"], "producer": m["producer"],
                     "release_id": RELEASE, "world_id": WORLD,
                     "minecraft_version": "26.3"},
        "action": "plan", "expected_current_release": None,
    }


def qualify(m: dict, artifact_root: pathlib.Path, *,
            now: dt.datetime | None = None) -> dict:
    check_export(m)
    moment = now or dt.datetime.now(dt.timezone.utc)
    receipts = [plan(request_for(m, kind, now=moment), artifact_root, now=moment)
                for kind in ("human", "automation", "agent")]
    refuse(all(x["classification"] == "SOURCE_VALIDATED" and
               x["provider_observed"] is False and
               x["principal_authenticated"] is False and
               x["authorization_verified"] is False and
               x["artifact_format_verified"] is False and
               x["world_activated"] is False and
               x["mutation_authorized"] is False and
               x["artifact_size"] == m["archive_size"] and
               x["artifact_sha256_verified"] == m["sha256"]
               for x in receipts), "SOURCE_PLAN_CONTRACT_NOT_MET")
    intents = {x["intent_sha256"] for x in receipts}
    refuse(len(intents) == 1 and len({x["request_sha256"] for x in receipts}) == 3,
           "CROSS_AUDIENCE_INTENT_DRIFT")
    return {
        "schema": SCHEMA,
        "classification": "REAL_DATAPACK_SOURCE_PLAN_PARITY",
        "source_producer": SOURCE_REF,
        "artifact_sha256": m["sha256"],
        "artifact_bytes": m["archive_size"],
        "artifact_kind": "datapack",
        "minecraft_version": "26.3",
        "world_id": WORLD,
        "native_guest_target": "TrueNAS-25.04.2.6",
        "native_app_candidate": APP,
        "intents_equal": True,
        "intent_sha256": receipts[0]["intent_sha256"],
        "caller_kinds": [x["declared_principal_kind"] for x in receipts],
        "provider_observed": False,
        "actor_authenticated": False,
        "permission_to_apply": False,
        "datapack_contents_independently_verified": False,
        "native_guest_with_this_artifact_qualified": False,
        "world_activated": False,
        "two_rivers_complete": False,
        "physical_truenas_apply": "HOLD",
        "next_gate": "REAL_NATIVE_GUEST_PROVIDER_READBACK_THEN_ADMITTED_ARTIFACT_ACTIVATION",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True, type=pathlib.Path)
    p.add_argument("--artifact-root", required=True, type=pathlib.Path)
    a = p.parse_args()
    try:
        result = qualify(read_json(a.manifest), a.artifact_root)
        code = 0
    except Refused as exc:
        result = {"schema": SCHEMA, "classification": "REFUSED",
                  "reason": exc.code, "permission_to_apply": False,
                  "provider_observed": False, "physical_truenas_apply": "HOLD"}
        code = 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
