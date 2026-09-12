# The RAPP Protocol Suite
### Unified normative specification of identity, canonicalization, the frame, the wire, and the egg

> **Generated/materialized view.** These exact UTF-8 bytes are carried inside
> the selected specification-revision frame in `anchor/chain.jsonl`. The frame
> chain proves integrity and lineage; canonical owner-ratified publication
> selects authority. Change the protocol by appending a successor frame, not by
> treating this file as independent authority.

**Status:** Owner-ratified RAPP/1 **rev-15 amendment**. It is effective iff the
prepared chain snapshot has been accepted onto canonical protected main under
the transition in §12.2. **Obsoletes / consolidates:**
`rapp-frame/2.0`, `rapp-frame/2.1`, `rapp-rappid-spec/2.0`, `rapp-protocol/1.0`, all scattered egg specs
(§9 subsumes them), and `OSI.md`. This is the current materialized view of the single living standard;
the consolidated specs are retired historical record (Protocol Constitution Article 6). Rev-14 becomes
the published current revision when the source merge and append-only anchor update carrying these exact
bytes complete.

**Rides existing standards; invents nothing:** requirement terms [RFC 2119]/[RFC 8174]; JSON restricted to
I-JSON [RFC 7493] over [RFC 8259]; canonicalization [RFC 8785] (JCS); hashing SHA-256 [FIPS 180-4] with
git-style domain separation; identifiers on the [RFC 3986] URI model; case-sensitive grammar [RFC 7405]
over [RFC 5234] ABNF; keyless entropy UUIDv4 [RFC 9562]; keyed identity X.509 SPKI [RFC 5280]; signatures
detached unencoded JWS [RFC 7515]/[RFC 7797], EdDSA [RFC 8037] / ES256 [RFC 7518]/[RFC 6979]. RAPP is a
*profile* over these, as HTTP profiles TCP/URIs/MIME.

---

## 1. Introduction
RAPP is a content-addressed distributed organism. Its integrity rests on one invariant: **the same
concept has the same bytes everywhere.** This document specifies, normatively and completely, five
load-bearing primitives so any two independent implementations interoperate **byte-for-byte with no
out-of-band agreement**: canonicalization (§4), content addressing (§5), identity (§6), the frame (§7),
the egg (§9) — all riding one wire (§8): `POST /chat`, or a signed append-only frame. Implementations add
agents, cartridges, and registered `kind`s — never new endpoints, never new envelopes.

**Repository scope.** `kody-w/RAPP` is the canonical public RAPP foundation,
product home, reference implementation, organism model, and philosophy.
`kody-w/rapp-1` is the canonical interoperable protocol authority. This
specification governs wire-compatible bytes and conformance; it does not absorb
the RAPP product or any downstream Rappter/RapterBox LLC product.

**Specification authority.** The append-only DOGG chain at
`anchor/chain.jsonl` carries the normative revision content. Its hashes prove
integrity, not authority or ratification. Until an authenticated RAPP
registry/checkpoint exists, the chain accepted by the owner onto protected
canonical `kody-w/rapp-1` main is authoritative; an immutable accepted commit
plus head frame hash is the portable checkpoint. `SPEC.md` is the byte-exact
materialized human view, and `orient.json` is only a discovery beacon. The
selected chain-frame hash, not a mutable path or `rev-N` label, is the durable
identity of a protocol revision (§12.2).

### 1.1 The layered model
```
  L5  EGG        cartridge packaging (§9)          — MIME-multipart analogue
  L4  FRAME      universal event envelope (§7)     — the IP packet of RAPP
  L3  WIRE       transport: /chat + frames (§8)    — HTTP-analogue single method
  L2  IDENTITY   rappid namespace + trust (§6,§10) — URI + PKI analogue
  L1  ADDRESS    canonicalization + hash (§4,§5)   — the git object model
```
A higher layer **MUST NOT** redefine a lower one. Every layer names exactly one canonical form.

## 2. Requirements language
The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHOULD**, **MAY** are as in [RFC 2119]/
[RFC 8174] when in **bold caps**. (The Federal Constitution adopts the same clause.)

## 3. Terminology
**organism** — a running brainstem with persistent identity. **rappid** — the eternal, mint-once name of an
organism/door/object (§6): minted once from a UUIDv4 or a public key, never derived from content or name.
**frame** — one immutable content-addressed event (§7). **stream** — an append-only hash-chained frame
sequence sharing one `stream_id`. **particle / wave** — a frame's two domain-separated addresses:
payload-hash / whole-frame-hash (§7.3). **canonical form** — the one [RFC 8785] byte string for a value
(§4). **legacy form** — any other historical encoding; legacy is drift and **MUST** be migrated out
(Fed. Const. Art. III), except sealed re-genesis history (§12.1).
**Grail kernel** — an estate-declared, byte-pinned runtime substrate. Its `grail_id` is
`"grail:" || Hb("rapp/1:grail", kernel_bytes)`; repository, immutable ref, commit, path, raw SHA-256,
and byte length are provenance and verification data, not alternate identities. Once activated through
§13.3, those bytes are permanent (Protocol Constitution Art. 15); capabilities evolve outside them.
**release capsule** — the canonical `rapp-cicd/1-release` payload identifying one immutable candidate.
**serving lineage** — the sequence of qualified release identities that have received user traffic;
the currently served release is immutable even while a separate candidate lineage grows.
**deployment cell** — an independently observable and isolatable runtime failure domain governed by
`rapp-deploy/1`.

## 4. Canonicalization (L1)
`canonical(v)` is the UTF-8 byte string produced by **[RFC 8785] JCS** for the value `v`, defined **only**
over I-JSON [RFC 7493]. JCS fixes member-name ordering (UTF-16 code-unit), string escaping, and number
serialization (ECMAScript `Number::toString`, [ECMA-262]); there is no insignificant whitespace and no
byte-order mark.

**RAPP input-domain profile (parse-side interoperability — this is a RAPP rule, not a JCS mandate).** An
implementation **MUST** refuse (never repair) any JSON value that, at any depth, contains: (a) duplicate
member names in one object; (b) an unpaired UTF-16 surrogate in any string; (c) a number token that does
not survive the binary64 round-trip — let `d` be the token's nearest binary64 value under `roundTiesToEven`
(the IEEE-754 default; ±∞ are admissible results); the token is refused iff `d` is not finite, or the
[RFC 8785] serialization of `d` (ECMA-262 `Number::toString`) denotes a different mathematical value than
the token (so `0.1` is accepted — it round-trips — while `9007199254740993` and `1e999` (→ +∞) are refused); (d) canonical form exceeding 1 MiB or JSON nesting depth
exceeding 64 (the root value is depth 1; each nested object/array adds 1). Refusal is whole (§7.5-style),
never partial.

**No normalization.** RAPP applies **no** Unicode normalization when hashing, storing, or re-emitting an
existing value; strings are code-point sequences preserved verbatim and equality everywhere is code-point
equality (no canonical-equivalence matching). A producer creating a **new** human-or-identifier string
(slug, kind, label, `payload` object key) **MUST** emit it in Unicode NFC.

> **Migration note (drift C4):** the `twin`/`rapp-body` `_frame.mjs::canonicalize()` (sorted-key
> `JSON.stringify`) coincides with JCS only for string-only payloads; it **MUST** be replaced by the JCS
> implementation of record, imported (not re-typed) by every repo that content-addresses.

## 5. Content addressing (L1) — domain-separated
Every hash is **domain-separated** (git's `type\0`, Nix's tagged store — collisions across address spaces
are made unconstructible):
```
H(space, v) = lowercase_hex( SHA-256( utf8(space) || 0x0A || canonical(v) ) )     ; v a value (§4)
Hb(space, b) = lowercase_hex( SHA-256( utf8(space) || 0x0A || b ) )                ; b raw octets
```
`space` is an exact ASCII tag, none containing `0x0A`: `"rapp/1:particle"`, `"rapp/1:wave"`, `"rapp/1:egg"`,
`"rapp/1:egg-manifest"`, `"rapp/1:rappid"`, `"rapp/1:grail"`, `"rapp/1:seal"`,
`"rapp/1:sealed-aad"`, `"rapp/1:sealed-key-request"`. A tag is used by either `H` or `Hb`, never
both. Output is always exactly 64 lowercase hex, **never truncated or uppercased**. Two values
are treated as the same object iff their same-space hashes are equal; SHA-256 collision resistance
[FIPS 180-4] is a security assumption of this standard (§14). A `name/X.Y` label is never identity — only
a hash is. A bare 64-hex is meaningful **only** within its space; an implementation **MUST NOT** dereference
a hash from one space as an object of another, and content-addressed stores **MUST** key by `(space, hash)`.

## 6. Identity — the rappid (L2)
### 6.1 Grammar (case-sensitive, [RFC 7405])
```abnf
rappid    = %s"rappid:@" owner "/" slug ":" hash
owner     = lclabel                       ; the lowercase GitHub login (1-39 chars)
slug      = lclabel                        ; 1-100 chars
lclabel   = lcalnum *( ["-"] lcalnum )     ; no leading/trailing/adjacent hyphen
lcalnum   = LCALPHA / DIGIT
LCALPHA   = %x61-7A                         ; a-z
hash      = 64HEXDIGLC
HEXDIGLC  = DIGIT / %x61-66                 ; 0-9 a-f
```
`owner` **MUST** be the lowercase form of the GitHub login (logins are case-insensitive; display casing is
presentation, never identity). Lengths are normative: `owner` 1–39, `slug` 1–100; an implementation
**MUST** refuse longer. This self-locating form is the **only** conformant rappid; `rappid:<slug>:<hash>`,
`rappid:v2:…`, bare UUIDs, `moment:`/name-hash derivations are legacy and **MUST** be migrated out
(Art. III), not read forever.

