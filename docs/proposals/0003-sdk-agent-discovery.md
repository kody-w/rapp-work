# Proposal 0003: SDK discovery records single-file agents as inert data

| | |
|---|---|
| Status | **Draft, not accepted.** Branch `experimental/gap-g3-agent-discovery`. Nothing is merged, released, or activated. |
| Gap | **G3**: SDK discovery misses `*_agent.py`. SDK discovery does not see single-file agents named `*_agent.py`; the fix records them as inert data that never runs. |
| Home spec | `rapp-work-sdk/1` §11 (Inert compatibility), new §11.1 (Single-file agents) |
| Base | `kody-w/rapp-work` `main` at `29ead23b21645f8d7682ee00414930ffa9ce0ca6` (SDK 1.0.0) |
| Blocks | Workspaces (organism layer 4) |
| Intended release | The next minor SDK release (1.1.0), or the release the owner bundles accepted `rapp-work-sdk/1` proposals into. This branch does not change the package version or `SDK_VERSION`. |

## 1. Context: what is true today

1. **Only top-level agents are live in every released Brainstem.** In
   `kody-w/rapp-installer` at tag `brainstem-v0.6.9` (the LTS channel),
   `rapp_brainstem/brainstem.py` sets `AGENTS_PATH` to the Brainstem
   directory's `agents` child by default (line 67). `load_agents()` is a flat
   glob of `AGENTS_PATH/*_agent.py` (lines 1202–1205).
   `_load_agent_from_file` (from line 1021) imports each file with
   `importlib` and `exec_module` (line 1041). It registers every class that
   has `perform`, except `BasicAgent`, `object`, and names that start with `_`
   (lines 1044–1048). At tag `brainstem-v0.6.16` (the newest channel) the glob
   is the same, now sorted (lines 1832–1835). Class selection also requires
   `cls.__module__ == mod.__name__` (line 1666). The HTTP API refuses to delete
   or replace `basic_agent.py`, "the shared base class" (lines 3025–3028 and
   3055–3060). Python's `glob` skips names that begin with `.` and is
   case-sensitive on POSIX. It does match `basic_agent.py`, so the kernel
   imports the base-class file on every sweep but registers no agent from it.
   The organism records this as the invariant "Only top-level
   `agents/*_agent.py` files are live. Every folder is organization."
2. **The SDK does not see those files.** At `29ead23`,
   `src/rapp_work/discovery.py` `discover_roots` (lines 187–249) classifies
   regular files by exact name only (lines 220–225): `SKILL.md` becomes
   `rapp-work-discovered-skill/1`, `rapp-work-plugin.json` becomes
   `rapp-work-discovered-plugin/1`, and `agent.py` becomes
   `rapp-work-portable-neuron/1`. A file named `hello_agent.py` matches none of
   these, so discovery omits it without saying so. `src/rapp_work/api.py`
   `_discover` (lines 174–193) takes the closed input `{roots, max_entries}`.
3. **The accepted rule.** `rapp-work-sdk/1` §11 (SPEC lines 146–154 at
   `29ead23`): "Portable Neurons, discovered plugins, and project skills are
   untrusted data. Discovery may parse bounded metadata and Python syntax, but
   MUST NOT import, execute, install, enable, or grant authority to discovered
   code."
4. **The canonical parent.** `rapp-work/1` §3 (`kody-w/rapp-1`
   `protocols/rapp-work/1/SPEC.md`; packaged mirror
   `src/rapp_work/data/rapp-work-1-SPEC.md`, pinned by `RAPP_WORK_PIN.json` at
   `591e014`) says catalogs are discovery, not authority. Catalog item `kind`
   is the closed set `plugin`, `skill`, `static-api`, and `portable-neuron`.
   Portable Neurons are accepted only as typed inert data. §10 item 7 requires
   implementations to "treat Portable Neurons and discovery entries as inert,
   non-authoritative data".
5. **How RAR reads agents.** `kody-w/RAR` `build_registry.py`
   `extract_manifest` (from line 84 at `ecf5f52`) extracts the
   `__manifest__` dictionary (`schema: "rapp-agent/1.0"`, RAR `CONSTITUTION.md`
   Article IV) through `ast.parse` and `ast.literal_eval`, without importing the
   file. It also calls `compile(source, path, "exec")` (line 93) as a stricter
   publication gate.
