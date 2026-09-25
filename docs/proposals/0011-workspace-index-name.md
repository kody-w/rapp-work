# Proposal 0011 — The SDK's pointer-only "Organization" is a workspace index

## Status

**Draft, not accepted.**

An AI agent drafted this proposal for gap G11 of the RAPP/1 LTS lock-in and
pushed it to the experimental branch `experimental/gap-g11-workspace-index`
only. It opens no pull request and merges nothing. This branch changes no
code, no token, no pin and no normative text of `rapp-work-sdk/1`. It adds
this document, an "Unreleased (proposal, not accepted)" note in
`CHANGELOG.md`, and the regenerated `RELEASE-INVENTORY.json`, because every
file under `docs/` ships in the source distribution.

The package version and `SDK_VERSION` stay `1.0.0` on this branch. The
intended releases for the implementation are **rapp-work 1.1.0** (step 1:
read both forms) and **1.2.0** (steps 2 and 3: write the new form, convert
through migration).

**Numbering.** `docs/proposals/` does not exist on `main`. This proposal
takes the gap's number: G11 is 0011.

## Gap

**G11 — "Organization" means two things.** The SDK uses "organization" for a
pointer-only object, while `rapp-work/1` uses it for the accountable body.
The organism records the fix, naming the SDK's object "workspace index", as
an idea
([`organism/gaps/G11.md`](https://github.com/kody-w/rapp-work/blob/experimental/rapp-work-constitution/organism/gaps/G11.md),
phase 3, blocks: organization). Gap G22 is its twin for the word
"workspace"; RAPP proposal 0010 in `kody-w/RAPP` handles it, with the same
naming table as this proposal.

## Home specification and section

- **`rapp-work-sdk/1` §7, "Workspace and Organization"**
  (`protocols/rapp-work-sdk/1/SPEC.md`, lines 92-101 at `29ead23`, the
  current `main`), with the successor sentence of §10 (lines 129-132) and
  the refusal list of §12 (lines 158-161).
- **Activation.** The signed `registry.json` does not pin this profile, so no
  re-signature is needed. `protocols/index.json` and
  `src/rapp_work/data/profiles.json` pin its `SPEC.md` by SHA-256; those pins
  move in step 1, when the accepted text lands. Acceptance of the text is the
  owner's.

## Context

Line numbers are at `29ead23` unless another commit is named.

### Two meanings

- **The accountable body (canonical).** Canonical `rapp-work/1`
  (`kody-w/rapp-1` at `591e014`, pinned here by `RAPP_WORK_PIN.json`) binds
  "one work organization" to its Hive, releases, migrations and custody. Its
  `work.organization` kind carries the closed `rapp-work/1-organization`
  payload (SPEC.md §1, lines 36-44), which binds "`organization_rappid`,
  which is also the frame stream id", the accountable `owner_rappid`, one
  `world_id`, one `hive_rappid`, the `release_scope`, `policy_sha256` and
  `created_utc` (§2, lines 56-72). The reference validates it
  (`rapp_work.py`, `validate_organization`, line 227). This repository ships
  byte-exact mirrors in `src/rapp_work/data/`.
- **The pointer-only object (this SDK).** `rapp-work-sdk/1` §7: "An
  Organization is a pointer-only routing object. Its registry may contain
  only workspace RAPPID, lexical path, world, mode, name, and active state.
  It MUST NOT copy workspace content, credentials, prompts, histories, or
  native provider stores."
- **Its ancestor.** The legacy workspace manager
  (`.github/skills/rapp-workspace-manager/`, a deprecated compatibility
  surface) keeps a pointer registry `workspaces.json` with schema
  `rapp-workspace-manager/1` and "stores pointers only—never workspace
  content" (`SKILL.md`, lines 9-11; `scripts/manage.py`, lines 19 and
  75-108).

### Every place the pointer-only Organization appears