### 6.1.1 stream_id and kind grammar
```abnf
stream_id   = memory-stream / body-stream / swarm-stream
memory-stream = rappid ":" instance      ; one organism instance's memory
body-stream   = rappid                    ; an organism's biography
swarm-stream  = %s"net:" lclabel          ; a planetary-wire stream
instance      = lclabel                   ; 1-64 chars
kind          = lclabel "." lclabel       ; each label 1-64 chars
```
A `kind` string carries **no intrinsic family**; the §13 registry binds each registered `kind` to exactly
one family. Membership is tested by exact-match against the registry — never prefix inference, never wildcards.

### 6.2 Minting (mint-once)
The 64-hex tail is minted **exactly once** per identity, then immutable:
- **keyless:** `tail = Hb("rapp/1:rappid", uuid4_octets)`, where `uuid4_octets` is the 16-octet binary
  UUIDv4 [RFC 9562] §5.4 (field/byte order per §4 of that RFC).
- **keyed:** `tail = Hb("rapp/1:rappid", SPKI_DER)`, the DER `SubjectPublicKeyInfo` [RFC 5280] of the master key.

A producer **MUST NOT** derive the tail from owner/slug or any name (`sha256("owner/slug")` is prohibited —
drift ID-01/C3). On read of an existing `rappid.json` an implementation **MUST** reuse the stored tail
(canonicalize-on-read) and **MUST NOT** re-mint — with exactly one mechanism: the owner-authorized
**re-anchor** (§6.3), which mints a fresh 64-hex tail once per authorization and records the superseded id
in `_migrated_from`. Re-anchor is lawful in exactly three cases: (a) a 128→256-bit provisional upgrade
(§6.3); (b) §10 key rotation or compromise; (c) migrating a pre-rev-3 keyed tail minted with the un-tagged
`sha256(SPKI)` formula (which fails §10 discovery and **MUST** be re-anchored like a provisional identity).

### 6.3 Canonicalization on read; provisional identifiers
`canonicalize_rappid(s)` restructures any legacy form into §6.1, **preserving the existing hash** (never
inventing one). A restructured identifier whose tail is not exactly 64 lowercase hex (e.g. a legacy 32-hex
tail) is **provisional**: it exists only inside the reading process and **MUST NOT** appear in any emitted
frame, `stream_id`, egg, or registry entry. The one-time owner-authorized 128→256-bit re-anchor mints a
fresh 64-hex, records the old id in `_migrated_from`, and is the only way a provisional identity becomes
usable. A provisional identifier found in a stored artifact is a drift finding (Art. III). Re-anchor is the
single re-mint mechanism (§6.2), lawful only in the enumerated cases: provisional 128→256-bit upgrade,
§10 key rotation/compromise, and pre-rev-3 un-tagged-`sha256(SPKI)` keyed-tail migration.

**A re-anchor is valid only with a verifiable authorization** — a self-asserted `_migrated_from` is
insufficient (it would let anyone hijack an identity). A re-anchor **MUST** be recorded as an owner-signed
§13.3 **re-anchor record** `{old_rappid, new_rappid, case, utc, sig, old_key_sig?}`; a consumer **MUST**
refuse a `new_rappid` (and treat `_migrated_from` as drift) unless that record is present and:
- `case:"rotation"` (uncompromised): `old_key_sig` (a §10 JWS by the **old** key) verifies — proof of
  continuity;
- `case:"compromise"`: `old_key_sig` is waived but a §10 **tombstone** for `old_rappid` is registered in the
  same append;
- `case:"tag-migrate"` (pre-rev-3 keyed tail): the verifier checks `lowercase_hex(SHA-256(SPKI_DER_old))` ==
  the old tail;
- `case:"upgrade"` (provisional 128→256): the old provisional id resolved to this owner at read time.
Each mints one fresh tail. The **estate_owner's own** re-anchor record **MUST** be signed by the outgoing
`estate_owner` key (§13.2); root-key compromise is recovered only by out-of-band re-anchoring (§13.1).

## 7. The Frame (L4)
### 7.1 The envelope — exactly eleven keys
```json
{
  "spec":         "rapp/1",
  "kind":         "<klabel.klabel>",
  "stream_id":    "<stream_id>",
  "seq":          <uint53>,
  "utc":          "YYYY-MM-DDTHH:MM:SS.mmmZ",
  "payload":      { },
  "payload_hash": "<64hex>",
  "frame_hash":   "<64hex>",
  "prev":         "<64hex|null>",
  "prev_wave":    "<64hex|null>",
  "sig":          "<jws|null>"
}
```
- **`spec` MUST be the exact string `"rapp/1"`** in every frame. `rapp-frame/2.0`/`2.1` are legacy tokens
  and **MUST NOT** be emitted. Any revision changing the key set, any field's grammar, or either hash rule
  **MUST** change this token and land an Art. III total migration; revisions adding only new registered
  `kind`s/registry entries keep the token (Fed. Const. Art. II).
- **Exactly these eleven keys, always present**, none missing, none extra. A field that does not apply is
  present with value `null` (`prev`/`prev_wave` at genesis and on non-swarm streams; `sig` when unsigned) — never omitted,
  because [RFC 8785] hashes `null` and an absent key differently. Extra or missing keys are refused (§7.5).
- **`payload` MUST be a JSON object** (possibly empty `{}`); never `null`, array, string, number, or bool.
- `seq` is `uint53` (§7.4). A producer **MUST NOT** emit a frame whose canonical form exceeds 1 MiB or
  nesting depth 64 (§4).

### 7.2 Kind families (one envelope, registry-bound families)
| family | example registered kinds | `stream_id` form | logs |
|---|---|---|---|
| `memory` | `memory.chat-turn`, `memory.tool-call`, `memory.save`, `memory.reconstructed` | memory-stream | one organism's life |
| `swarm`  | `swarm.guidance`, `swarm.echo`, `swarm.telemetry`, `swarm.reconstructed` | swarm-stream | the planetary wire |
| `body`   | `body.pulse`, `body.twin-pulse`, `body.reconstructed`, `body.re-genesis` | body-stream | an organism's biography |
Each family also has a `*.re-genesis` kind (`memory.re-genesis`, `swarm.re-genesis`, `body.re-genesis`)
used only by §12.1. The family is **not** the kind's prefix — it is the §13 registry binding (so
`body.twin-pulse` is family `body`). Adding a family or event is a new registered `kind` on the **same** envelope (Art. IV), never a
new frame type. A frame's `kind` family **MUST** be compatible with its `stream_id` form (table column 3).

### 7.3 Particle and wave (the unification)
A frame carries **both** of its domain-separated addresses; a reader collapses it to whichever it needs.
Computed in order:
- **particle** — `payload_hash = H("rapp/1:particle", payload)`. The **worldline identity and chain link**.
- **wave** — `frame_hash = H("rapp/1:wave", frame \ {frame_hash, sig})` — the frame with **exactly** the
  `frame_hash` and `sig` keys removed, all nine remaining keys (including `payload_hash`) present.
Because `payload_hash` is in the wave pre-image, `frame_hash` attests the particle; because only
`frame_hash` (cannot hash itself) and `sig` (signs the result) are removed, the pre-image is unambiguous
and non-circular. Both hashes are always present (never `null`).

### 7.4 Chaining, time, and merge order
- **`utc`** **MUST** be exactly the 24-byte form `YYYY-MM-DDTHH:MM:SS.mmmZ` — uppercase `T`/`Z`, exactly
  three fractional digits, no numeric offset; the seconds field **MUST NOT** be `60` (a leap second clamps
  to `59.999`). All `utc` comparisons are **bytewise** over this fixed form (identical to chronological order).
- **Worldline chain (particle):** the **genesis** frame has `seq`=0 and `prev`=null; every later frame has
  `seq` = predecessor's `seq`+1 (contiguous) and `prev` = predecessor's `payload_hash`. `seq` is `uint53`
  (JSON integer, 0 ≤ seq ≤ 2^53−1, no fraction/exponent; a stream nearing 2^53−1 converges by re-genesis).
- **Wire chain (wave):** `prev_wave` **MUST** be non-null **iff** `stream_id` is a swarm-stream **and**
  `seq` > 0, in which case it equals the predecessor's `frame_hash`; in every other frame (all memory/body
  streams, every genesis) it **MUST** be `null`. (Presence is a function of stream family, not transport.)
- A frame is **immutable**: a new state is a new frame at a new hash; the head pointer (§7.6) re-points.
- **Cross-stream merge order** (Dream-Catcher) is the total order: ascending `utc` (bytewise), ties broken
  by ascending `frame_hash` (bytewise); no further ties are possible (§5).

### 7.5 Verification (the complete consumer checklist)
Before accepting a frame, a consumer **MUST**, in order, **refuse** (never repair/reparent) on any failure:
1. **Shape & types:** exactly the eleven §7.1 keys; `spec`==`"rapp/1"`; `kind` a string matching §6.1.1
   ABNF and registered (§13); `stream_id` a string matching §6.1.1; `seq` a `uint53`; `utc` matching the
   §7.4 fixed form **and** a calendar-valid [RFC 3339] `date-time` (so `2026-13-45T25:61:61.999Z` is
   refused); `payload` a JSON object; `payload_hash`/`frame_hash` `64HEXDIGLC`; `prev`/`prev_wave` each
   `null` or `64HEXDIGLC`; `sig` `null` or a §10 JWS string.
1a. **Stream binding:** `frame.stream_id` **MUST** byte-equal the identifier of the stream being extended
   or read (its declared `stream_id` at the head pointer / repo path of record). A genesis frame is
   accepted only for the stream it names. (Defeats cross-stream genesis/segment replay — §14.)
2. **Particle:** `payload_hash` == `H("rapp/1:particle", payload)`.
3. **Wave:** `frame_hash` == `H("rapp/1:wave", frame \ {frame_hash, sig})`.
4. **Chain:** `seq`==head.`seq`+1 and `prev`==head.`payload_hash` (or `seq`==0 ∧ `prev`==null at genesis);
   `utc` ≥ head.`utc` (bytewise).
