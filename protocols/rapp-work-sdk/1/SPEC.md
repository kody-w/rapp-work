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

`update` also plans file moves (§4.1) through two optional members of its
closed input: `moves` plans a move plan, and `inverse_of` returns the exact
inverse of a supplied move plan (§4.3). The two are mutually exclusive, are
accepted only without `apply`, and are accepted by no other operation. An
`update` apply whose plan has schema `rapp-work-move-plan/1` is applied under
§4.2. Every other `update` plan remains a `rapp-work-release-plan/1`, whose
shape, hash, and meaning are unchanged.

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

A move creates its destination under the same create-only rule and removes its
source name only after the destination is durable and verified. A move
relocates bytes; it is not the source deletion refused by §12.

### 4.1 Move plans

A move plan relocates existing regular files inside one Workspace or
Organization root. It carries hashes, not bytes. Its schema is
`rapp-work-move-plan/1`, a closed object with exactly `schema`, `protocol`
(`rapp-work/1`), `profile` (`rapp-work-sdk/1`), `network` (`false`),
`operation` (`update`), `target`, `subject`, `preconditions`, and `moves`:

- `target` is the root's absolute lexical path.
- `subject` is exactly the root identity's `kind` (`workspace` or
  `organization`), `rappid`, and `world_id`.
- `preconditions` is exactly `identity_sha256` (of `rappid.json`),
  `managed_sha256` (of `.rapp-work/managed.json`), and `root_identity` (the
  root's `device`, `inode`, and permission `mode`).
- `moves` holds 1 to 64 move actions sorted by `source`. Each is exactly
  `operation` (`move`), `source`, `destination`, `sha256`, `bytes`, and `mode`
  (the source's permission bits, 0 to 0o777). Sources total at most 64 MiB.

The plan SHA-256 is the SHA-256 of the plan's canonical JSON. A
`rapp-work-release-plan/1` never contains a move, and a move plan never
contains a create or replace action.

Planning refuses unless all of the following hold. A first apply replays every
one before its first write. A resumed apply (§4.2) replays the same checks,
except that it expects its own move marker and checks each file against the
recovery states instead of 7 and 8.

1. The root is reached without symlinks, its identity is a Workspace or
   Organization, and its SDK integration verifies: the SDK-owned inventory
   exists and matches, and `.rapp-work/sdk.json` equals the qualified record.
   A legacy workspace first adopts the SDK through an ordinary update plan.
2. No update or move recovery marker is pending.
3. Each `source` and `destination` is a canonical relative path: 1 to 512
   characters, `/`-separated, with no empty, `.`, or `..` component, no
   leading or trailing `/`, no backslash, colon, or control character, and
   equal to its normalized form.
4. Neither is protected. After Unicode NFKC normalization and case folding, a
   path is protected when any component begins with `.` (this covers
   `.rapp-work`, `.rapp-hive`, `.git`, `.github`, and every other hidden
   entry); when any component is `rappid.json`; when the whole path is
   `organization.json`, `workspaces.json`, or `SPEC.md`; when the final
   component is `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `SKILL.md`, or
   `soul.md`, or ends in `.instructions.md`, `.prompt.md`, `.agent.md`, or
   `.chatmode.md`; or when it names a file in the SDK-owned inventory.
5. After the same folding, sources are distinct, destinations are distinct,
   and no source is a destination, so moves never chain, swap, or alias on a
   case- or normalization-insensitive filesystem.
6. Every directory between the root and each file exists, is reached without
   symlinks, is on the root's filesystem, and contains no entry named
   `rappid.json` or `.git` (a nested identity or repository root). A move plan
   never creates or removes a directory.
7. Each source is a regular file with exactly one link, owned by the effective
   user, without setuid, setgid, or sticky bits, at most 16 MiB, and on the
   root's filesystem, and its current SHA-256, byte length, and mode equal the
   plan.
8. Each destination is absent: no file, directory, symlink, or other entry.
9. `subject` and `preconditions` equal the root's current values.

### 4.2 Applying a move plan

After the replay, apply creates `.rapp-work/move-recovery.json` create-only
with mode 0600. It is a closed `rapp-work-move-recovery/1` record of exactly
`schema`, `plan`, and `plan_sha256`. The apply holds an exclusive advisory lock
on the marker until it finishes. An apply that finds the marker locked refuses
and changes nothing, and a resumed apply takes the lock before it reads the
marker. Then, for each move in order, apply:

1. links the destination to the source with one descriptor-relative,
   no-follow, no-replace hard link, and refuses an existing destination,
   another filesystem, or a filesystem without hard links;
2. makes the link durable and verifies that both names are one file with the
   planned bytes, SHA-256, and mode;
3. removes the source name and makes that durable; and
4. verifies that the destination is again a single-link file with the planned
   bytes.

After every move verifies, apply removes the marker. The file always has at
least one verified name. An implementation without descriptor-relative
no-follow hard links refuses move plans; it never falls back to a rename that
can replace a destination.

A marker for the same plan resumes apply. Each move must then be in one of
three states: not started (the planned source and no destination), linked
(both names are one planned file with two links), or done (no source and the
planned destination with one link). Apply continues from those states. Any
other state, a marker for another plan, or changed preconditions are refused,
and the marker and every name stay in place for the owner. Foreign or
ambiguous state is never repaired, deleted, or rewritten. A refusal before the
first link removes the marker that apply created; a refusal after it keeps the
marker.

While a move marker is pending, `update` refuses to plan another move and
refuses to apply any plan except that move plan.

| Interrupted | State left | Next apply of the same plan |
|---|---|---|
| before the marker is created | unchanged | a first apply |
| while the marker is written | nothing moved; the marker may be partial | refused; the owner removes the marker |
| after the marker, before a link | marker; source | link, verify, unlink |
| after a link | marker; one file with two names | verify, unlink the source |
| after a source name is removed | marker; destination | verify, continue |
| after every move | marker; every file moved | verify, remove the marker |

A completed move plan is spent: when every source is absent and every
destination holds its planned file, apply refuses and changes nothing. The
plan applies again only when its preconditions hold again, for example after
its inverse.

### 4.3 Inverse

The inverse of a move plan has the same `target`, `subject`, and
`preconditions`. Every move's `source` and `destination` are exchanged, with
the same `sha256`, `bytes`, and `mode`, and the moves are sorted by the new
`source`. The inverse has its own hash and applies only through an explicit
apply of that exact hash. The inverse of the inverse is the original plan,
byte for byte. `update` with `inverse_of` returns the inverse without effects
and without reading the moved files, so the owner can review a move and its
undo together. Applying a plan and then its inverse restores every moved path,
byte, and permission mode; directory timestamps are not restored.

A move never leaves its root and never writes an Organization pointer. An
Organization records whole workspace roots, and a move stays inside one root.
Knowledge moves between Workspaces or worlds only by signed and approved
copies.

## 5. RAPP/1 wrapper

The SDK loads the exact implementation pinned by `RAPP1_PIN.json` and verifies
the pinned implementation and specification hashes before use.

A RAPP/1 Frame accepted by the SDK has exactly:

`spec`, `kind`, `stream_id`, `seq`, `utc`, `payload`, `payload_hash`,
`frame_hash`, `prev`, `prev_wave`, `sig`.

The SDK delegates canonical particle, wave, chain, stream, and signature checks
to that pinned implementation. Additive SDK metadata never enters the Frame
envelope.

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

Unsupported sharing, public Git, credential inheritance, implicit apply,
unknown JSON members, parent-authority changes, plugin execution, neuron
execution, source deletion, owner rotation, and unverified Hive rollback/fork
acceptance are explicit refusals.
