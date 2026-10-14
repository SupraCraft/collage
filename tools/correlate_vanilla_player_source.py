#!/usr/bin/env python3
"""COLLAGE OP-3D: bind three read-only plans to independent client-action world proof.

This is evidence correlation only. A planned TrueNAS target is NOT a deployed
TrueNAS target; a real Mineflayer offline-session is not player IAM or a
stock Mojang presentation oracle. No authorization or mutation is performed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

PRODUCER = "SupraCraft/mc-server-images@7f888b5829f4e5576d5ce512d86327348c43f01e"
QUALIFIER = "SupraCraft/mc-server-images@7fcfd8bd8e10fe0959b1b32524680a6c1d8317cf"
AUDIENCES = {"human", "automation", "agent"}
SHA = re.compile(r"[0-9a-f]{64}")


class Refused(Exception):
    pass


def require(ok: bool, cause: str) -> None:
    if not ok:
        raise Refused(cause)


def correlate(manifest: dict, source: dict, player: dict, *,
              native_source: dict | None = None) -> dict:
    require(all(type(x) is dict for x in (manifest, source, player)),
            "RECEIPT_NOT_OBJECT")
    require(manifest.get("producer") == PRODUCER and
            isinstance(manifest.get("sha256"), str) and
            SHA.fullmatch(manifest["sha256"]) is not None and
            manifest.get("world_id") == "lantern-rdte" and
            manifest.get("release_id") == "lantern-core-restore-26-3" and
            manifest.get("world_save_included") is False and
            manifest.get("collage_deployed") is False,
            "PRODUCER_IDENTITY_OR_SCOPE_DRIFT")
    require(source.get("schema") == "collage.artifact-consumer-source-parity/1" and
            source.get("classification") == "SOURCE_ARTIFACT_AND_INTENT_PARITY_VALIDATED" and
            isinstance(source.get("common_intent_sha256"), str) and
            SHA.fullmatch(source["common_intent_sha256"]) is not None,
            "SOURCE_PLANS_NOT_QUALIFIED")
    candidate = source.get("candidate")
    require(type(candidate) is dict and
            candidate.get("producer") == PRODUCER and
            candidate.get("sha256") == manifest["sha256"] and
            candidate.get("world_id") == manifest["world_id"] and
            candidate.get("release_id") == manifest["release_id"] and
            candidate.get("minecraft_version") == "26.3" and
            candidate.get("kind") == "datapack" and
            candidate.get("member_count") == 3,
            "COLLAGE_PLAN_WRONG_ARTIFACT_OR_REALM")
    kinds = source.get("audience_receipts")
    require(type(kinds) is dict and set(kinds) == AUDIENCES and
            all(type(x) is dict and x.get("source_classification") == "SOURCE_VALIDATED"
                and isinstance(x.get("request_sha256"), str)
                and SHA.fullmatch(x["request_sha256"]) is not None
                for x in kinds.values()),
            "THREE_AUDIENCE_PARITY_NOT_QUALIFIED")
    require(source.get("principal_authenticated") is False and
            source.get("real_provider_readback") is False and
            source.get("world_activated") is False and
            source.get("mutation_authorized") is False,
            "SOURCE_CANNOT_CLAIM_APPLY_AUTHORITY")
    require(player.get("schema") == "supracraft.op3c-vanilla-client-world-artifact/1" and
            player.get("classification") == "REAL_OFFLINE_PLAYER_ACTION_CAUSAL_ARTIFACT_AND_ROLLBACK" and
            player.get("producer") == PRODUCER and
            player.get("source_artifact_sha256") == manifest["sha256"] and
            player.get("world_id") == manifest["world_id"] and
            player.get("release_id") == manifest["release_id"] and
            player.get("minecraft_version") == "26.3" and
            player.get("protocol") == 777 and
            player.get("source_archive_size") == manifest.get("archive_size"),
            "CLIENT_RUNTIME_WRONG_ARTIFACT_VERSION_OR_REALM")
    for name in ("candidate_player", "postrollback_player"):
        client = player.get(name)
        require(type(client) is dict and
                client.get("requested_version") == "26.3" and
                client.get("negotiated_version") == "26.3" and
                client.get("protocol") == 777 and
                client.get("offline_mode") is True and
                client.get("server_join_independently_observed") is True and
                client.get("client_saw_air_before") is True and
                client.get("client_saw_redstone_after") is True and
                client.get("action") == "mineflayer.placeBlock",
                "CLIENT_ACTION_OR_INDEPENDENT_JOIN_UNPROVEN_" + name)
    require(player.get("mineflayer_offline_protocol_qualified") is True and
            player.get("player_caused_datapack_effect") is True and
            player.get("same_player_action_without_datapack_no_effect") is True and
            player.get("rollback_exact_snapshot_before_restart") is True and
            player.get("baseline_world_sha256") == player.get("restored_world_sha256") and
            player.get("candidate_world_sha256") != player.get("baseline_world_sha256"),
            "PLAYER_CAUSALITY_OR_ROLLBACK_NOT_VERIFIED")
    require(player.get("stock_mojang_client_qualified") is False and
            player.get("authenticated_account_qualified") is False and
            player.get("collage_deployed") is False and
            player.get("truenas_deployed") is False and
            player.get("human_automation_agent_parity_qualified") is False and
            player.get("full_two_rivers_world_qualified") is False and
            player.get("operational_selection") is False and
            player.get("physical_truenas_apply") == "HOLD",
            "UNSUPPORTED_PROVIDER_IAM_OR_OPERATIONAL_CLAIM")
    if native_source is not None:
        # An independently validated native-target plan is source-only.
        # Its artifact identity MUST match both the generic COLLAGE plan
        # and the real player-used ZIP; no guest deployment inferred.
        require(type(native_source) is dict and
                native_source.get("schema") == source["schema"] and
                native_source.get("classification") == source["classification"] and
                native_source.get("candidate") == candidate and
                native_source.get("source_native_target_profile") ==
                    "vanilla263-250426" and
                native_source.get("expected_native_app") ==
                    "rdte-t6-minecraft-vanilla-263" and
                native_source.get("expected_truenas_version") == "25.04.2.6",
                "NATIVE_SOURCE_ARTIFACT_OR_TARGET_MISMATCH")
        ns_kinds = native_source.get("audience_receipts")
        require(type(ns_kinds) is dict and set(ns_kinds) == AUDIENCES and
                all(type(x) is dict and x.get("source_classification") ==
                    "SOURCE_VALIDATED" for x in ns_kinds.values()) and
                isinstance(native_source.get("common_intent_sha256"), str) and
                SHA.fullmatch(native_source["common_intent_sha256"]) and
                native_source["common_intent_sha256"] !=
                    source["common_intent_sha256"],
                "NATIVE_SOURCE_AUDIENCE_OR_TARGET_INTENT_DRIFT")
        require(native_source.get("real_provider_readback") is False and
                native_source.get("native_guest_with_this_artifact_qualified") is False and
                native_source.get("world_activated") is False and
                native_source.get("mutation_authorized") is False,
                "NATIVE_SOURCE_FALSE_LIVE_DEPLOYMENT_CLAIM")
    return {
        "schema": "collage.op3d-player-source-correlation/1",
        "classification": "SAME_ARTIFACT_SOURCE_PLANS_AND_INDEPENDENT_REAL_PLAYER_ACTION_CORRELATED",
        "producer": PRODUCER,
        "runtime_qualification_commit": QUALIFIER,
        "artifact_sha256": manifest["sha256"],
        "world_id": manifest["world_id"],
        "release_id": manifest["release_id"],
        "source_plan_intent_sha256": source["common_intent_sha256"],
        "audience_kinds": sorted(kinds),
        "native_app_artifact_source_intent_bound": native_source is not None,
        "native_app_expected": "rdte-t6-minecraft-vanilla-263" if native_source is not None else None,
        "native_app_source_plan_intent_sha256": (
            native_source["common_intent_sha256"] if native_source is not None else None),
        "native_guest_with_artifact_qualified": False,
        "native_artifact_activation_performed": False,
        "offline_client_action_independently_verified": True,
        "real_vanilla_datapack_consequence_verified": True,
        "postrollback_same_action_does_not_trigger_datapack": True,
        "collage_managed_deployment": False,
        "truenas_provider_observed": False,
        "authenticated_game_client_verified": False,
        "stock_client_visual_presentation_verified": False,
        "principal_authorization_verified": False,
        "operational_selection": False,
        "physical_truenas_apply": "HOLD",
        "next_gate": "ADMITTED_MANAGED_DISPOSABLE_DEPLOYMENT_AND_GYM_CLIENT_GAMEPLAY",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--source-receipt", type=Path, required=True)
    ap.add_argument("--player-receipt", type=Path, required=True)
    ap.add_argument("--native-source-receipt", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    try:
        result = correlate(json.loads(args.manifest.read_text()),
                           json.loads(args.source_receipt.read_text()),
                           json.loads(args.player_receipt.read_text()),
                           native_source=(json.loads(args.native_source_receipt.read_text())
                                          if args.native_source_receipt else None))
        exit_code = 0
    except (OSError, ValueError, KeyError, Refused) as exc:
        result = {
            "schema": "collage.op3d-player-source-correlation/1",
            "classification": "REFUSED",
            "reason": str(exc)[:220],
            "operational_selection": False,
            "physical_truenas_apply": "HOLD",
        }
        exit_code = 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "reason": result.get("reason")}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