| Surface | Where | Today |
|---|---|---|
| Normative profile | `protocols/rapp-work-sdk/1/SPEC.md` §7 (lines 92-101), §10 (lines 129-132) | "Workspace and Organization"; "Its registry may contain only…"; "a successor integration workspace or Organization" |
| Kinds | `src/rapp_work/workspace.py` line 35 | `WORKSPACE_KINDS = {"workspace", "organization"}` |
| Scaffolded `SPEC.md` | `workspace.py` line 66 | title "RAPP Work Organization" |
| Records | `workspace.py` lines 136-154 (`_organization_files`) | `organization.json` (`rapp-work-organization/1`: `organization_rappid`, `pointer_policy`, `profile`, `schema`, `world_id`) and `workspaces.json` (`rapp-work-organization-pointers/1`: `organization_rappid`, `schema`, `workspaces`) |
| Identity and scaffold | `workspace.py` lines 169-278 and 352-375 | `Literal["workspace", "organization"]`; `kind` in `rappid.json`; dispatch to `_organization_files` |
| Update | `workspace.py` lines 433-439, 675-678 and 730 | "only workspaces and pointer-only organizations can adopt the SDK profile" |
| Model | `workspace.py` lines 805-1010 (`class Organization`) | `pointers()`; `plan_register` (subject `kind: "organization-register"`, `organization_rappid`, precondition `organization_identity_sha256`, refusal detail `organization_world`); `apply_register`; `verify` (result `kind: "organization"`); refusal code `REFUSE_ORGANIZATION` |
| JSON API | `src/rapp_work/api.py` lines 22-30, 85, 151-152 and 162 | `status` reports `classification: "organization"` (`str(identity["kind"])`); `verify` dispatches on the kind |
| Migration | `src/rapp_work/migration.py` lines 26, 29-40, 52-57 and 321-336 | `organization.json` and `workspaces.json` are bound source authority; an Organization migrates to an Organization |
| CLI | `src/rapp_work/cli.py` line 36 | `--kind` choices `workspace`, `organization` |
| Public API | `src/rapp_work/__init__.py` lines 37 and 58; `tests/test_public_contract.py` line 30 | `Organization` in `__all__` |
| Docs | `README.md` line 117; `docs/API.md` line 50; `docs/ARCHITECTURE.md` line 48; `docs/MIGRATION.md` line 20; `CHANGELOG.md` lines 16-17 (the 1.0.0 entry, history) | "pointer-only Organization" |
| Tests | `tests/test_sdk_workspace.py` lines 12, 25-33 and 310-349; `tests/test_sdk_migration.py` lines 35-55 and 222-229 | scaffold, register, world boundary, migrate |
| Legacy skill | `.github/skills/rapp-workspace-manager/` | the ancestor above; frozen, fixtures preserved |
| Canonical body | `kody-w/rapp-1` `protocols/rapp-work/1/SPEC.md` §§1-2 and `schema.json` `$defs.organization`; mirrors `src/rapp_work/data/rapp-work-1-SPEC.md` and `rapp-work-1-schema.json` | the accountable body; not the SDK's object |
| Another repository | `kody-w/rapp-workspace` `protocols/rapp-work-sdk/1/SPEC.md` §5 and `schemas/discovery.schema.json` | pointer-only `organization_pointers` to `workspace-composite` addresses |
| Plain English, not the object | `.github/skills/autonomous-rapp-estate-manager/SKILL.md` lines 17, 43, 221 and 244; `.github/skills/rapp-workspace/SKILL.md` line 3; `.github/skills/rapp-private-hive/DEPLOYMENT.md` line 329 | "organize", "organization metadata", "organization-policy" |

### What the collision costs

- **One key, two meanings.** `organization_rappid` is the accountable body's
  RAPPID and body stream id in signed `work.organization` payloads, and a
  local, unsigned pointer folder's RAPPID in `organization.json` and
  `workspaces.json`.
- **A misleading classification.** `status` reports
  `classification: "organization"` for a folder with no owner, policy,
  release scope, Hive or body stream.
- **It grows worse at activation.** Phase 4 of the lock activates canonical
  `rapp-work/1` (gap G16). Once real organizations exist, an SDK
  "Organization" beside them invites "which organization?" from people and
  AIs alike.
- **Prose cannot fix it.** RAPP's Lexicon ruling R6 lets a word keep two
  meanings if the prose qualifies it. Here machines compare `kind`, `schema`,
  key and `classification` values byte for byte, so the names themselves
  must differ.

### What the suite pins today (mutations run locally, then restored)

- **Mutation A: a silent in-place rename passes.** Replacing
  `rapp-work-organization/1` with `rapp-work-workspace-index/1`,
  `rapp-work-organization-pointers/1` with
  `rapp-work-workspace-index-pointers/1`, and `organization_rappid` with
  `workspace_index_rappid` throughout `workspace.py` and `migration.py`
  leaves the full suite green: 169 passed, 69 subtests (Python 3.13). No test
  pins those bytes, so exactly the reshaping that RAPP/1 Article 2 forbids
  would go unnoticed.
- **Mutation B: a file rename is caught once.** Renaming the descriptor file
  from `organization.json` turns one test red:
  `tests/test_sdk_migration.py::test_pointer_only_organization_migrates_as_organization`.
