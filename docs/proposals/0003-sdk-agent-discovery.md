# Proposal 0003: SDK discovery records single-file agents as inert data

| | |
|---|---|
| Status | **Draft 2, not accepted.** Branch `experimental/gap-g3-agent-discovery`. Nothing is merged, released, or activated. |
| Gap | **G3**: SDK discovery misses `*_agent.py`. SDK discovery does not see single-file agents named `*_agent.py`; the fix records them as inert data that never runs. |
| Home spec | `rapp-work-sdk/1` §11 (Inert compatibility): new §11.1 (Single-file agents) and §11.2 (Bounded parsing), inserted before §12 |
| Base | `kody-w/rapp-work` `main` at `29ead23b21645f8d7682ee00414930ffa9ce0ca6` (SDK 1.0.0) |
| Blocks | Workspaces (organism layer 4) |
| Intended release | The next minor SDK release (1.1.0), or the release the owner bundles accepted `rapp-work-sdk/1` proposals into. This branch does not change the package version or `SDK_VERSION`. |

## Changes in draft 2

An independent review of draft 1 found one high and four medium defects.
This draft fixes all of them:

- **Crash on Python 3.10 (high).** Draft 1 handed every `*_agent.py` to
  `ast.parse`. On 3.10 a 400 KB `1+1+1...` chain overflows the C stack while
  the tree is converted to Python objects, and the process dies with SIGSEGV.
  The same crash already exists on `main` for a Portable Neuron named
  `agent.py`. Discovery now parses a source only after a token-level measure
  (§11.2) proves it is within fixed nesting, cost, integer, and
  replacement-field bounds. The same guard now protects Portable Neurons.
- **Unbounded time and memory (medium).** One 1 MiB file could take 1.1 GB or
  35 s to parse, and nothing bounded a call. Each file now has a cost bound,
  and each call has a parse budget, spent in a deterministic order. Measured
  costs are in section 4.
- **Article 2 (medium).** Draft 1 grew the discover result, and its existing
  `refusals` array, under unchanged labels for every tree with agent files.
  The review was right that this is the same kind of change draft 1 rejected
  for other options. Discovery of agents is now opt-in through a new closed
  input member, `agents: true`. Every request that 1.0.0 accepts returns its
  1.0.0 result, apart from the embedded static API document (section 3).
- **Imprecise normative text (medium).** The class bound now counts distinct
  names, as the code always did. Manifest nodes, depth, and every binding form
  of `__manifest__` are defined exactly; function and lambda parameters and
  type parameters now make the manifest `ambiguous`, as the text said.
- **Lows.** `live` now follows the file system's own name resolution, so
  case-insensitive volumes agree with the kernel. Digit limits and recursion
  limits of the host no longer change verdicts. Concurrent calls no longer
  race on warning filters. Vectors pin class order, every binding form, and
  `utf-8-sig` declarations. Cached bytecode is documented as a residual.
- **Composition.** Existing SPEC paragraphs keep their exact 1.0.0 bytes. The
  new text is a pure insertion. Section 9 lists sibling proposals that touch
  the same files and a recommended merge order.

## 1. Context: what is true today

1. **Only top-level agents are live in every released Brainstem.** In
   `kody-w/rapp-installer` at tag `brainstem-v0.6.9` (the LTS channel),
   `rapp_brainstem/brainstem.py` sets `AGENTS_PATH` to the Brainstem
   directory's `agents` child by default (line 67). `load_agents()` is a flat
   glob of `AGENTS_PATH/*_agent.py` (lines 1202–1205).
   `_load_agent_from_file` (from line 1021) imports each file with
   `importlib.util.spec_from_file_location` and `exec_module` (lines
   1039–1041). It registers every class that has `perform`, except
   `BasicAgent`, `object`, and names that start with `_` (lines 1044–1048).
   At tag `brainstem-v0.6.16` (the newest channel) the glob is the same, now
   sorted (lines 1832–1835). Class selection also requires
   `cls.__module__ == mod.__name__` (line 1666). The HTTP API refuses to
   delete `basic_agent.py`, "the shared base class" (lines 3025–3028), and
   requires uploads to match `*_agent.py` (lines 3055–3056). Python's `glob`
   skips names that begin with `.`. It matches file names case-sensitively on
   POSIX, but the directory name resolves as the file system resolves it. It
   does match `basic_agent.py`, so the kernel imports the base-class file on
   every sweep but registers no agent from it. The organism records this as
   the invariant "Only top-level `agents/*_agent.py` files are live. Every
   folder is organization."
2. **The SDK does not see those files.** At `29ead23`,
   `src/rapp_work/discovery.py` `discover_roots` (lines 187–249) classifies
   regular files by exact name only (lines 220–225): `SKILL.md` becomes
   `rapp-work-discovered-skill/1`, `rapp-work-plugin.json` becomes
   `rapp-work-discovered-plugin/1`, and `agent.py` becomes
   `rapp-work-portable-neuron/1`. A file named `hello_agent.py` matches none of
   these, so discovery omits it without saying so. `src/rapp_work/api.py`
   `_discover` (lines 174–193) takes the closed input `{roots, max_entries}`,
   and `src/rapp_work/data/api.json` (`rapp-work-static-api/1`) lists exactly
   those inputs.
3. **The accepted rule.** `rapp-work-sdk/1` §11 (SPEC lines 146–154 at
   `29ead23`): "Portable Neurons, discovered plugins, and project skills are
   untrusted data. Discovery may parse bounded metadata and Python syntax, but
   MUST NOT import, execute, install, enable, or grant authority to discovered
   code." The SPEC does not define "bounded".
