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

Portable Neurons, discovered plugins, and project skills are untrusted data.
Discovery may parse bounded metadata and Python syntax, but MUST NOT import,
execute, install, enable, or grant authority to discovered code.

The historical workspace-manager and Private Hive implementations remain
available only through explicit SDK compatibility wrappers and deprecated
legacy paths. Those wrappers do not broaden their profile claims.

### 11.1 Single-file agents

Single-file agents are untrusted data under the rule above. A single-file
agent is a Brainstem agent file: a regular file whose name ends with the
exact, case-sensitive suffix `_agent.py`.

`discover` accepts one more optional member in its closed input: `agents`, a
JSON Boolean. When it is absent or `false`, discovery treats files named
`*_agent.py` exactly as it did before this section: it neither opens nor
reports them, and its result has no `agents` member. When it is `true`, the
result MUST have an `agents` member: an array, possibly empty, of
`rapp-work-discovered-agent/1` objects, one for each single-file agent that
discovery can read safely, in code-point order of `path` and then `root`. A
file reached from several scanned roots yields one record per root. Agent
files count toward the same `max_entries` bound as every other entry.

A record has exactly these members:

| Member | Value |
|---|---|
| `schema` | `rapp-work-discovered-agent/1` |
| `path`, `root` | Absolute lexical paths, with no link resolved, of the file and of the scanned root it was found under |
| `bytes`, `sha256` | Exact byte length and SHA-256 of the file |
| `language` | `python` |
| `role` | `base-class` for `basic_agent.py`, the shared base class; otherwise `agent` |
| `live` | Boolean, defined below |
| `syntax` | `parsed`, `invalid`, `unsupported-encoding`, `over-limit`, or `over-budget` |
| `classes` | When `parsed`: the distinct names, in code-point order, of classes defined directly in the module body whose base list names `BasicAgent`, as a name or as an attribute; otherwise `null` |
| `manifest_status` | When `parsed`: `absent`, `literal`, `not-literal`, `ambiguous`, or `over-limit`; otherwise `null` |
| `manifest` | When `literal`: an object with exactly `schema`, `name`, `version`, `display_name`, and `description`; otherwise `null` |
| `executed` | `false` |
| `authority` | `discovery-only` |
| `treatment` | `inert-data` |

`live` is `true` exactly when the file name does not begin with `.` and the
file's directory is the scanned root's live directory. The live directory is
the root itself when the name `agents` in the root's parent directory resolves
to the root. Otherwise it is the directory that the name `agents` inside the
root resolves to, when that is a directory and not a symbolic link. Names
resolve as the file system resolves them and directories are compared by
file-system identity, so a case-insensitive volume behaves as the Brainstem
kernel's `*_agent.py` glob does. This mirrors the kernel, whose
`load_agents()` loads only the top level of its agents directory; every
subfolder is organization. `live` describes position only, as observed when
the file is inspected. The SDK never loads the file, and `live` does not claim
that a Brainstem exists, uses that directory, or would load the file
successfully.

Discovery reads the source with a descriptor-relative no-follow read of at
most 1 MiB. The source is `unsupported-encoding` when its bytes, after one
optional UTF-8 byte-order mark, are not strict UTF-8, or when an encoding
declaration on its first or second line names anything other than UTF-8
(`utf-8`, `utf8`, or a `utf-8-` prefix, compared case-insensitively with `_`
read as `-`). It is `invalid` when it contains a NUL code point. Otherwise
discovery measures the text with the call's parse budget (section 11.2). The
source is then `over-limit` or `over-budget` as section 11.2 says, `invalid`
when the measure or the Python parser rejects it, and otherwise `parsed`: the
running interpreter's parser built a syntax tree. `parsed` does not claim that
the module compiles, imports, or runs, and the host's warning filters do not
change the verdict.

`manifest_status` describes the name `__manifest__`, decided in this order.
It is `absent` when nothing binds that name. It is `ambiguous` when anything
binds it other than exactly one direct module-body assignment statement
(`__manifest__ = ...` or `__manifest__: T = ...`), or when that assignment's
value is a dictionary display that repeats a constant top-level key (compared
as Python values). Anywhere in the file, these bind the name: an assignment,
augmented assignment, annotated assignment with a value, assignment
expression, `for` or comprehension target, `with ... as` target, or `del` of
the name; a subscript or attribute assignment or `del` whose object is the
name itself; a function, class, or import alias of that name (`import
__manifest__`, `import __manifest__.x`, `... as __manifest__`); an
`except ... as` name; a match capture (`case __manifest__`, `*__manifest__`,
`**__manifest__`); a function or lambda parameter; and a type parameter. An
annotation without a value does not bind.

It is `not-literal` when the value is not a literal display. A literal display
is a dictionary display whose keys are all constants and whose values are
literal elements. A literal element is a constant; a signed constant, meaning
unary `+` or `-` applied directly to an integer, floating-point, or imaginary
constant; or a list, tuple, set, or dictionary display whose elements (for a
dictionary: keys that are constants, and values) are literal elements. The
display's nodes are the displays, constants, and signed constants it contains,
counting the outer dictionary; a signed constant is one node. The outer
dictionary has depth 1, and anything directly inside a display has that
display's depth plus 1. It is `over-limit` when the display has more than
4,096 nodes or a node deeper than 16. Otherwise it is `literal`, except that a
display that cannot be constructed as a value, such as a set that contains a
list, is `not-literal`. Discovery MAY evaluate a display that passed every
earlier test, and only as a literal; it MUST NOT evaluate any other
expression. Each `manifest` member is the same-named string value when that
value is a string of at most 1,024 characters containing no surrogate or
noncharacter code point, and `null` otherwise. The fields are the file's
literal text, not the value a running module would hold.

