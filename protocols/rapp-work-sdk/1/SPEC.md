# rapp-work-sdk/1

`profile_id: rapp-work-sdk/1`

This profile defines the installable, typed, offline-first integration surface
for the canonical `rapp-work/1` bytes pinned by
[`RAPP_WORK_PIN.json`](../../../RAPP_WORK_PIN.json). It is subordinate to the
exact pinned `rapp/1` parent and does not alter RAPPID identity,
canonicalization, the frozen eleven-key Frame envelope, hashes, signatures,
Eggs, sealed artifacts, or registry authority. Root `SPEC.md` is distinct
historical signed-estate evidence and is not the SDK parent specification.

## 1. Names

- Distribution: `rapp-work`
- Python import: `rapp_work`
- Console command: `rapp-work`
- Module command: `python -m rapp_work`
- Parent business protocol: `rapp-work/1`
- Workspace integration profile: `rapp-work-sdk/1`

Implementations MUST NOT substitute a repository name, Python package name, or
transport locator for any protocol identifier.

## 2. Public JSON operations

The public operation set is closed:

`status`, `verify`, `discover`, `scaffold`, `update`, `migrate`.

`status`, `verify`, and `discover` are read-only. They MUST NOT create a target,
cache, lock, registry, credential, network connection, or recovery record.

`scaffold`, `update`, and `migrate` produce an immutable plan by default. An
effect requires all of:

1. an explicit apply request;
2. the complete reviewed plan;
3. the exact SHA-256 of the plan's canonical JSON; and
4. successful replay of every current precondition before the first write.

Unknown operation inputs and unsupported capabilities MUST be refused before
effects. Output is canonical I-JSON with no floating-point values.

## 3. Offline and credential boundary

No operation uses a network by default. Network locations, environment
credentials, Git credential helpers, SSH agents, ambient cloud sessions, and
provider CLI logins are not inherited as authority.

Filesystem and local private-Git transports are replaceable evidence carriers.
A hosted private-Git adapter requires a separate explicit credential/evidence
provider and remains outside the default operation path.

## 4. Filesystem boundary

Authority-bearing reads and all writes use descriptor-relative no-follow
operations. Symlinks, hardlinked authority files, path traversal, device
entries, FIFOs, sockets, unmanaged collisions, and changed preconditions are
refused.

Create-only means no existing destination is replaced. SDK updates may replace
only files named in the prior SDK-owned inventory and only when their exact
current SHA-256 equals the plan precondition.

## 5. RAPP/1 wrapper

The SDK loads the exact implementation pinned by `RAPP1_PIN.json` and verifies
the pinned implementation and specification hashes before use.

A RAPP/1 Frame accepted by the SDK has exactly:

`spec`, `kind`, `stream_id`, `seq`, `utc`, `payload`, `payload_hash`,
`frame_hash`, `prev`, `prev_wave`, `sig`.

The SDK delegates canonical particle, wave, chain, stream, and signature checks
to that pinned implementation. Additive SDK metadata never enters the Frame
envelope.

### 5.1 Registry authority and owner succession

`RAPP1_REGISTRY_PIN.json` pins the exact `rapp_registry.py` of the same
accepted `kody-w/rapp-1` revision named by `RAPP1_PIN.json`. The SDK verifies
those bytes, and binds their `rapp` import to the already verified parent,
before use.

`rapp_work.registry` verifies a signed `rapp/1-registry` document read-only.
The caller supplies the entries member name, the out-of-band anchor RAPPID and
SPKI, a trusted tombstone issuance resolver keyed by the exact signed
tombstone's particle hash, and the registry state it retained from its last
verification. None of these is read from the document. The pinned reference
decides every section 13.3 entry, owner tenure, lifecycle signature, and
time-scoped key retirement. The SDK additionally requires that:

1. the anchor is the current estate owner or a predecessor reachable only
   through `case:"rotation"` re-anchor records; an owner `compromise` record
   requires a newly distributed out-of-band anchor (RAPP/1 sections 13.1 and
   13.2);
2. every owner transition is a `rotation` or `compromise` record;
3. the current estate owner key is registered and never deprecated,
   superseded, or tombstoned;
4. key retirement matches the SPKI tail, so a renamed RAPPID cannot revive a
   superseded or tombstoned key;
5. an anchor that is not the current estate owner is accepted only together
   with retained state: the caller's last verified registry, which also
   carries the persisted sequence floor and same-sequence commitment;
