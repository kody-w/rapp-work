# Proposal 0002: SDK move plans (gap G2)

- **Status:** draft, not accepted. Every change here is a proposal on branch
  `experimental/gap-g2-move-action`; the owner decides what moves.
- **Gap:** G2, "SDK plans cannot move a file": an SDK plan can create or
  update a file, but not move one. The proposed fix adds a `move` action whose
  undo is the inverse move.
- **Home specification:** `rapp-work-sdk/1`
  (`protocols/rapp-work-sdk/1/SPEC.md`), §2 (public JSON operations) and §4
  (filesystem boundary). The gap blocks the Workspaces part.
- **New status word requested for G2:** proposed.
- **Intended release:** `rapp-work` 1.1.0, an additive minor release. This
  branch does not bump the package version or `SDK_VERSION`.

## Why it matters

The organism's invariant (`organism/invariants.md` on
`experimental/rapp-work-constitution`) says: "Only top-level
`agents/*_agent.py` files are live. Every folder is organization: loading or
unloading an agent is a file move." The Grail kernel's `load_agents()` is a
flat glob of `agents/*_agent.py`, and `kody-w/rapp-installer` ships a
non-live `rapp_brainstem/agents/experimental/` folder (observed at tag
`brainstem-v0.6.16`). A person's Brainstem, and gap G17's Brainstem agent,
therefore needs to load or unload an agent by an exact-hash, reviewable,
reversible SDK plan: propose, confirm in a later turn, apply one exact step,
and undo it the same way. Today no SDK plan can express that step.

## Context: what is true today

All references are to `kody-w/rapp-work` `main` at `29ead23`.

- `protocols/rapp-work-sdk/1/SPEC.md` §2 closes the operation set at `status`,
  `verify`, `discover`, `scaffold`, `update`, and `migrate`. Effects need an
  explicit apply, the complete plan, its exact canonical SHA-256, and a replay
  of every precondition before the first write. Unknown inputs are refused.
- §4 requires descriptor-relative no-follow effects and refuses symlinks,
  hardlinked authority files, traversal, devices, FIFOs, sockets, unmanaged
  collisions, and changed preconditions. Create-only never replaces; updates
  replace only SDK-owned files at an exact precondition hash. §12 refuses
  "source deletion", which in context is the migration source of §10.
- `src/rapp_work/plans.py`: `FileAction.operation` is `create` or `replace`
  and carries the content bytes (base64), `mode`, and `expected_sha256`.
  `ReleasePlan` (`rapp-work-release-plan/1`) has exactly `actions`,
  `network`, `operation` (`scaffold` or `update`), `preconditions`, `profile`,
  `protocol`, `schema`, `subject`, and `target`; its hash is the SHA-256 of
  its canonical JSON. `SignedRelease` (`rapp-work-signed-release/1`) wraps a
  `/1` release plan.
- `src/rapp_work/workspace.py`: `plan_update`, `_validate_update_plan`, and
  `apply_update` adopt or refresh the SDK integration files only, under the
  inventory `.rapp-work/managed.json` (`rapp-work-managed-files/1`) and the
  plan-bound marker `.rapp-work/update-recovery.json`
  (`rapp-work-update-recovery/1`).
- `src/rapp_work/api.py`: `_update` accepts exactly `root` plus `apply`,
  `plan`, and `plan_sha256`; any other member is `REFUSE_INPUT_KEYS`.
- `src/rapp_work/_paths.py` holds the no-follow primitives: `directory_fd`
  walks every component with `O_NOFOLLOW | O_DIRECTORY`, `read_regular`
  requires a regular single-link file, and `write_new` is `O_CREAT | O_EXCL`.
  Scaffold and migration activate directories with a ctypes
  `renameat2(RENAME_NOREPLACE)` / `renameatx_np(RENAME_EXCL)` wrapper.
- `protocols/index.json` and `src/rapp_work/data/profiles.json` pin the SDK
  SPEC at `cf64a90f44427728966ba142d6ef42cdd31f08ad465badf86a93c969f0cb8ef1`.
  The frozen signed `registry.json` does not pin `rapp-work-sdk/1`
  (`tools/check.py` excludes it from the signed protocol set).

## Design decisions

### 1. Token: a new `rapp-work-move-plan/1`, not a wider `/1` release plan