6. **Who needs it.** The Brainstem app shows `agents/` as a workspace root and
   explains agents without running them. The future Brainstem SDK agent (gap
   G17) would reach agents through `discover`. Today neither can list agents
   through the SDK.

## 2. Proposed change

### 2.1 Normative text

This branch replaces `rapp-work-sdk/1` §11 in
`protocols/rapp-work-sdk/1/SPEC.md`. The first paragraph gains "single-file
agents". The second paragraph is unchanged. Section 11.1 is new. No other
section changes.

Current text at `29ead23`:

```markdown
## 11. Inert compatibility

Portable Neurons, discovered plugins, and project skills are untrusted data.
Discovery may parse bounded metadata and Python syntax, but MUST NOT import,
execute, install, enable, or grant authority to discovered code.

The historical workspace-manager and Private Hive implementations remain
available only through explicit SDK compatibility wrappers and deprecated
legacy paths. Those wrappers do not broaden their profile claims.
```

Proposed text, exactly as committed on this branch:

```markdown
## 11. Inert compatibility

Portable Neurons, discovered plugins, project skills, and single-file agents
are untrusted data. Discovery may parse bounded metadata and Python syntax, but
MUST NOT import, execute, install, enable, or grant authority to discovered
code.

The historical workspace-manager and Private Hive implementations remain
available only through explicit SDK compatibility wrappers and deprecated
legacy paths. Those wrappers do not broaden their profile claims.

### 11.1 Single-file agents

A single-file agent is a Brainstem agent file: a regular file whose name ends
with the exact, case-sensitive suffix `_agent.py`. For each one it can read
safely, `discover` MUST record one `rapp-work-discovered-agent/1` object in
the `agents` member of its result, in code-point order of `path` and then
`root`; a file reached from several scanned roots yields one record per root.
`discover` MUST omit `agents` when it records none, so a tree without such a
file yields the same result bytes as before this section. Agent files count
toward the same `max_entries` bound as every other entry. No existing record
shape changes.

A record has exactly these members:

| Member | Value |
|---|---|
| `schema` | `rapp-work-discovered-agent/1` |
| `path`, `root` | Absolute lexical paths, with no link resolved, of the file and of the scanned root it was found under |
| `bytes`, `sha256` | Exact byte length and SHA-256 of the file |
| `language` | `python` |
| `role` | `base-class` for `basic_agent.py`, the shared base class; otherwise `agent` |
| `live` | Boolean, defined below |
| `syntax` | `parsed`, `invalid`, or `unsupported-encoding` |
| `classes` | When `parsed`: the unique names, in code-point order, of classes defined directly in the module body whose base list names `BasicAgent`, as a name or as an attribute; otherwise `null` |
| `manifest_status` | When `parsed`: `absent`, `literal`, `not-literal`, `ambiguous`, or `over-limit`; otherwise `null` |
| `manifest` | When `literal`: an object with exactly `schema`, `name`, `version`, `display_name`, and `description`; otherwise `null` |
| `executed` | `false` |
| `authority` | `discovery-only` |
| `treatment` | `inert-data` |

`live` is `true` exactly when the file name does not begin with `.` and the
file is directly inside the scanned root's live directory: the root itself
when the root's final path component is `agents`, otherwise the root's child
directory `agents`. This mirrors the Brainstem kernel, whose `load_agents()`
loads only the top level of its agents directory through a flat `*_agent.py`
glob; every subfolder is organization. `live` describes position only. The SDK
never loads the file, and `live` does not claim that a Brainstem exists, uses
that directory, or would load the file successfully.

Discovery reads the source with a descriptor-relative no-follow read of at
most 1 MiB. The source is `unsupported-encoding` when its bytes, after one
optional UTF-8 byte-order mark, are not strict UTF-8, or when an encoding
declaration on its first or second line names anything other than UTF-8
(`utf-8`, `utf8`, or a `utf-8-` prefix, compared case-insensitively with `_`
read as `-`). It is `invalid` when it contains a NUL code point or when the
Python parser rejects it or reports it too complex. Otherwise it is `parsed`:
the running interpreter's parser built a syntax tree. `parsed` does not claim
that the module compiles, imports, or runs, and the host's warning filters do
not change the verdict.

`manifest_status` describes the name `__manifest__`, decided in this order.
It is `absent` when nothing binds that name. It is `ambiguous` when anything
other than exactly one direct module-body assignment (`__manifest__ = ...` or
`__manifest__: T = ...`) binds, rebinds, deletes, or item- or
attribute-assigns it, such as a second assignment, an assignment inside a
block, a definition, or an import alias, or when that assignment's value is a
dictionary display that repeats a constant top-level key (compared as Python
values). It is `not-literal` when the value is not a dictionary display built
only from constants, signed numeric constants, and nested lists, tuples, sets,
and dictionaries with constant keys. It is `over-limit` when the display has
more than 4,096 nodes or a depth over 16. Otherwise it is `literal`, except
that a display that cannot be constructed as a value, such as a set that
contains a list, is `not-literal`. Discovery MAY evaluate a display that
passed every earlier test, and only as a literal; it MUST NOT evaluate any
other expression. Each `manifest` member
is the same-named string value when that value is a string of at most 1,024
characters containing no surrogate or noncharacter code point, and `null`
otherwise. The fields are the file's literal text, not the value a running
module would hold.

A file that cannot be read safely produces a refusal and no record: a symbolic
link (`REFUSE_SYMLINK`), a non-regular or hard-linked entry
(`REFUSE_PATH_TYPE`), a file over 1 MiB (`REFUSE_FILE_LIMIT`), a file that
changes while it is read (`REFUSE_FILE_RACE`), an unreadable file
(`REFUSE_PATH_UNSAFE`), or a path that is not valid UTF-8
(`REFUSE_AGENT_NAME`, reported with an escaped path). A file whose module body
defines more than 256 such classes, or such a class with a name longer than
256 characters, is refused with `REFUSE_AGENT_METADATA`. Any other inspection
failure is likewise a refusal with no record.

A record is discovery, not authority. It does not load, enable, install, or
authorize an agent. It is not a `rapp-work/1-catalog` item, and the canonical
catalog kinds are unchanged.
```