4. **Parsing untrusted Python is not bounded today.** `PortableNeuron.inspect`
   (`src/rapp_work/neuron.py` lines 51–72 at `29ead23`) passes up to 1 MiB of
   discovered source to `ast.parse`. The interpreters behave very differently
   on deep expressions. Measured on macOS arm64 with CPython 3.10.20, 3.11.16,
   3.13.15, and 3.14.7, and with 3.12.14 on Linux:

   | Construct, depth *n* | 3.10 | 3.11 | 3.12, 3.13 | 3.14 |
   |---|---|---|---|---|
   | Left-recursive chain (`a+a+…`, `a.b.b…`, `a()()…`, `a[0][0]…`, `x: a\|a…`, `a@a…`, and the same inside an f-string field) | Parses at 100,000; beyond that the process dies (SIGSEGV). No guard at all | `RecursionError` above about 3,000 (3 × the recursion limit) | `RecursionError` above about 6,000 to 10,000 | `RecursionError` above 10,000 |
   | Right-recursive form (`not not …`, `- - …`, `lambda: lambda: …`, `a if b else …`, `a**a**…`, `elif` chains) | "Parser stack overflowed" (`MemoryError`) between 2,900 and 6,000 | Same, or `RecursionError` near 4,000 | Same | Same |

   Every construct parses on every version at depth 2,900. On 3.10 a
   left-recursive chain costs about 60 bytes of C stack per level; the parser
   recursion of a right-recursive form costs 140 to 240 bytes per level. So a
   file named `agent.py` holding `x = 1+1+…` (400 KB) kills a 3.10 process
   that runs `discover` today. On 3.11 the same happens if the host raised
   `sys.setrecursionlimit`. Time and memory are unbounded too: 1 MiB of `a\n`
   lines peaks at about 1.1 GB, and a 1 MiB f-string of `{a}` fields takes
   15 s (3.13) to 35 s (3.10). With `max_entries` 10,000, one call can take
   hours.
5. **The canonical parent.** `rapp-work/1` §3 (`kody-w/rapp-1`
   `protocols/rapp-work/1/SPEC.md`; packaged mirror
   `src/rapp_work/data/rapp-work-1-SPEC.md`, pinned by `RAPP_WORK_PIN.json` at
   `591e014`) says catalogs are discovery, not authority. Catalog item `kind`
   is the closed set `plugin`, `skill`, `static-api`, and `portable-neuron`.
   Portable Neurons are accepted only as typed inert data. §10 item 7 requires
   implementations to "treat Portable Neurons and discovery entries as inert,
   non-authoritative data".
6. **How RAR reads agents.** `kody-w/RAR` `build_registry.py`
   `extract_manifest` (from line 84 at `ecf5f52`) extracts the
   `__manifest__` dictionary (`schema: "rapp-agent/1.0"`, RAR `CONSTITUTION.md`
   Article IV) through `ast.parse` and `ast.literal_eval`, without importing the
   file. It also calls `compile(source, path, "exec")` (line 93) as a stricter
   publication gate.
7. **Who needs it.** The Brainstem app shows `agents/` as a workspace root and
   explains agents without running them. The future Brainstem SDK agent (gap
   G17) reaches the SDK through `discover`. Today neither can list agents
   through the SDK.

## 2. Proposed change

### 2.1 Normative text

The existing text of `protocols/rapp-work-sdk/1/SPEC.md` is unchanged, byte
for byte. Two subsections are inserted at the end of §11, after the paragraph
that ends "Those wrappers do not broaden their profile claims." and before
"## 12. Refusals". This is the exact inserted text:

````markdown
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
````

### 2.2 Interface changes (reference implementation)

- **Closed input.** `discover` accepts `agents` (JSON Boolean, default
  `false`). Any other type is refused with `REFUSE_INPUT_SHAPE`. SDK 1.0.0
  refuses the member with `REFUSE_INPUT_KEYS`, so a caller can tell whether an
  SDK supports agent discovery, and an old SDK never silently omits agents.
- **Static API.** In `src/rapp_work/data/api.json`
  (`rapp-work-static-api/1`, same shape), `discover` lists
  `optional_inputs: ["agents", "max_entries"]`, and the refusal summary
  `"plugin, skill, or neuron execution"` reads
  `"plugin, skill, neuron, or agent execution"`.
- **CLI.** `rapp-work discover --root PATH --agents` sends `agents: true`.
  Without `--agents` the CLI sends exactly what 1.0.0 sent.

### 2.3 What this means in practice (non-normative)

- `discover` without `agents` behaves as 1.0.0 did, including on trees full
  of agent files: it does not open them.
- `discover` with `agents: true` returns one record per `*_agent.py`: its
  hash, a parser verdict, its `BasicAgent` subclass names, and five of the
  manifest fields RAR defines (`schema`, `name`, `version`, `display_name`,
  `description`) when the manifest is a plain literal.
- `live: true` means "top level of the live `agents/` folder", which is where
  the kernel's flat glob picks the file up. Files in subfolders, anything
  outside the live folder, and hidden names are `live: false`.
  `basic_agent.py` is `role: "base-class"`.
- Nothing is imported, compiled to bytecode, or executed. A file too deep,
  too large, or too costly to parse safely is `over-limit`. A file that the
  call's budget no longer covers is `over-budget`; scanning it in a smaller
  call parses it. A file that cannot be read safely appears only as a
  refusal.
- Every real agent we measured is far inside the bounds (section 7.3).

## 3. Token and compatibility analysis

### 3.1 Every token this touches

