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
read both forms), **1.2.0** (steps 2 and 3: write the new form, convert
through migration) and, under decision D1's recommended answer, **1.3.0**
(step 5: stop writing the old form), followed by a read sunset the owner
names (step 7).

**Revision 2.** An independent review of the first draft (round 1: one high,
three medium and seven low findings) found, above all, that the draft's
claim that old records are never rewritten is false and that its plan could
never finish the total migration RAPP/1 Article 3 requires. This revision
corrects that, adds decision D1, and answers every other finding; see
"Review round 1 disposition".

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
  the refusal list of §12 (lines 158-161). §2 (lines 42-43) already requires
  the apply-time kind check of step 1b: "Unknown operation inputs and
  unsupported capabilities MUST be refused before effects."
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

### A third meaning: RAPP Workspace/1's organization tree

`kody-w/rapp-workspace` at `52d4f19` uses "organization" for an object of
its own. `protocols/rapp-workspace/1/SPEC.md` §12: "An organization tree is a
candidate lens output, not authority" (line 401). The controller accepts it
as 1 to 32 content-addressed tiles, which "avoids one giant organization
payload" (line 403), and assesses it in a `rapp-workspace/1/organization-assessment`
record (`schemas/organization-assessment.schema.json`). "A verified
organization MAY be wrapped into a `workspace-composite`" (line 420). It is
neither the accountable body nor this SDK's pointer-only object; the shared
naming table gives it its own row.

### Every place the pointer-only Organization appears

| Surface | Where | Today |
|---|---|---|
| Normative profile | `protocols/rapp-work-sdk/1/SPEC.md` §7 (lines 92-101), §10 (lines 129-132) | "Workspace and Organization"; "Its registry may contain only…"; "a successor integration workspace or Organization" |
| Kinds | `src/rapp_work/workspace.py` line 35 | `WORKSPACE_KINDS = {"workspace", "organization"}` |
| Scaffolded `SPEC.md` | `workspace.py` line 66 | title "RAPP Work Organization" |
| Records | `workspace.py` lines 136-154 (`_organization_files`) | `organization.json` (`rapp-work-organization/1`: `organization_rappid`, `pointer_policy`, `profile`, `schema`, `world_id`) and `workspaces.json` (`rapp-work-organization-pointers/1`: `organization_rappid`, `schema`, `workspaces`) |
| Identity and scaffold | `workspace.py` lines 169-278 and 352-375 | `Literal["workspace", "organization"]`; `kind` in `rappid.json`, copied into the scaffold plan subject and the scaffold result (line 344); dispatch to `_organization_files` |
| Update | `workspace.py` lines 433-439, 675-678, 692-721 and 730 | "only workspaces and pointer-only organizations can adopt the SDK profile"; `apply_update` replaces SDK-owned files in place, among them `.rapp-work/sdk.json` and `.rapp-work/managed.json` (line 708) |
| Model | `workspace.py` lines 805-1010 (`class Organization`) | `pointers()`; `plan_register` (subject `kind: "organization-register"` with key `organization_rappid`, lines 932-933; precondition `organization_identity_sha256`, line 947; refusal detail `organization_world`, line 901); `apply_register`, which replaces `workspaces.json` in place (lines 970-974) and returns key `organization_rappid` (line 976); `verify` (result `kind: "organization"`); refusal code `REFUSE_ORGANIZATION` |
| JSON API | `src/rapp_work/api.py` lines 22-30, 85, 151-152 and 162 | `status` reports `classification: "organization"` (`str(identity["kind"])`); `verify` dispatches on the kind |
| Migration | `src/rapp_work/migration.py` lines 26, 29-40, 52-57, 121-130 and 321-336 | `organization.json` and `workspaces.json` are bound source authority; the source binding `rapp-work-migration-source/1` copies the source `kind` (line 123); an Organization migrates to an Organization |
| CLI | `src/rapp_work/cli.py` line 36 | `--kind` choices `workspace`, `organization` |
| Public API | `src/rapp_work/__init__.py` lines 37 and 58; `tests/test_public_contract.py` line 30 | `Organization` in `__all__` |
| Docs | `README.md` line 117; `docs/API.md` line 50; `docs/ARCHITECTURE.md` line 48; `docs/MIGRATION.md` line 20; `CHANGELOG.md` lines 16-17 (the 1.0.0 entry, history) | "pointer-only Organization" |
| Tests | `tests/test_sdk_workspace.py` lines 12, 25-33 and 310-349; `tests/test_sdk_migration.py` lines 35-55 and 222-229 | scaffold, register, world boundary, migrate |
| Legacy skill | `.github/skills/rapp-workspace-manager/` | the ancestor above; frozen, fixtures preserved |
| Canonical body | `kody-w/rapp-1` `protocols/rapp-work/1/SPEC.md` §§1-2 and `schema.json` `$defs.organization`; mirrors `src/rapp_work/data/rapp-work-1-SPEC.md` and `rapp-work-1-schema.json` | the accountable body; not the SDK's object |
| Another repository | `kody-w/rapp-workspace` at `52d4f19`: `protocols/rapp-work-sdk/1/SPEC.md` §5 (lines 119 and 127); `schemas/discovery.schema.json` (`organization_pointers`, and the `organization_pointer` definition that `install`, `profile` and `update` schemas repeat); `reference/scaffold.py`, `reference/conformance.py`, `reference/schema_source.py` and `reference/README.md` line 31; `docs/rapp-work.md` line 32; `.github/skills/rapp-work-sdk/SKILL.md` line 18 and the vendored copy of the profile under that skill; `tests/test_rapp_work_sdk.py` line 74; and the prior-release fixture `fixtures/prior-release/.rapp-work/generations/4b4fc213…/discovery.json`, whose bytes the profile's `manifest.json` pins | `organization_pointers`: routing-only pointers to `workspace-composite` addresses, which may wrap a verified organization tree (above). A follow-up must keep the pinned fixture verifying |
| Plain English, not the object | `.github/skills/autonomous-rapp-estate-manager/SKILL.md` lines 17, 43, 221 and 244; `.github/skills/rapp-workspace/SKILL.md` line 3; `.github/skills/rapp-private-hive/DEPLOYMENT.md` line 329 | "organize", "organization metadata", "organization-policy" |

### What the collision costs

- **One key, two meanings.** `organization_rappid` is the accountable body's
  RAPPID and body stream id in signed `work.organization` payloads, and a
  local, unsigned pointer folder's RAPPID in `organization.json`,
  `workspaces.json`, the register plan subject and the register result.
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

### 1.0.0 Organizations are rewritten in place