- **So step 1 starts by pinning the 1.0.0 bytes** (vector P1), which must be
  red under Mutation A.

### How SDK 1.0.0 reads a future workspace index

A scratch probe, outside the repository, built a directory in the proposed
form (`kind: "workspace-index"` identity, `workspace-index.json` and
`workspaces.json` with the new tokens) and ran this branch's SDK on it with
Python 3.13:

| Operation | 1.0.0 result |
|---|---|
| `status` | `ok`, `classification: "legacy-workspace"`, subject kind `workspace-index` |
| `verify` | `ok`, subject `verified-legacy-identity-only` |
| `update` | refused, `REFUSE_IDENTITY` |
| `migrate` | refused, `REFUSE_MIGRATION_SOURCE` |

An older SDK therefore never reads a workspace index as an Organization and
never changes one. It reports only the identity, and calls it "legacy",
which is wrong but harmless.

### Two release interactions that exist today

The same probe showed them. Neither is caused by this proposal; both matter
to any release that carries it.

- **`Workspace.verify` is bound to the SDK version.** With `SDK_VERSION`
  raised to 1.1.0 and nothing else changed, `verify` refuses a 1.0.0
  Workspace with `REFUSE_SDK_PROFILE` until `update` runs, because
  `.rapp-work/sdk.json` records `sdk_version` and must match exactly. A 1.0.0
  Organization still verifies, because its `verify` does not read `sdk.json`.
- **A completed-migration replay is bound to the SDK version.** The
  successor's `sdk.json` and `managed.json` record `sdk_version`, and apply
  recomputes the plan, so a later SDK cannot replay a 1.0.0 migration as
  unchanged.

### One label, two documents (a finding, not fixed here)

`kody-w/rapp-workspace` ships its own `protocols/rapp-work-sdk/1/SPEC.md`, a
different document under the same label: "RAPP Work SDK/1", a sidecar
profile (8179 bytes, SHA-256 `4d404a1a…`), where this repository's is
6614 bytes (`cf64a90f…`). Its discovery document names pointer-only
references `organization_pointers`. The LTS lock pins "`rapp-work-sdk/1`"
without saying which. This proposal names only this repository's §7; the
other document's field is a follow-up once the owner decides which document
owns the label.

## Options

| Option | Verdict | Why |
|---|---|---|
| **A. "Workspace index"** | **Recommended** | The gap's own idea. It says what the object is, a lookup list of workspaces, and collides with nothing in `kody-w/rapp-1`, `kody-w/rapp-work`, `kody-w/RAPP`, `kody-w/RAR` or `kody-w/rapp-workspace` |
| B. "Workspace registry" | Refused | "Registry" is RAPP/1's signed root of trust (§13, Article 5). §7 already says "Its registry"; this proposal replaces that word too |
| C. "Workspace composite" | Refused | RAPP Workspace/1 §12 `workspace-composite` is a different shape: a recursive structure over catalog entries |
| D. "Workspace catalog" | Refused | `rapp-work/1-catalog` and RAPP Workspace/1 catalogs are discovery lists with other shapes |
| E. Rename the canonical organization instead | Refused | The canonical body is pinned, signed-frame vocabulary (`work.organization`, `rapp-work/1-organization`), and "organization" is the right word for the body that answers for the work |
| F. Keep both and qualify in prose | Not enough | Machines read the tokens; see "What the collision costs" |

## Proposed change

### 1. Names

| What | 1.0.0 (kept; keeps verifying) | Proposed (new writes) |
|---|---|---|
| The object | Organization | workspace index |
| Python class | `Organization` | `WorkspaceIndex` (`Organization` stays, deprecated) |
| Identity `kind` in `rappid.json` | `"organization"` | `"workspace-index"` |
| `scaffold` input `kind` and CLI `--kind` | `organization` | `workspace-index` |
| `status` classification and `verify` result `kind` | `organization` | `workspace-index` |
| Descriptor file and schema | `organization.json`, `rapp-work-organization/1` | `workspace-index.json`, `rapp-work-workspace-index/1` |
| Pointer list file and schema | `workspaces.json`, `rapp-work-organization-pointers/1` | `workspaces.json`, `rapp-work-workspace-index-pointers/1` |
| The object's own RAPPID in both records | `organization_rappid` | `workspace_index_rappid` |
| Register plan subject `kind` (Python API) | `organization-register` | `workspace-index-register` |
| Register precondition key; world refusal detail | `organization_identity_sha256`; `organization_world` | `workspace_index_identity_sha256`; `workspace_index_world` |
| Contract refusal code | `REFUSE_ORGANIZATION` | `REFUSE_WORKSPACE_INDEX` |
| Scaffolded `SPEC.md` title | "RAPP Work Organization" | "RAPP Workspace Index" |