| Token or surface | Change |
|---|---|
| `rapp-work-result/1` envelope (seven members) | None |
| Discover result for every request 1.0.0 accepts | Same member set, same records, same refusals, same bytes, except the `api` member (next row). Vectors in section 7.1 |
| `rapp-work-static-api/1` (`api.json`) | Same key set and grammar. Two values change: one string added to one `optional_inputs` array, and one refusal summary string reworded. Its bytes appear in every `status` and `discover` result |
| Closed `discover` input | One new optional member, `agents`. Requests without it are unchanged |
| Discover result for a request with `agents: true` | Has an `agents` member, and `refusals` can list agent files. 1.0.0 refuses such a request, so no result that existed before changes |
| `rapp-work-discovered-skill/1`, `rapp-work-discovered-plugin/1` | None |
| `rapp-work-portable-neuron/1` | Same shape and bytes for every neuron within the §11.2 bounds. A neuron outside them is refused, as a neuron the parser rejects is refused today |
| `rapp-work-sdk/1` integration record (`protocols/rapp-work-sdk/1/schema.json`) | None. Same bytes, same hash `a931fe3e…9029` |
| `rapp-work-sdk/1` specification text | §11.1 and §11.2 inserted; hash pins updated (section 3.4) |
| `rapp-work-discovered-agent/1` | **New** token. It has never denoted any other shape |
| `rapp-work/1-catalog` and its closed `kind` set | None. Agent records are not catalog items |
| RAPP/1 canonicalization, hashes, RAPPIDs, Frame, wire, Egg | None |

### 3.2 Article 2 (one label, one shape)

Article 2 says a versioned token "must never denote two shapes", and any
revision that changes a key set, a field grammar, or a hash rule moves the
token.

Draft 1 added the `agents` member to the discover result whenever the scanned
tree held a readable agent file, and it added agent-file refusals to the
existing `refusals` array (for example `REFUSE_PATH_TYPE` for a hard-linked
`*_agent.py` that 1.0.0 ignored). The same request, under the same labels
`rapp-work-result/1` and `rapp-work-sdk/1`, then produced a different key set
and different refusals. That is the change draft 1 itself rejected for other
options, and under a strict reading of Article 2 it needed a new token or an
owner ruling.

This draft makes agent discovery opt-in. The options, weighed again:

| Option | Effect on existing labels and bytes | Verdict |
|---|---|---|
| (a) Always add `agents: []` | Every discover result changes shape | Rejected |
| (b) Add `agents` when the tree holds agent files (draft 1) | Results of 1.0.0 requests change shape and refusals under unchanged labels | Rejected: needs an owner ruling |
| (c) Put agent records into `neurons` or `refusals` | Changes an existing array's grammar in place | Rejected: violates Article 2 |
| (d) Opt-in closed input member `agents: true` | No result of a request that 1.0.0 accepts changes shape. The static API document keeps its shape; two values change | **Chosen** |
| (e) Mint `rapp-work-sdk/2` or `rapp-work-result/2` | Lawful, but moves every consumer to a new label to add one inert record kind | Held in reserve (Open question 1) |

Why (d) is lawful without an owner ruling:

- No labeled artifact changes its key set, field grammar, or hash rule.
  `rapp-work-result/1` keeps its seven members. `rapp-work-static-api/1` keeps
  its keys and grammar: an `optional_inputs` array is still an array of input
  names, and `refusals` is still an array of summary strings.
- Every result that could exist before this change is reproduced exactly,
  apart from the static API document embedded in it. The vector in section 7.1
  proves it on a tree full of agent files: after the 1.0.0 static API
  document is put back, the result is byte-identical to 1.0.0's.
- The new shape appears only in the result of a new request, which 1.0.0
  refuses (`REFUSE_INPUT_KEYS`). A consumer that holds such a result also
  holds the request that asked for it.
- The new records carry their own new token.

What (d) still changes, stated plainly: the `api` member of every `status` and
`discover` result, because it embeds `api.json`. Draft 1 rejected (d) to keep
those bytes. That weighed byte identity above shape stability, which is what
Article 2 protects. A static API document exists to describe the operation
surface, so it must change whenever the surface grows; sibling proposals G2
(`update` gains `moves` and `inverse_of`) and G4 (`migrate` gains `hive` and
`successor`) change it the same way, in different arrays. The cost is paid once
per release, and it breaks no parser of the document.

What stays an owner question: whether the operation's accepted input set is
itself part of what `rapp-work-sdk/1` denotes. Under that reading every new
optional input, including those of G2 and G4, moves the token, and only
option (e) is lawful. That is a question for all SDK proposals at once
(Open question 1).

### 3.3 Other articles

- **Article 4.** A new record kind and one optional input member; no new
  operation, envelope, or door.
- **Article 18.** Canonicalization, hashes, the RAPPID grammar, the
  eleven-key Frame, wire forms, and the Egg container are untouched.
- **Article 10.** Output goes through the SDK's existing pinned canonicalizer
  (`rapp_work._json.canonical_text`). No reference primitive is re-typed.
- **Articles 6 and 7.** No owner authority is read or written. No identity is
  derived from a name. `root` and `path` are locators, not identities.
- **Article 8.** No oracle is skipped, muted, or weakened. Every existing test
  passes; the only existing test file that changes is this proposal's own
  `tests/test_discovery_agents.py` from draft 1.

### 3.4 Pins

- `protocols/rapp-work-sdk/1/SPEC.md` SHA-256 moves from
  `cf64a90f44427728966ba142d6ef42cdd31f08ad465badf86a93c969f0cb8ef1` to
  `ef4f7acef71942b27724dfc9d168051688565ca2c2619662f650954322dbdb6a` in both `protocols/index.json` and
  `src/rapp_work/data/profiles.json`. The index's `generated_utc` is
  refreshed, following the precedent in `a35db4d`.
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

- The `api` member of every `status` and `discover` result embeds the revised
  static API document (section 2.2).
