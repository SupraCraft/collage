"""S6 exact source-validated real datapack bridge, adversarial human/CI/agent parity."""
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
from tools.qualify_real_vanilla263_artifact_source_parity import (
    SCHEMA, SOURCE_REF, check_export, qualify, request_for,
)
from tools.collage_deploy_plan import Refused, plan

NOW=dt.datetime(2026,10,14,12,tzinfo=dt.timezone.utc)


class TestRealVanilla263SourceParity(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.root=pathlib.Path(self.d.name)
        self.blob=self.root/"lantern-restoration-26.3.zip"
        self.blob.write_bytes(b"not a real datapack: unit-test-only bytes")
        self.manifest={
            "schema":"supracraft-vanilla-datapack-candidate/1",
            "classification":"SOURCE_ARTIFACT_EXPORTED",
            "kind":"datapack","backend":"vanilla",
            "producer":SOURCE_REF,
            "minecraft_version":"26.3",
            "world_id":"lantern-rdte",
            "release_id":"lantern-core-restore-26-3",
            "pack_format":[121,0],
            "relative_path":self.blob.name,
            "sha256":hashlib.sha256(self.blob.read_bytes()).hexdigest(),
            "archive_size":self.blob.stat().st_size,
            "members":[
                {"path":"pack.mcmeta","bytes":10,"sha256":"a"*64},
                {"path":"data/minecraft/tags/function/tick.json","bytes":20,"sha256":"b"*64},
                {"path":"data/supracraft_core_restore/function/tick.mcfunction","bytes":30,"sha256":"c"*64},
            ],
            "world_save_included":False,
            "collage_deployed":False,
            "full_two_rivers_world_qualified":False,
            "minecraft_runtime_verified_by_this_export":False,
        }

    def test_parity_does_not_inherit_format_or_native_deploy(self):
        out=qualify(self.manifest,self.root,now=NOW)
        self.assertEqual(out["schema"],SCHEMA)
        self.assertEqual(out["classification"],"REAL_DATAPACK_SOURCE_PLAN_PARITY")
        self.assertEqual(out["caller_kinds"],["human","automation","agent"])
        self.assertTrue(out["intents_equal"])
        for flag in ("provider_observed","actor_authenticated","permission_to_apply",
                     "datapack_contents_independently_verified",
                     "native_guest_with_this_artifact_qualified","world_activated",
                     "two_rivers_complete"):
            self.assertIs(out[flag],False)
        self.assertEqual(out["physical_truenas_apply"],"HOLD")

    def test_declared_agent_scope_is_not_authority(self):
        req=request_for(self.manifest,"agent",now=NOW)
        self.assertEqual(req["principal"]["delegation"]["claimed_scopes"],["deploy:plan"])
        self.assertEqual(req["target"]["world_id"],"lantern-rdte")
        self.assertEqual(req["target"]["deployment_id"],"rdte-t6-minecraft-vanilla-263")
        self.assertEqual(req["target"]["purpose"],"generic") # Not complete Two Rivers
        self.assertEqual(plan(req,self.root,now=NOW)["classification"],"SOURCE_VALIDATED")
        req["action"]="apply"
        with self.assertRaisesRegex(Refused,"MUTATION_NOT_ADMITTED"):
            plan(req,self.root,now=NOW)
        with self.assertRaisesRegex(Refused,"CALLER_KIND_UNSUPPORTED"):
            request_for(self.manifest,"admin",now=NOW)

    def test_reject_producer_scope_world_version_digest_and_size_drift(self):
        variants=[
            ("producer","SupraCraft/mc-server-images@"+"f"*40),
            ("classification","NATIVE_GUEST_SUPPORTED"),
            ("backend","paper"),("minecraft_version","1.21.11"),
            ("world_id","foreign-world"),("release_id","wrong"),
            ("collage_deployed",True),("world_save_included",True),
            ("full_two_rivers_world_qualified",True),
            ("minecraft_runtime_verified_by_this_export",True),
            ("sha256","bad"),("archive_size",0),
            ("relative_path","../../foreign"),
        ]
        for key,value in variants:
            m=copy.deepcopy(self.manifest)
            m[key]=value
            with self.subTest(field=key),self.assertRaises(Refused):
                qualify(m,self.root,now=NOW)
        for change in ("missing","duplicate","bad-digest","zero-size"):
            m=copy.deepcopy(self.manifest)
            if change=="missing":m["members"].pop()
            if change=="duplicate":m["members"][1]=dict(m["members"][0])
            if change=="bad-digest":m["members"][0]["sha256"]="z"*64
            if change=="zero-size":m["members"][0]["bytes"]=0
            with self.subTest(change=change),self.assertRaises(Refused):
                qualify(m,self.root,now=NOW)

    def test_true_artifact_byte_integrity_even_when_export_manifest_claims_valid(self):
        self.blob.write_bytes(b"tampered")
        with self.assertRaisesRegex(Refused,"ARTIFACT_DIGEST_MISMATCH"):
            qualify(self.manifest,self.root,now=NOW)

    def test_cli_bounded_refusal_without_source_or_guest_promotion(self):
        manifest=self.root/"manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        script=(pathlib.Path(__file__).resolve().parents[1]/
                "tools/qualify_real_vanilla263_artifact_source_parity.py")
        a=subprocess.run([sys.executable,str(script),"--manifest",str(manifest),
                          "--artifact-root",str(self.root)],
                         text=True,capture_output=True)
        self.assertEqual(a.returncode,0,a.stderr)
        self.assertEqual(json.loads(a.stdout)["classification"],
                         "REAL_DATAPACK_SOURCE_PLAN_PARITY")
        self.manifest["minecraft_version"]="26.4"
        manifest.write_text(json.dumps(self.manifest))
        b=subprocess.run([sys.executable,str(script),"--manifest",str(manifest),
                          "--artifact-root",str(self.root)],
                         text=True,capture_output=True)
        self.assertEqual(b.returncode,2)
        self.assertEqual(json.loads(b.stdout)["classification"],"REFUSED")
        self.assertNotIn("World activated",b.stdout)


if __name__=="__main__":
    unittest.main()
