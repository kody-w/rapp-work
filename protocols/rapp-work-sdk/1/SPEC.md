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

Instruction files (§7.1) are not SDK authority: the SDK hashes them and never
interprets them. They are read only by the bounded instruction scan of §7.2,
which applies its own link rules and never opens or lists anything through a
symbolic link. SDK updates never create, replace, or delete an instruction
file that is not SDK-owned.

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

Unreviewed instruction-file changes in a Workspace or Organization whose
instruction inventory is SDK-owned are explicit refusals (§7.4).

Unsupported sharing, public Git, credential inheritance, implicit apply,
unknown JSON members, parent-authority changes, plugin execution, neuron
execution, source deletion, owner rotation, and unverified Hive rollback/fork
acceptance are explicit refusals.