The first draft of this proposal said that old records are immutable and
never rewritten. That is false. An Organization is a local folder that the
SDK changes in place:

- **Every registration rewrites `workspaces.json`.**
  `Organization.apply_register` replaces it with `replace_owned`
  (`workspace.py`, lines 970-974), after `plan_register` has rebuilt the
  whole pointer list (lines 895-951).
- **An update rewrites the integration records.** `apply_update` replaces
  SDK-owned files in place (lines 692-721). Both `.rapp-work/sdk.json` and
  `.rapp-work/managed.json` record `sdk_version` (lines 83 and 101), so a
  newer SDK's update plan for a 1.0.0 Organization replaces both.

An Organization folder is neither published nor content-addressed. It is the
estate's own, mutable artifact, which matters for RAPP/1 Article 3 (Token
analysis).

### The scaffold apply path does not check the kind (pre-existing)

Only planning checks the kind: `plan_scaffold` refuses an unsupported kind
(`workspace.py`, line 211). `_validate_scaffold_plan` (lines 244-278)
rebuilds the expected plan from the plan's own subject and never checks it,
and `apply_scaffold` activates the target (line 335) before it reads the
identity back (lines 340-341). A scratch probe on this branch's SDK 1.0.0
(Python 3.13) applied hand-built scaffold plans, each with its exact
SHA-256:

| Subject `kind` | Apply result | Afterwards |
|---|---|---|
| `workspace-index` | refused, `REFUSE_IDENTITY` | the target exists, with that kind in `rappid.json` and the SDK files |
| `protocol-estate` | applied | `status` reports `classification: "protocol-estate"` |
| an unknown value | refused, `REFUSE_IDENTITY` | the target exists, with that kind |

