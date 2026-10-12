#!/usr/bin/env python3
"""COLLAGE deployment intent v1: dependency-free, read-only source planning.

This is deliberately NOT TrueNAS discovery, authentication, world unpacking,
activation, or an APPLY API. Those need separate qualified live authorities.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import uuid

SCHEMA = "collage.deployment-request/1"
RECEIPT = "collage.deployment-plan/1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
PRINCIPAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:/._@+-]{0,255}$")
PRODUCER = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
ACTIONS = {"plan"}
KINDS = {"human", "automation", "agent"}
ARTIFACT_KINDS = {"world-save", "datapack", "resource-pack", "structure"}
MAX_LOCAL_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_REQUEST_BYTES = 128 * 1024


class Refused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(value: bool, reason: str) -> None:
    if not value:
        raise Refused(reason)


def fields(obj: object, mandatory: set[str], optional: set[str] = frozenset()) -> dict:
    require(type(obj) is dict, "INVALID_SHAPE")
    require(mandatory <= obj.keys() and obj.keys() <= mandatory | optional,
            "INVALID_FIELDS")
    return obj


def identifier(value: object) -> bool:
    return isinstance(value, str) and bool(IDENT.fullmatch(value))


def principal_id(value: object) -> bool:
    return isinstance(value, str) and bool(PRINCIPAL_ID.fullmatch(value))


def realm_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
        return str(parsed) == value and parsed.version == 4
    except (ValueError, AttributeError):
        return False


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path: pathlib.Path) -> dict:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        obj = {}
        for key, val in pairs:
            if key in obj:
                raise Refused("DUPLICATE_JSON_KEY")
            obj[key] = val
        return obj

    try:
        require(path.is_file() and 0 < path.stat().st_size <= MAX_REQUEST_BYTES,
                "REQUEST_SIZE_OUT_OF_BOUNDS")
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              Refused("INVALID_JSON_CONSTANT")))
    except Refused:
        raise
    except (OSError, UnicodeError, ValueError):
        raise Refused("REQUEST_UNREADABLE") from None


def check_artifact(root: pathlib.Path, name: str, expected: str) -> tuple[int, str]:
    require(isinstance(name, str) and bool(name) and not name.startswith("/")
            and "\\" not in name, "UNSAFE_ARTIFACT_PATH")
    parts = pathlib.PurePosixPath(name).parts
    require(parts and all(part not in {".", ".."} for part in parts),
            "UNSAFE_ARTIFACT_PATH")
    try:
        root = root.resolve()
        candidate = root
        for part in parts:
            candidate = candidate / part
            require(not candidate.is_symlink(), "UNSAFE_ARTIFACT_PATH")
        resolved = candidate.resolve()
        require(resolved.is_relative_to(root) and resolved.is_file(), "ARTIFACT_NOT_FOUND")
        size = resolved.stat().st_size
        require(0 < size <= MAX_LOCAL_ARTIFACT_BYTES, "ARTIFACT_SIZE_OUT_OF_BOUNDS")
        hasher = hashlib.sha256()
        with resolved.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
        actual = hasher.hexdigest()
    except OSError:
        raise Refused("ARTIFACT_UNREADABLE") from None
    require(actual == expected, "ARTIFACT_DIGEST_MISMATCH")
    return size, actual


def parse_time(value: object) -> dt.datetime:
    require(isinstance(value, str) and value.endswith("Z"), "INVALID_EXPIRY")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Refused("INVALID_EXPIRY") from None
    require(parsed.tzinfo is not None, "INVALID_EXPIRY")
    return parsed


def plan(request: dict, artifact_root: pathlib.Path, now: dt.datetime | None = None) -> dict:
    r = fields(request, {"schema", "request_id", "realm_id", "environment",
                         "principal", "authorization", "target", "artifact",
                         "action"}, {"ttl_seconds", "expected_current_release"})
    require(r["schema"] == SCHEMA, "SCHEMA_UNSUPPORTED")
    require(identifier(r["request_id"]) and realm_uuid(r["realm_id"]), "INVALID_IDENTITY")
    require(isinstance(r["environment"], str)
            and r["environment"] in {"rdte", "operations"}, "INVALID_ENVIRONMENT")
    require(isinstance(r["action"], str)
            and r["action"] in ACTIONS, "MUTATION_NOT_ADMITTED")
    if r["environment"] == "rdte":
        require(type(r.get("ttl_seconds")) is int
                and 60 <= r["ttl_seconds"] <= 86400, "INVALID_RDTE_TTL")
    else:
        require("ttl_seconds" not in r, "OPERATIONS_TTL_FORBIDDEN")
    if "expected_current_release" in r:
        require(r["expected_current_release"] is None
                or identifier(r["expected_current_release"]), "INVALID_RELEASE")

    p = fields(r["principal"], {"kind", "issuer", "subject"}, {"delegation"})
    require(isinstance(p["kind"], str) and p["kind"] in KINDS
            and principal_id(p["issuer"]) and principal_id(p["subject"]),
            "INVALID_PRINCIPAL")
    a = fields(r["authorization"], {"audience_realm_id", "claimed_scopes"})
    require(a["audience_realm_id"] == r["realm_id"], "CROSS_REALM")
    require(type(a["claimed_scopes"]) is list
            and a["claimed_scopes"] == ["deploy:plan"], "CLAIMED_SCOPE_INVALID")
    if p["kind"] == "agent":
        delegation = fields(p.get("delegation"), {"sponsor", "expires_at", "claimed_scopes"})
        require(principal_id(delegation["sponsor"]), "INVALID_DELEGATION")
        require(delegation["claimed_scopes"] == ["deploy:plan"], "INVALID_DELEGATION")
        current = now or dt.datetime.now(dt.timezone.utc)
        require(parse_time(delegation["expires_at"]) > current, "DELEGATION_EXPIRED")
    else:
        require("delegation" not in p, "UNEXPECTED_DELEGATION")

    t = fields(r["target"], {"provider", "deployment_id", "world_id",
                             "minecraft_version", "backend", "purpose"},
               {"service_id"})
    require(t["provider"] == "truenas"
            and identifier(t["deployment_id"]) and identifier(t["world_id"]),
            "INVALID_TARGET")
    require(isinstance(t["backend"], str)
            and t["backend"] in {"vanilla", "paper"}
            and isinstance(t["minecraft_version"], str)
            and bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", t["minecraft_version"])),
            "INVALID_RUNTIME")
    require(isinstance(t["purpose"], str)
            and t["purpose"] in {"two-rivers", "generic"}, "INVALID_PURPOSE")
    require(t["purpose"] != "two-rivers" or t["backend"] == "vanilla",
            "TWO_RIVERS_REQUIRES_VANILLA")
    if "service_id" in t:
        require(realm_uuid(t["service_id"]), "INVALID_SERVICE_ID")

    artifact = fields(r["artifact"], {"kind", "relative_path", "sha256",
                                     "producer", "release_id", "world_id",
                                     "minecraft_version"})
    require(isinstance(artifact["kind"], str)
            and artifact["kind"] in ARTIFACT_KINDS
            and identifier(artifact["release_id"])
            and identifier(artifact["world_id"])
            and artifact["world_id"] == t["world_id"], "ARTIFACT_WORLD_MISMATCH")
    require(artifact["minecraft_version"] == t["minecraft_version"],
            "ARTIFACT_VERSION_MISMATCH")
    require(isinstance(artifact["sha256"], str)
            and bool(SHA256.fullmatch(artifact["sha256"]))
            and isinstance(artifact["producer"], str)
            and bool(PRODUCER.fullmatch(artifact["producer"])),
            "INVALID_ARTIFACT_PROVENANCE")
    size, actual_hash = check_artifact(artifact_root, artifact["relative_path"],
                                        artifact["sha256"])
    intent = {"realm_id": r["realm_id"], "environment": r["environment"],
              "target": t, "artifact": {k: v for k, v in artifact.items()
                                       if k != "relative_path"},
              "action": r["action"],
              "expected_current_release": r.get("expected_current_release")}
    return {
        "schema": RECEIPT,
        "classification": "SOURCE_VALIDATED",
        "request_id": r["request_id"],
        "request_sha256": digest(r),
        "intent_sha256": digest(intent),
        "declared_principal_kind": p["kind"],
        "declared_principal_issuer": p["issuer"],
        "artifact_sha256_verified": actual_hash,
        "artifact_size": size,
        "provider_observed": False,
        "principal_authenticated": False,
        "authorization_verified": False,
        "artifact_format_verified": False,
        "world_activated": False,
        "minecraft_oracle_passed": False,
        "mutation_authorized": False,
        "next_gate": "INDEPENDENT_PROVIDER_READBACK_AND_AUTHORIZATION",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = plan(read_json(args.request), args.artifact_root)
        status = 0
    except Refused as exc:
        result = {"schema": RECEIPT, "classification": "REFUSED",
                  "reason": exc.code, "mutation_authorized": False,
                  "provider_observed": False}
        status = 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    sys.exit(main())
