# RDTE signed release-grant preflight (P0 source-only candidate)

Authority: [COLLAGE private #3](https://github.com/SupraCraft/collage-private/issues/3), [public #19](https://github.com/SupraCraft/collage/issues/19), [Agent Dispatch #627](https://github.com/SemperSupra/agent-dispatch-private/issues/627). This is a *candidate* cryptographic preflight, not a deploy API.

## Where this fits

The existing `collage.deployment-request/1` planner remains strictly `action=plan`: no actor authentication, no provider writes, no credential material, no world mutation. `collage_disposable_release_grant.inspect` independently verifies an Ed25519 signature from a *caller-configured pinned issuer public key* over exact canonical grant claims. The signature binds realm, disposable environment, principal kind/subject, server + service UUID + world, request SHA256, artifact SHA256, release compare value, apply-only intent, TTL <= 5 minutes, nonce and idempotency key. No keys are checked into this repository. This module cannot issue grants.

This is **not** itself a permission to APPLY or to rollback. A subject claim inside a signed grant is not proof that the active invoking session is that subject. A nonce in an envelope is not consumed merely by reading it. A read-only provider JSON report is not an authenticated TrueNAS transaction. All these claims must be tested separately at the actual narrowly admitted actuator boundary.

## Safe next integration gate — ordered

1. Reuse an existing independently accepted principal/issuer authority; obtain verified *invoking peer* and bounded delegation, never infer identity from `principal.kind` or a claimed JSON grant alone. Pin issuer trust out of band, use short-lived keys/rotation discipline, and reject non-matching peer-to-grant subject. In RDTE generate keys only inside an ephemeral isolated test run; do not introduce a permanent COLLAGE issuer or secret manager.
2. Read real current native owner App config through the independently TLS-verified Go observer, six exact metadata fields, pinned guest version, service UUID/world identity, and actual candidate stage/hash. Do not use a caller-supplied replacement JSON blob.
3. At one existing world-controller actuator, atomically reserve **(realm, server, world, expected-current-release)** and **(issuer, nonce/idempotency key)** in one durable transaction / compare-and-swap. Deny races, duplicate grants and stale release. No in-memory or file-only optimistic replay simulation counts.
4. Under exact owned quiescence, reuse the accepted G3 native ZFS snapshot/stage/rollback mechanics, retaining injected-fault negative, independent world/backend observation and final zero-residue cleanup. Fail closed on ambiguous timeout or controller loss. Keep rollback independently scoped and authorized; `action=apply` grant alone cannot authorize it.
5. Exercise synthetic negatives on public CPU first; then one unique, serial, disposable/free-tier KVM guest on exact signed-source and empty heavy queue. Only receipts from real independent guest and issuer/nonce/CAS may promote authenticated APPLY. **Physical TrueNAS APPLY HOLD.**

## Expected receipts

`SIGNED_GRANT_SOURCE_PREFLIGHT_ONLY` proves a narrow signature and claimed source binding. Fields `principal_session_authenticated`, `provider_live_owner_observed`, `nonce_durably_consumed`, `release_cas_acquired`, `rollback_admitted`, and `mutation_authorized` are explicitly **false**. This enables safe source-negative iteration without the danger of accidental admission.

## Red/blue failure analysis

- **Red:** a valid signature with another principal, realm, service, world, candidate, stale release, or action; expired, not-yet-valid or broad token; altered signature/key; malformed nonce; duplicate request; a trusted read-only observer reporting an untrusted owner; controller death after reservation.
- **Blue:** cryptographically bound exact claims with an externally pinned trust root and zero mutation surface; separate signed-claim verification from session authentication, live provider owner check, durable CAS and actuator; no second manager or scheduler.
- **Residual blocker:** availability and qualification of an existing issuer-side signing interface, and a durable atomic compare-and-swap reservation coupled to G3. Neither has been independently established by this candidate. Do not issue a disposable 016 request solely on this preflight.