### 2.2 What this means in practice (non-normative)

- Scan a Brainstem directory or its `agents/` folder with `discover`. Every
  `*_agent.py` comes back as one record: its hash, whether the parser accepts
  it, its `BasicAgent` subclass names, and five of the manifest fields RAR
  defines (`schema`, `name`, `version`, `display_name`, `description`),
  when the manifest is a plain literal.
- `live: true` means "top level of the live `agents/` folder", which is where
  the kernel's flat glob would pick the file up. Files in subfolders are
  `live: false` (organization). So is anything outside the live folder, or a
  hidden name. `basic_agent.py` is `role: "base-class"`.
- Nothing is imported, compiled to bytecode, or executed. A file that could
  not be read safely appears only as a refusal.
- A tree with no `*_agent.py` file produces exactly the bytes it produced
  before.

## 3. Token and compatibility analysis

### 3.1 Every token this touches

| Token or surface | Change |
|---|---|
| `rapp-work-result/1` envelope (seven members) | None |
| `rapp-work-discovered-skill/1`, `rapp-work-discovered-plugin/1`, `rapp-work-portable-neuron/1` | None. Same code path, same bytes |
| `rapp-work-static-api/1` (`src/rapp_work/data/api.json`) | None. Its bytes are embedded in every `status` and `discover` result, so they are deliberately untouched |
| Closed `discover` input `{roots, max_entries}` | None |
| `rapp-work-sdk/1` integration record (`protocols/rapp-work-sdk/1/schema.json`) | None. Same bytes, same hash `a931fe3e…9029` |
| `rapp-work-sdk/1` specification text | §11 revised; hash pins updated (3.4) |
| `rapp-work-discovered-agent/1` | **New** token. It has never denoted any other shape |
| `rapp-work/1-catalog` and its closed `kind` set | None. Agent records are not catalog items |
| RAPP/1 canonicalization, hashes, RAPPIDs, Frame, wire, Egg | None |

