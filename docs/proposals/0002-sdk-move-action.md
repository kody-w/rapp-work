# Proposal 0002: SDK move plans (gap G2)

- **Status:** draft, not accepted. Every change here is a proposal on branch
  `experimental/gap-g2-move-action`; the owner decides what moves.
- **Revision:** round 3. It answers the round-1 and round-2 independent
  reviews; see "Revision history" at the end.
- **Gap:** G2, "SDK plans cannot move a file": an SDK plan can create or
  update a file, but not move one. The proposed fix adds a `move` action whose
  undo is the inverse move.
- **Home specification:** `rapp-work-sdk/1`
  (`protocols/rapp-work-sdk/1/SPEC.md`), §2 (public JSON operations) and §4
  (filesystem boundary), with one qualifying sentence in §7. The gap blocks the
  Workspaces part.
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
  replace only SDK-owned files at an exact precondition hash. §7 says
  "Updating is additive for legacy workspaces and limited to SDK-owned
  integration files for SDK workspaces." §12 refuses "source deletion", which
  in context is the migration source of §10.
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
  (`rapp-work-update-recovery/1`). `Workspace.verify()` requires
  `.rapp-work/sdk.json` to equal the record of the running SDK version.
- `src/rapp_work/api.py`: `_update` accepts exactly `root` plus `apply`,
  `plan`, and `plan_sha256`; any other member is `REFUSE_INPUT_KEYS`.
- `src/rapp_work/_paths.py` holds the no-follow primitives: `directory_fd`
  walks every component with `O_NOFOLLOW | O_DIRECTORY`, `read_regular`
  requires a regular single-link file, and `write_new` is `O_CREAT | O_EXCL`.
  Scaffold and migration activate directories with a ctypes
  `renameat2(RENAME_NOREPLACE)` / `renameatx_np(RENAME_EXCL)` wrapper,
  `_rename_noreplace`, that takes one parent descriptor for both names and, on
  macOS without `renameatx_np`, falls back to the path-based `renamex_np`.
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
members (evidence below). Neither token has been released; round 2 revised
both drafts (the plan's preconditions no longer bind the SDK inventory, and
the marker is renamed into place).

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
  workspace, or one whose integration another SDK release wrote, first applies
  the ordinary update plan, so moves never write SDK state into an unqualified
  root.
- No update or move recovery marker is pending.
- Paths are canonical safe relatives: `safe_relative` (1 to 512 characters,
  no absolute path, `..`, empty or `.` component, backslash, colon, or
  control character) plus equality with the normalized POSIX form, which also
  refuses `./a`, `a//b`, `a/./b`, `a/`, and `.`.
- Paths contain no code point of general category Cc, Cf, Cn, Co, Cs, Zl, or
  Zp and no Unicode `Default_Ignorable_Code_Point` (Unicode 15.1, fixed in the
  code so every implementation refuses the same set whatever its Unicode
  database). Filesystems ignore or remap such code points (HFS+ ignores 16 of
  them; the macOS exFAT driver maps the private-use U+F029 to `.`), and bidi
  controls and invisible characters can make a reviewed path show something
  other than what it moves. The refusal names the code points and shows the
  path with each one spelled `<U+XXXX>`, so no invisible character is echoed
  to a reviewer.
- Protected paths are refused as a source or a destination (§4.1 item 4):
  every hidden component (which covers `.rapp-work/**`, `.rapp-hive/**`,
  `.git/**`, `.github/**`, `.claude/**`, `.agents/**`, `.cursor/**`,
  `.gitignore`, and `.env`), any `rappid.json`, the root's `organization.json`,
  `workspaces.json`, and `SPEC.md`, the AI instruction files `AGENTS.md`,
  `AGENTS.override.md`, `CLAUDE.md`, `CLAUDE.local.md`, `GEMINI.md`,
  `SKILL.md`, and `soul.md` and the names ending in `.instructions.md`,
  `.prompt.md`, `.agent.md`, and `.chatmode.md` anywhere, the Brainstem base
  class `basic_agent.py` anywhere (every agent imports it), and every path in
  the SDK-owned inventory. This set contains every path of G7's proposed
  `rapp-work-instruction-set/1` (its container rules all sit below hidden
  components). A move relocates content; it never adds, removes, or relocates
  the listed authority or instruction files.
- Comparison uses the fold `F(upper(F(s)))` with `F(x) = NFKC(casefold(NFKC(x)))`.
  `F` alone joins what case-insensitive and normalization-insensitive
  filesystems join (`Claude.md`, full-width letters, ß and `ss`, the Kelvin
  sign); the upper-case round trip also joins dotless `ı` (U+0131) with `i`,
  which filesystems that compare by upper-casing, such as case-insensitive
  ZFS, treat as one letter.
- Sources are distinct, destinations are distinct, and no source is a
  destination after the same folding, so a plan cannot chain, swap, or alias
  files. Moves are then independent of order.
- Every directory below the root on the way to each file exists, is reached
  without symlinks, is on the root's device, and contains no `rappid.json` or
  `.git` entry (a nested identity or repository root is a boundary).
- Parent directories must already exist. A move plan never creates or removes
  a directory, so the directory structure is constant during a plan and the
  inverse restores the tree exactly. This matches drag and drop, which always
  drops into an existing folder. The bound on created directories is zero.
