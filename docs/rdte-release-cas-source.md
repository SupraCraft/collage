# RDTE release atomic reservation — synthetic proof, not an APPLY gate

Authority: COLLAGE private #3, public #19, and Agent Dispatch private #627.

The prior Ed25519 grant verifier binds a declared narrow principal/realm/world/release. A signature does not authenticate the invoking session and a nonce alone does not prove reservation. This experiment evaluates SQLite atomic transactions with an existing signed grant and an exclusively synthetic world release head.

- seed_synthetic_head initializes a deliberately fake world release head in disposable CPU tests only.
- reserve_synthetic verifies the signed grant again; refuses a missing/foreign/stale head; then BEGIN IMMEDIATE plus unique nonce, idempotency and one outstanding reservation per realm/deployment/world. A local RESERVED row is durable, but cannot authorize a native world change or rollback. Ambiguous failures fail closed; held reservations require independent reconciliation.
- Independent source tests exercise same/re-keyed replay, foreign/missing/stale head, tampered grant or artifact, symlinked ledger, and simultaneous contenders. All input values and keys are synthetic.

This is a minimal source-only library experiment, not a new runtime service, IAM authority, second manager, scheduler, deploy command, or TrueNAS controller. The source receipt explicitly keeps principal_session_authenticated, native_provider_live_owner_verified, live_release_head_verified, release_mutation_performed, rollback_admitted and mutation_authorized FALSE, with physical_true_nas_apply=HOLD.

Next live gate: authenticate the invoking peer independently of claims, read exact native App ownership and current release using the existing TLS-verified provider observer, bind the reservation to the existing world controller and native ZFS transaction, and independently exercise crash/rollback/idempotency negatives. Before adopting the SQLite journal operationally, prove the existing controller lacks a sufficient native CAS; every component must earn its keep.

G4 server-owned block-state causality is separately under public Agent Dispatch OP4I-016 qualification. No source-only CAS test promotes that product or authorizes physical TrueNAS APPLY.