5. **Wire:** if `stream_id` is a swarm-stream and `seq`>0, `prev_wave`==head.`frame_hash`; else
   `prev_wave`==null.
6. **Signature:** if `sig`≠null, verify per §10 (present-but-invalid is refusal); a swarm-stream frame with
   `sig`==null is refused (§8/§10).
Steps 1–5 are **time-independent** (kind lookups only append, §13), so a frame passing them passes forever;
step 6 alone may flip pass→fail when a §10 tombstone with `revoked_utc` ≤ the frame's `utc` is later
registered — the one time-dependent check.

### 7.6 Heads and forks
A stream's **head** is the frame with the greatest verified `seq` descending from its registered genesis
(§13). A consumer **MUST** persist, per stream, the highest `(seq, frame_hash)` it verified and **MUST**
refuse any presented head with lower `seq`, or a different `frame_hash` at an already-verified `seq` (no
rollback, no silent reorg). Two distinct valid frames with equal `stream_id`, `seq`, and `prev` are a
**fork**: a consumer **MUST** refuse both branches past the fork point and surface a drift finding; only
the owner resolves a fork (Art. X), by re-genesis (§12.1) if needed.

**Exception (re-genesis head reset).** The no-rollback rule above refuses a lower-`seq` head — but a
legitimate §12.1 re-genesis presents a new genesis at `seq`=0. When (and only when) the §13 registry maps a
`stream_id` to a new genesis `frame_hash` (§12.1 step 3), a consumer **MUST** verify that registered
genesis (§7.5) and then **reset** its persisted head for that `stream_id` to it. Only a registry-published
genesis authorizes a reset; any other lower-`seq` head remains a refused rollback.

## 8. The Wire (L3)
All interaction rides one of exactly two forms:
1. **Synchronous — `POST /chat`, `application/json` both ways.** Request: `user_input` (string, REQUIRED);
   `session_id` (string, OPTIONAL — omit to start a session); `idempotency_key` (string, OPTIONAL — a repeat
   with the same key returns the original response, not a new turn or duplicate session; scoped to
   `session_id` when present, else to the key alone so session-creation is also de-duplicated); unrecognized members **MUST** be
   ignored, never refused. Success: HTTP 200 with **exactly** `{response:string, agent_logs:[string],
   session_id:string}` (no extra members). An unknown `session_id`, a refusal, or a malformed request
   **MUST** be HTTP 422, `{error:{code:string, step:string|null}}` where `code` is a §13-registered error
   code (e.g. `"unknown-session"`) and `step` is the failing §7.5 step as a string — one of
   `"1","1a","2","3","4","5","6"` — or `null`. No other shape is conformant. New capability is a new agent
   behind `/chat`, never a sibling REST route.
2. **Asynchronous — an append-only frame (§7) published to a stream** (a repo path, an `events/` log). A
   frame on a **swarm-stream MUST** carry `sig`≠null (§10); memory/body-stream frames **MAY** be unsigned.
   Any *history* is safe to read given a trusted head (§14); the hash chain (§5) makes tampering
   detectable.

## 9. The Egg (L5) — the single egg spec of record
An **egg** is a cartridge packing a unit of the estate. **RAPP §9 is the one egg spec of record** (it
subsumes and retires `EGG_FAMILY.md`, `NEIGHBORHOOD_EGG_SPEC.md`, `ESTATE_SPEC.md`, `rappterbook/EGG_SPEC.md`,
and the rest — drift C7). No other document may re-specify eggs; they cite this section.

### 9.1 Container, manifest, and egg address
An egg is either a JSON object (`invite`/`session` variants) or a ZIP whose root is `manifest.json` (tree
variants). The manifest is a §4 value with exactly these members:
```json
{ "schema": "rapp/1-egg", "variant": "<variant>", "rappid": "<§6.1 rappid>",
  "created_utc": "<§7.4 utc>", "contents": [ {"path":"<rel>","hash":"<64hex>"}, … ], "payload": { },
  "sig": "<jws|null>" }
```
- `contents` **MUST** list every packed file **except `manifest.json` itself**, exactly once each, with
  `hash = Hb("rapp/1:egg", file_octets)` (§5) over the raw stored octets. `contents` is **always present**;
  for JSON (pointer/session) variants it **MUST** be exactly `[]`.