- Every existing entry a plan names (each component of the source, and each
  directory component of the destination) is spelled exactly as its directory
  stores it. Case-insensitive and normalization-insensitive filesystems (for
  example APFS and HFS+ as macOS formats them by default) resolve
  `agents/Example_Agent.py`
  or a decomposed `café.md` to the stored `agents/example_agent.py` or
  composed `café.md`; a move under such an alias would rename the file to the
  alias, and its inverse would bring it back under the alias, not under the
  stored name (round-2 finding 1: an agent unloaded and "undone" that way no
  longer matches the Brainstem's case-sensitive `*_agent.py` glob). The
  check lists the directory and requires the exact name (`REFUSE_PATH_SPELLING`,
  reason `stored-spelling`); a directory with more than 100,000 entries is
  refused rather than listed without bound.
- The source is a regular file (checked with `lstat`, then opened with
  `O_NOFOLLOW` and matched by `fstat` identity), has exactly one link, is
  owned by the effective user, has no setuid, setgid, or sticky bit, is at
  most 16 MiB, and is on the root's device; its SHA-256, byte length, and
  permission mode equal the plan. It is also not another name of a protected
  file: its device and inode differ from those of every SDK-owned file and of
  the protected names that exist in the root and in its own directory. This
  identity check catches a filesystem alias that no lexical rule foresaw. A
  plan holds at most 64 moves and 64 MiB, the same byte bounds as release
  plans.
- The destination is absent: no file, directory, symlink, or other entry.
- The plan binds the root's `rappid.json` hash and root identity (`device`,
  `inode`, `mode`). It deliberately does not bind the SDK inventory: the
  replay reads the inventory again and refuses any path it owns, so an SDK
  update between planning and apply, or between a move and its undo, neither
  invalidates a plan nor widens what it may touch.

### 4. Atomic no-replace apply

The round-1 draft linked the destination, verified, and then unlinked the
source. The review showed that this can delete someone else's bytes: if an
editor atomically saves the source (writes a temporary file and renames it
over the source) after the verification and before the unlink, the unlink
removes the only name of the new version, and apply still reports success.
POSIX has no "unlink only if this is still that file", so no amount of
checking closes that window. The round-2 design therefore never unlinks a name
of a file it moves. Four options were evaluated against one requirement: no
step of the SDK may make any byte sequence that someone else wrote
unreachable.

| Option | Step that could lose someone else's bytes | Verdict |
|---|---|---|
| A. `link` destination, verify, `unlink` source (round 1) | the `unlink`: a concurrent atomic save of the source is deleted | rejected (review finding 1) |
| B. plain `rename` after an absence check | the `rename` replaces a destination created after the check | rejected: violates §4 create-only |
| C. descriptor-relative no-replace `rename` (`renameat2(RENAME_NOREPLACE)`, `renameatx_np(RENAME_EXCL)`) | none: it moves exactly the file the source name holds and refuses an existing destination | **chosen** |
| D. rename the source aside to a random private name, verify, `link` the destination, `unlink` the private name | the final `unlink` is safe only while nobody else knows or replaces the private name; a crash leaves the file under a private name | rejected: weaker guarantee, four recovery states |

Option C is one atomic kernel operation between two directory descriptors. It
never follows a symbolic link (it renames the final components themselves),
refuses an existing destination of any kind (file, directory, dangling
symlink, or another link to the same file) with `EEXIST`, refuses another
filesystem with `EXDEV`, and returns `EINVAL` or `ENOTSUP` where the
filesystem cannot guarantee no-replace, which apply maps to
`REFUSE_PLATFORM`. Moves use their own wrapper with two directory descriptors
and no path-based fallback; `_paths._rename_noreplace` is unchanged.

Verify before and after. Before the rename, apply opens the source with
`O_NOFOLLOW | O_NONBLOCK`, checks through the descriptor that it is the
listed file (device, inode, one link, owner, mode, byte length) and hashes it,
and checks that its identity is not a protected file's. It keeps that
descriptor open across the rename, so the verified file's identity cannot be
reused by another file. After the rename and `fsync` of both directories, the
file named by the destination must be that same open file, with one link, the
planned mode and byte length, and the planned SHA-256 (read again through the
descriptor), the destination directory must store it under exactly the
planned spelling, and no protected name in the destination directory may now
refer to it. Otherwise another process changed or replaced the source in the
window, the filesystem stored the new name under another spelling (HFS+
stores decomposed forms, so a composed destination name is refused with
`REFUSE_PATH_SPELLING`, reason `destination-spelling`, and undone), or the
destination is an alias of a protected name. Apply then renames the
destination back to the source name with the same no-replace rename, verifies
that the entry it moved is back, and refuses with `REFUSE_FILE_RACE` or
`REFUSE_MOVE_PROTECTED` (details `reason`, `undone`, `completed_moves`,
`recovery`). If the undo cannot be verified (for example because the source
name was created again meanwhile), every name is left as it is and the marker
stays.

Race matrix (another process acts while one move applies; every row is a
test in `tests/test_sdk_moves.py`):

| Concurrent action | Window | Result | Bytes |
|---|---|---|---|
| creates the destination (file, directory, dangling symlink) | before the rename | `REFUSE_MOVE_COLLISION`, nothing moved, marker removed | winner and source kept |
| atomically saves the source (temporary file renamed over it) | after verification, before the rename | the new file is moved, detected, moved back; `REFUSE_FILE_RACE` (`source-replaced`, undone) | the new version at the source (it was at the destination, unverified, until the undo); the old version was replaced by the saver itself |
| renames the source away and creates a new source | same | `REFUSE_FILE_RACE` (`source-replaced`, undone) | both files kept at their names |
| edits the source in place, same size or not | same | `REFUSE_FILE_RACE` (`source-changed`, undone) | the edited file at the source (at the destination, unverified, until the undo) |
| hard-links or re-modes the source | same | `REFUSE_FILE_RACE` (`source-changed`, undone) | every name kept |
| atomically saves the source again | after the rename | the planned file stays moved; the save creates a new source; apply succeeds | both versions kept |
| saves the source during the undo, so the undo finds a source | after the rename, before the undo | `REFUSE_FILE_RACE` (undone false), marker kept, resume refused | every version kept at a name |
| moves the destination away | after the rename | `REFUSE_FILE_RACE` (`destination-missing`), marker kept | the file where that process put it |
| replaces the marker with its own file | during the apply | moves complete; `REFUSE_RECOVERY_BINDING`; its file is never removed | kept |
| a second SDK apply of any plan | any time | `REFUSE_RECOVERY_BUSY` or `REFUSE_RECOVERY_PENDING`, no effect | unchanged |
| a stale resume whose marker was finished or replaced before it got the lock | after the other apply | `REFUSE_RECOVERY_BUSY`, no effect | unchanged |
| an ordinary SDK update | while a move is pending | allowed; it writes only SDK-owned files | unchanged |