6. a registry verified after retained state keeps every retained `re-anchor`
   and `tombstone` entry byte for byte and extends, never rewrites, the
   retained owner lineage, so no later registry, whoever signs it, can undo a
   succession or a revocation;
7. a `compromise` re-anchor that is new since the retained state appears in a
   registry exactly one sequence later, together with a new tombstone for its
   `old_rappid` (the RAPP/1 section 6.3 same-append rule; a single snapshot
   cannot show it, so a first verification relies on the trusted issuance
   context); and
8. a registry lineage is contiguous, and each snapshot is verified with the
   previous one as its retained state.

A verified registry reports the owner in effect at an artifact time and
supplies a signature verifier for `validate_frame` and `validate_chain`. This
is verification only. The SDK never mints keys or signs, appends, or rewrites a
registry, re-anchor, or tombstone, and adds no JSON operation.

## 6. Profiles

`ProfileRegistry` records immutable descriptors for the pinned parent,
`rapp-work/1`, this integration profile, `rapp-hive/1`, and
`rapp-federation/1`. A descriptor commits to exact specification and schema
bytes. The `rapp-work/1` descriptor resolves the canonical packaged mirrors
named by `RAPP_WORK_PIN.json`; it does not resolve root `SPEC.md`.

This integration profile is package-qualified metadata. It does not silently
add a signed activation entry to the frozen repository registry or another
estate.

## 7. Workspace and Organization

A Workspace has one existing or mint-once RAPPID and one hard `world_id`.
Scaffolding creates a new directory atomically. Updating is additive for legacy
workspaces and limited to SDK-owned integration files for SDK workspaces.

An Organization is a pointer-only routing object. Its registry may contain only
workspace RAPPID, lexical path, world, mode, name, and active state. It MUST NOT
copy workspace content, credentials, prompts, histories, or native provider
stores.

## 8. Hive vectors

A verified Hive vector contains the authenticated registry position and
complete retained hash lineage for every represented stream. High-water
comparison refuses:

- lower registry or stream sequence;
- same-sequence different hash;
- missing retained streams; and
- a higher position whose lineage does not contain the retained head at its
  exact prior sequence.

Git ancestry and transport delivery do not replace this signed-authority check.

## 9. Releases

`ReleasePlan` commits to its operation, target, subject, preconditions, and
exact output bytes. `SignedRelease` binds the complete canonical plan and plan
SHA-256 to a keyed RAPPID through a detached RAPP/1 JWS.

Release observations are immutable, content addressed, bounded, and
append-only. Reaching the bound refuses another observation; it does not erase
history or silently roll a checkpoint forward.

## 10. Migration

A `MigrationPlan` is source-bound and create-only. It preserves the source and
creates a successor integration workspace or Organization without rewriting
the source identity, Frames, keys, histories, Private Hive state, plugins,
skills, or neurons.

Before a first write, apply rechecks the complete plan, exact plan SHA-256,
source filesystem identity, allowlisted authority-byte commitments, target
absence, and any recovery marker.

If a completed target exists, the implementation performs a full completed
replay preflight before any write: receipt shape, plan/source binding, target
identity, and every receipt inventory byte MUST match. A valid replay is
read-only and returns unchanged. An invalid replay is refused.

Interrupted staging can resume only from a marker bound to the exact plan,
source, and target. Foreign or ambiguous staging is never repaired or deleted.

## 11. Inert compatibility

Portable Neurons, discovered plugins, and project skills are untrusted data.
Discovery may parse bounded metadata and Python syntax, but MUST NOT import,
execute, install, enable, or grant authority to discovered code.

The historical workspace-manager and Private Hive implementations remain
available only through explicit SDK compatibility wrappers and deprecated
legacy paths. Those wrappers do not broaden their profile claims.

## 12. Refusals

In the list below, owner rotation means performing it: minting keys, or
signing or appending a registry, re-anchor, or tombstone record. The SDK also
refuses owner succession that does not descend from the out-of-band anchor
through signed rotation or that does not extend the caller's retained registry
state. Read-only verification of lawful RAPP/1 owner succession (section 5.1)
is supported.

Unsupported sharing, public Git, credential inheritance, implicit apply,
unknown JSON members, parent-authority changes, plugin execution, neuron
execution, source deletion, owner rotation, and unverified Hive rollback/fork
acceptance are explicit refusals.