- `discover` accepts `agents`. With `agents: true` the result has `agents`, and
  `refusals` may list agent files, with the existing refusal shape
  `{code, message, path}`. `REFUSE_AGENT_NAME` and `REFUSE_AGENT_METADATA` are
  new codes.
- A Portable Neuron outside the §11.2 bounds is refused with
  `REFUSE_DISCOVERY_METADATA` ("Portable Neuron source is not valid bounded
  Python syntax"), the refusal a neuron the parser rejects gets today. Before,
  such a neuron was recorded, took unbounded time or memory, or killed the
  process on 3.10. No real neuron is known to be affected; every RAR agent is
  far inside the bounds.
- `verify` reports the new `rapp-work-sdk/1` specification hash, as it does
  for any revision of the specification.

## 4. Security and privacy analysis

**Threat model.** Scanned roots can hold hostile agent files: from RAR, from
other people, or written by an AI. They can be crafted to run code, crash or
exhaust the process, spoof metadata, or break the output.

| Threat | Control | Evidence |
|---|---|---|
| Code execution: top-level side effects, `__import__`, decorators, metaclasses, `__init_subclass__`, class bodies, `if __name__ == "__main__"` | Only `tokenize` and `ast.parse` (`PyCF_ONLY_AST`). Never `import`, `exec`, `eval`, `runpy`, `importlib` loaders, or `compile` to a code object | A sentinel file is never written; the environment and `sys.modules` are unchanged; tripwires on `exec`, `eval`, `compile`, `importlib`, and `runpy` record zero violations; mutants M1, M2, and M7 are killed |
| Evaluating a non-literal manifest | `ast.literal_eval` runs only on a `__manifest__` dictionary display that passed binding, literal, and bound checks | A spy sees `literal_eval` called only on `Dict` nodes; mutants M8 and M9–M9j are killed |
| Crashing the process through the parser (C stack) | §11.2 nesting bound 256 before any parse, for agents and Portable Neurons; f-string fields measured on every version | Hostile chains of every left- and right-recursive kind, including inside f-string fields, match patterns, decorators, and `del` targets, never reach the parser, in a child process with a 512 KiB thread stack and a recursion limit of 1,000,000, on 3.10, 3.11, 3.12, 3.13, and 3.14. The worst in-bound source needs at most 256 KiB (found by bisecting the thread stack size in 16 KiB steps: an f-string field holding 124 nested brackets; 126 nested parentheses need 240 KiB, and every other in-bound construction 48 KiB or less) of C stack on 3.10. Mutants N1, N3, N10 kill the process or turn tests red |
| Exhausting time or memory | §11.2 per-file cost bound (131,072 units), digit and replacement-field bounds, and a per-call budget of 8,388,608 units spent in a fixed order | See the measured costs below; mutants N2, N4–N9 are killed |
| Verdicts that depend on the host | The digit bound sits at the smallest limit a host can set. The nesting bound sits far below every interpreter's own limit. Warnings are suppressed around the parse under a lock | Vectors with `sys.set_int_max_str_digits` at 0, 640, and 100,000; warning filters set to `error`; concurrent calls; mutants N5, M13, and M13b |
| Filesystem tricks: symbolic links, FIFOs, devices, hard links, races, traversal | Walk classification without opening the entry. Descriptor-relative `O_NOFOLLOW` and `O_NONBLOCK` reads that require a regular, single-link file. Before/after `fstat` race check | Symlink, FIFO, hard-link, directory-named-like-an-agent, and unreadable-file tests; mutants M20 and M21 are killed |
| Encoding spoofing (showing the SDK one program and the interpreter another), for example through a `unicode_escape` declaration | Agents: strict UTF-8 only; any other declaration on line 1 or 2 means the file is not parsed (`unsupported-encoding`). Neurons: the measure reads the text decoded exactly as the parser decodes it (PEP 263) | Encoding tests; mutants M10, M10b, M11, and N11 are killed |
| Output breakage: lone surrogates, non-UTF-8 names, floats | Manifest fields containing surrogates or noncharacters become `null`. A non-UTF-8 path becomes a `REFUSE_AGENT_NAME` refusal with an escaped path. No float is ever emitted | Field-filter test; Linux test for `\xff` names; mutants M14 and M22 (Linux) are killed |
| Authority confusion | `executed: false`, `authority: "discovery-only"`, `treatment: "inert-data"`. `live` is position only. A record is not a catalog item | Closed-shape test |

**Measured costs.** Measured on one macOS workstation with the scratch harness (not committed):

- **Worst call.** The per-call budget admits 64 files at the per-file cost bound.
  64 such files took 17 to 19 s with a peak RSS of 147 to 454 MB on Python 3.13, and
  25 to 27 s with 129 to 394 MB on 3.10, depending on their shape (calls, bare
  statements, or lambdas). A 65th file in the same call is `over-budget` and is not
  parsed.
- **Real agents.** `discover` with `agents: true` over RAR's `agents/` (one call per
  area, 12 calls, 1,843 records; the largest file is 453,476 bytes) took 12.5 s with a
  peak RSS of 61 MB on 3.13 and 17.1 s with 58 MB on 3.10. The largest measure among
  them is 44,813 cost units (34 % of the per-file bound) and the deepest nesting 79.
- Draft 1 needed 1,158 MB and up to 35 s for a single 1 MiB file; such a file now
  stops at the cost bound before the parser.

**Residual limits.**

