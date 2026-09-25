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
| `update` | `root` | `apply`, `plan`, `plan_sha256` |
| `migrate` | `source`, `target` | `apply`, `plan`, `plan_sha256` |

For effectful operations, omitting `apply` returns a plan. `apply: true`
requires both the complete plan object and its exact canonical SHA-256.

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

## Owner succession verification

`rapp_work.registry` is an explicit read-only submodule, not part of the
top-level stable API or the JSON operation set:

```python
from rapp_work.registry import verify_registry, verify_registry_lineage

verified = verify_registry(
    registry_bytes,
    entries_member="entries",
    anchor_rappid=anchor_rappid,        # distributed out of band
    anchor_spki_der=anchor_spki_der,
    tombstone_issued_at=resolver,       # trusted: particle hash -> issuance UTC
    retained=previous,                  # last VerifiedRegistry or its to_dict() record
)
verified.owner_at(utc)                  # RAPP/1 section 13.2 owner in effect
verified.signer_acceptable(kid, utc)    # key retirement matched by SPKI tail
verified.signature_verifier()           # for validate_frame / validate_chain
verified.to_dict()                      # persist; pass back as retained next time
verify_registry_lineage(documents, ..., retained=None)
pinned_registry_reference()
```

It delegates to the `rapp_registry.py` bytes pinned by
`RAPP1_REGISTRY_PIN.json`. An anchor extends to a successor owner only through
signed `rotation` records, and only together with `retained`, the caller's
last verified registry. `retained` also carries the persisted sequence floor
and same-sequence commitment, and a later registry must keep every retained
`re-anchor` and `tombstone` entry and extend the retained owner lineage. A new
`compromise` re-anchor must arrive one sequence after the retained state,
together with its tombstone. Owner compromise recovery requires a newly
distributed anchor. A lineage must be contiguous. Refusal codes are
`REFUSE_REGISTRY`, `REFUSE_REGISTRY_ENTRY`, `REFUSE_REGISTRY_ANCHOR`,
`REFUSE_REGISTRY_SUCCESSION`, `REFUSE_REGISTRY_ISSUANCE`,
`REFUSE_REGISTRY_AUTHORITY`, `REFUSE_REGISTRY_OWNER`,
`REFUSE_REGISTRY_ROLLBACK`, `REFUSE_REGISTRY_FORK`,
`REFUSE_REGISTRY_LINEAGE`, `REFUSE_REGISTRY_TIME`, and `REFUSE_INPUT_SHAPE`.
The module never signs or writes anything.

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
- SharePoint, public Git, performing owner rotation or compromise recovery,
  key release, sealing, topology mutation, and Federation activation. Owner
  succession is verified read-only through `rapp_work.registry`.
- Plugin, skill, or Portable Neuron execution/install.
- Automatic repair of missing or modified SDK-owned files.
- Race-prone effectful fallback on platforms without descriptor-relative
  no-follow primitives.
