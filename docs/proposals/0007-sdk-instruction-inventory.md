# Proposal 0007: SDK instruction-file inventory

- **Status:** draft, not accepted. The owner decides.
- **Gap:** G7 — SDK verification accepts an edited instruction file. SDK
  verification does not notice when an instruction file was edited; the fix
  puts instruction files in the inventory and refuses new ones.
- **Home spec and section:** `rapp-work-sdk/1`
  ([`protocols/rapp-work-sdk/1/SPEC.md`](../../protocols/rapp-work-sdk/1/SPEC.md))
  §7 "Workspace and Organization", with insertions in §4 "Filesystem
  boundary" and §12 "Refusals".
- **Blocks:** Workspaces (RAPP Workspace/1; "Your private, local-first
  workspaces (GODD), changed only by exact SDK plans").
- **Branch:** `experimental/gap-g7-instruction-inventory` in `kody-w/rapp-work`.
- **Intended release:** `rapp-work` 1.1.0, or 2.0.0 if the owner wants strict
  verification by default (Open question 1). The package version and
  `SDK_VERSION` are unchanged on this branch.
- **Revision:** round 2. It answers the round-1 independent review; the
  disposition of every finding is in §15.

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
   checks the identity, the SDK-owned files through `_read_managed()`, and that
   `.rapp-work/sdk.json` parses to exactly the record the running SDK would
   write (`_sdk_record()`, which embeds `SDK_VERSION`). `Organization.verify()`
   checks the identity, the SDK-owned files, the descriptor, and the pointers;
   it never reads `sdk.json`, and `_read_managed()` returns an empty set when
   `.rapp-work/managed.json` is absent. `src/rapp_work/api.py` `_verify()`
   requires `.rapp-work/managed.json` only for a Workspace. So an edited
   `CLAUDE.md`, a new `AGENTS.md`, `.github/copilot-instructions.md`, or
   `.claude/rules/*.md`, or a linked instruction file, all verify; and an
   Organization verifies across SDK releases and with no `.rapp-work/` at all
   (`managed_files: 0`).
3. **The SPEC is silent.** `rapp-work-sdk/1` §7 says only that a Workspace has
   one RAPPID and one `world_id`, that updating is additive for legacy
   workspaces and limited to SDK-owned integration files, and that an
   Organization is pointer-only. §4 makes symlinks and hard links refusals only
   for "authority-bearing reads and all writes".
4. **The ecosystem already says instructions are authority.** The RAPP
   Workspace template (`.github/skills/rapp-workspace-manager/templates/workspace-SPEC.md`
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
6. **An SDK release needs one update for Workspaces only.** Because
   `Workspace.verify()` compares `sdk.json` with the running SDK's record, a
   Workspace integrated by one SDK version is refused (`REFUSE_SDK_PROFILE`) by
   the next until `update` is applied. Organizations are not affected (item 2).

## 2. Proposed change (summary)

1. Define the closed, versioned instruction-path set
   `rapp-work-instruction-set/1` (§3.1; SPEC §7.1), re-checked against each
   vendor's current documentation.
2. Scan for it with a bounded, descriptor-relative, no-follow walk that refuses
   rather than truncates, and that handles links by exact rules: in-tree links
   are recorded with the bytes a tool reads through them; links that would
   expose content the scan cannot see are refused (SPEC §7.2).
3. Record it in a new additive SDK-owned record,
   `.rapp-work/instructions.json` (`rapp-work-instruction-inventory/1`): path,
   byte length, and SHA-256 of every instruction file, never content (SPEC
   §7.3). The record is listed in the unchanged `rapp-work-managed-files/1`
   inventory.
4. **Compatible default.** A tree that owns the record is verified against it
   and refused on any drift. A tree that does not own it, including every
   Workspace and Organization integrated by SDK 1.0.0, is not refused and is
   never reported as plainly `verified`: its subject is
   `verified-without-instruction-inventory` with `instruction_inventory:
   "absent"`. Strict refusal is an explicit opt-in (`verify` input
   `require_instruction_inventory`), and the owner may make it the 2.0.0
   default (SPEC §7.4).
5. The only acceptance path is the existing `update` operation, with a derived
   `rapp-work-instruction-review/1` (SPEC §7.5). A fresh apply rescans before
   its first write; a resumed apply completes the reviewed writes and reports
   later changes; an apply whose closing verification refuses reports its
   effects (`updated-unverified`) instead of a refusal. A tree without the
   record that cannot be inventoried is updated as SDK 1.0.0 would update it,
   and the review says why.

## 3. Design decisions and reasons

### 3.1 Which files are instruction files

An instruction file is a file that an AI coding tool loads, because of where it
is, into a model's context as instructions, rules, prompts, agents, or skills,
or a project configuration file of such a tool that can itself hold
instruction text or name other instruction files. Each row below was
re-checked on 2026-09-25 against the vendor's current first-party
documentation (References); only project-level (in-tree) locations matter,
because per-user and administrator files are outside the workspace.

| Tool (sources) | Project paths the tool loads by location | Covered by |
|---|---|---|
| AGENTS.md open standard | `AGENTS.md` at the root and in any subdirectory; the nearest one wins | rule 1 |
| OpenAI Codex (AGENTS.md guide, skills, configuration, subagents) | `AGENTS.override.md`, then `AGENTS.md`, then configured fallback names, in each directory from the project root to the working directory; skills in `.agents/skills` from the working directory up to the repository root; project configuration `.codex/config.toml` (for example `model_instructions_file`, which names an instructions file); project custom agents `.codex/agents/*.toml` with `developer_instructions` | rules 1, 2 (`.codex/config.toml`), 3 (`.agents/skills`, `.codex/agents`) |
| GitHub Copilot and VS Code (custom instructions support, customization cheat sheet, agent skills, VS Code agent customization) | `.github/copilot-instructions.md`; `.github/instructions/**/*.instructions.md`; `AGENTS.md` (nested with a setting), `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `GEMINI.md`; `.claude/rules/*.md`; prompt files `.github/prompts/*.prompt.md`; custom agents `.github/agents/*.md` and `.claude/agents/*.md` (legacy `.github/chatmodes/*.chatmode.md`); skills in `.github/skills`, `.claude/skills`, `.agents/skills`; `.vscode/settings.json`, whose code-review, commit-message, and pull-request instruction settings take inline `text` or a `file`, and whose deprecated `chat.*Locations` settings add instruction, prompt, agent, and skill folders | rules 1, 2 (`.github/copilot-instructions.md`, `.vscode/settings.json`), 3 |
| Claude Code (memory, skills, subagents, output styles, settings) | `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` in the working directory and every ancestor at launch and in subdirectories on demand; `AGENTS.md` and `.claude/AGENTS.md`; `.claude/rules/**/*.md`, also nested; skills `.claude/skills/**/SKILL.md`, also nested; commands `.claude/commands/**/*.md`; subagents `.claude/agents/**/*.md`; output styles `.claude/output-styles/*.md`, which modify the system prompt; `.claude/settings.json` and `.claude/settings.local.json` (hooks whose output enters context, `autoMemoryDirectory`, `claudeMdExcludes`, `outputStyle`, plugins) | rules 1, 2 (`.claude/settings*.json`), 3 |
| Gemini CLI (GEMINI.md, custom commands, skills, settings, system prompt) | `GEMINI.md` in the workspace directories, their parents, and any directory a tool touches; names configured by `context.fileName` in `.gemini/settings.json`, which overrides user settings; commands `.gemini/commands/**/*.toml`; skills `.gemini/skills/` or `.agents/skills/`; a full system-prompt override `.gemini/system.md` when `GEMINI_SYSTEM_MD` is set (which `.gemini/.env` can do) | rules 1, 2 (`.gemini/settings.json`, `.gemini/system.md`), 3 |
| Cursor (rules, rules help, skills, skills help, subagents, 1.6 changelog, Bugbot) | `.cursor/rules/**/*.mdc` (a `.md` there is ignored), also nested; legacy `.cursorrules`; `AGENTS.md`, also nested; `CLAUDE.md`; skills in `.agents/skills`, `.cursor/skills` (recursive, also in nested project directories), and, for compatibility, `.claude/skills` and `.codex/skills`; subagents in `.cursor/agents`, `.claude/agents`, `.codex/agents`; commands `.cursor/commands/*.md`; Bugbot review rules `.cursor/BUGBOT.md`, at the root and nested | rules 1, 2 (`.cursor/BUGBOT.md`), 3 |
| Agent Skills open standard | a skill is a folder whose `SKILL.md` holds its instructions; locations are chosen by each client | rule 3 |

Decisions:

- **Every depth, not only the root.** Every tool above reads per-directory
  files below the root, so a root-only inventory would leave a trivial bypass
  (`docs/AGENTS.md`). The rules apply at every depth of the bounded scan,
  including inside a nested Workspace. Applying a rule at a depth where one
  tool would not look only inventories one more file.
- **Configuration that names instructions is covered; configuration that only
  runs or connects is not (yet).** A project settings file that can hold
  instruction text or name other instruction files (`.gemini/settings.json`
  `context.fileName`, `.claude/settings*.json` `autoMemoryDirectory`,
  `.codex/config.toml` `model_instructions_file`, `.vscode/settings.json`
  instruction settings) would otherwise defeat the path-based set: one
  unreviewed setting would turn any file into an instruction file. Those
  settings files are therefore instruction paths, hashed whole. Files that
  only run commands or connect tools (`.github/hooks/*.json`,
  `.cursor/hooks.json`, `.codex/hooks.json`, `.mcp.json`, `.vscode/mcp.json`,
  `.cursor/mcp.json`) and environment files (`.gemini/.env`, which may hold
  secrets) are named residuals (Open question 3). Files that a reviewed
  setting names, like files reached by `@` imports, are reached by reference
  and are not inventoried (Open question 4).
- **Case, width, normalization, and ignorable folding.** macOS and Windows
  filesystems are case-insensitive by default and APFS is also
  normalization-insensitive, so a tool opening `AGENTS.md` can read a file
  stored as `agents.md`, or as `AGENT` + U+017F LATIN SMALL LETTER LONG S +
  `.md`, because U+017F case-folds to `s`. HFS+ also ignores code points such
  as U+200C and U+FEFF in names (the class behind CVE-2014-9390). Each
  component is compared after removing every Unicode 16.0.0
  `Default_Ignorable_Code_Point`, then `NFKC(casefold(NFKC(x)))`, then removing
  them again. The ignorable list is pinned in the SPEC, not read from the
  runtime. Over-inclusion on a filesystem that distinguishes the variants only
  inventories one more file. NFKC and case folding use the runtime's Unicode
  database; under Unicode's normalization and case-folding stability policies
  a newer database can only classify more names as instruction names, and
  either disagreement is a refusal, never an acceptance.
- **Any recordable name.** Instruction paths are recorded exactly as the
  filesystem names them, so the portable path grammar used by other SDK records
  (no colon, backslash, or control character; at most 512 characters) does not
  apply: `meeting 10:30/AGENTS.md` is inventoried, not refused. A path must be
  valid UTF-8 (I-JSON cannot carry lone surrogates), have at most 33
  components (the depth bound plus the file name), and have no empty, `.`,
  `..`, NUL-bearing, or over-1,024-byte component.
- **Closed and versioned.** The set is named by `rapp-work-instruction-set/1`
  and its meaning never changes (Art. 2). A wider set is a new token that an
  inventory names; old inventories keep their meaning (Art. 4).

### 3.2 Bounds, links, and the no-follow rule

- The scan opens every directory with `O_NOFOLLOW | O_DIRECTORY` relative to
  its parent's descriptor, lists it with `os.scandir(fd)` while counting
  entries against the global bound (so one huge directory is not read past the
  bound), compares the opened directory's device and inode with the listed
  entry, and reads instruction files with `read_regular_at()` (the existing
  no-follow, single-link, size-bounded, race-checked read, now callable
  relative to a directory descriptor and bound to the listed entry's device
  and inode).
- Bounds: 32 directory levels, 100,000 entries listed, 1,024 instruction
  files, 1 MiB per file, 16 MiB total. Exceeding a bound is
  `REFUSE_INSTRUCTION_SCAN_LIMIT`, never a truncation, because a truncated scan
  is a place to hide a file. A directory the scan cannot open or list is
  `REFUSE_INSTRUCTION_SCAN`: an unreadable directory could hold an instruction
  file that a tool with other rights reads.
- Only `.git` is excluded: version-control internals are not a working
  directory for any tool. Dependency trees are scanned, because Claude Code and
  Copilot read nested files wherever the AI works, and packages can ship
  `AGENTS.md` and `CLAUDE.md`.
- **Links (round-1 findings 5 and 6).** The scan never opens or lists anything
  through a link. It reads a link's text and inspects what the link resolves to
  with `stat`, without opening it, then applies three rules (SPEC §7.2):
  1. A link at an instruction path is recorded, at the link's path, with the
     bytes of its target when the target is an in-tree, single-link regular
     file whose device and inode are what the link resolves to. This makes
     Claude Code's documented `ln -s AGENTS.md CLAUDE.md` verifiable: a later
     edit of `AGENTS.md` shows as a change of both paths, and retargeting the
     link shows as a change of `CLAUDE.md`. Links at instruction paths that
     leave the tree, dangle, chain, or name a directory are refused.
  2. A link that resolves to a directory must have an in-tree target, or it is
     refused: a directory link to a folder outside the tree, or into `.git`,
     would expose unscanned `AGENTS.md` or `CLAUDE.md` files at in-tree paths.
     A directory link at a container position (a link named `.claude`,
     `.github`, `.cursor`, ..., or at or below a container such as
     `.claude/skills`) is listed through, and what it exposes is recorded at
     the link's paths, so `.claude/skills -> ../skills` is verifiable and a
     later edit of `skills/deploy/SKILL.md` shows as a change of
     `.claude/skills/deploy/SKILL.md`. Other in-tree directory links (for
     example package-manager and virtual-environment links) are not listed
     through, because their targets are scanned where they are and, outside a
     container position, a path through a link is an instruction path only
     where the target's own path is one. Loops are refused.
  3. Links that resolve to a file at a non-instruction path, or to nothing,
     expose no instruction path and are ignored.
  The text is resolved lexically, and the device and inode of the entry the
  scan reaches by no-follow steps must equal the link's resolution; that
  catches a text whose `..` climbs out of an intermediate directory link.
- Hard-linked instruction files remain refused, like other hard-linked files
  the SDK reads (§4); package managers that hard-link from a shared store are
  a known limit (Open question 5).

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
   and meaning are unchanged; new workspaces list one more SDK-owned file,
   which is how any SDK release adds an integration file. The prior
   inventory's hash reaches the update plan through the existing
   `managed_files` precondition, so the update precondition record keeps
   exactly its four keys. Deleting a listed inventory is SDK-owned drift
   (`REFUSE_MANAGED_DRIFT`).

### 3.4 A compatible default, a strict opt-in (round-1 finding 2)

Round 1 refused every tree without an inventory. That changed the accepted
default for trees that carry none of the new tokens, including Organizations
that SDK 1.0.0 verifies across releases (Context item 2). This revision
follows the compatible design:

- **No false assurance.** A tree without an SDK-owned inventory is never
  reported as plainly `verified`. Its subject is
  `verified-without-instruction-inventory`, with `instruction_inventory:
  "absent"` and no instruction count or hash, and the envelope stays `ok`
  exactly as SDK 1.0.0 returns it. Consumers that gate on the subject status or
  on `instruction_inventory` see the difference; nothing is scanned, so no
  1.0.0 layout can make it fail.
- **No silent downgrade of a protected tree.** Once the record is listed, any
  drift is refused. Deleting it is `REFUSE_MANAGED_DRIFT`. Unlisting it takes a
  rewrite of `.rapp-work/managed.json` (the consistent-rewrite residual of §6)
  or an owner-applied update plan from an SDK without this section; either
  way verification reports the weak status, never `verified`, and a caller
  that pinned `instruction_inventory_sha256` or passes
  `require_instruction_inventory` notices.
- **Strict is explicit.** `require_instruction_inventory: true` refuses every
  subject without a verified inventory with
  `REFUSE_INSTRUCTION_INVENTORY_ABSENT`. SDK 1.0.0 refuses the member as an
  unknown input (`REFUSE_INPUT_KEYS`), so a consumer that asks for the check
  can never receive a success without it. Making strict the default is a
  2.0.0 decision for the owner (Open question 1).
- **Adoption is one reviewed update.** The next update plan adds the record
  and shows every instruction file as `added` in `instruction_review`. When a
  tree without the record cannot be inventoried (a directory link that leaves
  the tree, an unreadable directory, a bound), the plan is exactly what an SDK
  without this section would plan, and the review names the scan refusal; the
  tree keeps verifying weakly. A tree that owns the record is never planned
  without it.

### 3.5 The acceptance path

No new operation. `update` planning re-inventories the exact observed bytes;
SDK-owned instruction files (the integration skill) are recorded with the
bytes the SDK writes. The planned result adds a derived
`rapp-work-instruction-review/1` so a person reviews hashes instead of base64.
Apply requires the explicit request, the whole plan, and its exact SHA-256.

- **Fresh apply.** `_validate_update_plan()` rescans before the first write and
  refuses (`REFUSE_PRECONDITION`, with every changed path) if an instruction
  file differs from the inventory the plan leaves SDK-owned, whether the plan
  writes, keeps, or adopts it. A forged plan that omits a file from the planned
  inventory, or omits the inventory, is refused.
- **A change after the rescan (round-1 finding 7).** A change that lands after
  the pre-write rescan is caught by the verification that closes the apply.
  The reviewed writes are durable by then, so the result reports them:
  envelope `applied`, `effects: true`, `status: "updated-unverified"`,
  `verification: null`, and `verification_refusal`. A refusal would have said
  that nothing happened (`Refusal` means no effects).
- **Resuming (round-1 finding 8).** A resumed apply completes the reviewed
  writes without the pre-write rescan and closes with verification, which
  reports any instruction change made during the interruption. It records
  nothing that was not reviewed. Round 1 refused the resume instead, which left
  a tree with a pending marker and an edit stuck: the old plan was refused and
  every new plan was refused by the marker binding or by the half-written
  records. While a marker exists, a refused apply of another plan names the
  pending plan's SHA-256, managed-file refusals name the marker, and the CLI
  accepts the marker itself as `--plan`. `docs/MIGRATION.md` documents the
  recovery.

An edit to an SDK-owned instruction file stays SDK-owned drift and has no
acceptance path. `update` never writes an owner's instruction file.

### 3.6 Organizations, nested trees, and compatibility wrappers

- An Organization's scan covers its own directory tree. A Workspace placed
  inside that tree is part of it, because an AI opened at the Organization root
  reads it; the SPEC recommends placing Workspaces beside an Organization.
  Stopping at nested roots was rejected for `/1` because a planted
  `rappid.json` would then hide any instruction file below it.
- Organization behavior is otherwise unchanged: verification still does not
  read `sdk.json` or require `managed.json`. A 1.0.0 Organization and a bare
  Organization (no `.rapp-work/`) verify weakly; one reviewed update adds the
  integration and the inventory.
- Scaffold and migration add the inventory for the files they create;
  `_migration_files()` builds on `_workspace_files()`.
- The deprecated `rapp_work.compat` wrappers and their fixtures are unchanged.
  A workspace they create is a legacy Workspace, and one reviewed `update`
  integrates and inventories it.

## 4. Proposed normative text

The branch's `protocols/rapp-work-sdk/1/SPEC.md` is `main`'s text plus exactly
the three insertions below; no existing line is changed, so the insertions
compose with sibling drafts (§14). Because this profile is package-qualified
and not pinned by the signed estate registry, the branch edits it directly and
re-pins its SHA-256 in `protocols/index.json` and
`src/rapp_work/data/profiles.json`.

**§4 Filesystem boundary — insert after the first paragraph** (before
"Create-only means ..."):

````markdown
Instruction files (§7.1) are not SDK authority: the SDK hashes them and never
interprets them. They are read only by the bounded instruction scan of §7.2,
which applies its own link rules and never opens or lists anything through a
symbolic link. SDK updates never create, replace, or delete an instruction
file that is not SDK-owned.
````

**§7 Workspace and Organization — insert after the existing two paragraphs:**

````markdown
### 7.1 Instruction files

An instruction file is a file that an AI coding tool loads, because of where it
is, into a model's context as instructions, rules, prompts, agents, or skills,
or a project configuration file of such a tool that can itself hold instruction
text or name other instruction files. Instruction files steer every AI that
opens a Workspace or Organization, so an unreviewed edit or a newly placed
instruction file is a prompt-injection path into private (GODD) data.

`rapp-work-instruction-set/1` is the closed set of instruction paths. Paths are
relative to the Workspace or Organization root and use `/` separators. Each
path component is compared after the fold
`strip(NFKC(casefold(NFKC(strip(component)))))`, where `NFKC` is Unicode
normalization form NFKC, `casefold` is full Unicode case folding, and `strip`
removes every code point that has the `Default_Ignorable_Code_Point` property
in `DerivedCoreProperties.txt` of Unicode 16.0.0. Case, width,
canonical-equivalence, and ignorable-code-point variants that a
case-insensitive, normalization-insensitive, or ignorable-insensitive
filesystem may resolve to an instruction name are therefore covered. Table
entries below are written unfolded and compared folded. A path is an
instruction path when at least one of these holds:

1. its final component is `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`,
   `CLAUDE.local.md`, `GEMINI.md`, or `.cursorrules`;
2. its final component and the component before it are one of these pairs:

   | Directory | Final component |
   |---|---|
   | `.github` | `copilot-instructions.md` |
   | `.cursor` | `BUGBOT.md` |
   | `.gemini` | `system.md` or `settings.json` |
   | `.claude` | `settings.json` or `settings.local.json` |
   | `.codex` | `config.toml` |
   | `.vscode` | `settings.json` |

3. two consecutive directory components above the final component form one of
   these containers, and the final component satisfies the container's rule:

   | Container | Final component |
   |---|---|
   | `.github/instructions` | ends with `.instructions.md` |
   | `.github/prompts` | ends with `.prompt.md` |
   | `.github/agents` | ends with `.md` |
   | `.github/chatmodes` | ends with `.chatmode.md` |
   | `.github/skills`, `.claude/skills`, `.agents/skills`, `.cursor/skills`, `.codex/skills`, `.gemini/skills` | is `SKILL.md` |
   | `.claude/rules`, `.claude/agents`, `.claude/commands`, `.claude/output-styles` | ends with `.md` |
   | `.cursor/rules` | ends with `.mdc` |
   | `.cursor/agents`, `.cursor/commands` | ends with `.md` |
   | `.codex/agents` | ends with `.md` or `.toml` |
   | `.gemini/commands` | ends with `.toml` |

The rules apply at every depth of the scanned tree. These are not instruction
paths in this set: files reached only by reference (imports, links written in
instruction text, skill resources and scripts, and files that a configuration
file names), environment files, and configuration that only runs commands or
connects tools (hook files and MCP server lists). The meaning of
`rapp-work-instruction-set/1` never changes; a wider set is a new token.

### 7.2 Instruction scan

The instruction scan walks the Workspace or Organization root with
descriptor-relative, no-follow directory operations, listing each directory in
name order. It never opens or lists anything through a symbolic link and never
descends into an entry named `.git`. It descends into every other directory,
including a Workspace nested inside the tree. It is bounded:

- at most 32 directory levels below the root;
- at most 100,000 directory entries listed, counted while listing, so listing
  stops at the first entry over the bound;
- at most 1,024 instruction files; and
- at most 1 MiB per instruction file and 16 MiB for all instruction files.

Exceeding a bound is refused with `REFUSE_INSTRUCTION_SCAN_LIMIT` (details
`limit`, `reason` `depth`, `entries`, `files`, `file-bytes`, or `total-bytes`,
and `path` where one applies); the scan never truncates. A directory that
cannot be opened or listed, or an entry or link that cannot be inspected, is
refused with `REFUSE_INSTRUCTION_SCAN` (details `path` and `reason`
`unreadable` or `uninspectable`), because an incomplete scan cannot show that
no instruction file is there. An entry that changes identity while it is
scanned is refused with `REFUSE_FILE_RACE`.

A path is recordable when it is valid UTF-8, has at most 33 components, and
none of its components is empty, `.`, or `..`, contains NUL, or exceeds 1,024
bytes. The portable path grammar of other SDK records does not apply to
instruction paths.

An instruction file is a regular file with exactly one link, read with a
no-follow read bound to the device and inode of the entry the scan listed. For
a symbolic link, the scan may read the link's text and inspect, without opening
it, what the link resolves to. Its target is *in the tree* when the text is
relative, resolves lexically against the link's directory without climbing
above the root and without a component that folds to `.git`, and names an
existing entry that the scan reaches from the root by no-follow steps and that
has the device and inode the link resolves to. Then:

1. A link at an instruction path is recorded, at the link's path, with the
   bytes of its target when the target is an in-tree regular file with exactly
   one link. Any other link at an instruction path is refused.
2. A link that resolves to a directory is refused unless its target is in the
   tree. When the link's final component folds to `.github`, `.claude`,
   `.agents`, `.cursor`, `.codex`, `.gemini`, or `.vscode`, or two consecutive
   folded components of its path form a container of §7.1, the scan lists the
   target directory as if it were at the link's path and records the
   instruction files found there at those paths; a target that is already being
   listed on the current path is refused as a loop. Other directory links are not listed through: their
   targets are scanned where they are, and a path through such a link is an
   instruction path only where the target's own path is one.
3. Any other link, including one that resolves to nothing, is neither followed
   nor recorded.

The scan refuses with `REFUSE_INSTRUCTION_PATH`, with details `path` and a
`reason`: `symlink` when a link rule above refuses; `symlink-loop` for a loop;
`hardlink` for an instruction file with more than one link; `not-regular` for a
directory, FIFO, socket, or device at an instruction path; `path-grammar` for
an instruction path that is not recordable; and `unreadable` for an instruction
file that cannot be read without following links.

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

`files` lists every instruction file that the §7.2 scan records exactly once,
in path order (ascending Unicode code point order of the path, which is also
the byte order of its UTF-8 encoding), each entry with exactly `bytes`, `path`,
and `sha256` of the exact bytes a tool reads at that path, including a path
recorded through a link. `sdk_version` names the SDK release that wrote the
record. The inventory never contains file content. An SDK-owned instruction
file appears with the bytes the SDK writes. Scaffold and migration create the
inventory together with the files they create, so the canonical hash of a new
scaffold or migration plan differs from an earlier SDK's plan.

### 7.4 Verification

Workspace and Organization verification (`verify`, `Workspace.verify()`, and
`Organization.verify()`) first performs every check it performed without this
section. Then:

- When `.rapp-work/instructions.json` is listed in the SDK-owned inventory,
  verification reads it, runs the §7.2 scan, and refuses:
  `REFUSE_INSTRUCTION_INVENTORY` when the inventory is not canonical, not
  closed, not path sorted and unique, over a §7.2 bound, or lists a path that is
  not a recordable instruction path; `REFUSE_INSTRUCTION_DRIFT` when a recorded
  file's bytes differ (`changed`), a recorded path is absent (`missing`), or an
  instruction file is not recorded (`unlisted`); and the §7.2 refusals. A
  verified subject has `status` `verified`, `instruction_inventory`
  `verified`, `instruction_files`, `instruction_set`, and
  `instruction_inventory_sha256`, the SHA-256 of the inventory bytes, so an
  owner or another observer can pin the reviewed inventory outside the tree.
- When it is not listed, including in every Workspace and Organization
  integrated before this section and when an unowned file is at that path,
  verification does not scan. The subject has `status`
  `verified-without-instruction-inventory` and `instruction_inventory`
  `absent`, never `verified`, because no instruction file was checked. A legacy
  identity that verification can check only as an identity
  (`verified-legacy-identity-only`) also has `instruction_inventory` `absent`.

`verify` accepts one more optional input member,
`require_instruction_inventory`, a Boolean that defaults to `false`. When it
is `true`, verification refuses with `REFUSE_INSTRUCTION_INVENTORY_ABSENT`
(details `inventory`) unless the subject's instruction inventory is verified:
a Workspace or Organization without an SDK-owned inventory, a legacy or other
identity, and a source estate are refused. An SDK without this section refuses
the member as unknown input, so a consumer that requires the check never
receives a success without it. `Workspace.verify()` and
`Organization.verify()` accept the same keyword argument.

A drift refusal names every affected path and its reason in path order, at
most 64 of them, with the total count. No refusal or review echoes file
content.

### 7.5 Accepting an instruction change

`update` is the only operation that changes the inventory. Its plan records
the exact instruction bytes observed at planning time: it creates the
inventory when none is SDK-owned, or replaces it with the prior inventory's
exact SHA-256 as the `managed_files` precondition, and it replaces the managed
inventory. An unowned file already at `.rapp-work/instructions.json` carries no
authority: it is adopted only when its bytes are exactly the planned bytes, and
is otherwise refused as an unmanaged collision.

When no inventory is SDK-owned and the §7.2 scan is refused with
`REFUSE_INSTRUCTION_PATH`, `REFUSE_INSTRUCTION_SCAN`, or
`REFUSE_INSTRUCTION_SCAN_LIMIT`, the plan is built without an inventory, as an
SDK without this section builds it. When an inventory is SDK-owned, those
refusals refuse the plan.

The planned result carries a derived `rapp-work-instruction-review/1` object
with exactly `files`, `instruction_set`, `inventory` (the inventory path),
`planned_inventory` and `prior_inventory` (each `present` or `absent`),
`scan_refusal` (`null`, or the `code`, `details`, and `message` of the scan
refusal that left the plan without an inventory), and `schema`. `files` lists
every path of the prior and planned inventories once, in path order, with
exactly `path`, `change` (`added`, `changed`, `removed`, or `unchanged`),
`bytes`, `sha256`, `prior_bytes`, and `prior_sha256`; a side without the path
is `null`. The review is for the person reviewing the plan; the plan and its
SHA-256 remain the only authority.

Apply requires the explicit request, the complete plan, and its exact SHA-256
(§2). Before its first write, an apply that is not resuming rescans and refuses
with `REFUSE_PRECONDITION`, naming each path, if the instruction files differ
from the inventory that the plan leaves SDK-owned. An apply that resumes an
interrupted apply of the same plan (its `rapp-work-update-recovery/1` marker
exists) completes the reviewed writes without that rescan: it records nothing
that was not reviewed, and the verification that closes it reports an
instruction change made during the interruption. While a marker exists, a
refused apply of another plan (`REFUSE_RECOVERY_BINDING`) names the marker and
the pending plan's SHA-256 (`pending_plan_sha256`), and `REFUSE_MANAGED_DRIFT`
and `REFUSE_MANAGED_COLLISION` name the marker as `recovery_pending`.

Every apply with effects ends with verification. When that verification
refuses, for example because an instruction file changed after the pre-write
rescan, the result still reports the completed effects: `effects` `true`,
`status` `updated-unverified`, `verification` `null`, and
`verification_refusal` with the refusal's `code`, `details`, and `message`.
Verification keeps refusing until a new reviewed plan accepts the change.

An edit to an SDK-owned instruction file is SDK-owned drift and is never
accepted. There is no other acceptance path: no other operation and no
automatic acceptance.

### 7.6 Organizations, earlier trees, and compatibility wrappers

An Organization's inventory covers its own directory tree only. A Workspace
placed inside that tree is part of it for §7.2, so Workspaces SHOULD be placed
beside, not inside, an Organization. The pointer registry never carries
instruction data. Organization verification continues not to read
`.rapp-work/sdk.json` or require `.rapp-work/managed.json`.

A Workspace or Organization integrated by an earlier SDK, or a legacy
Workspace, receives the inventory from its next reviewed update plan together
with any other integration change. The deprecated compatibility wrappers keep
their historical behavior and never write an inventory; a workspace they
create is a legacy Workspace.
````

**§12 Refusals — insert before the existing paragraph:**

````markdown
Unreviewed instruction-file changes in a Workspace or Organization whose
instruction inventory is SDK-owned are explicit refusals (§7.4).
````

## 5. Token and compatibility analysis

| Token or shape | Change |
|---|---|
| `rapp-work-instruction-inventory/1` | **New** record at `.rapp-work/instructions.json` (SPEC §7.3). |
| `rapp-work-instruction-set/1` | **New** closed path set (SPEC §7.1), named by the record. |
| `rapp-work-instruction-review/1` | **New** derived output object in a planned `update` result (SPEC §7.5); not authority. |
| `rapp-work-managed-files/1` | Unchanged key set, grammar, and meaning. New workspaces list one more SDK-owned file. |
| `rapp-work-release-plan/1` | Unchanged shape. Scaffold, update, and migration plans may contain one more `FileAction`; the update precondition record keeps exactly `identity_sha256`, `managed_files`, `managed_sha256`, `root_identity`. |
| `rapp-work-update-recovery/1`, migration tokens | Unchanged shapes. The CLI additionally accepts a recovery marker as the `--plan` file. |
| `rapp-work-sdk/1` record (`sdk.json`) and `schema.json` | Unchanged; `schema.json` and its pin are untouched. |
| `verify` input | One more optional member, `require_instruction_inventory` (Boolean). The six operations, the other inputs, and their closedness are unchanged; SDK 1.0.0 refuses the member (`REFUSE_INPUT_KEYS`). `src/rapp_work/data/api.json` lists it, so the metadata that `status` returns lists it too. |
| `rapp-work-result/1` envelope | Unchanged seven keys. The `verify` subject adds `instruction_inventory` always and, when verified, `instruction_files`, `instruction_set`, and `instruction_inventory_sha256`; a tree without an inventory gets the new subject status `verified-without-instruction-inventory`; a planned `update` result adds `instruction_review`; an applied update may have the new status `updated-unverified` with `verification_refusal`; three existing refusals gain detail members (`recovery_pending`; `marker` and `pending_plan_sha256`). Operation results are not closed by the envelope token. |
| Public operations and top-level API | Unchanged: the six operations and `__all__`. `Workspace.verify()` and `Organization.verify()` gain a keyword-only `require_instruction_inventory=False`. CLI `verify` gains `--require-instruction-inventory`. |
| RAPP/1 (Art. 18) | No change to canonicalization, hashes, RAPPIDs, the eleven-key Frame, wire forms, or Eggs. The record is canonical JSON from the pinned canonicalizer (Art. 10). |

Pins changed on the branch: the `rapp-work-sdk/1` `spec_sha256` in
`protocols/index.json` and `src/rapp_work/data/profiles.json` (to the SHA-256
of the edited SPEC), and `RELEASE-INVENTORY.json` (regenerated). Nothing that
records signed authority changed: root `SPEC.md`, `registry.json`, its
signature, `owner-anchor.json`, `RAPP1_PIN.json`, `RAPP_WORK_PIN.json`, the
Hive and Federation profiles, and the legacy skill fixtures are untouched.
`tools/check.py` passes.

**Default behavior for accepted artifacts.** For a tree without the new record,
`verify` differs from SDK 1.0.0 only in the subject: `verified` becomes
`verified-without-instruction-inventory` and `instruction_inventory: "absent"`
is added; the envelope and every refusal are unchanged. Its next `update` plan
also adopts the record (reviewed like any integration change), unless the tree
cannot be inventoried, when the plan is exactly SDK 1.0.0's. Scaffold and
migration plans for new trees include the record, so their canonical hashes
differ from SDK 1.0.0 plans.

Compatibility, measured on 2026-09-25 by running SDK 1.0.0 (a file copy of
`origin/main`) and this branch against the same trees, each in its own
interpreter (`scratch` harness, not committed):

| Scenario | Result |
|---|---|
| workspace: scaffold by 1.0.0 | `applied` |
| workspace: 1.0.0-scaffolded, verify by 1.0.0 | `ok`, subject `verified` |
| workspace: 1.0.0-scaffolded, verify by branch | `ok`, subject `verified-without-instruction-inventory`, `instruction_inventory: "absent"` |
| workspace: 1.0.0-scaffolded, strict verify by branch | refused, `REFUSE_INSTRUCTION_INVENTORY_ABSENT` |
| workspace: 1.0.0-scaffolded, strict input sent to 1.0.0 | refused, `REFUSE_INPUT_KEYS` |
| workspace: 1.0.0-scaffolded, branch update plan | `create .rapp-work/instructions.json`, `replace .rapp-work/managed.json`; review: planned `present`, prior `absent` |
| workspace: 1.0.0-scaffolded, branch update plan+apply | `create .rapp-work/instructions.json`, `replace .rapp-work/managed.json` → `applied` (`updated`) |
| workspace: after branch adoption, verify by branch | `ok`, subject `verified`, `instruction_inventory: "verified"` |
| workspace: after branch adoption, verify by 1.0.0 | `ok`, subject `verified` |
| workspace: scaffold by branch | `applied` |
| workspace: branch-scaffolded, verify by 1.0.0 | `ok`, subject `verified` |
| workspace: branch-scaffolded, 1.0.0 update plan | `replace .rapp-work/managed.json` |
| workspace: branch-scaffolded, 1.0.0 update plan+apply (downgrade) | `replace .rapp-work/managed.json` → `applied` (`updated`) |
| workspace: after 1.0.0 downgrade, verify by branch | `ok`, subject `verified-without-instruction-inventory`, `instruction_inventory: "absent"` |
| workspace: after 1.0.0 downgrade, branch update plan+apply | `replace .rapp-work/managed.json` → `applied` (`updated`) |
| workspace: after re-adoption, verify by branch | `ok`, subject `verified`, `instruction_inventory: "verified"` |
| workspace: 1.0.0-scaffolded, verify by 1.0.0 with SDK_VERSION 1.0.1 | refused, `REFUSE_SDK_PROFILE` (`SDK_VERSION` 1.0.1) |
| workspace: 1.0.0-scaffolded, verify by branch with SDK_VERSION 1.0.1 | refused, `REFUSE_SDK_PROFILE` (`SDK_VERSION` 1.0.1) |
| organization: scaffold by 1.0.0 | `applied` |
| organization: 1.0.0-scaffolded, verify by 1.0.0 | `ok`, subject `verified` |
| organization: 1.0.0-scaffolded, verify by branch | `ok`, subject `verified-without-instruction-inventory`, `instruction_inventory: "absent"` |
| organization: 1.0.0-scaffolded, strict verify by branch | refused, `REFUSE_INSTRUCTION_INVENTORY_ABSENT` |
| organization: 1.0.0-scaffolded, strict input sent to 1.0.0 | refused, `REFUSE_INPUT_KEYS` |
| organization: 1.0.0-scaffolded, branch update plan | `create .rapp-work/instructions.json`, `replace .rapp-work/managed.json`; review: planned `present`, prior `absent` |
| organization: 1.0.0-scaffolded, branch update plan+apply | `create .rapp-work/instructions.json`, `replace .rapp-work/managed.json` → `applied` (`updated`) |
| organization: after branch adoption, verify by branch | `ok`, subject `verified`, `instruction_inventory: "verified"` |
| organization: after branch adoption, verify by 1.0.0 | `ok`, subject `verified` |
| organization: scaffold by branch | `applied` |
| organization: branch-scaffolded, verify by 1.0.0 | `ok`, subject `verified` |
| organization: branch-scaffolded, 1.0.0 update plan | `replace .rapp-work/managed.json` |
| organization: branch-scaffolded, 1.0.0 update plan+apply (downgrade) | `replace .rapp-work/managed.json` → `applied` (`updated`) |
| organization: after 1.0.0 downgrade, verify by branch | `ok`, subject `verified-without-instruction-inventory`, `instruction_inventory: "absent"` |
| organization: after 1.0.0 downgrade, branch update plan+apply | `replace .rapp-work/managed.json` → `applied` (`updated`) |
| organization: after re-adoption, verify by branch | `ok`, subject `verified`, `instruction_inventory: "verified"` |
| organization: 1.0.0-scaffolded, verify by 1.0.0 with SDK_VERSION 1.0.1 | `ok`, subject `verified` (`SDK_VERSION` 1.0.1) |
| organization: 1.0.0-scaffolded, verify by branch with SDK_VERSION 1.0.1 | `ok`, subject `verified-without-instruction-inventory`, `instruction_inventory: "absent"` (`SDK_VERSION` 1.0.1) |
| organization: bare (no .rapp-work), verify by 1.0.0 | `ok`, subject `verified` |
| organization: bare (no .rapp-work), verify by branch | `ok`, subject `verified-without-instruction-inventory`, `instruction_inventory: "absent"` |
| organization: bare (no .rapp-work), branch update plan | `create .github/skills/rapp-work-sdk/SKILL.md`, `create .rapp-work/instructions.json`, `create .rapp-work/managed.json`, `create .rapp-work/sdk.json`; review: planned `present`, prior `absent` |
| workspace with an outside directory link: verify by 1.0.0 | `ok`, subject `verified` |
| workspace with an outside directory link: verify by branch | `ok`, subject `verified-without-instruction-inventory`, `instruction_inventory: "absent"` |
| workspace with an outside directory link: branch update plan | no actions; review: planned `absent`, prior `absent`, `scan_refusal` `REFUSE_INSTRUCTION_PATH` |
| workspace with an outside directory link: 1.0.0 update plan applied by branch | `ok` (`unchanged`) |
| workspace: unapplied 1.0.0 update plan applied by branch | `refused`, `REFUSE_PRECONDITION` |
| workspace: unapplied branch update plan applied by 1.0.0 | `refused`, `REFUSE_PLAN` |
| workspace: unapplied 1.0.0 scaffold plan applied by branch | `refused`, `REFUSE_PLAN` |
| workspace: unapplied 1.0.0 migration plan applied by branch | `refused`, `REFUSE_MIGRATION_PLAN` |
| workspace: branch migration plan applied by branch | `applied` |
| workspace: branch migration successor, verify by 1.0.0 | `ok`, subject `verified` |
| workspace: branch migration successor, verify by branch | `ok`, subject `verified`, `instruction_inventory: "verified"` |

Plans are bound to the SDK that built them: an unapplied SDK 1.0.0 scaffold,
update, or migration plan is refused by this branch and must be re-planned,
except that an update plan for a tree this branch cannot inventory is the same
plan in both. A completed 1.0.0 migration target is brought forward with
`update`.

## 6. Security and privacy analysis

- **Threat closed, for trees that own the record.** An unreviewed edit to,
  addition of, or removal of an instruction file anywhere in the scanned tree,
  a retargeted in-tree link, or a link that would expose unscanned content
  turns verification red, with every path and reason. A change is trusted only
  after a person reviews the exact hashes and applies the exact plan.
- **Trees without the record are not protected, and say so.** They verify as
  `verified-without-instruction-inventory`; nothing about instruction files was
  checked. Callers that need protection pass `require_instruction_inventory`.
- **Downgrade.** Deleting a listed record is `REFUSE_MANAGED_DRIFT`. Unlisting
  it needs a rewrite of `.rapp-work/managed.json` (below) or an owner-applied
  update plan from an SDK without this section (measured in §5). Either leaves
  the weak status, never `verified`; a pinned `instruction_inventory_sha256` or
  the strict input detects it. An unowned file at the inventory path carries
  no authority.
- **Residual: a consistent rewrite.** Anyone who can write the workspace can
  rewrite both SDK records to match an edit; the records are integrity
  evidence, not a signature, exactly like `rapp-work-managed-files/1` today. A
  verified result reports `instruction_inventory_sha256`, so the owner, a
  Brainstem, or version control can pin the reviewed inventory outside the
  workspace and detect the rewrite (test
  `test_verified_inventory_hash_exposes_a_consistent_rewrite`). A signed
  inventory is Open question 7.
- **Residual: what `/1` does not cover.** Configuration that only runs
  commands or connects tools (hook files, MCP server lists), environment
  files, files reached by reference (imports, skill resources, files named by
  a reviewed setting), per-user and administrator files, and tools outside
  §3.1. An attacker who can add a hook file can run commands without touching
  an instruction file; that is a separate integrity class (Open question 3).
- **Time of check and time of use.** A fresh apply rescans before the first
  write and refuses on any difference; a change after that rescan makes the
  apply report `updated-unverified`, and verification keeps refusing. A
  resumed apply writes only the reviewed records and closes with
  verification. The walk is descriptor-relative with device and inode checks;
  file reads are single-link, size-bounded, stable across the read, and bound
  to the listed entry.
- **Links.** The scan opens nothing through a link. It resolves a link's text
  lexically and requires the entry it reaches by no-follow steps to be the
  one the link resolves to (device and inode), so a text that climbs out of
  an intermediate link cannot make the scan read or list something other than
  what a tool reads.
- **Privacy.** The inventory, the review, and every refusal hold paths, sizes,
  reasons, and SHA-256 values, never content (tests assert that a marker in an
  edited file appears in neither a refusal nor a plan). Settings files are
  hashed whole; only their SHA-256 is recorded, and environment files are
  excluded because they commonly hold secrets. The inventory is local (GODD)
  metadata: publish, if anything, only `instruction_inventory_sha256`, which
  reveals nothing about any file. No network, credential, or execution:
  instruction files are hashed as data and never interpreted. Organizations
  never copy member content; their pointer registry is unchanged.

## 7. Migration

1. Upgrade the SDK. Existing Workspaces and Organizations keep verifying,
   with `status: "verified-without-instruction-inventory"`. (After an SDK
   version bump, Workspaces are first refused with `REFUSE_SDK_PROFILE` until
   updated, as with every release; Organizations are not.)
2. `rapp-work update --root <tree>` plans the change; review
   `result.instruction_review` (every instruction file, marked `added`, with
   its SHA-256). If `planned_inventory` is `absent`, `scan_refusal` names what
   must change before the tree can be inventoried.
3. Apply with `--apply --plan <saved envelope> --plan-sha256 <exact hash>`.
   Only `.rapp-work/instructions.json` is created and `.rapp-work/managed.json`
   replaced; no instruction file is written.
4. Consumers that need the guarantee verify with
   `require_instruction_inventory: true`.

Legacy Workspaces without SDK integration receive the integration and the
inventory in one plan. `docs/MIGRATION.md` documents adoption and recovery
from an interrupted update.

## 8. Rollback

Revert the branch (or do not release it). Trees keep verifying under SDK
1.0.0, which checks `.rapp-work/instructions.json` only as another SDK-owned
file; an SDK 1.0.0 `update` offers one reviewed plan that drops the record from
the owned set. No instruction file is ever modified in either direction.
Re-upgrading adopts the untouched record in one reviewed plan (§5).

## 9. Conformance and test vectors

`tests/test_instruction_inventory.py`: 58 test functions, 207 cases with
parameters, using the `sandbox` fixture.

- Positive: scaffold then verify, with exact record bytes and the managed
  listing; 70 positive and 40 negative path vectors covering every §7.1 rule,
  case, width, Unicode case-fold, and default-ignorable variants, and names
  with colon, backslash, and tab; nested and pattern files within bounds (35
  paths, including every new set member and depth exactly 32); in-tree links at
  instruction paths (`CLAUDE.md -> AGENTS.md`) and at container positions
  (`.claude/skills -> ../skills`, `.cursor/skills`, `.vscode`); in-tree links
  that expose nothing new (package-manager and virtual-environment layouts,
  file links, dangling and self links); update re-inventory with the exact plan
  hash; removal accepted only through update; legacy, SDK 1.0.0, bare
  Organization, and unowned-record adoption; the weak status for trees without
  an inventory (Workspace, Organization, and after an SDK version bump); the
  strict input through the API, the typed models, and the CLI; migration
  successor; canonical I-JSON outputs; read-only verify and planning.
- Refusal: edited `CLAUDE.md` (no content echo); new `AGENTS.md`; deleted
  inventoried file; all drifts in path order; the 64-finding bound; 15 link
  vectors that expose unscanned content (outside targets, `.git`, absolute,
  dangling, chained, directory at an instruction path, the root's parent); a
  link whose text climbs out of an intermediate link, at an instruction path
  and at a container; three loops; hard links; a directory and a FIFO at an
  instruction path; paths outside the recordable grammar; depth, entry,
  listing, file-size, file-count, and total-size bounds; an unreadable
  directory; wrong plan hash; edit, addition, or deletion between plan and
  apply; a forged plan inventory and a forged plan without one; an SDK-owned
  skill edit; a deleted inventory; nine malformed or consistently rewritten
  inventories; a Workspace nested in an Organization; non-Boolean strict input.
- Effects and recovery: a change after the pre-write rescan
  (`updated-unverified`); an interrupted protected update resumed after an
  edit; an interrupted 1.0.0 adoption resumed after an edit; a foreign plan
  naming the pending one; the CLI resuming from the marker file.
- Compatibility: four layouts that cannot be inventoried (a directory link that
  leaves the tree, Claude Code's shared-rules link, an unreadable directory, a
  scan bound) keep SDK 1.0.0 verification and update behavior, including after
  an SDK version bump, while a tree that owns the record refuses them.
- Existing suites unchanged and green.

### Mutation proof

Each critical check was mutated locally, `tests/test_instruction_inventory.py`
and `tests/test_sdk_workspace.py` were run, and the source was restored
byte-for-byte (the harness verifies restoration by SHA-256):

| Mutation | Result | Failing tests (first two) |
|---|---|---|
| M1 drift ignores unlisted instruction files | red: 13 failed | `test_change_after_the_prewrite_rescan_is_reported_with_the_effects`, `test_consistent_rewrite_that_drops_an_entry_is_still_refused`, and 11 more |
| M2 drift ignores changed bytes | red: 10 failed | `test_edited_claude_md_is_refused_by_path_without_echoing_content`, `test_every_drift_is_reported_in_path_order`, and 8 more |
| M3 drift ignores missing files | red: 3 failed | `test_deleted_inventoried_instruction_file_is_refused_as_missing`, `test_instruction_change_between_plan_and_apply_is_refused_before_writes`, and 1 more |
| M4 hard-link check removed | red: 1 failed | `test_hardlinked_instruction_files_are_refused` |
| M5 depth bound removed | red: 1 failed | `test_scan_depth_bound_is_refused` |
| M6 entry bound removed | red: 3 failed | `test_directory_listing_stops_at_the_entry_bound`, `test_scan_entry_bound_is_refused`, and 1 more |
| M7 listing materialized before the entry bound | red: 1 failed | `test_directory_listing_stops_at_the_entry_bound` |
| M8 per-file byte bound removed (generic read limit remains) | red: 1 failed | `test_instruction_file_byte_bound_is_refused` |
| M9 case/Unicode folding removed | red: 84 failed | `test_change_after_the_prewrite_rescan_is_reported_with_the_effects`, `test_cli_resumes_from_the_recovery_marker`, and 37 more |
| M10 folding reduced to str.lower | red: 12 failed | `test_default_ignorable_code_points_are_removed_before_matching`, `test_instruction_set_positive_vectors`, and 1 more |
| M11 default-ignorable code points kept | red: 10 failed | `test_default_ignorable_code_points_are_removed_before_matching`, `test_instruction_set_positive_vectors`, and 1 more |
| M12 inventory may list non-instruction paths | red: 1 failed | `test_malformed_inventory_is_refused` |
| M13 non-canonical inventory accepted | red: 1 failed | `test_malformed_inventory_is_refused` |
| M14 verify trusts the inventory without scanning | red: 50 failed | `test_change_after_the_prewrite_rescan_is_reported_with_the_effects`, `test_consistent_rewrite_that_drops_an_entry_is_still_refused`, and 29 more |
| M15 strict opt-in ignored | red: 5 failed | `test_cli_verify_accepts_the_strict_flag`, `test_sdk_1_0_0_and_bare_organizations_verify_weakly_and_adopt`, and 3 more |
| M16 tree without inventory reported as plainly verified | red: 11 failed | `test_cli_verify_accepts_the_strict_flag`, `test_forged_plan_that_drops_the_inventory_is_refused`, and 6 more |
| M17 apply-time instruction replay removed | red: 4 failed | `test_forged_update_plan_inventory_is_refused`, `test_instruction_change_between_plan_and_apply_is_refused_before_writes` |
| M18 update apply hash gate removed | red: 1 failed | `test_update_reinventories_exact_bytes_and_requires_the_exact_plan_hash` |
| M19 scaffold omits instruction files from the inventory | red: 24 failed | `test_deleted_inventoried_instruction_file_is_refused_as_missing`, `test_drift_report_is_bounded_and_counts_every_finding`, and 22 more |
| M20 missing SDK-owned file reported imprecisely | red: 1 failed | `test_deleted_inventory_is_refused_without_automatic_repair` |
| M21 directory links leaving the tree accepted | red: 12 failed | `test_links_that_expose_unscanned_content_are_refused`, `test_trees_that_cannot_be_inventoried_keep_sdk_1_0_0_behaviour` |
| M22 container links not traversed | red: 4 failed | `test_container_link_loops_are_refused`, `test_in_tree_container_links_are_traversed_at_their_link_paths` |
| M23 link-at-instruction-path identity check removed | red: 1 failed | `test_link_resolving_through_another_link_to_a_different_file_is_refused` |
| M24 link loop detection removed | red: 3 failed | `test_container_link_loops_are_refused` |
| M25 link targets through .git accepted | red: 1 failed | `test_links_that_expose_unscanned_content_are_refused` |
| M26 protected tree tolerates an incomplete scan when planning | red: 22 failed | `test_hardlinked_instruction_files_are_refused`, `test_links_that_expose_unscanned_content_are_refused`, and 3 more |
| M27 post-write verification refusal hides the effects | red: 4 failed | `test_change_after_the_prewrite_rescan_is_reported_with_the_effects`, `test_interrupted_adoption_of_a_1_0_0_workspace_resumes_after_an_edit`, and 2 more |
| M28 resumed apply re-refuses instruction edits | red: 3 failed | `test_interrupted_adoption_of_a_1_0_0_workspace_resumes_after_an_edit`, `test_resume_is_the_documented_way_out_and_a_foreign_plan_names_the_pending_one`, and 1 more |
| M29 foreign-plan refusal hides the pending plan | red: 1 failed | `test_resume_is_the_documented_way_out_and_a_foreign_plan_names_the_pending_one` |
| M30 directory-link identity check removed | red: 1 failed | `test_container_link_resolving_elsewhere_than_its_text_is_refused` |
| M31 recovery hint removed | red: 2 failed | `test_interrupted_adoption_of_a_1_0_0_workspace_resumes_after_an_edit`, `test_resumed_update_completes_the_reviewed_writes_and_reports_later_edits` |
| M32 absent-inventory planning tolerance removed | red: 4 failed | `test_trees_that_cannot_be_inventoried_keep_sdk_1_0_0_behaviour` |

All 32 mutations turned the suite red; the harness restored and re-hashed the sources afterwards.

## 10. Reference implementation and gating

- `src/rapp_work/instructions.py` (new): the set, folding, the recordable
  grammar, the bounded no-follow scan with its link rules, record build and
  strict parse, drift, and review.
- `src/rapp_work/workspace.py`: the inventory in the integration files and
  scaffold templates; `plan_update_with_review()` with the tolerance for trees
  without an inventory; the planned-inventory derivation and the fresh-apply
  rescan in `_validate_update_plan()`; `updated-unverified`; the resumed-apply
  rule and the recovery hints; the weak status and the strict keyword in
  `Workspace.verify()` and `Organization.verify()`; a precise
  `REFUSE_MANAGED_DRIFT` for a missing SDK-owned file.
- `src/rapp_work/_paths.py`: `read_regular_at()` extracted from
  `read_regular()`, with an optional device-and-inode binding; `read_regular()`
  behaves as before.
- `src/rapp_work/api.py`: the strict `verify` input, `instruction_review` in
  planned `update` results, `instruction_inventory: "absent"` on identity-only
  legacy results. `src/rapp_work/cli.py`: `--require-instruction-inventory`
  and a recovery marker accepted as `--plan`. `src/rapp_work/data/api.json`:
  the new `verify` input and refusal line.
- Docs: `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/MIGRATION.md`,
  `protocols/README.md`, `README.md`, `CHANGELOG.md`.

Gating: the behavior exists only on this experimental branch, together with the
proposed SPEC text it implements; the CHANGELOG entry is "Unreleased
(proposal, not accepted)"; the package version is unchanged and nothing is
released, tagged, or activated. The accepted default for trees that carry none
of the new tokens is kept (the only change is the weaker subject status that
says nothing was checked); refusal of such trees is the explicit opt-in
`require_instruction_inventory`; the new refusals apply to trees that own the
new record. The `kody-w/rapp-work` workflow does not run on branch pushes; the
local mirror of its job passed on Python 3.13 and 3.10 (§12).

## 11. Open questions for the owner

1. **Release number and default.** 1.1.0 with the compatible default and the
   strict opt-in (this draft), or 2.0.0 with strict verification by default
   (`require_instruction_inventory` defaulting to `true`, so trees without an
   inventory are refused until updated)?
2. **Set breadth.** Register Windsurf, Cline, Roo, Kiro, Junie, Continue, Zed,
   Warp, Aider, OpenCode, Amp, Devin, and other tools' locations in
   `rapp-work-instruction-set/2` after first-party verification?
3. **Execution and connection configuration.** Add a companion record for
   hook files, MCP server lists, environment files, cloud-agent setup files
   (`copilot-setup-steps.yml`, `.cursor/environment.json`), and plugin
   manifests, which can run commands or inject context without an instruction
   file?
4. **References.** Should a later set resolve and inventory files reached by
   reference: `@` imports, skill resources, and files named by a reviewed
   setting (`context.fileName`, `project_doc_fallback_filenames`,
   `model_instructions_file`, `autoMemoryDirectory`)?
5. **Large, opaque, or shared trees.** Keep refusing trees above 100,000
   entries, unreadable directories, and hard-linked instruction files (for
   example from package-manager stores), or let an update plan record
   reviewed opaque subtrees and accept hard links hashed by content?
6. **Links that leave the tree.** Claude Code documents shared rules through
   links to folders outside the project. Keep refusing them in trees that own
   the record, or record them as reviewed external references whose content
   is not covered?
7. **Signature.** Should a later profile sign the inventory with the owner's
   keyed RAPPID (as `SignedRelease` does for plans), closing the
   consistent-rewrite residual?
8. **Adoption.** Keep adding the inventory in every update plan (this draft),
   or make adoption an explicit update input?
9. **Nested roots.** Keep whole-tree scanning for Organizations, or stop at
   nested RAPP roots and record them as reviewed boundaries?
10. **JSON Schema.** Publish a schema for `rapp-work-instruction-inventory/1`
    next to `protocols/rapp-work-sdk/1/schema.json`?

## 12. Evidence

All commands ran in this branch's own clone or its scratch directory.

- `python3 tools/check.py`: `RAPP Work: signed registry and all profile
  conformance checks PASS`.
- Local mirror of the `kody-w/rapp-work` workflow job (`tools/check.py`,
  `pytest`, `ruff`, `mypy`, `tools/release_inventory.py --check`,
  `python -m build`, `tools/verify_package.py`) on Python 3.13 and 3.10:
  `ALL RAPP-WORK CI STEPS PASS: 3.13 3.10`; pytest `376 passed, 69 subtests
  passed` on each (baseline `origin/main`: `169 passed, 69 subtests passed`).
- Compatibility table (§5): SDK 1.0.0 and this branch, 50 scenarios.
- Mutation table (§9): 32 of 32 red.
- Privacy scan of the branch diff against `origin/main`: `0 finding(s)`.

## 13. Owner actions needed

1. Accept, amend, or reject the SPEC insertions in §4 of this proposal.
2. Choose the release number and default (Open question 1).
3. Choose the merge order with the sibling drafts (§14).
4. If accepted: merge the branch, cut the release, and record the gap's status
   change in the organism. This branch opens no pull request or issue.

Ready-to-file summary, if the owner wants a tracking issue: "G7:
`rapp-work-sdk/1` verification inventories AI instruction files (proposal
0007, branch `experimental/gap-g7-instruction-inventory`); decisions needed on
the SPEC text, the strict default (1.1.0 or 2.0.0), and the merge order."

## 14. Related proposals

Sibling drafts on `kody-w/rapp-work` that touch the same files or sections,
read at their pushed heads; none was edited.

- **G2, proposal 0002, `experimental/gap-g2-move-action`.** Adds move plans to
  `update` (SPEC §2 input paragraph; a §4 paragraph and §4.1 to §4.3 after the
  second paragraph of §4; one §7 sentence after the first paragraph of §7;
  `api.py` `_update`; `cli.py`; `data/api.json`; its round 2 leaves
  `workspace.py` as on `main`). Its move protection keeps its own closed list:
  any hidden component; the names `AGENTS.md`, `AGENTS.override.md`,
  `CLAUDE.md`, `CLAUDE.local.md`, `GEMINI.md`, `SKILL.md`, `soul.md`, and
  `basic_agent.py` at any depth; four suffixes; and SDK-owned paths, with paths
  that contain a default-ignorable code point refused outright. Every §7.1 path
  is in that list (rules 2 and 3 sit below hidden components), so a move can
  never create, remove, or relocate an instruction path of this set. Both
  drafts use the same `Default_Ignorable_Code_Point` set (4,174 code points in
  Unicode 15.1 and 16.0.0 alike). Once both are accepted, G2 may name its
  instruction files by reference to this set (its open question 11). With both
  merged, a move's precondition runs the kind-specific `verify`, so a move in
  a tree that owns the record requires instruction verification to pass first.
  Textual overlap: this draft's §4 insertion sits after the first paragraph
  and G2's after the second, and G2's §7 sentence follows the first paragraph
  of §7 while §7.1 to §7.6 follow the second, so they compose; `_update` needs
  a manual merge (G2's move branch plus this draft's `instruction_review` and
  update-marker check).
- **G3, proposal 0003, `experimental/gap-g3-agent-discovery`.** SPEC §11.1 and
  discovery code. No shared code; discovered single-file agents are inert data,
  not instruction paths.
- **G4, proposal 0004, `experimental/gap-g4-migration-successors`.** Migration
  successors are built from `_workspace_files()`, so they carry an inventory;
  its `workspace.py` changes (`WORLD_ID_MAX`) do not overlap this draft's
  hunks.
- **G6, proposal 0006, `experimental/gap-g6-owner-succession`.** Adds SPEC
  §5.1 and rewrites the §12 paragraph; this draft's §12 text is a separate
  paragraph inserted before it, so the two compose.
- **G11, proposal 0011, `experimental/gap-g11-workspace-index`.** Proposes
  renaming the pointer-only Organization to a workspace index in prose; §7.6
  would follow the rename without a semantic change.
- **G17, proposal 0017, `experimental/gap-g17-brainstem-sdk-agent`.** The
  Brainstem agent calls `verify` and prints subjects generically; it should
  surface `instruction_inventory` and may pass `require_instruction_inventory`.
- **Every branch** edits `CHANGELOG.md`, `RELEASE-INVENTORY.json`, and, when it
  edits the SDK SPEC, the `spec_sha256` pins in `protocols/index.json` and
  `src/rapp_work/data/profiles.json`: merge one at a time, recompute the pins,
  and run `python3 tools/release_inventory.py --write`.

Recommended merge order: G6, G3, **G7**, G2, G4, G17 (G11 whenever it is
accepted). G7 before G2 lets the move protection import the instruction
classifier; G4 and G17 then consume the inventory and the new verify fields.

## 15. Disposition of the round-1 review

1. Cursor skill folders: fixed; every vendor row re-checked, and the set gained
   `.cursor/skills`, `.codex/skills`, `.gemini/skills`, `.cursor/commands`,
   `.cursor/agents`, `.codex/agents`, `.cursor/BUGBOT.md`,
   `.claude/output-styles`, `.gemini/commands`, `.gemini/system.md`, and the
   settings files that name instructions (§3.1).
2. Default refusal of 1.0.0 trees: fixed as the lead directed (§3.4); §10
   corrected.
3. Organization facts: corrected (Context items 2 and 6, §3.6, §5), with
   1.0.0, bare, and version-bump Organization tests and probes.
4. Gemini CLI: fixed; `.gemini/settings.json`, `.gemini/commands/**/*.toml`,
   and `.gemini/system.md` are instruction paths, and the text is corrected.
5. Directory links: fixed; links that expose unscanned content are refused,
   container links are listed through (§3.2).
6. Common layouts: fixed or disclosed; in-tree link layouts and any
   recordable name are accepted, 1.0.0 verification and update are unaffected,
   and the remaining refusals are listed in §6 and Open questions 5 and 6.
7. Refusal after writes: fixed; `updated-unverified` (§3.5).
8. Stuck recovery: fixed; resumable after an edit, recovery hints, CLI marker
   input, and documentation (§3.5).
9. Ignorable code points: fixed; pinned Unicode 16.0.0 list (§3.1).
10. Unbounded directory read: fixed; counted while listing.
11. `REFUSE_INSTRUCTION_SCAN`: specified in SPEC §7.2, documented in
    `docs/API.md`, and tested.

## 16. References

- `protocols/rapp-work-sdk/1/SPEC.md` §2, §4, §7, §10, §12 (this repository).
- `src/rapp_work/workspace.py`, `src/rapp_work/api.py`,
  `src/rapp_work/migration.py`, `src/rapp_work/_paths.py`; `docs/API.md`
  "Explicitly deferred".
- `.github/skills/rapp-workspace-manager/templates/workspace-SPEC.md` §2.
- RAPP/1 Protocol Constitution (`kody-w/rapp-1` `CONSTITUTION.md`): Art. 2
  (one label, one shape), Art. 4 (growth by registration), Art. 8 (red oracles
  are findings), Art. 10 (one canonicalizer), Art. 18 (the wire is frozen).
- Gap G7 in the RAPP/1 organism (`organism/gaps/G07.md` on `kody-w/rapp-work`
  branch `experimental/rapp-work-constitution`).
- AGENTS.md: https://agents.md
- OpenAI Codex, "Custom instructions with AGENTS.md":
  https://developers.openai.com/codex/guides/agents-md ; "Build skills":
  https://developers.openai.com/codex/skills ; "Advanced configuration"
  (project `.codex/config.toml`):
  https://developers.openai.com/codex/config-advanced ; "Subagents" (project
  `.codex/agents/*.toml`):
  https://learn.chatgpt.com/docs/agent-configuration/subagents
- GitHub Docs, "Support for different types of custom instructions":
  https://docs.github.com/en/copilot/reference/custom-instructions-support ;
  "Copilot customization cheat sheet":
  https://docs.github.com/en/copilot/reference/customization-cheat-sheet ;
  "About agent skills":
  https://docs.github.com/en/copilot/concepts/agents/about-agent-skills ;
  "About hooks": https://docs.github.com/en/copilot/concepts/agents/hooks
- VS Code, agent customization: custom instructions
  https://code.visualstudio.com/docs/agent-customization/custom-instructions ;
  prompt files
  https://code.visualstudio.com/docs/agent-customization/prompt-files ; custom
  agents https://code.visualstudio.com/docs/agent-customization/custom-agents ;
  agent skills
  https://code.visualstudio.com/docs/agent-customization/agent-skills ; hooks
  https://code.visualstudio.com/docs/agent-customization/hooks ; overview
  (deprecated location settings)
  https://code.visualstudio.com/docs/agent-customization/overview
- Claude Code Docs: memory https://code.claude.com/docs/en/memory ; skills
  https://code.claude.com/docs/en/skills ; subagents
  https://code.claude.com/docs/en/sub-agents ; output styles
  https://code.claude.com/docs/en/output-styles ; settings
  https://code.claude.com/docs/en/settings ; hooks
  https://code.claude.com/docs/en/hooks
- Gemini CLI docs (`google-gemini/gemini-cli`, `docs/cli/gemini-md.md`,
  `custom-commands.md`, `skills.md`, `settings.md`, `system-prompt.md`):
  https://github.com/google-gemini/gemini-cli/tree/main/docs/cli ; extensions
  load only from the user's home (`docs/extensions/reference.md`)
- Cursor Docs: rules https://cursor.com/docs/rules ; rules help
  https://cursor.com/help/customization/rules ; skills
  https://cursor.com/docs/skills ; skills help
  https://cursor.com/help/customization/skills ; subagents
  https://cursor.com/docs/subagents ; commands (changelog 1.6)
  https://cursor.com/changelog/1-6 ; Bugbot rules https://cursor.com/docs/bugbot
- Agent Skills specification: https://github.com/agentskills/agentskills
- Unicode 16.0.0 `DerivedCoreProperties.txt` (`Default_Ignorable_Code_Point`):
  https://www.unicode.org/Public/16.0.0/ucd/DerivedCoreProperties.txt ; Unicode
  Standard Annex #15 (normalization forms) and `CaseFolding.txt`.
- Git's handling of names HFS+ treats as equal (CVE-2014-9390).