- **Cached bytecode.** The kernel loads agents with
  `importlib.util.spec_from_file_location` (v0.6.9 line 1039, v0.6.16 line
  1659), whose loader prefers a matching `agents/__pycache__/*.pyc` over the
  source. An unchecked-hash `.pyc`, or a timestamp `.pyc` whose recorded
  mtime and size were forged to match, runs code the source does not show.
  Discovery skips `__pycache__` and never inspects bytecode, so a record
  describes only the source file. Open question 8 offers a flag.
- The manifest fields are the literal text of the file. Code that mutates the
  dictionary through a call, such as `__manifest__.update(...)`, or that binds
  it dynamically through `globals()` or a star import, is invisible to static
  reading.
- `classes` is syntactic: bases named `BasicAgent`. The kernel's runtime
  selection is different (`perform`, name filters, instance validation).
- The kernel follows a symbolic link in its agents directory, including an
  `agents` link; the SDK never does. Such an agent appears only as a
  `REFUSE_SYMLINK` refusal, or not as live.
- `live` is observed when the file is inspected. A directory swapped during
  discovery can flip it; it carries no authority.
- On Windows the kernel's glob is also case-insensitive for file names, while
  the SDK's suffix match is not. Separately, the SDK refuses reads on hosts
  without `O_NOFOLLOW`.
- The `parsed` verdict belongs to the running interpreter. For example, PEP 695
  and PEP 701 syntax parses on 3.12 and later but not on 3.10. `parsed` is
  never a claim that the module compiles or loads: `return` at module level
  parses.
- On 3.11, a host that lowers `sys.setrecursionlimit` below about 150 can turn
  an in-bound source `invalid` (3.11's tree guard is three times the remaining
  recursion depth). Raising the limit changes nothing, because out-of-bound
  sources never reach the parser.
- The warning-suppression window uses `warnings.catch_warnings`, which is
  process-wide except on interpreters with context-aware warnings. The SDK
  serializes its own windows with a lock; another thread of the host that emits
  a warning during a parse can have it suppressed.
- The budget spent on a source that the tokenizer rejects follows the
  running interpreter's tokenizer, so after such a file the remaining budget
  can differ between interpreters.
- Reading and hashing stay bounded only by `max_entries` × 1 MiB, as for
  Portable Neurons today. Reading and hashing 200 files of 1 MiB took 0.8 s on Python 3.13, so a call at the 10,000-entry bound can spend about 40 s reading.
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
- Callers that do not send `agents` see no change except the embedded static
  API document.
- The Brainstem app and the G17 agent opt in with `agents: true` (CLI
  `--agents`). Against an SDK without this proposal, that request is refused
  with `REFUSE_INPUT_KEYS`, and the caller can fall back to reading nothing.

## 6. Rollback

Revert this branch's commits. §11 returns to its 1.0.0 text, the pins return
to `cf64a90f…8ef1`, `api.json` returns to 1.0.0, and every discover result
returns to 1.0.0 bytes. There is no persisted state to clean up. The token
`rapp-work-discovered-agent/1` is then retired and must never be reused for
another shape (Article 2).

## 7. Conformance and test vectors

### 7.1 Vectors

Each vector hashes the canonical text of a complete `discover` envelope, with
the scanned root's absolute path replaced by `<root>`. The trees are built by
functions in `tests/agent_trees.py`, which imports nothing from `rapp_work`,
so the same builders run against 1.0.0.

| Vector | Input | SHA-256 |
|---|---|---|
| 1.0.0 envelope | `build_tree_without_agents` (a skill, a plugin, a neuron, and near misses: `Upper_AGENT.py`, `notes_agent.md`, `old_agent.py.bak`, a directory named `folder_agent.py`, a symbolic link named `link_agent.py`, a FIFO named `pipe_agent.py`), computed with the unmodified 1.0.0 code at `29ead23` | `104820080267095c3d8aee9b05934957b26c9e18f5b6ac267f3019e8d03921ba` |
| Default request, without `api` | Both `build_tree_without_agents` and `build_mixed_tree` (the same plus base class, hello, broken, 200,000-term chain, nested draft, hard-linked, and oversize agent files). Same value from 1.0.0 and from this branch | `592c18208d8fdbd43bab6416459d6f99226320f74abad3319013207b254b1a36` |
| Default request, 1.0.0 `api` restored | This branch's result for both trees, with `api` replaced by the 1.0.0 static API document | `104820080267095c3d8aee9b05934957b26c9e18f5b6ac267f3019e8d03921ba` (the 1.0.0 envelope) |
| 1.0.0 static API document | `canonical_sha256` of the 1.0.0 `api.json` value, reproduced from this branch's document by undoing the two changes | `aba158699a5b6760aafada5874517e1b49df6fd0c281426ea2191f21c5a7e34d` |
| Agent records, without `api` | `build_agent_tree` with `agents: true` (base class, literal manifest, syntax error, latin-1 declaration, 200,000-term chain, nested draft, and a copy outside `agents/`) | `9569e81b2f16a49e815816c3e1ae6072d107f8944f22e666f5e01da7d9c72af7` |

The last two vectors leave out `api`, so they survive sibling proposals that
change `api.json`. All values are identical on 3.10 and 3.13.

### 7.2 Tests

`tests/test_discovery_agents.py` (27 test functions, 32 cases) and
`tests/test_python_source.py` (12 functions, 37 cases), with tree builders in
`tests/agent_trees.py`, which imports nothing from `rapp_work`:

- **Gate.** Default `discover` ignores agent files exactly as 1.0.0 does (the
  vectors above); the static API differs from 1.0.0 only by the `agents` input; the
  `agents` member appears exactly when requested; `agents` must be a Boolean; the CLI
  sends it only with `--agents`.
- **Position.** Top-level `agents/*_agent.py` files are live and subfolders are
  organization; `live` is relative to each scanned root and follows the file system's
  own name resolution.
