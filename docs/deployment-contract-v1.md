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

The contract binds a realm UUID, environment (\`rdte\` or \`operations\`), operation \`plan\`, principal kind (\`human\`, \`automation\`, \`agent\`), declared issuer/subject, requested world/deployment and exact Minecraft backend/version, artifact origin Git commit, artifact kind/world ID/release/version/digest, expected current release, and a bounded \`rdte\` TTL.

Agent requests also declare sponsor/expiry/scope; the parser rejects expired declarations but **does not cryptographically authenticate them**. A live deployment actuator must obtain a verified external principal, enforce scope and issuer/audience binding, and reject unauthorized APPLY. Gameplay login and player membership through VIP are distinct from infrastructure control privileges.

Artifact contents are treated as opaque bytes. At this stage \`relative_path\` is an existing local regular file underneath an explicit artifact root. Traversal, symlinks, oversized files, an unexpected digest, cross-realm audience and mismatched world/runtime identity are refused. The parser never unpacks the file, follows remote URLs, sources shell code or uses site secrets. MCWORLD currently describes several provisional outputs; no single production-ready Two Rivers artifact archive format has been qualified.

## Source-only operator

From a checkout, after staging an artifact file in the chosen root and writing a request that matches the schema:

\`\`\`sh
python3 tools/collage_deploy_plan.py \
  --request /path/to/request.json \
  --artifact-root /path/to/staged-candidates
\`\`\`

A checked-in executable example uses an intentionally **non-playable**
source fixture and its exact Git-producing commit:

\`\`\`sh
python3 tools/collage_deploy_plan.py \
  --request examples/source-only-rdte.json --artifact-root .
\`\`\`

Exit 0 means **source-validated intent only**; exit 2 means fail-closed refusal. Both return machine-readable JSON. \`intent_sha256\` is intentionally independent of request ID and declared principal, allowing a human/CI/agent parity comparison for equivalent desired deployments. \`request_sha256\` preserves each complete caller request. Failure output is reason-coded and omits input values and secrets.

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
\`candidate_staged → candidate_hash_verified → quiesce → snapshot_current → activate_candidate → resume → health_check\`.
Failures restore/recheck according to the published failure policy. This request contract does not replace that transaction.

## Next live executable increments (do not promote source proof)

1. Admit a public-only Agent Dispatch nested TrueNAS request **separate** from the accepted standalone Paper T6 fixture; do not blindly rerun existing heavy proofs.
2. Translate an identical canonical request into a read-only provider observation and independently verify exact native App identity. Wire verified actor credentials only in the disposable guest; never accept client-supplied \`principal\` as authentication.
3. Complete CloudNet/App managed adoption and controller-loss tests in one serialized heavyweight guest. Existing Paper evidence proves Paper, not Two Rivers/vanilla.
4. Establish an **actual produced** Two Rivers/MCWORLD artifact with digest, compatibility and allowed contents from the artifact producer; reconcile its format before adding safe stage/activation.
5. Independently qualify vanilla Java 26.3, VanillaCord, Velocity and the requested game semantics. Use Gym protocol/state evidence; use a real stock client when UI/rendering claims matter.
6. Run human/CI/agent equivalent plans and scoped-actor negative tests, then a controlled stage/activate/rollback in a fresh real disposable world. Attach independent receipts; preserve the physical TrueNAS S8 APPLY HOLD.
7. Only then introduce a human-facing experience and operational release/promotion gates based on observed consumer needs, preferably as thin views over qualified upstream actions.

## Red-team acceptance

Refuse or classify as INCONCLUSIVE on wrong realm/audience; unauthenticated caller; expired or overbroad delegation; modified artifact; world ID/version mismatch; missing expected current release on live mutation; replayed mutation request; concurrent owners; direct world overwrite; cross-provider identity drift; unverified vanilla game behavior; unknown or failed cleanup.

A successful GitHub Action is **never** equivalent to a world/gameplay PASS. A read-only plan cannot authorize APPLY. Test actor privilege is never inferred from the label \`agent\`, \`automation\`, or \`human\`. No physical TrueNAS operations are permitted by this document.
