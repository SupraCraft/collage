#!/usr/bin/env python3
"""Strict RDTE grant SIGNATURE PREFLIGHT; deliberately no COLLAGE APPLY actuator.

Only a trusted caller may provide the pinned public key and expected issuer.
Caller-supplied request claims, a valid signature, or a provider JSON blob never
proves the invoking peer, a live native App, or a durable atomic nonce/CAS.
No rollback authority, privilege change, secrets, or production site action.
"""
from __future__ import annotations

import datetime as dt
import re

from .collage_deploy_plan import Refused, canonical, plan, parse_time

SCHEMA = "collage.rdte-release-grant/1"
RECEIPT = "collage.rdte-release-grant-preflight/1"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
HEX = re.compile(r"^[0-9a-f]{128}$")
NONCE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
MAX_LIFETIME = dt.timedelta(minutes=5)


def need(ok: bool, code: str) -> None:
    if not ok:
        raise Refused(code)


def inspect(*, request: dict, artifact_root, envelope: dict,
            pinned_key: bytes, expected_issuer: str, expected_key_id: str,
            now: dt.datetime | None = None) -> dict:
    """Check source bytes and an externally signed *candidate* grant.

    A PASS here means only: verified grant signing key and exact declared
    scope match. Never feed its result to a mutation API as authorization.
    Principal-session authentication, live TLS readback, and atomic nonce/CAS
    must be separately enforced in the existing qualified native actuator.
    """
    source = plan(request, artifact_root, now=now)
    need(type(envelope) is dict and set(envelope) == {"schema", "grant", "signature"},
         "GRANT_ENVELOPE_INVALID")
    need(envelope["schema"] == SCHEMA and type(envelope["grant"]) is dict,
         "GRANT_SCHEMA_INVALID")
    claims = envelope["grant"]
    required = {"issuer", "key_id", "subject", "kind", "realm_id",
                "environment", "deployment_id", "service_id", "world_id",
                "request_sha256", "candidate_sha256", "expected_current_release",
                "action", "not_before", "expires_at", "nonce", "idempotency_key"}
    need(set(claims) == required, "GRANT_FIELDS_INVALID")
    need(type(pinned_key) is bytes and len(pinned_key) == 32
         and type(expected_issuer) is str and bool(NAME.fullmatch(expected_issuer))
         and type(expected_key_id) is str and bool(NAME.fullmatch(expected_key_id)),
         "TRUST_CONFIGURATION_INVALID")
    need(claims["issuer"] == expected_issuer
         and claims["key_id"] == expected_key_id, "GRANT_ISSUER_NOT_PINNED")
    need(type(envelope["signature"]) is str
         and bool(HEX.fullmatch(envelope["signature"])), "GRANT_SIGNATURE_FORMAT")
    # Verify BEFORE treating any mutable claims as an authorized statement.
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
        Ed25519PublicKey.from_public_bytes(pinned_key).verify(
            bytes.fromhex(envelope["signature"]), canonical(claims))
    except (ImportError, ValueError, TypeError, InvalidSignature):
        raise Refused("GRANT_SIGNATURE_INVALID") from None
    p = request["principal"]
    t = request["target"]
    a = request["artifact"]
    expected = {
        "subject": p["subject"], "kind": p["kind"],
        "realm_id": request["realm_id"], "environment": "rdte",
        "deployment_id": t["deployment_id"], "service_id": t.get("service_id"),
        "world_id": t["world_id"], "request_sha256": source["request_sha256"],
        "candidate_sha256": source["artifact_sha256_verified"],
        "expected_current_release": request.get("expected_current_release"),
        "action": "apply",
    }
    need(request["environment"] == "rdte" and
         request["action"] == "plan" and
         p["issuer"] == expected_issuer and
         type(t.get("service_id")) is str,
         "DISPOSABLE_PLAN_AND_SERVICE_REQUIRED")
    need(all(type(claims[k]) is type(v) and claims[k] == v
             for k, v in expected.items()),
         "GRANT_REQUEST_SCOPE_MISMATCH")
    need(type(claims["nonce"]) is str
         and bool(NONCE.fullmatch(claims["nonce"])) and
         type(claims["idempotency_key"]) is str
         and bool(NONCE.fullmatch(claims["idempotency_key"])),
         "GRANT_NONCE_INVALID")
    try:
        nbf = parse_time(claims["not_before"])
        exp = parse_time(claims["expires_at"])
    except (Refused, TypeError, AttributeError):
        raise Refused("GRANT_TIME_INVALID") from None
    clock = now if now is not None else dt.datetime.now(dt.timezone.utc)
    need(isinstance(clock, dt.datetime) and clock.tzinfo is not None,
         "TRUSTED_CLOCK_REQUIRED")
    need(nbf <= clock < exp and dt.timedelta(0) < exp - nbf <= MAX_LIFETIME,
         "GRANT_TIME_WINDOW_INVALID")
    need(exp <= clock + MAX_LIFETIME, "GRANT_WINDOW_TOO_BROAD")
    return {
        "schema": RECEIPT, "classification": "SIGNED_GRANT_SOURCE_PREFLIGHT_ONLY",
        "request_sha256": source["request_sha256"],
        "artifact_sha256": source["artifact_sha256_verified"],
        "declared_principal_kind": claims["kind"],
        "grant_signature_verified": True,
        "grant_scope_matches_source": True,
        "principal_session_authenticated": False,
        "provider_live_owner_observed": False,
        "nonce_durably_consumed": False,
        "release_cas_acquired": False,
        "rollback_admitted": False,
        "mutation_authorized": False,
        "world_activated": False,
        "physical_truenas_apply": "HOLD",
        "next_gate": "TRUSTED_PEER_LIVE_OWNER_AND_ATOMIC_NONCE_CAS",
    }