- **Metadata.** The base-class file; `BasicAgent` subclasses by syntax only, in
  code-point order; the class bound counts distinct names; literal manifest fields and
  their exact display bounds; non-literal, ambiguous, and oversized manifests are
  never evaluated.
- **Inertness.** Agents with side effects never run or enter `sys.modules`; tripwires
  on import, compile, exec, eval, and runpy record nothing.
- **Verdicts.** Invalid, unsupported-encoding, over-limit, and over-budget sources are
  recorded without parsing trust; the verdict follows the running interpreter; host
  warning filters and concurrent calls change nothing.
- **File system.** Symbolic links, FIFOs, hard links, directories named like agents,
  unreadable files, and undecodable names are refused deterministically.
- **Output.** Closed, canonical, inert records, sorted and deterministic; the golden
  vector; agent files share the `max_entries` bound.
- **Measure (§11.2).** 21 samples measure identically on every interpreter (fields,
  conversions, nested and adjacent literals, quotes of either kind inside fields,
  including a lone quote inside a triple-quoted string); the nesting bound is exact at
  256 for six constructions; siblings do not accumulate nesting; the tokenizer's
  indentation limit; the exact cost bound; the decimal-digit bound whatever the host's
  integer digit limit; the replacement-field bound per run of adjacent literals;
  hostile chains never reach the parser in a child with a 512 KiB thread stack and a
  recursion limit of 1,000,000; the Portable Neuron guard; the call budget spent in
  order and charged for every measure; a NUL source is `invalid` before any budget
  check; the budget is 64 files at the per-file bound.

### 7.3 Cross-interpreter and corpus evidence

- **Five interpreters.** Every distinct `*_agent.py` anywhere in RAR at `ecf5f52`
  (1,878 files by content) yields the same token stream and the same measure on
  Python 3.10.20, 3.11.16, 3.12.13, 3.13.15, and 3.14.7, and all of them are within
  the bounds. The 21 measure samples and the six exact nesting edges of
  `tests/test_python_source.py` also give the same values on all five.
- **Fixed vectors.** The §7.1 values reproduce on 3.13 and 3.10.
- **Corpus through the API.** `discover` with `agents: true` over RAR's `agents/`
  returns 1,843 records, all `parsed`; 1,819 manifests are `literal`, 23 `absent`, and
  1 `ambiguous`; none is `live`, because RAR keeps agents in subfolders; there are no
  refusals. The measured costs are in section 4.

### 7.4 Mutation proof

A scratch harness outside the repository applied each mutant as a controlled
textual edit. It ran `tests/test_discovery_agents.py`,
`tests/test_python_source.py`, and `tests/test_discovery_neuron.py` on
Python 3.10 and 3.13, restored the original bytes, and verified each file's
SHA-256. The suite was green before and after.

| ID | Mutant | 3.13 | 3.10 |
|---|---|---|---|
| M1 | import the agent file (importlib exec_module) before parsing | killed | killed |
| M2 | exec the compiled source, then parse | killed | killed |
| M3 | every agent live | killed | killed |
| M4 | live for any directory named agents at any depth | killed | killed |
| M5 | drop the kernel glob's hidden-name rule | killed | killed |
| M6 | treat basic_agent.py as an ordinary agent | killed | killed |
| M7 | eval non-literal manifests | killed | killed |
| M8 | skip the literal validator | killed | killed |
| M9 | ignore rebinding and mutation sites | killed | killed |
| M9b | ignore repeated constant keys | killed | killed |
| M9c | drop the manifest node and depth bound | killed | killed |
| M9d | stop at the first bound hit (order-dependent precedence) | killed | killed |
| M9e | manifest bounds off by one (>=) | killed | killed |
| M9f | manifest depth bound loosened by 4 | killed | killed |
| M9g | drop parameter bindings of __manifest__ | killed | killed |
| M9h | drop class, except-handler, and match-capture bindings | killed | killed |
| M9i | drop match-mapping rest bindings | killed | killed |
| M9j | drop type-parameter bindings (3.12+) | killed | survived |
| M10 | drop the encoding-declaration check | killed | killed |
| M10b | reject utf-8- prefixed declarations (utf-8-sig) | killed | killed |
| M11 | decode leniently | killed | killed |
| M12 | drop the NUL pre-check in the agent parse | killed | killed |
| M13 | let host warning filters reach the parser | killed | killed |
| M13b | drop the parse lock around the warning filters | killed | killed |
| M14 | drop the surrogate and noncharacter filter | killed | killed |
| M15 | raise the 1 MiB read bound | killed | killed |
| M16 | drop the class bounds | killed | killed |
| M16b | classes in first-occurrence order | killed | killed |
| M17 | emit agents without the opt-in | killed | killed |
| M18 | inspect agent files in walk order (unsorted) | killed | killed |
| M19 | agent files do not count toward max_entries | killed | killed |
| M20 | walk follows symbolic links to files | killed | killed |
| M21 | accept hard-linked files | killed | killed |
| M23 | inspect agent files without the opt-in | killed | killed |
| M24 | lexical live directory (round-1 rule) | killed | killed |
| N1 | drop the nesting bound | killed | killed |
| N2 | drop the per-file cost bound | killed | killed |
| N3 | 3.10/3.11: read an f-string as one plain string (no field scanner) | survived | killed |
| N4 | drop the replacement-field bound | killed | killed |
| N5 | drop the decimal-digit bound | killed | killed |
| N6 | drop the line-length weighting inside formatted literals | killed | killed |
| N7 | never exhaust the call budget | killed | killed |
| N8 | charge the budget only for sources that are parsed | killed | killed |
| N9 | report budget exhaustion as over-limit | killed | killed |
| N10 | drop the Portable Neuron guard | killed | killed |
| N11 | neuron guard decodes UTF-8 instead of PEP 263 | killed | killed |
| N12 | commas do not reset siblings | killed | killed |
| N13 | replacement fields of one literal accumulate | killed | killed |
| N14 | lambda parameters reset at commas | killed | killed |
| N15 | elif clauses do not nest | killed | killed |
| N16 | drop the tokenizer's indentation limit | survived | killed |
| N17 | field scanner ignores quotes inside expressions | survived | killed |
| N18 | field scanner ends triple-quoted strings at one quote | survived | killed |
| N19 | adjacent string literals add instead of taking the largest | killed | killed |
| N20 | keywords add no nesting | killed | killed |