This contradicts `rapp-work-sdk/1` §2 ("unsupported capabilities MUST be
refused before effects"). It is pre-existing behavior of `main`, reported
separately as a drift finding, and this proposal-only branch does not change
`main`'s code. It matters here because step 1b teaches `load_identity` the
new kind: without a check before any effect, the same crafted plan would
then succeed on 1.1.0 and write a workspace index identity with no
descriptor. Step 1b therefore adds the check, and vector R9 pins it.

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
  `.rapp-work/sdk.json` records `sdk_version` and must match exactly
  (`workspace.py`, lines 785-793). A 1.0.0 Organization still verifies,
  because its `verify` does not read `sdk.json`.
- **A completed-migration replay is bound to the SDK version.** The
  successor's `sdk.json` and `managed.json` record `sdk_version`, and apply
  recomputes the plan, so a later SDK cannot replay a 1.0.0 migration as
  unchanged.

### One label, two documents (a finding, not fixed here)

`kody-w/rapp-workspace` ships its own `protocols/rapp-work-sdk/1/SPEC.md`, a
different document under the same label: "RAPP Work SDK/1", a sidecar
profile (8179 bytes, SHA-256 `4d404a1a…`), where this repository's is
6614 bytes (`cf64a90f…`). Its discovery document names routing-only
references `organization_pointers`. The LTS lock pins "`rapp-work-sdk/1`"
without saying which. This proposal names only this repository's §7; the
other document's field is a follow-up once the owner decides which document
owns the label.

## Options

| Option | Verdict | Why |
|---|---|---|
| **A. "Workspace index"** | **Recommended** | The gap's own idea. It says what the object is, a lookup list of workspaces. No exact use of the phrase exists in `kody-w/rapp-1`, `kody-w/rapp-work`, `kody-w/RAPP`, `kody-w/RAR` or `kody-w/rapp-workspace`. The nearest term is RAPP Workspace/1 §12's "external indexes" (line 414): bounded indexes of file and path metadata inside a scan boundary, which is the opposite of pointer-only. The §7 text below says that a workspace index is not an index of any workspace's files |
| B. "Workspace registry" | Refused | "Registry" is RAPP/1's signed root of trust (§13, Article 5). §7 already says "Its registry"; this proposal replaces that word too |
| C. "Workspace composite" | Refused | RAPP Workspace/1 §12 `workspace-composite` is a different shape: a recursive structure over catalog entries |
| D. "Workspace catalog" | Refused | `rapp-work/1-catalog` and RAPP Workspace/1 catalogs are discovery lists with other shapes |
| E. Rename the canonical organization instead | Refused | The canonical body is pinned, signed-frame vocabulary (`work.organization`, `rapp-work/1-organization`), and "organization" is the right word for the body that answers for the work |
| F. Keep both and qualify in prose | Not enough | Machines read the tokens; see "What the collision costs" |
| G. "Workspace pointer list" | Fallback | Consistent with existing uses: the legacy manager lists "registered workspace pointers", and RAPP Workspace/1's skill wraps "workspace pointers" into composites. Longer, and it names the entries rather than the object. Offered in open question 2 if the owner finds "index" too close to "external indexes" |

## Proposed change

### 1. Names

| What | 1.0.0 (kept through the migration window) | Proposed (new writes) |
|---|---|---|
| The object | Organization | workspace index |
| Python class | `Organization` | `WorkspaceIndex` (`Organization` stays, deprecated) |
| Identity `kind` in `rappid.json` (also copied into the scaffold and update plan subjects, the scaffold result and `rapp-work-migration-source/1`) | `"organization"` | `"workspace-index"` |
| `scaffold` input `kind` and CLI `--kind` | `organization` | `workspace-index` |
| `status` classification and `verify` result `kind` | `organization` | `workspace-index` |
| Descriptor file and schema | `organization.json`, `rapp-work-organization/1` | `workspace-index.json`, `rapp-work-workspace-index/1` |
| Pointer list file and schema | `workspaces.json`, `rapp-work-organization-pointers/1` | `workspaces.json`, `rapp-work-workspace-index-pointers/1` |
| The object's own RAPPID in both records | `organization_rappid` | `workspace_index_rappid` |
| Register plan subject `kind` (Python API) | `organization-register` | `workspace-index-register` |
| Register plan subject key and `apply_register` result key | `organization_rappid` (lines 933 and 976) | `workspace_index_rappid` |
| Register precondition key; world refusal detail | `organization_identity_sha256`; `organization_world` | `workspace_index_identity_sha256`; `workspace_index_world` |
| Contract refusal code | `REFUSE_ORGANIZATION` | `REFUSE_WORKSPACE_INDEX` |
| Scaffolded `SPEC.md` title | "RAPP Work Organization" | "RAPP Workspace Index" |

Unchanged: `.rapp-work/sdk.json` (schema `rapp-work-sdk/1`; its
`workspace_rappid` keeps naming the folder's own RAPPID, for an index as for
an Organization today), `.rapp-work/managed.json`, the six pointer entry
members (`active`, `mode`, `name`, `path`, `rappid`, `world_id`), and every
plan, receipt, recovery and result envelope schema.

### 2. Normative text for `rapp-work-sdk/1`

Each change is written to compose with the sibling drafts that touch the
same sections (see "Related proposals"): §7 keeps its Workspace paragraph
byte-identical, §10 changes one paragraph that no sibling touches, and §12
gains a paragraph instead of a replacement.

**§7, retitle the heading (line 92) to:**

```markdown
## 7. Workspace and workspace index
```

**§7, keep the Workspace paragraph (lines 94-96) byte-identical, and replace
the Organization paragraph (lines 98-101) with:**

```markdown
A workspace index is a pointer-only routing object for the Workspaces of one
`world_id`. Its pointer list may contain only workspace RAPPID, lexical path,
world, mode, name, and active state. It MUST NOT copy workspace content,
credentials, prompts, histories, or native provider stores. It lists
Workspaces; it is not an index of any Workspace's files. A workspace index is
not a `rapp-work/1` organization: it has no owner, policy, release scope, Hive,
or body stream, and it grants no authority.

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
their exact shape and meaning, and an Organization that an earlier
implementation of this profile verifies MUST continue to verify unless its root
also holds a workspace index descriptor. An implementation MUST read each record only under
its own identity kind and schema, and MUST NOT read an Organization record as a
workspace index record or the reverse.

A descriptor is known by its content, not by its file name. A root
`organization.json` is an Organization descriptor only when it is a JSON object
whose `schema` is `rapp-work-organization/1`, and a root `workspace-index.json`
is a workspace index descriptor only when it is a JSON object whose `schema` is
`rapp-work-workspace-index/1`. `verify`, `update`, `migrate`, and pointer
registration MUST refuse a root that holds both descriptors, whatever its
identity kind, and `status` MUST NOT classify it as either. Otherwise a file
that bears the other kind's descriptor name is ordinary content. An
implementation MUST NOT convert an Organization in place; a workspace index
successor is created only by migration (§10).
```

**§10, replace the first paragraph (lines 129-132), which no sibling draft
changes, with:**

```markdown
A `MigrationPlan` is source-bound and create-only. It preserves the source and
creates a successor integration workspace or workspace index without rewriting
the source identity, Frames, keys, histories, Private Hive state, plugins,
skills, or neurons. The successor of an Organization or of a workspace index is
a workspace index. It carries the source RAPPID and the source's exact pointer
entries, and its `.rapp-work/migration-source.json` names the source. Retiring
the source is a separate act of its owner; migration never deletes it (§12).
```

**§12, keep the existing paragraph (lines 158-161) byte-identical, and
append after it (after any paragraph an accepted sibling appends there):**

```markdown
In-place conversion of an Organization, and a root that holds both an
Organization descriptor and a workspace index descriptor (§7), are also
explicit refusals.
```

Step 1 lands the §7 text and the §12 paragraph. Step 2 appends to §7's last
paragraph the sentence "Scaffolding a new Organization is deprecated." Step 3
lands the §10 text. Steps 5 and 7 land the sunset texts below.

**Step 5 (write sunset).** In §7, replace "Scaffolding a new Organization is
deprecated." with "An implementation MUST refuse to scaffold an Organization
or to register a Workspace in one." In §12, append: "Scaffolding an
Organization, and registering a Workspace in one, are also explicit
refusals."

**Step 7 (read sunset).** In §7, replace "and an Organization that an earlier
implementation of this profile verifies MUST continue to verify unless its root
also holds a workspace index descriptor" with "and an implementation reads an
Organization only as a migration source (§10): `status` reports it as a
retired form, and `verify` and `update` MUST refuse it and name migration".

### 3. Implementation surfaces (later steps, not this branch)

Every row of the inventory above except the canonical body, the other
repository and the plain-English uses: `workspace.py`, `api.py`,
`migration.py` (add `workspace-index.json` to the bound source authority
paths), `cli.py`, `__init__.py`, `README.md`, `docs/API.md`,
`docs/ARCHITECTURE.md`, `docs/MIGRATION.md`, the tests, `protocols/index.json`,
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
| **workspace index** | A private, pointer-only list of RAPP Workspaces in one `world_id`. Each entry holds a RAPPID, a lexical path, the world, the mode, a name and an active flag, never content. It lists workspaces; it is not an index of any workspace's files | `rapp-work-sdk/1` §7 (`kody-w/rapp-work`) | Proposed: `WorkspaceIndex`, `kind: "workspace-index"`, `workspace-index.json` (`rapp-work-workspace-index/1`), `workspaces.json` (`rapp-work-workspace-index-pointers/1`), `workspace_index_rappid` | Proposal 0011. The SDK calls this object "Organization" today (`kind: "organization"`, `organization.json` with `rapp-work-organization/1`, `workspaces.json` with `rapp-work-organization-pointers/1`, `organization_rappid`). Those records keep verifying through a migration window whose end the owner sets (proposal 0011, decision D1) |
| **organization tree** | RAPP Workspace/1's candidate grouping of one catalog's entries: a lens output of 1 to 32 content-addressed tiles, assessed against bounds and never authority. A verified one may be wrapped into a workspace composite | RAPP Workspace/1 §12 (`kody-w/rapp-workspace`) | its tiles; `rapp-workspace/1/organization-assessment` records | None. It is neither the accountable organization nor a workspace index |
| **RAPP Workspace** | A private, local-first workspace under RAPP Workspace/1: one RAPPID and one hard `world_id`. The RAPP Work SDK changes it only through exact plans | RAPP Workspace/1 (`kody-w/rapp-workspace`); its SDK integration is `rapp-work-sdk/1` §7 (`kody-w/rapp-work`) | `rapp-workspace/1`; the SDK's `Workspace`: `rappid.json` with `"kind": "workspace"` and `"workspace_spec": "rapp-work-sdk/1"`, and `.rapp-work/` records | None. The proper noun means this and nothing else, in any letter case |
| **workspace composite** | RAPP Workspace/1's routing-only pointer structure over catalog entries and child composites | RAPP Workspace/1 §12 | `workspace-composite` | None. It is not a workspace index |
| **workspace gate** | A planted RAPP door of the door-bearing kind `workspace`, door type `gate`: members pick up work items through labeled Issues, in the private-workspace or public-workspace pattern | RAPP Constitution Article XLVI.2 (`kody-w/RAPP`) and its `tools/door_address.py` | `rappid.json` with `"schema": "rapp/1"` and `"kind": "workspace"`, beside `neighborhood.json` and `members.json` | Proposal 0010 names it in prose. No token. Its `kind` value is the same string as the SDK's; see the named collisions below |
| **Brainstem agents folder** | A Brainstem's `agents/` folder (its `AGENTS_PATH`), where a person adds, groups, loads and unloads agents. Only its top-level `*_agent.py` files are live (the grail's flat loader; RAPP proposal 0001) | RAPP Constitution Article XVII (its "User's Workspace") | `agents/` | Proposal 0010. No token. RAPP, RAR, the installer and the Brainstem app already call it the agents folder |
| **Brainstem data** | What the running Brainstem writes as it serves you: memory, state and sessions | RAPP Constitution Article XVI (its "brainstem's workspace") | `.brainstem_data/` and the Brainstem's own state folder | Proposal 0010. No token |
| **host workspace** | The editor's own word for the folders one window has open | Code - OSS, not RAPP | a `.code-workspace` file | Not a RAPP name. A window that shows `agents/` with Brainstem data beside it shows the Brainstem agents folder |

