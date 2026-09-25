# 0017 - A Brainstem agent for the RAPP Work SDK

- **Status:** draft, not accepted. Every change here is a proposal on branch
  `experimental/gap-g17-brainstem-sdk-agent`; the owner decides what moves.
- **Gap:** G17 - "The Brainstem does not call the RAPP Work SDK", so a person
  cannot yet reach their workspaces by talking to their Brainstem.
- **Home spec and section:** `rapp-work-sdk/1` section 2 (Public JSON
  operations), with one new additive section for conversational clients. The
  gap also names `kody-w/RAPP` (the Brainstem layer); no RAPP or Brainstem
  kernel change is needed (see "Home").
- **Channel:** newest (`brainstem-v0.6.16`). This agent is not part of the LTS
  `brainstem-v0.6.9` release scope. In RAR terms it is Frontier
  (`quality_tier: "experimental"`).
- **Intended release:** `rapp-work` 1.1.0 (additive: one sdist-only
  integration file plus tests; the wheel, the public API and `SDK_VERSION`
  stay as they are). The agent carries its own version, `0.1.0`.

## Summary

`integrations/brainstem/agents/rapp_work_agent.py` is one hot-loadable Brainstem
agent, `RappWork`. It exposes the read-only verbs `status`, `verify` and
`discover`, and the change verbs `propose` (a `scaffold`, `update` or `migrate`
plan), `confirm`, `apply` and `undo`. It calls only the six public SDK
operations, stores the SDK's complete plan itself, shows the person a short,
exact summary with the full plan SHA-256, accepts a confirmation only in a
later turn and only for the exact full hash, and then hands the stored plan and
that hash to the SDK, which replays every precondition before its first write.
Its module top level imports only the standard library and `BasicAgent`, so it
can never trigger the Brainstem's load-time `pip install`; it never imports or
runs discovered code and never installs anything.

## Home: where the reference lives, and why

**Decision:** the reference implementation and its tests live in the SDK
repository, `kody-w/rapp-work`, at `integrations/brainstem/agents/`, outside the
importable package. RAR stays the distribution home for the file, through RAR's
own front door, when the owner decides; the file already carries a RAR-ready
`__manifest__` that RAR's tooling accepts (see "Conformance").

This agrees with the lead's working recommendation. The facts it was tested
against:

| Fact | Where | What it means for the home |
|---|---|---|
| One bare `*_agent.py` file belongs to RAR; bundles belong to the rapp store | `kody-w/RAPP` `CONSTITUTION.md` Article XXVII.1 and Article XXXI.1-2 | RAR is the store for this artifact. A source tree with tests elsewhere is allowed: "Multi-file `source/` directories are build-time scaffolding, not ship-time payload" (XXVII.1). |
| Agents enter RAR only by issue mutation, staging, owner approval and a bot commit | RAR `CONTRIBUTING.md` ("Agent publication and lifecycle mutations must use the Issue/receipt path"), `scripts/process_issues.py` `handle_submit_agent`; RAPP Article XXIX.1 | A builder cannot place the file in RAR; the front door is the owner's call. The ready-to-file text is below. |
| RAR's test suite cannot run the agent against the SDK | RAR `CONSTITUTION.md` Article II ("agents use what CommunityRAPP provides", no `requirements.txt`); `tests/conftest.py` covers `agents/@aibast-agents-library` only; `tests/test_brainstem_hotload.py` lists fixed cases | In RAR the agent would be checked for shape only. In `kody-w/rapp-work` its CI (Python 3.10 and 3.13) tests it against the exact SDK commit, so the agent and the six-operation contract cannot drift apart (for example when G2, G3 or G7 change the SDK). |
| The newest Brainstem's in-app RAR browser is pinned | `kody-w/rapp-installer` tag `brainstem-v0.6.16`, `rapp_brainstem/brainstem.py` line 472 and `index.html` line 1882 (`RAR_REVISION = 241c6191...`) | Even after RAR accepts the file, the newest Brainstem's store panel will not list it until a later Brainstem release re-pins RAR. Copying the one file into `agents/` works in every case. |
| RAPP ships only the starter curriculum at the top of `agents/` | RAPP Article III.7 ("User-authored agents live in the user's own workspace, not this repo") and Article XVII | Putting it in RAPP's `agents/` would make it live for every RAPP Brainstem by accident and add a newest-channel file to the LTS pull. |
| The Brainstem kernel is Grail | organism `invariants.md` | No kernel edit is proposed; the existing hot-load contract already supports the agent. |
| A private repository | - | Not shareable with the people who would use it. |
| The SDK repo says new product behavior belongs in `src/rapp_work` | `AGENTS.md`, `docs/ARCHITECTURE.md` | The agent is not SDK behavior; it is a client of the public API. Placing it in `src/` would make it importable and ship it in the wheel. `integrations/` is outside the package, sdist-only, and covered by `RELEASE-INVENTORY.json` and `tools/verify_package.py`. |

Two refinements to the lead's recommendation follow from these facts: the RAR
submission must use RAR's large-source form (a revision-pinned raw URL plus the
`sha256-lf-v1` digest), because the file is 73,033 bytes and RAR's clients move
anything over 50 KiB out of the issue body (`api.json` `large_sources`); and RAR
acceptance alone does not make the agent installable from the newest Brainstem's
store panel (the `RAR_REVISION` pin above).

## Context: what is true today

The SDK (`kody-w/rapp-work` `main`, commit `29ead23b21645f8d7682ee00414930ffa9ce0ca6`):

- `protocols/rapp-work-sdk/1/SPEC.md` section 2: the operation set is closed
  (`status`, `verify`, `discover`, `scaffold`, `update`, `migrate`); the first
  three are read-only and create nothing; the last three plan by default, and an
  effect needs an explicit apply, the complete reviewed plan, its exact
  canonical SHA-256 and a successful replay of every precondition before the
  first write. `src/rapp_work/api.py` implements this in `_apply_fields`
  (line 196), `_scaffold` (216), `_update` (253), `_migrate` (275) and `execute`
  (311).