- `path` **MUST** be a relative POSIX path: `/`-separated NFC UTF-8 segments, no `.`/`..` segment, no
  leading `/`, no backslash, no Windows drive-qualified first segment (`ALPHA ":"`), no duplicate `path`
  in one manifest. A segment **MUST NOT** end in a period/space, contain `:`, contain a C0 control, or have
  a case-insensitive basename equal to `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, or `LPT1`–`LPT9`.
  `contents` **MUST** be sorted ascending
  by the UTF-8 bytes of `path`.
- `payload` is a §4 object (variant-specific). `sig` is a §10 JWS over `canonical(manifest \ {sig})`, or
  `null`. For the `invite` variant `sig` is REQUIRED and **MUST** verify with `kid` in the §13.2 estate-owner
  succession (invites are estate-issued; a `sig` by any other key, even a validly registered one, is
  refused — otherwise an attacker mints a fresh rappid and forges invites). For other variants a non-null
  `sig` **MUST** verify per §10 with `kid` == a keyed rappid the consumer resolves via §13; a consumer
  presented a signed egg **MUST** verify it.
- **The egg's one §5 address is** `egg_hash = H("rapp/1:egg-manifest", manifest \ {sig})` — the manifest with
  exactly the `sig` key removed (mirroring §7.3's wave rule: `sig` authenticates the egg, `egg_hash` names
  it, so re-signing never changes identity). Stores key eggs by `("rapp/1:egg-manifest", egg_hash)`.
  (`"rapp/1:egg"` addresses file octets; `"rapp/1:egg-manifest"` addresses the egg as a whole.)
- **Container determinism.** A ZIP variant **MUST** use compression method `stored` (0) for **every** entry
  — no deflate in any variant (deflate is library-dependent, so it cannot be byte-reproducible; transport
  compression, if any, wraps the egg and is not the egg). Entries appear in `contents` order with
  `manifest.json` first; the `manifest.json` entry's octets **MUST** be exactly `canonical(manifest)`; all
  timestamps `1980-01-01 00:00:00`; no extra fields; UTF-8 filename flag set; `contents[].hash` is over the
  file octets (identical to the archive octets under method 0). A JSON-variant egg's serialized form
  **MUST** be exactly `canonical(manifest)`. Two conformant packers of the **same manifest value** thus emit
  byte-identical eggs.

### 9.2 Variants (the ratified set — closes EGG-01)
| variant | container | packs | required members |
|---|---|---|---|
| `organism` | ZIP | a full brainstem instance | contents (sorted) MUST include `rappid.json`, `soul.md`; MAY include `agents/*`, `organs/*`, memory files |
| `rapplication` | ZIP | one rapp | contents MUST include `rappid.json` and exactly one `agent.py` at the root (the agent of record); MAY include one `ui.html` and files under `state/` |
| `session` | JSON | one runtime + transcript | `payload` = `{runtime:<string>, transcript:[<object>]}`; contents `[]` |
| `invite` | JSON | a QR-sized pointer (**no packed files**) | `payload` = `{target_rappid:<rappid>, target_url:<string>, target_kind:("neighborhood" / "estate")}`; contents `[]`; `sig` REQUIRED |
| `neighborhood` | ZIP | several organisms meant to live together | `payload` = `{members:[<rappid>,…]}`; contents = one sub-egg per member, named `<owner>--<slug>.egg` at the root, matched by the sub-egg manifest's `rappid` == the `payload.members[]` entry |
| `estate` | ZIP | several neighborhoods | `payload` = `{neighborhoods:[<rappid>,…]}`; contents = one sub-egg per neighborhood, named `<owner>--<slug>.egg` at root, matched by sub-egg `rappid` |
| `sealed` | ZIP | publicly mirrorable ciphertext with scoped key release | contents MUST be exactly `ciphertext.bin`; payload is the closed `rapp-sealed-artifact/1` profile in §9.2.1; `sig` REQUIRED |

The QR-sized invite that caused EGG-01 is the **`invite`** variant: a signed pointer object, not a
member-packing `neighborhood` egg. The banned legacy stamps (`brainstem-egg/2.3-neighborhood`,
`neighborhood-egg/1.0`) migrate to `{schema:"rapp/1-egg", variant:"invite" / "neighborhood"}` (Art. III).

### 9.2.1 Sealed artifact profile

The `sealed` variant lets any unauthenticated mirror, including a commit-pinned
`raw.githubusercontent.com` URL, distribute an encrypted artifact globally without distributing its
decryption key.

The public bytes are **ciphertext, not access control**. Bytecode or obfuscation alone provides no
confidentiality. A conformant producer **MUST** use a random 256-bit data-encryption key (DEK) per artifact,
**MUST NOT** embed that DEK or a shared master key in the egg/client/URL, and **MUST NOT** place a password
in a URL. A password, passkey, device assertion, or account credential may authenticate to the key service;
it is not the artifact encryption key.

The ZIP contents are exactly one file:

```text
ciphertext.bin = AES-256-GCM ciphertext || 16-byte authentication tag
```

The manifest `payload` has exactly:

```json
{
  "schema": "rapp-sealed-artifact/1",
  "cipher": "A256GCM",
  "nonce": "<12 bytes, unpadded base64url>",
  "plaintext_commitment": "<64hex>",
  "plaintext_bytes": 1234,
  "media_type": "application/wasm",
  "key_id": "<64hex>",
  "key_service_rappid": "rappid:@owner/key-service:64hex",
  "key_service_url": "https://keys.example.com/chat",
  "access": "scoped-key-release",
  "aad_hash": "<64hex>"
}
```

`plaintext_commitment` is a keyed commitment that cannot be tested without the DEK:

```text
prk = HMAC-SHA-256(32 zero octets, DEK)
commitment_key = HMAC-SHA-256(prk, utf8("rapp/1:sealed-commitment") || 0x01)
plaintext_commitment = lowercase_hex(HMAC-SHA-256(commitment_key, plaintext_octets))
```

This is the [RFC 5869] HKDF-Extract/HKDF-Expand construction with an empty salt, one 32-byte output block,
and the exact info string `rapp/1:sealed-commitment`. The commitment is public but does not permit an
offline dictionary attack without the random 256-bit DEK.

The exact authenticated-data descriptor is:

```json
{
  "schema": "rapp-sealed-artifact/1",
  "artifact_rappid": "<manifest.rappid>",
  "created_utc": "<manifest.created_utc>",
  "key_id": "<payload.key_id>",
  "plaintext_commitment": "<payload.plaintext_commitment>",
  "plaintext_bytes": 1234,
  "media_type": "<payload.media_type>"
}
```

`aad_hash = H("rapp/1:sealed-aad", descriptor)`, and `canonical(descriptor)` is supplied as AES-GCM
additional authenticated data. `nonce` decodes to exactly 12 bytes. `plaintext_bytes` is an integer from
zero through `2^30` (1 GiB), a RAPP safety ceiling below both the [NIST SP 800-38D] per-invocation limit
and the deterministic non-ZIP64 container boundary.
`ciphertext.bin` length is exactly `plaintext_bytes + 16`. The sealed egg's manifest signature is REQUIRED
and verifies per §10 with `kid` exactly equal to `manifest.rappid`. A sealed artifact therefore uses a
keyed §6.2 rappid controlled by its authorized publisher; another valid registry key cannot sign on its
behalf.

`key_service_rappid` identifies the RAPP organism authorizing key release. `key_service_url` is its absolute
HTTPS §8 `POST /chat` URL and **MUST** end in `/chat`. The URL is location, not authority: the service
response is accepted only when its signatures and identifiers bind to `key_service_rappid`.

The caller sends the following canonical JSON object as the `user_input` string:

```json
{
  "schema": "rapp-sealed-key-request/1",
  "egg_hash": "<64hex>",
  "key_id": "<64hex>",
  "recipient_rappid": "rappid:@owner/device:64hex",
  "recipient_spki_der_b64": "<standard base64>",
  "request_nonce": "<64hex>",
  "expires_utc": "YYYY-MM-DDTHH:MM:SS.mmmZ",
  "sig": "<recipient detached JWS>"
}
```

`sig` is over `canonical(request \ {sig})` and verifies under `recipient_rappid`; `egg_hash` is the §9.1
sealed egg address. The key service verifies entitlement, exact `(egg_hash,key_id)`, request expiry,
recipient key binding, and nonce non-reuse.

The §8 `response` string is canonical JSON:

```json
{
  "schema": "rapp-sealed-key-release/1",
  "egg_hash": "<request.egg_hash>",
  "key_id": "<request.key_id>",
  "recipient_rappid": "<request.recipient_rappid>",
  "request_hash": "<H('rapp/1:sealed-key-request', request without sig)>",
  "wrap_alg": "ECDH-ES+A256KW",
  "wrapped_key_jwe": "<JWE Compact Serialization>",
  "issued_utc": "YYYY-MM-DDTHH:MM:SS.mmmZ",
  "expires_utc": "YYYY-MM-DDTHH:MM:SS.mmmZ",
  "service_sig": "<key-service detached JWS>"
}
```

`service_sig` is over `canonical(release \ {service_sig})` and verifies under `key_service_rappid`.
`wrapped_key_jwe` uses [RFC 7516] with `alg:"ECDH-ES+A256KW"` and `enc:"A256GCM"` for the declared
recipient SPKI. The service **MUST NOT** return a global raw DEK. Authorization, expiry, device scope, and
key rotation are service policy recorded in signed frames, not fields that alter the sealed egg's content
address.

A mirror URL **SHOULD** be immutable (for GitHub Raw, pin a commit SHA rather than a moving branch). URL
secrecy is never assumed: integrity comes from the egg address and signature, confidentiality from
AES-GCM, and use authorization from scoped key release.

Revocation prevents future key release. It cannot erase ciphertext or plaintext already downloaded and
decrypted by an authorized recipient. A conformant product **MUST** state this limit plainly. It also
**MUST NOT** claim that encrypted bytecode cannot be inspected after decryption; legal/license controls and
bounded server authority remain separate from cryptographic confidentiality.

### 9.3 Conformance
- **Producer** **MUST** emit only `schema:"rapp/1-egg"` with a variant from §9.2, a §6.1 rappid, and, for
  ZIP variants, a `contents` list whose every hash verifies. It **MUST NOT** emit any legacy egg schema.
- **Consumer** **MUST** read every §9.2 variant, dispatch on `variant`, verify **integrity then viability** —
  (0) the manifest is a §4 value satisfying **every §9.1 rule** — exact member set, `path` grammar (no `..`,
  no leading `/`, no backslash), no duplicate paths, sort order, and for ZIP variants the archive entry set
  equals `contents` ∪ {`manifest.json`} in the §9.1 deterministic order (this is the zip-slip defense; an
  unenforced path grammar defends nothing); (1) every `contents[].hash` recomputes per §5; (2) the variant's
  §9.2 structural requirements hold — and refuse whole on any failure; it **MUST NOT** reparent on transport.

### 9.4 Instantiation — instance identity and `grown_from` lineage (rev-6; closes the hatch seam)
An egg names an **artifact**; a hatch creates an **instance**. Rev-5 specified packing and reading but
left instantiation identity unwritten, so every implementation had to invent its own — this section is
that missing word.

- The `rappid` in a packed egg's `rappid.json` (§9.2) names the **artifact**. Every hatch of the same
  egg reads the **same** artifact identity (§6.2 canonicalize-on-read); re-minting it on hatch is
  prohibited (§6.2).
- A consumer that instantiates an egg into a live installation **MUST** mint a **fresh §6.2 identity
  for the instance**, exactly once, at first boot — from entropy, never derived from the artifact
  identity, host name, or path. Two instances of one egg share the artifact identity and **MUST NOT**
  share an instance identity.
- The instance's identity document **SHOULD** record **`grown_from`**: the §9.1 egg address
  (64 lowercase hex) of the egg it was instantiated from. `grown_from` is written at mint time and is
  **immutable** thereafter; it is `null` when the source is unknown; a producer **MUST NOT** fabricate
  it — lineage is a fact about a birth, never a claim to invent. An instance that cannot say where it
  came from says `null`.
- `grown_from` is **lineage, not inheritance**: it confers no authority, no trust, and no §10 key
  material. A reader **MUST** treat it as an unverified assertion unless the named egg is available and
  its address recomputes per §9.1/§5.
- A newly authored artifact produced from one or more existing RAPP objects **MAY** record
  `crossed_from` in its packaged `rappid.json`. The value is a sorted, duplicate-free array of typed
  addresses `{space, hash}`, where `space` is `"rapp/1:particle"` or `"rapp/1:egg-manifest"` and `hash`
  is 64 lowercase hex. One parent denotes an **offspring**; two or more denote a **cross**. The new
  artifact **MUST** mint its own §6.2 rappid; parent artifacts and identities remain unchanged.
  `crossed_from` is lineage only: it transfers no signature authority, ownership, entitlement, secret,
  or trust. A verifier treats each parent as unverified until the addressed object is available and
  recomputes in its declared space.

## 10. Trust and signatures (L2)
`sig` is OPTIONAL on memory/body streams and REQUIRED on swarm streams (§8). Chain integrity comes from the
hash links (§5), not signatures. When present, `sig` **MUST** be JWS Compact Serialization with **detached,
unencoded payload** ([RFC 7515] App. F + [RFC 7797]):
- protected header members are **exactly** `alg` (`"EdDSA"` or `"ES256"`), `b64` (`false`), `crit`
  (`["b64"]`), `kid` (signer's §6.1 rappid), no others; the header octets **MUST** be `canonical(header)`
  (§4 — JCS orders them `alg`, `b64`, `crit`, `kid`, no whitespace);
- the `sig` string is the detached compact form `BASE64URL(canonical(header)) || ".." || BASE64URL(signature)`;
- JWS signing input = `BASE64URL(canonical(header)) || "." || canonical(frame \ {sig})`;
- `alg`: `EdDSA`/Ed25519 [RFC 8037] or `ES256` [RFC 7518]; ES256 signers **SHOULD** sign deterministically
  [RFC 6979] (Ed25519 is deterministic by construction) so signed frame files stay byte-reproducible.

**Key discovery.** A keyed rappid's tail is one-way (`Hb("rapp/1:rappid",SPKI)`). A verifier resolves the
signer's SPKI (DER) **from the §13 registry** entry (`rappid` → `spki_der_b64`); the door-of-record
`rappid.json` is the publication venue the registry entry is generated from, not itself a verification
source. The verifier **MUST** check `Hb("rapp/1:rappid", SPKI_DER)` == the rappid's tail and refuse on
mismatch or registry absence.

**Key lifecycle.** Rotation is an identity re-anchor (§6.3, case `rotation`) with new `tail =
Hb("rapp/1:rappid", newSPKI)` and a §13.3 re-anchor record. A re-anchor **deprecates** the superseded
rappid's §13 `spki` entry: a verifier **MUST** refuse a `sig` whose `kid` is a superseded rappid on any
frame with `utc` ≥ the re-anchor record's `utc` (rotation gives forward security; earlier frames verify as
before). Compromise is declared by an owner-signed **tombstone** in the §13 registry `{rappid, revoked_utc}`; a verifier **MUST** refuse any `sig` by a
tombstoned key on a frame whose `utc` ≥ `revoked_utc`, checking tombstones at verification time (§7.5 step
6). "Owner-signed" means a `sig` verifying with `kid` == the registry's designated `estate_owner` rappid
(§13). A consumer **MUST NOT** infer authorship from an unsigned frame (keyless rappids assert location,
not authorship).

## 11. Conformance classes
- **Producer:** emits only §4 JCS/I-JSON bytes, §5 domain-separated full-SHA-256 addresses, §6 rappids
  minted per §6.2, §7.1 eleven-key frames, §9 `rapp/1-egg` variants — and **no legacy form**.
- **Consumer:** runs the full §7.5 checklist (incl. 1a binding), §9.3 egg verification, §10 signature +
  key-discovery + tombstone checks, canonicalizes legacy ids on read (§6.3), refuses on any failure, never
  repairs/reparents/rolls back (§7.6).
- **Router/Mirror:** invents no endpoints (§8), declares subordination to
  `kody-w/rapp-1` for protocol semantics, and serves only
  provenance-stamped hash-matching mirrors. Estate-specific product scope is
  resolved separately through that estate's signed registry and master plan.

### 11.1 Immutable Grail kernel conformance
An estate declares a Grail kernel through the exact §13.3 `grail-kernel` entry. Its `release_scope`
selects the release family to which the pin applies; a registry **MUST** contain at most one
`grail-kernel` entry for any release scope. Its entry-level `sig`
**MUST** verify under `declared_by`, which **MUST** be the estate owner in effect at `activated_utc`
(§13.2); `activated_utc` **MUST NOT** be more than 300 seconds after the verifier's first-seen time for
that entry. The pin activates locally when a consumer first accepts an authenticated, non-rollback
registry containing that valid declaration. Until then it is structural evidence only. The Grail is
identified by `grail_id`, never by a mutable branch, tag, repository name, or product label. Once
activated, the pin is a permanent compatibility anchor, not a moving release channel:

1. Every conformance evaluation **MUST** receive `release_scope` from an authenticated owner-controlled
   release policy, never from candidate bytes or candidate-controlled configuration, then resolve its
   one `grail_id` exclusively from the activated, persisted §13.3 binding. If the policy repeats
   `grail_id`, that value is only a consistency assertion and **MUST** byte-equal the registry result; it
   cannot select or rebind the pin. Every ring and release/deployment stage, including development,
   qualification, Preprod, installation, and production verification, **MUST** compare the candidate's
   Grail path to that exact binding, SHA-256, and byte length.
2. A missing, changed, substituted, or unmeasured Grail byte is `kernel-drift` and **MUST** fail closed.
   Approval, urgency, compatibility claims, and semantic equivalence cannot waive byte inequality.
3. A pipeline **MUST NOT** silently restore the pinned file after testing a different file. The exact
   release-shaped artifact containing the immutable Grail bytes **MUST** itself pass the release gates.
4. Every gate **MUST** resolve every archive, container, wrapper, environment override, symlink, and
   filesystem indirection to one regular runtime entry-point file under the immutable release root;
   refuse links and ambiguous alternatives; verify its bytes; and bind the release digest, resolved
   entry-point path, `release_scope`, `grail_id`, raw SHA-256, and byte length into its evidence.
5. Every gate that executes the kernel **MUST** bind verification atomically to execution from a sealed
   immutable object or snapshot. An already-open descriptor is sufficient only when its backing bytes
   are under platform-enforced write exclusion for the entire verification-through-consumption interval
   and the interpreter/loader consumes that exact descriptor without reopening a pathname. An immutable
   content-addressed release root is sufficient only when no concurrent principal can modify it. A
   hash-then-path-launch without one of those guarantees is nonconformant. At least one execution gate for
   every supported production platform **MUST** perform this proof before release approval. Merely
   carrying an unused matching file is insufficient. A stored transpiled, bundled, generated, or patched
   derivative is different kernel bytes and requires a new `grail_id`; ordinary interpreter/JIT
   compilation directly from the pinned bytes is permitted when no alternate stored kernel is selected.
6. New implementation behavior **MUST** live outside the Grail kernel and **MUST NOT** alter any
   RAPP-visible canonical form or wire semantic except through the registration and evolution rules of
   §§7, 9, 12, and 13.
7. If required behavior cannot be expressed outside the pin, the implementation **MUST** report an
   incompatibility. It **MUST NOT** edit the Grail and continue under the same identity.
8. Different kernel bytes produce a different `grail_id` and therefore are a different Grail. A new
   `grail-kernel` entry may coexist and may name the old `grail_id` as `predecessor`, but it **MUST NOT**
   overwrite, retag, alias, or redefine the prior Grail. A successor uses a new `release_scope`; an
   existing scope is never rebound. A non-null `predecessor` **MUST** name an earlier accepted
   `grail-kernel` entry and **MUST NOT** form a cycle. A registry **MUST** contain at most one
   `grail-kernel` entry for each `grail_id`.
9. On first activation a consumer **MUST** persist the full canonical `grail-kernel` entry. Every later
   accepted registry **MUST** retain that entry byte-for-byte. Removal, mutation, or a second entry for
   the same `grail_id` is a permanent `kernel-drift` refusal even when `registry_seq` increased.

This rule governs release topology rather than the §8 wire shape, so it does not add a frame member,
endpoint, compatibility shim, or alternate `rapp/1` encoding.

### 11.2 Operational conformance profiles
RAPP/1 defines the substrate. Two subordinate operational profiles define how a production AI changes
without mutating that substrate or the serving system underneath users:

- **RAPP CI/CD** (`rapp-cicd/1`) — `protocols/rapp-cicd/1/SPEC.md`; immutable release capsules,
  ordered qualification evidence, exact-candidate promotion, Preprod, and rollback/restore proof.
- **RAPP Deploy** (`rapp-deploy/1`) — `protocols/rapp-deploy/1/SPEC.md`; isolated serving/candidate
  lineages, cellular rollout, progressive exposure, expiring AI-health evidence, quarantine, and exact
  rollback.

The profiles are RAPP/1 applications, not alternate wire versions:

1. Their payloads **MUST** be §4 canonical I-JSON and are identified by
   `H("rapp/1:particle", payload)`.
2. Authoritative profile payloads **MUST** travel in signed RAPP/1 frames using a registered compatible
   kind. Local unsigned files are drafts, fixtures, or caches and cannot authorize promotion or traffic.
3. They **MUST NOT** add a transport endpoint beside §8 `POST /chat`, redefine any RAPP/1 primitive, or
   weaken §11.1.
4. An estate activates a profile through an authenticated §13.3 `protocol` entry pinning its exact
   repository, path, and SHA-256. A moving branch is discovery, never authority.
5. A claim of **RAPP production conformance** requires both profiles. Core Producer, Consumer, and
   Router/Mirror implementations remain conformant without implementing production operations.
6. Fixed envelope keys carry the safety invariants. Policy-defined check identifiers, component kinds,
   health objectives, and resilience controls are extension points; adding one does not change the
   profile token or the RAPP/1 wire.
7. A consumer **MUST** refuse unknown required policy semantics. It may preserve and relay unknown
   optional evidence, but may not treat it as satisfying a requirement it does not implement.

The executable reference validators are `rapp_cicd.py` and `rapp_deploy.py`; controlled profile vectors
are in `operations_conformance.py`. JSON Schemas define structural shape, while the reference validators
enforce ordering, identity, temporal, and cross-document rules that JSON Schema cannot express.

## 12. Versioning, evolution, no-legacy
RAPP is a **living standard** (WHATWG): revised in place, never forked into parallel versions; a `name/X.Y`
label **MUST NOT** ever denote two shapes (Art. II) — a shape change moves the token (§7.1). Published
content-addressed artifacts are **immutable** (SemVer/crates). Within an estate there is **no perpetual
backward compatibility** for the estate's own artifacts and retired legacy encodings (Art. III): a change
to such a form is a **total migration** of every instance + **deletion** of the old form. Sealed re-genesis
history (§12.1) is the retained live-stream exception and is not "legacy compatibility."

**The `rapp/1` wire is frozen (rev-15, Art. 18).** No revision of this standard may change a form a
`rapp/1` artifact is verified by: canonicalization (§4), the hash function and its tags (§5), the rappid
grammar and mint (§6.1, §6.2), the eleven-key envelope and its two addresses (§7.1, §7.3), the consumer
checklist (§7.5), the two wire forms and the `/chat` shapes (§8), or the egg container and address (§9.1).
A change to any of those is not a revision; it moves the token to `rapp/2`, specified beside this
document, and `rapp/1` artifacts keep verifying under this document forever. A consumer **MUST NOT**
refuse a `rapp/1` artifact because a later token exists. Everything Art. IV names still grows under
`rapp/1`: registered kinds, egg variants, error codes, registry entry types, vocabulary, subordinate
profiles, and the registry itself. The frozen forms are what a stranger's implementation, written once
and never updated, relies on; they are the reason an independent implementation can be finished.

Immutable specification-governance history is a separate narrow exception:
rev-5 through rev-13 anchor frames retain interpretable immutable pointer
payloads so their ratified normative bytes remain resolvable. They are
historical authority records, not accepted live legacy protocol forms. A
producer **MUST NOT** emit the pointer-only revision profile after rev-13.

### 12.1 Re-genesis (converging an immutable chain — one owner-authorized operation)
1. **Terminal seal:** `seal = Hb("rapp/1:seal", head_octets)`. `head_octets` is the exact octets of the old
   head's record **as retained under `legacy/`** (step 4): for a one-frame-per-file store, the retired
   file's full octets; for a line-oriented log, the head's line **excluding** its trailing terminator. The
   retained `legacy/` artifact is the verification reference for the seal, and retirement **MUST** preserve
   those octets bit-exact. The step-3 `genesis` registry entry **SHOULD** record the `legacy/` artifact's
   repo+path so a consumer **MAY** verify the seal against it. (Defined for every legacy shape, including
   ones that cannot be §7.3-hashed.)
2. **New genesis:** emit `seq`=0, `prev`=null, `kind` = the registered re-genesis kind **of the stream's
   family** — `memory.re-genesis`, `swarm.re-genesis`, or `body.re-genesis` (three §13 kinds, used only
   here) so the frame satisfies §7.2 family↔stream compatibility for any stream — `sig`≠null owner-signed
   (§10, §13 `estate_owner`), `payload` = `{"migrated_from":{"stream_id":<old>,"terminal_seal":<seal>,
   "terminal_seq":<n>}}` and no other members. A consumer **MUST** treat any `*.re-genesis` kind as the sole
   re-genesis marker for its family and refuse an unsigned/non-owner one.
3. **Register (the linearization point):** append a §13.3 `genesis` entry mapping the `stream_id` to the new
   genesis's `frame_hash`, **and flag every prior `genesis` entry for that `stream_id` `deprecated`** — the
   first convergence included (it deprecates the creation-time genesis), so exactly one non-deprecated entry
   always remains. A consumer resolves the current genesis **only** via that sole non-deprecated entry. A
   **concurrent** second registration fails closed (the append is the linearization point, Art. IX); a
   later fork/brick (§7.6/§14) is a fresh owner-authorized convergence that appends again and re-deprecates.
4. **Retire:** move old frames under `legacy/` — retained as immutable sealed history, never served as
   current, never extended, never read as live chain. No live frame may set `prev`/`prev_wave` to a retired
   hash (a dangling ref is a drift finding).
5. Keep the old `stream_id` unless the identity itself re-anchored (§6.3), in which case the registry entry
   also records `old_stream_id → new_stream_id`.
6. Two frames with equal `stream_id`+`seq` from different eras are disambiguated **solely** by descent from
   the current registered genesis. Re-genesis is one-time per convergence; a repeat *of the same
   convergence* is the concurrent case (step 3, fails closed).

### 12.2 DOGG specification revision chain

The RAPP/1 revision content is the append-only JSONL stream at
`anchor/chain.jsonl`. The chain's particle, wave, and predecessor hashes prove
byte integrity and linear history; they do **not** authenticate who selected a
head or ratified an amendment. Until a separately authenticated RAPP
registry/checkpoint is ratified, authority is selected by owner-ratified
acceptance of a chain snapshot onto protected canonical
`refs/heads/main` at `https://github.com/kody-w/rapp-1`. A consumer starting
from an out-of-band pinned accepted commit and head frame hash has the same
immutable selection evidence. An internally valid fork is not authoritative
merely because its hashes verify.

Every protocol adjustment **MUST** append exactly one valid successor frame:

- `spec` remains `"rapp/1"`, the envelope remains exactly eleven keys, and the
  allowed registered anchor kind is `body.pulse`; this profile does not create
  a new kind or alter canonicalization, hashing, or registered-kind semantics;
- `stream_id` remains the bootstrap-pinned anchor stream, `seq` is contiguous,
  `prev` names the predecessor's `payload_hash`, `prev_wave` and `sig` are
  `null`, and the applicable §7.5 integrity checks hold;
- the frame's `frame_hash` is the durable protocol-revision identity.
  Human names such as `rev-14` are lookup labels/views, never identities.

#### 12.2.1 Immutable bootstrap boundary

Verification begins from the frozen `rapp-anchor-bootstrap/1` profile published
through `anchor/bootstrap/index.json`. The index names a
`anchor/bootstrap/sha256-<raw-profile-sha256>.json` object and pins the exact
stdlib verifier at `anchor/bootstrap_verify.py` by raw SHA-256 and byte length.
The profile fixes the exact-integer JCS subset and limits, particle/wave
domains, eleven frame keys, timestamp/sequence/predecessor rules, canonical
repository and protected ref, anchor stream ID, genesis frame and payload
hashes, `body.pulse` anchor profile, null signature/wave fields, and byte/depth
limits needed to verify this chain.

The content-addressed bootstrap profile is immutable. Changing it requires a
new bootstrap schema/version and a new external ratification; mutating
`rapp-anchor-bootstrap/1` in place is refusal. Its initial authenticity is
necessarily external — owner-ratified protected canonical main or an
out-of-band pinned profile hash/immutable commit — because neither a chain nor
code fetched with that chain can circularly authenticate its own parser.
`rapp.py` remains the complete reference implementation and is cross-checked,
but it is not the mutable bootstrap trust pin.

#### 12.2.2 Revision payloads and historical exception

Frames through rev-13 retain their immutable legacy pointer fields:
`canonical_repo`, a full 40-lowercase-hex `commit`, safe relative
`normative_path`, raw-file `normative_sha256`, and decimal-string
`normative_bytes`. A resolver **MUST** construct only an immutable
commit-pinned GitHub Raw URL from those fields, fetch the bytes, and verify
length and raw SHA-256 before use. A branch or tag name in `commit`, an unsafe
path, malformed UTF-8, a byte-order mark, or a hash/length mismatch is refusal.
Path validation occurs on the original string before path-library
normalization: empty, absolute, `.`/`..`, empty components, repeated slash,
leading `./`, trailing slash, backslash, percent-encoded ambiguity, or any
value whose reconstructed POSIX form differs is refused.
These pointer payloads are immutable governance history under Article 3's
narrow exception; they **MUST NOT** be emitted for rev-14 or later.

Rev-14 and each successor using this profile carries all normative text inside
the chain frame. Its payload **MUST** include
`schema:"rapp-spec-revision/1"`, a unique `revision`, and both
`previous_revision` and `previous_normative_sha256` matching the immediate
predecessor. It preserves the useful legacy fields above, carries the
publication/ratification metadata defined below, and adds exactly this
`normative` object:

```json
{
  "media_type": "text/markdown; charset=utf-8",
  "text": "<exact normative SPEC.md Unicode text>",
  "sha256": "<lowercase SHA-256 of text encoded as UTF-8>",
  "bytes": 123
}
```

`normative.text` **MUST** encode as UTF-8 without a byte-order mark;
`normative.sha256` and `normative.bytes` **MUST** match those exact octets and
the corresponding legacy `normative_sha256` and `normative_bytes`. The complete
canonical frame remains subject to §4's 1 MiB limit. Inline revisions require
only the selected, verified chain bytes once fetched; their commit/path fields
are immutable provenance, not a second source for normative text.

The payload's `publication` object, repeated in the beacon and revision index,
records: canonical repository `https://github.com/kody-w/rapp-1`; protected ref
`refs/heads/main`; selection by owner-ratified acceptance; the accepted
canonical-main commit as linearization point; prohibition of history
replacement; mandatory rebase/regeneration for a competing append; rev-14
ratification under rev-13 Article 14; application of this chain-append process
from rev-15 onward; and `authenticated_registry_checkpoint:null` until one
actually exists. This metadata **MUST NOT** be interpreted as a signature or
authenticated registry.

#### 12.2.3 Content-addressed publication and resolution

Every chain frame **MUST** also be published, without a trailing line
terminator, at:

```text
anchor/frames/<frame_hash>.json
```

A fetch through mutable main is discovery only. Given frame hash `F`, a
stranger may fetch
`https://raw.githubusercontent.com/kody-w/rapp-1/main/anchor/frames/F.json`,
parse it under the pinned bootstrap, and accept the object only if its computed
wave equals `F`. For accepted snapshot commit `C`, the immutable URL is
`https://raw.githubusercontent.com/kody-w/rapp-1/C/anchor/frames/F.json`.
Wrong content at the correct hash-derived path is refusal.

`anchor/index.json` is a deterministic generated index from `seq`, revision
label, frame hash, and payload hash to those objects. It carries no independent
authority: a consumer **MUST** verify each selected object and match the index
and beacon to the fully verified chain. Resolution by frame hash uses the path
algorithm directly; resolution by payload hash or sequence uses the verified
index; resolution by revision label is a view over it. The fixed pre-profile
rev-5 pulses share one historical label, so the `rev-5` view resolves to the
greatest matching `seq`, while every pulse remains directly resolvable by
sequence and hashes.

A consumer **MUST** verify the chain from the bootstrap-pinned genesis before
using a revision as selected history. It **MUST** refuse an invalid frame shape,
particle, wave, or `prev`; a fork or duplicate `seq`; duplicate frame/payload
hashes; a duplicate profiled revision; an unsupported schema; a legacy
pointer-only frame after rev-13; malformed UTF-8; normative hash/length drift;
bootstrap/index/object drift; or an object absent from the selected chain.

`orient.json` is only a beacon to the head. Its sequence, frame hash, payload
hash, bootstrap/index pins, authority-selection metadata, and every retained
head mirror — including `registered_kinds`, vocabulary, operational profiles,
foundation, philosophy, and Constitution metadata — **MUST** be regenerated
from and match the verified head. While the beacon schema remains
`rapp/1-anchor`, `spec.normative_path` **MUST** remain as a compatibility alias
equal to `spec.materialized_path`. `SPEC.md` **MUST** reproduce the selected
head byte-for-byte. The Atom feed and mutable main URLs are discovery only.

Materialization and immutable-pointer caching **MUST** use bounded reads and
same-directory atomic replacement without following a symlink in the
destination leaf or path. A symlink, unsafe directory component, oversized
cache entry, content change during read/write, or compare-and-swap mismatch is
refusal; the requested leaf is replaced, never the symlink target.

After acceptance, let `C` be the full 40-hex canonical-main commit containing
the accepted snapshot. The immutable checkpoint URLs are:

```text
https://raw.githubusercontent.com/kody-w/rapp-1/C/anchor/chain.jsonl
https://raw.githubusercontent.com/kody-w/rapp-1/C/anchor/orient.json
https://raw.githubusercontent.com/kody-w/rapp-1/C/anchor/index.json
```

The authority linearization point is the owner-ratified acceptance of `C` onto
protected canonical main, not creation of a local frame, a feed event, or a
hash alone. A stale competing append **MUST** rebase onto the accepted head and
regenerate. Force-push or history replacement of accepted authority is
prohibited.

#### 12.2.4 Rev-14 transition and draft replacement

Rev-14 is ratified under rev-13 Article 14. Owner acceptance of the prepared
change onto canonical protected main makes the final rev-14 frame effective;
the new chain-append process governs rev-15 onward. Before that acceptance,
rev-14 artifacts are unpublished drafts. A later commit in the same
owner-ratified change may deterministically replace the one unpublished rev-14
draft line/object and update dependent hashes, but **MUST** preserve every
rev-5 through rev-13 line byte-for-byte and **MUST NOT** represent the replaced
draft as accepted history.

The publication generator **MUST** hold one cross-process exclusive lock across
read, verification, generation, comparison, and publication. Immediately
before replacing `chain.jsonl` it **MUST** re-read and verify the on-disk head
and compare the complete expected prefix; a stale writer or changed prefix is
refused. Supporting content-addressed artifacts are published first, the
authority chain is compare-and-swap replaced next, and the beacon is replaced
last, with file and parent-directory synchronization. Because the chain is
authority content and the beacon is only a derived view, interruption after a
valid chain replacement may leave a stale or missing beacon; the next locked
run **MUST** deterministically regenerate it from the verified chain rather
than refusing the valid head forever.

This chain and beacon are unsigned. They provide integrity after authority
selection, not authorship, and implementations **MUST NOT** fabricate a
signature or authenticated registry/checkpoint state for them.

## 13. The registry — an estate's signed root of trust (append-only)
Each estate selects an owner-controlled `canonical_source` for its
`schema:"rapp/1-registry"` document. The kody-w reference estate may publish
its registry through `kody-w/RAPP` or another owner-authorized location, but
that estate instance cannot alter this protocol. Because §7.6 head resets, §10
key discovery, tombstone revocation, and ownership all resolve through the
selected registry, it is the **root of trust for that estate** and is itself
authenticated (an unsigned mutable file at the root of the trust graph would
forge that estate).

### 13.1 Trust anchor and registry authentication
- The one bootstrap axiom is the **`estate_owner` rappid string** itself: since a keyed tail is
  `Hb("rapp/1:rappid", SPKI_DER)`, the rappid **is** a self-certifying key fingerprint, distributed
  out-of-band exactly once (QR, invite, docs) the way a root-CA certificate is.
- The registry document **MUST** carry a top-level `registry_seq` (uint53) and a detached §10 JWS `sig` over
  `canonical(registry \ {sig})` with `kid` = the `estate_owner` rappid. A consumer **MUST** verify this
  signature against an SPKI whose `Hb("rapp/1:rappid", SPKI_DER)` equals the anchor rappid's tail (the SPKI
  may travel alongside the registry — the tail check authenticates it) and **MUST** refuse an unsigned or
  non-verifying registry.
- **No rollback:** a consumer persists the highest `registry_seq` it verified and refuses any registry with
  a lower one (mirrors §7.6). **Freshness:** a consumer **MUST** obtain the registry from `canonical_source`
  or a provenance-stamped (Art. VIII) mirror of it, **SHOULD** refresh before any §7.5-step-6 or §7.6
  head-reset decision, and **MUST** report a verification made against a registry older than its staleness
  policy as *stale*, not *clean*.

### 13.2 Owner succession (time-scoped authority)
"Owner-signed" means: the `sig` verifies per §10 **and** `kid` is the estate-owner **in effect at the
artifact's `utc`** — the current `estate_owner` or any predecessor reachable through the registry's
re-anchor records (§13.3), with the artifact's `utc` inside that owner's tenure `[record.utc, successor.utc)`.
Verification uses the owner in effect at the artifact's time, **never only the current one** (so a routine
owner key rotation never invalidates historical re-genesis frames or tombstones). Estate-owner **root-key
compromise** is recovered only by re-distributing a new trust anchor out-of-band (§13.1) — it cannot be
expressed inside the registry it signs.

### 13.3 Entry types (each a §4 value; document `schema:"rapp/1-registry"`)
The registry is an I-JSON document; every entry is append-only (never removed/renamed; retirement is a
`deprecated:true` flag). Entry types and their exact members:
- **protocol** `{type:"protocol", name, spec_repo, spec_path, spec_hash, deprecated}` — an estate
  adoption pin, never a power to redefine a protocol. An entry with `name:"rapp/1"` that is used for a
  current-conformance claim **MUST** set `spec_repo:"https://github.com/kody-w/rapp-1"`,
  `spec_path:"SPEC.md"`, and `spec_hash` to a normative SHA-256 published by a verified frame in this
  repository's anchor chain. A historical RAPP/1 pin may be retained only as `deprecated:true`; it does
  not override the current anchor. Other protocol entries are subordinate to their own canonical
  authorities and **MUST NOT** claim the `rapp/1` name or namespace.
- **kind** `{type:"kind", kind, family, deprecated}` (incl. the three `*.re-genesis` kinds)
- **egg-variant** `{type:"egg-variant", variant, deprecated}` · **error-code** `{type:"error-code", code}`
  (both closed namespaces; unregistered value = not conformant)
- **genesis** `{type:"genesis", stream_id, frame_hash, deprecated, old_stream_id?, new_stream_id?}` — **every**
  stream registers its creation genesis; re-genesis appends a new one and deprecates all prior (§12.1 step 3);
  §7.6's "registered genesis" is the sole non-deprecated `genesis` for a `stream_id`.
- **spki** `{type:"spki", rappid, spki_der_b64, deprecated}` — the §10 key-discovery source.
- **tombstone** `{type:"tombstone", rappid, revoked_utc, sig}`, `sig` owner-signed over `canonical(entry \ {sig})`.
- **re-anchor** `{type:"re-anchor", old_rappid, new_rappid, case:("upgrade"|"rotation"|"compromise"|"tag-migrate"),
  utc, sig, old_key_sig?}` — `sig` owner-signed; `old_key_sig` a §10 JWS by the **old** key over
  `canonical(entry \ {sig,old_key_sig})`, REQUIRED for `case:"rotation"`. This is the normative succession record (§13.2).
- **grail-kernel** `{type:"grail-kernel", release_scope, grail_id, repository, immutable_ref,
  object_format, commit, path, mode, blob, sha256, size_bytes, activated_utc, predecessor, declared_by,
  sig}` — exactly these members. `release_scope` is an absolute HTTPS URI selected by the estate owner;
  no two entries may share it. `grail_id` is
  `"grail:" || Hb("rapp/1:grail", kernel_bytes)`; `repository` is an absolute HTTPS URI;
  `immutable_ref` is a full `refs/tags/...` name that **MUST** resolve exactly to `commit`;
  `object_format` is `"sha1"` or `"sha256"` and fixes the required lowercase hexadecimal length of
  `commit` and `blob`; `path` at `commit` **MUST** resolve through the repository tree to exactly one
  regular blob with `mode` `"100644"` or `"100755"` and object id `blob`;
  `path` is a relative NFC POSIX path with no empty, `"."`, or `".."` component; `sha256` is the raw
  kernel bytes' 64-lowercase-hex SHA-256; `size_bytes` is their positive `uint53` length;
  `activated_utc` has the exact §7.4 form; `predecessor` is null or another `grail_id`; `declared_by` is
  a keyed rappid; and `sig` is a detached §10 JWS whose protected `kid` equals `declared_by`, over
  `canonical(entry \ {sig})`. The entry is additionally covered by the registry's §13.1 signature. A
  consumer verifies the entry signer as the estate owner in effect at `activated_utc`, verifies the
  referenced bytes, recomputes both hashes, persists the canonical entry on first activation, applies
  §11.1, and refuses a missing/mutated prior binding, duplicate `grail_id`, or locator whose bytes
  disagree.
- **estate_owner** `{type:"estate_owner", rappid}` (exactly one non-deprecated) · **master-plan**
  `{type:"master-plan", repo, path}` (Fed. Const. Art. VII).

§7.5 steps 1–5 are time-independent (append-only lookups); **only** step 6 (tombstones) and §13.2 owner
tenure are time-scoped, and both are monotone given the §13.1 no-rollback rule.

## 14. Security considerations
- **Integrity:** every object is domain-separated content-addressed (§5); a hostile mirror cannot alter
  bytes without breaking the hash, so *history is safe given a trusted head*.
- **Head freshness is not self-certifying:** the chain authenticates history, not which head is current; a
  hostile mirror may serve a stale/forked head. Consumers counter with the §7.6 monotonic-head rule; swarm
  heads **SHOULD** be owner-signed.
- **Cross-stream replay:** without §7.5 step 1a, any genesis/segment of stream A replays as stream B (seq=0,
  prev=null always pass). Step 1a's stream binding is mandatory.
- **Address-space confusion:** §5 domain tags make a particle, wave, egg, or rappid tail with equal hex
  non-interchangeable; stores key by `(space, hash)`.
- **Canonicalization attacks:** the §4 I-JSON input-domain profile (no duplicate keys, no lone surrogates,
  exact binary64, no normalization ambiguity) removes hash-splitting and NFC-twin vectors.
- **Identity forgery / key compromise:** authorship requires a keyed rappid + valid §10 `sig`; rotation is
  §6.3 re-anchor (verifiable authorization, §6.3/§13.3 — a self-asserted `_migrated_from` is refused);
  compromise is a §13 tombstone enforced at verify time. Because a tombstone gates on the frame's
  producer-controlled `utc`, a compromised key can still emit frames stamped just below `revoked_utc`; after
  a compromise the owner **SHOULD** advance affected stream heads (or re-genesis) past `revoked_utc`.
- **Root of trust:** the registry is the estate's signed root (§13.1); it is authenticated by an owner
  signature anchored to the out-of-band `estate_owner` rappid fingerprint, `registry_seq`-monotonic against
  rollback, and freshness-checked (a stale registry silently un-revokes keys and hides re-geneses).
- **Producer-controlled `utc` (DoS/merge bias):** a future-dated head can brick a stream (successors refused
  as earlier) and bias UTC-first merges. A consumer **SHOULD** refuse a frame whose `utc` exceeds receipt
  time by >300 s, and adversarial-scope merges **SHOULD** rank by `min(utc, first-seen)`; a bricked stream
  converges by re-genesis (§12.1).
- **Sealed-artifact limits:** a public mirror sees ciphertext and metadata. AES-GCM protects confidentiality
  only while the DEK remains secret; a recipient that has lawfully decrypted plaintext can copy it.
  Revocation stops future wrapped-key release, not prior possession. Shared passwords, embedded master keys,
  moving-branch URLs, nonce reuse under one DEK, and claims that bytecode cannot be inspected after
  decryption are non-conformant security postures (§9.2.1).
- **Kernel substitution:** testing mutable ring bytes and restoring the Grail only after approval creates
  an untested release. §11.1 requires the release-shaped artifact to contain the pinned bytes before its
  tests, attestations, and approval; a digest mismatch is a blocking `kernel-drift` finding.
- **Kernel registry rollback/rebinding:** persisting only `registry_seq` does not preserve an activated
  Grail declaration across a malicious higher-sequence registry. Consumers also persist every activated
  canonical `grail-kernel` entry and reject its later removal, mutation, or duplication (§11.1).

## 15. References
[RFC 2119] [RFC 8174] requirement terms · [RFC 8259] JSON · [RFC 7493] I-JSON · [RFC 8785] JCS ·
[FIPS 180-4] SHA-256 · [RFC 3986] URI · [RFC 5234] ABNF · [RFC 7405] case-sensitive ABNF · [RFC 9562] UUID
(obsoletes RFC 4122) · [RFC 5280] X.509 SPKI · [RFC 7515] JWS · [RFC 7797] unencoded JWS payload ·
[RFC 7518] JWA/ES256 · [RFC 8037] EdDSA in JOSE · [RFC 6979] deterministic ECDSA · [RFC 3339] timestamps ·
[NIST SP 800-38D] AES-GCM · [RFC 2104] HMAC · [RFC 5869] HKDF · [RFC 7516] JWE · [ECMA-262] ECMAScript.

---

### Revision log
- **rev-15 (the wire freeze)** — §12 freezes every form a `rapp/1` artifact is verified by (§4, §5,
  §6.1–6.2, §7.1, §7.3, §7.5, §8, §9.1); a change to any of them is `rapp/2` beside this document, never a
  revision of it, and `rapp/1` artifacts verify forever. Art. III is scoped to an estate's own artifacts.
  Registration, vocabulary, profiles, and the registry keep growing under `rapp/1` (Art. IV). Constitution
  Article 18 restates the rule.
- **rev-14 (DOGG specification-chain authority)** — makes the append-only
  `anchor/chain.jsonl` frame history carry normative specification content
  while protected canonical-main acceptance selects authority; defines the
  frame hash as durable revision identity; embeds the normative Markdown in a
  normal `body.pulse`; retains immutable rev-5–rev-13 pointer history; freezes
  a content-addressed bootstrap verifier profile; publishes hash-addressed
  frame objects and a deterministic index; makes `SPEC.md` a materialized
  selected-head view; and records the rev-13 Article 14 transition without
  inventing signatures or changing any RAPP/1 wire primitive.
- **rev-13 (public governance closure)** — makes the ratified public Protocol
  Constitution final for protocol governance; limits private governance and
  master plans to estate/product concerns; makes registry `protocol` entries
  subordinate adoption pins; verifies the exact canonical RAPP foundation
  object before anchoring; and aligns every public teaching surface with
  estate-specific registry authority.
- **rev-12 (foundation/protocol boundary)** — records `kody-w/RAPP` as the
  canonical public foundation and product home; limits `kody-w/rapp-1` to
  protocol authority; ratifies the complete public Protocol Constitution; makes
  registries explicit estate instances rather than protocol authorities; pins
  the canonical foundation commit and philosophy hash; and removes any
  implication that protocol publication transfers product, brand, company, or
  ownership authority.
- **rev-11 (planetary operations profiles)** — constitutionalized immutable candidate/serving lineage
  separation; defined RAPP CI/CD (`rapp-cicd/1`) and RAPP Deploy (`rapp-deploy/1`) as subordinate,
  registry-pinned production profiles; required exact-candidate qualification, production-shaped
  Preprod, cellular progressive exposure, expiring AI-health evidence, state/data continuity,
  automatic containment, and exact rollback while retaining policy-defined extension points; and
  defined typed, non-authoritative offspring/cross lineage without changing the egg or frame envelopes.
- **rev-10 (sealed artifact + Grail execution closure)** — registered the `sealed` egg variant for
  globally mirrorable public ciphertext with signed manifests and scoped recipient key release (§9.2.1);
  added the `rapp/1:sealed-aad` and `rapp/1:sealed-key-request` address spaces; retained rev-9's exclusive
  `release_scope` selection, persisted Grail binding, and verification-to-execution protections; and made
  both confidentiality limits and kernel drift release-blocking.
- **rev-9 (Grail selection and execution closure)** — makes release policy select only
  `release_scope`, resolves `grail_id` exclusively through the activated persisted registry binding,
  and closes verification-to-execution races by requiring a sealed immutable object/snapshot or
  platform-enforced write exclusion through byte consumption.
- **rev-8 (immutable Grail closure)** — makes pin selection deterministic through `release_scope`,
  defines the exact signed §13.3 `grail-kernel` entry and owner-at-time activation, requires consumers
  to persist every accepted binding, and specifies repository-object and executed-entry-point
  verification across interpreted and derived runtimes.
- **rev-7 (immutable Grail constitution)** — defines the Grail kernel by the SHA-256 of its exact bytes
  (§3), makes every ring and release/deployment stage verify both the pin and the actually executed entry
  point (§11.1), forbids post-test substitution, and makes changed bytes a different Grail rather than a
  mutation. This is release governance only; the RAPP wire and existing canonical forms are unchanged.
- **rev-6 (instantiation lineage)** — added §9.4's fresh per-install instance identity and immutable
  `grown_from` lineage, closing the hatch seam without changing the frame or egg envelopes.
- **rev-5 (war-game round 3 fold)** — folded 5 blockers + 7 majors + 7 minors, all clustered on the trust
  model that rev-4's fixes made load-bearing: the **registry is now a signed root of trust** (§13.1) —
  owner-signed, anchored to the out-of-band `estate_owner` rappid fingerprint, `registry_seq`-monotonic,
  freshness-checked (B-1); **re-anchor requires a verifiable §13.3 authorization record** with old-key
  continuity proof / tombstone / SPKI-tail check (B-2, mint-once now enforceable); **owner-succession is
  time-scoped** so a key rotation never invalidates historical signatures (B-3); **eggs are `stored`-only**
  (deflate is non-deterministic) with `canonical(manifest)` bytes (B-4); **invites sign under the
  estate-owner succession** not the egg's own rappid (B-5); `egg_hash` excludes `sig` (M-1); first
  re-genesis deprecates the creation genesis (M-2); full **registry entry schema** §13.3 (M-3); registry
  freshness rule (M-4); egg consumer enforces §9.1 (zip-slip, M-5); rotated key refused on new frames (M-6);
  `rapplication` exact `agent.py` (M-7); rev label, `invite` naming, sub-egg collision, rounding rule,
  idempotency, compromise-window, seal-path (m-1…m-7).
- **rev-4 (war-game round 2 fold)** — folded 6 blockers + 14 majors + 8 minors: domain-tagged mint
  reconciled across Constitution/ledger (B1); §4(c) binary64 round-trip test so `0.1` is accepted (B2);
  re-genesis head-reset exception so it isn't refused as rollback (B3); family-matched `*.re-genesis` kinds
  so memory/swarm streams can converge (B4); whole-egg address `H("rapp/1:egg-manifest",…)` + signed invites
  + manifest self-reference resolved + deterministic ZIP/`contents` ordering (B5, M2–M4); re-anchor
  enumerated three cases incl. key rotation (B6, M-rotation); `head_octets` pinned to the retained `legacy/`
  artifact (M6); subsequent-convergence via `deprecated` (M7); every stream registers its genesis (M8); JWS
  header canonical bytes + registry key-discovery + `estate_owner` designation (M9–M11); `/chat` error `step`
  as string incl. `"1a"` + code namespace + session semantics (M12, m5); tombstone as the one time-dependent
  verify check (M13); egg draft-artifact + dangling `§4` reference removed (M1, M5); calendar-valid `utc`,
  depth convention, kind dedup/bounds (m2, m7, m8).
- **rev-3 (war-game round 1 fold)** — folded 7 blockers + 19 majors + 12 minors from the Fable adversarial last-call:
  I-JSON input domain + no-normalization/NFC (§4); **domain-separated hashing** (§5, the stronger option);
  fixed `utc` byte form (§7.4); `prev_wave` by stream family not transport (§7.4); **stream-binding**
  anti-replay (§7.5.1a); `spec` token pinned to `rapp/1` (§7.1); full JWS profile + key discovery + rotation/
  tombstone (§10); hardened re-genesis with raw-byte terminal seal + registry linearization (§12.1); heads &
  forks (§7.6); `/chat` fully specified (§8); **egg variants ratified into the standard**, killing the
  6-spec collision and closing EGG-01 (§9); registry append-only (§13); type-validated verify (§7.5.1);
  cross-stream merge tie-break (§7.4); provisional-identifier rule (§6.3); all references added (§15).
- **rev-2** — first last-call tightening (7 self-review defects).
- **rev-1** — initial unified draft.

*The canonical protocol authority is the owner-selected, verified
specification chain in this repository. The canonical public RAPP foundation
and product home remain at `kody-w/RAPP`.*
