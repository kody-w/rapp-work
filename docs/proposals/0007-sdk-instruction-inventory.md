# Proposal 0007: SDK instruction-file inventory

- **Status:** draft, not accepted. The owner decides.
- **Gap:** G7 — SDK verification accepts an edited instruction file. SDK
  verification does not notice when an instruction file was edited; the fix
  puts instruction files in the inventory and refuses new ones.
- **Home spec and section:** `rapp-work-sdk/1`
  ([`protocols/rapp-work-sdk/1/SPEC.md`](../../protocols/rapp-work-sdk/1/SPEC.md))
  §7 "Workspace and Organization", with consequential edits to §4
  "Filesystem boundary" and §12 "Refusals".
- **Blocks:** Workspaces (RAPP Workspace/1; "Your private, local-first
  workspaces (GODD), changed only by exact SDK plans").
- **Branch:** `experimental/gap-g7-instruction-inventory` in `kody-w/rapp-work`.
- **Intended release:** `rapp-work` 1.1.0 (see Open questions). The package
  version and `SDK_VERSION` are unchanged on this branch.

## 1. Context: what is true today

All references are to `kody-w/rapp-work` `main` at `29ead23`.

1. **Scaffold writes an instruction file outside every inventory.**
   `src/rapp_work/workspace.py` `_workspace_files()` writes `CLAUDE.md`
   ("Workspace instructions ... Use the installed `rapp-work` SDK; discovered
   code is inert."). `_integration_files()` returns only
   `.github/skills/rapp-work-sdk/SKILL.md`, `.rapp-work/sdk.json`, and
   `.rapp-work/managed.json`; `_managed_record()` (`rapp-work-managed-files/1`)
   lists only those SDK-owned files. `CLAUDE.md` is in no record.
2. **Verification never looks at instruction files.** `Workspace.verify()`
   checks the identity, the SDK-owned files through `_read_managed()`, and
   `sdk.json` equality. `Organization.verify()` checks the identity, the
   managed files, the descriptor, and the pointers. `src/rapp_work/api.py`
   `_verify()` dispatches to them. An edited `CLAUDE.md`, a new `AGENTS.md`,
   `.github/copilot-instructions.md`, or `.claude/rules/*.md`, or a symlinked
   instruction file, all verify.
3. **The SPEC is silent.** `rapp-work-sdk/1` §7 says only that a Workspace has
   one RAPPID and one `world_id`, that updating is additive for legacy
   workspaces and limited to SDK-owned integration files, and that an
   Organization is pointer-only. §4 makes symlinks and hard links refusals only
   for "authority-bearing reads and all writes", and instruction files are not
   named as authority-bearing.
4. **The ecosystem already says instructions are authority.** The
   RAPP Workspace template (`.github/skills/rapp-workspace-manager/templates/workspace-SPEC.md`
   §2) says: "Trusting a workspace therefore means trusting its project
   instructions and skill files." Every current AI coding tool loads such files
   automatically (§3.1), so an unreviewed edit or a newly dropped instruction
   file is a prompt-injection path into a private (GODD) workspace.
5. **The machinery for a reviewed change already exists.** `plan_update()` /
   `apply_update()` implement plan-by-default, apply only with the exact plan
   SHA-256, replay of the plan before the first write, SDK-owned replacement
   only with exact `managed_files` preconditions, and an exact plan-bound
   recovery marker (`rapp-work-update-recovery/1`). `docs/API.md` lists
   "Automatic repair of missing or modified SDK-owned files" as explicitly
   deferred.
6. **Every SDK release already requires one update.** `_sdk_record()` embeds
   `SDK_VERSION` in `.rapp-work/sdk.json`, and `Workspace.verify()` requires
   byte equality with it, so a workspace integrated by one SDK version is
   refused (`REFUSE_SDK_PROFILE`) by the next until `update` is applied.

## 2. Proposed change (summary)

1. Define the closed, versioned instruction-path set
   `rapp-work-instruction-set/1` (§3.1 below; SPEC §7.1).
2. Scan for it with a bounded, descriptor-relative, no-follow walk that refuses
   rather than truncates (SPEC §7.2).
3. Record it in a new additive SDK-owned record,
   `.rapp-work/instructions.json` with token
   `rapp-work-instruction-inventory/1`: path, byte length, and SHA-256 of every
   instruction file, never content (SPEC §7.3). The record is listed in the
   unchanged `rapp-work-managed-files/1` inventory.
4. Verification refuses an edited, missing, or unlisted instruction file, a
   linked or non-regular instruction path, an exceeded bound, a malformed
   inventory, and an absent inventory, naming paths and reasons without
   echoing content (SPEC §7.4).
5. The only acceptance path is the existing `update` operation: the plan
   re-inventories the exact observed bytes, the planned result carries a
   derived `rapp-work-instruction-review/1` with every old and new hash, apply
   needs the exact plan SHA-256, and apply (including a resumed apply) rescans
   before the first write (SPEC §7.5).
6. Organizations inventory their own tree; earlier Workspaces are refused until
   one reviewed update adds the inventory; compatibility wrappers are unchanged
   (SPEC §7.6).

## 3. Design decisions and reasons

### 3.1 Which files are instruction files

An instruction file is a file an AI tool reads as instructions or context
*because of its path*. The set was chosen from the vendors' own documentation
(References) for the tools RAPP names or targets, plus the two open standards:

| Source | Paths it reads | Covered by |
|---|---|---|
| AGENTS.md open standard; OpenAI Codex | `AGENTS.md` in every directory from the project root to the working directory; `AGENTS.override.md` wins in a directory | rule 1, any depth |
| GitHub Copilot (cloud agent, CLI, VS Code, JetBrains, code review) | `.github/copilot-instructions.md`; `.github/instructions/**/*.instructions.md`; `AGENTS.md` (nearest wins); `CLAUDE.md`, `GEMINI.md`; prompt files `.github/prompts/*.prompt.md`; custom agents `.github/agents/*.md` (`*.agent.md` in VS Code; formerly `.github/chatmodes/*.chatmode.md`); skills in `.github/skills`, `.claude/skills`, `.agents/skills` | rules 1–3 |
| Claude Code | `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` in the working directory, every ancestor, and (on demand) every subdirectory; `AGENTS.md`; `.claude/rules/**/*.md` (recursive, also nested); skills `.claude/skills/*/SKILL.md`; subagents `.claude/agents/*.md`; commands `.claude/commands/**/*.md` | rules 1, 3 |
| Gemini CLI | `GEMINI.md` in the working directory, its ancestors, and its subdirectories | rule 1 |
| Cursor | `.cursor/rules/**/*.mdc` (a `.md` file there is ignored by Cursor), nested `.cursor/rules`, legacy `.cursorrules`, `AGENTS.md` | rules 1, 3 |
| Agent Skills open standard | `<skills root>/<name>/SKILL.md` | rule 3 |

Decisions:

- **Every depth, not only the root.** Codex, Claude Code, Gemini CLI, Copilot,
  and Cursor all read per-directory files below the root, so a root-only
  inventory would leave a trivial bypass (`docs/AGENTS.md`). The rules apply at
  every depth of the bounded scan, including inside a nested Workspace.
- **Case, width, and normalization folding.** macOS and Windows filesystems
  are case-insensitive by default, and APFS is also normalization-insensitive,
  so a tool
  opening `AGENTS.md` can read a file stored as `agents.md`, or even as
  `AGENT` + U+017F LATIN SMALL LETTER LONG S + `.md`, because U+017F
  case-folds to `s`. Each component is compared after
  `NFKC(casefold(NFKC(x)))`. Over-inclusion on a case-sensitive filesystem
  only means one more inventoried file. Folding uses the implementation's
  Unicode Character Database; under Unicode's normalization and case-folding
  stability policies a newer database can only classify more names as
  instruction names (characters an older one does not assign), and either
  disagreement is a refusal, never an acceptance.
- **Closed and versioned.** The set is named by `rapp-work-instruction-set/1`,
  and its meaning never changes (Art. 2). A wider set is a new token that an
  inventory names; old inventories keep their meaning (Art. 4: growth by
  registration).
- **Out of `/1`, deliberately** (each is an open question for a later set):
  files reached only *by reference* (Claude Code and Gemini CLI `@` imports,
  skill resources and scripts, links), because resolving references means
  parsing instructions differently for each tool; tool *configuration* that
  executes or connects (`.claude/settings.json` hooks, `.github/hooks/*.json`,
  MCP server lists), which is not instruction text; user-level and managed
  files outside the workspace (the tools' per-user home files and
  administrator-managed policy files); names configured per user (Codex
  `project_doc_fallback_filenames`, Gemini CLI `context.fileName`); and tools
  whose first-party documentation was not verified for this draft (Windsurf,
  Cline, Roo, Kiro, Junie, Continue, Zed, Warp, Aider, OpenCode).

### 3.2 Bounds and the no-follow rule

- The scan opens every directory with `O_NOFOLLOW | O_DIRECTORY` relative to
  its parent's descriptor, lists it with `os.scandir(fd)`, compares the opened
  directory's device and inode with the listed entry, and reads instruction
  files with `read_regular_at()` (the existing no-follow, single-link,
  size-bounded, race-checked read, now callable relative to a directory
  descriptor). It never follows a link.
- Bounds: 32 directory levels, 100,000 entries observed, 1,024 instruction
  files, 1 MiB per file, 16 MiB total. Exceeding any bound is a refusal
  (`REFUSE_INSTRUCTION_SCAN_LIMIT`), never a truncation, because a truncated
  scan is a place to hide a file. The 1 MiB file bound is well above what the
  tools load (Codex stops at 32 KiB by default; Claude Code recommends under
  200 lines).
- Only `.git` is excluded: version-control internals are not a working
  directory for any tool. Dependency trees (`node_modules`, virtual
  environments) are scanned, because Claude Code and Copilot read nested files
  wherever the AI works, and packages can ship `AGENTS.md` and `CLAUDE.md`.
  Very large trees therefore hit the entry bound; that is a refusal with a
  clear reason (see Open questions).
- A symbolic link whose own path is an instruction path, whose name is a
  container root (`.github`, `.claude`, `.agents`, `.cursor`), or that sits at
  or below a container is refused, because tools read through it. Other links
  (`data` pointing elsewhere, `node_modules/.bin/*`, `.venv/bin/python`) are
  neither followed nor inventoried: the inventory covers the workspace's own
  tree, just as per-user files outside it are out of scope.

### 3.3 Where the inventory lives (Art. 2)

Options considered:

1. **`rapp-work-managed-files/2`** holding both SDK-owned files and
   instruction files. Rejected: it changes a key set, so every SDK 1.0.0
   verifier would refuse every new workspace, and it merges two ownership
   classes: files the SDK may replace and files the SDK must never touch.
2. **A new record outside the managed inventory.** Rejected: replacing it would
   need a new `update` precondition key, reshaping the update precondition
   record inside `rapp-work-release-plan/1`, and a §4 exception.
3. **Chosen: a new additive record, SDK-owned, listed in the unchanged
   `rapp-work-managed-files/1`.** The managed record's key set, entry grammar,
   and meaning ("files the SDK owns and replaces only under an exact
   precondition") are unchanged; new workspaces simply list one more SDK-owned
   file, which is how any SDK release adds an integration file. The prior
   inventory's hash reaches the update plan through the existing
   `managed_files` precondition, so the `rapp-work-release-plan/1` update
   precondition record keeps exactly its four keys. The observed instruction
   bytes are bound through the planned inventory bytes, which the plan hash
   covers. Deleting the inventory is SDK-owned drift, so it cannot silently
   downgrade a workspace to "no inventory".

### 3.4 Refuse, not "absent"

A Workspace or Organization with SDK integration but no SDK-owned inventory is
**refused** (`REFUSE_INSTRUCTION_INVENTORY_ABSENT`) rather than verified with
an `absent` flag:

- Consumers gate on the envelope status. A verified workspace whose instruction
  files are unprotected is a false assurance.
- "Absent" would give an attacker a downgrade: delete the record, then edit
  freely. The record is SDK-owned, so its deletion is already refused as drift.
- It is the same experience as every SDK release (Context item 6): one
  reviewed `update`, whose `instruction_review` shows the owner every
  instruction file and hash being trusted for the first time.
- A legacy identity that can be verified only as an identity (no update path;
  migration creates a successor) keeps its explicit weak status
  `verified-legacy-identity-only`, now with `instruction_inventory: "absent"`,
  so the output says so.

### 3.5 The acceptance path

No new operation, flag, or public API. `update` planning re-inventories the
exact observed bytes; SDK-owned instruction files (the integration skill) are
recorded with the bytes the SDK writes. The planned result adds a derived
`rapp-work-instruction-review/1` (every path, change kind, and old and new byte
length and SHA-256) so a person reviews hashes instead of base64. Apply
requires the explicit request, the whole plan, and its exact SHA-256.
`_validate_update_plan()` rescans before the first write, both for a fresh
apply and when resuming from the recovery marker, and refuses
(`REFUSE_PRECONDITION`, with every changed path) if an instruction file
differs from the reviewed plan. A forged plan that omits a file from the
planned inventory is refused the same way. An edit to an SDK-owned instruction
file stays SDK-owned drift and has no acceptance path. `update` never writes an
owner's instruction file.

### 3.6 Organizations, nested trees, and compatibility wrappers

- An Organization's scan covers its own directory tree. A Workspace placed
  inside that tree is part of it, because an AI opened at the Organization root
  reads it; the SPEC recommends placing Workspaces beside an Organization. The
  pointer registry (`workspaces.json`) is unchanged and never carries
  instruction data, and the inventory holds only paths, sizes, and hashes.
  Stopping at nested roots was rejected for `/1` because a planted
  `rappid.json` would then hide any instruction file below it.
- Scaffold and migration add the inventory for the files they create.
  Migration needed no code change: `_migration_files()` builds on
  `_workspace_files()` and already lists every `.rapp-work/` file as
  SDK-owned.
- The deprecated `rapp_work.compat` wrappers and their fixtures are unchanged.
  They never write an inventory; a workspace they create is a legacy
  Workspace, and one reviewed `update` integrates and inventories it.

## 4. Proposed normative text

The branch's `protocols/rapp-work-sdk/1/SPEC.md` contains exactly the text
below. Because this profile is package-qualified and not pinned by the signed
estate registry, the branch edits it directly and re-pins its SHA-256 in
`protocols/index.json` and `src/rapp_work/data/profiles.json`.

**§4 Filesystem boundary — insert after the second paragraph:**

````markdown
Instruction files (§7.1) are authority-bearing. They are read only through the
bounded no-follow instruction scan of §7.2. SDK updates never create, replace,
or delete an instruction file that is not SDK-owned.
````

**§7 Workspace and Organization — insert after the existing two paragraphs:**

````markdown
### 7.1 Instruction files

An instruction file is a file that an AI tool reads as instructions or context
because of where it is. Instruction files steer every AI that opens a Workspace
or Organization, so an unreviewed edit or a newly placed instruction file is a
prompt-injection path into private (GODD) data.

`rapp-work-instruction-set/1` is the closed set of instruction paths. Paths are
relative to the Workspace or Organization root and use `/` separators. Each
path component is compared after the fold `NFKC(casefold(NFKC(component)))`
(Unicode normalization form NFKC and full case folding), so case, width, and
canonical-equivalence variants that a case-insensitive or
normalization-insensitive filesystem may resolve to an instruction name are
covered. A path is an instruction path when at least one of these holds:

1. its final component is `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`,
   `CLAUDE.local.md`, `GEMINI.md`, or `.cursorrules`;
2. its final component is `copilot-instructions.md` and the component before
   it is `.github`; or
3. two consecutive directory components above the final component form one of
   these containers, and the final component satisfies the container's rule:

| Container | Final component |
|---|---|
| `.github/instructions` | ends with `.instructions.md` |
| `.github/prompts` | ends with `.prompt.md` |
| `.github/agents` | ends with `.md` |
| `.github/chatmodes` | ends with `.chatmode.md` |
| `.github/skills`, `.claude/skills`, `.agents/skills` | is `SKILL.md` |
| `.claude/rules`, `.claude/agents`, `.claude/commands` | ends with `.md` |
| `.cursor/rules` | ends with `.mdc` |

The rules apply at every depth of the scanned tree. Files reached only by
reference from an instruction file (imports, links, skill resources) and tool
configuration (settings, hooks, MCP server lists) are not instruction paths in
this set. The meaning of `rapp-work-instruction-set/1` never changes; a wider
set is a new token.

### 7.2 Instruction scan

The instruction scan walks the Workspace or Organization root with
descriptor-relative, no-follow directory operations. It never follows a
symbolic link and never descends into an entry named `.git`. It descends into
every other directory, including a Workspace nested inside the tree. It is
bounded:

- at most 32 directory levels below the root;
- at most 100,000 directory entries observed;
- at most 1,024 instruction files; and
- at most 1 MiB per instruction file and 16 MiB for all instruction files.

Exceeding a bound is refused with `REFUSE_INSTRUCTION_SCAN_LIMIT`; the scan
never truncates. The scan refuses with `REFUSE_INSTRUCTION_PATH`:

- an instruction path that is a symbolic link, a hard-linked file, a
  directory, or any other non-regular entry;
- a symbolic link or other non-regular, non-directory entry named `.github`,
  `.claude`, `.agents`, or `.cursor`, or located at or below a §7.1 container;
  and
- an instruction path that is not valid UTF-8 or does not satisfy the portable
  relative-path grammar (at most 512 characters; no empty, `.`, or `..`
  component; no control character, backslash, or colon).

Other symbolic links and non-regular entries are neither followed nor
inventoried.

### 7.3 Instruction inventory

`.rapp-work/instructions.json` is an SDK-owned file listed in the
`rapp-work-managed-files/1` inventory. Its bytes are canonical RAPP/1 JSON with
exactly these members:

```json
{
  "files": [
    {"bytes": 151, "path": "CLAUDE.md", "sha256": "<64 lowercase hex>"}
  ],
  "instruction_set": "rapp-work-instruction-set/1",
  "profile": "rapp-work-sdk/1",
  "schema": "rapp-work-instruction-inventory/1",
  "sdk_version": "<major>.<minor>.<patch>"
}
```

`files` lists every instruction file of the scanned tree exactly once, in path
order (ascending Unicode code point order of the path, which is also the byte
order of its UTF-8 encoding), each entry with exactly `bytes`, `path`, and
`sha256` of the file's exact bytes. `sdk_version` names the SDK release that wrote the record. The
inventory never contains file content. An SDK-owned instruction file appears
with the bytes the SDK writes. Scaffold and migration create the inventory
together with the files they create, so the canonical hash of a new scaffold or
migration plan differs from an earlier SDK's plan.

### 7.4 Verification

Workspace and Organization verification reads the SDK-owned inventory, runs
the §7.2 scan, and refuses:

- `REFUSE_INSTRUCTION_INVENTORY_ABSENT` when no SDK-owned inventory exists;
- `REFUSE_INSTRUCTION_INVENTORY` when the inventory is not canonical, not
  closed, not path sorted and unique, over a §7.2 bound, or lists a path that
  is not an instruction path;
- `REFUSE_INSTRUCTION_DRIFT` when an inventoried file's bytes differ
  (`changed`), an inventoried file is absent (`missing`), or an instruction
  file is not inventoried (`unlisted`); and
- the §7.2 refusals.

A drift refusal names every affected path and its reason in path order, at
most 64 of them, with the total count. No refusal echoes file content. A
verified result reports the instruction file count, the instruction set, and
the SHA-256 of the inventory bytes, so an owner or another observer can pin
the reviewed inventory outside the Workspace.

### 7.5 Accepting an instruction change

`update` is the only operation that changes the inventory. Its plan records
the exact instruction bytes observed at planning time: it adds the inventory
when none is SDK-owned, or replaces it with the prior inventory's exact SHA-256
as the `managed_files` precondition, and it replaces the managed inventory. An
unowned file already at `.rapp-work/instructions.json` carries no authority: it
is adopted only when its bytes are exactly the planned bytes, and is otherwise
refused as an unmanaged collision. The planned result also carries a derived
`rapp-work-instruction-review/1` object with exactly `files`,
`instruction_set`, `inventory` (the inventory path), `prior_inventory`
(`present` or `absent`), and `schema`. `files` lists every path of the prior
and planned inventories once, in path order, with exactly `path`, `change`
(`added`, `changed`, `removed`, or `unchanged`), `bytes`, `sha256`,
`prior_bytes`, and `prior_sha256`; a side without the path is `null`. The
review is for the person reviewing the plan; the plan and its SHA-256 remain
the only authority.

Apply requires the explicit request, the complete plan, and its exact SHA-256
(§2). Before the first write, including when resuming an interrupted apply, the
implementation rescans and refuses with `REFUSE_PRECONDITION`, naming each
path, if the instruction files differ from the reviewed plan. An edit to an
SDK-owned instruction file is SDK-owned drift and is never accepted. There is
no other acceptance path: no additional operation, flag, or automatic
acceptance.

### 7.6 Organizations, earlier Workspaces, and compatibility wrappers

An Organization's inventory covers its own directory tree only. A Workspace
placed inside that tree is part of it for §7.2, so Workspaces SHOULD be placed
beside, not inside, an Organization. The pointer registry never carries
instruction data.

A Workspace or Organization without an SDK-owned inventory, including one
integrated by an earlier SDK release, is refused by verification until a
reviewed update adds the inventory. A legacy Workspace without SDK integration
receives the integration files and the inventory in one update plan. A legacy
identity that verification can check only as an identity reports
`instruction_inventory: "absent"`; migration creates an inventoried successor.
The deprecated compatibility wrappers keep their historical behavior and never
write an inventory; a workspace they create is a legacy Workspace.
````

**§12 Refusals — replace the paragraph with:**

````markdown
Unsupported sharing, public Git, credential inheritance, implicit apply,
unknown JSON members, parent-authority changes, plugin execution, neuron
execution, source deletion, owner rotation, unverified Hive rollback/fork
acceptance, and unreviewed instruction-file changes are explicit refusals.
````

## 5. Token and compatibility analysis

| Token or shape | Change |
|---|---|
| `rapp-work-instruction-inventory/1` | **New** record at `.rapp-work/instructions.json` (SPEC §7.3). |
| `rapp-work-instruction-set/1` | **New** closed path set (SPEC §7.1), named by the record. |
| `rapp-work-instruction-review/1` | **New** derived output object in a planned `update` result (SPEC §7.5); not authority. |
| `rapp-work-managed-files/1` | Unchanged key set, grammar, and meaning. New workspaces list one more SDK-owned file. |
| `rapp-work-release-plan/1` | Unchanged shape. Scaffold, update, and migration plans may contain one more `FileAction`; the update precondition record keeps exactly `identity_sha256`, `managed_files`, `managed_sha256`, `root_identity`. |
| `rapp-work-sdk/1` record (`sdk.json`) and `schema.json` | Unchanged; `schema.json` and its pin are untouched. |
| `rapp-work-update-recovery/1`, migration tokens | Unchanged shapes. |
| `rapp-work-result/1` envelope | Unchanged seven keys. The `verify` subject adds `instruction_files`, `instruction_set`, and `instruction_inventory_sha256`; the identity-only subject adds `instruction_inventory`; a planned `update` result adds `instruction_review`. Operation results are not closed by the envelope token. |
| Public operations and top-level API | Unchanged: the six operations, `__all__`, inputs, and CLI flags. |
| RAPP/1 (Art. 18) | No change to canonicalization, hashes, RAPPIDs, the eleven-key Frame, wire forms, or Eggs. The record is canonical JSON from the pinned canonicalizer (Art. 10). |

Pins changed on the branch: the `rapp-work-sdk/1` `spec_sha256` in
`protocols/index.json` and `src/rapp_work/data/profiles.json` (to the SHA-256
of the edited SPEC), and `RELEASE-INVENTORY.json` (regenerated). Nothing that
records signed authority changed: root `SPEC.md`, `registry.json`, its
signature, `owner-anchor.json`, `RAPP1_PIN.json`, `RAPP_WORK_PIN.json`, the
Hive and Federation profiles, and the legacy skill fixtures are untouched.
`tools/check.py` passes.

Compatibility, measured against SDK 1.0.0 extracted from `origin/main`:

| Scenario | Result |
|---|---|
| Workspace scaffolded by 1.0.0, verified by 1.0.0 | `ok` |
| Same workspace verified by this branch | refused, `REFUSE_INSTRUCTION_INVENTORY_ABSENT` |
| This branch's update plan for it | `create .rapp-work/instructions.json`, `replace .rapp-work/managed.json` |
| After applying that plan: this branch / 1.0.0 verify | `ok` / `ok` |
| Workspace scaffolded by this branch, verified by 1.0.0 | `ok` (1.0.0 checks the extra SDK-owned file's bytes) |
| 1.0.0 update plan for it | `replace .rapp-work/managed.json` (drops the inventory from the owned set) |
| After applying that downgrade, this branch verify | refused, `REFUSE_INSTRUCTION_INVENTORY_ABSENT` |
| This branch's update plan, then apply, then verify | `replace .rapp-work/managed.json` (adopts the unchanged unowned record), `applied`, `ok` |

Plans are bound to the SDK that built them: an unapplied 1.0.0 scaffold,
update, or migration plan is refused by this branch (`REFUSE_PLAN`,
`REFUSE_PRECONDITION`, or `REFUSE_MIGRATION_PLAN`) and must be re-planned, and
a completed 1.0.0 migration cannot be replayed as `unchanged` by this branch.
The completed target itself is verified and brought forward with `update`.

## 6. Security and privacy analysis

- **Threat closed.** An unreviewed edit to, addition of, removal of, or link to
  an instruction file anywhere in the scanned tree turns verification red, with
  every path and reason. A change is trusted only after a person reviews the
  exact hashes and applies the exact plan.
- **Time of check and time of use.** Apply rescans before the first write, in
  both the fresh and the resumed path, and refuses on any difference; the
  directory walk is descriptor-relative with device and inode checks, and
  file reads are single-link, size-bounded, and stable across the read.
- **A change racing an apply.** A change made after the pre-write rescan is
  caught by the verification that closes every apply, and the apply then
  returns that refusal instead of success.
- **Downgrade.** Deleting the inventory is SDK-owned drift
  (`REFUSE_MANAGED_DRIFT`, path named), and an unowned file at the inventory
  path carries no authority.
- **Residual: a consistent rewrite.** Anyone who can write the workspace can
  rewrite both SDK records to match an edit; the records are integrity
  evidence, not a signature, exactly like `rapp-work-managed-files/1` today. A
  verified result reports `instruction_inventory_sha256`, so the owner, a
  Brainstem, or version control can pin the reviewed inventory outside the
  workspace and detect the rewrite (test
  `test_verified_inventory_hash_exposes_a_consistent_rewrite`). A signed
  inventory is an open question.
- **Privacy.** The inventory and every refusal hold paths, sizes, reasons, and
  SHA-256 values, never content (a test asserts that a marker in an edited
  file does not appear in the refusal). The review exposes hashes only to the
  person planning the update on their own device. No network, credential, or
  execution: instruction files are hashed as data and never interpreted.
  Organizations never copy member content; their pointer registry is
  unchanged. Instruction paths are local (GODD) metadata and stay in local
  outputs.

## 7. Migration

1. Upgrade the SDK. `verify` refuses existing Workspaces and Organizations
   with `REFUSE_INSTRUCTION_INVENTORY_ABSENT` (or, after a version bump,
   `REFUSE_SDK_PROFILE` first).
2. `rapp-work update --root <workspace>` plans the change; review
   `result.instruction_review` (every instruction file, marked `added`, with
   its SHA-256).
3. Apply with `--apply --plan <saved envelope> --plan-sha256 <exact hash>`.
   Only `.rapp-work/instructions.json` is created and `.rapp-work/managed.json`
   replaced; no instruction file is written.

Legacy Workspaces without SDK integration receive the integration and the
inventory in one plan. `docs/MIGRATION.md` documents the steps.

## 8. Rollback

Revert the branch (or do not release it). Workspaces keep verifying under SDK
1.0.0, which checks `.rapp-work/instructions.json` only as another SDK-owned
file; an SDK 1.0.0 `update` offers one reviewed plan that drops the record from
the owned set. No instruction file is ever modified in either direction.
Re-upgrading adopts the untouched record in one reviewed plan (table in §5).

## 9. Conformance and test vectors

`tests/test_instruction_inventory.py` (37 test functions, 113 cases with
parameters), using the `sandbox` fixture:

- Positive: scaffold then verify, with exact record bytes and the managed
  listing; nested and pattern files within bounds (20 paths, including depth
  exactly 32 and a case variant); 37 positive and 23 negative path vectors,
  including case, width, and Unicode case-fold variants; update re-inventory
  with the exact plan hash; removal accepted only through update; legacy
  Workspace adoption; SDK 1.0.0 Workspace adoption; unowned record adoption;
  Organization inventory and pointer-only registry; migration successor;
  canonical I-JSON outputs; read-only verify and planning.
- Refusal: edited `CLAUDE.md` (no content echo); new `AGENTS.md`; deleted
  inventoried file; all drifts reported in path order; symlinked instruction
  files and container links (7 cases); hard links; a directory and a FIFO at
  an instruction path; paths outside the portable grammar; depth, entry,
  file-size, file-count, and total-size bounds; wrong plan hash; edit,
  addition, or deletion between plan and apply; a resumed apply after an edit
  during the interruption; a forged plan inventory; an SDK-owned skill edit; a
  deleted inventory; eight malformed or consistently rewritten inventories; a
  Workspace nested in an Organization; an absent inventory.
- Existing suites unchanged and green.

### Mutation proof

Each critical check was mutated locally, `tests/test_instruction_inventory.py`
and `tests/test_sdk_workspace.py` were run, and the source was restored
byte-for-byte (the harness verifies restoration by SHA-256):

| Mutation | Result | Failing tests |
|---|---|---|
| M1 drift ignores unlisted instruction files | red: 9 failed | `test_consistent_rewrite_that_drops_an_entry_is_still_refused`, `test_every_drift_is_reported_in_path_order`, `test_forged_update_plan_inventory_is_refused`, and 6 more |
| M2 drift ignores changed bytes | red: 6 failed | `test_edited_claude_md_is_refused_by_path_without_echoing_content`, `test_every_drift_is_reported_in_path_order`, `test_instruction_change_between_plan_and_apply_is_refused_before_writes`, and 3 more |
| M3 drift ignores missing files | red: 3 failed | `test_deleted_inventoried_instruction_file_is_refused_as_missing`, `test_instruction_change_between_plan_and_apply_is_refused_before_writes`, `test_removed_instruction_file_is_accepted_only_through_update` |
| M4 symlinked/non-regular exposure not refused | red: 8 failed | `test_non_regular_instruction_paths_are_refused`, `test_symlinked_instruction_paths_are_refused` |
| M5 hard-link check removed | red: 1 failed | `test_hardlinked_instruction_files_are_refused` |
| M6 depth bound removed | red: 1 failed | `test_scan_depth_bound_is_refused` |
| M7 entry bound removed | red: 1 failed | `test_scan_entry_bound_is_refused` |
| M8 per-file byte bound removed (generic read limit remains) | red: 1 failed | `test_instruction_file_byte_bound_is_refused` |
| M9 case/Unicode folding removed | red: 52 failed | `test_consistent_rewrite_that_drops_an_entry_is_still_refused`, `test_deleted_inventoried_instruction_file_is_refused_as_missing`, `test_edited_claude_md_is_refused_by_path_without_echoing_content`, and 26 more |
| M10 folding reduced to str.lower | red: 2 failed | `test_instruction_set_positive_vectors` |
| M11 inventory may list non-instruction paths | red: 1 failed | `test_malformed_inventory_is_refused` |
| M12 non-canonical inventory accepted | red: 1 failed | `test_malformed_inventory_is_refused` |
| M13 verify trusts the inventory without scanning | red: 23 failed | `test_consistent_rewrite_that_drops_an_entry_is_still_refused`, `test_deleted_inventoried_instruction_file_is_refused_as_missing`, `test_edited_claude_md_is_refused_by_path_without_echoing_content`, and 14 more |
| M14 absent inventory accepted | red: 2 failed | `test_sdk_1_0_0_workspace_is_refused_until_update_adds_the_inventory`, `test_unowned_inventory_file_carries_no_authority` |
| M15 apply-time instruction replay removed | red: 5 failed | `test_forged_update_plan_inventory_is_refused`, `test_instruction_change_between_plan_and_apply_is_refused_before_writes`, `test_resumed_update_rechecks_instruction_bytes_before_writing` |
| M16 update apply hash gate removed | red: 1 failed | `test_update_reinventories_exact_bytes_and_requires_the_exact_plan_hash` |
| M17 scaffold omits instruction files from the inventory | red: 21 failed | `test_deleted_inventoried_instruction_file_is_refused_as_missing`, `test_edited_claude_md_is_refused_by_path_without_echoing_content`, `test_every_drift_is_reported_in_path_order`, and 18 more |
| M18 missing SDK-owned file reported imprecisely | red: 1 failed | `test_deleted_inventory_is_refused_without_automatic_repair` |

All 18 mutations turned the suite red; the harness restored and re-hashed the sources afterwards.

## 10. Reference implementation and gating

- `src/rapp_work/instructions.py` (new): the set, folding, bounded no-follow
  scan, record build and strict parse, drift, and review.
- `src/rapp_work/workspace.py`: the inventory in `_integration_files()`,
  scaffold templates, `plan_update_with_review()`, the apply-time rescan in
  `_validate_update_plan()`, verification for Workspace and Organization, and a
  precise `REFUSE_MANAGED_DRIFT` for a missing SDK-owned file (the code the
  existing `plan_update()` branch already intended).
- `src/rapp_work/_paths.py`: `read_regular_at()` extracted from
  `read_regular()` without behavior change.
- `src/rapp_work/api.py`: `instruction_review` in planned `update` results;
  `instruction_inventory: "absent"` on identity-only legacy results.
- Docs: `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/MIGRATION.md`,
  `protocols/README.md`, `README.md`, `CHANGELOG.md`.

Gating: the behavior exists only on this experimental branch, together with the
proposed SPEC text it implements; the CHANGELOG entry is "Unreleased
(proposal, not accepted)"; the package version is unchanged and nothing is
released, tagged, or activated. New behavior is scoped to the new tokens, and
the default for anything without a reviewed inventory is fail-closed. The
`kody-w/rapp-work` workflow does not run on branch pushes; the local mirror of
its job passed on Python 3.13 and 3.10 (§12).

## 11. Open questions for the owner

1. **Release number.** 1.1.0 (new record; verification needs one reviewed
   update, as every release already does) or 2.0.0 (verification of existing
   workspaces becomes red until updated)?
2. **Set breadth.** Register Windsurf, Cline, Roo, Kiro, Junie, Continue, Zed,
   Warp, Aider, and OpenCode locations in `rapp-work-instruction-set/2` after
   first-party verification?
3. **References and configuration.** Should a later set cover skill
   directories whole (scripts and resources), `@` import targets, and
   executable agent configuration (hooks, MCP lists, settings)?
4. **Large trees.** Keep refusing trees above 100,000 entries, or let an
   update plan record reviewed opaque subtrees (for example dependency
   caches), each named in the inventory?
5. **Nested roots.** Keep whole-tree scanning for Organizations, or stop at
   nested RAPP roots and record them as reviewed boundaries?
6. **Signature.** Should a later profile sign the inventory with the owner's
   keyed RAPPID (as `SignedRelease` does for plans), closing the
   consistent-rewrite residual?
7. **JSON Schema.** Publish a schema for `rapp-work-instruction-inventory/1`
   next to `protocols/rapp-work-sdk/1/schema.json`?

## 12. Evidence

All commands ran in this branch's own clone.

- `python3 tools/check.py`: `RAPP Work: signed registry and all profile
  conformance checks PASS`.
- Local mirror of the `kody-w/rapp-work` workflow job (`tools/check.py`,
  `pytest`, `ruff`, `mypy`, `tools/release_inventory.py --check`,
  `python -m build`, `tools/verify_package.py`) on Python 3.13 and 3.10:
  `ALL RAPP-WORK CI STEPS PASS: 3.13 3.10`; pytest `282 passed, 69 subtests
  passed` on each (baseline `origin/main`: `169 passed, 69 subtests passed`);
  release inventory 147 files; wheel 114 files; sdist 156 files.
- Cross-version table (§5): SDK 1.0.0 extracted from `origin/main` and this
  branch, run against the same workspaces.
- Mutation table (§9).
- Privacy scan of the branch diff against `origin/main`: `0 finding(s)`.

## 13. Owner actions needed

1. Accept, amend, or reject the SPEC text in §4 of this proposal.
2. Choose the release number (Open question 1).
3. If accepted: merge the branch, cut the release, and record the gap's status
   change in the organism. This branch opens no pull request or issue.

Ready-to-file summary, if the owner wants a tracking issue: "G7:
`rapp-work-sdk/1` verification inventories AI instruction files (proposal
0007, branch `experimental/gap-g7-instruction-inventory`); decision needed on
the SPEC text and the release number."

## 14. References

- `protocols/rapp-work-sdk/1/SPEC.md` §2, §4, §7, §10, §12 (this repository).
- `src/rapp_work/workspace.py`, `src/rapp_work/api.py`,
  `src/rapp_work/migration.py`, `src/rapp_work/_paths.py`; `docs/API.md`
  "Explicitly deferred".
- `.github/skills/rapp-workspace-manager/templates/workspace-SPEC.md` §2.
- RAPP/1 Protocol Constitution (`kody-w/rapp-1` `CONSTITUTION.md`): Art. 2
  (one label, one shape), Art. 4 (growth by registration), Art. 8 (red oracles
  are findings), Art. 10 (one canonicalizer), Art. 18 (the wire is frozen).
- Gap G7 in the RAPP/1 organism (`organism/gaps/G07.md` on
  `kody-w/rapp-work` branch `experimental/rapp-work-constitution`).
- GitHub Docs, "Support for different types of custom instructions":
  https://docs.github.com/en/copilot/reference/custom-instructions-support
- GitHub Docs, "Copilot customization cheat sheet":
  https://docs.github.com/en/copilot/reference/customization-cheat-sheet
- GitHub Docs, "About agent skills":
  https://docs.github.com/en/copilot/concepts/agents/about-agent-skills
- Claude Code Docs, "How Claude remembers your project":
  https://code.claude.com/docs/en/memory
- OpenAI, "Custom instructions with AGENTS.md" (Codex):
  https://developers.openai.com/codex/guides/agents-md
- Gemini CLI, "Provide context with GEMINI.md files":
  https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html
- Cursor Docs, "Rules": https://cursor.com/docs/rules
- AGENTS.md: https://agents.md
- Agent Skills specification: https://github.com/agentskills/agentskills
- Unicode Standard Annex #15 (normalization forms) and the Unicode
  `CaseFolding.txt` data file.