Apply order and the marker. After the replay, apply writes the
`rapp-work-move-recovery/1` record to a new private file
`.rapp-work/.move-recovery-<32 hex>.tmp` (`O_CREAT | O_EXCL`, mode 0600),
takes an exclusive `flock` on it, makes it durable, renames it without
replacing to `.rapp-work/move-recovery.json`, and makes the directory
durable. The marker therefore appears complete and already locked, or not at
all (round-1 finding 7), and two first applies cannot both place one. The
lock is held until the apply ends; a crashed apply's lock is released by the
kernel. A resume opens the marker, takes the lock without waiting, and then
requires that `nlink >= 1` and that the marker name still has the locked
file's device and inode; an apply that opened a marker another apply then
finished or replaced refuses with `REFUSE_RECOVERY_BUSY` (round-1 finding 2).
For each move in `source` order: verify and pin the source, rename, make both
directories durable, verify the arrival or undo. After every move, apply
removes the marker only while the marker name still refers to the file it
holds, and makes the removal durable. The only names an apply ever removes
are its own marker and temporary file. A refusal before any rename of an
apply takes effect removes the marker that apply created; a refusal after one
keeps it and reports `completed_moves` and `recovery: pending`.

Crash matrix (process death or power loss; one move; a plan applies moves in
`source` order, each in one of these states; rows 2 to 6 are tests):

| Interrupted | On disk | Next apply of the same plan |
|---|---|---|
| before the temporary marker is renamed into place | no marker; after process death, one private `.move-recovery-*.tmp` that is never read | a first apply (tested with and without the leftover) |
| after the marker is placed, before the rename | marker; source | pin, rename, verify |
| after the rename, durable or not | marker; exactly one of source or destination (rename is atomic) | continue from the state found |
| during an undo | marker; the other process's file at one of the names | `REFUSE_RECOVERY_STATE`; left for the owner |
| after every move, before the marker is removed | marker; destinations | verify, remove the marker |
| after the marker is removed, before its `fsync` | the marker may return | as the row above |

Resume states are exactly pending (the planned source metadata and no
destination; the bytes are verified through the pinned descriptor before the
rename) and moved (no source; a destination with the planned bytes, mode, and
one link). A destination replaced after a crash by a file with the identical
bytes and mode counts as moved (tested): the plan promises paths, bytes, and
modes. Every other state (both names present, both missing, changed bytes or
mode, a second link, a foreign or forged marker) is refused with
`REFUSE_RECOVERY_STATE` or `REFUSE_RECOVERY_BINDING`; the marker and every
name are left for the owner, and the SDK never repairs, deletes, or rewrites
them.

While a move marker is pending, `update` refuses to plan another move or an
inverse (`REFUSE_RECOVERY_PENDING`, naming the pending plan hash; round-1
finding 6) and refuses another move plan (`REFUSE_RECOVERY_BINDING`, or
`REFUSE_RECOVERY_BUSY` while an apply holds the marker). Moves refuse while an
update recovery is pending, because the replay reads the inventory. An
ordinary SDK update is allowed while a move is pending (round-1 finding 4): it
writes only SDK-owned files, which no move names, and a move plan does not
bind the inventory. After an SDK upgrade, a resume or a stored plan asks for
the ordinary update first (`REFUSE_SDK_PROFILE`, whose message says it may run
while a move is pending), and then applies; nothing deadlocks. The round-1
guard that `apply_update` added is removed, so `workspace.py` is unchanged
from `main`.

Platform and filesystem evidence (scratch probes, not committed):

| Host | Filesystem | No-replace rename | Move suite |
|---|---|---|---|
| macOS 27.0, `renameatx_np(RENAME_EXCL)` | APFS (case-insensitive) | `EEXIST` onto an existing file, same-inode link, or dangling symlink; success onto an absent name | 298 of 299 cases pass, 1 skipped (it needs a filesystem that rewrites new names) (3.13 and 3.10) |
| same | HFS+ disk image (case-insensitive, journaled) | same | 299 cases pass, the stored-spelling cases included (3.13) |
| same | exFAT disk image | `ENOTSUP`, no effect (`EEXIST` if the target exists) | moves refused `REFUSE_PLATFORM`; the SDK's own scaffold already refuses there |
| Linux 6.12, glibc 2.41, `renameat2(RENAME_NOREPLACE)`, uid 1000 | overlayfs, tmpfs, Docker Desktop host bind mount | same as APFS | 292 of 299 cases pass on overlayfs and tmpfs, 7 skipped (they need case or normalization folding) (Python 3.12) |

The 299 cases are the move suite plus the SDK workspace, CLI, public-contract,
and migration suites; the skipped cases test the stored-spelling rule, which
only a folding filesystem can exercise. A host without `renameat2` or `renameatx_np` (Windows,
the BSDs, a C library without the symbol) refuses moves with
`REFUSE_PLATFORM` before planning; a filesystem that cannot honor the flag
(exFAT on macOS, above) refuses at the first rename, which is the marker's, so
nothing moves. Neither case falls back to another primitive.

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
differ. Because move plans do not bind the SDK inventory, a stored inverse
stays valid across SDK updates (tested; round-1 finding 4).

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
  every move. The move marker and its temporary file live under `.rapp-work/`
  and are not inventory entries.
- Legacy workspaces are refused (`REFUSE_SDK_PROFILE`) until the ordinary
  additive update adopts the SDK; after that, moves work and the legacy
  `rappid.json` bytes are untouched (tested). A workspace integrated by another
  SDK release refreshes through its ordinary update first (tested), which may
  run while a move is pending.
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
`protocols/rapp-work-sdk/1/SPEC.md`. No existing sentence is removed or
reworded (`git diff origin/main` of the SPEC has no deleted line). The inserted
§7 sentence qualifies the existing sentence "Updating is additive for legacy
workspaces and limited to SDK-owned integration files for SDK workspaces",
which would otherwise contradict §4.1 (round-1 finding 5).

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
```

Insertion in §7, after "Updating is additive for legacy workspaces and
limited to SDK-owned integration files for SDK workspaces.":

```text
An `update` move plan (§4.1) is not an integration update. It relocates
existing files inside an SDK Workspace or Organization, never writes,
replaces, or removes an SDK-owned file, and writes only its own recovery
marker.
```

Static API metadata (`src/rapp_work/data/api.json`, `rapp-work-static-api/1`,
whose shape is unchanged) lists the two new optional `update` inputs and adds
the refusal "replacing, cross-filesystem, or protected-path moves".
`docs/API.md`, `docs/ARCHITECTURE.md`, `README.md`, `protocols/README.md`, and
`CHANGELOG.md` (`## Unreleased (proposal, not accepted)`) describe the change.

