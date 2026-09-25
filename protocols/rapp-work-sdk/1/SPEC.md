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

A move relocates an existing file with one descriptor-relative rename that
never replaces an existing destination (§4.2). It writes no file bytes except
its own recovery marker, and it is not the source deletion refused by §12.

### 4.1 Move plans

A move plan relocates existing regular files inside one Workspace or
Organization root. It carries hashes, not bytes. Its schema is
`rapp-work-move-plan/1`, a closed object with exactly `schema`, `protocol`
(`rapp-work/1`), `profile` (`rapp-work-sdk/1`), `network` (`false`),
`operation` (`update`), `target`, `subject`, `preconditions`, and `moves`:

- `target` is the root's absolute lexical path.
- `subject` is exactly the root identity's `kind` (`workspace` or
  `organization`), `rappid`, and `world_id`.
- `preconditions` is exactly `identity_sha256` (of `rappid.json`) and
  `root_identity` (the root's `device`, `inode`, and permission `mode`). A move
  plan does not bind the SDK-owned inventory; every apply reads it again
  (item 4).
- `moves` holds 1 to 64 move actions sorted by `source`. Each is exactly
  `operation` (`move`), `source`, `destination`, `sha256`, `bytes`, and `mode`
  (the source's permission bits, 0 to 0o777). Sources total at most 64 MiB.

The plan SHA-256 is the SHA-256 of the plan's canonical JSON. A
`rapp-work-release-plan/1` never contains a move, and a move plan never
contains a create or replace action.

The fold of a string `s` is `F(upper(F(s)))`, where `F(x)` is
`NFKC(casefold(NFKC(x)))` (Unicode normalization form NFKC and full case
folding) and `upper` is the full upper-case mapping. It joins the spellings
that case-insensitive, normalization-insensitive, and upper-case-comparing
filesystems resolve to one name.

Planning refuses unless all of the following hold. A first apply replays every
one before its first write. A resumed apply (§4.2) replays the same checks,
except that it expects its own move marker and checks each file against the
recovery states instead of items 7 and 8 and, for the files themselves,
item 10.

1. The root is reached without symlinks, its identity is a Workspace or
   Organization, and its SDK integration verifies: the SDK-owned inventory
   exists and matches, and `.rapp-work/sdk.json` equals the qualified record.
   A legacy workspace, or one whose integration another SDK release wrote,
   first applies an ordinary update plan.
2. No update or move recovery marker is pending.
3. Each `source` and `destination` is a canonical relative path: 1 to 512
   characters, `/`-separated, with no empty, `.`, or `..` component, no
   leading or trailing `/`, no backslash or colon, and equal to its normalized
   form. It contains no code point of general category Cc, Cf, Cn, Co, Cs, Zl,
   or Zp and no `Default_Ignorable_Code_Point` of Unicode 15.1
   (`DerivedCoreProperties.txt`): filesystems ignore or remap such code points,
   and they can hide what a reviewed path says. General categories are those of
   the implementation's Unicode character database; a code point it does not
   assign is Cn, so an older database refuses more, never less.
4. Neither is protected. A path is protected when, with each component folded,
   any component begins with `.` (this covers `.rapp-work`, `.rapp-hive`,
   `.git`, `.github`, and every other hidden entry); when any component is
   `rappid.json`; when the path is the single component `organization.json`,
   `workspaces.json`, or `SPEC.md`; when the final component is `AGENTS.md`,
   `AGENTS.override.md`, `CLAUDE.md`, `CLAUDE.local.md`, `GEMINI.md`,
   `SKILL.md`, `soul.md`, or `basic_agent.py`, or ends in `.instructions.md`,
   `.prompt.md`, `.agent.md`, or `.chatmode.md`; or when its fold equals the
   fold of a path in the SDK-owned inventory.
5. After the fold, sources are distinct, destinations are distinct, and no
   source is a destination, so moves never chain, swap, or alias.
6. Every directory between the root and each file exists, is reached without
   symlinks, is on the root's filesystem, and contains no entry named
   `rappid.json` or `.git` (a nested identity or repository root). A move plan
   never creates or removes a directory.
7. Each source is a regular file with exactly one link, owned by the effective
   user, without setuid, setgid, or sticky bits, at most 16 MiB, and on the
   root's filesystem; its current SHA-256, byte length, and mode equal the
   plan; and it is not another name of a protected file: its device and inode
   differ from those of every SDK-owned file (the inventory included), of every
   file in the root named `rappid.json`, `SPEC.md`, `organization.json`,
   `workspaces.json`, or a final-component name of item 4, and of every file in
   its own directory named `rappid.json` or a final-component name of item 4.
8. Each destination is absent: no file, directory, symlink, or other entry.
9. `subject` and `preconditions` equal the root's current values.
10. Every existing entry a move names, each component of `source` and each
    directory component of `destination`, is spelled exactly, code point for
    code point, as its directory stores it, never as another case, width, or
    normalization form that the filesystem only resolves to it. So applying a
    plan and then its inverse restores every name exactly. A directory that
    cannot be listed, or that lists more than 100,000 entries, is refused.

### 4.2 Applying a move plan

Apply needs a no-replace rename between two directory descriptors that never
follows a symbolic link: Linux `renameat2` with `RENAME_NOREPLACE`, macOS
`renameatx_np` with `RENAME_EXCL`, or an equivalent. Without one, or when the
filesystem does not support it, move plans are refused with `REFUSE_PLATFORM`.
An implementation never falls back to a rename that can replace, to a hard link
followed by an unlink, or to a copy.

After the replay, apply writes a closed `rapp-work-move-recovery/1` record of
exactly `schema`, `plan`, and `plan_sha256` to a new private file in
`.rapp-work/` named `.move-recovery-`, 32 lowercase hexadecimal digits, and
`.tmp`, with mode 0600. It locks that file with an exclusive advisory lock,
makes it durable, and renames it without replacing to
`.rapp-work/move-recovery.json`, so the marker appears complete and locked, or
not at all. The apply holds the lock until it finishes. An apply that finds the
marker locked refuses and changes nothing. A resumed apply takes the lock
without waiting and then requires that the marker name still refers to the
file it locked; an apply whose marker was removed or replaced before it got
the lock refuses and changes nothing.

Then, for each move in order, apply:

1. opens the source without following links and verifies, through that open
   file, that it is the planned file (identity, one link, owner, mode, byte
   length, and SHA-256) and not another name of a protected file (§4.1 item 7);
2. renames the source name to the destination name with the no-replace rename,
   refusing an existing destination or another filesystem, and makes both
   directories durable; and
3. verifies that the file now named by the destination is that same open file,
   stored under exactly the planned spelling, with one link and the planned
   mode, byte length, and SHA-256, and that no entry of the destination
   directory named `rappid.json` or a final-component name of §4.1 item 4
   (and, at the root, `organization.json`, `workspaces.json`, or `SPEC.md`)
   refers to it.

If step 3 fails, another process changed or replaced the source during the
move, the filesystem stored the destination under another spelling, or the
destination is another name of a protected file. Apply renames the
destination name back to the source name with the same no-replace rename and
refuses. When that undo is verified, the apply created the marker, and no
earlier move of the apply took effect, it also removes the marker; otherwise
the marker and every name stay for the owner. No step of a move unlinks or
replaces a name of a file it moves, so a move never makes a file unreachable,
whatever another process does meanwhile. The only names an apply removes are
its own recovery marker and temporary file.

A move is not a transaction against concurrent writers of its source. Until
step 3 completes, the destination holds whatever file the source name held at
the rename; if another process replaced or edited the source after step 1,
those unverified bytes are at the destination until the undo, and a program
that reads the destination directory in that instant, such as a Brainstem
loading agents, may read them.

After every move verifies, apply removes the marker, only while the marker name
still refers to the file it created and holds, and makes the removal durable.

A marker for the same plan resumes apply. Each move must then be in one of two
states: pending (the planned source, under its stored spelling, and no
destination) or moved (no source and a destination, under the planned
spelling, with the planned bytes, mode, and one link). Apply continues
from those states. Any other state, a marker for another plan, or changed
preconditions are refused, and the marker and every name stay in place for the
owner. Foreign or ambiguous state is never repaired, deleted, or rewritten. A
refusal before any rename of the apply takes effect removes the marker that
apply created; after that, the marker stays.

While a move marker is pending, `update` refuses to plan a move or an inverse
and refuses to apply any other move plan. An ordinary SDK update may still be
applied: it writes only SDK-owned files, which no move touches, so a pending
move can always resume after an SDK upgrade.

| Interrupted (process death or power loss) | State left | Next apply of the same plan |
|---|---|---|
| before the marker is renamed into place | no marker; perhaps a private temporary file | a first apply |
| after the marker, before a rename | marker; source | rename, verify |
| after a rename | marker; source or destination | continue from the state found |
| during an undo | marker; a changed file at one of the names | refused; left for the owner |
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
undo together. Applying a plan and then its inverse restores every moved
name exactly (§4.1 item 10), with its bytes and permission mode; directory
timestamps are not restored. Move plans do
not bind the SDK-owned inventory, so an SDK update between a move and its undo
leaves the stored inverse valid.

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

An `update` move plan (§4.1) is not an integration update. It relocates
existing files inside an SDK Workspace or Organization, never writes,
replaces, or removes an SDK-owned file, and writes only its own recovery
marker.

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