### 3.2 How the discover result grows (Constitution Article 2)

Article 2 says a versioned token "must never denote two shapes", and any
revision that changes a key set, a field grammar, or a hash rule moves the
token. The discover `result` object carries no label of its own. The accepted
specification does not list its members. Its members are arrays of records,
and each record carries its own versioned token. It is closed in practice:
today it has exactly nine members (`api`, `executed`, `network`, `neurons`,
`plugins`, `refusals`, `roots`, `skills`, `status`). Five ways to add a record
kind were considered:

| Option | Effect on existing labels and bytes | Verdict |
|---|---|---|
| (a) Always add `agents: []` | Changes every discover result, including trees with no agents | Rejected: fails the byte-identity requirement |
| (b) Add `agents` only when at least one new-token record exists | No existing token changes shape. Every tree without a regular `*_agent.py` file keeps identical bytes. Only trees that contain agent files, which discovery used to omit silently, gain one member holding only new-token records | **Chosen** |
| (c) Put agent records into `neurons` or `refusals` | Mixes kinds inside an existing record array, which changes that array's grammar in place | Rejected: violates Article 2 |
| (d) New opt-in input member, for example `agents: true` | Widens the closed discover input and changes `rapp-work-static-api/1`, whose bytes appear in every `status` and `discover` result. Every existing output would change | Rejected: more disruptive than (b) for every caller |
| (e) Mint `rapp-work-sdk/2` or `rapp-work-result/2` | Lawful, but moves every consumer to a new label to add one inert record kind | Held in reserve (Open question 1) |

Option (b) is growth by registration (Article 4): a new record kind on the same
envelope. It adds no new envelope, operation, input, or door. No existing
token's key set, field grammar, or hash rule changes. Every old-token artifact
keeps its exact bytes. The observable changes are listed in 3.5. The branch
gates them by scoping them to the new token and by omitting the member when it
is empty (section 8).

### 3.3 Other articles

- **Article 4.** A new record kind; no new operation, envelope, or door.
- **Article 18.** Canonicalization, hashes, the RAPPID grammar, the
  eleven-key Frame, wire forms, and the Egg container are untouched.
- **Article 10.** Output goes through the SDK's existing pinned canonicalizer
  (`rapp_work._json.canonical_text`). No reference primitive is re-typed.
- **Articles 6 and 7.** No owner authority is read or written. No identity is
  derived from a name. `root` and `path` are locators, not identities.
- **Article 8.** No oracle is skipped, muted, or weakened. All 169 existing
  tests pass unchanged, and every existing test file is byte-identical.

### 3.4 Pins

- `protocols/rapp-work-sdk/1/SPEC.md` SHA-256 moves from
  `cf64a90f44427728966ba142d6ef42cdd31f08ad465badf86a93c969f0cb8ef1` to
  `1e7022905e1e028ef684e5d4edaf71aa555d08e1e1bf82572fbe81b1308f6e7d` in both
  `protocols/index.json` and `src/rapp_work/data/profiles.json`. The index's
  `generated_utc` is refreshed, following the precedent in `a35db4d`.
- `RELEASE-INVENTORY.json` is regenerated with `tools/release_inventory.py
  --write`.
- These are untouched: `registry.json` and its signature, root `SPEC.md`,
  `protocols/rapp-hive/1/SPEC.md`, `protocols/rapp-federation/1/SPEC.md`,
  every schema, `RAPP1_PIN.json`, `RAPP_WORK_PIN.json`,
  `.github/skills/rapp-private-hive/rapp/agent.lock.json`, and the legacy
  skill fixtures.
- **No re-signature is needed.** The frozen signed registry does not pin
  `rapp-work-sdk/1`. `verify_source_estate` lists its signed profiles as
  `rapp-federation/1`, `rapp-hive/1`, `rapp-work/1`, and `rapp/1`, and
  `tools/check.py` passes.

### 3.5 Observable changes for consumers

- A tree with at least one regular `*_agent.py` that can be read safely gains
  the `agents` member.