## Token and compatibility analysis

- **New tokens:** `rapp-work-move-plan/1` and `rapp-work-move-recovery/1`
  (drafts; neither has been released).
- **Unchanged tokens:** `rapp-work-release-plan/1` (the fixed vector below
  hashes identically on `main` and on this branch), `rapp-work-signed-release/1`,
  `rapp-work-update-recovery/1`, `rapp-work-managed-files/1`, the
  `rapp-work-sdk/1` integration record and `schema.json`, `rapp-work-result/1`,
  `rapp-work-static-api/1` (content only), and every RAPP/1 form. Article 18
  (frozen wire) and Article 10 (one canonicalizer) are untouched: plans hash
  with the pinned canonicalizer, and the eleven-key Frame is not involved.
- **Accepted paths unchanged:** `apply_update`, `plan_update`, and every other
  existing operation path are byte for byte as on `main`; `workspace.py` is not
  modified.
- **Old SDKs fail closed.** Evidence, run in memory against an archive of
  `origin/main` on Python 3.13 and 3.10 with the round-2 plan shape:

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
  to `7b3ceacf4f57d11b1f9bc27f14d70b4f713743460b4b35e0a464dc85f1c5dde1`
  in `protocols/index.json` and `src/rapp_work/data/profiles.json`, and
  `RELEASE-INVENTORY.json` is regenerated. The `generated_utc` of
  `protocols/index.json` is left as is. The signed `registry.json`, root
  `SPEC.md`, the `rapp-hive/1` and `rapp-federation/1` SPECs,
  `RAPP1_PIN.json`, `RAPP_WORK_PIN.json`, and every signature are untouched,
  so no re-signature is needed and `tools/check.py` stays green.

## Security and privacy analysis

- **No lost bytes:** no step of a move unlinks or replaces a name of a file it
  moves; a no-replace rename can never make a file unreachable. Concurrent
  writers can make an apply refuse, and the move is then undone, but they can
  never make the SDK destroy a version (race matrix above; mutations M23 to
  M26).
- **Escape and traversal:** only canonical relative paths; every directory is
  opened component by component with `O_NOFOLLOW | O_DIRECTORY` from the
  root, each file is opened with `O_NOFOLLOW` and matched by `fstat` identity
  to its `lstat`, and the rename works on the verified directory descriptors
  and never follows a link. Symlinked roots, parents, sources, and
  destinations are refused (M6).
- **Clobbering:** the destination is created only by the no-replace rename; a
  destination that appears at any moment is refused and kept (tested with a
  race injected immediately before the rename; M10, M14).
- **Authority and instructions:** identity, Organization, workspace SPEC,
  hidden, SDK-owned, kernel, and AI instruction paths can be neither moved nor
  created by a move, so a move cannot turn someone else's text into an
  instruction file or remove the workspace's own instructions. The lexical
  rule is backed by file identity: a source that is another name of a
  protected file is refused, and a destination that turns out to be another
  name of a protected name is undone (M32 to M34).
- **Aliasing evidence:** an exhaustive probe of every code point from U+0080
  to U+10FFFF (surrogates excluded) against one- and two-letter ASCII names and
  against ignorable insertion found: APFS (case-insensitive) ignores none and
  folds ß, ẞ, ſ, the Kelvin sign, and five Latin ligatures onto ASCII; HFS+
  ignores exactly U+200C to U+200F, U+202A to U+202E, U+206A to U+206F, and
  U+FEFF; the macOS exFAT driver folds the Kelvin sign and maps U+F029 to `.`.
  Every one of them is refused or folded by the rule on Python 3.10 (Unicode
  13.0) and 3.13 (Unicode 15.1). The hard-coded `Default_Ignorable_Code_Point`
  ranges equal Unicode 15.1 `DerivedCoreProperties.txt` (4,174 code points).
  On the HFS+ image, the review's three attacks (`AGENTS<U+200C>.md`,
  `rappid<U+200C>.json`, `<U+200C>.rapp-work/sdk.json`) are refused with
  `REFUSE_PATH`; with the lexical rule switched off by instrumentation, the
  identity checks still refused the source alias and undid the destination
  alias (round-1 finding 3).
- **Review integrity:** bidi controls and invisible characters are refused, and
  refusals echo such paths only in the visible `<U+XXXX>` form.
- **Names:** every existing entry a plan names is spelled exactly as stored,
  and a destination the filesystem would store under another spelling is
  undone, so a plan and its inverse restore every name exactly and a reviewed
  path is the name on disk (M40, M41).
- **Boundaries:** one root, one filesystem, no nested identity or repository
  roots, and no directories; world and Organization boundaries are unchanged.
- **Hardlinks and special files:** sources must be single-link regular files
  owned by the user, without special mode bits; FIFOs, sockets, devices, and
  directories are refused before they are opened.
- **Execution:** the SDK never imports or executes a moved file. Moving an
  agent into the top of a Brainstem's `agents/` makes the Brainstem load it;
  that is the person's explicit, exact-hash adoption step.
- **Concurrency of SDK applies:** the marker is placed complete and locked,
  and a resume proves after locking that the marker name is still the file it
  locked, so two applies never run on one marker (M22, M27).
- **Durability:** every rename, undo, marker placement, and marker removal is
  followed by `fsync` of the affected directories. On macOS, `fsync` does not
  force the drive cache (`F_FULLFSYNC` would); the SDK uses `fsync`
  everywhere, as today.