- Section 4: "Create-only means no existing destination is replaced. SDK updates
  may replace only files named in the prior SDK-owned inventory and only when
  their exact current SHA-256 equals the plan precondition." There is no delete
  operation. Section 12 lists "source deletion" as an explicit refusal.
- Section 11: discovered plugins, skills and Portable Neurons are data; the SDK
  never imports, executes, installs or enables them. `src/rapp_work/discovery.py`
  (lines 220-224) recognizes only `SKILL.md`, `rapp-work-plugin.json` and
  `agent.py`; single-file `*_agent.py` agents are not recognized (gap G3).
- No Brainstem calls any SDK operation today (organism
  `crossings/brainstem-workspaces.md`: "The SDK is in force, but the Brainstem
  does not call it yet").

The newest Brainstem (`kody-w/rapp-installer` tag `brainstem-v0.6.16`,
`rapp_brainstem/brainstem.py`, read only):

- `load_agents()` (line 1832) globs `AGENTS_PATH/*_agent.py` (line 1834), flat.
  `/chat` calls it on every request (line 2271), so each message gets fresh
  module objects and fresh agent instances.
- `_load_agent_from_file()` (line 1640) runs `spec_from_file_location` and
  `exec_module`, instantiates each qualifying class (line 1671) and validates it
  with `_validate_agent_instance()` (line 1524) and `_validate_agent_schema()`
  (line 1554): a name matching `^[a-zA-Z0-9_-]+$` (line 1513), a `metadata`
  dict, a string description and well-formed JSON-schema `parameters`.
- On `ModuleNotFoundError` during a load (line 1691) it derives a package name
  (`_extract_package_name`, line 1794) and runs `pip install <name>` through
  `_auto_install()` (line 1810, command at line 1818).
  `rapp_brainstem/CLAUDE.md` documents it: "Missing pip dependencies are
  auto-installed at import time". RAPP Article III.5 says the same. A module name
  the owner does not hold on the package index is therefore a supply-chain risk
  whenever an agent's top level imports it.
- `run_tool_calls()` (line 2176) calls `agent.perform(**args)` (line 2209) with
  the model's JSON arguments and returns `str(result)`; an exception becomes
  `Error: ...`. The agent never sees the person's own words.
- `start.sh` runs the Brainstem with the installer's virtual environment under
  `.brainstem/venv` in the home folder, on Python 3.11 or newer.

RAPP (`kody-w/RAPP` `main`) Article XVI fixes where agent runtime state goes:
"one env var overrides the default, and the default is a simple directory
outside the repo", home-relative under `.brainstem/`, with "no cwd heuristics,
no multi-tier fallbacks". Article XIII asks that every feature be removable by
deleting one file.

RAR (`kody-w/RAR` `main`): Article IV fixes the `__manifest__` fields
(`schema: "rapp-agent/1.0"`, `name`, `version`, `display_name`, `description`,
`author`, `tags`, `category`, plus `quality_tier`, `requires_env`,
`dependencies`); Article V makes `experimental` the Frontier tier and a
submittable tier; Article XI forbids secrets, network calls in `__init__` and
code execution on import; `CLAUDE.md` describes the rhyme gate
(`scripts/check_near_duplicates.py --base <sha>`).

The organism (read only): `gaps/G17.md` (status idea, phase 4); `invariants.md`
("Propose, confirm, apply. Every change is proposed, confirmed in a later turn,
and applied as one exact step"; "Other people's text is data"; "Only top-level
`agents/*_agent.py` files are live").

## Proposed change

### 1. Normative text for `rapp-work-sdk/1` (not applied on this branch)

`protocols/rapp-work-sdk/1/SPEC.md` is unchanged here: its SHA-256
(`cf64a90f...`) is pinned by `protocols/index.json` and
`src/rapp_work/data/profiles.json`, and the owner decides whether the text
moves. It is not pinned by the frozen signed `registry.json`, so accepting it
needs no re-signature: the owner applies the two insertions below and refreshes
both pins and `RELEASE-INVENTORY.json` in the same change.

Insertion A, appended to section 2 after "Output is canonical I-JSON with no
floating-point values.":

> A conversational client that drives these operations for a person follows
> section 13.

Insertion B, a new section after section 12:

> ## 13. Conversational clients
>
> A conversational client relays a person's requests to the public operations
> through a language model, for example as a Brainstem agent. The model is not
> the person: it may repeat, reorder, shorten or invent arguments. Such a client:
>
> 1. calls only the six public operations of section 2 and no other SDK surface;
> 2. treats the SDK's plan as the only plan: it keeps the complete plan and its
>    `plan_sha256` exactly as the SDK returned them, in private client state; it
>    never accepts a plan or a state location from the model, and treats a hash
>    from the model only as the name of a plan it already stores;
> 3. shows the person a summary derived from the stored plan together with the
>    full `plan_sha256`;
> 4. records a confirmation only when it names the full hash exactly and arrives
>    in a later conversational turn than the latest proposal of that plan;
>    prefixes, other spellings and same-turn confirmations are refused;
> 5. applies only a confirmed plan, sending the complete stored plan and the
>    confirmed hash; the SDK's replay of every precondition (section 2) stays the
>    final gate, and an SDK refusal is reported, never retried with another plan;
> 6. never applies a plan twice, and lets the person withdraw a plan that was not
>    applied;
> 7. offers undo after apply only when an SDK plan expresses the exact inverse;
>    while effects are create-only or exact-hash replacements (section 4) and
>    source deletion is refused (section 12), undo after apply is refused with an
>    account of what was created;
> 8. imports and executes no discovered code (section 11) and installs nothing; a
>    client loaded by a host that installs missing dependencies imports the SDK
>    only when an operation runs, and refuses a module named `rapp_work` found
>    inside the host's own agent folders;
> 9. uses no network and no ambient credentials (section 3); its private state is
>    owner-only, bounded and opened without following symbolic links (section 4).
>
> This section adds obligations for clients only. It changes no operation, input,
> output, plan, hash rule or refusal of this profile.

### 2. Reference implementation (on this branch)

- `integrations/brainstem/agents/rapp_work_agent.py`: the agent (one file).
- `integrations/brainstem/README.md`: what the folder is.
- `tests/brainstem_harness.py`, `tests/test_brainstem_agent.py`,
  `tests/test_brainstem_agent_isolation.py`: 66 tests.
- `pyproject.toml`: the agent is in ruff's `include` and mypy's strict `files`
  (with `agents.*` and `basic_agent` as ignored missing imports).
- `MANIFEST.in`: `recursive-include integrations *`, so the sdist carries the
  file; the wheel does not.
- `CHANGELOG.md`: an "Unreleased (proposal, not accepted)" entry.
- `RELEASE-INVENTORY.json`: regenerated with `tools/release_inventory.py --write`.

No other pinned file changes: `registry.json`, root `SPEC.md`, the
`rapp-hive/1` and `rapp-federation/1` SPECs, `protocols/index.json`,
`src/rapp_work/data/profiles.json`, `RAPP1_PIN.json`, `RAPP_WORK_PIN.json` and
the legacy skill fixtures keep their bytes. The public API (`rapp_work.__all__`,
`PUBLIC_OPERATIONS`, `docs/API.md`) and `SDK_VERSION` are unchanged.

## Design

### Verbs

| `action` | Arguments | SDK operation | Effect |
|---|---|---|---|
| `status` | nothing, `root`, or `plan_sha256` | `status` (with `root`) | Read-only. With nothing: this agent's plans and whether `rapp_work` can be found (found only, never imported). With `plan_sha256`: that record and its history. |
| `verify` | `root` | `verify` | Read-only. |
| `discover` | `roots` (or `root`), optional `max_entries` 1-10000 | `discover` | Read-only and inert. |
| `propose` | `operation` plus `root`, `owner_label`, `slug`, `world_id`, optional `kind` (default `workspace`) and `mode` (default `solo`) for scaffold; `root` for update; `source` and `target` for migrate | the same operation, plan only | Stores the SDK's complete plan and returns the summary and full hash. |
| `confirm` | `plan_sha256` | none | Records the person's yes. |
| `apply` | `plan_sha256` | the stored plan's operation, with `apply`, the stored plan and the confirmed hash; then `verify`, read-only | The SDK's effect. |
| `undo` | `plan_sha256` | `verify`, read-only, after apply | Withdraws before apply; after apply, refuses and explains. |

Every verb takes a closed argument set (empty values a model sends for unused
properties are ignored); anything else is refused. `perform()` with no `action`
returns a usage line, so RAR's and the Brainstem's contract probes get a string.

### The gates, in order

1. **Arguments.** Paths must be absolute without `..`; strings must not contain
   control or invisible formatting characters (Unicode categories Cc, Cf, Cn,
   Co, Cs, Zl, Zp), so a crafted path cannot draw a fake "Plan SHA-256" line into
   a summary; paths inside the agent's own state folder are refused.
2. **The plan comes only from the SDK.** `propose` calls the SDK in plan mode and
   stores exactly the `plan` and `plan_sha256` it returns. There is no argument
   through which a model could pass a plan or a state location.
3. **Exact full hash.** `confirm`, `apply`, `undo` and `status` accept only a
   64-character lowercase hex string; the record is found by exact file name, never
   by prefix.
4. **A later turn.** The Brainstem reloads agents for every message
   (`brainstem.py` line 2271), so an instance lives for exactly one turn. Each
   instance draws a random 128-bit turn id at construction; `confirm` is refused
   when the latest `proposed` event of that plan carries the current turn id.
   Re-proposing a plan resets it to `proposed` in the new turn, so it needs a
   fresh confirmation in a later turn again.
5. **Confirmed state.** `apply` requires the record's history to end in a
   `confirmed` event that names the same hash.
6. **Stored bytes unchanged.** On every read the record must match its file name,
   schema, inputs and a tamper tripwire: a plain SHA-256 over this agent's own
   serialization of the stored plan. The tripwire is not the plan hash and does
   not canonicalize anything (RAPP/1 Article 10); it only stops an edited record
   before the SDK is asked.
7. **The SDK decides.** `apply` sends the stored inputs, `apply: true`, the stored
   plan and the confirmed hash. The SDK recomputes the canonical hash and replays
   every precondition before its first write; a refusal is recorded as an
   `apply-refused` event and reported with the SDK's code.
8. **Once.** An applied plan is terminal: confirm and apply are refused, and
   proposing the identical plan again (for example a replayed migration) says it
   was already applied.

### Private state

- Location: `BRAINSTEM_RAPP_WORK_PATH` if set, otherwise `.brainstem/rapp_work`
  in the home folder (RAPP Article XVI: one variable, one home-relative default).
  The model cannot set it; tests set the variable.
- Layout: `records/<plan_sha256>.json`, one record per plan, plus a `lock` file.
  Folders 0700 and files 0600, owned by the running user, single-link regular
  files, opened component by component with `O_NOFOLLOW` and `dir_fd`; writes
  go to an exclusive new temporary file and are renamed into place; mutating
  verbs hold an exclusive `flock`. Read-only verbs never create the folder.
- Record (`rapp-work-brainstem-agent-record/1`, private to this agent, never
  exchanged): `agent_version`, `operation`, `inputs` (the exact SDK inputs),
  `plan` (the SDK's plan), `plan_sha256`, `plan_storage_sha256` (the tripwire),
  `schema` and `events`: `proposed`, `confirmed` (with the hash), `apply-refused`
  (with the SDK code), `applied` (with a bounded result summary), `withdrawn`,
  each with a UTC time and the turn id. The state is replayed from the events on
  every read; any history the agent could not have written is refused.
- Bounds: 4 MiB per record, 256 records, 16 open plans, 32 events per record,
  8 refused apply attempts per plan, 1024 entries read from the records folder.
  Reaching a bound refuses; nothing is pruned or overwritten.
- Contents: SDK plans (template bytes, RAPPIDs, local folder paths). No
  credentials, tokens or secrets.

### Loading the SDK

The module top level imports `contextlib`, `errno`, `hashlib`, `importlib.util`,
`json`, `os`, `re`, `secrets`, `stat`, `sys`, `time`, `unicodedata`,
`collections.abc` and `typing`, all standard and cross-platform, then
`BasicAgent` from `agents.basic_agent`, else `basic_agent`, else a small
in-file stand-in, so no `ModuleNotFoundError` can escape a load. `fcntl` is
imported only inside the lock functions. `rapp_work` is imported in exactly one
place, inside the function that calls an operation, after
`importlib.util.find_spec("rapp_work")` (which runs no package code) shows it is
not a module inside the Brainstem's `agents/` tree, directly in the Brainstem
folder or the working folder, or inside the agent's own state. A missing SDK
produces an install line that names only the pinned source,
`rapp-work @ git+https://github.com/kody-w/rapp-work@29ead23b21645f8d7682ee00414930ffa9ce0ca6`;
the agent never installs anything and never names a package index project.

## Undo

The SDK's rules decide what undo can honestly be:

- **Before apply** (`proposed` or `confirmed`): undo appends a `withdrawn` event.
  Confirm and apply are refused from then on; the record stays as history.
  Proposing the same plan again reopens it and needs a new confirmation in a later
  turn.
- **After apply:** refused, always, with RAPP Work SDK 1.0.0, and nothing is
  written, not even to the agent's own state. The refusal lists what apply
  created (the target folder, each file with its size and hash prefix, and for a
  migration the SDK's receipt and recovery record and the untouched source) and
  says why: the SDK's only effects are create-only writes and exact-hash
  replacements of SDK-owned files (section 4), it has no delete operation, and
  source deletion is an explicit refusal (section 12), so no SDK plan can express
  the inverse of a scaffold, update or migrate. Restoring a replaced file would
  also need a plan the SDK does not build: an update plan carries only the SDK's
  own current integration bytes, and the prior bytes are recorded only as a hash.
  The agent appends a read-only SDK `verify` of the target.
- **With G2:** gap G2 proposes a `move` plan action whose undo is the inverse move
  (branch `experimental/gap-g2-move-action`, not accepted). Once
  `rapp-work-sdk/1` accepts it, undo of an applied plan made only of moves can be
  offered like any other change: ask the SDK (never this agent) for the inverse
  plan, show its summary and full hash, take a confirmation in a later turn, and
  apply it through the same gate. Plans that create or replace files would still
  be refused. This branch does not depend on G2.

## Refusals

Agent refusals begin `RAPP Work: REFUSED [CODE]` and end with what happened
("Nothing was changed.", or, when an effect's outcome cannot be known, an
instruction to check with status or verify). SDK refusals are passed through as
`RAPP Work: REFUSED by the RAPP Work SDK [CODE]` with the SDK's details.

| Code | When |
|---|---|
| `AGENT_REFUSE_ACTION` | `action` is not one of the seven verbs (exact spelling). |
| `AGENT_REFUSE_INPUT` | An argument the verb does not take (including `plan`, `apply` or a state path), a missing or ill-typed argument, a string over 4096 characters, or control or invisible characters. |
| `AGENT_REFUSE_PATH` | A relative path, a path with `..`, or a path inside the agent's state folder. |
| `AGENT_REFUSE_HASH_FORMAT` | `plan_sha256` is not exactly 64 lowercase hex characters (prefixes, upper case, `sha256:` forms, spaces). |
| `AGENT_REFUSE_UNKNOWN_PLAN` | No stored record has exactly that hash. |
| `AGENT_REFUSE_SAME_TURN` | `confirm` in the same turn as the plan's latest proposal. |
| `AGENT_REFUSE_NOT_CONFIRMED` | `apply` on a plan that is not confirmed, or whose confirmation names another hash. |
| `AGENT_REFUSE_WITHDRAWN` | `confirm` or `apply` after undo withdrew the plan. |
| `AGENT_REFUSE_ALREADY_APPLIED` | `confirm` or `apply` on an applied plan. |
| `AGENT_REFUSE_ATTEMPTS` | The SDK already refused this plan 8 times. |
| `AGENT_REFUSE_UNDO_AFTER_APPLY` | `undo` on an applied plan (see "Undo"). |
| `AGENT_REFUSE_STORED_PLAN` | A record that is not a private single-link regular file, not valid strict JSON, does not match its name, schema or inputs, fails the tripwire, or has an impossible history. |
| `AGENT_REFUSE_STATE` | The state path is relative or contains `..`, a component is a symlink or not a directory, a folder is not 0700 and owned by the user, the lock is busy, or the platform lacks descriptor-relative no-follow operations (the SDK also refuses effects there). |
| `AGENT_REFUSE_STATE_BOUND` | A size, count or history bound would be exceeded. |
| `AGENT_REFUSE_SDK_MISSING` | `rapp_work` cannot be found or imported; the message gives the pinned install line. |
| `AGENT_REFUSE_SDK_SHADOWED` | `rapp_work` resolves inside the Brainstem's own folders or the agent state; it is not imported. |
| `AGENT_REFUSE_SDK_RESPONSE` | The SDK returned an envelope the agent does not recognize. |
| `AGENT_REFUSE_INTERNAL` | Any unexpected exception; the agent stops and says to check with status or verify. |

## Token and compatibility analysis

- **No SDK token moves (RAPP/1 Article 2).** No key set, field grammar or hash
  rule of any SDK record changes: `rapp-work-result/1`,
  `rapp-work-release-plan/1`, `rapp-work-migration-plan/1`,
  `rapp-work-migration-receipt/1`, `rapp-work-managed-files/1`,
  `rapp-work-discovered-skill/1`, `rapp-work-static-api/1` and the `rapp-work-sdk/1`
  records keep their shapes. The proposed section 13 adds obligations for clients
  only; every existing artifact verifies unchanged.
- **One new private token.** `rapp-work-brainstem-agent-record/1` names the
  agent's own state records. They never cross a device boundary and are not part
  of any profile. A later incompatible shape gets a new token; this version
  refuses any record whose schema it does not know.
- **RAPP/1 Article 18 and Article 10.** Nothing touches canonicalization, hashes,
  RAPPIDs, the eleven-key Frame, wire forms or eggs. The agent re-types no
  reference primitive: the canonical plan hash is computed and enforced only by
  the SDK; the tripwire is a plain SHA-256 of the agent's own bytes and is never
  presented as a plan hash.
- **Article 4.** No new envelope and no second door beside `POST /chat`: the agent
  is reached only through the Brainstem's existing tool call.
- **RAR.** The manifest uses the existing `rapp-agent/1.0` shape.
- **Python.** Python 3.10 and newer (the SDK floor); the newest Brainstem runs
  3.11 or newer. The file uses no platform-specific module at load time.
- **Brainstem.** Written and tested against the documented `brainstem-v0.6.16`
  hot-load contract. It is not claimed for, and not tested on, the LTS
  `brainstem-v0.6.9` or the cloud Tier 2 loader (G19); a host that reuses an agent
  instance across messages makes every confirmation look same-turn, so it fails
  closed.
- **Pins.** Only `RELEASE-INVENTORY.json` is regenerated. The wheel keeps its
  113 files; the sdist grows from 153 to 159 files (the agent, its README, the
  harness, two test modules and this proposal).

## Security and privacy analysis

The adversary is the language model: it may be confused or prompt-injected (for
example by text in a workspace it was asked to read) and can call the tool with
any arguments at any time. Other people's files are data. Code the person
adopted into their own Brainstem runs with the person's authority and is out of
scope.

| Threat | Defense | Evidence |
|---|---|---|
| The model applies a plan the person did not see | The plan exists only in agent state, built by the SDK; no plan argument exists; apply needs a confirmed record | `test_the_model_cannot_pass_...`, `test_apply_without_confirmation_is_refused`, mutation M2 |
| The model confirms on its own, in the same turn | Turn id per instance, per message | `test_confirmation_in_the_proposing_turn_is_refused`, mutation M3 |
| A shortened or guessed hash | Exact 64-hex, exact file name | `test_short_wrong_and_respelled_hashes_are_refused`, mutation M1 |
| A confirmed plan that went stale | Stored plan and confirmed hash go to the SDK, which replays every precondition; never re-planned | three stale tests, mutation M5 |
| An edited record | Tripwire before the SDK; the SDK's canonical hash after | two tamper tests, mutation M4 |
| A crafted path that fakes a hash line in the summary | Control and invisible characters refused on input and escaped on output | `test_paths_must_be_absolute_...`, mutation M9 |
| Load-time `pip install` of a name nobody owns | Standard-library-only top level; lazy SDK import; in-file `BasicAgent` stand-in; pinned git install line only | static and blocked-import tests, RAR's own hot-load child, mutations M6 and M6b |
| A `rapp_work` planted in the Brainstem's folders | `find_spec` origin check before any import | shadow tests (four layouts), mutation M7 |
| Other people's agents, skills, plugins, neurons | Never imported or run; discovery is the SDK's inert scan | booby-trap test (sentinel never written), static test for `exec`, `eval`, `import_module`, `subprocess` |
| State under a symlink, or opened by others | `O_NOFOLLOW` walk, 0700/0600, owner check, single link | `test_state_is_private_and_symlinks_...` |
| Two requests at once | Exclusive `flock`, atomic rename | design; SDK also refuses a second effect |
| Undo that destroys data | Undo after apply writes nothing | `test_undo_after_apply_...`, mutation M11 |
| Network or processes | None used; sockets guarded in every in-process test; audit hook denies them in a clean interpreter | `test_a_full_flow_in_a_clean_interpreter_...` |

Residual risks, stated plainly: the agent cannot see the person's words, so a
model that lies about a later reply, or a separately adopted agent that drives
the Brainstem's own `/chat` to manufacture a later turn, could still confirm a
plan the person saw but did not approve. The exact hash, the visible summary, the
later-turn rule and the SDK's replay narrow this; a host-level confirmation (the
Brainstem's click-to-accept, RAPP Article IX) would close it and is an open
question. Anyone who can write the state folder as the person can forge a record;
that is the person's own authority, which could run the SDK directly.

Privacy: the state holds SDK plans (template bytes, RAPPIDs, local folder
paths) on the device only. Nothing leaves the device. Outputs show local paths
only in the person's own chat.

## Migration

None. The agent is new and opt-in: a person copies one file into `agents/` and
installs the SDK. If the owner later accepts section 13, the SPEC edit and its
pin refresh are one change. If the owner submits to RAR, the same bytes go
through RAR's front door (below).

## Rollback

- For a person: delete `agents/rapp_work_agent.py` (RAPP Article XIII). The state
  folder, `.brainstem/rapp_work` in the home folder (or
  `BRAINSTEM_RAPP_WORK_PATH`), is plain data and may be kept or removed. Nothing
  the SDK applied is touched.
- For the repository: revert this branch's commits and run
  `python3 tools/release_inventory.py --write`; no signed or protocol pin needs
  restoring.

## Conformance and test vectors

66 tests: `tests/test_brainstem_agent.py` (53, in-process, through the hot-load
harness, against the real SDK) and `tests/test_brainstem_agent_isolation.py` (13,
in clean `-I -S` interpreters with an audit hook and an import watcher).
`tests/brainstem_harness.py` re-implements the documented v0.6.16 hot-load
contract (flat glob, `spec_from_file_location` plus `exec_module`, a fresh module
per load, the `agents.basic_agent` shim, the instance and schema checks) without
copying kernel bytes, and turns an escaping `ModuleNotFoundError` into a failure.

| Required behavior | Tests |
|---|---|
| Hot-load contract | `test_agent_hot_loads_as_exactly_one_valid_tool`, `test_hot_load_validator_rejects_malformed_schemas` (6), `test_harness_flags_what_the_brainstem_would_quarantine_or_auto_install` |
| Top level: standard library and BasicAgent only | `test_module_top_level_imports_only_cross_platform_stdlib_and_basic_agent`, `test_load_and_first_use_never_look_up_a_third_party_module` (with and without the shim), `test_the_constructor_and_the_load_have_no_side_effects`, `test_the_sdk_is_imported_in_exactly_one_lazy_place_and_nothing_runs_code` |
| Read-only verbs create nothing | `test_read_only_verbs_create_nothing`, `test_status_overview_and_plan_detail_are_read_only`, `test_default_state_location_is_in_the_brainstem_home_folder` |
| Scaffold, confirm, apply, SDK verify | `test_scaffold_propose_confirm_apply_then_sdk_verify_passes` (workspace, organization) |
| Update | `test_update_flow_adopts_sdk_files_on_a_legacy_workspace`, `test_zero_change_update_is_reported_and_not_stored`, `test_reproposal_requires_a_fresh_confirmation_in_a_later_turn` |
| Migrate | `test_migrate_flow_creates_a_successor_and_preserves_the_source` |
| No apply without confirmation | `test_apply_without_confirmation_is_refused`, `test_confirmation_in_the_proposing_turn_is_refused` |
| Wrong or short hash | `test_short_wrong_and_respelled_hashes_are_refused` |
| Tampered stored plan | `test_an_edited_stored_plan_is_refused_before_the_sdk_sees_it`, `test_an_edited_plan_with_a_forged_tripwire_is_refused_by_the_sdk`, `test_corrupt_renamed_or_reordered_records_are_refused` |
| Stale preconditions refused by the SDK and reported | `test_a_stale_scaffold_target_is_refused_by_the_sdk_and_reported`, `test_a_stale_update_precondition_is_refused_by_the_sdk`, `test_a_changed_migration_source_is_refused_by_the_sdk` |
| Double apply | `test_a_plan_is_never_applied_twice` |
| Undo before and after apply | `test_undo_before_apply_withdraws_a_proposal_or_a_confirmation`, `test_undo_after_apply_refuses_explains_and_writes_nothing`, `test_undo_after_a_migration_names_the_untouched_source` |
| Booby-trapped trees never execute | `test_booby_trapped_agents_skills_plugins_and_neurons_never_run`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported` (4 layouts) |
| SDK missing | `test_a_missing_sdk_is_reported_with_its_pinned_source_and_no_side_effects` |
| No network | the autouse socket guard on all 53 in-process tests; `test_a_full_flow_in_a_clean_interpreter_never_touches_network_or_processes` |
| Outputs are strings | every harness call asserts `str`; `test_hostile_arguments_always_return_a_string_and_store_nothing` (17) |
| Only the six operations | `test_only_the_six_public_sdk_operations_are_touched` (a proxy module records every attribute the agent reads) |
| Model cannot pass a plan, state or paths it should not | `test_the_model_cannot_pass_a_plan_a_state_folder_or_unknown_arguments`, `test_paths_must_be_absolute_visible_and_outside_the_agent_state` |
| Private, no-follow, bounded state | `test_state_is_private_and_symlinks_are_never_followed`, `test_open_plan_and_apply_attempt_bounds_are_enforced` |
| Standalone run | `test_standalone_execution_exits_zero_and_writes_nothing` (clean and venv interpreters) |

### Mutation proofs

Each mutation was applied to the agent in place, both test modules were run on
Python 3.13, and the original bytes were restored and checked by SHA-256
(`fba74268602466a5eb3af8d6271598473d400b795cb5f29e6b8a5046643bd509`) before the
next one. Every mutation turned tests red.

| Mutation | Result | Tests that turned red |
|---|---|---|
| M1 hash gate: accept a unique 8-64 hex prefix and resolve it | 1 failed, 65 passed | `test_short_wrong_and_respelled_hashes_are_refused` |
| M2 confirmation gate: apply a merely proposed plan | 4 failed, 62 passed | `test_apply_without_confirmation_is_refused`, `test_confirmation_in_the_proposing_turn_is_refused`, `test_reproposal_requires_a_fresh_confirmation_in_a_later_turn`, `test_short_wrong_and_respelled_hashes_are_refused` |
| M3 later-turn gate removed | 3 failed, 63 passed | `test_confirmation_in_the_proposing_turn_is_refused`, `test_reproposal_requires_a_fresh_confirmation_in_a_later_turn`, `test_a_full_flow_in_a_clean_interpreter_never_touches_network_or_processes` |
| M4 stored-plan tripwire removed | 1 failed, 65 passed | `test_an_edited_stored_plan_is_refused_before_the_sdk_sees_it` |
| M5 apply re-plans instead of sending the confirmed plan and hash | 7 failed, 59 passed | the three stale-precondition tests, `test_an_edited_plan_with_a_forged_tripwire_is_refused_by_the_sdk`, `test_open_plan_and_apply_attempt_bounds_are_enforced`, `test_scaffold_propose_confirm_apply_then_sdk_verify_passes` (both kinds) |
| M6 `import rapp_work` at module top | 10 failed, 56 passed | the static import test, both blocked-import load tests, the constructor test, the SDK-missing test, the isolated standalone run, all four shadow layouts |
| M6b `import fcntl` at module top | 1 failed, 65 passed | `test_module_top_level_imports_only_cross_platform_stdlib_and_basic_agent` |
| M7 shadow check removed | 4 failed, 62 passed | all four layouts of `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported` |
| M8 read-only overview creates the state folder | 7 failed, 59 passed | `test_read_only_verbs_create_nothing`, `test_default_state_location_is_in_the_brainstem_home_folder`, the SDK-missing test, all four shadow layouts |
| M9 control and invisible characters accepted | 1 failed, 65 passed | `test_paths_must_be_absolute_visible_and_outside_the_agent_state` |
| M10 calls `execute` instead of the six operations | 6 failed, 60 passed | `test_only_the_six_public_sdk_operations_are_touched`, `test_read_only_verbs_create_nothing`, `test_a_plan_is_never_applied_twice`, `test_an_edited_plan_with_a_forged_tripwire_is_refused_by_the_sdk`, `test_scaffold_propose_confirm_apply_then_sdk_verify_passes` (both kinds) |
| M11 undo after apply deletes the created folder | 2 failed, 64 passed | `test_undo_after_apply_refuses_explains_and_writes_nothing`, `test_a_full_flow_in_a_clean_interpreter_never_touches_network_or_processes` |

### RAR's own tooling, run read-only on a scratch copy

Against RAR `main` `ecf5f52312cf083eaedf5e0aa8782debc7f0af4b` (1,700 registered
agents), with the file placed at `agents/@kody-w/rapp_work_agent.py` in a scratch
copy (RAR itself was not modified and nothing was pushed or filed):

- `build_registry.py`: `validate_manifest` [], `validate_runtime_contract` [],
  `scan_security` [], `scan_capabilities` [] (no `exec`/`eval` tags);
  `install_filename` `rar_kody_w_rapp_work_agent.py`; seed
  `15158198232163431418`, no collision; the name and display name are unused.
- `scripts/process_issues.py`: `validate_manifest` [],
  `validate_candidate_contract` [], tier submittable, identity
  `@kody-w/rapp_work_agent`, template guard clear.
- `rapp_sdk.py validate`: `Valid: @kody-w/rapp_work_agent [experimental]`;
  `rapp_sdk.py test`: 10/10 contract tests passed (including standalone
  execution and the secret scan).
- `scripts/check_near_duplicates.py --base HEAD^` in a scratch git repository
  holding RAR's `registry.json`: "OK 1 changed agent(s) carry no undeclared
  rhymes".
- RAR's `tests/test_brainstem_hotload.py` child, run on a flattened copy with
  `rapp_work` (and `cryptography`) blocked: loads `["RappWork"]`.
- sha256-lf-v1 of the file: `fba74268602466a5eb3af8d6271598473d400b795cb5f29e6b8a5046643bd509`
  (73,033 bytes, LF only).

## Reference implementation and how it is gated

- **Opt-in by one file copy.** Nothing loads the agent unless a person copies it
  to the top of a Brainstem's `agents/` folder; `integrations/brainstem/agents/`
  is not a Brainstem folder, not in `testpaths`, and not a package.
- **Not in the package.** It is outside `src/rapp_work`, not importable as
  `rapp_work.*`, and absent from the wheel (checked: the wheel keeps its 113
  files); the sdist carries it for source review and tests.
- **Default semantics unchanged.** No SDK operation, input, output or refusal
  changes; section 13 is proposed text only. The agent uses only behavior the
  current `rapp-work-sdk/1` already allows.
- **Fail-closed.** Every check refuses when unsure; nothing is pruned, repaired,
  retried with another plan, deleted or installed.

## How to try

1. Use the newest Brainstem (`brainstem-v0.6.16`) from the installer.
2. Install the SDK into the Brainstem's own Python, from the pinned source (git
   is required; pip fetches the SDK's declared dependency `cryptography` and the
   build tools by their own names, and never looks up `rapp-work` on an index):

   ```bash
   "$HOME/.brainstem/venv/bin/python" -m pip install \
     "rapp-work @ git+https://github.com/kody-w/rapp-work@29ead23b21645f8d7682ee00414930ffa9ce0ca6"
   ```

3. Fetch the agent at commit `0aa83de1713c28a70f82a97b833a7225ee7bdffd` and check
   its hash (the digest is what identifies the bytes; if the branch is merged,
   the same file on `main` has the same digest):

   ```bash
   curl -fsSLO https://raw.githubusercontent.com/kody-w/rapp-work/0aa83de1713c28a70f82a97b833a7225ee7bdffd/integrations/brainstem/agents/rapp_work_agent.py
   shasum -a 256 rapp_work_agent.py
   # fba74268602466a5eb3af8d6271598473d400b795cb5f29e6b8a5046643bd509
   ```

4. Read it, then copy it to the top of the Brainstem's `agents/` folder (or drag
   it into the Brainstem's page, which asks before it installs). Only the top
   level is live. Optionally set `BRAINSTEM_RAPP_WORK_PATH` to choose the state
   folder.
5. Talk to the Brainstem (paths are examples):
   - `status`: "Which RAPP Work plans are open?", or "What is the RAPP Work status
     of /srv/example/finance?", or "Show me RAPP Work plan <full hash>."
   - `verify`: "Verify my RAPP Work workspace at /srv/example/finance."
   - `discover`: "List the skills, plugins and neurons in /srv/example/finance
     without running anything."
   - `propose` scaffold: "Create a RAPP Work workspace called finance for owner
     label example in world example-world at /srv/example/finance."
   - `propose` update: "Bring the workspace at /srv/example/legacy up to the RAPP
     Work SDK integration."
   - `propose` migrate: "Migrate the workspace at /srv/example/finance to a new
     folder /srv/example/finance-next."
   - `confirm` and `apply`, in a new message after reading the summary:
     "confirm <the full 64-character hash>".
   - `undo`: "Withdraw plan <full hash>." before apply; after apply the same
     request returns the explanation and changes nothing.
6. To remove it, delete `agents/rapp_work_agent.py`.
7. To run the tests from a checkout: `python3 -m pip install -e ".[dev]"`, then
   `python3 -m pytest -q tests/test_brainstem_agent.py tests/test_brainstem_agent_isolation.py`.

## Ready-to-file RAR submission (not filed)

For the owner, from the `kody-w` account, when the owner decides. The file is
over 50 KiB, so the command names a revision-pinned raw URL and the
`sha256-lf-v1` digest instead of embedding the source (`api.json`
`large_sources`). Replace the two request ids with one fresh UUID.

Title:

```text
[RAR] CREATE agent @kody-w/rapp_work_agent
```

Body:

````text
```json
{"schema":"rar-change-request/1.0","request_id":"req_<uuid>","idempotency_key":"req_<uuid>","operation":"create","resource":{"kind":"agent","id":"@kody-w/rapp_work_agent"},"preconditions":{"if_none_match":"*"},"payload":{"source":{"media_type":"text/x-python","encoding":"utf-8","url":"https://raw.githubusercontent.com/kody-w/rapp-work/0aa83de1713c28a70f82a97b833a7225ee7bdffd/integrations/brainstem/agents/rapp_work_agent.py","sha256":"sha256:fba74268602466a5eb3af8d6271598473d400b795cb5f29e6b8a5046643bd509"}},"client":{"name":"manual","version":"1"}}
```

RappWork (Frontier, newest Brainstem channel brainstem-v0.6.16; not in the LTS
brainstem-v0.6.9 scope): reaches private RAPP Work workspaces through the RAPP
Work SDK's six public operations and applies only plans whose exact SHA-256 the
person confirmed in a later turn. Reference and tests: kody-w/rapp-work proposal
0017. The top level imports only the standard library and BasicAgent; it needs
the RAPP Work SDK installed from its pinned source to do anything.
````

## Open questions for the owner

1. Accept section 13 into `rapp-work-sdk/1` (recommended: additive, no token
   move), or register a separate client profile instead?
2. Is the later-turn rule (one agent instance per Brainstem message) the right
   confirmation boundary for the newest channel, or should a later Brainstem
   release offer a host-level confirmation that agents can bind a plan hash to
   (RAPP Article IX click-to-accept)?
3. Keep the reference in `kody-w/rapp-work` and, later, submit the same bytes to
   RAR as Frontier? Or keep it out of RAR's default branch until it graduates?
4. Re-pin `RAR_REVISION` in a later newest-channel Brainstem release so its
   store panel can offer the agent?
5. Is `.brainstem/rapp_work` in the home folder, with `BRAINSTEM_RAPP_WORK_PATH`,
   the right state location (RAPP Article XVI's shape)?
6. When G2 is accepted, adopt the inverse-move undo described above; when G3 is
   accepted, discovery will list `*_agent.py` files with no agent change.
7. Promote the agent from `0.1.0` Frontier after a real week of use?

## Owner actions needed

- Accept or refuse this proposal. If accepted: merge the branch (the owner's
  merge), apply insertions A and B to `protocols/rapp-work-sdk/1/SPEC.md`,
  refresh its SHA-256 in `protocols/index.json` and
  `src/rapp_work/data/profiles.json`, rerun
  `python3 tools/release_inventory.py --write`, and choose the release version
  (1.1.0 proposed).
- Decide the RAR submission and, if yes, file the text above from the `kody-w`
  account and approve the staged revision.
- Optionally re-pin RAR in a later newest-channel Brainstem release.
- Organism: G17 moves from `idea` to `proposed` (relayed by the lead).

## References

- `kody-w/rapp-work` `main` `29ead23b21645f8d7682ee00414930ffa9ce0ca6`:
  `protocols/rapp-work-sdk/1/SPEC.md` sections 2, 3, 4, 11, 12;
  `src/rapp_work/api.py`; `src/rapp_work/workspace.py`;
  `src/rapp_work/migration.py`; `src/rapp_work/discovery.py`; `docs/API.md`;
  `AGENTS.md`; `CONTRIBUTING.md`; `docs/RELEASE.md`.
- `kody-w/rapp-installer` tag `brainstem-v0.6.16`
  (`5fbde1776a72715935c3d597a9ddfce28a04032b`): `rapp_brainstem/brainstem.py`
  lines 472, 1513, 1524, 1554, 1640, 1671, 1691, 1794, 1810, 1818, 1832, 1834,
  2176, 2209, 2271; `rapp_brainstem/index.html` lines 1733, 1882, 2134;
  `rapp_brainstem/CLAUDE.md`; `rapp_brainstem/start.sh`.
- `kody-w/RAPP` `main` `8afc9733e20ccf7e579a58028c29ab9c207087fa`:
  `CONSTITUTION.md` Articles III.5, III.7, IX, XIII, XVI, XVII, XXVII, XXVIII,
  XXIX, XXXI.
- `kody-w/RAR` `main` `ecf5f52312cf083eaedf5e0aa8782debc7f0af4b`:
  `CONSTITUTION.md` Articles II, IV, V, XI, XII; `CONTRIBUTING.md`; `CLAUDE.md`;
  `api.json`; `build_registry.py`; `rapp_sdk.py`; `scripts/process_issues.py`;
  `scripts/check_near_duplicates.py`; `tests/test_agent_contract.py`;
  `tests/test_brainstem_hotload.py`.
- `kody-w/rapp-1` `591e014ad39e223b00ab343ae26e5d9a867ebeee`:
  `CONSTITUTION.md` Articles 2, 4, 8, 10, 18.
- The organism (`kody-w/rapp-work` branch `experimental/rapp-work-constitution`):
  `organism/gaps/G17.md`, `organism/gaps/G02.md`, `organism/gaps/G03.md`,
  `organism/crossings/brainstem-workspaces.md`, `organism/invariants.md`.
