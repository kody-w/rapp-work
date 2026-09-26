# Public API

## Constants

```python
DIST_NAME = "rapp-work"
IMPORT_NAME = "rapp_work"
COMMAND_NAME = "rapp-work"
PROTOCOL_ID = "rapp-work/1"
WORKSPACE_PROFILE_ID = "rapp-work-sdk/1"
SDK_VERSION = "1.0.0"
PUBLIC_OPERATIONS = ("status", "verify", "discover", "scaffold", "update", "migrate")
```

## JSON operations

All functions return the same seven-key result envelope.

```python
execute(operation, inputs=None)
status(inputs=None)
verify(inputs=None)
discover(inputs)
scaffold(inputs)
update(inputs)
migrate(inputs)
```

### Inputs

| Operation | Required | Optional |
|---|---|---|
| `status` | — | `root` |
| `verify` | — | `root` |
| `discover` | `roots` | `agents`, `max_entries` |
| `scaffold` | `root`, `kind`, `owner_label`, `slug`, `world_id`, `mode` | `apply`, `plan`, `plan_sha256` |
| `update` | `root` | `apply`, `plan`, `plan_sha256` |
| `migrate` | `source`, `target` | `apply`, `plan`, `plan_sha256` |

For effectful operations, omitting `apply` returns a plan. `apply: true`
requires both the complete plan object and its exact canonical SHA-256.

A `discover` result groups its inert records in `skills`, `plugins`, and
`neurons`, and lists `refusals`. With `agents: true` it also reads Brainstem
single-file agents (`*_agent.py`) and adds an `agents` member, possibly empty,
of inert `rapp-work-discovered-agent/1` records; see `rapp-work-sdk/1` §11.1.
Discovery parses Python source only after a token-level measure shows that it
is within fixed nesting and cost bounds, and one call spends at most a fixed
parse budget on agents (§11.2).

## Typed models

```python
RappFrame
ProfileDescriptor
ProfileRegistry
Workspace
Organization
FileAction
ReleasePlan
SignedRelease
HiveStreamPosition
HiveVector
HiveHighWater
ReleaseObservation
ReleaseObservationStore
MigrationPlan
MigrationReceipt
PortableNeuron
FilesystemTransport
PrivateGitTransport
```

Both transport types expose `publication_plan(...)`. `publish(...)` retains its
existing effect inputs and additionally requires that complete `ReleasePlan`
(or a `SignedRelease` containing it) plus the recomputed `plan_sha256`.
Standalone 64-hex strings are not publication authorization.

## RAPP/1 helpers

```python
FRAME_KEYS
build_frame(...)
validate_frame(...)
validate_chain(...)
pinned_parent()
verify_hive_high_water(current, retained)
```

`build_frame` and `validate_frame` delegate to the exact implementation named
by `RAPP1_PIN.json`; the SDK does not reimplement particle/wave semantics.

`ProfileRegistry.default()` separately binds `rapp-work/1` to the exact
specification and schema named by `RAPP_WORK_PIN.json`. Source-estate
verification reports that SDK parent pin independently from the historical
signed `rapp-work/1` entry committed by root `registry.json`.

## Compatibility namespace

`rapp_work.compat` intentionally exports only:

```python
workspace_manager()
private_hive_prepare()
private_hive()
run_private_hive_cli(argv, allow_network=False)
```

These emit `DeprecationWarning` and wrap the preserved historical code. They
are not included in the top-level stable API.

The Private Hive CLI wrapper parses the complete legacy command with long
option abbreviation disabled and refuses every hosted channel before loading
the compatibility implementation unless `allow_network=True`.

## Explicitly deferred

- Core hosted-Git network transport. The core adapter is local private Git;
  historical GitHub publication requires explicit compatibility inputs.
- SharePoint, public Git, owner rotation, key release, sealing, topology
  mutation, and Federation activation.
- Plugin, skill, Portable Neuron, or single-file agent execution, loading, or
  install.
- Automatic repair of missing or modified SDK-owned files.
- Race-prone effectful fallback on platforms without descriptor-relative
  no-follow primitives.
