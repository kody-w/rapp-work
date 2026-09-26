# 0017 - A Brainstem agent for the RAPP Work SDK

- **Status:** draft, not accepted. Every change here is a proposal on branch
  `experimental/gap-g17-brainstem-sdk-agent`; the owner decides what moves.
  **Revision 2** answers the round-1 independent review (see "Review round 1
  disposition").
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
  stay as they are). The agent carries its own version, `0.2.0` (round 1
  shipped `0.1.0` on this branch only).

## Summary

`integrations/brainstem/agents/rapp_work_agent.py` is one hot-loadable Brainstem
agent, `RappWork`. It exposes the read-only verbs `status`, `verify` and
`discover`, and the change verbs `propose` (a `scaffold`, `update` or `migrate`
plan), `confirm`, `apply` and `undo`. It calls only the six public SDK
operations and stores the SDK's complete plan itself. A proposal returns a
short, exact summary with the full plan SHA-256 for the Brainstem to show;
apart from that output, the agent prints an open plan's full hash only when
echoing a full hash it was just given, and its overview lists 12-character
prefixes. A
confirmation must name the exact full hash and must come from a later turn: a
request that began after the plan's latest proposal was recorded, in an order
the agent keeps in its private state, so neither the proposing request nor a
request that began before the proposal was recorded can confirm it. `apply` hands the stored plan and that hash to the
SDK, which replays every precondition before its first write. Its module top
level imports only the standard library and `BasicAgent`, so it can never
trigger the Brainstem's load-time `pip install`; it never imports or runs
discovered code and never installs anything.

What this enforces is order, not consent. The agent never sees the person's
words: a model that holds a plan's full hash can confirm and apply it in any
later request (see "Residual risks").

## Home: where the reference lives, and why

**Decision:** the reference implementation and its tests live in the SDK
repository, `kody-w/rapp-work`, at `integrations/brainstem/agents/`, outside the
importable package. RAR stays the distribution home for the file, through RAR's
own front door, when the owner decides; the file carries a RAR-ready
`__manifest__` that RAR's tooling accepts (see "Conformance").

This agrees with the lead's working recommendation. The facts it was tested
against:

| Fact | Where | What it means for the home |
|---|---|---|
| One bare `*_agent.py` file belongs to RAR; bundles belong to the rapp store | `kody-w/RAPP` `CONSTITUTION.md` Article XXVII.1 and Article XXXI.1-2 | RAR is the store for this artifact. A source tree with tests elsewhere is allowed: "Multi-file `source/` directories are build-time scaffolding, not ship-time payload" (XXVII.1). |
| Agents enter RAR only by issue mutation, staging, owner approval and a bot commit | RAR `CONTRIBUTING.md` ("Agent publication and lifecycle mutations must use the Issue/receipt path"), `scripts/process_issues.py` `handle_submit_agent`; RAPP Article XXIX.1 | A builder cannot place the file in RAR; the front door is the owner's call. The ready-to-file text is below. |
| RAR's test suite cannot run the agent against the SDK | RAR `CONSTITUTION.md` Article II ("agents use what CommunityRAPP provides", no `requirements.txt`); `tests/conftest.py` covers `agents/@aibast-agents-library` only; `tests/test_brainstem_hotload.py` lists fixed cases | In RAR the agent would be checked for shape only. In `kody-w/rapp-work` its CI (Python 3.10 and 3.13) tests it against the exact SDK, so the agent and the six-operation contract cannot drift apart (see "Related proposals"). |
| The newest Brainstem's in-app RAR browser is pinned | `kody-w/rapp-installer` tag `brainstem-v0.6.16`, `rapp_brainstem/brainstem.py` line 472 and `index.html` line 1882 (`RAR_REVISION = 241c6191...`) | Even after RAR accepts the file, the newest Brainstem's store panel will not list it until a later Brainstem release re-pins RAR. Copying the one file into `agents/` works in every case. |
| RAPP ships only the starter curriculum at the top of `agents/` | RAPP Article III.7 ("User-authored agents live in the user's own workspace, not this repo") and Article XVII | Putting it in RAPP's `agents/` would make it live for every RAPP Brainstem by accident and add a newest-channel file to the LTS pull. |
| RAPP also has `rapp_brainstem/agents/experimental/` | RAPP Article III.7: "In-flight agents the auto-loader ignores. Hand-load them when you're ready." | Considered and not chosen. The Grail's flat loader ignores every subfolder, but RAPP's own recursive loader (RAPP commits `c1f356e` to `06d16f1`, release tags `brainstem-v0.10.0` through `brainstem-v0.12.1`) skipped only `experimental_agents/`, `disabled_agents/` and `__pycache__/`, so a file in `agents/experimental/` is live there. It would also put a newest-channel file inside RAPP's LTS-pinned tree, and RAPP's CI cannot run it against the SDK. Hand-loading from there is the same one-file copy as from here. |
| The Brainstem kernel is Grail | organism `invariants.md` | No kernel edit is proposed; the existing hot-load contract already supports the agent. |
| A private repository | - | Not shareable with the people who would use it. |
| The SDK repo says new product behavior belongs in `src/rapp_work` | `AGENTS.md`, `docs/ARCHITECTURE.md` | The agent is not SDK behavior; it is a client of the public API. Placing it in `src/` would make it importable and ship it in the wheel. `integrations/` is outside the package, sdist-only, and covered by `RELEASE-INVENTORY.json` and `tools/verify_package.py`. |

Two refinements to the lead's recommendation follow from these facts: the RAR
submission must use RAR's large-source form (a revision-pinned raw URL plus the
`sha256-lf-v1` digest), because the file is 77,318 bytes and RAR's clients move
anything over 50 KiB out of the issue body (`api.json` `large_sources`); and RAR
acceptance alone does not make the agent installable from the newest Brainstem's
store panel (the `RAR_REVISION` pin above).

## Context: what is true today

The SDK (`kody-w/rapp-work` `main` at `29ead23b21645f8d7682ee00414930ffa9ce0ca6`;
`main` has since moved to `0da52a6`, which adds only a README network header
and a regenerated `RELEASE-INVENTORY.json`, so the SDK is the same):

- `protocols/rapp-work-sdk/1/SPEC.md` section 2: the operation set is closed
  (`status`, `verify`, `discover`, `scaffold`, `update`, `migrate`); the first
  three are read-only and create nothing; the last three plan by default, and an
  effect needs an explicit apply, the complete reviewed plan, its exact
  canonical SHA-256 and a successful replay of every precondition before the
  first write. `src/rapp_work/api.py` implements this in `_apply_fields`
  (line 196), `_scaffold` (216), `_update` (253), `_migrate` (275) and `execute`
  (311). `execute` turns `OSError`, `ValueError`, `KeyError`, `TypeError` and
  `RuntimeError` into the refusal `REFUSE_RUNTIME`.
- Section 4: "Create-only means no existing destination is replaced. SDK updates
  may replace only files named in the prior SDK-owned inventory and only when
  their exact current SHA-256 equals the plan precondition." There is no delete
  operation. Section 12 lists "source deletion" as an explicit refusal.
- An apply can stop part-way. `src/rapp_work/workspace.py` `apply_update` writes
  a plan-bound recovery marker (`.rapp-work/update-recovery.json`) before its
  first file write; a failure after that leaves the marker and some files, a
  retry of the same plan resumes, and any other plan is refused with
  `REFUSE_RECOVERY_BINDING`. `src/rapp_work/migration.py` `apply_migration`
  does the same with a hidden staging folder next to the target. A scaffold is
  staged and activated in one rename, and its staging is removed on failure.
- Section 11: discovered plugins, skills and Portable Neurons are data; the SDK
  never imports, executes, installs or enables them. `src/rapp_work/discovery.py`
  (lines 220-224) recognizes only `SKILL.md`, `rapp-work-plugin.json` and
  `agent.py`; single-file `*_agent.py` agents are not recognized.