- **Privacy:** plans and markers stay local. They carry relative paths,
  hashes, byte lengths, modes, the root's absolute path, and its device and
  inode numbers (as update plans already do), but no file bytes, network
  locations, or credentials. The marker is mode 0600 under `.rapp-work/`. No
  operation uses a network.

Residual risks, stated precisely:

- Removing the marker is an identity check followed by `unlinkat`. A program
  other than the SDK that renames its own file over the reserved
  `.rapp-work/move-recovery.json` in that instant would lose that file. No SDK
  apply can do so: none can place a marker while one exists.
- Crash atomicity of a rename is the filesystem's (journaled filesystems make
  it atomic); after a power loss on a filesystem without a journal, a rename
  may need `fsck`.
- Effects are descriptor-relative: if another process moves a parent
  directory during an apply, the move happens inside the directory that was
  verified, wherever it now is.
- The lexical rule was verified exhaustively for single code points on APFS,
  HFS+, and exFAT. On other filesystems, fixed protected names are also
  guarded by the identity checks; suffix-pattern names and hidden directories
  rely on the lexical rule alone.
- A move is not a transaction against concurrent writers of its source. From
  the rename until the arrival check completes, the destination holds whatever
  the source name held at the rename; if another process replaced or edited
  the source after it was pinned, those unreviewed bytes sit at the
  destination until the undo, and a Brainstem that loads agents in that
  instant may run them (round-2 finding 2). The writer is the same user, apply
  still refuses and undoes the move, and no version is lost. A two-step
  variant (rename the source without replacing to a private name in its own
  directory, verify it there, then rename it into place without replacing)
  would close this window at the cost of a third recovery state and a
  private name that a crash can leave behind; open question 13 asks whether
  that is wanted.

## Migration

None is required. Existing Workspaces, Organizations, plans, and recovery
markers keep working unchanged. A workspace that wants moves must pass
`verify` with its SDK integration; a legacy workspace adopts it through the
ordinary update plan first. Callers that never send `moves` or `inverse_of`
see no difference.

## Rollback

Before reverting the branch commits, resume or resolve any pending
`.rapp-work/move-recovery.json` with the proposing SDK. Every file always has
a name (no step removes one), so no bytes can be lost; a leftover marker, or a
leftover `.rapp-work/.move-recovery-*.tmp`, can be removed by hand after
checking the named paths. After a rollback the SDK again refuses `moves`,
`inverse_of`, and move plans with `REFUSE_INPUT_KEYS`. An SDK without this
proposal does not read a move marker; since an ordinary SDK update touches
only SDK-owned files, running it with a pending move is harmless.

## Conformance and test vectors

`tests/test_sdk_moves.py` (pytest, `sandbox` fixture) has 67 test functions
that expand to 267 cases. Fixed vectors:

- **`/1` stability:** the release plan built in
  `test_release_plan_v1_hash_vector_is_unchanged` hashes to
  `196dd7112d6371b94535f7e136dd457491c2efc1c82428ca05bbd9409adb801e`. The
  value was computed with the unmodified `origin/main` code and is unchanged on
  this branch.
- **Move plan:** the two-move plan in `test_move_plan_conformance_vector`
  hashes to
  `84f659901443ab4500d6664db1073e88852bb8236ad621f6938b8ac82f9f3f5c`; its
  inverse hashes to
  `ba4845523f60e4d51d54ffe749ed8b1b2298d0e95e2435cec9c25cf8e77c347b`; the
  inverse of the inverse is the plan, and a plan that still carries the
  round-1 `managed_sha256` precondition is refused. Canonical bytes of the
  plan:

  ```json
  {"moves":[{"bytes":42,"destination":"agents/experimental/example_agent.py","mode":420,"operation":"move","sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","source":"agents/example_agent.py"},{"bytes":7,"destination":"agents/notes_agent.py","mode":384,"operation":"move","sha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff","source":"agents/experimental/notes_agent.py"}],"network":false,"operation":"update","preconditions":{"identity_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","root_identity":{"device":1,"inode":2,"mode":448}},"profile":"rapp-work-sdk/1","protocol":"rapp-work/1","schema":"rapp-work-move-plan/1","subject":{"kind":"workspace","rappid":"rappid:@example/finance:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","world_id":"example-world"},"target":"/example/workspace"}
  ```

Positive vectors: plan-only by default (tree unchanged, no marker); apply with
the exact hash (bytes, mode, and inode preserved, one link, `verify` passes);
a three-move plan (an unload, a load, and a note) and its inverse restore the
exact tree; a stored non-ASCII name round-trips under its stored spelling; the
inverse's own hash is required; redo after undo; every crash
matrix row resumes or refuses exactly; an identical replacement after a crash
counts as moved; a leftover temporary marker never blocks a first apply; an
SDK upgrade during a pending move resumes after the ordinary update, and a
stored undo applies after an SDK update; Organizations keep their pointer
registry byte for byte; legacy and stale integrations work after their
ordinary update; the CLI plans, inverts, and applies; every envelope is
canonical and float-free; default `update` still plans
`rapp-work-release-plan/1`.