Adding a move to `FileAction` would change the action grammar and the key set
of `rapp-work-release-plan/1`, so RAPP/1 Constitution Article 2 ("One label,
one shape") forbids it in place. Two new tokens carry the capability instead:

- `rapp-work-move-plan/1`, a closed plan whose `moves` hold only move actions.
  It carries hashes, byte lengths, and modes, never file bytes, and never
  contains a create or replace action.
- `rapp-work-move-recovery/1`, the plan-bound marker
  `.rapp-work/move-recovery.json`.

A distinct move-plan token was chosen over a `rapp-work-release-plan/2`
superset because a move relocates existing bytes while a release plan writes
carried bytes: they are different shapes with different verification, and a
`/2` superset would invite mixed plans whose crash semantics combine both
recovery markers. It also leaves `rapp-work-signed-release/1` exactly as it
is, because that record only wraps `/1` release plans. Every existing `/1`
plan keeps its exact bytes, meaning, and hash (test vector below). An SDK that
predates this proposal refuses a move plan before any effect: its
`ReleasePlan.from_dict` sees `moves` instead of `actions`
(`REFUSE_INPUT_KEYS`), and its `update` refuses the `moves` and `inverse_of`
members (evidence below).

### 2. Operation: `update`, with two additive optional closed members

`update` is the operation that changes an existing Workspace or Organization
in place; `scaffold` creates a new root and `migrate` creates a successor, so
neither fits, and no seventh operation is added. `update` gains two optional
members of its closed input:

- `moves`: an array of 1 to 64 closed `{"source", "destination"}` objects.
  It returns a move plan and its hash, without effects.
- `inverse_of`: a complete move plan. It returns that plan's exact inverse
  and its hash, without effects.

They are mutually exclusive and are refused together with `apply` (the plan
object alone carries the reviewed moves). An apply whose `plan.schema` is
`rapp-work-move-plan/1` is dispatched to the move path; every other apply is
parsed exactly as before. `update` without the new members is unchanged. The
CLI mirrors the members as `update --move SOURCE DESTINATION` (repeatable) and
`update --inverse-of PLAN_FILE`.

### 3. Preconditions

Every check below runs at planning and again, from scratch, before the first
write of a first apply. A resumed apply (decision 4) repeats them too, except
that it expects its own marker and checks each file against the recovery
states instead of the source and destination checks:

- The root is reached without symlinks, is a Workspace or Organization, and
  its SDK integration verifies (inventory present and matching, `sdk.json`
  equal to the qualified record, kind-specific `verify` passing). A legacy
  workspace first adopts the SDK through the ordinary additive update plan,
  so moves never write SDK state into an unqualified root.
- No update or move recovery marker is pending.
- Paths are canonical safe relatives: `safe_relative` (1 to 512 characters,
  no absolute path, `..`, empty or `.` component, backslash, colon, NUL, or
  control character) plus equality with the normalized POSIX form, which also
  refuses `./a`, `a//b`, `a/./b`, `a/`, and `.`.
- Protected paths are refused as a source or a destination (§4.1 item 4):
  every hidden component (which covers `.rapp-work/**`, `.rapp-hive/**`,
  `.git/**`, `.github/**`, `.claude/**`, `.gitignore`, and `.env`), any
  `rappid.json`, the root's `organization.json`, `workspaces.json`, and
  `SPEC.md`, the common AI instruction files anywhere (`AGENTS.md`,
  `CLAUDE.md`, `GEMINI.md`, `SKILL.md`, `soul.md`, `*.instructions.md`,
  `*.prompt.md`, `*.agent.md`, and `*.chatmode.md`), and every path in the
  SDK-owned inventory. Comparison uses NFKC normalization and case folding, so
  `Claude.md` or a full-width spelling is refused too. A move relocates
  content; it never adds, removes, or relocates authority or instructions,
  which keeps G7's instruction inventory meaningful.
- Sources are distinct, destinations are distinct, and no source is a
  destination after the same folding, so a plan cannot chain, swap, or alias
  files on a case- or normalization-insensitive filesystem. Moves are then
  independent of order.
- Every directory below the root on the way to each file exists, is reached
  without symlinks, is on the root's device, and contains no `rappid.json` or
  `.git` entry (a nested identity or repository root is a boundary).
- Parent directories must already exist. A move plan never creates or removes
  a directory, so the directory structure is constant during a plan and the
  inverse restores the tree exactly. This matches drag and drop, which always
  drops into an existing folder. The bound on created directories is zero.
- The source is a regular file (checked with `lstat`, then opened with
  `O_NOFOLLOW` and matched by `fstat` identity), has exactly one link, is
  owned by the effective user, has no setuid, setgid, or sticky bit, is at
  most 16 MiB, and is on the root's device; its SHA-256, byte length, and
  permission mode equal the plan. A plan holds at most 64 moves and 64 MiB,
  the same byte bounds as release plans.
- The destination is absent: no file, directory, symlink, or other entry.
- The plan also binds the root's `rappid.json` hash, inventory hash, and root
  identity (`device`, `inode`, `mode`), exactly as update plans already do.

### 4. Atomic no-replace apply

Three options were evaluated:

| Option | No-replace | Crash window | Verdict |
|---|---|---|---|
| A. `os.link(src, dst, src_dir_fd=, dst_dir_fd=, follow_symlinks=False)`, verify, `os.unlink(src, dir_fd=)` | the kernel refuses an existing destination (`EEXIST`) | two names for one file, which is resumable | **chosen** |
| B. plain `rename` after an absence check, with a lock or marker | none: `rename` silently replaces a destination created after the check, and a lock binds only cooperating processes | none | rejected: violates §4 create-only |
| C. ctypes `renameat2(RENAME_NOREPLACE)` / `renameatx_np(RENAME_EXCL)` | the kernel | none | not chosen |

Option A uses only the standard library, is descriptor-relative on both
directories, refuses a cross-filesystem move by itself (`EXDEV`), and lets the
SDK verify the new name (same inode, planned SHA-256 and mode) before the old
name disappears; the destination link is made durable (`fsync` of its
directory) before the source is unlinked. Option C has no two-name window but
depends on per-filesystem support, cannot verify before the flip, and its
macOS fallback `renamex_np` is path-based, not descriptor-relative. Both
`os.link` modes used here were verified on macOS with Python 3.10 and 3.13
and on Linux with Python 3.12. Without them, or on a filesystem without hard
links (`EPERM`, `EMLINK`, `ENOTSUP`), moves are refused with `REFUSE_PLATFORM`
and never fall back to a replacing rename.

Apply order: replay every precondition; create the marker create-only
(`O_EXCL`, mode 0600, `fsync`) and hold an exclusive `flock` on it until the
apply ends; for each move, link, `fsync` the destination directory, verify
both names are one planned file with two links, unlink the source, `fsync` the
source directory, and verify one planned link remains; then read every
destination back, remove the marker, and run `verify`. The marker is
therefore also the apply lock: a second apply that finds it locked refuses
with `REFUSE_RECOVERY_BUSY` and changes nothing, two first applies racing to
create it cannot both succeed (`O_EXCL`), and a resume takes the lock without
waiting before it compares the marker's bytes. A crashed apply's lock is
released by the kernel, so its marker can be resumed. If the marker cannot be
locked or fully written without a crash (for example `ENOLCK` or `ENOSPC`),
apply removes the marker it just created and refuses; only a power loss in
that short window can leave a partial marker, which then fails closed like any
foreign marker. The accepted update marker has the same window.

Crash and interruption matrix (one move; a plan applies moves in `source`
order and each move is in exactly one of these states):

| Interrupted | On disk | User's copy | Next apply of the same plan |
|---|---|---|---|
| before the marker is created | unchanged | source | first apply (full replay) |
| while the marker is written (power loss) | nothing moved; an empty or partial marker may remain | source | refused as another plan's marker; the owner removes it |
| after the marker, before the link | marker; source | source | link, verify, unlink |
| after the link, before its `fsync` (power loss) | the link may be lost | source, perhaps also destination | as the row above or below |
| after the link is durable | marker; one file, two names | both names | verify SHA-256, unlink the source |
| after the unlink, before its `fsync` (power loss) | the source name may return | one or two names | as the row above or below |
| after the source name is removed | marker; destination | destination | verify, continue |
| after every move, before the marker is removed | marker; all moved | destinations | verify, remove the marker |
| after the marker is removed, before its `fsync` | the marker may return | destinations | as the row above |

The source name is removed only after the destination link is durable and
verified, so the file always has at least one verified name. Every other
state (both names missing, two different files, a third link, changed bytes
or mode, a foreign or forged marker) is refused with `REFUSE_RECOVERY_STATE`
or `REFUSE_RECOVERY_BINDING`; the marker and every name are left for the
owner, and the SDK never repairs, deletes, or rewrites them. A refusal before
the first link of an apply removes the marker that apply created (nothing
changed); a refusal after it keeps the marker and reports `completed_moves`
and `recovery: pending`. While a move marker is pending, `update` refuses to
plan another move (`REFUSE_RECOVERY_PENDING`, naming the pending plan hash),
refuses another move plan (`REFUSE_RECOVERY_BINDING`, or
`REFUSE_RECOVERY_BUSY` while an apply holds the marker), and refuses an SDK
update apply (`REFUSE_RECOVERY_PENDING`, the one guarded refusal added to
`apply_update`); moves likewise refuse while an update recovery is pending.
The two recovery paths therefore never interleave.

### 5. Undo is itself a plan

The inverse has the same `target`, `subject`, and `preconditions`, exchanges
every `source` and `destination` with the same `sha256`, `bytes`, and `mode`,
and sorts by the new `source`. It has its own canonical hash and needs its own
explicit apply with that hash. The inverse of the inverse is the original
plan, byte for byte (no back-reference is embedded, so inversion is an
involution). `update` with `inverse_of` computes it from the plan alone,
without reading the moved files, so the Brainstem can show a move and its undo
together at review time; the inverse's own apply replays all of its
preconditions. Moves preserve the inode, bytes, and mode, and plans never
change directories, so applying a plan and then its inverse restores every
path, byte, permission mode, and inode (tested); only directory timestamps
differ.

Replay decision: a completed plan is spent. When every source is absent and
every destination holds its planned single-link file, apply refuses with
`REFUSE_PLAN_APPLIED` and changes nothing. That is consistent with `update`'s
existing refusal of replayed plans and still gives a retrying caller a
machine-readable "already done". The plan applies again only when its
preconditions hold again, for example after its inverse (redo is tested).
Applying an inverse before its forward plan is `REFUSE_PLAN_APPLIED` for the
same reason: its postconditions already hold.

### 6. Inventory, legacy workspaces, and Organizations

- SDK-owned inventory files can never be a move source or destination, the
  inventory is never rewritten by a move, and `verify` passes before and after
  every move. The move marker lives under `.rapp-work/` and is not an
  inventory entry.
- Legacy workspaces are refused (`REFUSE_SDK_PROFILE`) until the ordinary
  additive update adopts the SDK; after that, moves work and the legacy
  `rappid.json` bytes are untouched (tested). A workspace integrated by an
  older SDK refreshes through its ordinary update first (tested).
- Organizations stay pointer-only. A move stays inside one root, cannot move a
  directory, cannot cross a nested `rappid.json` root, and refuses
  `organization.json` and `workspaces.json`, so it can never change or break a
  pointer (tested with a registered workspace). Moving knowledge between
  Workspaces or worlds remains the job of signed and approved copies.

### How G17 would use it

Unloading an agent that lives in a Workspace:

1. `update` with `root` and `moves: [{"source": "agents/example_agent.py",
   "destination": "agents/experimental/example_agent.py"}]` returns the plan
   and its hash; `update` with `root` and `inverse_of: <plan>` returns the
   undo and its hash. The Brainstem shows both in plain words.
2. In a later turn the person confirms; the Brainstem sends `apply: true`,
   the plan, and its exact hash.
3. "Undo that" is the same exchange with the stored inverse plan.

How the Brainstem's own `agents/` folder is addressed as an SDK root is G17's
and G22's decision (open question 8).

## Proposed change

The branch inserts the following normative text into
`protocols/rapp-work-sdk/1/SPEC.md`. No existing sentence is changed or
removed.

Insertion in §2, after "Unknown operation inputs and unsupported capabilities
MUST be refused before effects. Output is canonical I-JSON with no
floating-point values.":

```text
`update` also plans file moves (§4.1) through two optional members of its
closed input: `moves` plans a move plan, and `inverse_of` returns the exact
inverse of a supplied move plan (§4.3). The two are mutually exclusive, are
accepted only without `apply`, and are accepted by no other operation. An
`update` apply whose plan has schema `rapp-work-move-plan/1` is applied under
§4.2. Every other `update` plan remains a `rapp-work-release-plan/1`, whose
shape, hash, and meaning are unchanged.
```

Insertion in §4, after "SDK updates may replace only files named in the prior
SDK-owned inventory and only when their exact current SHA-256 equals the plan
precondition.":

```text
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
```

Static API metadata (`src/rapp_work/data/api.json`, `rapp-work-static-api/1`,
whose shape is unchanged) lists the two new optional `update` inputs and adds
the refusal "replacing, cross-filesystem, or protected-path moves".
`docs/API.md`, `docs/ARCHITECTURE.md`, `README.md`, `protocols/README.md`, and
`CHANGELOG.md` (`## Unreleased (proposal, not accepted)`) describe the change.

## Token and compatibility analysis

- **New tokens:** `rapp-work-move-plan/1` and `rapp-work-move-recovery/1`.
- **Unchanged tokens:** `rapp-work-release-plan/1` (the fixed vector below
  hashes identically on `main` and on this branch), `rapp-work-signed-release/1`,
  `rapp-work-update-recovery/1`, `rapp-work-managed-files/1`, the
  `rapp-work-sdk/1` integration record and `schema.json`, `rapp-work-result/1`,
  `rapp-work-static-api/1` (content only), and every RAPP/1 form. Article 18
  (frozen wire) and Article 10 (one canonicalizer) are untouched: plans hash
  with the pinned canonicalizer, and the eleven-key Frame is not involved.
- **Old SDKs fail closed.** Evidence, run in memory against an archive of
  `origin/main` on Python 3.13 and 3.10:

  ```text
  plan-moves refused REFUSE_INPUT_KEYS {"missing":[],"unknown":["moves"]}
  inverse-of refused REFUSE_INPUT_KEYS {"missing":[],"unknown":["inverse_of"]}
  apply-move-plan refused REFUSE_INPUT_KEYS {"missing":["actions"],"unknown":["moves"]}
  ```

- **The `update` input set widens in place.** `rapp-work-sdk/1` §2 closes the
  operation inputs, and this proposal adds two optional members to `update`.
  No versioned record changes shape, every old request keeps its exact
  meaning, and an old SDK refuses the new members before any effect, which is
  what a closed input guarantees. The organism's lock plan closes G2 inside
  `rapp-work-sdk/1` (phase 3). If the owner reads Article 2 as covering the
  operation input set itself, the same text can instead be published as
  `rapp-work-sdk/2`; that is open question 1.
- **Pins:** the SDK SPEC hash moves from
  `cf64a90f44427728966ba142d6ef42cdd31f08ad465badf86a93c969f0cb8ef1`
  to `370194df915b11f42ee5706b06feae7eb6b44254f28ae9a9f9fcbf9dbcec1018`
  in `protocols/index.json` and `src/rapp_work/data/profiles.json`, and
  `RELEASE-INVENTORY.json` is regenerated. The `generated_utc` of
  `protocols/index.json` is left as is. The signed `registry.json`, root
  `SPEC.md`, the `rapp-hive/1` and `rapp-federation/1` SPECs,
  `RAPP1_PIN.json`, `RAPP_WORK_PIN.json`, and every signature are untouched,
  so no re-signature is needed and `tools/check.py` stays green.

## Security and privacy analysis

- **Escape and traversal:** only canonical relative paths; every directory is
  opened component by component with `O_NOFOLLOW | O_DIRECTORY` from the
  root, and each file is opened with `O_NOFOLLOW` and matched by `fstat`
  identity to its `lstat`. Symlinked roots, parents, sources, and
  destinations are refused (mutation M6 shows that the tests catch a walk
  that follows links).
- **Clobbering:** the destination is created only by a no-replace hard link;
  a destination that appears at any moment is refused and kept (tested with a
  race injected immediately before the link; mutation M10).
- **Authority and instructions:** identity, Organization, workspace SPEC,
  hidden, SDK-owned, and AI instruction paths can be neither moved nor created
  by a move, so a move cannot turn someone else's text into an instruction
  file or remove the workspace's own instructions.
- **Boundaries:** one root, one filesystem, no nested identity or repository
  roots, and no directories; world and Organization boundaries are unchanged.
- **Hardlinks and special files:** sources must be single-link regular files
  owned by the user, without special mode bits; FIFOs, sockets, devices, and
  directories are refused before they are opened.
- **Execution:** the SDK never imports or executes a moved file. Moving an
  agent into the top of a Brainstem's `agents/` makes the Brainstem load it;
  that is the person's explicit, exact-hash adoption step.
- **Durability:** the fsync ordering guarantees at least one name across a
  crash. On macOS, `fsync` does not force the drive cache (`F_FULLFSYNC`
  would); the SDK uses `fsync` everywhere, as today.
- **Concurrency:** concurrent SDK applies are serialized by the locked
  marker. A concurrent writer inside the root can make an apply refuse; it
  can never make the SDK replace a file, leave the root, or drop the last
  name. At worst both names and the marker are left for the owner.
- **Privacy:** plans and markers stay local. They carry relative paths,
  hashes, byte lengths, modes, the root's absolute path, and its device and
  inode numbers (as update plans already do), but no file bytes, network
  locations, or credentials. The marker is mode 0600 under `.rapp-work/`. No
  operation uses a network.

## Migration

None is required. Existing Workspaces, Organizations, plans, and recovery
markers keep working unchanged. A workspace that wants moves must pass
`verify` with its SDK integration; a legacy workspace adopts it through the
ordinary update plan first. Callers that never send `moves` or `inverse_of`
see no difference.

## Rollback

Before reverting the branch commit, resume or resolve any pending
`.rapp-work/move-recovery.json` with the proposing SDK. Every file is always
at one or two verified names, so no bytes can be lost; a leftover marker can
be removed by hand after checking the named paths. After a rollback the SDK
again refuses `moves`, `inverse_of`, and move plans with `REFUSE_INPUT_KEYS`.
An SDK without this proposal ignores a move marker, so it must not be used to
run `update` on a workspace with a pending move.

## Conformance and test vectors

`tests/test_sdk_moves.py` (pytest, `sandbox` fixture) adds 41 test functions
that expand to 153 cases. Fixed vectors:

- **`/1` stability:** the release plan built in
  `test_release_plan_v1_hash_vector_is_unchanged` hashes to
  `196dd7112d6371b94535f7e136dd457491c2efc1c82428ca05bbd9409adb801e`. The
  value was computed with the unmodified `origin/main` code before any change
  and is unchanged on this branch.
- **Move plan:** the two-move plan in `test_move_plan_conformance_vector`
  hashes to
  `24f2ba8b123c39b23d9bad00870609905a32451eca95bd66aa9e0858c0af57c9`; its
  inverse hashes to
  `feb001785460f881f2dc626b61476d583143ff31e69083cf0167c55ecd673524`; the
  inverse of the inverse is the plan. Canonical bytes of the plan:

  ```json
  {"moves":[{"bytes":42,"destination":"agents/experimental/example_agent.py","mode":420,"operation":"move","sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","source":"agents/example_agent.py"},{"bytes":7,"destination":"agents/notes_agent.py","mode":384,"operation":"move","sha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff","source":"agents/experimental/notes_agent.py"}],"network":false,"operation":"update","preconditions":{"identity_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","managed_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","root_identity":{"device":1,"inode":2,"mode":448}},"profile":"rapp-work-sdk/1","protocol":"rapp-work/1","schema":"rapp-work-move-plan/1","subject":{"kind":"workspace","rappid":"rappid:@example/finance:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","world_id":"example-world"},"target":"/example/workspace"}
  ```

Positive vectors: plan-only by default (tree unchanged, no marker); apply with
the exact hash (bytes, mode, and inode preserved, one link, `verify` passes);
a three-move plan (an unload, a load, and a note) and its inverse restore the
exact tree; the inverse's own hash is required; redo after undo; interrupted
applies resume after a crash before the link, between the link and the
unlink, and before the marker is removed; Organizations keep their pointer
registry byte for byte; legacy and stale integrations work after their
ordinary update; the CLI plans, inverts, and applies; every envelope is
canonical and float-free; default `update` still plans
`rapp-work-release-plan/1`.

Refusal vectors (each asserts that the tree is unchanged or exactly as
documented): wrong hash, missing plan or hash, and plan evidence without
`apply`; source edited, re-moded, removed, or hardlinked after planning; a
same-size edit injected after the replay; a destination file, dangling
symlink, or directory created after planning; a destination created
immediately before the link; a symlinked source, source parent, destination
parent, or root, and a parent swapped for a symlink after planning;
hardlinked, FIFO, directory, setuid, oversize, and missing sources; 15 unsafe
path spellings on each side; 26 protected paths on each side; SDK-owned
inventory paths; nested `rappid.json` and `.git` roots in both directions;
missing or non-directory destination parents; empty, oversized, open,
duplicate, chained, swapped, aliased, identical, and case-only moves; `moves`
with `inverse_of`, either one with `apply`, unknown members, and `moves` on
the other five operations; closed plan parsing (extra key, wrong schema,
`network: true`, no moves, float `bytes`, protected path, unsorted moves, and
a `/1` plan) and the `/1` parser refusing a move plan; a forged re-hashed
plan; replay of an applied plan; an inverse for another root; ambiguous
interrupted states (edited, same-size edit, third link, replaced, and both
names missing); a second apply while another holds the marker lock; racing
first applies; a marker that cannot be locked; foreign or forged markers; a
partial multi-move failure; cross-filesystem and link-less filesystems;
another device at planning; a pending update recovery; and an SDK update
while a move is pending.

### Mutation proof

Each critical check was mutated locally, its targeted tests were run on
Python 3.13, and the original bytes were restored and verified by SHA-256 and
`git diff`. Every mutation turned its tests red:

| ID | Mutation | Targeted tests |
|---|---|---|
| M1 | apply without the exact plan-hash comparison | red: 2 failed |
| M2 | first apply skips the full precondition replay | red: 5 failed, 2 passed |
| M3 | per-move source SHA-256 check skipped just before the link | red: 1 failed |
| M4 | hardlinked sources accepted | red: 2 failed, 8 passed |
| M5 | protected-path policy disabled | red: 46 failed, 6 passed |
| M6 | move walks, reads, and links follow symlinks | red: 4 failed |
| M7 | recovery marker accepted without exact plan binding | red: 2 failed |
| M8 | linked recovery state accepted without its SHA-256 | red: 1 failed, 4 passed |
| M9 | inverse does not exchange source and destination | red: 2 failed |
| M10 | replacing rename instead of the no-replace hard link | red: 2 failed |
| M11 | nested identity or repository boundary check disabled | red: 3 failed |
| M12 | spent-plan detection disabled | red: 2 failed |
| M13 | `rapp-work-release-plan/1` widened in place with a `moves` key | red: 1 failed |
| M14 | destination-absence check at planning disabled | red: 3 failed |
| M15 | marker kept even when no link happened | red: 3 failed |
| M16 | SDK update apply allowed while a move recovery is pending | red: 1 failed |
| M17 | same-filesystem checks disabled | red: 1 failed |
| M18 | setuid, setgid, or sticky sources accepted | red: 1 failed, 5 passed |
| M19 | non-canonical path spellings accepted | red: 8 failed, 22 passed |
| M20 | chained, swapped, or aliased moves accepted | red: 4 failed, 8 passed |
| M21 | `moves` or `inverse_of` accepted together with `apply` | red: 1 failed |
| M22 | a locked (busy) recovery marker is resumed anyway | red: 1 failed |

The cases that stayed green under a mutation are refused by an independent
layer, which is intended defense in depth: M2's content changes are also
caught by the per-move state check, M5's SDK-owned paths by the inventory
check, M19's other spellings by `safe_relative`, and M4, M8, M18, and M20's
other cases by their own checks. Two properties are reviewed rather than
mutation-tested: the fsync ordering (power loss cannot be simulated in a unit
test) and the owner check (tests cannot create files owned by another user
without privileges).

## Reference implementation and gating

- `src/rapp_work/plans.py`: `FileMove` and `MovePlan` (closed parsing, bounds,
  folding, the protected-path policy, and the inverse). They stay in
  `rapp_work.plans`; the top-level `__all__` is unchanged.
- `src/rapp_work/moves.py`: `plan_moves`, `invert_move_plan`,
  `apply_move_plan`, the descriptor-relative walk, the state classifier, and
  the marker.
- `src/rapp_work/api.py`: `update`'s two optional members and schema dispatch.
- `src/rapp_work/cli.py`: `--move` and `--inverse-of`.
- `src/rapp_work/workspace.py`: one guarded refusal in `apply_update` while a
  move recovery is pending.
- `tests/test_sdk_moves.py`.

Gating: the behavior is reachable only through the new `moves` and
`inverse_of` members or a plan whose schema is `rapp-work-move-plan/1`, and
the branch's SPEC text describes it. `update` without those members behaves
exactly as accepted (the full pre-existing suite passes unchanged). The only
change on an existing path is the fail-closed refusal of an SDK update apply
while `.rapp-work/move-recovery.json` exists, a file that only this feature
creates. Defaults remain plan-only, offline, credential-free, and refusing.

Checks: the local mirror of the `conformance` workflow (`tools/check.py`,
`pytest -q`, `ruff check`, `mypy`, `release_inventory.py --check`, `build`,
and `verify_package.py`) passes on Python 3.13 and on Python 3.10: 322 tests
passed with 69 subtests (the 169 pre-existing tests plus the 153 new cases),
an inventory of 147 files, a wheel of 114 files, and an sdist of 156 files.
The move suite, together with the SDK workspace, CLI, public-contract, and
migration suites (185 tests), also passes on Linux (Python 3.12, overlayfs)
as a non-root user. GitHub CI does not run for branch pushes in this
repository.

## Open questions for the owner

1. Accept the additive widening of `rapp-work-sdk/1`'s `update` input, or
   publish the same text as `rapp-work-sdk/2`?
2. Is the protected set right? It deliberately refuses `.github/**` (skills,
   workflows, and instructions), `soul.md`, and root `SPEC.md`. Unloading a
   skill by a move would need a later decision.
3. Should a later token allow a bounded creation of missing destination
   parents, removed by its inverse only when empty?
4. Should move plans be signable, like `rapp-work-signed-release/1`, for Hive
   or multi-device use?
5. Should `status` report a pending move or update recovery marker, and
   should the scaffold `.gitignore` template ignore
   `.rapp-work/move-recovery.json` as it ignores the update marker? Both
   change accepted outputs, so neither is done here.
6. Replay: is refusal with `REFUSE_PLAN_APPLIED` preferred over an `ok`
   `unchanged` result?
7. Case-only renames are refused everywhere because they alias on
   case-insensitive filesystems. Allow them where the filesystem is
   case-sensitive?
8. G17 and G22: how does the Brainstem address its own `agents/` folder as an
   SDK root, for example by making the Brainstem data directory a Workspace?
9. Export `FileMove` and `MovePlan` at the top level?

## Owner actions needed

1. Decide on the §2 and §4 text, or on the `rapp-work-sdk/2` alternative.
2. If accepted, merge the branch. If it is merged together with other
   `rapp-work-sdk/1` gap branches (G3, G4, G7), recompute the SDK SPEC hash in
   `protocols/index.json` and `src/rapp_work/data/profiles.json` and run
   `python3 tools/release_inventory.py --write`.
3. Release as 1.1.0: bump `pyproject.toml`, `SDK_VERSION`, and the version
   checks in `tools/verify_package.py`, `tools/release_inventory.py`, and
   `docs/RELEASE.md`.
4. Relay G2's new status (proposed) to the organism.

No registry signature, owner anchor, or Grail byte is affected.

## Ready-to-file pull request text

Title: `rapp-work-sdk/1: exact, reversible move plans (proposal 0002, G2)`

Body: "Adds `rapp-work-move-plan/1`, planned and applied by `update` through
the optional closed members `moves` and `inverse_of`. A move links without
replacing, verifies, then unlinks, under a plan-bound
`rapp-work-move-recovery/1` marker; its inverse is its own exact-hash plan.
`rapp-work-release-plan/1` is unchanged (fixed vector), old SDKs refuse the
new token, and the SDK SPEC pins are updated. See
`docs/proposals/0002-sdk-move-action.md` for the rationale, crash matrix,
vectors, and mutation results."

## References

- `protocols/rapp-work-sdk/1/SPEC.md` §§2, 4, 10, and 12.
- `src/rapp_work/plans.py`, `workspace.py`, `api.py`, `_paths.py`, and
  `cli.py`.
- `kody-w/rapp-1` `CONSTITUTION.md`, Articles 2, 4, 8, 10, and 18.
- Organism (`kody-w/rapp-work`, branch `experimental/rapp-work-constitution`):
  `organism/gaps/G02.md`, `organism/gaps/G17.md`, `organism/gaps/G22.md`,
  `organism/invariants.md`, `organism/crossings/brainstem-workspaces.md`, and
  `organism/parts/workspaces.md`.
- Grail kernel `load_agents()` flat glob: `kody-w/rapp-installer`
  `rapp_brainstem/brainstem.py` at `brainstem-v0.6.9`, as cited by the
  organism's invariant.
- POSIX `linkat(2)` without `AT_SYMLINK_FOLLOW`, `unlinkat(2)`, and
  `fsync(2)`; Python `os.link` and `os.unlink` with `dir_fd` and
  `follow_symlinks`.
