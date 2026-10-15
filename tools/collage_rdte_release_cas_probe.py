#!/usr/bin/env python3
"""Disposable SOURCE-ONLY atomic reservation experiment for COLLAGE.

Never call this file from deploy:apply. It has no authenticated peer, live
provider release head, native App controller or ZFS actuator. The SQLite file
is a synthetic disposable ledger proving small transaction invariants only.
Do not introduce this as a second operational manager or production registry.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sqlite3

from .collage_deploy_plan import Refused
from .collage_disposable_release_grant import inspect

SCHEMA = "collage.rdte-release-cas-source-probe/1"
EMPTY = "<no-release>"
DDL = """
CREATE TABLE IF NOT EXISTS heads (
  realm TEXT NOT NULL, deployment TEXT NOT NULL, world TEXT NOT NULL,
  current_release TEXT NOT NULL,
  PRIMARY KEY(realm, deployment, world)
);
CREATE TABLE IF NOT EXISTS reservations (
  issuer TEXT NOT NULL, nonce TEXT NOT NULL, idempotency_key TEXT NOT NULL,
  realm TEXT NOT NULL, deployment TEXT NOT NULL, world TEXT NOT NULL,
  request_sha256 TEXT NOT NULL, artifact_sha256 TEXT NOT NULL,
  prior_release TEXT NOT NULL, state TEXT NOT NULL CHECK(state='RESERVED'),
  PRIMARY KEY(issuer, nonce), UNIQUE(issuer, idempotency_key),
  UNIQUE(realm, deployment, world)
);
"""


def _open(path: pathlib.Path):
    if not isinstance(path, pathlib.Path) or not path.parent.is_dir() or path.parent.is_symlink():
        raise Refused("SYNTHETIC_LEDGER_OWNER_NOT_EXACT")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise Refused("SYNTHETIC_LEDGER_FILE_UNSAFE")
    try:
        db = sqlite3.connect(str(path), timeout=0.2, isolation_level=None)
        db.execute("PRAGMA busy_timeout=200")
        db.executescript(DDL)
        return db
    except sqlite3.Error:
        raise Refused("SYNTHETIC_LEDGER_UNAVAILABLE") from None


def seed_synthetic_head(path: pathlib.Path, *, realm: str, deployment: str,
                        world: str, current_release: str | None) -> None:
    """Fixture only; NOT a way to assert live external world release state."""
    db = _open(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO heads VALUES (?,?,?,?)",
                   (realm, deployment, world, current_release or EMPTY))
        db.execute("COMMIT")
    except sqlite3.Error:
        db.execute("ROLLBACK")
        raise Refused("SYNTHETIC_HEAD_ALREADY_EXISTS") from None
    finally:
        db.close()


def reserve_synthetic(*, db_path: pathlib.Path, request: dict,
                      artifact_root: pathlib.Path, envelope: dict,
                      pinned_key: bytes, issuer: str, key_id: str,
                      now: dt.datetime | None = None) -> dict:
    """Signed source claim + durable SQLite compare/reserve **simulation**.

    The signed request alone cannot identify the actual invoking actor, prove
    live owner/world head or authorize APPLY. Retain the reserved row on
    ambiguous completion; recovery must independently reconcile it.
    """
    preflight = inspect(request=request, artifact_root=artifact_root,
                        envelope=envelope, pinned_key=pinned_key,
                        expected_issuer=issuer, expected_key_id=key_id,
                        now=now)
    if preflight["classification"] != "SIGNED_GRANT_SOURCE_PREFLIGHT_ONLY":
        raise Refused("GRANT_SOURCE_NOT_ADMITTED")
    c = envelope["grant"]
    if request.get("environment") != "rdte" or request.get("action") != "plan":
        raise Refused("SYNTHETIC_DISPOSABLE_PLAN_ONLY")
    key = (c["realm_id"], c["deployment_id"], c["world_id"])
    previous = c["expected_current_release"] or EMPTY
    db = _open(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            "SELECT current_release FROM heads WHERE realm=? AND deployment=? AND world=?",
            key).fetchall()
        if len(rows) != 1:
            raise Refused("SYNTHETIC_LIVE_OWNER_NOT_ESTABLISHED")
        if rows[0][0] != previous:
            raise Refused("SYNTHETIC_RELEASE_CAS_MISMATCH")
        db.execute(
            "INSERT INTO reservations VALUES (?,?,?,?,?,?,?,?,?,?)",
            (c["issuer"], c["nonce"], c["idempotency_key"], *key,
             preflight["request_sha256"], preflight["artifact_sha256"],
             previous, "RESERVED"))
        db.execute("COMMIT")
    except Refused:
        db.execute("ROLLBACK")
        raise
    except sqlite3.IntegrityError:
        db.execute("ROLLBACK")
        raise Refused("SYNTHETIC_REPLAY_OR_CONCURRENT_OWNER") from None
    except sqlite3.Error:
        db.execute("ROLLBACK")
        raise Refused("SYNTHETIC_TX_UNAVAILABLE") from None
    finally:
        db.close()
    return {
        "schema": SCHEMA,
        "classification": "SYNTHETIC_DURABLE_RESERVATION_ONLY",
        "source_request_sha256": preflight["request_sha256"],
        "source_artifact_sha256": preflight["artifact_sha256"],
        "synthetic_sqlite_reservation_recorded": True,
        "synthetic_replay_concurrent_cas_enforced": True,
        "principal_session_authenticated": False,
        "native_provider_live_owner_verified": False,
        "live_release_head_verified": False,
        "release_mutation_performed": False,
        "rollback_admitted": False,
        "mutation_authorized": False,
        "physical_true_nas_apply": "HOLD",
        "next_gate": "TRUSTED_PEER_AND_ACTUAL_WORLD_RELEASE_HEAD_COUPLED_TO_NATIVE_ACTUATOR",
    }