All 55 mutants are killed on at least one interpreter. Five survive on one interpreter only because the code they mutate does not run there: M9j (type-parameter bindings) on 3.10, which has no type parameters, and N3, N16, N17, and N18 (the port of CPython's f-string scanner and the tokenizer's indentation limit) on 3.13, which tokenizes f-strings itself and enforces its own limit.

### 7.5 Local CI

The local mirror of the `kody-w/rapp-work` workflow job (`tools/check.py`,
`pytest -q`, `ruff check`, `mypy`, `tools/release_inventory.py --check`,
`python -m build`, and `tools/verify_package.py`) ends
`ALL RAPP-WORK CI STEPS PASS: 3.13 3.10`: 237 tests passed and 1 was skipped,
with 69 subtests, on Python 3.13 and on Python 3.10 (the 169 tests of `main`
plus the 69 new cases; the skipped case needs a Linux file system to create a
non-UTF-8 file name). `tests/test_python_source.py`,
`tests/test_discovery_agents.py`, and `tests/test_discovery_neuron.py` also
pass on Python 3.11.16, 3.12.13, and 3.14.7 (72 passed, the same case skipped).
GitHub CI does not run for branch pushes in this repository.

## 8. Reference implementation and gating

- `src/rapp_work/_python_source.py` (new, private): the §11.2 measure. It
  reads the running interpreter's tokens; on 3.10 and 3.11 it expands f-strings
  with a port of CPython's `fstring_find_literal` and `fstring_find_expr`
  (`Parser/string_parser.c`, identical in 3.10 and 3.11 apart from a warning
  argument).
- `src/rapp_work/agent_files.py` (new): `DiscoveredAgent`, `ParseBudget`,
  `live_directory`, and `inspect_agent_entry`.
- `src/rapp_work/discovery.py`: agent files are collected only when `agents`
  is true, then inspected in code-point order of path and root with one budget.
  Without `agents`, `*_agent.py` files take the unchanged 1.0.0 path.
- `src/rapp_work/neuron.py`: `PortableNeuron.inspect` measures the text before
  its unchanged `ast.parse`.
- `src/rapp_work/api.py`, `src/rapp_work/cli.py`, `src/rapp_work/data/api.json`:
  the `agents` input and `--agents`.
- The module names match neither `*_agent.py` nor `agent.py`, so the SDK never
  classifies its own source. No new top-level export; `rapp_work.__all__` is
  unchanged.
- **Gating.** Agent discovery is opt-in: only a request with `agents: true`
  gets agent records or agent refusals, and 1.0.0 refuses that request. The
  default is unchanged and fail-closed. The Portable Neuron guard is not
  opt-in: it only refuses sources that could crash or exhaust the process, and
  every neuron within the bounds is inspected exactly as before. Tests cover
  both sides of each gate. The branch is experimental and is not merged; the
  owner decides.