Unchanged: `.rapp-work/sdk.json` (schema `rapp-work-sdk/1`; its
`workspace_rappid` keeps naming the folder's own RAPPID, for an index as for
an Organization today), `.rapp-work/managed.json`, the six pointer entry
members (`active`, `mode`, `name`, `path`, `rappid`, `world_id`), and every
plan, receipt, recovery and result envelope schema.

### 2. Normative text for `rapp-work-sdk/1`

**§7, replace lines 92-101 with:**

```markdown
## 7. Workspace and workspace index

A Workspace has one existing or mint-once RAPPID and one hard `world_id`.
Scaffolding creates a new directory atomically. Updating is additive for legacy
workspaces and limited to SDK-owned integration files for SDK workspaces.

A workspace index is a pointer-only routing object for the Workspaces of one
`world_id`. Its pointer list may contain only workspace RAPPID, lexical path,
world, mode, name, and active state. It MUST NOT copy workspace content,
credentials, prompts, histories, or native provider stores. A workspace index
is not a `rapp-work/1` organization: it has no owner, policy, release scope,
Hive, or body stream, and it grants no authority.

A workspace index has identity `kind: "workspace-index"`. Its descriptor,
`workspace-index.json`, has schema `rapp-work-workspace-index/1` and exactly the
members `pointer_policy` (`"pointer-only"`), `profile` (`"rapp-work-sdk/1"`),
`schema`, `workspace_index_rappid`, and `world_id`. Its pointer list,
`workspaces.json`, has schema `rapp-work-workspace-index-pointers/1` and exactly
the members `schema`, `workspace_index_rappid`, and `workspaces`.

Organization is this profile's earlier name for the same object. Its records
(`kind: "organization"`, `organization.json` with schema
`rapp-work-organization/1`, and `workspaces.json` with schema
`rapp-work-organization-pointers/1`, both keyed by `organization_rappid`) keep
their exact shape and meaning and MUST continue to verify. An implementation
MUST read each record only under its own kind and schema, MUST NOT read an
Organization record as a workspace index record or the reverse, and MUST refuse
a directory that carries both descriptors. It MUST NOT convert an Organization
in place; a successor is created only by migration (§10). Scaffolding a new
Organization is deprecated.
```

**§10, replace the first paragraph (lines 129-132) with:**

```markdown
A `MigrationPlan` is source-bound and create-only. It preserves the source and
creates a successor integration workspace or workspace index without rewriting
the source identity, Frames, keys, histories, Private Hive state, plugins,
skills, or neurons. The successor of an Organization or of a workspace index is
a workspace index. It carries the source RAPPID and the source's exact pointer
entries, and its `.rapp-work/migration-source.json` names the source.
```

**§12, replace lines 158-161 with:**

```markdown
Unsupported sharing, public Git, credential inheritance, implicit apply,
unknown JSON members, parent-authority changes, plugin execution, neuron
execution, source deletion, owner rotation, in-place Organization conversion, a
directory carrying both an Organization and a workspace index descriptor, and
unverified Hive rollback/fork acceptance are explicit refusals.
```

Step 1 lands the §7 text without its last sentence, and the §12 text. Step 2
adds the sentence "Scaffolding a new Organization is deprecated." Step 3
lands the §10 text.

### 3. Implementation surfaces (later steps, not this branch)

Every row of the inventory above except the canonical body and the plain
English uses: `workspace.py`, `api.py`, `migration.py` (add
`workspace-index.json` to the bound source authority paths), `cli.py`,
`__init__.py`, `README.md`, `docs/API.md`, `docs/ARCHITECTURE.md`,
`docs/MIGRATION.md`, the tests, `protocols/index.json`,
`src/rapp_work/data/profiles.json` and `RELEASE-INVENTORY.json`. The legacy
workspace-manager skill and its fixtures stay as they are.

### 4. This branch

This document; a `CHANGELOG.md` note under "Unreleased (proposal, not
accepted)"; and `RELEASE-INVENTORY.json`, regenerated with
`python3 tools/release_inventory.py --write`, because `MANIFEST.in` ships
`docs/`.

## Shared naming table

This section is identical in RAPP proposal 0010 (`kody-w/RAPP`, gap G22) and
RAPP Work proposal 0011 (`kody-w/rapp-work`, gap G11). One name means one
thing. Where a word must keep two meanings, the prose qualifies it and never
relies on capitalization alone (RAPP `LEXICON.md`, ruling R6).