- No Brainstem calls any SDK operation today (organism
  `crossings/brainstem-workspaces.md`: "The SDK is in force, but the Brainstem
  does not call it yet").

The newest Brainstem (`kody-w/rapp-installer` tag `brainstem-v0.6.16`,
`rapp_brainstem/brainstem.py`, read only):

- `load_agents()` (line 1832) globs `AGENTS_PATH/*_agent.py` (line 1834), flat.
  `/chat` (line 2271) and `/chat/stream` (line 2444) call it once per request,
  before the model runs, so each request gets fresh module objects and fresh
  agent instances; `/agents`, `/health` and the diagnostics routes build
  instances too but never call `perform`.
- The server runs requests on threads: `app.run(..., threaded=True)`
  (line 3465). Two requests can be in flight at once.
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
- Every tool result is appended to the conversation (line 2317; `/chat/stream`
  line 2543) and posted with the next model round to the Copilot
  chat-completions API (line 2304; `/chat/stream` line 2525).
- `start.sh` runs the Brainstem with the installer's virtual environment under
  `.brainstem/venv` in the home folder, on Python 3.11 or newer.

The newest Brainstem's page (`rapp_brainstem/index.html`, same tag): it keeps
several requests in flight (`activeRequests`, line 2612) and Enter always sends
(line 2353); a request's history leaves out the turns still in flight
(lines 2595-2600); the history it sends holds only user and assistant text
(line 1335), so a tool result reaches the model only within its own request;
the raw tool output is shown to the person only in a collapsed "agent called"
panel under the reply (lines 2495, 2504).

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

The organism (read only): `gaps/G17.md` (status proposed, phase 5);
`invariants.md` ("Propose, confirm, apply. Every change is proposed, confirmed
in a later turn, and applied as one exact step"; "Other people's text is data";
"Only top-level `agents/*_agent.py` files are live").

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
> the person: it may repeat, reorder, shorten or invent arguments. A turn is one
> host request, for which the host builds the client before the model runs; a
> host may run several turns at once. Such a client:
>
> 1. calls only the six public operations of section 2 and no other SDK surface;
> 2. treats the SDK's plan as the only plan: it keeps the complete plan and its
>    `plan_sha256` exactly as the SDK returned them, in private client state; it
>    never accepts a plan or a state location from the model, and treats a hash
>    from the model only as the name of a plan it already stores;
> 3. returns, for the host to show the person, a summary derived from the stored
>    plan together with the full `plan_sha256`, and reveals the full hash of an
>    open plan nowhere else (echoing a hash the caller supplied reveals nothing
>    new);
> 4. records a confirmation only when it names the full hash exactly and arrives
>    in a later turn than the plan's latest proposal. A turn is later only if it
>    began after that proposal was durably recorded, as ordered by a sequence the
>    client persists in its private state and advances under its state lock
>    whenever it records an event; being a different turn, request, thread or
>    client instance is not enough. Prefixes, other spellings, and
>    confirmations from the proposing turn or from a turn that began before the
>    proposal was recorded are refused;
> 5. applies only a confirmed plan, sending the complete stored plan and the
>    confirmed hash; the SDK's replay of every precondition (section 2) stays the
>    final gate. It reports an SDK refusal of an apply as possibly partial, never
>    retries it with another plan, and after a runtime or write refusal offers
>    the same plan again, because only that plan can finish a partly applied
>    update or migration;
> 6. never applies a plan twice, and lets the person withdraw a plan that was not
>    applied; any bound on refused applies counts only refusals since the latest
>    confirmation, and a new confirmation in a later turn than those refusals
>    resets it;
> 7. offers undo after apply only when an SDK plan expresses the exact inverse;
>    while effects are create-only or exact-hash replacements (section 4) and
>    source deletion is refused (section 12), undo after apply is refused with an
>    account of what was created;
> 8. imports and executes no discovered code (section 11) and installs nothing; a
>    client loaded by a host that installs missing dependencies imports the SDK
>    only when an operation runs, and refuses a module named `rapp_work` found
>    inside the host's own agent folders;
> 9. uses no network and no ambient credentials (section 3); its private state is
>    owner-only, bounded and opened without following symbolic links (section 4),
>    and it refuses every path input that lies inside that state;
> 10. treats everything it returns as leaving the device, because a
>     conversational host sends tool results to its model provider: it returns
>     no home-folder path, identifier or discovered detail that the person's
>     request does not need.
>
> This section adds obligations for clients only. It changes no operation, input,
> output, plan, hash rule or refusal of this profile.

### 2. Reference implementation (on this branch)

- `integrations/brainstem/agents/rapp_work_agent.py`: the agent (one file,
  77,318 bytes, SHA-256
  `5f916e5e2a0f23f8e07dded1d1f8ad7729789a12c027313ad44571b737999f07`).
- `integrations/brainstem/README.md`: what the folder is.
- `tests/brainstem_harness.py`, `tests/test_brainstem_agent.py`,
  `tests/test_brainstem_agent_isolation.py`: 79 tests.
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
| `status` | nothing, `root`, or `plan_sha256` | `status` (with `root`) | Read-only. With nothing: this agent's plans, each open plan named by a 12-character hash prefix only, and whether `rapp_work` can be found (found only, never imported). With `plan_sha256`: that record and its history. |
| `verify` | `root` | `verify` | Read-only. |
| `discover` | `roots` (or `root`), optional `max_entries` 1-10000 | `discover` | Read-only and inert; found paths are shown under the searched folder's name. |
| `propose` | `operation` plus `root`, `owner_label`, `slug`, `world_id`, optional `kind` (default `workspace`) and `mode` (default `solo`) for scaffold; `root` for update; `source` and `target` for migrate | the same operation, plan only | Stores the SDK's complete plan and returns the summary and the full hash. |
| `confirm` | `plan_sha256` | none | Records a confirmation from a later turn. |
| `apply` | `plan_sha256` | the stored plan's operation, with `apply`, the stored plan and the confirmed hash; then `verify`, read-only | The SDK's effect. |
| `undo` | `plan_sha256` | `verify`, read-only, after apply | Withdraws before apply; after apply, refuses and explains. |

Every verb takes a closed argument set (empty values a model sends for unused
properties are ignored); anything else is refused. `perform()` with no `action`
returns a usage line, so RAR's and the Brainstem's contract probes get a string.

### The gates, in order

1. **Arguments.** Paths must be absolute without `..`; strings must not contain
   control or invisible formatting characters (Unicode categories Cc, Cf, Cn,
   Co, Cs, Zl, Zp), so a crafted path cannot draw a fake "Plan SHA-256" line into
   a summary. Every path input of every verb (`status`, `verify`, `discover` and
   all three proposals) is refused when it lies inside the agent's own state
   folder, compared case-insensitively and after resolving symbolic links, so a
   differently cased spelling or a symlinked alias is caught too.
2. **The plan comes only from the SDK.** `propose` calls the SDK in plan mode and
   stores exactly the `plan` and `plan_sha256` it returns. There is no argument
   through which a model could pass a plan or a state location.
3. **Exact full hash.** `confirm`, `apply`, `undo` and `status` accept only a
   64-character lowercase hex string; the record is found by exact file name, never
   by prefix. The agent prints the full hash of an open plan only in that
   plan's proposal output and when echoing a full hash it was given.
4. **A later turn.** Defined exactly:
   - A turn is one Brainstem request. `/chat` and `/chat/stream` build fresh
     agent instances before the model runs (lines 2271, 2444), and the server
     runs requests on threads (line 3465), so turns can overlap.
   - The agent keeps a logical clock: the file `clock` in its state holds the
     sequence number of the latest event it recorded. Recording an event
     (proposed, confirmed, apply-refused, applied, withdrawn) happens under the
     exclusive state lock: the agent reads the clock, gives the event the next
     number, writes the record, and only then replaces the clock file by an
     atomic rename.
   - Each instance reads the clock once, without the lock, when it is built,
     and never writes it.
   - `confirm` is recorded only if that reading is at least the number of the
     plan's latest event: its proposal, or, for a new confirmation after refused
     applies, its latest refused apply. The proposing request, a request that
     began before the proposal, and a request that began while the proposal was
     being recorded are refused with `AGENT_REFUSE_NOT_LATER_TURN`.
   - Proposing a plan again gives it a new number, so every request already in
     flight must wait for a later one.
   - Why the order holds under threads: `flock` excludes every other open file
     description, including another thread of the same process, so events are
     numbered one at a time; the rename is atomic, so an unlocked reader sees
     the old number or the new one, never a mix; and the record is written
     before the clock, so reading the new number implies the stored event (a
     test builds an instance in the middle of that commit).
   - An instance whose state cannot be read safely has no reading and refuses
     every confirmation with `AGENT_REFUSE_STATE`. A host that keeps one instance across requests makes
     every confirmation look early, so it fails closed.
   - What this does not decide is listed under "Residual risks".
5. **Confirmed state.** `apply` requires the record's history to end in a
   `confirmed` event, or in refused applies after one, that names the same hash.
6. **Stored bytes unchanged.** On every read the record must match its file name,
   schema, inputs and a tamper tripwire: a plain SHA-256 over this agent's own
   serialization of the stored plan. The tripwire is not the plan hash and does
   not canonicalize anything (RAPP/1 Article 10); it only stops an edited record
   before the SDK is asked.
7. **The SDK decides.** `apply` sends the stored inputs, `apply: true`, the stored
   plan and the confirmed hash. The SDK recomputes the canonical hash and replays
   every precondition before its first write; a refusal is recorded as an
   `apply-refused` event and reported as possibly partial (see "After a refused
   apply").
8. **Once.** An applied plan is terminal: confirm and apply are refused, and
   proposing the identical plan again (for example a replayed migration) says it
   was already applied.
9. **Refused applies.** After 8 SDK refusals since the latest confirmation,
   `apply` is refused with `AGENT_REFUSE_ATTEMPTS`. The recovery is named: fix
   the cause, then confirm the plan again in a new message (a turn later than
   its latest refused apply), which allows 8 more; or withdraw it. Proposing it
   again also starts afresh.

### After a refused apply

An SDK apply can stop part-way (see "Context"), so the agent never says that
nothing changed after an apply refusal. It records the refusal and returns the
SDK's code, message and details, then one next step chosen by the code:

| SDK code | Next step the agent gives |
|---|---|
| `REFUSE_RUNTIME`, `REFUSE_WRITE_VERIFY` (an I/O or read-back error) | Fix the cause (for example free space or permissions), then apply the same hash again: the SDK finishes this same plan. Do not withdraw it, because only this plan can finish a partly applied update or migration. |
| `REFUSE_RECOVERY_BINDING` | An earlier plan's apply stopped part-way in this folder, and the SDK lets only that plan finish: apply it again with the full hash from its proposal. This plan stays confirmed. |
| any other code (a changed precondition, a stale target, an edited plan) | Check the folder with verify. If it changed on purpose after the proposal, withdraw this plan with undo and propose again; if not, put it back as it was and apply the same hash again. |

A withdrawal of a plan whose apply was refused says how many refusals there
were since its latest proposal and that a refused apply can stop part-way. If
the agent cannot record the refusal itself, it adds a warning that its record
may be incomplete.

### Private state

- Location: `BRAINSTEM_RAPP_WORK_PATH` if set, otherwise `.brainstem/rapp_work`
  in the home folder (RAPP Article XVI: one variable, one home-relative default).
  The model cannot set it; tests set the variable.
- Layout: `records/<plan_sha256>.json`, one record per plan, plus `lock` and
  `clock`. Folders 0700 and files 0600, owned by the running user, single-link
  regular files, opened component by component with `O_NOFOLLOW` and `dir_fd`;
  writes go to an exclusive new temporary file and are renamed into place;
  mutating verbs hold an exclusive `flock`. Read-only verbs never create the
  folder, and building an instance only reads the clock.
- Record (`rapp-work-brainstem-agent-record/2`, private to this agent, never
  exchanged): `agent_version`, `operation`, `inputs` (the exact SDK inputs),
  `plan` (the SDK's plan), `plan_sha256`, `plan_storage_sha256` (the tripwire),
  `schema` and `events`. Every event carries `event`, a UTC time and its clock
  number `seq`; `confirmed` adds the hash and `refused` (refused applies since
  the latest proposal, before this confirmation); `apply-refused` adds the SDK
  code and message; `applied` adds a bounded result summary.
- History: the latest proposal, at most one confirmation, the refused applies
  since that confirmation, and at most one final event (`applied` or
  `withdrawn`). Proposing again keeps nothing before the new proposal;
  confirming again keeps only the proposal. So a history never exceeds 11
  events and can never fill up. The state is replayed from the events on every
  read; any history the agent could not have written, including sequence
  numbers that do not rise, is refused.
- Bounds: 4 MiB per record, 256 records, 16 open plans, 11 events per record,
  8 refused applies per confirmation, 1024 entries read from the records folder.
  Reaching a bound refuses and names the way out; no record is pruned or
  overwritten to make room (the only history the agent drops is a plan's own,
  when that plan is proposed or confirmed again, as described above).
- Contents: SDK plans (template bytes, RAPPIDs, local folder paths). No
  credentials, tokens or secrets.

### Loading the SDK

The module top level imports `contextlib`, `errno`, `hashlib`, `importlib.util`,
`json`, `os`, `re`, `secrets`, `stat`, `time`, `unicodedata`, `collections.abc`
and `typing`, all standard and cross-platform, then `BasicAgent` from
`agents.basic_agent`, else `basic_agent`, else a small in-file stand-in, so no
`ModuleNotFoundError` can escape a load. `fcntl` is imported only inside the
lock functions. `rapp_work` is imported in exactly one place, inside the
function that calls an operation, after `importlib.util.find_spec("rapp_work")`
(which runs no package code) shows it is not a module inside the Brainstem's
`agents/` tree, directly in the Brainstem folder or the working folder, or
inside the agent's own state. A missing SDK produces an install line that names
only the pinned source,
`rapp-work @ git+https://github.com/kody-w/rapp-work@29ead23b21645f8d7682ee00414930ffa9ce0ca6`,
and names the interpreter generically ("the Python that runs this Brainstem");
the agent never installs anything and never names a package index project.

## Undo

The SDK's rules decide what undo can honestly be:

- **Before apply** (`proposed` or `confirmed`): undo appends a `withdrawn` event.
  Confirm and apply are refused from then on; the record stays. Proposing the
  same plan again reopens it and needs a new confirmation in a later turn.
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
- Proposal 0002 (see "Related proposals") would give the SDK an inverse-move
  plan; the agent's runtime text does not mention unaccepted proposals.

## Refusals

Agent refusals begin `RAPP Work: REFUSED [CODE]` and end with what happened
("Nothing was changed.", or, when an effect's outcome cannot be known, an
instruction to check with status or verify). SDK refusals are passed through as
`RAPP Work: REFUSED by the RAPP Work SDK [CODE]` with the SDK's details.

| Code | When |
|---|---|
| `AGENT_REFUSE_ACTION` | `action` is not one of the seven verbs (exact spelling). |
| `AGENT_REFUSE_INPUT` | An argument the verb does not take (including `plan`, `apply` or a state path), a missing or ill-typed argument, a string over 4096 characters, or control or invisible characters. |
| `AGENT_REFUSE_PATH` | A relative path, a path with `..`, or, for any verb, a path inside the agent's state folder (in any letter case, or through a symlink). |
| `AGENT_REFUSE_HASH_FORMAT` | `plan_sha256` is not exactly 64 lowercase hex characters (prefixes, upper case, `sha256:` forms, spaces). |
| `AGENT_REFUSE_UNKNOWN_PLAN` | No stored record has exactly that hash. |
| `AGENT_REFUSE_NOT_LATER_TURN` | `confirm` from a request that began before the plan's latest proposal (or, for a new confirmation, its latest refused apply) was recorded, including the proposing request. |
| `AGENT_REFUSE_NOT_CONFIRMED` | `apply` on a plan that is not confirmed, or whose confirmation names another hash. |
| `AGENT_REFUSE_WITHDRAWN` | `confirm` or `apply` after undo withdrew the plan. |
| `AGENT_REFUSE_ALREADY_APPLIED` | `confirm` or `apply` on an applied plan. |
| `AGENT_REFUSE_ATTEMPTS` | The SDK refused this plan 8 times since its latest confirmation; the message names the recovery. |
| `AGENT_REFUSE_UNDO_AFTER_APPLY` | `undo` on an applied plan (see "Undo"). |
| `AGENT_REFUSE_STORED_PLAN` | A record, the state lock or the state clock that is not a private single-link regular file, or a record that is not valid strict JSON, does not match its name, schema or inputs, fails the tripwire, or has an impossible history. |
| `AGENT_REFUSE_STATE` | The state path is relative or contains `..`, a component is a symlink or not a directory, a folder is not 0700 and owned by the user, the clock is not a decimal counter or cannot be written, the clock could not be read safely when a confirming request began, the lock is busy, or the platform lacks descriptor-relative no-follow operations (the SDK also refuses effects there). |
| `AGENT_REFUSE_STATE_BOUND` | A size or count bound would be exceeded; the message names the way out. |
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
- **One private token, relabeled.** `rapp-work-brainstem-agent-record/2` names
  the agent's own state records. They never cross a device boundary and are not
  part of any profile. Round 1's draft wrote `/1` records with per-instance turn
  ids; the revised events carry clock numbers, so the shape gets a new label and
  a `/1` record (for example one written by someone who tried the round-1 file)
  is refused as an unknown shape instead of being misread. This version refuses
  any record whose schema it does not know.
- **RAPP/1 Article 18 and Article 10.** Nothing touches canonicalization, hashes,
  RAPPIDs, the eleven-key Frame, wire forms or eggs. The agent re-types no
  reference primitive: the canonical plan hash is computed and enforced only by
  the SDK; the tripwire is a plain SHA-256 of the agent's own bytes and is never
  presented as a plan hash; the clock is a plain decimal counter.
- **Article 4.** No new envelope and no second door beside `POST /chat`: the agent
  is reached only through the Brainstem's existing tool call.
- **RAR.** The manifest uses the existing `rapp-agent/1.0` shape.
- **Python.** Python 3.10 and newer (the SDK floor); the newest Brainstem runs
  3.11 or newer. The file uses no platform-specific module at load time.
- **Brainstem.** Written and tested against the `brainstem-v0.6.16` hot-load
  contract, including its real loader functions (see "Conformance"). It is not
  claimed for, and not tested on, the LTS `brainstem-v0.6.9` or the cloud Tier 2
  loader (G19). The later-turn rule assumes a host builds the agent once per
  request, before the model runs; a host that reuses an instance across requests
  fails closed, and a host that built a new instance for every tool call would
  let one request confirm its own proposal (not the case in `brainstem-v0.6.16`).
- **Pins.** Only `RELEASE-INVENTORY.json` is regenerated. The wheel keeps its
  113 files; the sdist carries 159 files, 6 more than `main` (the agent, its
  README, the harness, two test modules and this proposal).

## Security and privacy analysis

The adversary is the language model: it may be confused or prompt-injected (for
example by text in a workspace it was asked to read) and can call the tool with
any arguments at any time, in any request, including two at once. Other
people's files are data. Code the person adopted into their own Brainstem runs
with the person's authority and is out of scope.

| Threat | Defense | Evidence |
|---|---|---|
| The model applies a plan that no proposal produced | The plan exists only in agent state, built by the SDK; no plan argument exists; apply needs a confirmed record | `test_the_model_cannot_pass_...`, `test_apply_without_confirmation_is_refused`, mutation M2 |
| The model confirms in the proposing request | The instance's clock reading predates the proposal's number | `test_confirmation_in_the_proposing_turn_is_refused`, mutations M3, M3b |
| A request already in flight confirms a plan proposed meanwhile (round-1 finding 1) | Same rule: the reading was taken when that request began; re-proposing restarts the order | `test_a_request_that_began_before_the_proposal_cannot_confirm_it`, `test_proposing_again_restarts_the_order_for_requests_in_flight`, `test_a_request_that_begins_while_a_proposal_is_recorded_counts_as_earlier`, `test_concurrent_requests_are_serialized_by_the_state_lock`, mutations M3c, M21 |
| The model learns a full hash from something other than the proposal | The overview lists 12-character prefixes; state-folder paths are refused for every verb, so the records' names cannot be listed | `test_status_overview_and_plan_detail_are_read_only`, `test_every_verb_refuses_paths_inside_the_agent_state`, mutations M12, M13, M13b, M13c |
| A shortened or guessed hash | Exact 64-hex, exact file name | `test_short_wrong_and_respelled_hashes_are_refused`, mutation M1 |
| A confirmed plan that went stale | Stored plan and confirmed hash go to the SDK, which replays every precondition; never re-planned | four stale tests, mutation M5 |
| An apply that stops part-way is abandoned (round-1 finding 4) | Refusals are reported as possibly partial; runtime and write errors send the person back to the same hash | `test_an_apply_that_stops_part_way_says_so_and_the_same_plan_finishes_it`, mutation M14 |
| A plan locked out by its own history (round-1 finding 5) | Refusals count since the latest confirmation; re-confirmation and re-proposal restart the history | `test_refused_applies_count_since_the_latest_confirmation`, `test_proposing_and_withdrawing_never_fills_a_plan_history`, mutations M15, M16, M17 |
| An edited record | Tripwire before the SDK; the SDK's canonical hash after | two tamper tests, mutation M4 |
| A crafted path that fakes a hash line in the summary | Control and invisible characters refused on input and escaped on output | `test_paths_must_be_absolute_...`, mutation M9 |
| Load-time `pip install` of a name nobody owns | Standard-library-only top level; lazy SDK import; in-file `BasicAgent` stand-in; pinned git install line only | static and blocked-import tests, RAR's own hot-load child, the real v0.6.16 loader, mutations M6 and M6b |
| A `rapp_work` planted in the Brainstem's folders | `find_spec` origin check before any import | shadow tests (four layouts), mutation M7 |
| Other people's agents, skills, plugins, neurons | Never imported or run; discovery is the SDK's inert scan | booby-trap test (sentinel never written), static test for `exec`, `eval`, `import_module`, `subprocess` |
| State under a symlink, or opened by others | `O_NOFOLLOW` walk, 0700/0600, owner check, single link; an instance that could not read the clock safely refuses to confirm | `test_state_is_private_and_symlinks_...`, the constructor test, mutation M23 |
| Two requests at once | Exclusive `flock` across threads and processes, atomic rename, numbered events | `test_concurrent_requests_are_serialized_by_the_state_lock`, `test_a_change_waits_for_the_state_lock_and_refuses_when_it_stays_busy` |
| Undo that destroys data | Undo after apply writes nothing | `test_undo_after_apply_...`, mutation M11 |
| Local details sent to the model provider (round-1 finding 3) | No interpreter or state path, no RAPPIDs, relative discovery paths, prefixes for open plans | `test_outputs_leave_out_home_folders_rappids_and_the_interpreter`, the SDK-missing test, mutations M18, M19, M20 |
| Network or processes | None used; sockets guarded in every in-process test; audit hook denies them in a clean interpreter | `test_a_full_flow_in_a_clean_interpreter_...` |

### Residual risks, stated plainly

- **Order is not consent.** The agent cannot see the person's words, so it
  cannot tell whether the person saw or approved a summary. Any request that
  began after a plan's latest proposal can confirm and apply it if its model
  has the full hash: from the person's message (the intended path), from the
  model's own earlier reply (the page sends assistant text as history), or from
  anything the person pasted. A model that puts the hash in its reply without
  the summary, or that confirms on its own in a later request (one the person
  sent about something else, or typed while a reply was still streaming), is not
  stopped by this agent.
- **The summary may never be shown.** The agent returns the summary to the
  model; the Brainstem shows the model's reply, and shows the raw proposal
  output only in a collapsed "agent called" panel. The agent cannot make the
  model relay the summary.
- **Other clients can manufacture later turns.** Anything that can post to the
  Brainstem's own `/chat`, including a separately adopted agent, can start a new
  request, and the kernel accepts `tool` messages in `conversation_history`
  (line 2228), so such a client can hand a model a full hash.
- **Host assumptions.** The rule relies on the host building the agent once per
  request before the model runs. A future host that built an instance for every
  tool call would let one request confirm its own proposal; a host that caches
  instances fails closed.
- **The state owner.** Anyone who can write the state folder as the person can
  forge a record or the clock; that is the person's own authority, which could
  run the SDK directly.
- **What would close it.** A host-level confirmation bound to a plan hash (the
  Brainstem's click-to-accept, RAPP Article IX) would close the first three; it
  is open question 2.

### Privacy

Everything this agent returns leaves the device. The newest Brainstem appends
every tool result to the conversation it posts to the Copilot chat-completions
API (`brainstem.py` lines 2304 and 2317 for `/chat`, 2525 and 2543 for
`/chat/stream`), and shows it in the page's collapsed "agent called" panel. So
the folder paths, plan summaries, file names and hashes it prints reach the
model provider. The agent itself opens no network connection, and its state
stays on the device.

To send less, revision 2 removed: the Brainstem's interpreter path from the
install line; the state folder's absolute path (the overview says
".brainstem/rapp_work in your home folder" or names the variable); absolute
paths from shadow and state refusals; RAPPIDs from summaries, subject lines and
verify lines; absolute discovered paths (shown under the searched folder's
name); and the full hashes of open plans. What still leaves the device, because
the person's decision or request needs it: the folders the request names or
that open plans name, the operation's details (kind, slug, owner label, world,
mode), planned file paths with sizes and 12-character hash prefixes, the full
hash of the plan just proposed or named by the request, SDK refusal codes and
messages (which can name paths), and the names of discovered skills, plugins
and neurons.

## Migration

None for the SDK. The agent is new and opt-in: a person copies one file into
`agents/` and installs the SDK. Anyone who tried the round-1 file (`0.1.0`)
keeps plain-data `/1` records that `0.2.0` lists as unreadable and never uses;
deleting that state folder is safe, because nothing the SDK applied depends on
it. If the owner later accepts section 13, the SPEC edit and its pin refresh are
one change. If the owner submits to RAR, the same bytes go through RAR's front
door (below).

## Rollback

- For a person: delete `agents/rapp_work_agent.py` (RAPP Article XIII), or move
  it out of the top level of `agents/` (any subfolder is not live in
  `brainstem-v0.6.16`). The state folder, `.brainstem/rapp_work` in the home
  folder (or `BRAINSTEM_RAPP_WORK_PATH`), is plain data and may be kept or
  removed. Nothing the SDK applied is touched.
- For the repository: revert this branch's commits and run
  `python3 tools/release_inventory.py --write`; no signed or protocol pin needs
  restoring.

## Conformance and test vectors

79 tests: `tests/test_brainstem_agent.py` (66, in-process, through the hot-load
harness, against the real SDK) and `tests/test_brainstem_agent_isolation.py` (13,
in clean `-I -S` interpreters with an audit hook and an import watcher).
`tests/brainstem_harness.py` re-implements the documented v0.6.16 hot-load
contract (flat glob, `spec_from_file_location` plus `exec_module`, a fresh module
per load, the `agents.basic_agent` shim, the instance and schema checks) without
copying kernel bytes, and turns an escaping `ModuleNotFoundError` into a failure;
several `Turn` objects model requests in flight at once.

| Required behavior | Tests |
|---|---|
| Hot-load contract | `test_agent_hot_loads_as_exactly_one_valid_tool`, `test_hot_load_validator_rejects_malformed_schemas` (6), `test_harness_flags_what_the_brainstem_would_quarantine_or_auto_install` |
| Live only at the top of `agents/`; loading and unloading are file moves | `test_only_the_top_of_agents_is_live` |
| Top level: standard library and BasicAgent only | `test_module_top_level_imports_only_cross_platform_stdlib_and_basic_agent`, `test_load_and_first_use_never_look_up_a_third_party_module` (with and without the shim), `test_the_constructor_and_the_load_have_no_side_effects` (also: building an instance reads the clock and writes nothing), `test_the_sdk_is_imported_in_exactly_one_lazy_place_and_nothing_runs_code` |
| Read-only verbs create nothing | `test_read_only_verbs_create_nothing`, `test_status_overview_and_plan_detail_are_read_only`, `test_default_state_location_is_in_the_brainstem_home_folder` |
| Scaffold, confirm, apply, SDK verify | `test_scaffold_propose_confirm_apply_then_sdk_verify_passes` (workspace, organization) |
| Update, including replacing SDK-owned files | `test_update_flow_adopts_sdk_files_on_a_legacy_workspace`, `test_an_update_that_replaces_sdk_owned_files_applies_and_explains_its_undo`, `test_a_replacing_update_is_refused_when_an_sdk_owned_file_changed`, `test_zero_change_update_is_reported_and_not_stored`, `test_reproposal_requires_a_fresh_confirmation_in_a_later_turn` |
| Migrate | `test_migrate_flow_creates_a_successor_and_preserves_the_source` |
| No apply without a later-turn confirmation | `test_apply_without_confirmation_is_refused`, `test_confirmation_in_the_proposing_turn_is_refused`, `test_a_request_that_began_before_the_proposal_cannot_confirm_it`, `test_a_request_that_begins_while_a_proposal_is_recorded_counts_as_earlier`, `test_proposing_again_restarts_the_order_for_requests_in_flight` |
| Two requests at once; the file lock | `test_concurrent_requests_are_serialized_by_the_state_lock` (four threads), `test_a_change_waits_for_the_state_lock_and_refuses_when_it_stays_busy` |
| Wrong or short hash | `test_short_wrong_and_respelled_hashes_are_refused` |
| Tampered stored plan | `test_an_edited_stored_plan_is_refused_before_the_sdk_sees_it`, `test_an_edited_plan_with_a_forged_tripwire_is_refused_by_the_sdk`, `test_corrupt_renamed_or_reordered_records_are_refused` |
| Stale preconditions refused by the SDK and reported as possibly partial | `test_a_stale_scaffold_target_is_refused_by_the_sdk_and_reported`, `test_a_stale_update_precondition_is_refused_by_the_sdk`, `test_a_changed_migration_source_is_refused_by_the_sdk`, `test_a_replacing_update_is_refused_when_an_sdk_owned_file_changed` |
| An apply that stops part-way (injected disk-full error on the SDK's third write) | `test_an_apply_that_stops_part_way_says_so_and_the_same_plan_finishes_it` |
| Refused-apply bound and history bound never lock a plan out | `test_refused_applies_count_since_the_latest_confirmation`, `test_proposing_and_withdrawing_never_fills_a_plan_history`, `test_open_plan_and_apply_attempt_bounds_are_enforced` |
| Double apply | `test_a_plan_is_never_applied_twice` |
| Undo before and after apply | `test_undo_before_apply_withdraws_a_proposal_or_a_confirmation`, `test_undo_after_apply_refuses_explains_and_writes_nothing`, `test_undo_after_a_migration_names_the_untouched_source` |
| Booby-trapped trees never execute | `test_booby_trapped_agents_skills_plugins_and_neurons_never_run`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported` (4 layouts) |
| SDK missing | `test_a_missing_sdk_is_reported_with_its_pinned_source_and_no_side_effects` |
| No network | the autouse socket guard on all 66 in-process tests; `test_a_full_flow_in_a_clean_interpreter_never_touches_network_or_processes` |
| Outputs are strings | every harness call asserts `str`; `test_hostile_arguments_always_return_a_string_and_store_nothing` (17) |
| Only the six operations | `test_only_the_six_public_sdk_operations_are_touched` (a proxy module records every attribute the agent reads) |
| Model cannot pass a plan, state or paths it should not | `test_the_model_cannot_pass_a_plan_a_state_folder_or_unknown_arguments`, `test_paths_must_be_absolute_visible_and_outside_the_agent_state`, `test_every_verb_refuses_paths_inside_the_agent_state` |
| Fewer local details to the model | `test_outputs_leave_out_home_folders_rappids_and_the_interpreter`, `test_default_state_location_is_in_the_brainstem_home_folder`, the SDK-missing test |
| Private, no-follow, bounded state | `test_state_is_private_and_symlinks_are_never_followed`, `test_open_plan_and_apply_attempt_bounds_are_enforced` |
| Standalone run | `test_standalone_execution_exits_zero_and_writes_nothing` (clean and venv interpreters) |

### The real v0.6.16 loader

The harness emulates the loader; this check used the loader itself. The
functions `load_agents`, `_load_agent_from_file`, `_validate_agent_instance`,
`_validate_agent_schema`, `_extract_package_name` and `run_tool_calls` were
compiled in memory from `rapp_brainstem/brainstem.py` at tag
`brainstem-v0.6.16` (read only; no kernel bytes were copied or changed), with
stubs only for shim registration (a documented `BasicAgent` shim, never the
Grail's `basic_agent.py`), quarantine logging, and auto-install (recorded,
never run). Results:

- Copies in `agents/experimental/`, `agents/experimental_agents/` and
  `agents/workspaces/finance/` load nothing; the copy at the top of `agents/`
  loads as `["RappWork"]` with `rapp_work` and `cryptography` blocked, passes
  `_validate_agent_instance` (`None`), answers the usage line, and triggers no
  auto-install and no quarantine.
- Through the real `run_tool_calls`, with the reviewer's interleaving (request
  B's agents loaded before request A proposes): A's own confirm and B's confirm
  are refused with `AGENT_REFUSE_NOT_LATER_TURN`, B's overview does not contain
  the full hash, B's apply is refused as not confirmed, and a request loaded
  after the proposal confirms and applies (the target is created).
- No tool result contains the home folder or the interpreter path; the state
  was created at `.brainstem/rapp_work` under the (scratch) home folder.

### Mutation proofs

Each mutation was applied to a scratch copy of this tree only (never to the
branch), both test modules were run from inside the copy on Python 3.13 (the
copy's own `src` is on pytest's path), the copy was restored, and the branch's
agent bytes were checked by SHA-256
(`5f916e5e2a0f23f8e07dded1d1f8ad7729789a12c027313ad44571b737999f07`) after the
run. Every mutation turned tests red. Unchanged gates (M1, M2, M4-M11) were
rerun against the new file; M3 was rerun and M3b-M23 are new for revision 2.

Baseline: 79 passed.

| Mutation | Result | Tests that turned red |
|---|---|---|
| M1 hash gate: accept a unique 8-64 hex prefix and resolve it | 1 failed, 78 passed | `test_short_wrong_and_respelled_hashes_are_refused` |
| M2 confirmation gate: apply a merely proposed plan | 5 failed, 74 passed | `test_a_request_that_began_before_the_proposal_cannot_confirm_it`, `test_apply_without_confirmation_is_refused`, `test_confirmation_in_the_proposing_turn_is_refused`, `test_reproposal_requires_a_fresh_confirmation_in_a_later_turn`, `test_short_wrong_and_respelled_hashes_are_refused` |
| M3 later-turn gate removed | 8 failed, 71 passed | `test_a_request_that_began_before_the_proposal_cannot_confirm_it`, `test_a_request_that_begins_while_a_proposal_is_recorded_counts_as_earlier`, `test_concurrent_requests_are_serialized_by_the_state_lock`, `test_confirmation_in_the_proposing_turn_is_refused`, `test_proposing_again_restarts_the_order_for_requests_in_flight`, `test_refused_applies_count_since_the_latest_confirmation`, `test_reproposal_requires_a_fresh_confirmation_in_a_later_turn`, `test_a_full_flow_in_a_clean_interpreter_never_touches_network_or_processes` |
| M3b clock read when confirm runs instead of when the instance was built | 8 failed, 71 passed | `test_a_request_that_began_before_the_proposal_cannot_confirm_it`, `test_a_request_that_begins_while_a_proposal_is_recorded_counts_as_earlier`, `test_concurrent_requests_are_serialized_by_the_state_lock`, `test_confirmation_in_the_proposing_turn_is_refused`, `test_proposing_again_restarts_the_order_for_requests_in_flight`, `test_refused_applies_count_since_the_latest_confirmation`, `test_reproposal_requires_a_fresh_confirmation_in_a_later_turn`, `test_a_full_flow_in_a_clean_interpreter_never_touches_network_or_processes` |
| M3c round-1 rule: refuse only the instance that proposed (any other instance may confirm) | 4 failed, 75 passed | `test_a_request_that_began_before_the_proposal_cannot_confirm_it`, `test_a_request_that_begins_while_a_proposal_is_recorded_counts_as_earlier`, `test_proposing_again_restarts_the_order_for_requests_in_flight`, `test_refused_applies_count_since_the_latest_confirmation` |
| M4 stored-plan tripwire removed | 1 failed, 78 passed | `test_an_edited_stored_plan_is_refused_before_the_sdk_sees_it` |
| M5 apply re-plans instead of sending the confirmed stored plan and hash | 9 failed, 70 passed | `test_a_changed_migration_source_is_refused_by_the_sdk`, `test_a_replacing_update_is_refused_when_an_sdk_owned_file_changed`, `test_a_stale_scaffold_target_is_refused_by_the_sdk_and_reported`, `test_a_stale_update_precondition_is_refused_by_the_sdk`, `test_an_apply_that_stops_part_way_says_so_and_the_same_plan_finishes_it`, `test_an_edited_plan_with_a_forged_tripwire_is_refused_by_the_sdk`, `test_open_plan_and_apply_attempt_bounds_are_enforced`, `test_scaffold_propose_confirm_apply_then_sdk_verify_passes[organization]`, `test_scaffold_propose_confirm_apply_then_sdk_verify_passes[workspace]` |
| M6 import rapp_work at module top | 10 failed, 69 passed | `test_a_missing_sdk_is_reported_with_its_pinned_source_and_no_side_effects`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[agents/rapp_work.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[agents/rapp_work/__init__.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[rapp_work.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[rapp_work/__init__.py]`, `test_load_and_first_use_never_look_up_a_third_party_module[False]`, `test_load_and_first_use_never_look_up_a_third_party_module[True]`, `test_module_top_level_imports_only_cross_platform_stdlib_and_basic_agent`, `test_standalone_execution_exits_zero_and_writes_nothing[True]`, `test_the_constructor_and_the_load_have_no_side_effects` |
| M6b import fcntl at module top | 1 failed, 78 passed | `test_module_top_level_imports_only_cross_platform_stdlib_and_basic_agent` |
| M7 shadow check removed | 4 failed, 75 passed | `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[agents/rapp_work.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[agents/rapp_work/__init__.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[rapp_work.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[rapp_work/__init__.py]` |
| M8 read-only overview creates the state folder | 7 failed, 72 passed | `test_default_state_location_is_in_the_brainstem_home_folder`, `test_read_only_verbs_create_nothing`, `test_a_missing_sdk_is_reported_with_its_pinned_source_and_no_side_effects`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[agents/rapp_work.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[agents/rapp_work/__init__.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[rapp_work.py]`, `test_a_rapp_work_inside_the_brainstem_folders_is_never_imported[rapp_work/__init__.py]` |
| M9 control and invisible characters accepted | 1 failed, 78 passed | `test_paths_must_be_absolute_visible_and_outside_the_agent_state` |
| M10 calls execute instead of the six operations | 7 failed, 72 passed | `test_a_plan_is_never_applied_twice`, `test_an_edited_plan_with_a_forged_tripwire_is_refused_by_the_sdk`, `test_every_verb_refuses_paths_inside_the_agent_state`, `test_only_the_six_public_sdk_operations_are_touched`, `test_read_only_verbs_create_nothing`, `test_scaffold_propose_confirm_apply_then_sdk_verify_passes[organization]`, `test_scaffold_propose_confirm_apply_then_sdk_verify_passes[workspace]` |
| M11 undo after apply deletes the created folder | 3 failed, 76 passed | `test_outputs_leave_out_home_folders_rappids_and_the_interpreter`, `test_undo_after_apply_refuses_explains_and_writes_nothing`, `test_a_full_flow_in_a_clean_interpreter_never_touches_network_or_processes` |
| M12 status overview prints the full hash of open plans | 2 failed, 77 passed | `test_a_request_that_began_before_the_proposal_cannot_confirm_it`, `test_status_overview_and_plan_detail_are_read_only` |
| M13 state-folder path check removed for every verb | 2 failed, 77 passed | `test_every_verb_refuses_paths_inside_the_agent_state`, `test_paths_must_be_absolute_visible_and_outside_the_agent_state` |
| M13b state-folder check exact spelling only (no case fold, no symlink resolution) | 1 failed, 78 passed | `test_every_verb_refuses_paths_inside_the_agent_state` |
| M13c round-1 rule: state-folder check only for propose (read-only verbs unchecked) | 2 failed, 77 passed | `test_every_verb_refuses_paths_inside_the_agent_state`, `test_paths_must_be_absolute_visible_and_outside_the_agent_state` |
| M14 runtime and write errors get the withdraw-and-propose advice | 1 failed, 78 passed | `test_an_apply_that_stops_part_way_says_so_and_the_same_plan_finishes_it` |
| M15 refused applies counted over the plan's life (a new confirmation does not reset them) | 1 failed, 78 passed | `test_refused_applies_count_since_the_latest_confirmation` |
| M16 a new confirmation is accepted in the request that saw the refusals | 1 failed, 78 passed | `test_refused_applies_count_since_the_latest_confirmation` |
| M17 proposing again appends instead of restarting the history | 3 failed, 76 passed | `test_proposing_again_restarts_the_order_for_requests_in_flight`, `test_proposing_and_withdrawing_never_fills_a_plan_history`, `test_reproposal_requires_a_fresh_confirmation_in_a_later_turn` |
| M18 overview names the state folder's absolute path | 2 failed, 77 passed | `test_default_state_location_is_in_the_brainstem_home_folder`, `test_outputs_leave_out_home_folders_rappids_and_the_interpreter` |
| M19 scaffold summary shows the new RAPPID | 3 failed, 76 passed | `test_outputs_leave_out_home_folders_rappids_and_the_interpreter`, `test_scaffold_propose_confirm_apply_then_sdk_verify_passes[organization]`, `test_scaffold_propose_confirm_apply_then_sdk_verify_passes[workspace]` |
| M20 discovered paths shown as absolute device paths | 1 failed, 78 passed | `test_outputs_leave_out_home_folders_rappids_and_the_interpreter` |
| M21 clock written before the record (commit order swapped) | 1 failed, 78 passed | `test_a_request_that_begins_while_a_proposal_is_recorded_counts_as_earlier` |
| M22 withdrawal after refused applies no longer warns | 1 failed, 78 passed | `test_a_replacing_update_is_refused_when_an_sdk_owned_file_changed` |
| M23 an unreadable clock reading counts as a later turn | 1 failed, 78 passed | `test_state_is_private_and_symlinks_are_never_followed` |

### RAR's own tooling, run read-only on a scratch copy

Against RAR `main` `ecf5f52312cf083eaedf5e0aa8782debc7f0af4b` (1,700 registered
agents), with the file placed at `agents/@kody-w/rapp_work_agent.py` in a scratch
clone (RAR itself was not modified and nothing was pushed or filed):

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
- `scripts/check_near_duplicates.py --base HEAD^` after a local scratch commit:
  "OK 1 changed agent(s) carry no undeclared rhymes".
- RAR's `tests/test_brainstem_hotload.py` child, run on a flattened copy with
  `rapp_work` (and `cryptography`) blocked: loads `["RappWork"]`.
- sha256-lf-v1 of the file: `5f916e5e2a0f23f8e07dded1d1f8ad7729789a12c027313ad44571b737999f07`
  (77,318 bytes, LF only).

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
- **Fail-closed.** Every check refuses when unsure; no record is pruned, and
  nothing is repaired, retried with another plan, deleted or installed.

## How to try

1. Use the newest Brainstem (`brainstem-v0.6.16`) from the installer.
2. Install the SDK into the Brainstem's own Python, from the pinned source (git
   is required; pip fetches the SDK's declared dependency `cryptography` and the
   build tools by their own names, and never looks up `rapp-work` on an index):

   ```bash
   "$HOME/.brainstem/venv/bin/python" -m pip install \
     "rapp-work @ git+https://github.com/kody-w/rapp-work@29ead23b21645f8d7682ee00414930ffa9ce0ca6"
   ```

3. Fetch the agent at commit
   `52f528da5bc038e9021f3ed32c971746a4f2449a` and check its hash (the digest
   is what identifies the bytes; if the branch is merged, the same file on
   `main` has the same digest):

   ```bash
   curl -fsSLO https://raw.githubusercontent.com/kody-w/rapp-work/52f528da5bc038e9021f3ed32c971746a4f2449a/integrations/brainstem/agents/rapp_work_agent.py
   shasum -a 256 rapp_work_agent.py
   # 5f916e5e2a0f23f8e07dded1d1f8ad7729789a12c027313ad44571b737999f07
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
   - `confirm` and `apply`, in a new message sent after the reply with the
     summary has arrived: "confirm <the full 64-character hash>".
   - `undo`: "Withdraw plan <full hash>." before apply; after apply the same
     request returns the explanation and changes nothing.
6. To unload it, move `agents/rapp_work_agent.py` into any subfolder of
   `agents/` (for example `agents/experimental/`), or delete it; the next
   message no longer offers it.
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
{"schema":"rar-change-request/1.0","request_id":"req_<uuid>","idempotency_key":"req_<uuid>","operation":"create","resource":{"kind":"agent","id":"@kody-w/rapp_work_agent"},"preconditions":{"if_none_match":"*"},"payload":{"source":{"media_type":"text/x-python","encoding":"utf-8","url":"https://raw.githubusercontent.com/kody-w/rapp-work/52f528da5bc038e9021f3ed32c971746a4f2449a/integrations/brainstem/agents/rapp_work_agent.py","sha256":"sha256:5f916e5e2a0f23f8e07dded1d1f8ad7729789a12c027313ad44571b737999f07"}},"client":{"name":"manual","version":"1"}}
```

RappWork 0.2.0 (Frontier, newest Brainstem channel brainstem-v0.6.16; not in
the LTS brainstem-v0.6.9 scope): reaches private RAPP Work workspaces through
the RAPP Work SDK's six public operations and applies only a plan confirmed by
its exact SHA-256 in a later request than the plan's proposal. It cannot see
the person's words, so it enforces that order, not consent. Reference and
tests: kody-w/rapp-work proposal 0017. The top level imports only the standard
library and BasicAgent; it needs the RAPP Work SDK installed from its pinned
source to do anything.
````

## Related proposals

Read at each branch's pushed head on 2026-09-25 (read only). To check the
agent against each of them, this branch's 79 agent tests were run on a scratch
copy of this tree whose `src/`, `protocols/` and `vendor/` were replaced by that
branch's; all 79 pass against every one.

| Proposal (branch, head) | What it changes that this agent touches | This agent `0.2.0` |
|---|---|---|
| 0002, G2: `experimental/gap-g2-move-action` @ `8b3c361` | `update` gains the optional closed inputs `moves` and `inverse_of`, which plan a `rapp-work-move-plan/1` of verified no-replace renames under a plan-bound move-recovery marker, and its inverse. Every existing entry a move names must be spelled exactly as stored (`REFUSE_PATH_SPELLING`), so a plan and its inverse restore every name exactly. Its own example unloads an agent by moving it from the top of `agents/` into `agents/experimental/`. | Sends neither input and never builds a move plan, so nothing depends on G2 (SDK 1.0.0 refuses both inputs as unknown). It is the SDK path to honest undo after apply for plans made only of moves, and to loading and unloading agents by moving files. A later agent version could adopt it only by opting in when the installed SDK's API document lists `moves`: accept the move-plan shape, list its moves in the summary, pass every path exactly as the person gave it (the agent case-folds paths only to refuse them, never to rewrite them), and offer the inverse plan through the same propose, confirm and apply gate. |
| 0003, G3: `experimental/gap-g3-agent-discovery` @ `3200a27` | `discover` gains the optional closed input `agents`; with `agents: true` the result adds an `agents` member of inert `rapp-work-discovered-agent/1` records for `*_agent.py` files, parsed and never imported, with `live` marking the top level of `agents/`. Without it, results are unchanged apart from the embedded API document. | Never sends `agents`, because SDK 1.0.0 refuses unknown discover inputs; its discover output keeps saying single-file agents are not listed. Degrades gracefully; nothing depends on G3. A later version can send `agents: true` when the installed SDK lists it and show those records, still as data. |
| 0007, G7: `experimental/gap-g7-instruction-inventory` @ `68b549c` | `verify` gains the optional input `require_instruction_inventory` and `instruction_inventory` members; a tree integrated by SDK 1.0.0 verifies with the subject status `verified-without-instruction-inventory`; planned updates add `instruction_review`; an apply whose closing verification refuses reports `updated-unverified`; scaffold and migration plans gain the inventory file; a missing SDK-owned file is refused as `REFUSE_MANAGED_DRIFT`. | Never sends `require_instruction_inventory`. Its verify line prints the subject's own status and its subject line prints every subject member except `rappid` and `root`, so the new status and members show through; an `updated-unverified` apply is recorded as applied (its effects happened) and followed by a read-only verify; `REFUSE_MANAGED_DRIFT` gets the changed-precondition advice. It does not yet show `instruction_review` (the person sees each planned file, including instruction files, but not the review's classification): a later version should. Degrades gracefully; the two tests that used to assert SDK 1.0.0 file counts now take the count from the stored plan. |
| 0004, G4: `experimental/gap-g4-migration-successors` @ `be1772b` | `migrate` gains the opt-in `successor: "pointer-only"` and the planning-only `hive`; without `successor`, `migrate`, `update` and `verify` are unchanged. | Sends neither; its migrations keep the 1.0.0 path, and adopting pointer-only successors would be an explicit later change with its own summary. No dependency. |
| 0006, G6: `experimental/gap-g6-owner-succession` @ `7af9cbb` | Adds the read-only `rapp_work.registry` submodule (outside the six-operation JSON API) and owner succession in the `rapp-hive/1` reference. | Must not and does not use it: the agent reads only the six operations (`test_only_the_six_public_sdk_operations_are_touched`). No behavioral interaction. |
| 0011, G11: `experimental/gap-g11-workspace-index` @ `e3909b3` | Documentation only today: names the pointer-only Organization the "workspace index" and plans its migration over releases 1.1.0 to 1.3.0. | Says "organization" and offers `kind: organization`, SDK 1.0.0's words; a later agent version should follow the new name when the SDK writes it. No code interaction now. |

**Recommended merge order.** Merge the SDK-changing proposals first, in the
order their own reviews need (G2, G3, G7 and G4 all change
`src/rapp_work/api.py`; G6 changes the `rapp-hive/1` reference; G11 is
documentation and can go at any time), and merge 0017 last: rebase it on that
`main`, move its pinned SDK commit (`SDK_SOURCE_COMMIT` and the install line)
to the merged commit, rerun its tests and mutations, and re-issue the digest in
the RAR text. The agent depends on none of them and degrades gracefully against
SDK 1.0.0 and against each branch, so merging it earlier is possible; then each
later SDK merge must rerun its tests. Every one of these branches edits
`CHANGELOG.md` and `RELEASE-INVENTORY.json`, so each merge regenerates the
inventory; G6 also edits `MANIFEST.in`, on a different line from this branch.

## Open questions for the owner

1. Accept section 13 into `rapp-work-sdk/1` (recommended: additive, no token
   move), or register a separate client profile instead?
2. Is "a request that began after the plan's latest proposal was recorded" the
   right confirmation boundary for the newest channel, or should a later
   Brainstem release offer a host-level confirmation that agents can bind a plan
   hash to (RAPP Article IX click-to-accept), which would close the residual
   risks above?
3. Keep the reference in `kody-w/rapp-work` and, later, submit the same bytes to
   RAR as Frontier? Or keep it out of RAR's default branch until it graduates?
4. Re-pin `RAR_REVISION` in a later newest-channel Brainstem release so its
   store panel can offer the agent?
5. Is `.brainstem/rapp_work` in the home folder, with `BRAINSTEM_RAPP_WORK_PATH`,
   the right state location (RAPP Article XVI's shape)?
6. After G2, G3 and G7 are accepted, adopt them in a later agent version:
   inverse-move undo and file-move loading, agent listings in discover, and the
   instruction review in update summaries (see "Related proposals").
7. Promote the agent from `0.2.0` Frontier after a real week of use?

## Owner actions needed

- Accept or refuse this proposal. If accepted: merge the branch (the owner's
  merge; see "Recommended merge order"), apply insertions A and B to
  `protocols/rapp-work-sdk/1/SPEC.md`, refresh its SHA-256 in
  `protocols/index.json` and `src/rapp_work/data/profiles.json`, rerun
  `python3 tools/release_inventory.py --write`, and choose the release version
  (1.1.0 proposed).
- Decide the RAR submission and, if yes, file the text above from the `kody-w`
  account and approve the staged revision.
- Optionally re-pin RAR in a later newest-channel Brainstem release.
- Organism: G17 stays `proposed` (relayed by the lead).

## Review round 1 disposition

Round 1 (0 high, 4 medium, 5 low, plus lead notes) reviewed commit `c75b4d7`.
Revision 2 answers every item; the agent went from 73,033 bytes (SHA-256
`fba74268...5046643bd509`) to 77,318 bytes (SHA-256 `5f916e5e...b737999f07`),
and the tests from 66 to 79.

| # | Finding | Disposition |
|---|---|---|
| 1 (medium) | "Later turn" meant only "a different agent instance", and v0.6.16 runs requests at once | Fixed. A persisted logical clock orders events under the state lock; each instance reads it when built; confirm needs a reading at least the plan's latest event. Gate 4 and section 13 item 4 define "later turn" in these terms; "Residual risks" states what stays open. The reviewer's repro is `test_a_request_that_began_before_the_proposal_cannot_confirm_it`; three more tests cover re-proposal, a request that begins mid-commit, and four threads. Mutations M3, M3b, M3c (the round-1 rule), M21 and M23 turn them red. |
| 2 (medium) | The model can confirm a plan the person never saw; the text claimed more than was enforced | Fixed where it can be, and stated where it cannot. The overview names open plans by 12-character prefixes (M12), so a full hash comes only from a proposal's output or from outside the agent. Every over-claim was removed from the agent's docstring and runtime text, the manifest, the README, the CHANGELOG, the RAR text and this proposal. The residual-risk section now names every way a model can still confirm what the person did not approve. |
| 3 (medium) | "Nothing leaves the device" was false | Fixed. "Privacy" now says plainly that every tool result goes to the model provider, cites the kernel lines, and lists what the agent stopped sending (interpreter and state paths, RAPPIDs, absolute discovered paths, full hashes of open plans) and what it still sends and why. Tested by `test_outputs_leave_out_home_folders_rappids_and_the_interpreter`; mutations M18-M20. |
| 4 (medium) | After a failed apply the agent said nothing changed and advised undo and re-propose, which strands an update | Fixed. Apply refusals are reported as possibly partial; `REFUSE_RUNTIME` and `REFUSE_WRITE_VERIFY` send the person back to the same hash; `REFUSE_RECOVERY_BINDING` points to the earlier plan; only other codes suggest withdrawing and proposing again. Withdrawal after refusals warns. Tested with an injected disk-full error on the SDK's third write (`test_an_apply_that_stops_part_way_says_so_and_the_same_plan_finishes_it`); mutations M14, M22. |
| 5 (low) | Refused applies counted over the record's life; history-full advice was unworkable | Fixed. Refusals count since the latest confirmation; a new confirmation in a later turn resets them (M15, M16), and the message names that recovery. Re-proposing restarts the history, which is now at most 11 events and can never fill (M17). |
| 6 (low) | The state-folder check applied only to propose | Fixed. `_path_input` refuses state paths for every verb, case-insensitively and through symlinks (`test_every_verb_refuses_paths_inside_the_agent_state`; M13, M13b, M13c). |
| 7 (low) | The replacing update path and the file lock were untested | Fixed. Two replacing-update tests (apply and its undo explanation; a changed SDK-owned file) and two lock tests (four concurrent proposals; a held lock that makes a change wait, then refuse). |
| 8 (low) | The home rationale did not consider RAPP's `rapp_brainstem/agents/experimental/` | Fixed: a new row in "Home"; the conclusion holds. |
| 9 (low) | Runtime text named internal gap ids and an unaccepted branch | Fixed. The agent's bytes name no gap id or branch; such references live only in this proposal ("Related proposals"). |
| Lead | "Related proposals" section; keep the file small | Added "Related proposals" (read at the siblings' pushed heads, with a test run against each) and a merge order. The file grew by 4,285 bytes for the new gates and honest texts; the docstring was shortened to offset part of it. |

## References

- `kody-w/rapp-work` `main` `29ead23b21645f8d7682ee00414930ffa9ce0ca6` (and
  `0da52a6`, which changes no SDK file): `protocols/rapp-work-sdk/1/SPEC.md`
  sections 2, 3, 4, 11, 12; `src/rapp_work/api.py`; `src/rapp_work/workspace.py`
  (`apply_update`, `apply_scaffold`); `src/rapp_work/migration.py`
  (`apply_migration`); `src/rapp_work/discovery.py`; `docs/API.md`;
  `AGENTS.md`; `CONTRIBUTING.md`; `docs/RELEASE.md`.
- `kody-w/rapp-work` branches, read only: `experimental/gap-g2-move-action`
  `8b3c361`, `experimental/gap-g3-agent-discovery` `3200a27`,
  `experimental/gap-g7-instruction-inventory` `68b549c`,
  `experimental/gap-g4-migration-successors` `be1772b`,
  `experimental/gap-g6-owner-succession` `7af9cbb`,
  `experimental/gap-g11-workspace-index` `e3909b3`.
- `kody-w/rapp-installer` tag `brainstem-v0.6.16`
  (`5fbde1776a72715935c3d597a9ddfce28a04032b`): `rapp_brainstem/brainstem.py`
  lines 472, 1513, 1524, 1554, 1640, 1671, 1691, 1794, 1810, 1818, 1832, 1834,
  2176, 2209, 2228, 2271, 2304, 2317, 2444, 2525, 2543, 3465;
  `rapp_brainstem/index.html` lines 1335, 1882, 2134, 2353, 2495, 2504,
  2595-2600, 2612; `rapp_brainstem/CLAUDE.md`; `rapp_brainstem/start.sh`.
- `kody-w/RAPP` `main` `8afc9733e20ccf7e579a58028c29ab9c207087fa`:
  `CONSTITUTION.md` Articles III.5, III.7, IX, XIII, XVI, XVII, XXVII, XXVIII,
  XXIX, XXXI; release tags `brainstem-v0.10.0` and `brainstem-v0.12.1`
  (`rapp_brainstem/brainstem.py`, the recursive loader's skipped folders).
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
