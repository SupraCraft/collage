#!/usr/bin/env python3
"""Correlate COLLAGE's three-source plans to a separate real vanilla RDTE receipt.

This explicitly does NOT authorize or execute a COLLAGE-managed deployment.
The consumer source planner still names the *intended* TrueNAS target, whereas
the runtime oracle is a separate loopback/free-runner fixture. Never convert
their shared artifact identity into evidence of TrueNAS provider readback,
principal authentication, or authorized mutation.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re

PRODUCER = "SupraCraft/mc-server-images@7f888b5829f4e5576d5ce512d86327348c43f01e"
RUNTIME_QUALIFIER = "SupraCraft/mc-server-images@2906aa1bc0ccb2f2da3a7e61adea1ea88dfc3aaa"
EXPECTED_STEPS = [
    "quiesce", "snapshot_current", "activate_candidate", "resume",
    "health_check", "inject_health_fault_after_positive_oracle",
    "restore_snapshot", "rollback_recheck"
]
AUDIENCES = {"human", "automation", "agent"}


class Refused(Exception):
    pass


def require(value: bool, reason: str) -> None:
    if not value:
        raise Refused(reason)


def correlate(manifest: dict, source: dict, runtime: dict) -> dict:
    require(type(manifest) is dict and type(source) is dict and type(runtime) is dict,
            "INVALID_RECEIPT_SHAPE")
    require(manifest.get("producer") == PRODUCER and
            manifest.get("sha256") == runtime.get("source_artifact_sha256") and
            isinstance(manifest.get("sha256"), str) and
            re.fullmatch("[0-9a-f]{64}", manifest["sha256"]),
            "RUNTIME_ARTIFACT_IDENTITY_MISMATCH")
    require(source.get("schema") == "collage.artifact-consumer-source-parity/1" and
            source.get("classification") == "SOURCE_ARTIFACT_AND_INTENT_PARITY_VALIDATED",
            "COLLAGE_SOURCE_PLAN_NOT_ACCEPTED")
    candidate = source.get("candidate")
    require(type(candidate) is dict and
            candidate.get("sha256") == manifest["sha256"] and
            candidate.get("producer") == PRODUCER and
            candidate.get("world_id") == manifest.get("world_id") and
            candidate.get("release_id") == manifest.get("release_id") and
            candidate.get("minecraft_version") == "26.3" and
            candidate.get("kind") == "datapack" and
            candidate.get("member_count") == 3,
            "COLLAGE_CANDIDATE_BOUNDARY_DRIFT")
    kinds = source.get("audience_receipts")
    require(type(kinds) is dict and set(kinds) == AUDIENCES and
            all(type(item) is dict and item.get("source_classification") == "SOURCE_VALIDATED"
                and isinstance(item.get("request_sha256"), str)
                and re.fullmatch("[0-9a-f]{64}", item["request_sha256"])
                for item in kinds.values()) and
            isinstance(source.get("common_intent_sha256"), str) and
            re.fullmatch("[0-9a-f]{64}", source["common_intent_sha256"]),
            "THREE_AUDIENCE_SOURCE_INTENT_NOT_QUALIFIED")
    require(source.get("principal_authenticated") is False and
            source.get("real_provider_readback") is False and
            source.get("mutation_authorized") is False and
            source.get("world_activated") is False,
            "SOURCE_PLAN_PRIVILEGE_CLAIM_DRIFT")
    require(runtime.get("schema") == "supracraft.op3-disposable-world-activation/1" and
            runtime.get("classification") ==
            "REAL_VANILLA_DATAPACK_ACTIVATION_AND_FAULT_ROLLBACK" and
            runtime.get("producer") == PRODUCER and
            runtime.get("minecraft_version") == "26.3" and
            runtime.get("protocol") == 777 and
            runtime.get("world_id") == manifest["world_id"] and
            runtime.get("release_id") == manifest["release_id"] and
            runtime.get("steps") == EXPECTED_STEPS,
            "INDEPENDENT_VANILLA_RUNTIME_NOT_ACCEPTED")
    require(runtime.get("independent_server_trigger_pass") is True and
            runtime.get("fault_injection_rollback_pass") is True and
            runtime.get("rollback_absence_of_datapack_behavior_pass") is True and
            runtime.get("world_restored_exact_bytes_before_restart") is True and
            runtime.get("restored_world_hash") == runtime.get("baseline_world_hash") and
            runtime.get("candidate_world_hash") != runtime.get("baseline_world_hash"),
            "RUNTIME_SEMANTIC_OR_ROLLBACK_ORACLE_FAILED")
    require(runtime.get("collage_deployed") is False and
            runtime.get("truenas_deployed") is False and
            runtime.get("human_automation_agent_parity_qualified") is False and
            runtime.get("client_gameplay_qualified") is False and
            runtime.get("full_two_rivers_world_qualified") is False and
            runtime.get("operational_selection") is False and
            runtime.get("physical_truenas_apply") == "HOLD",
            "RUNTIME_UNSUPPORTED_PROMOTION_CLAIM")
    require(manifest.get("world_save_included") is False and
            manifest.get("collage_deployed") is False,
            "PRODUCER_UNSUPPORTED_PROMOTION_CLAIM")
    return {
        "schema": "collage.vanilla-world-source-runtime-correlation/1",
        "classification": "SAME_ARTIFACT_SOURCE_PLAN_AND_INDEPENDENT_DISPOSABLE_RUNTIME_CONFIRMED",
        "source_producer": PRODUCER,
        "qualified_runtime_source": RUNTIME_QUALIFIER,
        "artifact_sha256": manifest["sha256"],
        "world_id": manifest["world_id"],
        "release_id": manifest["release_id"],
        "minecraft_version": "26.3",
        "source_plan_intent_sha256": source["common_intent_sha256"],
        "source_plan_audiences": sorted(kinds),
        "independent_vanilla_real_server_activation_pass": True,
        "independent_vanilla_rollback_pass": True,
        "collage_deployment_performed": False,
        "truenas_provider_observed": False,
        "client_gameplay_qualified": False,
        "principal_authentication_verified": False,
        "human_automation_agent_mutation_parity_qualified": False,
        "operational_selection": False,
        "physical_truenas_apply": "HOLD",
        "next_gate": "ADMITTED_COLLAGE_TO_DISPOSABLE_VANILLA_TARGET_ACTUATION_AND_GYM",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--source-receipt", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-receipt", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = correlate(json.loads(args.manifest.read_text()),
                           json.loads(args.source_receipt.read_text()),
                           json.loads(args.runtime_receipt.read_text()))
        exit_code = 0
    except (ValueError, OSError, Refused, KeyError) as exc:
        result = {
            "schema": "collage.vanilla-world-source-runtime-correlation/1",
            "classification": "REFUSED",
            "reason": type(exc).__name__,
            "detail": str(exc)[:180],
            "operational_selection": False,
            "physical_truenas_apply": "HOLD",
        }
        exit_code = 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "reason": result.get("detail")}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