- A regular `*_agent.py` that cannot be read safely (hard-linked, over 1 MiB,
  unreadable, changed during the read, not valid UTF-8 as a path, or over the
  class bounds) adds a refusal. It uses the existing refusal shape
  `{code, message, path}`; `REFUSE_AGENT_NAME` and `REFUSE_AGENT_METADATA`
  are new codes. Symbolic links, FIFOs, sockets, and devices named
  `*_agent.py` keep exactly the refusals they already produce.
- `verify` reports the new `rapp-work-sdk/1` specification hash, as it does
  for any revision of the specification.
- Everything else is byte-identical.

## 4. Security and privacy analysis

**Threat model.** Scanned roots can hold hostile agent files: from RAR, from
other people, or written by an AI. They can be crafted to run code, exhaust
resources, spoof metadata, or break the output.

| Threat | Control | Evidence |
|---|---|---|
| Code execution: top-level side effects, `__import__`, decorators, metaclasses, `__init_subclass__`, class bodies, `if __name__ == "__main__"` | Only `ast.parse` (`PyCF_ONLY_AST`). Never `import`, `exec`, `eval`, `runpy`, `importlib` loaders, or `compile` to a code object | A sentinel file is never written; the environment and `sys.modules` are unchanged; tripwires on `exec`, `eval`, `compile`, `importlib`, and `runpy` record zero violations; mutants M1, M2, and M7 are killed |
| Evaluating a non-literal manifest | `ast.literal_eval` runs only on a `__manifest__` dictionary display that passed binding, literal, and bound checks | A spy sees `literal_eval` called only on `Dict` nodes; mutants M8, M9, M9b, M9c, and M9d are killed |
| Resource exhaustion | 1 MiB per file. Agent files count toward the shared `max_entries` bound. Manifest displays are capped at 4,096 nodes and depth 16. At most 256 class names, each up to 256 characters, and fields up to 1,024 characters. The SDK's own traversals are iterative, and parser failures are caught. Worst case is `max_entries` × 1 MiB of parsing, the same order as the existing `agent.py` neuron inspection | Oversize, deep-nesting, wide-manifest, and class-bound tests; mutants M15, M16, M19, and M9c are killed |
| Filesystem tricks: symbolic links, FIFOs, devices, hard links, races, traversal | Walk classification without opening the entry. Descriptor-relative `O_NOFOLLOW` and `O_NONBLOCK` reads that require a regular, single-link file. Before/after `fstat` race check | Symlink, FIFO, hardlink, directory-named-like-an-agent, and unreadable-file tests; mutants M20 and M21 are killed |
| Encoding spoofing (showing the SDK one program and the interpreter another), for example through a `unicode_escape` declaration | Strict UTF-8 only. Any PEP 263 declaration on line 1 or 2 that is not UTF-8 means the file is not parsed (`unsupported-encoding`). One leading BOM is handled | Encoding tests; mutants M10 and M11 are killed |
| Verdict depends on host state (`-W error` turns parser warnings into errors) | Warnings are suppressed around the parse | Warning-filter test; mutant M13 is killed |
| Output breakage: lone surrogates, non-UTF-8 names, floats | Manifest fields containing surrogates or noncharacters become `null`. A non-UTF-8 path becomes a `REFUSE_AGENT_NAME` refusal with an escaped path. No float is ever emitted | Field-filter test; Linux container test for `\xff` names; mutants M14 and M22 (Linux) are killed |
| Authority confusion | `executed: false`, `authority: "discovery-only"`, `treatment: "inert-data"`. `live` is position only. A record is not a catalog item | Closed-shape test |

**Residual limits.**

- The manifest fields are the literal text of the file. Code that mutates the
  dictionary through a call, such as `__manifest__.update(...)`, or that binds
  it dynamically through `globals()`, is invisible to static reading.
- `classes` is syntactic: bases named `BasicAgent`. The kernel's runtime
  selection is different (`perform`, name filters, instance validation).
- The kernel follows a symbolic link in its agents directory; the SDK never
  does. Such an agent appears only as a `REFUSE_SYMLINK` refusal.
