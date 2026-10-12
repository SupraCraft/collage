"""Synthetic hostile package tests for the real-artifact consumer policy.

Live-genuine artifact path is qualified by the public cross-repo workflow,
not by these in-memory ZIPs. No Minecraft/TrueNAS processes start here.
"""
import hashlib
import json
import pathlib
import tempfile
import unittest
import zipfile

from tools.collage_deploy_plan import Refused
from tools.consume_vanilla_datapack_source import ALLOWED, consume, verify_candidate


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = pathlib.Path(self.td.name)
        self.path = self.root / "candidate.zip"
        self.blobs = {
            "pack.mcmeta": json.dumps({"pack": {"min_format": [121, 0],
                                                 "max_format": [121, 0]}}).encode(),
            "data/minecraft/tags/function/tick.json": b'{"values":[]}\n',
            "data/supracraft_core_restore/function/tick.mcfunction": b"say test\n",
        }
        self.manifest = None
        self.generate()

    def generate(self):
        with zipfile.ZipFile(self.path, "w") as z:
            for name, payload in sorted(self.blobs.items()):
                record = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                record.external_attr = 0o100644 << 16
                record.create_system = 3
                z.writestr(record, payload)
        payload = self.path.read_bytes()
        self.manifest = {
            "schema": "supracraft-vanilla-datapack-candidate/1",
            "classification": "SOURCE_ARTIFACT_EXPORTED",
            "kind": "datapack", "backend": "vanilla",
            "world_id": "lantern-rdte", "release_id": "lantern-core-restore-26-3",
            "minecraft_version": "26.3", "pack_format": [121, 0],
            "world_save_included": False, "collage_deployed": False,
            "producer": "SupraCraft/mc-server-images@" + "a" * 40,
            "relative_path": self.path.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "archive_size": len(payload),
            "members": [{"path": k, "sha256": hashlib.sha256(v).hexdigest(),
                         "bytes": len(v)} for k, v in sorted(self.blobs.items())],
        }

    def reject(self, code):
        with self.assertRaises(Refused) as ctx:
            consume(self.manifest, self.path, self.root)
        self.assertEqual(ctx.exception.code, code)

    def test_identical_real_bytes_for_three_actor_plans(self):
        report = consume(self.manifest, self.path, self.root)
        self.assertEqual(report["classification"],
                         "SOURCE_ARTIFACT_AND_INTENT_PARITY_VALIDATED")
        self.assertEqual(set(report["audience_receipts"]),
                         {"human", "automation", "agent"})
        self.assertEqual(report["candidate"]["member_count"], 3)
        self.assertFalse(report["principal_authenticated"])
        self.assertFalse(report["mutation_authorized"])
        self.assertFalse(report["world_activated"])
        self.assertFalse(report["real_provider_readback"])

    def test_archive_and_source_drift_refused(self):
        self.path.write_bytes(self.path.read_bytes() + b"attacker")
        self.reject("CANDIDATE_ARCHIVE_SIZE")
        self.generate()
        self.manifest["sha256"] = "0" * 64
        self.reject("CANDIDATE_DIGEST_MISMATCH")
        self.generate()
        self.manifest["producer"] = "unknown/repo@" + "a" * 40
        self.reject("CANDIDATE_PRODUCER_DRIFT")

    def test_unsafe_member_refused(self):
        self.blobs["../outside"] = b"hidden\n"
        self.generate()
        # Manifest member-count validation is the earliest independent guard.
        self.reject("CANDIDATE_MEMBER_MANIFEST")

    def test_wrong_runtime_and_unqualified_claim_refused(self):
        self.manifest["minecraft_version"] = "1.21.11"
        self.reject("CANDIDATE_CONTRACT_DRIFT")
        self.generate()
        self.manifest["world_save_included"] = True
        self.reject("CANDIDATE_CONTRACT_DRIFT")

    def test_member_digest_and_duplicate_entries_refused(self):
        self.manifest["members"][0]["sha256"] = "0" * 64
        self.reject("CANDIDATE_MEMBER_DIGEST_MISMATCH")
        self.generate()
        with zipfile.ZipFile(self.path, "a") as z:
            z.writestr("pack.mcmeta", b"duplicate")
        self.manifest["archive_size"] = self.path.stat().st_size
        self.manifest["sha256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.reject("CANDIDATE_MEMBERS_DRIFT")

    def test_cross_root_refused(self):
        with tempfile.TemporaryDirectory() as second:
            with self.assertRaises(Refused) as caught:
                consume(self.manifest, self.path, pathlib.Path(second))
        self.assertEqual(caught.exception.code, "CANDIDATE_OUTSIDE_ARTIFACT_ROOT")


if __name__ == "__main__":
    unittest.main()
