# COLLAGE deployment-intent v1: three audiences, two environments

Authority: [collage-private#3](https://github.com/SupraCraft/collage-private/issues/3).
Parent manager/TrueNAS qualification: [collage-private#1](https://github.com/SupraCraft/collage-private/issues/1).
Related: [Minecraft deployment model](https://github.com/SupraCraft/mc-server-images/blob/main/docs/deployment-model-v1.md),
[world activation transaction](https://github.com/SupraCraft/mc-server-images/blob/main/spec/minecraft-world-activation-transaction-v1.json),
[MCSTORY/MCWORLD/MCRUN draft](https://github.com/SupraCraft/mc-structure-foundry-private/blob/main/spec/MCSTORY-MCWORLD-MCRUN-v0.1-DRAFT.md),
[VIP enrollment/realm model](https://github.com/SupraCraft/velocity-identity-private/issues/6).

## Exact status and purpose

This slice introduces an executable **read-only source contract and plan**, not a functional deployment operator, identity verifier, authorization service, TrueNAS controller, world-format validator, or Minecraft gameplay proof. It does not call a network endpoint, grant permissions, write world data, provision resources, or mutate TrueNAS. Its positive verdict is **SOURCE_VALIDATED**, not PASS for a real world/runtime.

The same request/intent semantics must work for human tools, unattended CI, and delegated agents. We do not create a second controller or scheduler; future adapters may wrap qualified CloudNet, Foundry and the independent world controller. The caller's declared principal and claimed scopes are **untrusted claims**; source validation is not authentication or permission.

## Canonical contract

- JSON Schema: [spec/deployment-request-v1.schema.json](../spec/deployment-request-v1.schema.json)
- Dependency-free parser/validator/read-only planner: [tools/collage_deploy_plan.py](../tools/collage_deploy_plan.py)
- Source/negative qualification: [tests/test_collage_deploy_plan.py](../tests/test_collage_deploy_plan.py)
- Public cheap CI: [qualify-deployment-contract.yml](../.github/workflows/qualify-deployment-contract.yml)

The contract binds a realm UUID, environment (`rdte` or `operations`), operation `plan`, principal kind (`human`, `automation`, `agent`), declared issuer/subject, requested world/deployment and exact Minecraft backend/version, artifact origin Git commit, artifact kind/world ID/release/version/digest, expected current release, and a bounded `rdte` TTL.

Agent requests also declare sponsor/expiry/scope; the parser rejects expired declarations but **does not cryptographically authenticate them**. A live deployment actuator must obtain a verified external principal, enforce scope and issuer/audience binding, and reject unauthorized APPLY. Gameplay login and player membership through VIP are distinct from infrastructure control privileges.

Artifact contents are treated as opaque bytes. At this stage `relative_path` is an existing local regular file underneath an explicit artifact root. Traversal, symlinks, oversized files, an unexpected digest, cross-realm audience and mismatched world/runtime identity are refused. The parser never unpacks the file, follows remote URLs, sources shell code or uses site secrets. MCWORLD currently describes several provisional outputs; no single production-ready Two Rivers artifact archive format has been qualified.

## Source-only operator

From a checkout, after staging an artifact file in the chosen root and writing a request that matches the schema:

```sh
python3 tools/collage_deploy_plan.py \
  --request /path/to/request.json \
  --artifact-root /path/to/staged-candidates
```

A checked-in executable example uses an intentionally **non-playable**
source fixture and its exact Git-producing commit:

```sh
python3 tools/collage_deploy_plan.py \
  --request examples/source-only-rdte.json --artifact-root .
```

Exit 0 means **source-validated intent only**; exit 2 means fail-closed refusal. Both return machine-readable JSON. `intent_sha256` is intentionally independent of request ID and declared principal, allowing a human/CI/agent parity comparison for equivalent desired deployments. `request_sha256` preserves each complete caller request. Failure output is reason-coded and omits input values and secrets.

No direct TrueNAS APPLY, public world-serving link, or operational promotion is available in this version.

## Authority boundaries

| Role | Owns | Excludes |
| --- | --- | --- |
| MCSTORY/MCWORLD/MCRUN | World/story/gameplay artifact compilation and trace demands | Runtime or infrastructure permission |
| COLLAGE or adopted CloudNet adapter | Desired deployment composition, provider-neutral inventory, read-only plans, eventual bounded reconciliation | World compilation/promotion policy; forced server dependence |
| TrueNAS App Foundry | Native app materialization and provider lifecycle | Two Rivers semantics and world release policy |
| World controller | Artifact lineage, candidate selection, release approval, world rollback policy | Generic container control |
| Narrow world agent | Admitted save/quiesce/hash/stage/snapshot/activate/restore/resume | Docker socket, IAM, approval policy |
| VIP and enrollment issuers | Verified game login, realm-bound membership, human/workload/agent admission | Infrastructure deployment authorization |
| MC Bot Gym / stock client | Independent gameplay/transport and presentation verification | Deployment state or approval |

World activation must follow the already published transaction:
`candidate_staged → candidate_hash_verified → quiesce → snapshot_current → activate_candidate → resume → health_check`.
Failures restore/recheck according to the published failure policy. This request contract does not replace that transaction.

## First native TrueNAS read-only join (implementation, not live acceptance)

The v1 source contract may optionally include `target.service_id` (stable RFC 4122 version-4 UUID). A provider-bound request **must** include it. The existing six native App ownership metadata fields then bind service UUID, world, manager/fleet and managed/schema markers. `realm_id` is site-context-bound; no claim is made that those six fields cryptographically bind a realm.

[tools/collage_native_readback.py](../tools/collage_native_readback.py) is a thin executable wrapper around the *existing* repository-owned, TLS-verified `tools/truenas-readonly-probe` Go source. It validates the local artifact/request, then **itself invokes** the read-only Go `app.query` probe and compares live returned App metadata with the request and admitted site tuple.

On an authorized **disposable** test boundary with Go 1.25 and a verified TrueNAS TLS trust root (for example, explicitly installed trust or a pinned `SSL_CERT_FILE`), pass a scoped **read-only** TrueNAS API credential through the existing process environment, never an argument or issue:

```sh
python3 tools/collage_native_readback.py \
  --request /path/to/actual-readonly-request.json \
  --artifact-root /path/to/staged-artifact \
  --host <isolated-disposable-truenas-host> \
  --username <scoped-readonly-username> \
  --trusted-realm-id <pinned-local-realm-uuid> \
  --manager-id manager-rdte --fleet-id rdte
```

Its `PROVIDER_READBACK_MATCH` means only that **this process ran the approved authenticated/TLS-verified native App read-only probe and matched App ownership state**. It does not prove game version/protocol, world artifact format/deployment, CloudNet adoption, player/agent authorization, cryptographic realm binding, or physical host qualification. Under no condition does this wrapper issue TrueNAS mutations. A supplied JSON document alone cannot produce a runtime PASS; synthetic documents used in unit tests test **policy matching only**.

This runtime join **has not yet been executed in the disposable KVM guest**. Its real-system acceptance is tracked in [public COLLAGE issue #19](https://github.com/SupraCraft/collage/issues/19). The checked-in example fixture is deliberately non-playable; it must not be used to infer a successful Two Rivers deployment.

## Exact native vanilla26.3 source-to-owner binding (opt-in, source-only)

Public disposable [Agent Dispatch KVM run 38489327594](https://github.com/SemperSupra/agent-dispatch/actions/runs/38489327594) independently accepted **TrueNAS 25.04.2.6 / native community Minecraft 1.15.30 / Java25 vanilla26.3 protocol777**, App `rdte-t6-minecraft-vanilla-263`, source owner service UUID `11111111-1111-4111-8111-111111111111`, world `lantern-rdte`, with native App lifecycle, world retain/reinstall, and zero residue. That run did **not** stage the Lantern restoration datapack through COLLAGE and did not execute this read-only Go readback adapter.

The pinned Go websocket client `github.com/deevus/truenas-go v0.5.0` reports `ws.Version().Raw` directly from the middleware `system.version` response. For the exact native target this is `TrueNAS-25.04.2.6`, **not** the unprefixed `25.04.2.6` in the COLLAGE request. The native readback comparison therefore insists on the complete raw value first and only then emits the normalized source target version `25.04.2.6`. Other prefixes, numeric-only raw reports and prefix/suffix drift fail closed; this is not fuzzy version matching.

The existing real-artifact consumer now accepts optional `--native-target-profile vanilla263-250426`. This binds its **already verified real ZIP**, from exact producer `SupraCraft/mc-server-images@7f888b5829f4e5576d5ce512d86327348c43f01e`, to that native App's **expected identity** within the same human/automation/agent source-plan semantics. Without the flag, the prior source-only `lantern-rdte-candidate` plan remains unchanged. It refuses a different world/release/producer instead of guessing. The existing `collage_native_readback.py` comparison also refuses wrong TrueNAS 25.04.2.6, native App catalog version 1.15.30, expected service/world ID, or missing container when this native deployment ID is requested; legacy Paper controls are unchanged.

```sh
python3 tools/consume_vanilla_datapack_source.py \
  --manifest /path/to/lantern-restoration-26.3.json \
  --artifact /path/to/lantern-restoration-26.3.zip \
  --artifact-root /path/to \
  --native-target-profile vanilla263-250426
```

**This is still SOURCE_ARTIFACT_AND_INTENT_PARITY_VALIDATED**, not live provider readback. Native App identity is an expected source binding; a supplied sanitized provider document in tests cannot prove live state. Next live gate must invoke the existing **independent authenticated/TLS-verified read-only Go probe** during a separately admitted disposable guest lifecycle and compare actual App ownership, then run separately admitted world activation and gameplay tests. Never promote source actor claims into authorization or deploy/activate the world based only on this output. No physical TrueNAS APPLY.

## Next live executable increments (do not promote source proof)

1. Admit a public-only Agent Dispatch nested TrueNAS request **separate** from the accepted standalone Paper T6 fixture; do not blindly rerun existing heavy proofs.
2. Translate an identical canonical request into a read-only provider observation and independently verify exact native App identity. Wire verified actor credentials only in the disposable guest; never accept client-supplied `principal` as authentication.
3. Complete CloudNet/App managed adoption and controller-loss tests in one serialized heavyweight guest. Existing Paper evidence proves Paper, not Two Rivers/vanilla.
4. Establish an **actual produced** Two Rivers/MCWORLD artifact with digest, compatibility and allowed contents from the artifact producer; reconcile its format before adding safe stage/activation.
5. Independently qualify vanilla Java 26.3, VanillaCord, Velocity and the requested game semantics. Use Gym protocol/state evidence; use a real stock client when UI/rendering claims matter.
6. Run human/CI/agent equivalent plans and scoped-actor negative tests, then a controlled stage/activate/rollback in a fresh real disposable world. Attach independent receipts; preserve the physical TrueNAS S8 APPLY HOLD.
7. Only then introduce a human-facing experience and operational release/promotion gates based on observed consumer needs, preferably as thin views over qualified upstream actions.

## Red-team acceptance

Refuse or classify as INCONCLUSIVE on wrong realm/audience; unauthenticated caller; expired or overbroad delegation; modified artifact; world ID/version mismatch; missing expected current release on live mutation; replayed mutation request; concurrent owners; direct world overwrite; cross-provider identity drift; unverified vanilla game behavior; unknown or failed cleanup.

A successful GitHub Action is **never** equivalent to a world/gameplay PASS. A read-only plan cannot authorize APPLY. Test actor privilege is never inferred from the label `agent`, `automation`, or `human`. No physical TrueNAS operations are permitted by this document.
