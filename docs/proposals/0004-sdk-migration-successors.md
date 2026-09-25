# 0004 — Pointer-only migration successors for repository-seeded Hives and long world ids

| Field | Value |
|---|---|
| Status | **Draft, not accepted.** A proposal on branch `experimental/gap-g4-migration-successors`. Nothing here is activated; the owner decides what moves. |
| Gap | **G4**: SDK migration refuses repository-seeded Hives and world ids over 64 characters. |
| Home spec | [`rapp-work-sdk/1`](../../protocols/rapp-work-sdk/1/SPEC.md) §10 (Migration), with §12 (Refusals). The 64-character caps named by the gap are in [`rapp-hive/1` `schema.json`](../../protocols/rapp-hive/1/schema.json) `$defs/label` and in `src/rapp_work/migration.py` (`_source_identity`). |
| Blocks | Workspaces. |
| Intended release | `rapp-work` **1.1.0** (a minor release: an additive, opt-in API). The package version and `SDK_VERSION` are unchanged on this branch. |
| Reference implementation | Yes, opt-in only (section 10). Without the new input, the SDK 1.0.0 code runs; section 9.3 lists every observable difference. |
| Revision | Round 2, after independent review G4-r1. The round-1 default enforcement of a 64-character world id outside the pointer path is withdrawn and reported as pre-existing drift (section 13). |

## 1. Summary

`rapp-work migrate` cannot bring along a Private Hive that was seeded from a
repository, because such a Hive has no workspace identity file
(`rappid.json`). It also refuses any source whose world id is longer than 64
characters, while RAPP Workspace/1 allows world ids of up to 128 characters
and seeded Hives in the wild use world ids longer than 64 characters.

This proposal adds one explicit, opt-in successor form to `migrate`: a
**pointer-only successor**. It records where the source is, what the source
says it is, and the exact bytes of the source's authority files, and nothing
else. It copies no Hive state, key, history, frame, GODD, credential, prompt,
or instruction file, mints or derives no identity, and never writes the
source. The existing plan-hash gate, source-binding rechecks, recovery marker
and read-only completed replay all apply unchanged.

World ids of up to 128 characters become lawful in exactly one place: the
three new pointer-successor tokens, where the world id is a *legacy source
identifier* recorded verbatim. No existing token is widened, and nothing
outside the opt-in changes: `rapp-hive/1`, canonical `rapp-work/1`, the
`rapp-work-sdk/1` record, SDK workspace identities and Organization pointers
keep exactly the grammar and enforcement they have in SDK 1.0.0.

Without the new `successor` input, `migrate`, `update` and `verify` behave
exactly as on `main`. `status` and `discover` differ only in the static API
metadata they return, which now lists the two optional `migrate` inputs, and
the CLI differs only in the message it gives for `--hive` without
`--successor` (section 9.3).

## 2. Context: what is true today

References are to `kody-w/rapp-work` `main` at `29ead23`, unless stated.

### 2.1 Migration today

- `rapp-work-sdk/1` [SPEC.md](../../protocols/rapp-work-sdk/1/SPEC.md) §10:
  "A `MigrationPlan` is source-bound and create-only. It preserves the source
  and creates a successor integration workspace or Organization without
  rewriting the source identity, Frames, keys, histories, Private Hive state,
  plugins, skills, or neurons." §7: "A Workspace has one existing or mint-once
  RAPPID and one hard `world_id`."
- `src/rapp_work/migration.py` `_source_identity` (lines 43–91) reads
  `rappid.json` unconditionally (line 44), defaults `schema`, `kind`
  (`workspace`) and `mode`, takes `world_id` from `rappid.json` or else from
  `.rapp-hive/declaration.json`, and requires the SDK label grammar
  `[a-z0-9]+(?:-[a-z0-9]+)*` with `len(world_id) <= 64` (lines 64–70).
- `source_binding` (lines 94–130) binds the allowlisted
  `SOURCE_AUTHORITY_PATHS` (lines 29–40) that exist, and requires
  `rappid.json` among them.
- `_migration_files` (lines 321–354) re-emits the source's **own** RAPPID,
  kind, world, name and mode as the successor's `rappid.json`, adds the SDK
  template (README, `CLAUDE.md` with the world id interpolated, SPEC, HOME,
  `.gitignore`), the SDK integration files, and
  `.rapp-work/migration-source.json`
  (`rapp-work-migration-source-pointer/1`).
- `docs/MIGRATION.md` describes the same contract.

The successor therefore *is* the source workspace under the SDK profile. There
is no successor form for a source that has no workspace identity.

### 2.2 Reproduction and root cause

The reproduction used synthetic, local-only sources built from minted test
keys, including the historical `rapp-private-hive` skill through
`rapp_work.compat`. The test module
[`tests/test_sdk_migration_pointer.py`](../../tests/test_sdk_migration_pointer.py)
rebuilds every case.

| Source (synthetic) | `migrate` plan on `main` | Refusing check |
|---|---|---|
| S1: a Git working tree with `rappid.json`, prepared by the historical skill (`prepare_workspace.py prepare`, `.rapp-hive/` sidecar) | **planned** (not refused) | none: it is a workspace |
| S2: a checkout of the Private Hive publication that the skill deploys to its authority channel (`objects/`, `chains/`, `refs/current.json`, a signed `hive.declaration` genesis frame), as a Git working tree | refused `REFUSE_PATH_UNSAFE` | `plan_migration` → `source_binding` → `_source_identity` line 44 → `read_regular(root / "rappid.json")` |
| S2m: a member's copy materialized from that channel | refused `REFUSE_PATH_UNSAFE` | same |
| S3: a repository-seeded Hive: an owner card (`rapp-work-anchor/1`), a policy, signed join-request frames, a seed record, content, a Git index | refused `REFUSE_PATH_UNSAFE` | same |
| W: `rappid.json` with a 65, 80, 128 or 129-character world id | refused `REFUSE_MIGRATION_SOURCE` | `_source_identity` lines 64–70 |
| W: a world id from `.rapp-hive/declaration.json` of 80 characters | refused `REFUSE_MIGRATION_SOURCE` | same |
| W: a Workspace/1 text world (`Example World`) or a `rapp-hive/1`-valid label with a double hyphen (`example--world`) | refused `REFUSE_MIGRATION_SOURCE` | same |
| W: a 64-character world | planned | none |

Root causes:

1. **No successor form without a workspace identity.** Migration assumes the
   source is a Workspace or Organization and that its successor re-emits the
   source RAPPID. A Hive seeded from a repository carries a *Hive* identity
   (in a declaration, an owner anchor, or an unstandardized seed record), not a
   workspace identity. Re-emitting a Hive RAPPID as a workspace identity would
   impersonate the sovereign Hive (`rapp-work/1` §2: organization and Hive
   identities are distinct), and deriving a workspace identity from it is
   forbidden (RAPP/1 Constitution Art. 7). So the refusal is correct today;
   what is missing is a lawful successor form.
2. **The world rule is the SDK label, at most 64.** `_source_identity`
   applies one grammar to every source, including older sources whose own
   protocol allowed 128 characters (section 2.4).
3. **A misleading refusal.** For a missing `rappid.json`, `read_regular`
   opens the file inside `with directory_fd(path.parent)`
   (`src/rapp_work/_paths.py` lines 117–118). The `FileNotFoundError`
   propagates into `directory_fd`, whose handler (line 80) converts it to
   `REFUSE_PATH_UNSAFE` "unsafe or missing directory path" naming the source
   *directory*. The message does not say that `rappid.json` is missing. This
   proposal does not change the default refusal (the regression vector pins
   it) and reports it in section 13.

Checks that do **not** refuse a repository-seeded Hive: `SOURCE_AUTHORITY_PATHS`
(missing files are skipped), `.git` (never inspected), channel records (never
read), and the identity kind (only reached once `rappid.json` exists).

### 2.3 Every 64-character cap on world ids

| Location | Grammar | Governs |
|---|---|---|
| `protocols/rapp-hive/1/schema.json` `$defs/label` | `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$`, 1–64 | Shared by `world_id` of the declaration, shared object, GODD slice, reconciliation, catalog and artifact manifest; channel ids; `authority_channel_id`; room ids; `room_id`; `classification.sensitivity`; `source_channel_ids`; `reason_code`; projection `channel_id` |
| `protocols/rapp-hive/1/reference/rapp_profile.py` `label()` and the vendored copy under `.github/skills/rapp-private-hive/vendor/hive/` | same | The reference validator |
| `.github/skills/rapp-private-hive/schemas/deployment.schema.json` `$defs/label` | same pattern | The deployment owner anchor's `world_id` |
| `.github/skills/rapp-private-hive/scripts/prepare_workspace.py` (`control_files` lines 454–460, `command_prepare` lines 611–617) | SDK label, at most 64 | Hive preparation and its control-file check |
| `.github/skills/rapp-workspace-manager/scripts/manage.py` `validate_label` (line 55) | SDK label, at most 64 | The historical workspace manager |
| `protocols/rapp-federation/1/schema.json` `$defs/label` | `^[a-z0-9]+(?:-[a-z0-9]+)*$`, at most 64 | `party.world_id`, `cell.world_id` |
| `src/rapp_work/migration.py` `_source_identity` lines 64–70 | SDK label, at most 64 | Migration sources |
| `src/rapp_work/workspace.py` `_label` (line 38, default 64; used at line 180) | SDK label | `scaffold` |
| `src/rapp_work/workspace.py` `load_identity` (line 369) and Organization pointers (line 877) | SDK label, **no length cap** | `status`, `verify`, `update`, Organization registry (section 2.5) |
| `protocols/rapp-work-sdk/1/schema.json` `world_id` | SDK label, `maxLength: 64` | The `rapp-work-sdk/1` record (`.rapp-work/sdk.json`) |
| canonical `rapp-work/1` `schema.json` `$defs/label` (`kody-w/rapp-1` `591e014`; mirror `src/rapp_work/data/rapp-work-1-schema.json`) | `rapp-hive/1` pattern, 1–64 | `organization.world_id`, `migrationSource.world_id`, `catalogItem.id`, `migration.catalog_item_ids` |
| RAPP/1 `SPEC.md` §6.1.1 `lclabel` | 1–64 | Stream instances and kind labels (not world ids) |

