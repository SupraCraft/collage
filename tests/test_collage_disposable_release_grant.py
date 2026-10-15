"""Adversarial synthetic tests; no real credentials, provider or world mutation."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import pathlib
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.collage_deploy_plan import Refused, canonical, digest
from tools.collage_disposable_release_grant import inspect, SCHEMA

NOW = dt.datetime(2026, 10, 15, 6, tzinfo=dt.timezone.utc)
REALM = "d68a14b9-2a1c-4e83-a452-e3b569cdf93e"


class ReleaseGrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.blob = self.root / "fixture.bin"
        self.blob.write_bytes(b"source-only synthetic world fixture; never a valid MCWORLD")
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.req = {
            "schema": "collage.deployment-request/1",
            "request_id": "release-grant-source-test-001",
            "realm_id": REALM,
            "environment": "rdte",
            "ttl_seconds": 3600,
            "principal": {"kind": "human", "issuer": "rdte-test-issuer",
                          "subject": "human-test-operator"},
            "authorization": {"audience_realm_id": REALM,
                              "claimed_scopes": ["deploy:plan"]},
            "target": {"provider": "truenas",
                       "deployment_id": "rdte-t6-minecraft-vanilla-263",
                       "service_id": "11111111-1111-4111-8111-111111111111",
                       "world_id": "lantern-rdte", "minecraft_version": "26.3",
                       "backend": "vanilla", "purpose": "two-rivers"},
            "artifact": {"kind": "datapack", "relative_path": "fixture.bin",
                         "sha256": hashlib.sha256(self.blob.read_bytes()).hexdigest(),
                         "producer": "SupraCraft/mc-server-images@" + "a"*40,
                         "release_id": "lantern-release-001",
                         "world_id": "lantern-rdte", "minecraft_version": "26.3"},
            "action": "plan", "expected_current_release": None,
        }

    def make_grant(self, *, kind="human"):
        req = self.req
        req["principal"]["kind"] = kind
        if kind == "agent":
            req["principal"]["delegation"] = {
                "sponsor": "human-test-operator",
                "expires_at": "2026-10-16T06:00:00Z",
                "claimed_scopes": ["deploy:plan"],
            }
        else:
            req["principal"].pop("delegation", None)
        claims = {
            "issuer": "rdte-test-issuer", "key_id": "test-key-01",
            "subject": req["principal"]["subject"], "kind": kind,
            "realm_id": req["realm_id"], "environment": "rdte",
            "deployment_id": req["target"]["deployment_id"],
            "service_id": req["target"]["service_id"],
            "world_id": req["target"]["world_id"],
            "request_sha256": digest(req),
            "candidate_sha256": req["artifact"]["sha256"],
            "expected_current_release": req["expected_current_release"],
            "action": "apply",
            "not_before": "2026-10-15T05:59:00Z",
            "expires_at": "2026-10-15T06:02:00Z",
            "nonce": "unique-nonce-1234567890",
            "idempotency_key": "unique-transaction-12345",
        }
        return self.sign(claims)

    def sign(self, claims):
        return {"schema": SCHEMA, "grant": copy.deepcopy(claims),
                "signature": self.key.sign(canonical(claims)).hex()}

    def inspect(self, grant, *, key=None, now=NOW):
        return inspect(request=self.req, artifact_root=self.root, envelope=grant,
                       pinned_key=self.public if key is None else key,
                       expected_issuer="rdte-test-issuer",
                       expected_key_id="test-key-01", now=now)

    def reject(self, grant, code, *, key=None, now=NOW):
        with self.assertRaises(Refused) as ctx:
            self.inspect(grant, key=key, now=now)
        self.assertEqual(ctx.exception.code, code)

    def test_valid_signature_is_explicitly_not_apply_authority(self):
        for kind in ("human", "automation", "agent"):
            with self.subTest(kind=kind):
                r = self.inspect(self.make_grant(kind=kind))
                self.assertEqual(r["classification"],
                                 "SIGNED_GRANT_SOURCE_PREFLIGHT_ONLY")
                self.assertTrue(r["grant_signature_verified"])
                for field in ("mutation_authorized", "principal_session_authenticated",
                              "provider_live_owner_observed", "nonce_durably_consumed",
                              "release_cas_acquired", "world_activated", "rollback_admitted"):
                    self.assertFalse(r[field], field)
                self.assertEqual(r["physical_truenas_apply"], "HOLD")

    def test_forgery_changed_unsigned_bytes(self):
        g = self.make_grant()
        g["grant"]["world_id"] = "foreign-world"
        self.reject(g, "GRANT_SIGNATURE_INVALID")

    def test_signature_from_unpinned_key(self):
        g = self.make_grant()
        foreign = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.reject(g, "GRANT_SIGNATURE_INVALID", key=foreign)

    def test_signed_cross_realm_and_foreign_owner(self):
        for field, value in (("realm_id", "1819675e-f8b1-41e2-91dc-279350accf04"),
                             ("world_id", "foreign-world"),
                             ("deployment_id", "foreign-app"),
                             ("service_id", "22222222-2222-4222-8222-222222222222"),
                             ("kind", "agent"),
                             ("subject", "unbound-peer"),
                             ("environment", "operations"),
                             ("candidate_sha256", "0"*64),
                             ("request_sha256", "0"*64),
                             ("expected_current_release", "stale-release"),
                             ("action", "rollback")):
            with self.subTest(field=field):
                g = self.make_grant()
                g["grant"][field] = value
                self.reject(self.sign(g["grant"]), "GRANT_REQUEST_SCOPE_MISMATCH")

    def test_expired_not_yet_valid_or_unbounded_grant(self):
        for when in ("2026-10-15T05:58:00Z", "2026-10-15T06:03:00Z"):
            with self.subTest(when=when):
                self.reject(self.make_grant(), "GRANT_TIME_WINDOW_INVALID",
                            now=dt.datetime.fromisoformat(when.replace("Z", "+00:00")))
        g = self.make_grant()
        g["grant"]["expires_at"] = "2026-10-15T07:00:00Z"
        self.reject(self.sign(g["grant"]), "GRANT_TIME_WINDOW_INVALID")
        g = self.make_grant()
        g["grant"]["not_before"] = "2026-10-15T06:01:00Z"
        self.reject(self.sign(g["grant"]), "GRANT_TIME_WINDOW_INVALID")

    def test_key_id_and_issuer_are_preconfigured_not_envelope_supplied(self):
        for field, value in (("issuer", "other-issuer"), ("key_id", "other-key")):
            g = self.make_grant()
            g["grant"][field] = value
            self.reject(self.sign(g["grant"]), "GRANT_ISSUER_NOT_PINNED")

    def test_incorrect_nonce_and_idempotency_key_rejected(self):
        for field, value in (("nonce", "1"), ("idempotency_key", "all/*")):
            g = self.make_grant()
            g["grant"][field] = value
            self.reject(self.sign(g["grant"]), "GRANT_NONCE_INVALID")

    def test_unsigned_extra_fields_are_not_allowed(self):
        g = self.make_grant()
        g["grant"]["permit_physical_apply"] = True
        self.reject(self.sign(g["grant"]), "GRANT_FIELDS_INVALID")

    def test_bad_signature_format_and_missing_trust_configuration(self):
        g = self.make_grant()
        g["signature"] = "x"*128
        self.reject(g, "GRANT_SIGNATURE_FORMAT")
        self.reject(self.make_grant(), "TRUST_CONFIGURATION_INVALID", key=b"short")

    def test_planner_still_does_not_accept_apply_or_ops(self):
        self.req["action"] = "apply"
        self.reject(self.make_grant(), "MUTATION_NOT_ADMITTED")
        self.req["action"] = "plan"
        self.req["environment"] = "operations"
        self.req.pop("ttl_seconds")
        self.reject(self.make_grant(), "DISPOSABLE_PLAN_AND_SERVICE_REQUIRED")

    def test_artifact_tamper_cannot_use_valid_grant(self):
        g = self.make_grant()
        self.blob.write_bytes(b"tampered artifact")
        self.reject(g, "ARTIFACT_DIGEST_MISMATCH")

    def test_double_use_has_no_source_level_consumption_or_false_promotion(self):
        g = self.make_grant()
        a, b = self.inspect(g), self.inspect(g)
        self.assertEqual(a, b)
        self.assertFalse(b["nonce_durably_consumed"])
        self.assertFalse(b["release_cas_acquired"])
        self.assertFalse(b["mutation_authorized"])


if __name__ == "__main__":
    unittest.main()