- Documentation updated: `README.md`, `AGENTS.md`, `CLAUDE.md`,
  `docs/API.md`, `docs/ARCHITECTURE.md`, and `CHANGELOG.md` ("Unreleased
  (proposal, not accepted)").

## 9. Related proposals

Sibling drafts on `kody-w/rapp-work`, read at their pushed heads (none is
edited here):

| Gap | Branch and head | Files shared with this branch | How they compose |
|---|---|---|---|
| G1 | `experimental/gap-g1-roster-declaration` at `1899e52` | `CHANGELOG.md`, `README.md`, `RELEASE-INVENTORY.json` | Textual only. |
| G2 | `experimental/gap-g2-move-action` at `8b3c361` | SDK SPEC (its §2, §4, and §7 insertions), its pins, `api.py`, `cli.py`, `data/api.json`, `docs/API.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, `README.md`, the inventory | Different operations (`update` against `discover`) and different SPEC anchors: keep both sides of each hunk, then recompute the SDK SPEC pins. |
| G4 | `experimental/gap-g4-migration-successors` at `be1772b` | `api.py`, `cli.py`, `data/api.json`, `docs/API.md`, `CHANGELOG.md`, `README.md`, the inventory | Different operations (`migrate` against `discover`); keep both sides. |
| G6 | `experimental/gap-g6-owner-succession` at `8e5e44e` | SDK SPEC (its §5.1, and a §12 paragraph inserted right after the "## 12. Refusals" heading, next to this branch's insertion before that heading), its pins, `docs/API.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, `README.md`, the inventory | A merge may conflict at the §11/§12 boundary; keep §11.1 and §11.2 before the §12 heading and G6's paragraph after it. |
| G7 | `experimental/gap-g7-instruction-inventory` at `68b549c` | SDK SPEC (its §4, §7.1 to §7.6, and §12 insertions), its pins, `api.py`, `cli.py`, `data/api.json` (its new `verify` input and a new refusal line; this branch rewords the neighbouring "plugin, skill, or neuron execution" line), `docs/API.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, `README.md`, the inventory | As for G6 at the §11/§12 boundary; keep both refusal lines in `data/api.json`. |
| G11 | `experimental/gap-g11-workspace-index` at `e3909b3` | `CHANGELOG.md`, `README.md`, the inventory | Naming only. |
| G17 | `experimental/gap-g17-brainstem-sdk-agent` at `c75b4d7` | `CHANGELOG.md`, `README.md`, the inventory | Its Brainstem agent calls `discover`; once this proposal is accepted it may pass `agents: true` to list agents. |

Recommended order: this proposal is semantically independent and may land in any
order; merge it before G17 if G17 lists agents. Every merge recomputes the SDK SPEC
pins in `protocols/index.json` and `src/rapp_work/data/profiles.json` and runs
`python3 tools/release_inventory.py --write`.

## 10. Open questions for the owner

1. **Article 2 reading.** Is the operation's accepted input set part of what
   `rapp-work-sdk/1` denotes? If yes, this proposal (and G2 and G4) moves to a
   new label (option e).
2. **Bounds.** Nesting 256 (real agents reach 79), cost 131,072 per file (real
   agents reach 44,813), 640 decimal digits, 1,024 replacement fields per run,
   and a call budget of 8,388,608 (the whole RAR catalog needs 4.9 million).
   Should the budget be smaller, trading throughput for a shorter worst case?
3. **`live` for the base class.** `live` stays purely positional, so a
   top-level `basic_agent.py` is `live: true` and `role: "base-class"`: the
   kernel does import it on every sweep. The alternative forces `live: false`
   for the base class.
4. **§12.** "Agent execution" could join §12's list of explicit refusals. §12
   was left untouched because gaps G6 and G7 edit that paragraph.
5. **Catalogs.** Advertising single-file agents in a signed
   `rapp-work/1-catalog` needs an upstream `kody-w/rapp-1` revision under a
   new token. This proposal does not do that.
6. **Parser version.** Should the SDK pin a parser `feature_version`, so that
   `syntax` agrees across interpreters for newer syntax, at the cost of
   rejecting syntax that a newer Brainstem would load?
7. **Neuron budget.** Portable Neurons get the per-file bounds but no call
   budget, so that default `discover` keeps its 1.0.0 results. Should a
   later revision give neurons a budget too?
8. **Bytecode flag.** Should a record say when `__pycache__` beside a live
   agent holds bytecode the kernel may prefer (section 4)? That needs a
   bounded, no-follow listing of `__pycache__`, which discovery skips today.

## 11. Owner actions needed

1. Review §11.1 and §11.2 on `experimental/gap-g3-agent-discovery` and accept
   or refuse them (Open questions 1–8).
2. If accepted: merge through the owner's own process (section 9 suggests an
   order), then release. Bump `pyproject.toml` and `SDK_VERSION`, add the
   dated CHANGELOG entry, and run `tools/release_inventory.py --write`.
3. Report G3 as `proposed` now, and `fixed` after the release. The
   Constitution agent owns the organism file.
4. No signing action: the frozen signed registry does not pin
   `rapp-work-sdk/1`.

## 12. Ready-to-file pull request text

**Title:** `rapp-work-sdk/1` §11.1–11.2: opt-in inert discovery of
single-file agents, and bounded parsing (G3)

**Body:** Adds opt-in `rapp-work-discovered-agent/1` records to `discover`
(`agents: true`) for Brainstem single-file agents (`*_agent.py`). They are
parsed, never imported, compiled, or executed. Records carry hashes, a parser
verdict, `BasicAgent` subclass names, a literal `__manifest__` subset, a
positional `live` flag, and the base-class role. Every parse of discovered
Python, including Portable Neurons, is preceded by a token-level measure with
fixed nesting, cost, integer, and replacement-field bounds, which removes a
process crash on Python 3.10 and bounds time and memory per file and per call.
Requests without `agents` return their 1.0.0 results apart from the embedded
static API document (vectors `592c1820…1a36` and `10482008…21ba`). The SDK
specification pins follow the new §11 bytes; the frozen signed registry is
unaffected. Full rationale: `docs/proposals/0003-sdk-agent-discovery.md`.

## 13. References

- `kody-w/rapp-work` at `29ead23`: `protocols/rapp-work-sdk/1/SPEC.md` §§2,
  11, and 12; `src/rapp_work/discovery.py`; `src/rapp_work/neuron.py`;
  `src/rapp_work/api.py`; `src/rapp_work/data/api.json`;
  `docs/ARCHITECTURE.md` ("Inert extension model"); `AGENTS.md`;
  `CONTRIBUTING.md`.
- `kody-w/rapp-1`: `CONSTITUTION.md` Articles 2, 4, 6, 7, 8, 10, and 18;
  `protocols/rapp-work/1/SPEC.md` §§3 and 10 at `591e014`.
- `kody-w/rapp-installer` `rapp_brainstem/brainstem.py` at `brainstem-v0.6.9`
  (lines 67, 1021–1048, and 1202–1205) and at `brainstem-v0.6.16` (lines 441,
  1659–1669, 1832–1835, 3025–3028, and 3055–3056).
- `kody-w/RAR` at `ecf5f52`: `build_registry.py` `extract_manifest`;
  `CONSTITUTION.md` Article IV; the `*_agent.py` corpus used in section 7.3.
- CPython `Parser/string_parser.c` (3.10 and 3.11 branches):
  `fstring_find_literal`, `fstring_find_expr`, `fstring_compile_expr`; the
  tokenizer limits `MAXINDENT` (100) and `MAXLEVEL` (200).
- PEP 263 (source code encodings), PEP 552 (hash-based `.pyc`), PEP 701
  (f-string grammar), PEP 750 (template strings); RFC 7493 (I-JSON); RFC 8785
  (JCS).
