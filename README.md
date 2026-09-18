# RAPP Work SDK

**A typed, installable, offline-first SDK for `rapp-work/1`.**

| Contract | Value |
|---|---|
| Distribution | `rapp-work` |
| Import | `rapp_work` |
| Console | `rapp-work` |
| Module | `python -m rapp_work` |
| Business protocol | `rapp-work/1` |
| Workspace integration profile | `rapp-work-sdk/1` |

The repository still carries the existing RAPP/1, Private Hive, and Federation
profiles and their compatibility fixtures. The product entrypoint is now the
SDK, not a standards-only checkout or an embedded project skill.

## Install

```bash
python3 -m pip install .
rapp-work status
python3 -m rapp_work verify --root .
```

The runtime performs no network access by default. Core operation is standard
library only except for RAPP detached-signature verification, which uses the
declared `cryptography` dependency.

## Public JSON operations

The operation set is closed:

```text
status  verify  discover  scaffold  update  migrate
```

Every command emits one canonical JSON object. Unknown inputs and unsupported
behavior return a machine-readable refusal.

```bash
rapp-work status --root .
rapp-work verify --root .
rapp-work discover --root .
```

`status`, `verify`, and `discover` are read-only. Discovery records only bounded
metadata and hashes. It never imports or executes a plugin, skill, or Portable
Neuron.

### Plan, review, apply

`scaffold`, `update`, and `migrate` are plan-only by default:

```bash
rapp-work scaffold \
  --root "$PWD/example-workspace" \
  --kind workspace \
  --owner-label example \
  --slug example-workspace \
  --world-id example-world \
  > scaffold-plan.json
```

The result contains `result.plan` and `result.plan_sha256`. Apply requires the
complete saved envelope, an explicit flag, and that exact hash:

```bash
rapp-work scaffold \
  --root "$PWD/example-workspace" \
  --kind workspace \
  --owner-label example \
  --slug example-workspace \
  --world-id example-world \
  --apply \
  --plan scaffold-plan.json \
  --plan-sha256 '<exact result.plan_sha256>'
```

The same contract applies to:

```bash
rapp-work update --root /path/to/workspace
rapp-work migrate --source /path/to/old-workspace --target /path/to/successor
```

Migration is create-only. It preserves the source, binds recovery to exact
source authority bytes, and performs a complete receipt/inventory replay before
returning an existing migration as unchanged.

## Python API

```python
from rapp_work import ProfileRegistry, Workspace, scaffold, verify

profiles = ProfileRegistry.default()
profiles.verify()

planned = scaffold(
    {
        "root": "/absolute/path/example",
        "kind": "workspace",
        "owner_label": "example",
        "slug": "example",
        "world_id": "example-world",
        "mode": "solo",
    }
)

verification = verify({"root": "/absolute/path/example"})
```

Top-level public classes cover:

- exact RAPP/1 Frame validation through the pinned canonical implementation;
- `ProfileRegistry`;
- `Workspace` and pointer-only `Organization`;
- `HiveVector` and signed-authority high-water checks;
- `ReleasePlan`, `SignedRelease`, and bounded immutable release observations;
- `MigrationPlan` and `MigrationReceipt`;
- inert `PortableNeuron` inspection;
- local `FilesystemTransport` and credential-free local
  `PrivateGitTransport`.

Transport publication first builds a complete canonical `ReleasePlan`.
`publish(...)` requires that plan (or its `SignedRelease`) and its recomputed
SHA-256; an arbitrary digest is never sufficient.

See [the exact API surface](docs/API.md).

## Authority and safety

- RAPP/1 remains authoritative for RAPPIDs, canonicalization, Frames, hashes,
  signatures, Eggs, sealed artifacts, and signed registries.
- `RAPP1_PIN.json` pins accepted canonical RAPP/1 revision
  `591e014ad39e223b00ab343ae26e5d9a867ebeee` and the exact vendored
  `SPEC.md` / `rapp.py` bytes.
- `RAPP_WORK_PIN.json` pins the canonical `rapp-work/1` specification and
  schema at that same `kody-w/rapp-1` revision. The packaged canonical mirrors
  are `src/rapp_work/data/rapp-work-1-SPEC.md` and
  `src/rapp_work/data/rapp-work-1-schema.json`.
- Accepted Frames have exactly eleven keys:
  `spec`, `kind`, `stream_id`, `seq`, `utc`, `payload`, `payload_hash`,
  `frame_hash`, `prev`, `prev_wave`, `sig`.
- Root `SPEC.md` and `registry.json` remain untouched historical signed-estate
  evidence for the earlier `kody-w/rapp-work` pin. They are not the SDK's
  canonical `rapp-work/1` parent and their signatures are never synthesized or
  rewritten.
- SDK profile metadata explicitly says
  `workspace-integration-not-estate-authority`; another estate still needs its
  own owner-signed activation.
- Filesystem effects use descriptor-relative no-follow operations and refuse
  symlinks, hardlinked authority files, unsafe types, stale preconditions, and
  unmanaged collisions.
- Ambient Git, shell, cloud, SSH-agent, and provider credentials are not
  inherited.
- DOGG remains PII-free. GODD remains private. Transport is evidence, never
  authority.

## Compatibility

The historical workspace manager and Private Hive implementations remain in
their original project-skill locations so existing fixtures and copied
workspaces remain verifiable. The SDK exposes them through
`rapp_work.compat`; those modules are deprecated compatibility surfaces, not
the new product architecture.

The Private Hive compatibility transport now requires explicit GitHub privacy
evidence and an owner-only token file. Ambient `gh`, environment, credential
helper, and SSH-agent state is not inherited.

## Repository profiles

- [`RAPP_WORK_PIN.json`](RAPP_WORK_PIN.json) — accepted canonical
  `rapp-work/1` SDK parent.
- [`src/rapp_work/data/rapp-work-1-SPEC.md`](src/rapp_work/data/rapp-work-1-SPEC.md)
  and
  [`src/rapp_work/data/rapp-work-1-schema.json`](src/rapp_work/data/rapp-work-1-schema.json)
  — exact packaged canonical parent bytes.
- [`SPEC.md`](SPEC.md) — historical `rapp-work/1` bytes retained because the
  frozen signed estate registry commits to them.
- [`protocols/rapp-work-sdk/1`](protocols/rapp-work-sdk/1/SPEC.md) — package and
  workspace integration contract.
- [`protocols/rapp-hive/1`](protocols/rapp-hive/1/SPEC.md) — Private Hive.
- [`protocols/rapp-federation/1`](protocols/rapp-federation/1/SPEC.md) —
  consent-bound federation candidate.

## Validate and build

```bash
python3 tools/check.py
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy
python3 tools/release_inventory.py --check
python3 -m build
python3 tools/verify_package.py dist/*.whl dist/*.tar.gz
```

See [architecture](docs/ARCHITECTURE.md),
[migration](docs/MIGRATION.md), and [release qualification](docs/RELEASE.md).

MIT.