- On Windows the kernel's glob is case-insensitive, while the SDK's match is
  case-sensitive. Separately, the SDK already refuses reads on hosts without
  `O_NOFOLLOW`.
- The `parsed` verdict belongs to the running interpreter. For example, PEP 695
  syntax parses on 3.12 and later but not on 3.10. `parsed` is never a claim
  that the module compiles or loads: `return` at module level parses.
- The binding analysis is conservative. A local variable named `__manifest__`
  inside a function makes the status `ambiguous`.
- The encoding check is stricter than Python's. A non-UTF-8 declaration on
  line 2 counts even when line 1 is code, where Python would ignore it. The
  cost is only a missing parse (`unsupported-encoding`), never a wrong one.

**Privacy.** Records hold absolute local paths, as existing discovery records
already do, and at most five manifest strings copied from files the caller
asked to scan. Discovery stays read-only and offline and persists nothing. It
adds no network use, credential, or cache. Anyone who shares discover output
shares those paths, which is also true today.

## 5. Migration

- No data or files migrate; discovery writes nothing.
- Consumers that ignore unknown members need no change. Consumers that check
  the discover result's member set as closed must accept `agents` when they
  scan trees containing `*_agent.py`.
- The Brainstem app and a future G17 agent can switch from reading agent files
  themselves to calling `discover`.

## 6. Rollback

Revert this branch's commit. §11 returns to its 1.0.0 text, the pins return to
`cf64a90f…8ef1`, and every discover result returns to 1.0.0 bytes. There is no
persisted state to clean up. The token `rapp-work-discovered-agent/1` is then
retired and must never be reused for another shape (Article 2).

## 7. Conformance and test vectors

Both vectors hash the canonical text of the complete `discover` envelope, with
the scanned root's absolute path replaced by `<root>`. The trees are built by
functions in `tests/test_discovery_agents.py`.

| Vector | Tree | SHA-256 |
|---|---|---|
| Byte identity | `build_tree_without_agents`: a skill, a plugin, a neuron, and near misses (`Upper_AGENT.py`, `notes_agent.md`, `old_agent.py.bak`, a directory named `folder_agent.py`, a symbolic link named `link_agent.py`, a FIFO named `pipe_agent.py`) | `104820080267095c3d8aee9b05934957b26c9e18f5b6ac267f3019e8d03921ba` |
| New records | `build_agent_tree`: base class, literal manifest, syntax error, latin-1 declaration, nested draft, and a copy outside `agents/` | `e71ec3c56a5d5765a5e7b3dce0859e009a79cf746f01e635e83edc8c85d09c49` |

The byte-identity vector was computed with the unmodified 1.0.0 code at
`29ead23` on Python 3.10 and 3.13. It is unchanged on this branch on 3.10 and
3.13 (macOS) and on 3.12 (Linux). The new-records vector is identical on all
three.

`tests/test_discovery_agents.py` has 21 tests. Twenty run on macOS. One is
Linux-only, because APFS cannot hold a non-UTF-8 file name.

- Positive:
  - top-level and nested classification for a Brainstem root and for an
    `agents/` root;
  - root-relative `live` with overlapping roots;
  - the base class, including a tampered copy;
  - `BasicAgent` subclass names;
  - literal manifest extraction and field filtering;
  - valid UTF-8 declarations and a BOM;
  - an exactly-1-MiB file;
  - closed and canonical records;
  - determinism and sorting;
  - the shared `max_entries` bound;
  - CLI canonical output;
  - both vectors.
- Refusal and inertness:
  - non-literal, ambiguous, and over-limit manifests, including precedence
    cases;
  - side-effect traps, checked through the file system, the environment, and
    `sys.modules`;
  - tripwires on every execution path;
  - syntax errors, NUL, non-UTF-8, non-UTF-8 declarations (lines 1 and 2,
    `\r` endings, BOM plus latin-1), and parser overflow;
  - verdicts that follow the running interpreter;
  - independence from warning filters;
  - oversize files, symbolic links, FIFOs, hard links, and unreadable files;
  - class bounds;
  - non-UTF-8 names (Linux).