| Name | What it is | Who decides | On disk and in records | Change |
|---|---|---|---|---|
| **organization** | The accountable body: one owner, one world, one policy, one release scope and exactly one Hive, with a body stream of signed RAPP/1 frames | Canonical `rapp-work/1` §§1–2 (`kody-w/rapp-1`) | `work.organization`, `rapp-work/1-organization`, `organization_rappid` (also the body stream id) | None |
| **workspace index** | A private, pointer-only list of RAPP Workspaces in one `world_id`. Each entry holds a RAPPID, a lexical path, the world, the mode, a name and an active flag, never content | `rapp-work-sdk/1` §7 (`kody-w/rapp-work`) | Proposed: `WorkspaceIndex`, `kind: "workspace-index"`, `workspace-index.json` (`rapp-work-workspace-index/1`), `workspaces.json` (`rapp-work-workspace-index-pointers/1`), `workspace_index_rappid` | Proposal 0011. The SDK calls this object "Organization" today (`kind: "organization"`, `organization.json` with `rapp-work-organization/1`, `workspaces.json` with `rapp-work-organization-pointers/1`, `organization_rappid`). Those records keep verifying |
| **RAPP Workspace** | A private, local-first workspace under RAPP Workspace/1: one RAPPID and one hard `world_id`. The RAPP Work SDK changes it only through exact plans | RAPP Workspace/1 (`kody-w/rapp-workspace`); its SDK integration is `rapp-work-sdk/1` §7 | `rapp-workspace/1`; the SDK's `Workspace`, `kind: "workspace"` and `.rapp-work/` records | None. The proper noun means this and nothing else |
| **workspace composite** | RAPP Workspace/1's routing-only pointer structure over catalog entries and child composites | RAPP Workspace/1 §12 | `workspace-composite` | None. It is not a workspace index |
| **agents workspace** | The Brainstem's `agents/` folder, where a person adds, groups, loads and unloads agents. Only its top-level `*_agent.py` files are live (the grail's flat loader; RAPP proposal 0001) | RAPP Constitution Article XVII (its "User's Workspace"). RAR's Constitution Article XVI already says "agents workspace" | `agents/` | Proposal 0010. No token |
| **Brainstem data** | What the running Brainstem writes as it serves you: memory, state and sessions | RAPP Constitution Article XVI (its "brainstem's workspace") | `.brainstem_data/` and the Brainstem's own state folder | Proposal 0010. No token |
| **host workspace** | The editor's own word for the folders one window has open | Code - OSS, not RAPP | a `.code-workspace` file | Not a RAPP name. A window that shows `agents/` with Brainstem data beside it shows the agents workspace |

Words already taken, so not used for these objects: "agentspace" (RAPP
Article LVI, the public commons), "workbench" (RAPP Article XLIX, a twin's
working area, and the editor's name for its whole window), "registry" (the
signed RAPP/1 §13 root of trust), "catalog" (`rapp-work/1-catalog` and
RAPP Workspace/1 catalogs) and "Brainstem workspace" (RAPP's vault glossary
uses it for Brainstem data). Plain-English "organize" and "organization", as
in "every folder is organization" (RAPP proposal 0001) or RAPP Workspace/1's
"organization tree", name an activity, not an object, and stay as they are.

One more record uses "organization" in the pointer-only sense: the discovery
document of the sidecar profile in `kody-w/rapp-workspace`
(`protocols/rapp-work-sdk/1`, field `organization_pointers`, which point at
`workspace-composite` addresses). Both proposals list it as a follow-up for
that repository.

## Token and compatibility analysis

- **New tokens.** `rapp-work-workspace-index/1`,
  `rapp-work-workspace-index-pointers/1`, the identity kind value
  `workspace-index`, the key `workspace_index_rappid`, the register subject
  kind `workspace-index-register` (inside the open `subject` of
  `rapp-work-release-plan/1`), and the refusal code `REFUSE_WORKSPACE_INDEX`.
- **Never widened or reshaped.** `rapp-work-organization/1`,
  `rapp-work-organization-pointers/1`, the `rapp-work-sdk/1` integration
  record, `rapp-work-managed-files/1`, `rapp-work-release-plan/1`, the
  migration plan, source, pointer, recovery and receipt schemas,
  `rapp-work-result/1`, `rapp-work-static-api/1` (it lists input names, not
  kind values), canonical `rapp-work/1`, and every RAPP/1 form.
