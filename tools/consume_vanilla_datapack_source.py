#!/usr/bin/env python3
"""Consume a real, versioned vanilla datapack candidate as COLLAGE source plans.

Only inspects local immutable artifact bytes and emits SOURCE_VALIDATED plans.
Does NOT unpack to any world, authenticate principals, contact TrueNAS,
authorize deployment, activate a release, or assert Minecraft gameplay.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import zipfile

if __package__:
    from .collage_deploy_plan import Refused, plan, read_json
else:
    from collage_deploy_plan import Refused, plan, read_json

MANIFEST_SCHEMA = "supracraft-vanilla-datapack-candidate/1"
REPORT_SCHEMA = "collage.artifact-consumer-source-parity/1"
ALLOWED = {
    "pack.mcmeta",
    "data/minecraft/tags/function/tick.json",
    "data/supracraft_core_restore/function/tick.mcfunction",
}
SHA = re.compile(r"^[0-9a-f]{64}$")
PRODUCER = re.compile(r"^SupraCraft/mc-server-images@[0-9a-f]{40}$")
REALM = "d68a14b9-2a1c-4e83-a452-e3b569cdf93e"
SERVICE = "11111111-1111-4111-8111-111111111111"
NATIVE_VANILLA263_PRODUCER = "SupraCraft/mc-server-images@7f888b5829f4e5576d5ce512d86327348c43f01e"
NATIVE_VANILLA263_APP = "rdte-t6-minecraft-vanilla-263"
NATIVE_VANILLA263_WORLD = "lantern-rdte"
NATIVE_VANILLA263_RELEASE = "lantern-core-restore-26-3"
NATIVE_VANILLA263_VERSION = "25.04.2.6"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Refused(reason)


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_candidate(manifest: dict, zip_path: pathlib.Path) -> dict:
    require(isinstance(manifest, dict) and manifest.get("schema") == MANIFEST_SCHEMA,
            "CANDIDATE_MANIFEST_SCHEMA")
    require(manifest.get("classification") == "SOURCE_ARTIFACT_EXPORTED",
            "CANDIDATE_UNQUALIFIED")
    require(manifest.get("kind") == "datapack"
            and manifest.get("minecraft_version") == "26.3"
            and manifest.get("backend") == "vanilla"
            and manifest.get("pack_format") == [121, 0]
            and manifest.get("world_save_included") is False
            and manifest.get("collage_deployed") is False, "CANDIDATE_CONTRACT_DRIFT")
    require(isinstance(manifest.get("producer"), str)
            and PRODUCER.fullmatch(manifest["producer"]) is not None,
            "CANDIDATE_PRODUCER_DRIFT")
    require(isinstance(manifest.get("sha256"), str)
            and SHA.fullmatch(manifest["sha256"]) is not None,
            "CANDIDATE_DIGEST_INVALID")
    require(manifest.get("relative_path") == zip_path.name,
            "CANDIDATE_ARTIFACT_NAME_MISMATCH")
    require(type(manifest.get("archive_size")) is int
            and 0 < manifest["archive_size"] <= 1024 * 1024,
            "CANDIDATE_ARCHIVE_SIZE")
    require(type(manifest.get("members")) is list
            and len(manifest["members"]) == len(ALLOWED),
            "CANDIDATE_MEMBER_MANIFEST")
    try:
        actual_size = zip_path.stat().st_size
        require(actual_size == manifest["archive_size"],
                "CANDIDATE_ARCHIVE_SIZE")
        content = zip_path.read_bytes()
        require(hash_bytes(content) == manifest["sha256"],
                "CANDIDATE_DIGEST_MISMATCH")
        with zipfile.ZipFile(zip_path, "r") as archive:
            records = archive.infolist()
            require(len(records) == len(ALLOWED)
                    and {record.filename for record in records} == ALLOWED,
                    "CANDIDATE_MEMBERS_DRIFT")
            require(all(not x.is_dir() and not (x.flag_bits & 1)
                        and (x.external_attr >> 16) & 0o170000 == 0o100000
                        and 0 < x.file_size <= 128 * 1024
                        for x in records), "CANDIDATE_ARCHIVE_UNSAFE")
            verified = {}
            for member in records:
                with archive.open(member) as stream:
                    verified[member.filename] = (
                        hash_bytes(stream.read(128 * 1024 + 1)), member.file_size)
            claimed = {}
            for row in manifest["members"]:
                require(type(row) is dict and set(row) == {"path", "sha256", "bytes"}
                        and row["path"] not in claimed
                        and row["path"] in ALLOWED
                        and type(row["bytes"]) is int
                        and isinstance(row["sha256"], str), "CANDIDATE_MEMBER_MANIFEST")
                claimed[row["path"]] = (row["sha256"], row["bytes"])
            require(claimed == verified, "CANDIDATE_MEMBER_DIGEST_MISMATCH")
            with archive.open("pack.mcmeta") as stream:
                metadata = json.load(stream)
            require(metadata.get("pack", {}).get("min_format") == [121, 0]
                    and metadata.get("pack", {}).get("max_format") == [121, 0],
                    "CANDIDATE_PACK_METADATA_DRIFT")
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, Refused):
            raise
        raise Refused("CANDIDATE_UNREADABLE") from None
    return {
        "producer": manifest["producer"], "sha256": manifest["sha256"],
        "size": actual_size, "kind": manifest["kind"],
        "world_id": manifest["world_id"], "release_id": manifest["release_id"],
        "minecraft_version": manifest["minecraft_version"],
        "member_count": len(verified),
    }


def audience_requests(candidate: dict, relative_path: str, *,
                      native_vanilla263: bool = False) -> list[dict]:
    # An actual native guest has now been qualified, but these source plans
    # remain read-only and do not inherit its live App or world proof.
    if native_vanilla263:
        require(candidate["producer"] == NATIVE_VANILLA263_PRODUCER
                and candidate["world_id"] == NATIVE_VANILLA263_WORLD
                and candidate["release_id"] == NATIVE_VANILLA263_RELEASE
                and candidate["minecraft_version"] == "26.3"
                and candidate["kind"] == "datapack",
                "EXACT_NATIVE_SOURCE_PROFILE_MISMATCH")
    deployment = (NATIVE_VANILLA263_APP if native_vanilla263
                  else "lantern-rdte-candidate")
    base = {
        "schema": "collage.deployment-request/1",
        "realm_id": REALM, "environment": "rdte", "action": "plan",
        "ttl_seconds": 3600, "expected_current_release": None,
        "authorization": {"audience_realm_id": REALM, "claimed_scopes": ["deploy:plan"]},
        "target": {"provider": "truenas", "deployment_id": deployment,
                   "service_id": SERVICE, "world_id": candidate["world_id"],
                   "minecraft_version": "26.3", "backend": "vanilla",
                   "purpose": "two-rivers"},
        "artifact": {"kind": "datapack", "relative_path": relative_path,
                     "sha256": candidate["sha256"],
                     "producer": candidate["producer"],
                     "release_id": candidate["release_id"],
                     "world_id": candidate["world_id"],
                     "minecraft_version": "26.3"},
    }
    import copy
    requests = []
    for kind in ("human", "automation", "agent"):
        req = copy.deepcopy(base)
        req["request_id"] = "lantern-artifact-" + kind
        req["principal"] = {"kind": kind, "issuer": "source-contract-demo",
                            "subject": "sample-" + kind}
        if kind == "agent":
            # Fixed expiry for a reproducible source example, not live delegated authority.
            req["principal"]["delegation"] = {
                "sponsor": "source-contract-demo",
                "expires_at": "2030-01-01T00:00:00Z",
                "claimed_scopes": ["deploy:plan"],
            }
        requests.append(req)
    return requests


def consume(manifest: dict, zip_path: pathlib.Path, artifact_root: pathlib.Path, *,
            native_vanilla263: bool = False) -> dict:
    candidate = verify_candidate(manifest, zip_path)
    root = artifact_root.resolve()
    absolute = zip_path.resolve()
    require(absolute.is_relative_to(root), "CANDIDATE_OUTSIDE_ARTIFACT_ROOT")
    relative = absolute.relative_to(root).as_posix()
    requests = audience_requests(candidate, relative,
                                 native_vanilla263=native_vanilla263)
    receipts = [plan(r, root) for r in requests]
    require(all(r["classification"] == "SOURCE_VALIDATED"
                and r["mutation_authorized"] is False
                and r["provider_observed"] is False
                and r["artifact_sha256_verified"] == candidate["sha256"]
                for r in receipts), "CANDIDATE_SOURCE_PLAN_NOT_QUALIFIED")
    require(len({r["intent_sha256"] for r in receipts}) == 1,
            "AUDIENCE_INTENT_PARITY_FAILURE")
    return {
        "schema": REPORT_SCHEMA,
        "classification": "SOURCE_ARTIFACT_AND_INTENT_PARITY_VALIDATED",
        "candidate": candidate,
        "common_intent_sha256": receipts[0]["intent_sha256"],
        "audience_receipts": {req["principal"]["kind"]: {
            "request_id": req["request_id"],
            "request_sha256": receipt["request_sha256"],
            "source_classification": receipt["classification"],
        } for req, receipt in zip(requests, receipts)},
        "principal_authenticated": False,
        "real_provider_readback": False,
        "world_activated": False,
        "minecraft_runtime_qualified_by_this_step": False,
        "mutation_authorized": False,
        "source_native_target_profile": "vanilla263-250426" if native_vanilla263 else None,
        "expected_native_app": NATIVE_VANILLA263_APP if native_vanilla263 else None,
        "expected_truenas_version": NATIVE_VANILLA263_VERSION if native_vanilla263 else None,
        "native_guest_with_this_artifact_qualified": False,
        "next_gate": ("REAL_TLS_VERIFIED_NATIVE_APP_PROVIDER_READBACK"
                      if native_vanilla263 else
                      "DISPOSABLE_VANILLA_WORLD_STAGE_AND_INDEPENDENT_GAMEPLAY_ORACLE"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=pathlib.Path, required=True)
    ap.add_argument("--artifact", type=pathlib.Path, required=True)
    ap.add_argument("--artifact-root", type=pathlib.Path, required=True)
    ap.add_argument("--native-target-profile", choices=("vanilla263-250426",))
    args = ap.parse_args()
    try:
        print(json.dumps(consume(read_json(args.manifest),
                                 args.artifact, args.artifact_root,
                                 native_vanilla263=(args.native_target_profile == "vanilla263-250426")),
                         sort_keys=True, indent=2))
        return 0
    except Refused as exc:
        print(json.dumps({"schema": REPORT_SCHEMA, "classification": "REFUSED",
                          "reason": exc.code, "mutation_authorized": False},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