Two grammars coexist: the `rapp-hive/1` and canonical label allows consecutive
hyphens (`a--b`); the SDK and federation label does not.

### 2.4 Where longer world ids come from

- **RAPP Workspace/1** (`kody-w/rapp-workspace` `main` `52d4f19`):
  `protocols/rapp-workspace/1/schemas/seed.schema.json`,
  `workspace-binding.schema.json`, and `common.schema.json`
  (`$defs/frontier.world_id`, composite `child_world_id`) define `world_id` as
  1–128 characters matching `^[^\u0000-\u001f\u007f]*$`: any text without C0
  controls or DEL, not a lowercase label.
- **The `rapp-work-sdk/1` sidecar hosted in `kody-w/rapp-workspace`**
  (`protocols/rapp-work-sdk/1/schemas/install.schema.json` `$defs/world`, and
  its discovery "Hive endpoint" entries): 1–128 characters without controls.
  (This is a different shape under the same token as this repository's
  profile; see section 13.)
- **The frozen `rapp-hive/2` research draft** (`kody-w/rapp-workspace` branch
  `experimental/frontier-rapp-hive-2`, frozen at `b0d0f07`): commit `aa9af2b`
  records that a dry run against a real repository-seeded Private Hive found
  "world_id may be up to 128 characters, as in RAPP Workspace/1 (seeded Hives
  use long world ids)"; its anchor allowed a 128-character lowercase label
  with `-`, `.` and `/` separators. This proposal's vectors use a synthetic
  80-character world id for that case.

The historical skills could never produce a long world id themselves: both
versions of `prepare_workspace.py` cap world ids at 64.

### 2.5 A pre-existing mismatch that this proposal does not change

`load_identity` checks `LABEL.fullmatch(world_id)` with no length cap
(`workspace.py` line 369), and so do Organization pointer entries (line 877).
On `main`, for a workspace whose `rappid.json` has an 80-character label world
id, `update` plans and applies `.rapp-work/sdk.json` with that world id, which
`protocols/rapp-work-sdk/1/schema.json` forbids (`maxLength: 64`); `verify`
then verifies the workspace with its full managed-file checks, and refuses
tampered SDK files (`REFUSE_MANAGED_DRIFT`) or a missing integration
(`REFUSE_SDK_PROFILE`).

Round 1 of this proposal enforced the 64-character cap in `load_identity` and
Organization pointers by default. That is withdrawn. It was not needed by the
pointer path, it changed accepted default behavior outside G4
(`rapp-work-sdk/1` §7: "Updating is additive for legacy workspaces"), and it
made `verify` fall back to its identity-only legacy path (`api.py` lines
125–143), so a tampered `.rapp-work/sdk.json` or SDK skill file of an already
integrated workspace verified instead of being refused (review finding 1).
`workspace.py` is byte-identical to `main` on this branch. The mismatch is
reported in section 13 with a narrowly scoped candidate fix for the owner, and
a regression test pins SDK 1.0.0's fail-closed `verify` for such workspaces.

## 3. Design

### 3.1 Constraints

- **Art. 2 (one label, one shape).** Widening `$defs/label`, the
  `rapp-work-sdk/1` record or canonical `rapp-work/1` labels in place would
  make an old verifier refuse a new artifact under the same label. It is
  forbidden. Every new shape gets a new token; every old token keeps verifying.
- **Art. 7 (minted, never derived).** A successor MUST NOT derive a
  workspace identity from a Hive RAPPID or a name, and a world id MUST NOT be
  derived, hashed, truncated or normalized from a longer one.
- **Art. 4 and 18.** No new operation, envelope, frame or door. `migrate`
  stays one of the six operations.
- **`rapp-work-sdk/1` §2–§4.** Plan by default; exact plan SHA-256 to apply;
  every precondition replayed before the first write; offline, no ambient
  credentials; descriptor-relative no-follow reads and writes.
- **`rapp-work/1` §3 and `rapp-hive/1` §3.** World ids are hard boundaries; a
  locator is transport metadata, never identity.
- **The SDK must not implement a second Private Hive** (`AGENTS.md`): it must
  not authenticate or replay Hive history itself.
- **Accepted behavior stays.** A specification change is proposed, never
  silently activated: without the explicit opt-in, every accepted behavior of
  `migrate`, `status`, `verify`, `update` and the Organization registry stays
  as it is.

### 3.2 Options for world ids up to 128

| Option | Lawful now? | Assessment |
|---|---|---|
| A. Widen `$defs/label` (and the SDK record, canonical labels) to 128 in place | **No** | Violates Art. 2; the shared label also governs channel, room and reason-code ids; `rapp-hive/1` `SPEC.md` is pinned by the signed registry. Rejected. |
| B. New `rapp-hive/1` payload tokens, or a `rapp-hive/2` | Only by the Hive owner | Needs new signed-registry kinds and an owner re-signature; `rapp-hive/2` is frozen as research ("Never activate"). Proposed as an owner decision only (section 12). |
| C. A new world grammar only inside newly minted SDK tokens used by pointer-only successors | **Yes** | New tokens, no widening; Hive and canonical payloads stay at 64 until their owners revise them. |
| D. Accept 128 only as a legacy source identifier inside the pointer, and refuse to bind such a world into any Hive, Organization or Workspace payload | **Yes** | The narrowest use of C. |
| E. A long-world *workspace* successor (a new SDK integration record, Organization support) | Needs new tokens across workspace, update, status, verify and Organization | Larger than G4; proposed only (section 11, question 4). |

**Recommendation: C restricted to D.** The 128-character grammar exists only in
`rapp-work-pointer-successor/1` and its plan and source tokens, where the world
id is the source's own identifier, recorded verbatim. The successor has no
identity of its own, so it cannot be bound into an Organization, a Hive, or a
`rapp-work-sdk/1` record. This is implemented. Options B and E are left to
their owners.

### 3.3 Why the Hive's identity must be described, not discovered

No closed, accepted token describes a repository-seeded Hive:

- the only closed declaration that names a Hive RAPPID, a world and an
  authority channel is `rapp-hive/1-declaration`, whose world id is at most 64,
  so it cannot carry the longer world ids that seeded Hives use;
- the deployment layer's `rapp-private-hive-owner-anchor/1` names a Hive and a
  world but no channel, and is normally delivered out of band
  (`.github/skills/rapp-private-hive/DEPLOYMENT.md`, "Authority");