- **RAPP/1 Article 2 (one label, one shape).** No existing record changes its
  key set, field grammar or hash rule, and every 1.0.0 record keeps its exact
  bytes and meaning. The one grammar that grows is the SDK's identity `kind`
  vocabulary under `workspace_spec: "rapp-work-sdk/1"`, which gains
  `workspace-index`. This proposal reads that as growth by registration
  (Article 4): a new kind value whose shape-bearing records carry their own
  new tokens, which older readers refuse or reduce to identity only (the
  probe above), exactly as a new registered frame kind does not move
  `rapp/1`. The stricter reading counts the closed kind set as part of the
  profile's grammar and moves the profile to `rapp-work-sdk/2`; that would
  relabel every SDK record, so this proposal recommends the first reading and
  leaves the choice to the owner.
- **Article 3 (no legacy).** The way out is forward: new writes use the new
  form, and a create-only migration converts. Old records are immutable
  artifacts; the SDK never rewrites or deletes them (source deletion is a
  §12 refusal). Retiring the old write path is a later owner decision
  (step 5).
- **Articles 6 and 7 (owner in time; identity is minted).** A workspace index
  grants no authority. Old records are read under the rules they were
  written under. No RAPPID changes: a converted index carries the minted
  source RAPPID, which RAPP/1 §6.2 requires an implementation to reuse on
  read, and nothing derives a RAPPID from a name.
- **Articles 4, 10 and 18.** No new envelope, operation, input or door; the
  six-operation JSON API keeps its closed inputs, and `scaffold` only accepts
  one more `kind` value. All records use the one pinned canonicalizer. The
  frozen wire does not change.
- **Article 8.** No check is muted. The mutations above are findings, and
  step 1 adds the vectors that catch them.
- **Forward compatibility.** Shown by the probe: an older SDK reduces a
  workspace index to its identity and refuses to change it.
- **Backward compatibility.** A newer SDK verifies every 1.0.0 Organization
  unchanged (vectors P1 and P2).

## Security and privacy analysis

- **Authority confusion goes away.** Today a local, unsigned, pointer-only
  folder shares its key name, its kind word and its `status` word with the
  accountable body that signs `work.*` frames. After activation (G16), a
  person or an AI could take a pointer folder for the organization that
  answers for the work, or treat the organization's RAPPID as a local folder
  pointer. Distinct names remove both mistakes.
- **No new data.** A workspace index holds the same six pointer members as an
  Organization, never content, credentials, prompts or histories. The
  lexical paths it holds are private (GODD) as before: mode 0600 files in
  mode 0700 directories on POSIX, written only through descriptor-relative,
  no-follow operations, never published.
- **Fail-closed both ways.** Older readers reduce an index to its identity
  and refuse to change it. Newer readers refuse a directory that carries both
  descriptors, so one folder cannot be read two ways.
- **Explicit conversion only.** Conversion is a reviewed migration plan
  applied with its exact SHA-256; the source is preserved byte for byte.
- **No network, no credentials, no execution.** Nothing here changes the
  offline, no-credential or inert-discovery defaults.

## Migration

One step per change, additive first: read both, then write new. Each step is
a pull request to `main` through this repository's front door
(`CONTRIBUTING.md`), with positive and refusal vectors and mutation proofs.
This workstream opens none of them.

0. **This proposal (docs only).** The owner accepts or refuses it.
1. **Pin the old bytes, then read both (rapp-work 1.1.0).**
   - 1a. A test-only change: vector P1, exact-byte 1.0.0 Organization
     fixtures. It must turn red under Mutation A.
   - 1b. The reader: `WorkspaceIndex` with `pointers()` and `verify()`;
     `load_identity`, `status`, `verify`, `update` and migration sources
     recognize `kind: "workspace-index"`; strict dispatch and the ambiguity
     refusal; the §7 text without its last sentence, and the §12 text;
     re-pin `protocols/index.json` and `src/rapp_work/data/profiles.json`;
     regenerate `RELEASE-INVENTORY.json`. Nothing writes the new form yet.
2. **Write new (rapp-work 1.2.0).** `scaffold` accepts
   `kind: "workspace-index"`; `WorkspaceIndex.plan_scaffold`,
   `plan_register` and `apply_register`; the CLI choice; the docs; the §7
   deprecation sentence. `Organization.plan_scaffold` warns with a
   `DeprecationWarning`, and `scaffold` with `kind: "organization"` still
   writes the exact 1.0.0 bytes (vector P7), so existing scripts keep
   working.
