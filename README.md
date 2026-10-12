# COLLAGE

**Composable Orchestration Layer for Lifecycle-Aware Game Environments**

COLLAGE is an experimental SupraCraft project exploring a thin composition and reconciliation layer for Minecraft server environments.

The central idea under test is simple:

> A Minecraft server managed as part of a fleet should remain the same independently useful server application that could have been installed and operated without the manager.

The initial research target is TrueNAS Apps, with persistent worlds treated independently from disposable server runtimes. The project is intentionally being developed through falsifiable experiments before broader implementation claims are made.

Current status: **experimental / candidate**.

Private RDTE authority: `SupraCraft/collage-private`.

## Deployment intent: humans, automation and agents

The first deployment-facing interface is a shared, strictly read-only source planner,
not a working Minecraft deployment controller. It validates immutable artifact
bytes, declared realm/world/runtime identity and scoped request shape for all
three principal types. The same request can later be consumed by qualified
TrueNAS/CloudNet world-runtime and independent world-activation adapters.

Runnable source-only example from a checkout:

```sh
python3 tools/collage_deploy_plan.py \
  --request examples/source-only-rdte.json --artifact-root .
```

A separate [native TrueNAS read-only join](tools/collage_native_readback.py)
invokes the existing TLS-verified Go App probe and matches exact provider-neutral
App ownership against a service-UUID-bound request and trusted site context.
It has not yet been qualified in a live disposable guest; track that acceptance
in [COLLAGE #19](https://github.com/SupraCraft/collage/issues/19).

The example intentionally references a **non-playable fixture**. A green
`SOURCE_VALIDATED` response does *not* authenticate a principal, verify a
Minecraft artifact format, touch a TrueNAS host, or authorize APPLY.

See [deployment contract v1](docs/deployment-contract-v1.md), the
[request schema](spec/deployment-request-v1.schema.json), and
[COLLAGE consumer authority](https://github.com/SupraCraft/collage-private/issues/3).