- seeded Hives in the wild use unstandardized owner anchors and seed records
  (the frozen `rapp-hive/2` notes that the real one "matched neither
  `rapp-hive/1` nor this draft").

Guessing an identity or a world from unknown files would be derivation.
Authenticating Hive history would be a second Private Hive implementation. So
the SDK takes the Hive RAPPID, world and authority channel from an explicit,
closed description that the operator reviews in the plan, binds it to exact
source bytes, records that the identity came from `operator-description`, and
refuses a description that contradicts a recognized Hive record in those
bytes: a `rapp-hive/1-declaration`, a `hive.declaration` frame carrying one, a
`rapp-private-hive-owner-anchor/1`, or a Private Hive current pointer
(`rapp-private-hive-current/1`).

A checkout of a historical Private Hive publication has no owner anchor, but
its `refs/current.json` is a signed current pointer. When a bound
`refs/current.json` is such a pointer, the SDK follows exactly two
content-addressed references from it: the Mother chain index
`chains/<mother.frame_hash>.json`, and that index's first frame,
`objects/wave/<frames[0]>.json`, which the historical deployment writes as the
Hive's genesis `hive.declaration` frame
(`.github/skills/rapp-private-hive/lib/private_hive/authority.py`,
`bootstrap`). Both files are bound and corroborated, so the description's
Hive, world and authority channel are all checked against the Hive's own
founding declaration. Nothing is verified or replayed; a recognized current
pointer that cannot be followed this way is refused. Corroboration is not
authentication, and the pointer grants nothing.

A source that has `rappid.json` (for example an older workspace with a long
Workspace/1 world id) is not described: its identity, kind and world are read
from that file by the existing source rule, with the legacy world grammar, and
recorded as `source-identity-file`.

### 3.4 The legacy world grammar

`source_world_id` is 1 to 128 Unicode scalar values that

- are not C0 or C1 controls or DEL;
- are not in a fixed list of ranges that Unicode 15.1 (and 16.0) classifies as
  format characters (Cf, which includes every bidirectional control), line or
  paragraph separators (Zl, Zp), or `Default_Ignorable_Code_Point`: U+00AD,
  U+034F, U+0600–U+0605, U+061C, U+06DD, U+070F, U+0890–U+0891, U+08E2,
  U+115F–U+1160, U+17B4–U+17B5, U+180B–U+180F, U+200B–U+200F, U+2028–U+202E,
  U+2060–U+206F, U+3164, U+FE00–U+FE0F, U+FEFF, U+FFA0, U+FFF0–U+FFFB,
  U+110BD, U+110CD, U+13430–U+1343F, U+1BCA0–U+1BCA3, U+1D173–U+1D17A and
  U+E0000–U+E0FFF;
- are assigned in the Unicode database of the implementation that checks them
  (no general category Cn, which also excludes noncharacters); and
- form an NFC string.

That is the RAPP Workspace/1 length and a strict subset of its character rule,
inside the RAPP I-JSON domain (`rapp-hive/1` §14.1). It is text, not a label,
because the older protocols that produced long world ids allow text; refusing
their letters would strand real sources. It is safe to record because the SDK
only compares it for equality and writes it into canonical JSON: never into a
path, a name, an instruction file (`CLAUDE.md` interpolates the world for
workspace successors; pointer-only successors have no such file), or a hash
input that yields another world id.

The excluded ranges are invisible or reorder text, so a reviewed plan cannot
display one world while binding another through them. The rule does **not**
refuse look-alike characters from other scripts (for example a Cyrillic `а`
for a Latin `a`) or non-ASCII spaces: canonical JSON writes non-ASCII
characters raw, so an operator reviewing a non-ASCII world id should inspect
its code points. A world id is compared by exact code points, so a look-alike
never matches the original.

**Version dependence.** The fixed ranges do not depend on the Unicode
database; the assigned-code-point and NFC checks do. By Unicode's stability
policies (an assigned code point is never unassigned, and a string of
characters assigned in one version that is NFC under that version is NFC
under every later one), a world id accepted by an implementation with an
older Unicode database is accepted by every implementation with a newer one.
The converse does not hold: a world id that uses a character assigned after
the older version is refused there. For example, `a` U+1DFA U+0301 is refused
by Python 3.10 (Unicode 13.0: U+1DFA is unassigned) and by Python 3.13
(Unicode 15.1: the string is not NFC). A plan made with a newer database
therefore fails closed, never open, where the database is older.

### 3.5 What a pointer-only successor is

- **Opt-in.** `migrate` input `successor: "pointer-only"` (CLI
  `--successor pointer-only`) at both plan and apply. Without it, `migrate`
  runs the SDK 1.0.0 code and refuses `hive` as SDK 1.0.0 refuses any unknown
  input (`REFUSE_INPUT_KEYS`).
- **Never a Git directory.** A source whose path has a component that names
  `.git` under Git's own HFS+ and NTFS equivalences, or a source that is, or is
  inside, a directory holding entries named `HEAD`, `objects` and `refs`
  (Git's own directory test, by existence only), is refused before anything
  is read.
- **Source classes.** With `rappid.json`: the identity comes from that file
  and must be a Workspace or Organization identity (otherwise the §10 source
  rule refuses it, with or without a description); then a description is
  refused. Without `rappid.json`: a closed `hive` description is required
  while planning, and refused while applying (apply uses the reviewed plan).
- **Bound authority.** For a source with `rappid.json`, the existing
  `SOURCE_AUTHORITY_PATHS`. Otherwise every described path, those present
  among a fixed list of Hive control and authority files (`.rapp-hive/*`,
  `owner-anchor.json`, `registry.json` variants, and the publication pointer
  `refs/current.json`, which commits to the exact published release), and,
  when `refs/current.json` is a Private Hive current pointer, its Mother chain
  index and genesis frame (section 3.3). Each is read without following
  links, must be a regular single-link file of at most 16 MiB, and is recorded
  as `{bytes, path, sha256}`; together they hold at most 64 MiB. No bound path
  has a component that names `.git`: letter case, HFS+ ignorable code points,
  compatibility forms, NTFS trailing dots and spaces, NTFS stream suffixes and
  `GIT~<n>` short names are all folded first. Git internals are never read.
- **Successor bytes.** Exactly three owner-only files (section 4.2). No
  `rappid.json`, no template, no instruction file.
- **Unchanged machinery.** The same exact-hash gate, the same rebinding before
  the first write and again after staging, the same
  `rapp-work-migration-recovery/1` marker and staging name, the same atomic
  no-replace activation, and the same `rapp-work-migration-receipt/1`
  completed replay. The tests change a bound file while staging and swap the
  source for a byte-identical copy between plan and apply; both are refused
  before activation.

## 4. Proposed change

### 4.1 (withdrawn in round 2) `rapp-work-sdk/1` §7

Round 1 proposed a §7 paragraph that made a Workspace or Organization
`world_id` a 1–64 character label for `status`, `verify`, `update` and
Organization pointers, and enforced it by default. It is withdrawn: G4 does
not need it, and it changed accepted behavior (section 2.5). §7 is unchanged
by this proposal. Section 13 reports the underlying mismatch for the owner.

### 4.2 `protocols/rapp-work-sdk/1/SPEC.md` §10: append

> #### 10.1 Pointer-only successors
>
> A pointer-only successor records where a source is and the exact bytes of its
> authority files, and nothing else. It is an explicit opt-in: the `migrate`
> input `successor` MUST equal `"pointer-only"` when planning and when
> applying. Without it, migration follows §10, and a `hive` input is an unknown
> input.
>
> The source MUST NOT be a Git directory or inside one: an implementation MUST
> refuse a source whose path has a component that names `.git` (defined below),
> and a source that is, or is inside, a directory that contains entries named
> `HEAD`, `objects` and `refs`.
>
> The source MUST be one of:
>
> 1. a source with `rappid.json`. It MUST be a Workspace or Organization
>    identity under the §10 source rule, except that its world id follows the
>    legacy world grammar below; its RAPPID, kind and world id are read from
>    that file. A `hive` description is refused; or
> 2. a source without `rappid.json`, such as a Hive seeded from a repository.
>    The planning request MUST include a closed `hive` description with exactly
>    `hive_rappid` (an existing valid RAPPID, recorded verbatim and never
>    minted or derived), `world_id` (legacy world grammar), `authority_channel`
>    (`id`, a `rapp-hive/1` label; `kind`, a `rapp-hive/1` channel kind;
>    `locator`, a credential-free locator), and `authority_paths` (1 to 256
>    sorted, unique, safe relative paths). A `hive` description is refused when
>    applying; apply uses the reviewed plan.
>
> A credential-free locator is 1 to 2048 visible ASCII characters (U+0021 to
> U+007E) without
> `@`, `?`, `#`, `"`, `'`, `\`, `<`, `>`, `` ` ``, `{`, `}`, `[`, `]`, `|` or
> `^`, in one of three forms:
>
> - an `https://` URL: a host of letters, digits, `.` and `-`, an optional
>   port of 1 to 5 digits, and an optional path;
> - an opaque locator `scheme:path`: a scheme of 2 to 32 characters (a
>   lowercase letter, then lowercase letters, digits, `+`, `.` or `-`) that is
>   not `file`, `ftp`, `ftps`, `git`, `http`, `https`, `sftp` or `ssh`, then
>   `:` and a path that does not start with `/`; or
> - a relative locator: one or more `/`-separated segments that contain no
>   `:`.
>
> Path segments use letters, digits and `-._~%!$&()*+,;=`, and `:` outside
> relative locators; no segment is `.` or `..`. A `github` locator is exactly
> `https://github.com/<owner>/<repository>` and does not end in `.git`. A
> locator is transport metadata, never identity or authority.
>
> The legacy world grammar is 1 to 128 Unicode scalar values that form an NFC
> string, are assigned in the implementation's Unicode database, and are
> neither C0 or C1 controls, DEL, nor in the fixed ranges of the
> `legacyWorldId` pattern of `pointer-successor.schema.json` (the Unicode 15.1
> format, line separator, paragraph separator and default-ignorable code
> points). A legacy world id is recorded verbatim. It MUST NOT be normalized,
> truncated, hashed or otherwise used to derive another world id, and it MUST
> NOT be written into a Workspace or Organization identity, a
> `rapp-work-sdk/1` record, an Organization pointer, a `rapp-hive/1` payload, a
> canonical `rapp-work/1` payload, a path, or an instruction file.
>
> The plan (`rapp-work-pointer-successor-plan/1`) binds a
> `rapp-work-pointer-successor-source/1` record: the source path and filesystem
> identity; the source kind, RAPPID, world id, profile and authority channel;
> where the identity came from (`source-identity-file` or
> `operator-description`); the described paths; and the exact byte length and
> SHA-256 of every bound authority file. For a source with `rappid.json` the
> bound files are the §10 allowlisted files that exist. For a source without it
> they are every described path; those present among
> `.rapp-hive/authority.json`, `.rapp-hive/baseline.json`,
> `.rapp-hive/declaration.json`, `.rapp-hive/migration-receipt.json`,
> `.rapp-hive/owner-anchor.json`, `.rapp-hive/registry.json`,
> `.rapp-hive/selection.json`, `.rapp-hive/state.json`,
> `.rapp/registry.json`, `owner-anchor.json`, `rapp/registry.json`,
> `refs/current.json` and `registry.json`; and, when `refs/current.json` parses
> as a `rapp-private-hive-current/1` object, the Mother chain index
> `chains/<mother.frame_hash>.json` and that index's first frame
> `objects/wave/<frames[0]>.json`. `mother.frame_hash` and `frames[0]` MUST be
> 64 lowercase hexadecimal digits, the chain index MUST be a
> `rapp-private-hive-chain/1` object for the pointer's `hive_rappid` whose last
> frame is `mother.frame_hash`, and the first frame MUST be an eleven-key
> RAPP/1 `hive.declaration` frame carrying a `rapp-hive/1-declaration`;
> otherwise the source is refused. These references are followed, not
> verified: nothing is authenticated or replayed.
>
> Authority files are read without following links and MUST be regular,
> single-link files of at most 16 MiB; 1 to 512 are bound, and together they
> hold at most 64 MiB. No bound path may have a component that names `.git`. A
> path component names `.git` if, after removing C0 and C1 controls, DEL and the
> fixed ranges of the legacy world grammar (which include every code point that
> HFS+ ignores), applying NFKC and full case folding, cutting at the first `:`,
> and removing trailing `.` and space characters, it is `.git`, or `git~`
> followed by digits. Git internals are never read.
>
> A description MUST agree with every bound authority file whose path ends in
> `.json` and whose bytes parse as a RAPP I-JSON object that is a
> `rapp-hive/1-declaration`, or an eleven-key RAPP/1 `hive.declaration` frame
> carrying one (same `hive_rappid`, `world_id`, and authority channel `id`,
> `kind` and `locator`); a `rapp-private-hive-owner-anchor/1` (same
> `hive_rappid` and `world_id`); or a `rapp-private-hive-current/1` (same
> `hive_rappid`). Other bound files are opaque bytes. Agreement is
> corroboration, not authentication. A described pointer never becomes Hive
> authority.
>
> The successor contains exactly `.rapp-work/pointer-successor.json` (the
> `rapp-work-pointer-successor/1` record), `.rapp-work/migration-receipt.json`
> and `.rapp-work/migration-recovery.json`, as owner-only files. The record
> repeats the bound source fields and authority commitments, carries the
> canonical SHA-256 of the source binding, and fixes `content_copied: false`,
> `execution: "never"` and `grants_authority: false`. The successor has no
> `rappid.json`: no identity is minted, reused or derived, and it cannot be
> registered in an Organization. It copies no source content, keys, histories,
> frames, GODD, credentials, prompts or instruction files, and the source is
> never written.
>
> The apply gate, the source-binding recheck before the first write and again
> after staging, recovery from an exact plan-bound marker, create-only
> activation, and the read-only completed replay of §10 apply unchanged.

### 4.3 `protocols/rapp-work-sdk/1/SPEC.md` §12: insert after the paragraph

The insertion leaves the existing paragraph untouched, so it composes with
proposals that replace that paragraph (0006, 0007 and 0011; section 14).

> A pointer-only successor without the explicit opt-in, a Hive description
> while applying, a Git directory or a Git-internal path as a pointer-only
> source or its authority, a credential-bearing locator, and a world id outside
> the grammar of the record that would carry it are also explicit refusals.

### 4.4 New token schemas

On acceptance these become `protocols/rapp-work-sdk/1/pointer-successor.schema.json`,
`pointer-successor-source.schema.json` and `pointer-successor-plan.schema.json`.
As with the Hive schemas (`rapp-hive/1` §14.1), apply the RAPP I-JSON domain
first (NFC, no lone surrogates, exact integers); that is why the world pattern
omits the surrogate range. The reference additionally enforces what JSON
Schema cannot express: NFC and assigned code points in world ids; sorted,
unique commitments and described paths; at most 64 MiB in total; the locator
forms; publication following and corroboration; and cross-record equality. The
test suite checks these schemas against the implementation, including exact
equality of the world pattern with the implemented ranges.

<!-- schema: rapp-work-pointer-successor/1 -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/kody-w/rapp-work/protocols/rapp-work-sdk/1/pointer-successor.schema.json",
  "title": "RAPP Work SDK pointer-only successor record (proposed)",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "authority_channel",
    "authority_files",
    "content_copied",
    "execution",
    "grants_authority",
    "identity_source",
    "schema",
    "source",
    "source_binding_sha256",
    "source_kind",
    "source_profile",
    "source_rappid",
    "source_world_id"
  ],
  "properties": {
    "schema": {"const": "rapp-work-pointer-successor/1"},
    "authority_channel": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/channel"}]},
    "authority_files": {"$ref": "#/$defs/commitments"},
    "content_copied": {"const": false},
    "execution": {"const": "never"},
    "grants_authority": {"const": false},
    "identity_source": {"enum": ["operator-description", "source-identity-file"]},
    "source": {"type": "string", "minLength": 1},
    "source_binding_sha256": {"$ref": "#/$defs/hex64"},
    "source_kind": {"enum": ["hive", "organization", "workspace"]},
    "source_profile": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/profile"}]},
    "source_rappid": {"$ref": "#/$defs/rappid"},
    "source_world_id": {"$ref": "#/$defs/legacyWorldId"}
  },
  "if": {"properties": {"identity_source": {"const": "operator-description"}}},
  "then": {
    "properties": {
      "source_kind": {"const": "hive"},
      "source_profile": {"type": "null"},
      "authority_channel": {"type": "object"}
    }
  },
  "else": {
    "properties": {
      "source_kind": {"enum": ["organization", "workspace"]},
      "source_profile": {"type": "string"},
      "authority_channel": {"type": "null"}
    }
  },
  "$defs": {
    "hex64": {"type": "string", "pattern": "^[0-9a-f]{64}$(?![\\s\\S])"},
    "rappid": {
      "type": "string",
      "pattern": "^rappid:@(?=[a-z0-9-]{1,39}/)[a-z0-9]+(?:-[a-z0-9]+)*/(?=[a-z0-9-]{1,100}:)[a-z0-9]+(?:-[a-z0-9]+)*:[0-9a-f]{64}$(?![\\s\\S])"
    },
    "legacyWorldId": {
      "type": "string",
      "minLength": 1,
      "maxLength": 128,
      "pattern": "^[^\u0000-\u001f\u007f-\u009f\u00ad\u034f\u0600-\u0605\u061c\u06dd\u070f\u0890-\u0891\u08e2\u115f-\u1160\u17b4-\u17b5\u180b-\u180f\u200b-\u200f\u2028-\u202e\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufffb\ud804\udcbd\ud804\udccd\ud80d\udc30-\ud80d\udc3f\ud82f\udca0-\ud82f\udca3\ud834\udd73-\ud834\udd7a\udb40\udc00-\udb43\udfff]*$(?![\\s\\S])"
    },
    "profile": {
      "type": "string",
      "minLength": 1,
      "maxLength": 128,
      "pattern": "^[^\\u0000-\\u001f\\u007f]*$(?![\\s\\S])"
    },
    "label": {
      "type": "string",
      "minLength": 1,
      "maxLength": 64,
      "pattern": "^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$(?![\\s\\S])"
    },
    "channel": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "kind", "locator"],
      "properties": {
        "id": {"$ref": "#/$defs/label"},
        "kind": {"enum": ["custom", "github", "lan", "local", "nas", "sharepoint"]},
        "locator": {
          "type": "string",
          "minLength": 1,
          "maxLength": 2048,
          "pattern": "^[!$%&()*+,./0-9:;=A-Z_a-z~-]+$(?![\\s\\S])"
        }
      }
    },
    "commitments": {
      "type": "array",
      "minItems": 1,
      "maxItems": 512,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["bytes", "path", "sha256"],
        "properties": {
          "bytes": {"type": "integer", "minimum": 0, "maximum": 16777216},
          "path": {"type": "string", "minLength": 1, "maxLength": 512},
          "sha256": {"$ref": "#/$defs/hex64"}
        }
      }
    }
  }
}
```

<!-- schema: rapp-work-pointer-successor-source/1 -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/kody-w/rapp-work/protocols/rapp-work-sdk/1/pointer-successor-source.schema.json",
  "title": "RAPP Work SDK pointer-only successor source binding (proposed)",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "authority_channel",
    "authority_files",
    "described_paths",
    "identity_source",
    "kind",
    "path",
    "profile",
    "rappid",
    "root_identity",
    "schema",
    "world_id"
  ],
  "properties": {
    "schema": {"const": "rapp-work-pointer-successor-source/1"},
    "authority_channel": {
      "oneOf": [
        {"type": "null"},
        {"$ref": "pointer-successor.schema.json#/$defs/channel"}
      ]
    },
    "authority_files": {"$ref": "pointer-successor.schema.json#/$defs/commitments"},
    "described_paths": {
      "type": "array",
      "maxItems": 256,
      "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 512}
    },
    "identity_source": {"enum": ["operator-description", "source-identity-file"]},
    "kind": {"enum": ["hive", "organization", "workspace"]},
    "path": {"type": "string", "minLength": 1},
    "profile": {
      "oneOf": [
        {"type": "null"},
        {"$ref": "pointer-successor.schema.json#/$defs/profile"}
      ]
    },
    "rappid": {"$ref": "pointer-successor.schema.json#/$defs/rappid"},
    "root_identity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["device", "inode", "mode"],
      "properties": {
        "device": {"type": "integer", "minimum": 0},
        "inode": {"type": "integer", "minimum": 0},
        "mode": {"type": "integer", "minimum": 0}
      }
    },
    "world_id": {"$ref": "pointer-successor.schema.json#/$defs/legacyWorldId"}
  },
  "if": {"properties": {"identity_source": {"const": "operator-description"}}},
  "then": {
    "properties": {
      "kind": {"const": "hive"},
      "profile": {"type": "null"},
      "authority_channel": {"type": "object"},
      "described_paths": {"minItems": 1}
    }
  },
  "else": {
    "properties": {
      "kind": {"enum": ["organization", "workspace"]},
      "profile": {"type": "string"},
      "authority_channel": {"type": "null"},
      "described_paths": {"maxItems": 0}
    }
  }
}
```