3. **Convert through migration (rapp-work 1.2.0, its own pull request).**
   `migrate` from an Organization plans a workspace index successor. `update`
   never converts. The §10 text lands. For an existing on-disk Organization:
   1. `rapp-work migrate --source <organization> --target <successor>`
      returns a plan and changes nothing. The plan binds the source identity
      and its authority bytes (`rappid.json`, `organization.json`,
      `workspaces.json` and `.rapp-work/`), and lists every successor byte:
      `rappid.json` with `kind: "workspace-index"` and the source RAPPID,
      `workspace-index.json`, `workspaces.json` with the new pointer token
      and the exact pointer entries, the integration files,
      `.rapp-work/migration-source.json` and `.rapp-work/managed.json`.
   2. The owner reviews the plan and its `plan_sha256`.
   3. Apply with `--apply --plan <file> --plan-sha256 <hash>`. The SDK replays
      every precondition, stages beside the target, verifies the staged
      bytes, activates without replacement and writes the receipt.
   4. The source stays byte for byte. The person switches to the successor,
      and retires the source separately if they wish.
   5. A replay against the completed target, with the same SDK version, is
      read-only and returns unchanged.
4. **Deprecation window: the rest of `rapp-work-sdk/1`.** Old records verify;
   an old Organization can still register workspaces, and its pointer list
   keeps `rapp-work-organization-pointers/1`; scaffolding an Organization
   works and is documented as deprecated.
