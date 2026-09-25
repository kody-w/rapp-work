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
| `discover` | `roots` | `max_entries` |
| `scaffold` | `root`, `kind`, `owner_label`, `slug`, `world_id`, `mode` | `apply`, `plan`, `plan_sha256` |
| `update` | `root` | `apply`, `inverse_of`, `moves`, `plan`, `plan_sha256` |
| `migrate` | `source`, `target` | `apply`, `plan`, `plan_sha256` |

For effectful operations, omitting `apply` returns a plan. `apply: true`
requires both the complete plan object and its exact canonical SHA-256.

### Move plans

`update` with `moves` plans a `rapp-work-move-plan/1` instead of an SDK
integration update. Each move names a `source` and a `destination` relative to
`root`, for example unloading an agent file from the live top of `agents/`:

```python
planned = update(
    {
        "root": "/absolute/path/example",
        "moves": [
            {
                "source": "agents/example_agent.py",
                "destination": "agents/experimental/example_agent.py",
            }
        ],
    }
)
undo = update({"root": "/absolute/path/example", "inverse_of": planned["result"]["plan"]})
```

Apply either plan with `apply: true`, its complete plan, and its own exact
`plan_sha256`; `moves` and `inverse_of` are refused together with `apply`. A
move plan commits to each source's SHA-256, byte length, and mode. It never
carries file bytes, creates or removes a directory, or replaces a destination,
and it refuses hidden, identity, Organization, workspace-specification,
instruction, kernel (`basic_agent.py`), and SDK-owned paths, as well as paths
containing invisible, format, private-use, unassigned, or
filesystem-ignorable code points. Each move is one no-replace rename; if
another program changes or replaces the source while it moves, the move is
undone and refused with `REFUSE_FILE_RACE`, so no version of the file is ever
lost. The applied result has status `moved`. Applying a completed plan again
is refused with `REFUSE_PLAN_APPLIED`. An interrupted apply leaves
`.rapp-work/move-recovery.json`; applying the same plan again resumes it, and
other moves, inverses, and move plans are refused with
`REFUSE_RECOVERY_PENDING` or `REFUSE_RECOVERY_BINDING` until it finishes. An
ordinary SDK update may still run, so a pending move resumes after an SDK
upgrade, and a stored inverse stays valid across SDK updates. The marker is
locked while an apply runs, so a concurrent apply is refused with
`REFUSE_RECOVERY_BUSY`. Hosts without a descriptor-relative no-replace rename
(Linux `renameat2`, macOS `renameatx_np`) refuse moves with
`REFUSE_PLATFORM`.

The CLI equivalents are `rapp-work update --root ROOT --move SOURCE
DESTINATION` (repeatable) and `rapp-work update --root ROOT --inverse-of
PLAN_FILE`, applied with `--apply --plan PLAN_FILE --plan-sha256 HASH`.

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

`FileMove` and `MovePlan` (`rapp-work-move-plan/1`) live in `rapp_work.plans`;
they are not top-level exports.

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
- Plugin, skill, or Portable Neuron execution/install.
- Automatic repair of missing or modified SDK-owned files.
- Move plans that create or remove directories, move directories, leave their
  root, or carry a signature; repair of an ambiguous interrupted move.
- Race-prone effectful fallback on platforms without descriptor-relative
  no-follow primitives.