A file that cannot be read safely produces a refusal in `refusals` and no
record: a symbolic
link (`REFUSE_SYMLINK`), a non-regular or hard-linked entry
(`REFUSE_PATH_TYPE`), a file over 1 MiB (`REFUSE_FILE_LIMIT`), a file that
changes while it is read (`REFUSE_FILE_RACE`), an unreadable file
(`REFUSE_PATH_UNSAFE`), or a path that is not valid UTF-8
(`REFUSE_AGENT_NAME`, reported with an escaped path). A file whose `classes`
would hold more than 256 names, or a name longer than 256 characters, is
refused with `REFUSE_AGENT_METADATA`. Any other inspection failure is likewise
a refusal with no record.

A record is discovery, not authority. It does not load, enable, install, or
authorize an agent. It is not a `rapp-work/1-catalog` item, and the canonical
catalog kinds are unchanged.

### 11.2 Bounded parsing

Discovery MUST NOT pass discovered Python source to the interpreter's parser
unless the measure below has read the whole source within its bounds. This
applies to Portable Neurons and to single-file agents. A source outside the
bounds is not parsed: a Portable Neuron is then refused exactly as a source
the parser rejects, and a single-file agent is `over-limit` or `over-budget`.
The measured text is the text the parser would read: for a single-file agent,
the strict UTF-8 text of section 11.1; for a Portable Neuron, the source
decoded as PEP 263 prescribes.

The measure reads the tokens that the running interpreter's `tokenize` module
produces, after `\r\n` and `\r` are read as `\n`. It never evaluates anything.
A formatted string literal (an f-string, or a t-string on an interpreter that
has them) is read as an opening mark; then, for each replacement field, `{`,
the tokens of its expression, any `=`, any `!` and conversion name, any `:`
followed by the replacement fields of its format specification, and `}`; then
a closing mark. Literal text is not a token. On Python 3.10 and 3.11, whose
tokenizer returns a formatted string literal as one string token, the
replacement fields and their expressions are the ones that CPython's own
f-string scanner finds, and an expression's tokens are those of the
expression enclosed in parentheses, without the added pair. A source that the
tokenizer or that scanner rejects, or that opens a 100th indentation level
(which CPython's tokenizer refuses), is `invalid`.

- **Cost.** Each token costs 1, except that a token inside a formatted string
  literal, including its opening and closing marks, costs 1 plus 1 for every
  full 4,096 characters of the physical line on which the token begins.
  Literal text, `ENCODING`, and `ENDMARKER` cost nothing.
- **Nesting.** Each indentation level keeps an elif count. A logical line that
  begins with `elif` adds 1 to the count of its own level, a line that begins
  with `else` leaves it, and any other line sets it to 0; a level opened by an
  indent starts at 0. The statement weight of a logical line is 1 plus, for
  its own level and every enclosing level, 2 plus that level's elif count.
  Within a logical line, tokens form groups: the line itself, each open
  bracket, and each open formatted string literal. A group's count starts at
  0, or at 1 for a formatted string literal. An opening bracket adds 2 to the
  group it is in and opens a new group; when the group it is in is a formatted
  string literal, that literal's count first returns to 1. A closing bracket
  closes its group.
  `lambda` adds 2 and leaves one `:` pending in its group; `:` settles one
  pending `lambda` and, like every operator or delimiter token other than `,`,
  `;`, and closing brackets, adds 1. `,` sets its group's count to 0 unless a
  `lambda` is pending there. Each of the keywords `and`, `async`, `await`,
  `else`, `for`, `from`, `if`, `in`, `is`, `not`, `or`, and `yield` adds 1.
  Consecutive string literals in a group form a run. The weight of a plain
  string is 0; the weight of a formatted string literal is the greatest
  nesting reached inside it minus the nesting just before it. When an opening
  bracket, operator, delimiter, name, or number follows a run in the same
  group, the group's count first gains the largest weight in the run; a `,`,
  a closing bracket, or the end of the statement ends the run without adding
  it. A `;` or the end of a logical line closes every group and returns the
  line's count to 0. The nesting at a token is the statement weight plus the
  counts of all groups open after the token.
- **Integers.** A decimal integer literal counts its digits, not counting
  underscores.
- **Replacement fields.** A run's replacement fields are the `{` tokens inside
  the formatted string literals of the run, at any depth.

The measure reads tokens in order and stops at the first token at which the
source is invalid or outside the bounds. At each token it checks the cost
first: the source is outside the bounds when its cost exceeds the measure's
allowance, and then when its nesting exceeds 256, a decimal integer literal
has more than 640 digits, or a run holds more than 1,024 replacement fields.
The allowance is 131,072 for a Portable Neuron. The number 640 is the
smallest limit that `sys.set_int_max_str_digits` accepts, so no host setting
changes a verdict.

Each `discover` call with `agents: true` has a parse budget of 8,388,608 cost
units, spent on single-file agents in code-point order of `path` and then
`root`. A measure's allowance is the smaller of 131,072 and the remaining
budget, and the measure consumes the cost units it reads, up to its
allowance, whatever its verdict. A source whose measure stops at a bound
other than a remaining budget smaller than 131,072 is `over-limit`; a source
whose measure stops at such a budget, or that finds no budget left, is
`over-budget`.

## 12. Refusals

Unsupported sharing, public Git, credential inheritance, implicit apply,
unknown JSON members, parent-authority changes, plugin execution, neuron
execution, source deletion, owner rotation, and unverified Hive rollback/fork
acceptance are explicit refusals.
