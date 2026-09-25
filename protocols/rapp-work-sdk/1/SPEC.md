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

## 12. Refusals

Unsupported sharing, public Git, credential inheritance, implicit apply,
unknown JSON members, parent-authority changes, plugin execution, neuron
execution, source deletion, owner rotation, and unverified Hive rollback/fork
acceptance are explicit refusals.
