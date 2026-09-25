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

Instruction files (§7.1) are authority-bearing. They are read only through the
bounded no-follow instruction scan of §7.2. SDK updates never create, replace,
or delete an instruction file that is not SDK-owned.

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
execution, source deletion, owner rotation, unverified Hive rollback/fork
acceptance, and unreviewed instruction-file changes are explicit refusals.
