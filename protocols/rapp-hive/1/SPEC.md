# RAPP Private Hive
## Shared GODD, frame convergence, and multi-channel projection profile

**Protocol identifier:** `rapp-hive/1`  
**Status:** Normative RAPP/1 operational profile  
**Parent:** [`rapp/1`](https://github.com/kody-w/rapp-1/blob/main/SPEC.md)  
**Schema:** [`schema.json`](schema.json)

RAPP Private Hive defines the access-restricted, off-device portion of a RAPP
workspace. It is a **GODD estate**, not a DOGG publication surface. A user
selects which local GODD material becomes Hive-shared GODD; authorized members
may then verify and assimilate that shared slice into their own local GODD.

The same Hive may be projected through private Git, SharePoint, NAS, LAN, or
other stores. These are channels for one authority, not independent Hives.
Dream Catcher convergence gathers immutable frames from temporary local
dimensions and produces one signed successor on the Mother Hive stream.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, and **MAY** are
used as defined by RAPP/1 section 2.

## 1. RAPP/1 foundation

An implementation:

1. **MUST** use the exact eleven-key `rapp/1` frame envelope.
2. **MUST** canonicalize payloads with RAPP/1 section 4 and identify them with
   `H("rapp/1:particle", payload)`.
3. **MUST** register this profile and its exact kinds in the adopting estate's
   signed section 13 registry.
4. **MUST** carry every authoritative declaration, GODD slice, assimilation,
   convergence, and projection receipt in a signed frame. Unsigned documents
   are drafts or caches only.
5. **MUST NOT** add a transport endpoint beside `POST /chat`; Git, SharePoint,
   SMB, filesystem, and HTTP are artifact stores or frame logs.
6. **MUST** use RAPP/1 cross-stream Dream-Catcher order: ascending `utc`, then
   ascending `frame_hash`.
7. **MUST NOT** repair, reparent, mutate, or discard a received RAPP/1 frame.
8. **MUST** refuse in favor of RAPP/1 whenever this profile conflicts with the
   parent specification.

An adopting estate registers these **eight exact kinds**, bound to the `body`
family, and pins this specification's exact SHA-256 in its signed section 13
`protocol` entry:

| Kind | Only permitted payload schema |
| --- | --- |
| `hive.declaration` | `rapp-hive/1-declaration` |
| `hive.object` | `rapp-hive/1-object` |
| `hive.godd-slice` | `rapp-hive/1-godd-slice` |
| `hive.assimilation` | `rapp-hive/1-assimilation` |
| `hive.convergence` | `rapp-hive/1-convergence` |
| `hive.reconciliation` | `rapp-hive/1-reconciliation` |
| `hive.projection` | `rapp-hive/1-projection` |
| `hive.template` | `rapp-hive/1-template` |

Being a registered kind does not authorize carrying another kind's schema.
The profile requires signatures even where RAPP/1 would otherwise permit
`sig:null`. These are subordinate registered payload extensions, **not** a new
envelope, wire API, signature format, identity namespace, or registry-entry
type. The two derived catalog/manifest schemas below are particle commitments,
not additional frame kinds.

The hardening closes pre-adoption draft payloads. A draft lacking the base
catalog commitment or carrying an unsigned reconciliation is not accepted
through a legacy lane. Any estate that adopted incompatible prior bytes must
perform the parent specification's migration/retirement procedure before
adopting these bytes; it must not silently treat an old schema as this one.

## 2. The three boundaries

1. **Local RAPP workspace** — the full on-device GODD. Material stays here
   unless its owner explicitly selects it.
2. **RAPP Private Hive** — the restricted collaborative workspace. It may
   contain both DOGG and explicitly shared GODD objects.
3. **DOGG** — a separately generated, globally public-facing projection. DOGG
   **MUST NOT** contain PII, secrets, credentials, private prompts, plaintext
   GODD, or data whose global-publication rights are unproven. Hive membership,
   a private repository push, or a Hive frame never authorizes DOGG publication.

The default transfer is copy. Moving or withdrawing a Hive slice **MUST NOT**
erase the owner's local source or rewrite accepted history.

DOGG and GODD classify data, not storage locations. A DOGG object remains
PII-free and globally safe even when it is held inside a restricted Hive. A
GODD object remains private data even when authorized Hive members share it.
Moving an object between local workspace and Hive does not change its data
class.

## 3. Declaration

`rapp-hive/1-declaration` names one Hive, its hard `world_id`, one owner, its
members, sealed rooms, channels, and policy. Members, rooms, and channels are
sorted by stable id. Exactly one channel has role `authority`; other channels
are writable contribution endpoints, mirrors, caches, or backups.

A member is a RAPP identity, not a human-only account. The protocol makes no
capability distinction between a person, AI, agent, service, or hybrid team
holding an authorized RAPPID. Roles, rooms, signatures, provenance, and policy
govern access. An implementation **MUST NOT** reduce collaboration rights merely
because an authorized member is non-human, and **MUST NOT** grant extra authority
merely because a member is human.

Supported channel kinds are `github`, `sharepoint`, `nas`, `lan`, `local`, and
`custom`. A locator is transport metadata, not identity. Changing a URL, mount,
tenant, repository, or server **MUST NOT** change the Hive rappid or any
artifact address.

The declaration policy is closed:

```json
{
  "godd_sharing": "explicit",
  "default_godd_scope": "local-only",
  "external_publication": "disabled",
  "conflict_mode": "explicit",
  "default_transfer": "copy"
}
```

`default_godd_scope:"local-only"` is load-bearing. The most sensitive GODD
never moves merely because a workspace joined a Hive. Each shared slice is a
separate affirmative act.

### 3.1 Sealed rooms

A room is a scoped area with a sorted member subset. `access:"repository"`
permits member-visible objects inside the repository's access boundary;
`access:"sealed"` additionally requires encrypted room objects. Rooms may
overlap. A four-member Hive may have a sealed room whose encrypted slices are
decryptable by only two named members.

All repository collaborators may be able to observe the sealed egg ciphertext,
hashes, room id, and non-sensitive routing metadata. That visibility grants no
plaintext access. The key service releases a slice DEK only to a recipient
whose keyed RAPPID is both:

1. a current member of the declared room; and
2. present in the slice's explicit audience.

Repository access, branch access, possession of ciphertext, or membership in a
different room is insufficient.

## 4. The Hive as an organic RAPP/1 workspace object

The Hive is itself a RAPP/1-identified workspace object that can present any
verified RAPP/1 object. `rapp-hive/1-object` is the generic membership record.
It names:

- the object's own RAPPID;
- one typed RAPP address (`rapp/1:particle`, `rapp/1:wave`, or
  `rapp/1:egg-manifest`);
- the object's registered or application kind;
- its target path in a member or shared area;
- its room and audience;
- its data class (`dogg`, `godd`, or `neutral`);
- its PII status and optional scan-evidence hash;
- its protection mode; and
- source frames and mutation keys for provenance and convergence.

Agents, skills, projects, frames, eggs, neighborhoods, rapplications, GODD
schemas, DOGG projections, tools, knowledge, media, and future registered RAPP
objects can all enter through this one rule. The profile does not prescribe a
fixed taxonomy. Members may reorganize their own areas and grow new structures
organically as long as RAPP identity, content addressing, world boundaries,
audience, provenance, and append-only history remain valid.

`protection:"member-visible"` is permitted in a repository-access room.
`protection:"sealed-room"` requires a sealed room and a signed RAPP/1 sealed
egg address. Unknown object kinds are not inferred; they must resolve through
the adopting estate's registry or remain untrusted application data.

A generic object classified `godd` **MUST** use `sealed-room` protection.
`rapp-hive/1-godd-slice` is the richer GODD specialization when assimilation,
plaintext schema, record count, and source-layer semantics are required. A
`dogg` object may be member-visible, but it still must satisfy the global
PII-free DOGG rule: `pii_status` is `none` and `pii_evidence_hash` binds the
sanitization or detection evidence used for that decision.

## 5. Hive-shared GODD slices

`rapp-hive/1-godd-slice` describes one immutable, owner-selected slice of GODD.
The frame contains only non-sensitive routing and verification metadata. The
actual GODD bytes **MUST** be a signed RAPP/1 `sealed` egg:

- `content.sealed_egg_hash` is its `rapp/1:egg-manifest` address;
- `content.artifact_rappid` is the keyed identity that signs the sealed egg;
- confidentiality uses RAPP/1 AES-256-GCM and scoped key release;
- the DEK, credentials, plaintext, and private source paths **MUST NOT** appear
  in the frame, Git history, channel locator, catalog, or projection receipt.

The slice classification is always `estate:"godd"` and
`scope:"hive-shared"`. Sharing does not turn GODD into DOGG. Every slice names
one room. Its audience is a sorted, non-empty subset of both current Hive
members and that room's members. Key release is authorized only for that
audience and may be narrower than repository read access.

`source_frames` preserves the RAPP/1 addresses from which the slice was
derived. `mutation_keys` declares the logical entities or invariants the slice
changes; Dream Catcher uses them to detect semantic conflicts.

## 6. Assimilation into another GODD

`rapp-hive/1-assimilation` records that an authorized recipient verified,
decrypted, and injected a Hive slice into a local workspace. Assimilation:

- **MUST** verify the slice frame, sealed egg, publisher signature, audience,
  key release, plaintext commitment, and world boundary before use;
- **MUST** mount the slice under an explicit local namespace;
- **MUST** preserve the source slice particle hash and resulting local layer
  hash;
- **MUST NOT** overwrite unrelated personal GODD;
- **MUST** use `overlay`, `copy`, or `materialize` mode with explicit
  precedence;
- **MUST NOT** imply that the recipient owns or may republish the source data.

A workspace may generate DOGG from its authorized GODD layers only when every
included slice independently allows DOGG projection and a separate publication
policy authorizes it. The projection pipeline **MUST** still remove and refuse
PII; `dogg_projection_allowed:true` is permission to evaluate a slice, not proof
that its raw fields are safe to publish.

## 7. Dimensions and the Mother Hive

A device, branch, contributor area, or access channel may evolve temporarily as
a **dimension** of one Hive. A dimension has its own RAPPID and immutable local
frames, but it is not a new authoritative Hive.

The **Mother Hive** is the one registered authority stream. Its signed
`hive.convergence` frame is the linearization point that accepts a new
canonical successor. Git may carry branches, commits, authorship, review, and
conflict evidence, but signed RAPP frames and the registered Mother Hive head
remain semantic authority.

## 8. Dream Catcher convergence

### 8.1 Shape is not acceptance

`rapp-hive/1-convergence` is a **proposal** until its signed Mother Hive frame
passes authenticated evaluation. `validate_convergence`, JSON Schema, the
payload CLI, a particle hash, and a candidate's asserted `accepted` decision
prove no acceptance. Structural validation deliberately does not infer
conflicts from unverified summaries or pretend a hex string is a signature.
The CLI reports `authenticated:false`.

Authenticated acceptance requires all of:

1. A verified, fresh section 13 registry anchored out of band, with persisted
   sequence/hash protection against rollback and same-sequence forks.
2. The owner-signed declaration at the Mother's registered creation genesis.
   In the direct-owner profile, the declaration owner is the anchored estate
   owner. Mother Hive `stream_id` is exactly `hive_rappid`.
3. The locally accepted Mother frame head, last convergence particle hash (or
   null immediately after the declaration), and derived catalog commitment.
   A bare caller-supplied catalog or accepted-frame list is not a checkpoint.
   Recovery replays signed Mother history and verifies all its dependencies.
4. Candidate bytes and complete authenticated ancestry, not only the
   `candidates` array's summaries.
5. A signed `hive.convergence` frame that is the **single next** Mother frame.
   Its `base_head_frame_hash`, `base_convergence_payload_hash`, and required
   `base_catalog_hash` must equal the locally accepted state. A competing
   successor prepared against the same old base is refused after the first
   commits, even if it is validly owner-signed.

The compare-and-swap is the linearization point. Validate first; commit the
head, signed decisions, derived catalog, replay ledger, and conflict backlog
atomically. Failure must leave the accepted state unchanged. Implementations
sharing storage need a storage-level transaction/lock; a per-process lock alone
does not coordinate other writers.

### 8.2 Candidate verification and authorization

Candidates are `hive.object`, `hive.godd-slice`, or `hive.reconciliation`
catalog mutations. Assimilation, declaration, template, convergence, and
projection receipts are not disguised catalog candidates.

For each candidate independently:

- Resolve its complete sequence of immutable frame bytes from the sole active
  registered genesis through the named wave. Refuse absent ancestors,
  noncontiguous `seq`, wrong `prev` particle, wrong registered genesis,
  timestamp regression, invalid signature, or a cross-stream chain. Verify
  the parent RAPP/1 `prev_wave` rule unchanged; this body's off-swarm value
  remains null. Do not synthesize a missing parent from summary fields.
- Check every eleven-key envelope, particle hash, wave hash, detached JWS,
  registry SPKI/RAPPID binding, and time-scoped revocation.
- Bind `dimension_rappid == stream_id == actual frame.stream_id`, with a
  registered body-stream RAPPID distinct from the Mother. Every summary
  `seq`, `utc`, `payload_hash`, `frame_hash`, and `mutation_keys` must match
  the signed bytes. Channel observations must name declared channels.
- Bind payload Hive/world to the authenticated declaration and payload time
  to envelope time. Object/slice JWS `kid` must equal `producer_rappid`, whose
  current role is owner/member (not viewer) and whose identity is in the
  selected room. Object targets must be below the producer's member area or
  selected room area; the owner may also target another declared member area.
- Resolve signed `source_frames` and reconciliation parents recursively;
  verify their summaries, signatures, Hive/world, and time ordering. Hash
  references alone are not causal proof. Only registered Hive mutation
  frames establish causal edges in this reference gate. External local
  source material needs upstream verification and a signed Hive
  representation; unknown kinds are not inferred as trusted provenance.
- Require every previously unsettled ancestor to be offered as a candidate.
  A verified chain cannot silently add unoffered mutations to the catalog.
  A new descendant must extend the exact previously settled dimension head.
  Competing same-stream positions are quarantined, even with disjoint mutation
  keys; a RAPP stream fork cannot be repaired with an ordinary Hive merge.

An invalid candidate is `quarantined`. Exclude it **and dependent candidates
that cannot stand without it** before constructing mutation conflict sets.
Repeat dependency pruning after rejecting a reconciliation. Malformed
summaries cannot inject keys that block an independent authenticated update.
A structurally malformed convergence envelope is still refused as a whole.

### 8.3 Causality, conflicts, and signed reconciliation

Sort candidate descriptors by `(utc, frame_hash)` and require one descriptor
per wave; aggregate duplicate channel observations in its sorted channel list.
This is presentation order, not last-write-wins or proof of causal order.
Verify the whole graph before classifying it, including equal-UTC updates whose
hash order places a child before its parent.

Two changes of a mutation key are sequential when one is a verified causal
ancestor of the other. Their differing payload hashes do **not** make them a
conflict. Two incomparable frames changing the same key are concurrent.
Equal payload hashes on different waves are not a replay exemption.

Build connected components by shared mutation keys over new verified ordinary
mutations and active previously accepted frames. If a component has a
concurrent pair, preserve the **entire atomic component**: all participating
frames and all their mutation keys, including causally intermediate parents
and the other effects of multi-key frames. Previously accepted history is
never removed. A component consisting only of causal updates is additive.

The closed `rapp-hive/1-reconciliation` payload has exactly:

| Member | Meaning |
| --- | --- |
| `schema` | `rapp-hive/1-reconciliation` |
| `hive_rappid`, `world_id` | The authenticated declaration's ownership boundary |
| `resolver_rappid` | The authorized owner JWS signer |
| `created_utc` | The reconciliation envelope's timestamp |
| `base_head_frame_hash` | Exact Mother head being reconciled |
| `parents` | Sorted, unique wave hashes of **every** frame in one conflicting component |
| `mutation_keys` | Sorted union of **all** those parents' mutation keys |
| `result` | Closed `{space, hash}` typed address of the reconciled artifact |

It travels only in a signed `hive.reconciliation` frame. An unsigned frame,
ordinary object wearing a resolution summary, non-owner resolver, stale base,
omitted/extra parent, or incomplete mutation set is quarantined. The resolver
does not name itself as a parent. Two competing resolvers for one component
are both quarantined; timestamp/hash sorting cannot choose an owner decision.
Independent components may be resolved independently.

The convergence's `resolutions` array is derived from accepted reconciliation
bytes, not independent authority. For each resolved mutation key shared by at
least two component parents it records exactly that sorted parent subset and
the accepted resolver wave. Single-parent side effects are still covered by
the reconciliation's signed complete mutation set.

Decisions are mechanically checked:

- `accepted`: a new compatible ordinary mutation or complete authorized
  reconciliation, contributing its frame to the catalog.
- `duplicate`: an exact previously settled frame, including a previously
  accepted frame later superseded or an already recorded superseded parent.
  **It must not be marked accepted again** or reopen an old conflict.
- `conflict`: a new member of an unresolved authenticated component.
- `quarantined`: invalid evidence or an unsatisfied dependency; no catalog
  contribution and no conflict-blocking authority.
- `superseded`: a new component parent replaced by its accepted reconciliation.
  This does not remove any previously accepted catalog frame.

Every candidate gets one decision in `frame_hash` order. `reason_code` is
descriptive metadata, not permission to override the derived status.
Every previous unresolved candidate must reappear in the next proposal until
settled; simply omitting an old conflict is not reconciliation.
`status:"partial"` is required iff authenticated unresolved conflicts remain.
`converged` does not mean quarantined inputs were accepted.

### 8.4 Deterministic catalog commitment

The catalog is an append-only **accepted-frame index**, not an arbitrary
channel directory digest. Its closed particle has exactly:

- `schema:"rapp-hive/1-catalog"`;
- `hive_rappid` and `world_id` from the authenticated declaration; and
- `frames`: unique `{frame_hash, payload_hash}` pairs, sorted by `frame_hash`,
  taken from actual accepted frames.

The genesis catalog has an empty `frames` array. To evaluate a successor,
union the previous accepted-frame set with **only** new `accepted` decisions,
derive the pairs from verified bytes, and compute
`H("rapp/1:particle", catalog)`. `resulting_catalog_hash` must equal that value.
`duplicate`, `conflict`, `quarantined`, and newly `superseded` frames do not
add entries. Previously accepted entries are immutable even when a later
reconciliation replaces their current effect.

Replaying the same verified candidate set against the same accepted base
cannot change the accepted set or catalog hash. A repeated candidate in a
new successor is a duplicate; replaying the old Mother frame is refused.
Materialized views follow accepted causality/reconciliation, not an invented
last-write-wins ordering of ciphertext or object paths.

## 9. Multi-channel projection

`rapp-hive/1-projection` is a signed receipt for one channel. A current receipt
binds:

- the exact convergence payload hash;
- channel id;
- registry sequence;
- Mother Hive frame head;
- catalog hash; and
- complete artifact-manifest hash.

All current channels **MUST** expose the same verified identities and hashes.
A stale, partial, divergent, or tampered projection is surfaced and cannot
overwrite authority. A read-only mirror, cache, backup, or temporarily newer
local dimension never becomes authority by availability or timestamp.

### 9.1 Current receipt acceptance

`validate_projection` validates shape and optional advertised payload links.
Only authenticated current-receipt acceptance establishes currency. The
receipt is owner-signed on a separately registered body stream, not appended
to the Mother as an alternative convergence. That stream is bound to one
declared channel; accepted receipts are protected against replay/rollback/fork.
Its creation genesis may be an owner-signed `stale` or `failed` receipt with
unavailable hashes. It establishes stream identity **only**, never currency,
and avoids a circular registry → genesis → current-registry commitment.

A `current` receipt must match, simultaneously:

1. the authenticated registry's actual `registry_seq`, not any positive number;
2. the latest accepted convergence's particle hash;
3. the actual current Mother **frame** hash, not the convergence particle;
4. the derived catalog hash; and
5. the deterministically derived artifact-manifest particle hash.

The closed `rapp-hive/1-artifact-manifest` contains `schema`, `hive_rappid`,
`world_id`, `registry_seq`, `registry_hash`, `frame_head`, `catalog_hash`, and
`artifacts`. `registry_hash` is the particle hash of the authenticated registry
without `sig`, the same commitment persisted beside its monotonic sequence.
`artifacts` is a unique list of `{space, hash}` addresses sorted by
`(space, hash)`. It covers the signed registry particle **including** its
signature, every retained Mother/candidate/ancestor frame, every derived
catalog checkpoint, and all object/slice/reconciliation artifact addresses.
Authenticated conflict and superseded branches are retained; unavailable or
unauthenticated quarantine bytes cannot inject manifest entries. The manifest
does not include itself or its receipt, which would create a hash cycle.

The channel must supply the actual manifest and every listed artifact's
bytes. Verify particle addresses, exact signed frames and their ancestry, and
signed RAPP/1 egg addresses and viability. GODD metadata additionally binds
the sealed variant and, for slices, `artifact_rappid`. A re-signed receipt with
an omitted artifact, recomputed counterfeit manifest, stale head, fabricated
catalog, or tampered artifact is still refused. Shape validation or checking
only that these fields contain 64 hex characters is insufficient.

## 10. Storage portability

The canonical Hive is ordinary verified bytes: frames, signed registries,
sealed eggs, manifests, and derived indexes. Backends are adapters.

A conformant export/import or migration:

1. verifies the source authority;
2. copies bytes without mutation;
3. verifies every destination byte and head;
4. records a projection receipt;
5. switches an authority locator only through an owner-signed declaration; and
6. leaves source retirement as a separate explicit action.

One Hive may project simultaneously through private GitHub, SharePoint, NAS,
LAN, and local caches. Members may use different channels and still verify the
same Hive.

## 11. Git contribution loop

Git is the default contribution and reconciliation substrate:

1. pull and verify the registered Mother Hive head;
2. make local changes and append dimension frames;
3. commit with attributable authorship;
4. push a branch or proposal to a writable channel;
5. run Dream Catcher;
6. review explicit conflicts or quarantines;
7. append the signed Mother Hive convergence frame; and
8. resynchronize every channel.

A Git merge alone does not authorize a Hive state. A signed convergence frame
does. Non-fast-forward history rewriting, force-push loss, or deletion of
accepted frames is nonconformant.

## 12. Privacy and access limits

- A Private Hive may contain DOGG, GODD, and neutral RAPP objects. The Hive's
  restricted location does not alter an object's data class.
- Hive GODD may contain sensitive data approved for the declared audience.
- The default GODD scope is local-only; only explicitly selected slices enter
  the Hive.
- Plaintext GODD **MUST NOT** be broadcast. Shared GODD uses sealed eggs and
  scoped key release.
- Rooms create cryptographic sub-audiences inside one Hive. Ciphertext
  visibility to other repository collaborators does not grant plaintext
  access.
- Repository, SharePoint, SMB, or LAN authorization is necessary but not
  sufficient; artifact key release enforces the slice audience.
- Revocation stops future key release but cannot erase plaintext already
  decrypted by an authorized member, as required by RAPP/1 section 9.2.1.
- External or globally public publication is outside this profile and disabled
  by declaration policy.
- DOGG is always PII-free. A DOGG projection that contains PII is
  nonconformant regardless of source consent or Hive membership.
- Cross-`world_id` assimilation is refused.

## 13. PII-free Hive template eggs

`rapp-hive/1-template` records a reusable Hive template packaged as a RAPP/1
egg. A template is a DOGG projection of Hive structure, not a backup or clone
of the live Private Hive.

A conformant template:

- receives a distinct template RAPPID rather than reusing the live Hive
  identity;
- includes only objects classified `dogg` or `neutral`;
- requires `pii_status:"none"` for every DOGG object;
- binds an aggregate `pii_evidence_hash`;
- excludes every GODD slice, sealed-room ciphertext, member-specific access
  grant, key-service secret, DEK, credential, personal memory, and live channel
  locator;
- may retain reusable workspace structure, schemas, agents, skills, tools,
  project templates, room definitions without live members, and DOGG content;
  and
- is packed and verified under the existing RAPP/1 egg specification.

The template egg can be shared globally because its selected bytes are DOGG or
neutral and PII-free. Hatching it creates a new Hive identity and empty local
GODD layers; it never joins the recipient to the source Hive or grants access
to source GODD.

## 14. Conformance

An implementation claiming `rapp-hive/1` conformance must:

1. validate all eight closed authoritative payload schemas and both derived
   commitment schemas;
2. reproduce every RAPP particle hash;
3. verify authoritative signed frames and signer authorization;
4. use sealed RAPP/1 eggs for Hive-shared GODD bytes;
5. preserve explicit member audience and world boundaries;
6. order candidate frames by `(utc, frame_hash)`;
7. distinguish causal updates from concurrent conflicts, isolate quarantine,
   and require signed complete-parent reconciliation;
8. maintain one Mother Hive head across all dimensions;
9. verify every current channel against the same accepted hashes;
10. pass
    `python3 protocols/rapp-hive/1/reference/hive_conformance.py`.

### 14.1 Scalar domain and parity

Both schema and Python validation operate inside the parent's shared RAPP
I-JSON/canonical domain: bounded document size/depth, NFC strings, no duplicate
members or lone surrogates, and the reference implementation's exact-integer
domain. A bare JSON Schema library does not enforce this domain; apply it
first and enable `date-time` format checking. An integral Python float is not
an exact-integer reference input merely because JSON Schema calls it integer.

- Sequence numbers and record counts are integers in `0..2^53-1`, excluding
  booleans. Sealed plaintext byte count is `0..2^30`, inclusive.
- RAPPID owner length is `1..39`, slug length `1..100`; both use the parent's
  lowercase single-hyphen-separated grammar. Consecutive hyphens, uppercase,
  overlength components, and trailing newlines are invalid.
- Paths are NFC, `1..1024` characters, already canonical relative POSIX paths
  with no empty/`.`/`..` component, backslash, colon, control/DEL character,
  trailing dot/space component, or Windows reserved device name.
- Mutation keys are opaque NFC text, `1..512` characters, without control/DEL
  characters. They are **not** filesystem paths: punctuation and `/` have no
  implicit path authority. Arrays are sorted and duplicate-free. The same
  bounds apply to objects, slices, candidates, reconciliation, and summaries.

### 14.2 Reference gate and limits

`reference/rapp_hive.py` provides structural and local cross-document checks.
`reference/hive_acceptance.py` supplies `RegistryAuthority` and
`HiveAcceptance`; the latter resolves frame bytes, authenticates their graph,
derives proposals, and serializes `accept_convergence` / `accept_projection`.
`preview_convergence` produces a signing proposal, never an accepted head.
`checkpoint()` exposes the state to persist atomically; `restore()` reconstructs
it by re-verifying signed history, not by trusting a serialized frame list.

The direct-owner registry reference checks real detached JWS/SPKI binding,
the exact profile pin, kinds, active genesis, sequence floor/same-sequence
commitment, and signed tombstones. It fails closed on owner succession
records requiring a full time-scoped section 13 tenure verifier. A production
adapter must supply fresh registry retrieval, persistent high-water marks,
distributed storage CAS, retention, and the full parent verifier where those
features are needed. These are trust prerequisites, not Boolean payload
flags. No result here certifies key release, plaintext consent, global DOGG
publication, or full estate-wide RAPP/1 conformance.

Run the profile gate from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 protocols/rapp-hive/1/reference/hive_conformance.py
```

It runs the payload vectors, exact specification/schema index pins, real
Ed25519 positive/negative vectors, and Draft 2020-12/Python scalar parity
checks. The signed vectors require `cryptography` and `jsonschema`; missing
verification dependencies fail the suite rather than skipping authentication.