Named collisions (R6: both meanings stay, and prose qualifies them):

- **`kind: "workspace"` in a `rapp/1` `rappid.json`.** RAPP's door tooling
  reads the value as a workspace gate and resolves the record's RAPPID to door
  type `gate` and nine public URLs. The RAPP Work SDK writes the same value,
  with the same `"schema": "rapp/1"`, for a private RAPP Workspace, and adds
  `workspace_spec`. No document says which vocabulary owns a `rappid.json`
  `kind` value. Both proposals leave this to the owner and move no token.
- **"agents workspace".** RAR's Constitution Article XVI uses it for a
  person's local copy of RAR, their card collection and agent workbench. These
  proposals do not use it.
- **"private workspace".** RAPP's door patterns (`private-workspace`,
  `public-workspace`) name workspace gates, while RAPP Workspace/1 calls its
  own workspaces private. Qualify: *private workspace gate*, *RAPP Workspace*.

Words already taken, so not used for these objects: "agentspace" (RAPP
Article LVI, the public commons), "workbench" (RAPP Article XLIX, a twin's
working area; the editor's name for its whole window; RAR's agent
workbench), "registry" (the signed RAPP/1 §13 root of trust), "catalog"
(`rapp-work/1-catalog` and RAPP Workspace/1 catalogs), "Brainstem workspace"
(RAPP's vault glossary uses it for Brainstem data) and "external index"
(RAPP Workspace/1 §12: bounded indexes of file and path metadata inside a
scan boundary; a workspace index holds none). "Agent workspace" differs from
RAR's term by one letter, which fails in speech as capitalization does.

Plain-English "organize" and "organization" name an activity and stay as they
are: the organism's invariant "Every folder is organization" and RAPP proposal
0001's "Every subfolder of `agents/` is organization only" mean that a folder
only groups files. RAPP Workspace/1's organization tree is an object, with its
own row above.

The sidecar profile in `kody-w/rapp-workspace` (`protocols/rapp-work-sdk/1`)
names a discovery field `organization_pointers`: routing-only pointers to
`workspace-composite` addresses, which may wrap a verified organization tree.
Both proposals list it as an optional follow-up for that repository.

## Token and compatibility analysis

- **New tokens.** `rapp-work-workspace-index/1`,
  `rapp-work-workspace-index-pointers/1`, the identity kind value
  `workspace-index`, the key `workspace_index_rappid`, the register subject
  kind `workspace-index-register` (inside the open `subject` of
  `rapp-work-release-plan/1`), and the refusal code `REFUSE_WORKSPACE_INDEX`.
- **Never widened or reshaped.** `rapp-work-organization/1`,
  `rapp-work-organization-pointers/1`, the `rapp-work-sdk/1` integration
  record, `rapp-work-managed-files/1`, `rapp-work-release-plan/1`, the
  migration plan, source pointer (`rapp-work-migration-source-pointer/1`,
  which carries no kind), recovery and receipt schemas,
  `rapp-work-result/1`, `rapp-work-static-api/1` (it lists input names, not
  kind values), canonical `rapp-work/1`, and every RAPP/1 form.
- **Two value sets grow.** The SDK's identity `kind` vocabulary under
  `workspace_spec: "rapp-work-sdk/1"` gains `workspace-index`, and with it the
  plan subjects and results that copy the kind. So does the `kind` member of
  the source binding `rapp-work-migration-source/1` (`migration.py`, lines
  121-130), which copies the source kind (line 123) from a closed set (lines
  53-57): migrating an index (vector P6) writes `kind: "workspace-index"`
  into it. The first draft listed that record as never widened; it is not.
  Neither growth changes a key set or a hash rule.
- **RAPP/1 Article 2 (one label, one shape).** No existing record changes its
  key set or hash rule, and every 1.0.0 record keeps its exact bytes and
  meaning. This proposal reads the two growing value sets as growth by
  registration (Article 4): a new kind value whose shape-bearing records carry
  their own new tokens, which older readers refuse or reduce to identity only
  (the probe above), exactly as a new registered frame kind does not move
  `rapp/1`. The stricter reading counts a closed value set as part of a field
  grammar. It would move the profile to `rapp-work-sdk/2` and the source
  binding to a new token such as `rapp-work-migration-source/2`, and it would
  relabel every SDK record. This proposal recommends the first reading and
  leaves the choice to the owner (open question 3). Sibling drafts that mint
  closed kind sets of their own can add `workspace-index` before they are
  accepted, so that no token moves (Related proposals).
- **Article 3 (no legacy) and RAPP/1 §12.** Article 3 reads: "rapp/1 is a
  **living standard**: revised in place, never forked into parallel versions,
  with **no perpetual backward compatibility.** A change to a canonical form
  is a total migration of every instance plus deletion of the old form. The
  single exception is sealed re-genesis history (SPEC §12.1) — retained
  bit-exact under `legacy/`, never served as current. Published
  content-addressed artifacts are immutable; the way out is always forward."
  A second, narrow exception covers the rev-5 to rev-13 governance anchor
  frames. RAPP/1 `SPEC.md` §12 applies the rule to an estate's own records
  (`vendor/rapp-1/SPEC.md`, lines 656-661): "Within an estate there is **no
  perpetual backward compatibility** for the estate's own artifacts and
  retired legacy encodings (Art. III): a change to such a form is a **total
  migration** of every instance + **deletion** of the old form." An SDK
  Organization is one of the estate's own artifacts. It is neither published
  nor content-addressed, and the SDK rewrites it in place (Context), so the
  immutability sentence does not cover it. Renaming its form therefore calls
  for a total migration: every Organization converted, each source deleted by
  its owner, and the old form removed from the SDK. The first draft claimed
  that old records are immutable and never rewritten, planned to read and
  write both forms for the life of `rapp-work-sdk/1`, and kept the SDK's
  refusal of source deletion, so its migration could never finish.
  **Decision D1** puts the choice to the owner: total migration
  (recommended; Migration steps 4 to 7, with each source retired by its
  owner, as canonical `rapp-work/1` §6 says: "Source retirement is a separate
  owner-authorized operation"), or an explicit exception. Article 3 names its
  exceptions, so an exception for SDK Organizations would itself amend the
  RAPP/1 Protocol Constitution under Article 14. Its only justification would
  be that Organizations are private, local and unsigned, which many other
  estate artifacts also are. This proposal does not recommend it.
- **Articles 6 and 7 (owner in time; identity is minted).** A workspace index
  grants no authority. Old records are read under the rules they were
  written under. No RAPPID changes: a converted index carries the minted
  source RAPPID. It is the same object under its new name, and RAPP/1 §6.2
  allows a new tail for an existing identity only through an owner-authorized
  re-anchor in three enumerated cases, none of which applies. Nothing derives
  a RAPPID from a name. The cost is that two live folders share one RAPPID
  until the owner retires the source (open question 6).
- **Articles 4, 10 and 18.** No new envelope, operation, input or door; the
  six-operation JSON API keeps its closed inputs, and `scaffold` only accepts
  one more `kind` value. All records use the one pinned canonicalizer. The
  frozen wire does not change.
- **Article 8.** No check is muted. The mutations above are findings, and
  step 1 adds the vectors that catch them.
- **Forward compatibility.** Shown by the probe: an older SDK reduces a
  workspace index to its identity and refuses to change it.
- **Backward compatibility.** A newer SDK verifies every 1.0.0 Organization
  unchanged through the migration window (vectors P1, P2 and P8), until the
  read sunset that decision D1 asks the owner to set.
- **RAPP's door kinds.** A workspace index identity's `kind` is not one of
  RAPP's door-bearing kinds, so RAPP's door tooling refuses to resolve it
  (`kody-w/RAPP` `tools/door_address.py` refuses a kind outside
  `VALID_KINDS`), as it refuses an Organization's today. The SDK Workspace's
  `kind: "workspace"` does collide with RAPP's workspace gate kind; the shared
  naming table records that, and open question 12 asks the owner.

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
  and refuse to change it. Newer readers refuse a root that holds both
  descriptors, known by their content, so one folder cannot be read two ways,
  and a stray file that merely bears a descriptor's name changes nothing.
- **No crafted writes.** The apply-time kind check refuses, before any
  effect, a scaffold plan whose kind the running release does not write
  (R9). A hand-built plan can therefore create neither an index identity
  before the release that writes indexes nor an identity of any other kind.
- **One identity in two folders, for a while.** A conversion carries the
  source RAPPID (open question 6). Until the owner retires the source, both
  folders are live under one RAPPID, and a registration into the source makes
  their pointer lists differ. The migration steps bound this: from 1.2.0 a
  registration into an Organization warns, the write sunset refuses it, and
  retirement ends it. No authority rides on either folder, so the risk is
  confusion, not escalation.
- **Explicit conversion only.** Conversion is a reviewed migration plan
  applied with its exact SHA-256; the source is preserved byte for byte until
  its owner retires it.
- **No network, no credentials, no execution.** Nothing here changes the
  offline, no-credential or inert-discovery defaults.

## Migration

One step per change, additive first: read both, write new, convert, then
retire the old form. Each step is a pull request to `main` through this
repository's front door (`CONTRIBUTING.md`), with positive and refusal
vectors and mutation proofs. This workstream opens none of them. Steps 4 to 7
follow decision D1's recommended answer, total migration.

0. **This proposal (docs only).** The owner accepts or refuses it.
1. **Pin the old bytes, then read both (rapp-work 1.1.0).**
   - 1a. A test-only change: vector P1, exact-byte 1.0.0 Organization
     fixtures. It must turn red under Mutation A.
   - 1b. The reader: `WorkspaceIndex` with `pointers()` and `verify()`;
     `load_identity`, `status`, `verify`, `update` and migration sources
     recognize `kind: "workspace-index"`; strict dispatch by identity kind;
     the ambiguity refusal, with descriptors known by content, in
     `load_identity` and in `api.py`'s `status` and `verify` dispatch (R1,
     R2, P8);
     and the apply-time kind check: `apply_scaffold` refuses, before it
     creates a staging directory, a plan whose subject kind the running
     release does not write, which in 1.1.0 is anything but `workspace` and
     `organization` (R9). Also the §7 text and the §12 paragraph; re-pin
     `protocols/index.json` and `src/rapp_work/data/profiles.json`; regenerate
     `RELEASE-INVENTORY.json`. Nothing the SDK plans writes the new form yet,
     and a crafted plan that tries is refused before any effect.
2. **Write new (rapp-work 1.2.0).** `scaffold` accepts
   `kind: "workspace-index"`, and the apply-time kind check admits it;
   `WorkspaceIndex.plan_scaffold`, `plan_register` and `apply_register`; the
   CLI choice; the docs; the §7 deprecation sentence. `Organization.plan_scaffold`
   and `Organization.plan_register` warn with a `DeprecationWarning`.
   `scaffold` with `kind: "organization"` still writes the 1.0.0 file set, and
   every file keeps its 1.0.0 bytes except `.rapp-work/sdk.json` and
   `.rapp-work/managed.json`, which record the running `sdk_version` (vector
   P7), so existing scripts keep working.
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
   4. The source stays byte for byte. From then on the person registers
      Workspaces only in the successor, and the owner retires the source
      (step 6).
   5. A replay against the completed target, with the same SDK version, is
      read-only and returns unchanged.
4. **The migration window (from step 2 to step 5).** Old records verify. An
   Organization can still register Workspaces, and each registration rewrites
   that Organization's own `workspaces.json` in the old form, as 1.0.0 does.
   Scaffolding an Organization works and warns.
5. **Stop writing the old form (the write sunset; recommended rapp-work 1.3.0,
   one release after conversion ships).** `scaffold` refuses
   `kind: "organization"` with `REFUSE_KIND`, and registration into an
   Organization is refused with `REFUSE_ORGANIZATION`, naming migration; the
   step 5 texts land. Organizations still verify, update and migrate.
6. **Retire each converted source (its owner, one Organization at a time).**
   After the successor verifies, and a replay of the conversion returns
   unchanged (step 3.5, which rechecks the source binding), the owner deletes
   the source folder. The SDK never deletes
   it: source deletion stays a §12 refusal, and canonical `rapp-work/1` §6
   likewise keeps source retirement "a separate owner-authorized operation".
   `docs/MIGRATION.md` gains these checks. When every Organization of an
   estate has been converted and retired, that estate's migration is total.
7. **Stop reading the old form (the read sunset; a release the owner names
   and announces in `CHANGELOG.md` at least one release ahead).** `status`
   reports an Organization as a retired form; `verify` and `update` refuse
   it and name migration; `migrate` still accepts it, as a conversion source
   only; the step 7 text lands. That last reader goes at `rapp-work-sdk/2` at
   the latest, and those release notes name the last release that converts
   an Organization. After that the old form is gone from the SDK.

Decision D1's other answer, an explicit exception, would keep steps 4 onward
open for the life of `rapp-work-sdk/1`; the Token analysis explains why it
needs an amendment of the RAPP/1 Protocol Constitution.

Follow-ups outside this repository, each through its own front door:

- **`kody-w/rapp-workspace` (optional):** its sidecar's
  `organization_pointers`, under a new discovery schema token, after the
  label decision (RAPP proposal 0010, step 6). The byte-pinned prior-release
  fixture must keep verifying.
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
  closed and loses nothing. A source Organization that its owner has not
  retired is still there to return to; a successor is a separate folder its
  owner may discard.
- **Steps 5 and 7:** a later release that restores the closed path undoes a
  sunset; nothing on disk changes either way.
- **Step 6:** a retirement is the owner's own deletion, and the SDK cannot
  undo it. The successor holds the source's exact pointer entries, and every
  release from 1.1.0 on reads it.
- The SDK itself deletes no record at any step. During the window,
  registration and update rewrite an Organization's own files in place, as
  they do in 1.0.0.

## Conformance and test vectors

This branch adds no test. Vectors for the implementation steps:

| Id | Kind | Vector | Expected |
|---|---|---|---|
| P1 | positive | Exact-byte 1.0.0 Organization fixture (`rappid.json`, `organization.json`, `workspaces.json` with two pointers, `.rapp-work/`) | `verify` ok with `kind: "organization"`; SHA-256 of every record pinned in the test; red under Mutation A |
| P2 | positive | `status` and `update` on P1 | `classification: "organization"`; `update` keeps `kind: "organization"` and touches only SDK-owned files (a newer SDK's plan replaces `.rapp-work/sdk.json` and `.rapp-work/managed.json` to record its own `sdk_version`) |
| P3 | positive | `scaffold` with `kind: "workspace-index"` | exact file set and bytes; `verify` ok; `status` says `workspace-index` |
| P4 | positive | Register a same-world Workspace in an index | one pointer with exactly the six members; key `workspace_index_rappid` |
| P5 | positive | Migrate P1 | the planned bytes above; source inode, modification time and SHA-256 unchanged; successor verifies; replay unchanged |
| P6 | positive | Migrate an index | a workspace index successor with the same pointers; its `rapp-work-migration-source/1` binding carries `kind: "workspace-index"` |
| P7 | positive | `scaffold` with `kind: "organization"` during the window | the 1.0.0 file set; every file byte-identical to 1.0.0 except `.rapp-work/sdk.json` and `.rapp-work/managed.json`, which differ only by the running `sdk_version` (and, in `managed.json`, the entry for `sdk.json`) |
| P8 | positive | P1 plus a root `workspace-index.json` that is not a descriptor (`{}`, or plain text) | `verify` ok as in 1.0.0; the file is ordinary content |
| R1 | refusal | Index identity whose root also holds an Organization descriptor (known by content) | refused by `verify`, `update`, `migrate` and registration; `status` classifies it as neither |
| R2 | refusal | Organization identity whose root also holds a workspace index descriptor (known by content) | refused as in R1 |
| R3 | refusal | Index `workspaces.json` carrying `rapp-work-organization-pointers/1`, and the reverse | `REFUSE_WORKSPACE_INDEX`; `REFUSE_ORGANIZATION` |
| R4 | refusal | `workspace-index.json` with an extra member, a missing member, `organization_rappid`, a foreign RAPPID or a `pointer_policy` other than `pointer-only` | `REFUSE_WORKSPACE_INDEX` |
| R5 | refusal | Registration across `world_id` | `REFUSE_WORLD_BOUNDARY`, as today |
| R6 | refusal | Migration plan whose successor bytes were swapped for the Organization form | `REFUSE_MIGRATION_PLAN` |
| R7 | refusal | Update plan that changes `kind` | `REFUSE_PLAN` |
| R8 | refusal | Unknown kind in a scaffold request | `REFUSE_KIND` at planning, as today |
| R9 | refusal | A crafted scaffold apply: a hand-built plan with its exact SHA-256 whose subject kind the running release does not write (`workspace-index` in 1.1.0, `protocol-estate`, an unknown value) | `REFUSE_KIND` before any effect; the target and its staging directory stay absent |
| R10 | refusal | After the write sunset: `scaffold` with `kind: "organization"`; registration into an Organization | `REFUSE_KIND`; `REFUSE_ORGANIZATION`, naming migration |
| R11 | refusal | After the read sunset: `verify` and `update` on P1 | refused, naming migration; `migrate` on P1 still plans |

Mutation proofs for those steps: Mutation A turns P1 red; removing the
ambiguity check turns R1 and R2 red; knowing descriptors by file name instead
of content turns P8 red; accepting the old pointer token for an index turns
R3 red; writing `organization.json` for a converted successor turns P5 red;
removing the apply-time kind check turns R9 red (on 1.0.0 the target is then
left behind, as the Context probe shows).

Checks run on this branch, which has no code change: the full local mirror
of the CI job on Python 3.13 and 3.10 (`tools/check.py`, `pytest`, `ruff`,
`mypy`, `tools/release_inventory.py --check`, the build and
`tools/verify_package.py`), 169 tests passing on each.

## Reference implementation

None on this branch; the gap is an idea, so this is the proposal only. When
implemented, it is gated this way: the new kind is recognized only for an
identity that says `kind: "workspace-index"`; every other path keeps its
1.0.0 behavior and bytes, except the `sdk_version` that `.rapp-work/sdk.json`
and `.rapp-work/managed.json` record for the running SDK (P1, P2 and P7);
nothing the SDK plans writes the new form before step 2, and a crafted plan
that tries is refused before any effect (R9); a new index is created only by
an explicit `kind`; conversion happens only through an explicit, reviewed,
hash-applied `migrate`; each sunset lands only in a release the owner names;
and every refusal stays fail-closed. No step lands before the owner accepts
the matching text. The pre-existing apply-path gap (Context) is reported
separately; this branch does not change `main`'s code.

## Related proposals

Sibling drafts on `kody-w/rapp-work` touch the same files and sections. This
branch edits none of them. Each was read at its current pushed head.

| Proposal (gap, branch, head) | Overlap with this proposal | How they compose |
|---|---|---|
| 0001 (G1, `experimental/gap-g1-roster-declaration`, `1899e52`) | `CHANGELOG.md`, `RELEASE-INVENTORY.json` | Textual only: keep both changelog entries, regenerate the inventory |
| 0002 (G2, `experimental/gap-g2-move-action`, `8b3c361`) | Adds §2 and §4.1-§4.3 text and a paragraph in §7 between the Workspace and Organization paragraphs; its draft token `rapp-work-move-plan/1` closes `subject.kind` to `workspace` or `organization`; its move rules protect the root names `organization.json`, `workspaces.json` and `SPEC.md`; edits `api.py`, `cli.py`, `plans.py`, docs, pins, changelog and inventory | This proposal keeps the §7 Workspace paragraph byte-identical and replaces only the Organization paragraph, so 0002's paragraph survives; a merge that shows them adjacent keeps both. Combined wording below |
| 0003 (G3, `experimental/gap-g3-agent-discovery`, `be72a23`) | §11 and a new §11.1 (its "every subfolder is organization" is plain English); `discovery.py`, docs, pins, changelog and inventory | No semantic overlap |
| 0004 (G4, `experimental/gap-g4-migration-successors`, `a26fa71`) | Appends §10.1 and a §12 sentence after the list paragraph (proposal text only); its draft token `rapp-work-pointer-successor/1` closes `source_kind` and the binding `kind` to `hive`, `organization` or `workspace`; edits `migration.py`, `api.py`, `cli.py`, `docs/MIGRATION.md` | Its section 14 already names this proposal and asks for it to be decided first. Its §10.1 composes with this proposal's §10 paragraph. Combined wording below |
| 0006 (G6, `experimental/gap-g6-owner-succession`, `8e5e44e`) | Adds §5.1 and inserts a paragraph before §12's list paragraph (its section 12 text is an insertion at this head); registry files, pins, changelog and inventory | No wording overlap; the §12 insertions sit side by side |
| 0007 (G7, `experimental/gap-g7-instruction-inventory`, `68b549c`) | Adds §7.1-§7.6 after §7's Organization paragraph, including "§7.6 Organizations, earlier trees, and compatibility wrappers", and a paragraph before §12's list paragraph; edits `workspace.py` (including `Organization.verify`), `api.py`, `_paths.py`, docs, pins | Its subsections follow the paragraph this proposal replaces; a merge that shows them adjacent keeps both. Combined wording below |
| 0017 (G17, `experimental/gap-g17-brainstem-sdk-agent`, `c75b4d7`) | Its Brainstem agent's `scaffold` tool closes `kind` to `workspace` or `organization`; changelog and inventory | Combined wording below |

**Combined wording.** Whichever proposal lands second adopts these words, so
that no sibling keeps "Organization" as the only name of the pointer-only
object once this proposal is accepted:

- **0002:** `subject.kind` also allows `workspace-index`, and the protected
  root names also include `workspace-index.json`. "Workspace or Organization"
  reads "Workspace, workspace index or Organization" throughout, and "never
  writes an Organization pointer" reads "never writes a workspace index or
  Organization pointer".
- **0004:** `source_kind` and the binding `kind` also allow
  `workspace-index`, and the bound authority allowlist also names
  `workspace-index.json`. "Workspace or Organization" reads "Workspace,
  workspace index or Organization", and "cannot be registered in an
  Organization" reads "cannot be registered in a workspace index or an
  Organization". Added while 0004's tokens are drafts, this moves no token;
  added after, it would need a new pointer token (Article 2).
- **0007:** "Workspace or Organization" reads "Workspace, workspace index or
  Organization" in §7.1-§7.5 and in its §12 paragraph, and §7.6 applies to a
  workspace index as it does to an Organization.
- **0017:** from step 2 on, the agent's `scaffold` `kind` also allows
  `workspace-index`.
- **All:** keep every changelog entry, and regenerate `RELEASE-INVENTORY.json`
  after each merge.

**Recommended order.** Decide this proposal first, as 0004 also recommends,
because its names settle the closed kind sets that 0002 and 0004 are about to
mint. Then land 0006, 0007, 0002 and 0003 in any order, then 0004, then 0017,
which is 0004's own order. This proposal's implementation steps come last,
rebased on them: step 1b brings the workspace index into 0007's instruction
inventory, 0002's protected names and 0004's successor sources, where those
drafts have not already adopted the combined wording.

## Open questions for the owner (decisions)

1. **Decision D1: Article 3.** Total migration, with a write sunset,
   retirement of each source by its owner and a read sunset (recommended), or
   an explicit exception, which would amend the RAPP/1 Protocol Constitution
   (Token analysis)?
2. **The name and tokens** in "Names" above. If "index" sits too close to
   RAPP Workspace/1's "external indexes", the fallback is "workspace pointer
   list" (Option G).
3. **Article 2 reading.** Growth by registration within `rapp-work-sdk/1`
   (recommended), or new tokens: `rapp-work-sdk/2` and a new
   `rapp-work-migration-source` token?
4. **Releases.** Read in 1.1.0, write and convert in 1.2.0, stop writing the
   old form in 1.3.0 (recommended), or other releases?
5. **Conversion.** Should `migrate` turn an Organization into a workspace
   index (recommended), or keep migrating Organizations as Organizations
   until retirement?
6. **The RAPPID on conversion.** Carry the source RAPPID (recommended): the
   workspace index is the same object under its new name, `rapp-work-sdk/1`
   §10 migration carries the source RAPPID today, and RAPP/1 §6.2 allows a
   new tail for an existing identity only through a re-anchor. The cost: two
   live folders share one RAPPID until the owner retires the source, and a
   registration into the source during that time makes their pointer lists
   differ. Or mint a fresh one, as canonical `rapp-work/1` §6 does for its
   own migrations, which requires "a fresh target workspace RAPPID" and
   forbids "target identity reuse"? That treats the successor as a new
   object, contradicts §7's "the same object", and changes the RAPPID that
   anything outside the SDK may have recorded.
7. **The read sunset.** Which release stops reading Organizations except as
   a migration source, and is `rapp-work-sdk/2` the right last stop for that
   reader (recommended)?
8. **`workspaces.json`.** Keep the file name (recommended), or rename it too?
9. **`Workspace.verify` and the SDK version.** Fix it first, under its own
   proposal (recommended), so a release that carries step 1 does not refuse
   every 1.0.0 Workspace?
10. **The `rapp-work-sdk/1` label.** Which document owns it: this
    repository's or `kody-w/rapp-workspace`'s sidecar profile?
11. **Unknown kinds.** Should step 1 make `status` name an unknown kind
    instead of calling it `legacy-workspace`?
12. **`kind: "workspace"` in `rappid.json`.** RAPP's Article XLVI.2 door
    tooling reads it as a workspace gate, while the SDK writes it for a
    private Workspace (the shared naming table; RAPP proposal 0010, open
    question 7). Which vocabulary owns a `rappid.json` `kind` value? This
    proposal needs no answer to proceed: RAPP's door tooling refuses
    `workspace-index`, as it refuses `organization`.

## Owner actions needed

- Accept or refuse this proposal, and answer the questions above, decision
  D1 first.
- If accepted: land steps 1 to 3 as separate pull requests, name the
  releases, and name the write and read sunsets (steps 5 and 7).
- Retire each converted Organization of the estate (step 6).
- Decide which document owns the `rapp-work-sdk/1` label, and which
  vocabulary owns a `rappid.json` `kind` value (with RAPP proposal 0010).
- Have the organism's maintainer record G11 as proposed.
- No re-signature is needed: the signed registry does not pin
  `rapp-work-sdk/1`.

## Review round 1 disposition

The round 1 review of `505349d` found one high, three medium and seven low
issues. Each is answered here.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | high | The Article 3 claim rested on "old records are never rewritten", which is false, and the plan could never finish a total migration | Fixed. Context now shows the in-place rewrites (`apply_register`, lines 970-974; `apply_update`, lines 692-721); the Token analysis quotes Article 3 and RAPP/1 §12 exactly; Migration steps 4 to 7 give a total migration with a write sunset, per-source retirement by the owner and a read sunset; Rollback no longer claims that nothing is rewritten. The choice is decision D1, open question 1 |
| 2 | medium | The shared naming table missed RAPP Workspace/1's organization tree as an object, and misattributed "every folder is organization" | Fixed in both proposals: an "organization tree" row and a Context section; the quote is now the organism's invariant, beside proposal 0001's own words |
| 3 | medium | The scaffold apply path never checks the kind | Fixed in the plan: step 1b adds the check before any effect, and vector R9 pins it. Context records the probe on 1.0.0. It is pre-existing behavior of `main`, reported separately; this branch does not change `main`'s code |
| 4 | medium | Sibling drafts rewrite the same sections, unmentioned | Fixed: §12 is now an appended paragraph, §7 keeps its Workspace paragraph, and "Related proposals" lists every sibling at its current head, with combined wording and a merge order |
| 5 | low | `rapp-work-migration-source/1` copies the source kind and grows too | Fixed: the Token analysis names it as a second growing value set, and open question 3 covers its token under the strict reading |
| 6 | low | Two more `organization_rappid` keys were missing | Fixed: the register plan subject (line 933) and the `apply_register` result (line 976) are in the inventory and the names table |
| 7 | low | P7 could not pass: `sdk.json` and `managed.json` embed `SDK_VERSION` | Fixed: P7, P2, step 2 and the Reference implementation now exempt exactly those two files. A probe confirmed that only they differ between `SDK_VERSION` 1.0.0 and 1.2.0 |
| 8 | low | The ambiguity refusal would break 1.0.0 Organizations holding a file named `workspace-index.json` | Fixed: descriptors are known by content; the §7 text names the operations and step 1b the code; P8 pins the harmless case |
| 9 | low | The `kody-w/rapp-workspace` inventory was incomplete | Fixed: the inventory row lists every file, including the byte-pinned prior-release fixture that a follow-up must keep verifying |
| 10 | low | "Workspace index" nearly collides with RAPP Workspace/1's "external indexes" | Answered: Option A records it, the §7 text says a workspace index indexes no workspace's files, and "workspace pointer list" is the fallback (Option G, open question 2) |
| 11 | low | Carrying the source RAPPID leaves two live folders on one RAPPID | Disclosed: open question 6 states the divergence and the canonical §6 text, and the Security analysis shows how the steps bound it |

## References

- This repository: `protocols/rapp-work-sdk/1/SPEC.md` §§2, 4, 7, 10, 11 and
  12; `protocols/index.json`; `src/rapp_work/data/profiles.json`;
  `RAPP_WORK_PIN.json`; `vendor/rapp-1/SPEC.md` §12; `src/rapp_work/workspace.py`,
  `api.py`, `migration.py` and `cli.py`; `docs/API.md`, `docs/ARCHITECTURE.md`
  and `docs/MIGRATION.md`; `tests/test_sdk_workspace.py` and
  `tests/test_sdk_migration.py`; `.github/skills/rapp-workspace-manager/`;
  `CONTRIBUTING.md`; `docs/RELEASE.md`.
- Canonical `rapp-work/1`: [`kody-w/rapp-1`](https://github.com/kody-w/rapp-1)
  `protocols/rapp-work/1/SPEC.md` §§1, 2 and 6, `schema.json` and
  `rapp_work.py`.
- RAPP/1 Protocol Constitution: `kody-w/rapp-1` `CONSTITUTION.md` Articles 2,
  3, 4, 6, 7, 8, 10, 14 and 18; RAPP/1 `SPEC.md` §§6.2 and 12.
- RAPP proposal 0010, "The Brainstem's agents folder is not a RAPP
  Workspace", on `kody-w/RAPP` branch `experimental/gap-g22-workspace-names`;
  RAPP `LEXICON.md`, ruling R6; RAPP `CONSTITUTION.md` Article XLVI.2 and
  `tools/door_address.py`.
- RAPP Workspace/1: [`kody-w/rapp-workspace`](https://github.com/kody-w/rapp-workspace)
  `protocols/rapp-workspace/1/SPEC.md` §12 and
  `schemas/organization-assessment.schema.json`, and the sidecar profile
  `protocols/rapp-work-sdk/1`.
- Sibling proposals on this repository: 0001, 0002, 0003, 0004, 0006, 0007
  and 0017 on their `experimental/gap-g*` branches (Related proposals).
- The organism: [`organism/`](https://github.com/kody-w/rapp-work/tree/experimental/rapp-work-constitution/organism)
  on branch `experimental/rapp-work-constitution`: gaps G11, G16 and G22,
  its invariants, the Organization layer and the Workspaces part.
