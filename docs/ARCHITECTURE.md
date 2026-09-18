# Architecture

## Qualified front door

The product is the `rapp-work` Python distribution:

```text
rapp-work CLI / python -m rapp_work
              |
       closed JSON API
              |
  typed plans, models, verification
              |
  no-follow filesystem / offline transports
              |
 pinned canonical RAPP/1 + preserved profiles
```

The project-skill implementations remain available only as compatibility
payloads. New product behavior belongs in `src/rapp_work`.

## Authority layers

1. **Pinned RAPP/1** — `RAPP1_PIN.json` authenticates exact `SPEC.md` and
   `rapp.py` bytes at accepted canonical commit `591e014`. `rapp_work.rapp1`
   checks both hashes before exposing the wrapper.
2. **Canonical SDK parent** — `RAPP_WORK_PIN.json` commits to the accepted
   `rapp-work/1` specification and schema under `protocols/rapp-work/1` in that
   same canonical `kody-w/rapp-1` revision. `ProfileRegistry` resolves exact
   packaged mirrors of those bytes.
3. **Historical signed estate** — root `SPEC.md` and the existing signed
   registry are preserved evidence for the earlier `kody-w/rapp-work`
   adoption. They are verified, but they do not supply the SDK parent bytes
   and are not re-signed.
4. **SDK integration** — `rapp-work-sdk/1` defines packaging, operations,
   plan/apply semantics, inert discovery, and workspace integration. It does
   not edit the frozen registry.
5. **Workspace/Hive/Federation** — existing profiles and fixtures remain
   independently verifiable.

## Module map

| Module | Responsibility |
|---|---|
| `rapp_work.api` | Six closed JSON operations and stable result envelopes |
| `rapp_work.rapp1` | Exact pinned canonical Frame/canonicalization wrapper |
| `rapp_work.profiles` | Canonical SDK parent descriptors plus distinct historical source-estate verification |
| `rapp_work.workspace` | Workspace and pointer-only Organization models/templates |
| `rapp_work.plans` | `FileAction`, `ReleasePlan`, and `SignedRelease` |
| `rapp_work.hive` | Complete-lineage Hive vectors and high-water verification |
| `rapp_work.release` | Bounded immutable release observations |
| `rapp_work.migration` | Create-only source-bound plans, receipts, and replay |
| `rapp_work.discovery` | Bounded inert skill/plugin/neuron metadata discovery |
| `rapp_work.neuron` | Portable Neuron syntax/metadata inspection as data |
| `rapp_work.transports` | Private filesystem and local private-Git CAS adapters |
| `rapp_work.compat` | Explicit deprecated wrappers over historical implementations |

## Stable JSON

Outputs use the pinned parent canonicalizer over I-JSON values. Top-level
operation envelopes have exactly:

```text
operation, profile, protocol, refusal, result, schema, status
```

Inputs use operation-specific closed key sets. Unknown keys, floats, duplicate
JSON members, implicit effects, and unsupported operations are refusals.

## Plan/apply state machine

```text
observe read-only state
        |
    build plan
        |
 canonical SHA-256
        |
 owner review/save
        |
 explicit apply + complete plan + exact SHA-256
        |
 replay every precondition
        |
 effects / explicit refusal
```

Scaffold and migration activate staging directories with an atomic no-replace
primitive (`renameat2(RENAME_NOREPLACE)` on Linux or
`renameatx_np`/`renamex_np(RENAME_EXCL)` on macOS); unsupported hosts refuse.
Update replaces only prior SDK-owned bytes and uses an exact plan-bound
recovery marker. Migration uses a retained source-bound marker and completed
receipt.

## Filesystem model

Effectful paths use descriptor-relative `openat`-style operations with
`O_NOFOLLOW`. Authority files must be regular, single-link files. Private state
uses mode 0700 directories and mode 0600 files on POSIX. Unsupported hosts
refuse rather than silently falling back to a race-prone path API.

## Transport model

`FilesystemTransport` stores immutable data plus one pointer CAS.
`PrivateGitTransport` operates only on an explicitly supplied local Git
repository and constructs a minimal environment containing no home directory,
Git credential helper, cloud token, SSH agent, or inherited provider session.
Every publication reconstructs a complete canonical `ReleasePlan`, matches all
files, pointers, refs, and timestamps, and checks its recomputed digest before
the first transport write.

Hosted private Git remains available through the historical Private Hive
compatibility layer only with explicit privacy evidence and an explicit
owner-only token file.

## Inert extension model

Discovery can read bounded regular files, parse closed plugin JSON, parse Python
syntax, and extract literal metadata. It never imports, installs, enables, or
executes discovered code. A copied Portable Neuron is mode-0600 data.