**Mutation proof.** A scratch harness outside the repository applied each
mutant as a controlled textual edit. It ran `tests/test_discovery_agents.py`
and `tests/test_discovery_neuron.py` on Python 3.13, restored the original
bytes, and verified each file's SHA-256. The suite was green before and after.

| Mutant | Result | Tests that turned red |
|---|---|---|
| M1 import the agent file (`importlib` `exec_module`) before parsing | Killed | never-evaluated manifests, side-effect traps, tripwires |
| M2 `exec` the compiled source, then parse | Killed | never-evaluated manifests, side-effect traps, tripwires |
| M3 every agent `live` | Killed | golden vector, base class, root-relative live, top-level classification |
| M4 `live` for any directory named `agents` at any depth | Killed | root-relative live, top-level classification |
| M5 drop the kernel glob's hidden-name rule | Killed | top-level classification |
| M6 treat `basic_agent.py` as an ordinary agent | Killed | golden vector, base class |
| M7 `eval` non-literal manifests | Killed | never-evaluated manifests |
| M8 skip the literal validator | Killed | never-evaluated manifests |
| M9 ignore rebinding and mutation sites | Killed | never-evaluated manifests |
| M9b ignore repeated constant keys | Killed | never-evaluated manifests |
| M9c drop the node and depth bound | Killed | never-evaluated manifests |
| M9d stop at the first bound hit (order-dependent precedence) | Killed | never-evaluated manifests |
| M10 drop the encoding-declaration check | Killed | invalid and unsupported sources |
| M11 decode leniently | Killed | invalid and unsupported sources |
| M12 drop the NUL pre-check | Survived (equivalent) | Every supported parser rejects NUL (a `SyntaxError` on 3.12 and later, a `ValueError` on 3.10), and `_parse` catches both. The pre-check makes the rule independent of parser behavior; the verdict cannot differ |
| M13 let host warning filters reach the parser | Killed | warning-filter independence |
| M14 drop the surrogate and noncharacter filter | Killed | manifest extraction (and canonical encoding) |
| M15 raise the 1 MiB bound | Killed | unsafe entries |
| M16 drop the class bounds | Killed | class bounds |
| M17 always emit `agents` | Killed | byte-identity vector |
| M18 leave agent records unsorted | Killed | determinism, golden vector, root-relative live |
| M19 do not count agent files toward `max_entries` | Killed | shared bound |
| M20 walk follows symbolic links to files | Killed | existing symlink test, byte-identity vector, unsafe entries |
| M21 accept hard-linked files | Killed | unsafe entries |
| M22 drop the non-UTF-8 name check | Killed on Linux | The non-UTF-8 name test fails with M22 in an offline Linux container (a streamed copy of the sources, Python 3.12). On macOS that test is skipped |

**Local CI.** On this branch, the local mirror of the `conformance` workflow
job passes on both matrix Pythons, 3.13 and 3.10: `tools/check.py`, `pytest`
(190 collected: 189 passed and 1 skipped on macOS), `ruff`, `mypy --strict`,
`release_inventory --check`, `build`, and `verify_package`. The GitHub
workflow runs only for `main` and pull requests, so it does not run for this
branch.

## 8. Reference implementation and gating

- `src/rapp_work/agent_files.py` (new): `DiscoveredAgent` and
  `inspect_agent_entry`. The module name matches neither `*_agent.py` nor
  `agent.py`, so the SDK never classifies its own source.
- `src/rapp_work/discovery.py`: routes names that end with `_agent.py` to that
  inspector before the unchanged skill, plugin, and neuron chain. It sorts the
  records and adds `agents` only when there is at least one.
- **Gating.** The behavior is scoped to the new token
  `rapp-work-discovered-agent/1`, in a member that is absent when empty. There
  is no new input, operation, or static API change. The default remains
  fail-closed: nothing runs, and anything uncertain is refused or reported as
  not parsed. Tests cover both sides: byte identity for trees without agents,
  and records for trees with agents. The branch is experimental and is not
  merged; the owner decides.
