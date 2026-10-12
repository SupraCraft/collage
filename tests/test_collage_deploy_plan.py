"""Unit and adversarial tests for the source-only COLLAGE deployment contract."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tools.collage_deploy_plan import Refused, plan, read_json

NOW = dt.datetime(2026, 10, 12, 12, tzinfo=dt.timezone.utc)
REALM = "d68a14b9-2a1c-4e83-a452-e3b569cdf93e"
PRODUCER = "SupraCraft/mc-structure-foundry-private@" + "a" * 40


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "artifacts").mkdir()
        self.blob = self.root / "artifacts" / "bounded-world-projection.bin"
        # Deliberately a non-world contract fixture, never a runtime acceptance.
        self.blob.write_bytes(b"contract-only fixture; not a valid Minecraft world\n")
        self.expected = hashlib.sha256(self.blob.read_bytes()).hexdigest()

    def request(self, kind="human", environment="rdte"):
        principal = {"kind": kind, "issuer": "test-issuer", "subject": "test-subject"}
        if kind == "agent":
            principal["delegation"] = {
                "sponsor": "qualified-sponsor",
                "expires_at": "2026-10-13T12:00:00Z",
                "claimed_scopes": ["deploy:plan"],
            }
        req = {
            "schema": "collage.deployment-request/1",
            "request_id": "two-rivers-rdte-001",
            "realm_id": REALM,
            "environment": environment,
            "principal": principal,
            "authorization": {"audience_realm_id": REALM,
                              "claimed_scopes": ["deploy:plan"]},
            "target": {"provider": "truenas",
                       "deployment_id": "two-rivers-test",
                       "world_id": "two-rivers-world",
                       "minecraft_version": "26.3",
                       "backend": "vanilla",
                       "purpose": "two-rivers"},
            "artifact": {"kind": "world-save",
                         "relative_path": "artifacts/bounded-world-projection.bin",
                         "sha256": self.expected,
                         "producer": PRODUCER,
                         "release_id": "candidate-1",
                         "world_id": "two-rivers-world",
                         "minecraft_version": "26.3"},
            "action": "plan",
            "expected_current_release": None,
        }
        if environment == "rdte":
            req["ttl_seconds"] = 3600
        return req

    def good(self, req):
        return plan(req, self.root, now=NOW)

    def reject(self, req, reason):
        with self.assertRaises(Refused) as caught:
            self.good(req)
        self.assertEqual(caught.exception.code, reason)

    def test_three_audiences_share_identical_intent(self):
        receipts = [self.good(self.request(kind)) for kind in
                    ("human", "automation", "agent")]
        self.assertEqual(len({x["intent_sha256"] for x in receipts}), 1)
        self.assertEqual({x["classification"] for x in receipts},
                         {"SOURCE_VALIDATED"})
        for receipt in receipts:
            self.assertFalse(receipt["provider_observed"])
            self.assertFalse(receipt["principal_authenticated"])
            self.assertFalse(receipt["authorization_verified"])
            self.assertFalse(receipt["artifact_format_verified"])
            self.assertFalse(receipt["world_activated"])
            self.assertFalse(receipt["mutation_authorized"])
            self.assertEqual(receipt["artifact_sha256_verified"], self.expected)

    def test_operations_uses_same_intent_semantics(self):
        receipt = self.good(self.request(environment="operations"))
        self.assertEqual(receipt["classification"], "SOURCE_VALIDATED")
        self.assertFalse(receipt["mutation_authorized"])

    def test_reject_cross_realm(self):
        req = self.request()
        req["authorization"]["audience_realm_id"] = (
            "1819675e-f8b1-41e2-91dc-279350accf04")
        self.reject(req, "CROSS_REALM")

    def test_reject_unbounded_scope_and_apply(self):
        req = self.request()
        req["authorization"]["claimed_scopes"] = ["deploy:apply"]
        self.reject(req, "CLAIMED_SCOPE_INVALID")
        req = self.request()
        req["action"] = "apply"
        self.reject(req, "MUTATION_NOT_ADMITTED")

    def test_reject_expired_agent(self):
        req = self.request("agent")
        req["principal"]["delegation"]["expires_at"] = "2026-10-11T12:00:00Z"
        self.reject(req, "DELEGATION_EXPIRED")

    def test_reject_missing_agent_delegation(self):
        req = self.request("agent")
        del req["principal"]["delegation"]
        self.reject(req, "INVALID_SHAPE")

    def test_reject_bad_world_version_and_backend(self):
        req = self.request()
        req["artifact"]["world_id"] = "not-the-world"
        self.reject(req, "ARTIFACT_WORLD_MISMATCH")
        req = self.request()
        req["artifact"]["minecraft_version"] = "1.21.11"
        self.reject(req, "ARTIFACT_VERSION_MISMATCH")
        req = self.request()
        req["target"]["backend"] = "paper"
        self.reject(req, "TWO_RIVERS_REQUIRES_VANILLA")

    def test_reject_digest_drift(self):
        req = self.request()
        self.blob.write_bytes(b"tampered")
        self.reject(req, "ARTIFACT_DIGEST_MISMATCH")

    def test_reject_escape_symlink_and_unknown_fields(self):
        req = self.request()
        req["artifact"]["relative_path"] = "../outside"
        self.reject(req, "UNSAFE_ARTIFACT_PATH")
        shortcut = self.root / "artifacts" / "shortcut"
        shortcut.symlink_to(self.blob)
        req = self.request()
        req["artifact"]["relative_path"] = "artifacts/shortcut"
        self.reject(req, "UNSAFE_ARTIFACT_PATH")
        req = self.request()
        req["authorization"]["credential"] = "never accept caller secrets"
        self.reject(req, "INVALID_FIELDS")

    def test_reject_ops_ttl_and_invalid_rdte_ttl(self):
        req = self.request(environment="operations")
        req["ttl_seconds"] = 3600
        self.reject(req, "OPERATIONS_TTL_FORBIDDEN")
        req = self.request()
        req["ttl_seconds"] = True
        self.reject(req, "INVALID_RDTE_TTL")

    def test_reject_duplicates(self):
        p = self.root / "duplicate.json"
        p.write_text('{"schema":"v1","schema":"v2"}')
        with self.assertRaises(Refused) as caught:
            read_json(p)
        self.assertEqual(caught.exception.code, "DUPLICATE_JSON_KEY")

    def test_no_host_claims_or_mutations(self):
        # A missing live provider is not concealed by a source-only PASS.
        receipt = self.good(self.request())
        self.assertEqual(receipt["next_gate"],
                         "INDEPENDENT_PROVIDER_READBACK_AND_AUTHORIZATION")
        self.assertNotIn("truenas_observed_state", receipt)


    def test_cli_smoke_is_machine_readable_and_non_mutating(self):
        request_file = self.root / "request.json"
        request_file.write_text(json.dumps(self.request()))
        entrypoint = pathlib.Path(__file__).resolve().parents[1] / "tools" / "collage_deploy_plan.py"
        cp = subprocess.run([sys.executable, str(entrypoint),
                             "--request", str(request_file),
                             "--artifact-root", str(self.root)],
                            capture_output=True, text=True, check=False)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        receipt = json.loads(cp.stdout)
        self.assertEqual(receipt["classification"], "SOURCE_VALIDATED")
        self.assertFalse(receipt["mutation_authorized"])
        self.assertFalse(receipt["provider_observed"])
        self.assertFalse(receipt["authorization_verified"])

    def test_malformed_unhashable_values_refuse_without_crash(self):
        fields_to_break = [
            ("environment",), ("action",), ("principal", "kind"),
            ("target", "backend"), ("target", "purpose"), ("artifact", "kind")
        ]
        for path in fields_to_break:
            req = self.request()
            node = req
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = []
            with self.subTest(path=path):
                with self.assertRaises(Refused):
                    self.good(req)

    def test_namespaced_issuers_and_subjects(self):
        req = self.request("agent")
        req["principal"]["issuer"] = "urn:supracraft:workload:rdte"
        req["principal"]["subject"] = "realm/example/actor@host"
        receipt = self.good(req)
        self.assertEqual(receipt["declared_principal_issuer"],
                         "urn:supracraft:workload:rdte")
        self.assertFalse(receipt["principal_authenticated"])

    def test_reject_oversized_request_file(self):
        p = self.root / "oversized.json"
        p.write_bytes(b" " * (128 * 1024 + 1))
        with self.assertRaises(Refused) as caught:
            read_json(p)
        self.assertEqual(caught.exception.code, "REQUEST_SIZE_OUT_OF_BOUNDS")


if __name__ == "__main__":
    unittest.main()