Refusal vectors (each asserts that the tree is unchanged or exactly as
documented): wrong hash, missing plan or hash, and plan evidence without
`apply`; source edited, re-moded, removed, or hard-linked after planning; a
same-size edit injected after the replay; a destination file, dangling
symlink, or directory created after planning or immediately before the
rename; every concurrent-writer row of the race matrix; a symlinked source,
source parent, destination parent, or root, and a parent swapped for a
symlink after planning, and a parent swapped for another directory while it
is opened; hard-linked, FIFO, directory, setuid, oversize, and missing
sources; a source or a directory named by another case or normalization of
its stored name, at planning and after a respelling rename between planning
and apply, and a destination that the filesystem stores under another
spelling (undone; on HFS+ for real, elsewhere by instrumentation); 15 unsafe path spellings on each side; 23 invisible,
format, private-use, unassigned, surrogate, and ignorable code points on each
side (also refused by the plan parser) and the review's three HFS+ spellings;
34 protected paths on each side, including `CLAUDE.local.md`,
`AGENTS.override.md`, `basic_agent.py`, and dotless-`ı` spellings; sources
that are another name of a protected file, at planning and on resume; a
destination that becomes a protected name; SDK-owned inventory paths; nested
`rappid.json` and `.git` roots in both directions; missing or non-directory
destination parents; empty, oversized, open, duplicate, chained, swapped,
aliased (case, `ß`, dotless `ı`), identical, and case-only moves; `moves` with
`inverse_of`, either one with `apply`, unknown members, and `moves` on the
other five operations; closed plan parsing (extra key, wrong schema,
`network: true`, no moves, float `bytes`, protected path, unsorted moves, and
a `/1` plan) and the `/1` parser refusing a move plan; a forged re-hashed
plan; replay of an applied plan; an inverse for another root; `inverse_of`,
another move, and another move plan while a move is pending; ambiguous
interrupted states (edited, same-size edit, second link, source reappears,
both missing, source edited before the rename, destination appears before the
rename); a second apply while another holds the marker lock; a stale resume
whose marker was removed or replaced; racing first applies; a marker that
cannot be locked; a marker replaced, or edited in place, during an apply;
foreign or forged markers; an undo that would move another file back (not
reported as undone); a resume whose path the SDK inventory now owns; a
partial multi-move failure; rename errors (`EXDEV`, `EINVAL`,
`ENOTSUP`, `ENOENT`, `EACCES`); a filesystem and a host without a no-replace
rename; another device at planning; and a pending update recovery.

### Mutation proof

Each critical check was mutated locally, its targeted tests were run on
Python 3.13, and the original bytes were restored and verified by SHA-256 and
`git diff`. Every mutation turned its tests red:

| ID | Mutation | Targeted tests |
|---|---|---|
| M1 | apply without the exact plan-hash comparison | red: 2 failed |
| M2 | first apply skips the full precondition replay | red: 5 failed, 2 passed |
| M3 | pinned source SHA-256 not checked just before the rename | red: 2 failed, 6 passed |
| M4 | hard-linked sources accepted at planning | red: 2 failed, 8 passed |
| M5 | protected-path policy disabled | red: 59 failed, 9 passed |
| M6 | move walks, reads, and opens follow symlinks | red: 4 failed |
| M7 | recovery marker accepted without exact plan binding | red: 2 failed |
| M8 | moved recovery state accepted without its SHA-256 | red: 1 failed, 6 passed |
| M9 | inverse does not exchange source and destination | red: 2 failed |
| M10 | replacing rename instead of the no-replace rename (flag dropped) | red: 4 failed |
| M11 | nested identity or repository boundary check disabled | red: 3 failed |
| M12 | spent-plan detection disabled | red: 2 failed |
| M13 | `rapp-work-release-plan/1` widened in place with a `moves` key | red: 1 failed |
| M14 | destination-absence check at planning disabled | red: 3 failed |
| M15 | marker kept even when nothing moved | red: 8 failed |
| M17 | same-filesystem checks disabled | red: 1 failed |
| M18 | setuid, setgid, or sticky sources accepted | red: 1 failed, 5 passed |
| M19 | non-canonical path spellings accepted | red: 8 failed, 22 passed |
| M20 | chained, swapped, or aliased moves accepted | red: 5 failed, 9 passed |
| M21 | `moves` or `inverse_of` accepted together with `apply` | red: 1 failed |
| M22 | a locked (busy) recovery marker is resumed anyway | red: 1 failed |
| M23 | arrival identity check disabled (a swapped source is accepted) | red: 2 failed, 4 passed |
| M24 | arrival SHA-256 check disabled (an in-place edit is accepted) | red: 1 failed, 5 passed |
| M25 | arrival link-count, mode, and owner check disabled | red: 2 failed, 4 passed |
| M26 | undo rename disabled (a raced move stays at the destination) | red: 7 failed |
| M27 | marker identity not re-checked after the lock (stale resume runs) | red: 2 failed |
| M28 | marker identity not re-checked before removal | red: 1 failed |
| M29 | marker written in place instead of renamed into place | red: 1 failed, 1 passed |
| M30 | invisible, ignorable, and unassigned code points accepted | red: 49 failed |
| M31 | upper-case round trip dropped from the fold (dotless `ı` aliases) | red: 7 failed, 75 passed |
| M32 | source alias identity check at planning disabled | red: 4 failed |
| M33 | source alias identity check before the rename disabled | red: 1 failed |
| M34 | destination alias identity check after the rename disabled | red: 1 failed |
| M35 | `inverse_of` planned while a move is pending | red: 1 failed |
| M36 | platform check ignores a missing no-replace rename | red: 1 failed |
| M37 | an unsupported no-replace rename is not a platform refusal | red: 2 failed, 3 passed |
| M38 | SDK update refused while a move is pending (round-1 guard restored) | red: 2 failed |
| M39 | move plans bind the SDK inventory bytes (a stored undo expires) | red: 1 failed |
| M40 | existing entries not checked for their stored spelling (planning, replay, resume) | red: 6 failed |
| M41 | the destination's stored spelling not checked after the rename | red: 1 failed |
| M42 | an undo reported verified without comparing identities | red: 1 failed |
| M43 | a parent's identity not re-checked after it is opened | red: 1 failed |
| M44 | the marker's bytes not re-checked before its removal | red: 1 failed |
| M45 | SDK-owned paths not checked on resume | red: 1 failed |