<!-- schema: rapp-work-pointer-successor-plan/1 -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/kody-w/rapp-work/protocols/rapp-work-sdk/1/pointer-successor-plan.schema.json",
  "title": "RAPP Work SDK pointer-only successor plan (proposed)",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "actions",
    "network",
    "operation",
    "profile",
    "protocol",
    "schema",
    "source",
    "source_binding",
    "successor",
    "target"
  ],
  "properties": {
    "schema": {"const": "rapp-work-pointer-successor-plan/1"},
    "actions": {
      "type": "array",
      "minItems": 1,
      "maxItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "bytes",
          "content_base64",
          "expected_sha256",
          "mode",
          "operation",
          "path",
          "sha256"
        ],
        "properties": {
          "bytes": {"type": "integer", "minimum": 0},
          "content_base64": {"type": "string"},
          "expected_sha256": {"type": "null"},
          "mode": {"const": 384},
          "operation": {"const": "create"},
          "path": {"const": ".rapp-work/pointer-successor.json"},
          "sha256": {"$ref": "pointer-successor.schema.json#/$defs/hex64"}
        }
      }
    },
    "network": {"const": false},
    "operation": {"const": "migrate"},
    "profile": {"const": "rapp-work-sdk/1"},
    "protocol": {"const": "rapp-work/1"},
    "source": {"type": "string", "minLength": 1},
    "source_binding": {"$ref": "pointer-successor-source.schema.json"},
    "successor": {"const": "pointer-only"},
    "target": {"type": "string", "minLength": 1}
  }
}
```

The plan hash is the SHA-256 of the plan's canonical RAPP/1 JSON, exactly as
for `rapp-work-migration-plan/1`.

### 4.5 Static API metadata

`src/rapp_work/data/api.json` (`rapp-work-static-api/1`, shape unchanged):
`migrate` `optional_inputs` becomes `apply`, `hive`, `plan`, `plan_sha256`,
`successor`. `status` and `discover` return this metadata, so their results
list the two inputs; that is the only change in their output (section 9.3).
`docs/API.md` and `docs/MIGRATION.md` describe the opt-in.

### 4.6 Dependent changes that are not proposed here

- **`rapp-hive/1`.** No change. Its payloads keep `$defs/label`. A Hive that
  needs a longer world id inside signed Hive payloads needs new payload tokens
  and signed-registry kinds from the Hive owner (option B). `schema.json` and
  `SPEC.md` are untouched.
- **Canonical `rapp-work/1` (`kody-w/rapp-1`).** No change is required: a
  pointer-only successor never emits a canonical payload. If the owner later
  wants a signed `rapp-work/1-migration` intent whose source is a long-world
  legacy source, `migrationSource.world_id` cannot carry it; that would need a
  new canonical token (for example a legacy-source record) ratified in
  `kody-w/rapp-1`, never an in-place widening of `$defs/label`. The pin in
  `RAPP_WORK_PIN.json` stays unchanged.

## 5. Token and compatibility analysis

| Token | Change |
|---|---|
| `rapp-work-pointer-successor/1` | **New.** The record in `.rapp-work/pointer-successor.json`. |
| `rapp-work-pointer-successor-plan/1` | **New.** Plan envelope; hash rule identical to the migration plan. |
| `rapp-work-pointer-successor-source/1` | **New.** Source binding inside the plan. |
| `rapp-work-migration-receipt/1`, `rapp-work-migration-recovery/1` | Reused **unchanged**: same key sets, grammars and hash rules; their `plan_sha256` names the plan that created the target. |
| `rapp-work-migration-plan/1`, `rapp-work-migration-source/1`, `rapp-work-migration-source-pointer/1` | Unchanged; the default path is the SDK 1.0.0 code, and its plans are byte-identical (section 9.3). |
| `rapp-work-sdk/1` record, `rapp-work-managed-files/1`, `rapp-work-organization/1`, `rapp-work-organization-pointers/1` | Unchanged in shape and in enforcement (section 2.5). |
| `rapp-work-static-api/1` | Shape unchanged; `migrate` lists two more optional inputs. |
| `rapp-hive/1-*`, `rapp-private-hive-*`, `rapp-federation/1-*`, canonical `rapp-work/1-*`, RAPP/1 | Unchanged. The pointer path only reads `rapp-private-hive-current/1` and `rapp-private-hive-chain/1` objects. |

Compatibility:

- **Old SDK, new request or artifact.** SDK 1.0.0 refuses `successor` and
  `hive` (`REFUSE_INPUT_KEYS`), refuses a pointer plan
  (`MigrationPlan.from_dict`: unknown key `successor`), and does not recognize
  a pointer successor as a Workspace (`verify` refuses `REFUSE_VERIFY_TARGET`).
  It fails closed.
- **New SDK, old request or artifact.** Every request without `successor`
  takes the SDK 1.0.0 code; every `rapp-work-migration-plan/1` still applies
  and replays exactly as before; SDK workspaces and Organizations with any
  world id load, update and verify exactly as before.
- **Observable differences without the opt-in.** Exactly those of section
  9.3: the static API metadata in `status` and `discover` results, and the
  CLI message for `--hive` without `--successor`.
- **Pins.** `protocols/rapp-work-sdk/1/SPEC.md` and `schema.json`,
  `protocols/index.json`, `src/rapp_work/data/profiles.json`, `RAPP1_PIN.json`,
  `RAPP_WORK_PIN.json`, the signed `registry.json`, root `SPEC.md`, and the
  `rapp-hive/1` and `rapp-federation/1` specifications and schemas are
  untouched. Only `RELEASE-INVENTORY.json` is regenerated.

## 6. Security and privacy analysis

| Threat | Control |
|---|---|
| Copying Hive state, GODD or keys into the successor | The plan has exactly one create action (the record), checked when the plan is parsed and again by re-derivation at apply. Tests assert the exact file set and that no source byte string (content, private sentinel, signatures, keys, Git objects) appears in the successor or the plan. |
| Writing to the source | No source write exists. Tests compare the full source tree (inode, mtime, mode, SHA-256, including `.git`) before and after plan, apply and replay. |
| Credentials in locators | Locators refuse user information, queries, fragments, whitespace and quoting characters in two layers (a forbidden-character check with an explicit message, and three closed locator forms). Only syntax can be checked: a secret inside a path segment cannot be detected, which is why the operator reviews the plan. |
| Reading Git internals | Before anything is read, a source path with a component that names `.git`, and a source that is or is inside a directory holding `HEAD`, `objects` and `refs`, are refused. Every bound path is checked for a `.git` component under Git's HFS+ and NTFS equivalences (ignorable code points, case, trailing dots and spaces, stream suffixes, `GIT~<n>`) and NFKC. A Git directory that lacks one of those three entries is not recognized as one; the operator reviews the bound paths in the plan. |
| Link, hardlink and traversal attacks | Authority files are read by descriptor-relative `O_NOFOLLOW` opens and must be regular single-link files; paths are safe relative POSIX paths; publication references are 64-hex addresses before they become paths. |
| Prompt injection through a long world id | The legacy world id is written only into canonical JSON. A pointer-only successor has no `CLAUDE.md`, README or other instruction file. |
| A spoofed world in a reviewed plan | Control, format, separator, bidirectional and default-ignorable code points, and unassigned code points, are refused, and NFC is required. Look-alike characters from other scripts are not refused (section 3.4); world ids compare by exact code points. |
| A mistaken or malicious description | Corroboration refuses a description that contradicts a bound declaration, `hive.declaration` frame, owner anchor or Private Hive current pointer, and a publication checkout's genesis declaration is bound through its current pointer. A source without any recognized record (for example a member's materialized copy) is uncorroborated: the pointer then says only `identity_source: "operator-description"`, `grants_authority: false` and `execution: "never"`. It is never authority. |
| Forged or stale plans | Exact plan hash; closed plan, binding and record shapes; re-derivation of the record from the binding; source rebinding before the first write and after staging. |
| A source changed while staging, or swapped for a byte-identical copy | The post-staging rebinding and the bound source directory identity (device, inode, mode); both refuse before activation, and tests exercise each. |
| Interrupted apply and replay | The unchanged plan-bound recovery marker and full completed replay; foreign staging is refused and left untouched. |
| Resource exhaustion | At most 256 described paths, 512 bound files, 16 MiB per file and 64 MiB in total; the publication rule reads at most two extra files. |
| Privacy of the pointer | It records the source path, the channel locator, the authority file paths and their hashes. It is private local metadata in the operator's successor directory and is never published. Hashes of small authority records reveal nothing new to someone who does not already hold those bytes. |

No network, credential or environment access is added. Git is never invoked by
the SDK. Discovery stays inert.

## 7. Migration

1. For a repository-seeded Hive, write the closed description (the Hive
   RAPPID, its world id, its authority channel, and the authority files to
   bind), plan with `--successor pointer-only --hive <file>`, review the plan,
   and apply it with `--successor pointer-only` and the exact hash. For a
   checkout of a historical Private Hive publication, `authority_paths` can be
   just `["refs/current.json"]`: its Mother chain index and genesis
   declaration are bound and corroborated automatically.
2. For an older workspace whose world id is longer than 64 characters, plan
   with `--successor pointer-only` (no description): the identity comes from
   its `rappid.json`.
3. The source stays byte-identical and keeps working with its own tools. The
   successor is only a pointer. Admitting members, carrying signed requests or
   founding a new Hive are separate, later steps with their own authority.

No existing artifact needs to be rewritten.

## 8. Rollback

- Delete the successor directory: it holds only the pointer, the receipt and
  the recovery marker, and nothing else depends on it. The source was never
  written.
- To withdraw the proposal, revert this branch: the default paths are the SDK
  1.0.0 code, and old SDKs already refuse the new inputs and plans.

## 9. Conformance and test vectors

### 9.1 Vectors

New module [`tests/test_sdk_migration_pointer.py`](../../tests/test_sdk_migration_pointer.py):
33 test functions, 116 test cases with parametrization, all on synthetic data
(minted test keys, `example` names, local sandboxes).

| Area | Vectors |
|---|---|
| Regression (passes on `main` and here) | The default `migrate` of a seeded Hive still refuses `REFUSE_PATH_UNSAFE` with the same details; an 80-character world (from `rappid.json` or from `.rapp-hive/declaration.json`), a Workspace/1 text world and `example--world` still refuse `REFUSE_MIGRATION_SOURCE`; the source is untouched. SDK 1.0.0 behavior for long-world workspaces: an 80-character workspace integrated by `update` stays a `workspace` for `status`, verifies with its managed-file checks, refuses a tampered `.rapp-work/sdk.json` or SDK skill file (`REFUSE_MANAGED_DRIFT`) and a missing integration (`REFUSE_SDK_PROFILE`), and still plans `update`; `Workspace.load` and Organization pointer entries keep accepting it. |
| Reproduction (fails on `main`, passes here) | Plan and apply a pointer-only successor for an 80-character-world seeded Hive with the exact hash; exact plan, binding, record and receipt contents; owner-only modes. |
| No copied state | Exact successor file set; no content, sentinel, key, signature or Git object bytes in the successor or plan. |
| Source untouched | Full tree snapshot equality, including `.git`, after plan, apply and replay. |
| Completed replay | Read-only `unchanged`; stable re-plan hash; tampered record or receipt refused without repair. |
| Changed source | Changed bytes, a newly appearing authority file, or a removed described file refuse before any write and leave no staging; a changed source refuses replay without touching the target; a bound file changed while staging refuses before activation (pointer and default paths) and the exact marker then resumes; a byte-identical copy swapped in between plan and apply refuses (both source classes). |
| Plan gates | Wrong hash; forged record; forged commitment; extra action; wrong `successor`; `network: true`. |
| Recovery and create-only activation | A foreign marker is refused and preserved; the exact marker resumes; an activation race never replaces the winner. |
| Opt-in contract | Pointer plan without the opt-in; default plan with it; unknown successor value; `hive` without `successor` refused exactly as on `main` (`REFUSE_INPUT_KEYS`, same details and message) or while applying; description required and refused by source class; a non-workspace `rappid.json` refused identically with and without a description; unknown keys; invalid RAPPIDs; unsorted, duplicate, empty or missing paths; bad channel kind; 129-character world. |
| World grammar | Accepted: 1, 64, 65 and 128 characters, `example--world`, text with spaces and capitals, `.` and `/`, 128 precomposed `é`, CJK, accented Latin, an emoji. Refused: empty, 129 characters, 129 `é`, NFD, C0, newline, DEL, C1, bidirectional controls, a lone surrogate, U+200B, U+2028, U+2029, U+FEFF, U+00AD, U+2060, U+034F, U+180E, U+3164, U+FE0F, tag and supplementary variation-selector characters, an unassigned code point, noncharacters, `a` U+1DFA U+0301, non-strings. An exhaustive check over all 1,114,112 code points against the running Unicode database. |
| World boundaries end to end | Lengths 1, 64, 65, 128, 129 through both source classes; the default path accepts only up to 64. |
| Not a Workspace; other labels stay 64 | `scaffold` refuses 65; a pointer successor is a `directory` for `status`, `REFUSE_VERIFY_TARGET` for `verify`, refused by `update` and `Workspace.load`; the `rapp-work-sdk/1`, `rapp-hive/1` and canonical schemas still say 64. |
| Channels and paths | Credential-free locators accepted (https, opaque, relative); user information, queries, fragments, `http`, `ftp`, `file`, `ssh` and `git` in URL or opaque form, scp-style (including `rapp-hive/1`'s conformance locator), `file:/…`, drive letters, absolute, traversal, whitespace, non-ASCII, empty and overlong locators refused; channel ids. Paths: `.git` in any case or depth, HFS+ ignorables, bidirectional controls, trailing dots and spaces, `GIT~1`, `git~2`, fullwidth `.git`, NTFS streams, traversal, absolute, colon, symlinked file or directory, hardlink; `.github`, `.gitignore`, `git/` and `.git.d` are ordinary paths. |
| Git directories | A `.git` directory and a directory inside it; a workspace inside `.git`; a bare repository and a directory inside it; a `.git.` alias directory. |
| Corroboration | Matching `rapp-hive/1-declaration` accepted; mismatched RAPPID, world or channel refused; `rapp-private-hive-owner-anchor/1` mismatch refused. |
| Private Hive publications | A synthetic publication: current pointer, chain index and genesis bound; a description differing in Hive, world, channel id or channel kind refused at the genesis frame; a current pointer for another Hive refused at `refs/current.json`; a pointer without a Mother frame, a missing chain index, a chain index for another stream, with another tip or without frames, a missing genesis frame, and a genesis frame that is not a declaration are each refused at the named file; an unrecognized `refs/current.json` stays opaque bytes. |
| Historical skill | Through `rapp_work.compat`: a prepared repository checkout still plans a workspace successor; a member's materialized copy and the deployed publication checkout refuse by default; the checkout **without an owner anchor**, naming only `refs/current.json`, refuses the review's unrelated description and every single-field contradiction (at the genesis frame), and applies a pointer-only successor binding the current pointer, chain index and genesis frame; with the anchor added it is also bound. |
| Organization source | A scaffolded Organization becomes a pointer-only successor with `source_kind: "organization"` and its five allowlisted authority files. |
| Record token, schemas, CLI, metadata | Closed record vectors, including 16 MiB per file, 64 MiB in total and 512 files; JSON Schema parity for the three tokens (reference-only rules shown valid in the schema but refused by the reference); exact equality of the schema world pattern with the implemented ranges; CLI plan and exact apply, `--hive` without `--successor` refused as a CLI argument error without reading the file, `--hive` refused with `--apply`, apply without the opt-in refused; static API inputs. |

### 9.2 Results

- `main`'s `src/` (`29ead23`) with this test module: **114 failed, 2
  passed**. The two passes are the regression vectors
  (`test_seeded_hive_default_migration_refusal_is_unchanged` and
  `test_long_world_default_behavior_matches_sdk_1_0_0`). With the change:
  **116 passed** on Python 3.13 and on Python 3.10.
- `main`'s own 169 tests (this branch changes no existing test file) on this
  branch: **169 passed** on Python 3.13 and on Python 3.10.
- Full suite with the change: **285 passed, 69 subtests passed** on Python
  3.13 and on Python 3.10.

### 9.3 Default behavior compared with `main`

Method: a differential probe (a local verification script, not committed)
built five scenarios once — a workspace with a short world id (API and CLI
plan, apply, replay, wrong hash; `status`, `verify` and `update` of source
and successor); workspaces with 65, 80, 128 and 129-character, text, double-hyphen and
declaration-sourced world ids (`migrate`, `status`, `verify`, `update` plan and
apply, then `verify` of tampered SDK files and a removed inventory);
Organizations, one with an 80-character pointer entry (`status`, `verify`,
`update`, `migrate` plan and apply, successor `verify`); a seeded Hive and a
protocol estate (default `migrate`, ten malformed `migrate` inputs including
`hive` without `successor`, `status`, `verify`, `update`, and the CLI with and
without `--hive`); and a historical prepared workspace (`migrate`, `status`,
`verify`, `discover`). Each scenario was run through `main`'s `src/` and then,
restored in place (so source directory identities match), through this
branch's `src/`, on Python 3.13 and on Python 3.10, comparing complete
canonical result envelopes and the resulting file trees.

Result, identical on both Pythons: 99 comparisons.

- **79 byte-identical**, including every `migrate` and `verify` result, every
  `update` result but the one below, and all five resulting file trees.
  `migrate` with `hive` but without `successor` is byte-identical to `main`:
  `REFUSE_INPUT_KEYS`, details `{"missing": [], "unknown": ["hive"]}`.
- **1 identical after substituting a directory identity**: the `update` plan
  of a freshly migrated successor, whose directory each run created anew. With
  `main`'s `root_identity` substituted and the plan hash recomputed, the
  outputs are byte-identical.
- **19 differ**, in exactly two ways:
  1. 17 `status` results and 1 `discover` result: only
     `result.api.operations[migrate].optional_inputs`, which gains `hive` and
     `successor` (section 4.5);
  2. 1 CLI call with `--hive` but without `--successor`: the same exit code
     and envelope (`operation: "cli"`, `REFUSE_CLI_ARGUMENTS`), but the message
     is "--hive is accepted only with --successor pointer-only" instead of
     argparse's "unrecognized arguments: --hive …".

### 9.4 Mutation proof

Each mutation was applied alone, the named tests were run, and the file was
restored and checked by SHA-256. Every mutation turned its tests red on Python
3.13 and on Python 3.10; after restoring every file, all 116 cases pass on
both.

| Mutation | Result |
|---|---|
| M1 read Git internals (drop the authority-path `.git` guard) | red |
| M1b compare `.git` exactly (drop the HFS+, NTFS and NFKC equivalences) | red |
| M1c drop the source-path `.git` component check | red |
| M1d drop Git-directory detection for the source and its parents | red |
| M2 widen the pointer world to 129 | red |
| M3 skip the pre-write rebinding | red |
| M3b skip the pre-write rebinding and re-derivation | red |
| M3c skip the post-staging rebinding (pointer apply) | red |
| M3d skip the post-staging rebinding (default apply, shared tail) | red |
| M3e constant source directory identity in the pointer binding | red |
| M4 allow `@`, `?`, `#` in locators | red |
| M4b drop only the forbidden-character layer | red |
| M4c allow `:` in relative locators (`file:/…`, `C:/…`) | red |
| M4d accept `http`, `file` and other hierarchical schemes as opaque | red |
| M4e accept single-letter opaque schemes (drive letters) | red |
| M5 re-add round 1's cap in `load_identity` | red |
| M5b re-add round 1's cap in Organization pointer entries | red |
| M5c accept `hive` in the default `migrate` key set (round 1's shape) | red |
| M6 copy an authority file into the successor | red |
| M7 bypass the recovery-marker binding | red |
| M8 skip completed-replay inventory bytes | red |
| M9 disable corroboration | red |
| M9b drop the current-pointer corroboration rule | red |
| M9c do not follow the current pointer to the genesis frame | red |
| M9d accept a chain index that does not name a genesis frame | red |
| M10 accept `hive` without the opt-in | red |
| M11 drop every fixed forbidden world range | red |
| M11b keep only the C0, DEL, C1 and surrogate ranges | red |
| M11c drop the unassigned-code-point rule | red |
| M12 drop NFC | red |
| M13 relax the default migration cap to 128 | red |
| M14 accept a description for a source with `rappid.json` | red |
| M14b refuse the description before reading the identity (round 1's order) | red |
| M15 accept `hive` while applying | red |
| M16 let the record claim authority | red |
| M17 per-file commitment limit back to 64 MiB | red |
| M17b drop the total-bytes check | red |
| M17c drop the commitment count cap | red |
| M18 CLI reads `--hive` without `--successor` | red |
| M19 accept unsorted described paths in a binding | red |
| After restoring every file | green |

## 10. Reference implementation and gating

- `src/rapp_work/migration.py`: `pointer_world_id`, `authority_channel`,
  `authority_locator`, `hive_description`, `pointer_source_binding` (with
  `_pointer_source_root`, `_git_equivalent`, `_read_authority`,
  `_publication_references` and `_corroborate`), `pointer_record`,
  `validate_pointer_record`, `PointerSuccessorPlan`, `plan_pointer_successor`
  and `apply_pointer_successor`. The shared tail of `apply_migration` is
  factored into `_complete` without changing its order, codes or messages.
  `_source_identity` gains a `pointer` switch that only selects the world
  grammar.
- `src/rapp_work/api.py`: a request carrying `successor` goes to the pointer
  path; every other request runs the unchanged SDK 1.0.0 `_migrate` body,
  including its closed key set.
- `src/rapp_work/cli.py`: `--successor pointer-only` and `--hive <file>`;
  `--hive` without `--successor` is refused with the argument parse, before
  the file is read.
- `src/rapp_work/data/api.json`, `docs/API.md`, `docs/MIGRATION.md`,
  `CHANGELOG.md` (`Unreleased (proposal, not accepted)`), and
  `RELEASE-INVENTORY.json`.
- `src/rapp_work/workspace.py` is unchanged (byte-identical to `main`).

**Gate.** The pointer-only path runs only when a request carries
`successor: "pointer-only"`, at plan and at apply. The default remains the
accepted §10 behavior and fails closed. Nothing is exported at the top level of
`rapp_work` (`__all__` is unchanged).

Local mirror of the `conformance` workflow (`tools/check.py`, `pytest`,
`ruff`, `mypy`, `tools/release_inventory.py --check`, `python -m build`,
`tools/verify_package.py`) passes on Python 3.13 and 3.10: `ok check.py`;
285 passed, 69 subtests passed; ruff and mypy clean; release inventory
verified (146 files); wheel 113 files; sdist 155 files. The repository's GitHub
workflow runs only on `main` and pull requests, so it does not run for this
branch.

## 11. Open questions for the owner

1. Is an operator description, bound to exact bytes and corroborated where a
   recognized record exists, an acceptable source of a Hive identity for a
   *pointer*? The alternative is to accept only sources that carry a
   recognized record, which excludes the real seeded Hive.
2. Should the legacy world grammar be Workspace/1 text without invisible code
   points (proposed), or a lowercase label of up to 128 characters (which
   could refuse real legacy world ids)?
3. Should `status` and `verify` recognize `rapp-work-pointer-successor/1`
   read-only? Today a pointer successor is a plain `directory` for `status` and
   `REFUSE_VERIFY_TARGET` for `verify`; completed replay is its verification.
4. Is a long-world *workspace* successor wanted (option E)? It needs a new SDK
   integration record, `update`/`verify`/`status` support and an Organization
   decision.
5. Should the two coexisting `rapp-work-sdk/1` profiles (this repository's and
   the sidecar hosted in `kody-w/rapp-workspace`) be reconciled under distinct
   tokens (section 13)?
6. Should corroboration compare the authority channel's `locator`?
   `rapp-hive/1` §3 calls a locator transport metadata, not identity. Comparing
   only the channel `id` and `kind` would let an operator record a
   credential-free rendering of a declared locator that the pointer grammar
   cannot carry (limit 1 below), at the cost of no longer catching a mistyped
   locator. This draft keeps comparing it (fail closed).
7. Should a Hive description be allowed beside a `rappid.json` that is not a
   Workspace or Organization identity (limit 2 below)?
8. Should the pre-existing `update` mismatch (section 13, D1) be fixed, and
   how: a `plan_update`-only refusal, or a long-world integration record
   (question 4)?
9. Should plans present non-ASCII world ids with their code points, or refuse
   confusable characters (which needs a confusables table)?
10. If proposal 0011 is accepted, add `workspace-index` to this proposal's
    closed kind enums before accepting it (section 14).

### 11.1 Known limits

1. **Declared locators outside the pointer grammar.** A Hive whose bound
   declaration names an authority locator that the credential-free grammar
   refuses (an scp-style SSH locator such as `rapp-hive/1`'s own conformance
   locator `git@example.invalid:example/private-hive.git`, an `http://` URL, a
   `.git`-suffixed GitHub URL) cannot get a pointer-only successor: the
   description cannot repeat that locator (`REFUSE_POINTER_CHANNEL`) and cannot
   differ from it (`REFUSE_POINTER_CLAIM`). Question 6.
2. **Non-workspace identity files.** A source whose `rappid.json` is not a
   Workspace or Organization identity (for example `kind: "protocol-estate"`)
   cannot get a pointer-only successor, with or without a description; it is
   refused with the same `REFUSE_MIGRATION_SOURCE` as default migration.
   Question 7.
3. **Corroboration needs a recognized record.** A source without a
   declaration, `hive.declaration` frame, owner anchor or current pointer
   (for example a member's materialized copy) is uncorroborated; its pointer
   says `identity_source: "operator-description"`.
4. **Look-alikes.** Confusable characters in world ids are not refused
   (section 3.4). Question 9.
5. **Unicode versions.** A world id that uses characters newer than an
   implementation's Unicode database is refused by that implementation
   (section 3.4).
6. **Git directory detection.** A Git directory is recognized by a `.git`
   path component or by the presence of `HEAD`, `objects` and `refs`; one
   missing an entry is not, and the operator reviews the bound paths.

## 12. Owner actions needed

1. Accept or reject sections 4.2 and 4.3 and apply the text to
   `protocols/rapp-work-sdk/1/SPEC.md`; add the schemas of section 4.4 as files
   under `protocols/rapp-work-sdk/1/`.
2. On acceptance, update the SDK specification pins in
   `src/rapp_work/data/profiles.json` and `protocols/index.json` (these are
   package pins, not signed-registry pins: no re-signature is needed), bump the
   package and `SDK_VERSION` to 1.1.0 (with `tools/verify_package.py`'s version
   check), and regenerate `RELEASE-INVENTORY.json`.
3. Decide open questions 1–10, including whether to act on section 13's D1.
4. For the Hive owner: decide whether `rapp-hive/1` ever needs longer world ids
   in signed payloads (option B: new payload tokens and signed-registry kinds;
   the `rapp-hive/1` `SPEC.md` is pinned by the signed registry, so any SPEC
   change needs the owner's re-signature).
5. For `kody-w/rapp-1`: nothing now; see section 4.6 for the condition under
   which a new canonical legacy-source token would be needed.

## 13. Observations outside this proposal (reported, not fixed)

- **D1. `update` writes a `rapp-work-sdk/1` record that its schema forbids.**
  Reproduction on `main` (and unchanged here): a workspace whose `rappid.json`
  has an 80-character label world id; `update` plans and applies, writing
  `.rapp-work/sdk.json` with that world id, which
  `protocols/rapp-work-sdk/1/schema.json` limits to 64 characters; `verify`
  then reports it `verified`. The cause is `load_identity`
  (`src/rapp_work/workspace.py` line 369), which checks the label grammar
  without a length cap, while `scaffold` (`_label`, line 38, default 64) and
  migration (`migration.py` line 67) cap at 64. Organization pointer entries
  (line 877) have no cap either. A narrowly scoped candidate fix for the owner
  (not implemented): make `plan_update` refuse, before any effect, to plan an
  `.rapp-work/sdk.json` whose `world_id` violates `schema.json`, and leave
  `load_identity`, `status`, `verify` and Organization pointers unchanged, so
  already integrated workspaces keep verifying with their managed-file checks.
  `rapp-work-sdk/1` §7 ("Updating is additive for legacy workspaces") and the
  record schema pull in different directions here, so this is the owner's
  decision (question 8). Round 1's broader fix made `verify` skip the
  managed-file checks of such workspaces and was withdrawn (section 2.5).
- `directory_fd` reports a missing *file* as "unsafe or missing directory
  path" naming its parent (section 2.2). A clearer default refusal would be a
  separate, owner-visible behavior change.
- The SDK label forbids consecutive hyphens, while `rapp-hive/1` and canonical
  `rapp-work/1` labels allow them, so a `rapp-hive/1`-valid world id such as
  `example--world` is refused by SDK migration.
- Two different profiles are published as `rapp-work-sdk/1`: this repository's
  integration profile (`.rapp-work/sdk.json`, `managed.json`) and the sidecar
  profile in `kody-w/rapp-workspace` (`.rapp-work/install.json`,
  `generations/`, world ids up to 128). One label denotes two shapes
  (RAPP/1 Constitution Art. 2).
- The workspace successor re-emits the *source* RAPPID, while canonical
  `rapp-work/1` §6 describes "a fresh target workspace RAPPID" for its signed
  migration intent. The SDK successor is not a canonical migration intent, but
  the difference deserves an explicit statement in `rapp-work-sdk/1` §10.
- A completed-migration receipt is compared semantically, so extra whitespace
  in the receipt file does not refuse replay (its hash is still reported).

## 14. Related proposals and merge order

Sibling drafts on `kody-w/rapp-work` touch some of the same files and
sections. This branch does not edit them.

| Proposal (gap, branch) | Overlap with this proposal | How it composes |
|---|---|---|
| 0002 (G2, `experimental/gap-g2-move-action`) | `api.py` imports (it edits the `.plans` import directly below the `.migration` import that this branch expands) and `_update`; `cli.py` (`update` arguments); `data/api.json` (`update` inputs); the `docs/API.md` operations table; `CHANGELOG.md`; `RELEASE-INVENTORY.json` | Textual only; moves are `update` plans and pointer successors are `migrate` plans. Resolve the adjacent import lines and table rows by keeping both, merge the changelog entries, and regenerate the inventory. |
| 0003 (G3, `experimental/gap-g3-agent-discovery`) | SPEC §11 (and a new §11.1), `discovery.py`, `docs/API.md`, `CHANGELOG.md`, inventory | No semantic overlap. |
| 0006 (G6, `experimental/gap-g6-owner-succession`) | Replaces the SPEC §12 paragraph; adds §5.1; `docs/API.md`, `CHANGELOG.md`, inventory | Composes: section 4.3 inserts a sentence after the §12 paragraph instead of replacing it. |
| 0007 (G7, `experimental/gap-g7-instruction-inventory`) | Replaces the SPEC §12 paragraph; adds §7.1–§7.6; edits `workspace.py`, `api.py` (`_verify`, `_update`), `_paths.py`; appends to `docs/MIGRATION.md` after the same paragraph this branch appends after | Composes: §12 is an insertion here; `workspace.py` and `_paths.py` are untouched here; different `api.py` functions; keep both `docs/MIGRATION.md` sections. A pointer successor is not a Workspace, so 0007's instruction inventory never applies to it. |
| 0011 (G11, `experimental/gap-g11-workspace-index`) | Proposes renaming the pointer-only Organization to "workspace index" (`kind: "workspace-index"`, new records) and replacing §7, the first §10 paragraph and §12 | This proposal's closed enums (`source_kind`, binding `kind`: `hive`, `organization`, `workspace`) and its accepted identity kinds would need `workspace-index`, and the bound allowlist `workspace-index.json`. Add them before either is accepted, while these tokens are drafts, so no token moves; if this proposal were accepted first, a workspace index source would need a new pointer token (Art. 2). Section 4.2 appends §10.1 and composes with 0011's §10 replacement. |
| 0017 (G17, `experimental/gap-g17-brainstem-sdk-agent`) | Its Brainstem agent calls `migrate` with only `source` and `target` | No conflict; the agent never requests a pointer-only successor. Offering one would be a later change to that agent. |

Recommended order: decide 0011 first (it settles the kind enums above); then
0006, 0007, 0002 and 0003 in any order; then this proposal, whose §12 text is
written to apply after any of their §12 replacements; then 0017, so the
agent follows the final API. Each merge regenerates `RELEASE-INVENTORY.json`
and keeps every changelog entry.

## 15. References

- Gap: `organism/gaps/G04.md` on `kody-w/rapp-work` branch
  `experimental/rapp-work-constitution`.
- Independent review G4-r1 of this branch at `ff1d27b` (findings 1–9;
  disposition in the round-2 commit message).
- RAPP/1 Protocol Constitution, Articles 2, 4, 6, 7, 8, 10 and 18
  (`kody-w/rapp-1` `CONSTITUTION.md`, `591e014`).
- `rapp-work-sdk/1` `SPEC.md` §2–§4, §7, §10 and §12; `schema.json`.
- `rapp-hive/1` `SPEC.md` §3, §10, §12 and §14.1; `schema.json` `$defs/label`,
  `$defs/channel`, `$defs/declaration`; `reference/hive_conformance.py`
  (the scp-style conformance locator).
- Canonical `rapp-work/1` `SPEC.md` §2, §3 and §6; `schema.json` `$defs/label`,
  `$defs/migrationSource` (`kody-w/rapp-1` `591e014`, mirrored under
  `src/rapp_work/data/`).
- RAPP Workspace/1 schemas (`kody-w/rapp-workspace` `52d4f19`):
  `seed.schema.json`, `workspace-binding.schema.json`, `common.schema.json`;
  and its hosted `protocols/rapp-work-sdk/1/schemas/install.schema.json`.
- Frozen `rapp-hive/2` research record: `kody-w/rapp-workspace` branch
  `experimental/frontier-rapp-hive-2` (`b0d0f07`; commit `aa9af2b`).
- The Hive folder model's migration notes: `kody-w/rapp-model-hive` branch
  `experimental/hive-md` (`2bd7c95`), `MIGRATION.md`.
- Historical skill: `.github/skills/rapp-private-hive/` (`SKILL.md`,
  `DEPLOYMENT.md`, `schemas/deployment.schema.json` (`current`, `anchor`),
  `scripts/prepare_workspace.py`, `lib/private_hive/` (`authority.py`
  `bootstrap`, `bundle.py`, `release.py`)), exposed through `rapp_work.compat`.
- Git's own `.git` equivalences: `is_hfs_dotgit`, `is_ntfs_dotgit` and
  `is_git_directory` (`git/git`, `path.c` and `setup.c`).
- Unicode Standard Annex #15 (normalization stability) and the Unicode
  Character Database 15.1 (`Default_Ignorable_Code_Point`, general categories).

### Ready-to-file pull request text

Title: `rapp-work-sdk/1: opt-in pointer-only migration successors (G4)`

Body: Adds an explicit `successor: "pointer-only"` form to `migrate` for
repository-seeded Hives and sources with world ids longer than 64 characters.
The successor holds only a `rapp-work-pointer-successor/1` record with exact
authority-byte commitments, plus the unchanged receipt and recovery marker; it
copies nothing, mints nothing, never reads Git internals, and never writes the
source. A description of a seeded Hive is corroborated against the source's
own Hive records, including a publication's genesis declaration found through
its current pointer. World ids up to 128 characters exist only inside the new
tokens; no existing token is widened. Without `successor`, `migrate`, `update`
and `verify` are unchanged; the static API metadata lists the two new optional
inputs. See `docs/proposals/0004-sdk-migration-successors.md`.
