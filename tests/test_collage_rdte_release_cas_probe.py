"""Synthetic durable nonce/world compare-and-swap falsification, no native APPLY."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import pathlib
import tempfile
import threading
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.collage_deploy_plan import Refused, canonical, digest
from tools.collage_rdte_release_cas_probe import (
    reserve_synthetic, seed_synthetic_head, SCHEMA)

NOW = dt.datetime(2026,10,15,7,tzinfo=dt.timezone.utc)
REALM="d68a14b9-2a1c-4e83-a452-e3b569cdf93e"
DEPLOY="rdte-t6-minecraft-vanilla-263"
WORLD="lantern-rdte"


class CASProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.artifact=self.root/"synthetic.bin"
        self.artifact.write_bytes(b"source-only fixture: NOT a native Minecraft world")
        self.database=self.root/"cas-fixture.sqlite3"
        self.private=Ed25519PrivateKey.generate()
        self.public=self.private.public_key().public_bytes(
            serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.req={
            "schema":"collage.deployment-request/1",
            "request_id":"synthetic-release-reservation-001",
            "realm_id":REALM,"environment":"rdte","ttl_seconds":3600,
            "principal":{"kind":"automation","issuer":"test-pinned-issuer",
                         "subject":"synthetic-ci-client"},
            "authorization":{"audience_realm_id":REALM,
                             "claimed_scopes":["deploy:plan"]},
            "target":{"provider":"truenas","deployment_id":DEPLOY,
                      "service_id":"11111111-1111-4111-8111-111111111111",
                      "world_id":WORLD,"minecraft_version":"26.3",
                      "backend":"vanilla","purpose":"two-rivers"},
            "artifact":{"kind":"datapack","relative_path":"synthetic.bin",
                        "sha256":hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
                        "producer":"SupraCraft/collage@"+"a"*40,
                        "release_id":"candidate-1","world_id":WORLD,
                        "minecraft_version":"26.3"},
            "action":"plan","expected_current_release":None,
        }

    def envelope(self, *, nonce="0123456789abcdef-seed", key="0123456789abcdef-once"):
        c={
            "issuer":"test-pinned-issuer", "key_id":"pinned-key-01",
            "subject":"synthetic-ci-client","kind":"automation",
            "realm_id":REALM,"environment":"rdte",
            "deployment_id":DEPLOY,
            "service_id":"11111111-1111-4111-8111-111111111111",
            "world_id":WORLD, "request_sha256":digest(self.req),
            "candidate_sha256":self.req["artifact"]["sha256"],
            "expected_current_release":None,"action":"apply",
            "not_before":"2026-10-15T06:59:00Z",
            "expires_at":"2026-10-15T07:03:00Z",
            "nonce":nonce,"idempotency_key":key,
        }
        return {"schema":"collage.rdte-release-grant/1",
                "grant":c,"signature":self.private.sign(canonical(c)).hex()}

    def reserve(self, envelope):
        return reserve_synthetic(db_path=self.database, request=self.req,
               artifact_root=self.root, envelope=envelope, pinned_key=self.public,
               issuer="test-pinned-issuer", key_id="pinned-key-01",now=NOW)

    def seed(self, *, current=None, realm=REALM,world=WORLD):
        seed_synthetic_head(self.database,realm=realm,deployment=DEPLOY,
                            world=world,current_release=current)

    def test_one_durable_reservation_never_grants_apply(self):
        self.seed()
        out=self.reserve(self.envelope())
        self.assertEqual(out["schema"],SCHEMA)
        self.assertEqual(out["classification"],"SYNTHETIC_DURABLE_RESERVATION_ONLY")
        for k in ("principal_session_authenticated","native_provider_live_owner_verified",
                  "live_release_head_verified","release_mutation_performed",
                  "rollback_admitted","mutation_authorized"):
            self.assertFalse(out[k],k)
        self.assertEqual(out["physical_true_nas_apply"],"HOLD")
        self.assertNotIn("0123456789abcdef-seed",str(out))
        with self.assertRaisesRegex(Refused,"REPLAY_OR_CONCURRENT_OWNER"):
            self.reserve(self.envelope())  # reconnect same file, replay refused

    def test_new_nonce_still_fails_while_world_reservation_is_active(self):
        self.seed()
        self.reserve(self.envelope())
        with self.assertRaisesRegex(Refused,"REPLAY_OR_CONCURRENT_OWNER"):
            self.reserve(self.envelope(nonce="fresh-new-nonce-12345",
                                       key="fresh-new-key-123456"))

    def test_missing_foreign_or_stale_release_head(self):
        with self.assertRaisesRegex(Refused,"LIVE_OWNER_NOT_ESTABLISHED"):
            self.reserve(self.envelope())
        self.seed(realm="1819675e-f8b1-41e2-91dc-279350accf04")
        with self.assertRaisesRegex(Refused,"LIVE_OWNER_NOT_ESTABLISHED"):
            self.reserve(self.envelope())
        with tempfile.TemporaryDirectory() as td:
            self.database=pathlib.Path(td)/"another.sqlite"
            self.seed(current="prior-release")
            with self.assertRaisesRegex(Refused,"RELEASE_CAS_MISMATCH"):
                self.reserve(self.envelope())

    def test_altered_source_or_signature_never_reaches_ledger(self):
        self.seed()
        g=self.envelope()
        g["grant"]["nonce"]="forged-new-nonce-12345"
        with self.assertRaisesRegex(Refused,"GRANT_SIGNATURE_INVALID"):
            self.reserve(g)
        g=self.envelope()
        self.artifact.write_bytes(b"tampered")
        with self.assertRaisesRegex(Refused,"ARTIFACT_DIGEST_MISMATCH"):
            self.reserve(g)

    def test_symlinked_ledger_refused(self):
        self.seed()
        alias=self.root/"alias.sqlite"
        alias.symlink_to(self.database)
        self.database=alias
        with self.assertRaisesRegex(Refused,"LEDGER_FILE_UNSAFE"):
            self.reserve(self.envelope())

    def test_race_two_threads_exactly_one_simulated_reservation(self):
        self.seed()
        barrier=threading.Barrier(3)
        successes=[]
        failures=[]
        def worker(n):
            barrier.wait()
            try:
                successes.append(self.reserve(self.envelope(
                    nonce="thread-nonce-value-"+str(n)+"-12345",
                    key="thread-unique-key-"+str(n)+"-12345")))
            except Refused as e:
                failures.append(e.code)
        threads=[threading.Thread(target=worker,args=(i,)) for i in (1,2)]
        for t in threads: t.start()
        barrier.wait()
        for t in threads: t.join(timeout=4)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(len(successes),1)
        self.assertEqual(len(failures),1)
        self.assertIn(failures[0],{"SYNTHETIC_REPLAY_OR_CONCURRENT_OWNER",
                                   "SYNTHETIC_LEDGER_UNAVAILABLE",
                                   "SYNTHETIC_TX_UNAVAILABLE"})


if __name__=="__main__":
    unittest.main()