5. **Retirement (the owner's decision, not before `rapp-work-sdk/2`).**
   `scaffold` refuses `kind: "organization"`. Reading and verifying old
   records stays; they are never rewritten or deleted.

Follow-ups outside this repository, each through its own front door:

- **`kody-w/rapp-workspace`:** its sidecar's `organization_pointers`, under a
  new discovery schema token, after the label decision (RAPP proposal 0010,
  step 6).
- **The organism** (branch `experimental/rapp-work-constitution`, by its
  maintainer): G11 becomes proposed, and the glossary can name the workspace
  index.
- **Canonical `rapp-work/1` (`kody-w/rapp-1`):** no change.

## Rollback

- **Step 0:** delete the branch, or revert the documentation commit.
- **Step 1:** revert the reader. Nothing in the new form exists yet, so
  nothing is stranded.
- **Steps 2 and 3:** new-form records may exist by then. Going back to 1.1.0
  keeps them readable, because the reader shipped first. Going back to 1.0.0
  reduces them to their identity and refuses to change them, which fails
  closed and loses nothing. Every conversion kept its source Organization,
  so a person can return to the source; a successor is a separate folder
  they may discard. No old record is ever rewritten or deleted.

## Conformance and test vectors

This branch adds no test. Vectors for the implementation steps:

| Id | Kind | Vector | Expected |
|---|---|---|---|
| P1 | positive | Exact-byte 1.0.0 Organization fixture (`rappid.json`, `organization.json`, `workspaces.json` with two pointers, `.rapp-work/`) | `verify` ok with `kind: "organization"`; SHA-256 of every record pinned in the test; red under Mutation A |
| P2 | positive | `status` and `update` on P1 | `classification: "organization"`; `update` keeps `kind: "organization"` and touches only SDK-owned files |
| P3 | positive | `scaffold` with `kind: "workspace-index"` | exact file set and bytes; `verify` ok; `status` says `workspace-index` |
| P4 | positive | Register a same-world Workspace in an index | one pointer with exactly the six members; key `workspace_index_rappid` |
| P5 | positive | Migrate P1 | the planned bytes above; source inode, modification time and SHA-256 unchanged; successor verifies; replay unchanged |
| P6 | positive | Migrate an index | a workspace index successor with the same pointers |
| P7 | positive | `scaffold` with `kind: "organization"` during the window | exact 1.0.0 bytes |
| R1 | refusal | Index identity with `organization.json` beside it | refused, no read under either shape |
| R2 | refusal | Organization identity with `workspace-index.json` beside it | refused |
| R3 | refusal | Index `workspaces.json` carrying `rapp-work-organization-pointers/1`, and the reverse | `REFUSE_WORKSPACE_INDEX`; `REFUSE_ORGANIZATION` |
| R4 | refusal | `workspace-index.json` with an extra member, a missing member, `organization_rappid`, a foreign RAPPID or a `pointer_policy` other than `pointer-only` | `REFUSE_WORKSPACE_INDEX` |
| R5 | refusal | Registration across `world_id` | `REFUSE_WORLD_BOUNDARY`, as today |
| R6 | refusal | Migration plan whose successor bytes were swapped for the Organization form | `REFUSE_MIGRATION_PLAN` |
| R7 | refusal | Update plan that changes `kind` | `REFUSE_PLAN` |
| R8 | refusal | Unknown scaffold kind | `REFUSE_KIND`, as today |

Mutation proofs for those steps: Mutation A turns P1 red; removing the
ambiguity check turns R1 and R2 red; accepting the old pointer token for an
index turns R3 red; writing `organization.json` for a converted successor
turns P5 red.

Checks run on this branch, which has no code change: the full local mirror
of the CI job on Python 3.13 and 3.10 (`tools/check.py`, `pytest`, `ruff`,
`mypy`, `tools/release_inventory.py --check`, the build and
`tools/verify_package.py`), 169 tests passing on each.

## Reference implementation

None on this branch; the gap is an idea, so this is the proposal only. When
implemented, it is gated this way: the new kind is recognized only for an
identity that says `kind: "workspace-index"`; every other path stays
byte-for-byte as in 1.0.0 (P1, P2 and P7); nothing writes the new form before
step 2; a new index is created only by an explicit `kind`; conversion happens
only through an explicit, reviewed, hash-applied `migrate`; and every refusal
stays fail-closed. No step lands before the owner accepts the matching text.

## Open questions for the owner (decisions)

1. **The name and tokens** in "Names" above.
2. **Article 2 reading.** Growth by registration within `rapp-work-sdk/1`
   (recommended), or a new profile token `rapp-work-sdk/2`?
3. **Releases.** Read in 1.1.0 and write in 1.2.0 (recommended), or both in
   one release?
4. **Conversion.** Should `migrate` turn an Organization into a workspace
   index (recommended), or keep migrating Organizations as Organizations
   until retirement?
5. **The RAPPID on conversion.** Carry the source RAPPID, as §10 migration
   does today (recommended), or mint a fresh one, as canonical `rapp-work/1`
   §6 requires of its own migrations?
6. **The window.** All of `rapp-work-sdk/1` (recommended), or a date?
7. **`workspaces.json`.** Keep the file name (recommended), or rename it too?
8. **`Workspace.verify` and the SDK version.** Fix it first, under its own
   proposal (recommended), so a release that carries step 1 does not refuse
   every 1.0.0 Workspace?
9. **The `rapp-work-sdk/1` label.** Which document owns it: this
   repository's or `kody-w/rapp-workspace`'s sidecar profile?
10. **Unknown kinds.** Should step 1 make `status` name an unknown kind
    instead of calling it `legacy-workspace`?

## Owner actions needed

- Accept or refuse this proposal, and answer the questions above.
- If accepted: land steps 1 to 3 as separate pull requests, and choose the
  release versions.
- Decide which document owns the `rapp-work-sdk/1` label.
- Have the organism's maintainer record G11 as proposed.
- No re-signature is needed: the signed registry does not pin
  `rapp-work-sdk/1`.

## References

- This repository: `protocols/rapp-work-sdk/1/SPEC.md` §§2, 7, 10, 11 and 12;
  `protocols/index.json`; `src/rapp_work/data/profiles.json`;
  `RAPP_WORK_PIN.json`; `src/rapp_work/workspace.py`, `api.py`,
  `migration.py` and `cli.py`; `docs/API.md`, `docs/ARCHITECTURE.md` and
  `docs/MIGRATION.md`; `tests/test_sdk_workspace.py` and
  `tests/test_sdk_migration.py`; `.github/skills/rapp-workspace-manager/`;
  `CONTRIBUTING.md`; `docs/RELEASE.md`.
- Canonical `rapp-work/1`: [`kody-w/rapp-1`](https://github.com/kody-w/rapp-1)
  `protocols/rapp-work/1/SPEC.md` §§1, 2 and 6, `schema.json` and
  `rapp_work.py`.
- RAPP/1 Protocol Constitution: `kody-w/rapp-1` `CONSTITUTION.md` Articles 2,
  3, 4, 6, 7, 8, 10 and 18; RAPP/1 `SPEC.md` §6.2.
- RAPP proposal 0010, "The agents workspace is not a RAPP Workspace", on
  `kody-w/RAPP` branch `experimental/gap-g22-workspace-names`; RAPP
  `LEXICON.md`, ruling R6.
- RAPP Workspace/1: [`kody-w/rapp-workspace`](https://github.com/kody-w/rapp-workspace)
  `protocols/rapp-workspace/1/SPEC.md` §12 and the sidecar profile
  `protocols/rapp-work-sdk/1`.
- The organism: [`organism/`](https://github.com/kody-w/rapp-work/tree/experimental/rapp-work-constitution/organism)
  on branch `experimental/rapp-work-constitution`: gaps G11, G16 and G22, the
  Organization layer and the Workspaces part.