- No new top-level export; `rapp_work.__all__` is unchanged.
- Documentation updated: `README.md`, `AGENTS.md`, `CLAUDE.md`,
  `docs/API.md`, `docs/ARCHITECTURE.md`, and `CHANGELOG.md` ("Unreleased
  (proposal, not accepted)").

## 9. Open questions for the owner

1. **Article 2 reading.** Does the owner treat the discover result's member set
   as part of what `rapp-work-sdk/1` denotes? If yes, choose option (e) and
   this text moves under a new label instead.
2. **`live` for the base class.** This proposal keeps `live` purely positional,
   so `basic_agent.py` at the top level is `live: true` and
   `role: "base-class"`: the kernel does import it on every sweep. The
   alternative forces `live: false` for the base class.
3. **Static API summary.** `rapp-work-static-api/1`'s human `refusals` list
   says "plugin, skill, or neuron execution". Adding agents there would change
   every `status` and `discover` result, so it is left for a release that
   revises that document anyway.
4. **§12.** "Agent execution" could join §12's list of explicit refusals. §12
   was left untouched because it is gap G6's home.
5. **Catalogs.** Advertising single-file agents in a signed
   `rapp-work/1-catalog` needs an upstream `kody-w/rapp-1` revision under a
   new token. This proposal does not do that.
6. **Bounds.** 1 MiB per file (above RAR's largest agent, 453,476 bytes, among
   1,843 files); 256 classes and 256-character names; 4,096 manifest nodes and
   depth 16; 1,024-character fields.
7. **Parser version.** Should the SDK pin a parser `feature_version`, so that
   `syntax` agrees across interpreters, at the cost of rejecting newer syntax
   that a newer Brainstem would load?

## 10. Owner actions needed

1. Review §11.1 on `experimental/gap-g3-agent-discovery` and accept or refuse
   it (Open questions 1–7).
2. If accepted: merge through the owner's own process, then release. Bump
   `pyproject.toml` and `SDK_VERSION`, add the dated CHANGELOG entry, and run
   `tools/release_inventory.py --write`.
3. Report G3 as `proposed` now, and `fixed` after the release. The
   Constitution agent owns the organism file.
4. No signing action: the frozen signed registry does not pin
   `rapp-work-sdk/1`.

## 11. Ready-to-file pull request text

**Title:** `rapp-work-sdk/1` §11.1: record single-file agents as inert
discovery data (G3)

**Body:** Adds `rapp-work-discovered-agent/1` records to `discover` for
Brainstem single-file agents (`*_agent.py`). They are parsed, never imported,
compiled, or executed. Records carry hashes, a parser verdict, `BasicAgent`
subclass names, a literal `__manifest__` subset, a positional `live` flag, and
the base-class role. The `agents` member is omitted when empty, so trees
without agents keep byte-identical output (vector `10482008…21ba`). No new
input, operation, envelope, or static API change. The SDK specification pins
follow the new §11 bytes; the frozen signed registry is unaffected. Full
rationale: `docs/proposals/0003-sdk-agent-discovery.md`.

## 12. References

- `kody-w/rapp-work` at `29ead23`: `protocols/rapp-work-sdk/1/SPEC.md` §§2,
  11, and 12; `src/rapp_work/discovery.py`; `src/rapp_work/neuron.py`;
  `src/rapp_work/api.py`; `docs/ARCHITECTURE.md` ("Inert extension model");
  `AGENTS.md`; `CONTRIBUTING.md`.
- `kody-w/rapp-1`: `CONSTITUTION.md` Articles 2, 4, 6, 7, 8, 10, and 18;
  `protocols/rapp-work/1/SPEC.md` §§3 and 10 at `591e014`.
- `kody-w/rapp-installer` `rapp_brainstem/brainstem.py` at `brainstem-v0.6.9`
  (lines 67, 1021–1048, and 1202–1205) and at `brainstem-v0.6.16` (lines 441,
  1640–1669, 1832–1835, 3025–3028, and 3055–3060).
- `kody-w/RAR` at `ecf5f52`: `build_registry.py` `extract_manifest`;
  `CONSTITUTION.md` Article IV.
- PEP 263 (source code encodings); RFC 7493 (I-JSON); RFC 8785 (JCS).