Round 3 reran M1 to M39 on the final code with the same results and added
M40 to M45 for the stored-spelling rule and the four checks the round-2 review
found untested. M16 of round 1 ("SDK update apply allowed while a move
recovery is pending") is retired: that refusal was removed by design, and M38 now proves the
opposite property. The cases that stay green under a mutation are refused by
an independent layer or do not exercise the mutated check, which is intended
defense in depth: M2's content changes are also caught by the per-move state
check, M3 and M8 only matter for same-size edits, M5's SDK-owned paths are
caught by the inventory check, M19's other spellings by `safe_relative`, M23
to M25 each own the race rows they are named for (the others are caught by the
remaining arrival checks), M29's in-process variant cleans up in both designs
while its process-death variant turns red, M31 only matters for dotless `ı`,
M37's other errors have their own codes, and M4, M18, and M20's other cases
are refused by their own checks. Two properties are reviewed rather than
mutation-tested: the `fsync` ordering (power loss cannot be simulated in a unit
test) and the owner check (tests cannot create files owned by another user
without privileges).

## Reference implementation and gating

- `src/rapp_work/plans.py`: `FileMove` and `MovePlan` (closed parsing, bounds,
  the code-point rule, the fold, the protected-path policy, and the inverse).
  They stay in `rapp_work.plans`; the top-level `__all__` is unchanged.
- `src/rapp_work/moves.py`: `plan_moves`, `invert_move_plan`,
  `apply_move_plan`, the descriptor-relative walk, the no-replace rename
  wrapper, the pinned-source verification, arrival verification and undo, the
  identity alias checks, the state classifier, and the marker protocol.
- `src/rapp_work/api.py`: `update`'s two optional members and schema dispatch.
- `src/rapp_work/cli.py`: `--move` and `--inverse-of`.
- `tests/test_sdk_moves.py`.

Gating: the behavior is reachable only through the new `moves` and
`inverse_of` members or a plan whose schema is `rapp-work-move-plan/1`, and
the branch's SPEC text describes it. `update` without those members behaves
exactly as accepted: no existing code path changed, and the full pre-existing
suite passes unchanged. Defaults remain plan-only, offline, credential-free,
and refusing.

Checks: the local mirror of the `conformance` workflow (`tools/check.py`,
`pytest -q`, `ruff check`, `mypy`, `release_inventory.py --check`, `build`,
and `verify_package.py`) passes on Python 3.13 and on Python 3.10: 435 tests
passed and 1 skipped, with 69 subtests (the 169 pre-existing tests plus the
267 new cases), an inventory of 147 files, a wheel of 114 files, and an sdist
of 156 files. The 299-case subset in the platform table also passes on an
HFS+ disk image (Python 3.13) and on Linux overlayfs and tmpfs (Python 3.12,
uid 1000), with the skips listed there.
GitHub CI does not run for branch pushes in this repository.

## Open questions for the owner

1. Accept the additive widening of `rapp-work-sdk/1`'s `update` input, or
   publish the same text as `rapp-work-sdk/2`?
2. Is the protected set right? It deliberately refuses `.github/**` (skills,
   workflows, and instructions), `soul.md`, root `SPEC.md`, and
   `basic_agent.py`. Unloading a skill by a move would need a later decision,
   as would protecting further Grail kernel files if a Brainstem folder becomes
   an SDK root.
3. Should a later token allow a bounded creation of missing destination
   parents, removed by its inverse only when empty?
4. Should move plans be signable, like `rapp-work-signed-release/1`, for Hive
   or multi-device use?
5. Should `status` report a pending move or update recovery marker, and
   should the scaffold `.gitignore` template ignore
   `.rapp-work/move-recovery.json` and `.rapp-work/.move-recovery-*.tmp` as it
   ignores the update marker? Both change accepted outputs, so neither is done
   here.
6. Replay: is refusal with `REFUSE_PLAN_APPLIED` preferred over an `ok`
   `unchanged` result?
7. Case-only renames are refused everywhere because they alias on
   case-insensitive filesystems. Allow them where the filesystem is
   case-sensitive?
8. G17 and G22: how does the Brainstem address its own `agents/` folder as an
   SDK root, for example by making the Brainstem data directory a Workspace?
9. Export `FileMove` and `MovePlan` at the top level?
10. Hosts that this implementation does not bind (Windows and the BSDs) and
    filesystems without a no-replace rename (such as exFAT on macOS) refuse
    moves. Is a rename-aside fallback (option D) wanted
    there despite its weaker guarantee? The recommendation is no.
11. Should the protected instruction names be defined by reference to G7's
    `rapp-work-instruction-set/1` and its successors instead of being listed
    here, once G7 is accepted?
12. Should a later operation help the owner abandon a refused interrupted move
    (today the owner checks the named paths and removes the marker by hand)?
13. Should moves stage each file under a private name before renaming it into
    place, so that bytes changed by a concurrent writer are never visible at
    the destination, even briefly (Residual risks)? That adds a third recovery
    state; the recommendation is to keep one rename per move.

## Owner actions needed

1. Decide on the §2, §4, and §7 text, or on the `rapp-work-sdk/2`
   alternative.
2. If accepted, merge the branch. If it is merged together with other
   `rapp-work-sdk/1` gap branches, follow "Related proposals" below: recompute
   the SDK SPEC hash in `protocols/index.json` and
   `src/rapp_work/data/profiles.json` and run
   `python3 tools/release_inventory.py --write`.
3. Release as 1.1.0: bump `pyproject.toml`, `SDK_VERSION`, and the version
   checks in `tools/verify_package.py`, `tools/release_inventory.py`, and
   `docs/RELEASE.md`.
4. Relay G2's new status (proposed) to the organism.

No registry signature, owner anchor, or Grail byte is affected.

## Related proposals

Sibling drafts on `kody-w/rapp-work` touch the same files (none of them is
edited here):

| Gap | Branch | Overlap with this branch |
|---|---|---|
| G3 | `experimental/gap-g3-agent-discovery` | SDK SPEC §11; the SPEC hash pins and inventory |
| G4 | `experimental/gap-g4-migration-successors` | `api.py`, `cli.py`, `data/api.json` (other operations); the inventory |
| G6 | `experimental/gap-g6-owner-succession` | SDK SPEC §5.1 and §12; the SPEC hash pins and inventory |
| G7 | `experimental/gap-g7-instruction-inventory` | SDK SPEC §4 (its paragraph follows the first paragraph, before "Create-only means"; this proposal's insertion follows the second), §7.1 to §7.6 (after both §7 paragraphs; this proposal's §7 sentence ends the first), and §12; `api.py` (it rewrites the same `_update` planning lines, with `plan_update_with_review` and `instruction_review`), `cli.py`, `data/api.json` (the same refusal list), `workspace.py`, `_paths.py` (it refactors `read_regular`, which `moves.py` imports, into `read_regular_at` without changing its behavior), `README.md`, and `protocols/README.md`; the pins and inventory |
| G11 | `experimental/gap-g11-workspace-index` | none in the SDK SPEC |
| G17 | `experimental/gap-g17-brainstem-sdk-agent` | consumes move plans to load and unload agents |

Every SDK SPEC edit here is an insertion, so the drafts compose textually.
G7's §4 paragraph and this proposal's §4 insertion follow different
paragraphs of §4, and G7's §7.1 to §7.6 follow the second paragraph of §7
while this proposal's sentence ends the first, so the two SPEC texts merge
without a conflict. A merged `_update` keeps G7's `instruction_review` for
ordinary updates and sends `moves`, `inverse_of`, and move plans to this
proposal's path first. Both G6 and G7 keep the words "source deletion" in
§12, to which §4 refers. This proposal's protected set contains every G7
instruction path, so a move can never change G7's instruction inventory.
Recommended order: G7, then G2, then G17 (which calls move plans); G3, G4, G6,
and G11 are independent of G2 and may land in any order. After each merge,
recompute the SDK SPEC hash in `protocols/index.json` and
`src/rapp_work/data/profiles.json`, regenerate `RELEASE-INVENTORY.json`, and
resolve the `api.py`, `cli.py`, and `data/api.json` hunks by keeping every
branch's members.

## Ready-to-file pull request text

Title: `rapp-work-sdk/1: exact, reversible move plans (proposal 0002, G2)`

Body: "Adds `rapp-work-move-plan/1`, planned and applied by `update` through
the optional closed members `moves` and `inverse_of`. Each move is one
verified, descriptor-relative no-replace rename (`renameat2(RENAME_NOREPLACE)`
or `renameatx_np(RENAME_EXCL)`), undone if another program changes the source
meanwhile, so no version of a file can be lost; hosts without such a rename
refuse moves. A plan-bound `rapp-work-move-recovery/1` marker makes an
interrupted apply resumable, and the inverse is its own exact-hash plan.
`rapp-work-release-plan/1` is unchanged (fixed vector), old SDKs refuse the
new token, `apply_update` is unchanged, and the SDK SPEC pins are updated. See
`docs/proposals/0002-sdk-move-action.md` for the rationale, race and crash
matrices, vectors, and mutation results."

## Revision history

- **Round 1** (`e6361ce`): link, verify, unlink under a locked marker.
- **Round 2** (`5d5a043`), answering the round-1 independent review:
  1. (high) Moves use one verified no-replace rename with undo instead of
     link-then-unlink, so a concurrent atomic save can no longer be deleted;
     race and crash matrices are specified and tested.
  2. (medium) A resume re-checks after locking that the marker name is still
     the locked file; the marker is renamed into place complete and locked.
  3. (medium) Paths with invisible, format, private-use, unassigned,
     surrogate, or `Default_Ignorable_Code_Point` code points are refused;
     the fold also joins dotless `ı`; identity checks back the lexical rule.
  4. (medium) An ordinary SDK update may run while a move is pending, and move
     plans no longer bind the inventory, so a pending move resumes and a stored
     undo applies after an SDK upgrade; `workspace.py` is unchanged.
  5. (medium) §7 gains a qualifying sentence, quoted above.
  6. (low) `inverse_of` is refused while a move is pending, as the text says.
  7. (low) The partial-marker window is closed by writing privately and
     renaming into place.
  8. (low) The protected set adds `AGENTS.override.md`, `CLAUDE.local.md`, and
     `basic_agent.py`, contains every G7 instruction path, and the claim is
     stated as that closed list.
- **Round 3** (this revision), answering the round-2 independent review:
  1. (medium) Every existing entry a plan names must be spelled exactly as
     its directory stores it (§4.1 item 10, `REFUSE_PATH_SPELLING`), and a
     destination the filesystem stores under another spelling is undone, so
     a plan and its inverse restore every name exactly on case- and
     normalization-insensitive filesystems (tested on APFS and HFS+).
  2. (low) The brief exposure of a concurrent writer's bytes at the
     destination is stated in §4.2, the race matrix, and the residual risks,
     with open question 13 on staging.
  3. (low) Tests and mutations M42 to M45 now cover the undo identity check,
     the parent identity check after open, the marker bytes check before
     removal, and SDK-owned paths on resume.
  4. (low) The G7 row of "Related proposals" names every shared file and
     the real §4 and §7 anchors.

## References

- `protocols/rapp-work-sdk/1/SPEC.md` §§2, 4, 7, 10, and 12.
- `src/rapp_work/plans.py`, `moves.py`, `workspace.py`, `api.py`, `_paths.py`,
  and `cli.py`.
- `kody-w/rapp-1` `CONSTITUTION.md`, Articles 2, 4, 8, 10, and 18.
- Organism (`kody-w/rapp-work`, branch `experimental/rapp-work-constitution`):
  `organism/gaps/G02.md`, `organism/gaps/G17.md`, `organism/gaps/G22.md`,
  `organism/invariants.md`, `organism/crossings/brainstem-workspaces.md`, and
  `organism/parts/workspaces.md`.
- Grail kernel `load_agents()` flat glob: `kody-w/rapp-installer`
  `rapp_brainstem/brainstem.py` at `brainstem-v0.6.9`, as cited by the
  organism's invariant.
- Linux `renameat2(2)` (`RENAME_NOREPLACE`) and macOS `renameatx_np(2)`
  (`RENAME_EXCL`, `VOL_CAP_INT_RENAME_EXCL`); POSIX `fsync(2)` and `flock(2)`.
- Unicode Standard Annex #44 and Unicode 15.1 `DerivedCoreProperties.txt`
  (`Default_Ignorable_Code_Point`); Unicode `CaseFolding.txt`.
- Git's handling of HFS+ ignorable characters and case-insensitive aliases of
  `.git` (CVE-2014-9390), a precedent for refusing ignorable code points in
  protected names.
- Sibling proposals: `experimental/gap-g7-instruction-inventory`
  (`rapp-work-instruction-set/1`) and the branches in "Related proposals".
