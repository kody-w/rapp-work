# Proposal 0006: owner succession in the Hive reference and the SDK

## Status

Draft, not accepted. Branch `experimental/gap-g6-owner-succession`, revised
after independent review round 1. The owner decides what moves. Intended
release: `rapp-work` `1.1.0` (additive; the package version and `SDK_VERSION`
are unchanged on this branch).

## Gap

**G6 — implementations refuse owner succession.** RAPP/1 already defines
time-scoped owner succession and compromise re-anchor (RAPP/1 sections 13.2
and 13.3), but the `rapp-hive/1` reference fails closed on any `re-anchor`
record and the SDK lists owner rotation among its refusals. Folder Hives need
no owner and are out of scope. G6 blocks the Private Hive part.

## Home specification and section

- `rapp-hive/1` (`protocols/rapp-hive/1/SPEC.md`) section 8.1 items 1 and 2
  and a new paragraph after item 5, a new paragraph in section 9.1, and
  section 14.2. That file is pinned by the frozen signed `registry.json`, so
  its text is proposed here only.
- `rapp-work-sdk/1` (`protocols/rapp-work-sdk/1/SPEC.md`) a new section 5.1
  and an inserted section 12 paragraph. That file is not registry-pinned; the
  edit is on this branch with its profile pins refreshed.

## Context: what is true today

1. **RAPP/1 already specifies succession.** `vendor/rapp-1/SPEC.md` (pinned by
   `RAPP1_PIN.json`, `kody-w/rapp-1` commit `591e014`):
   - section 13.2: "owner-signed" means the `kid` is the estate owner *in
     effect at the artifact's `utc`*, the current owner or a predecessor
     reachable through re-anchor records, with tenure
     `[record.utc, successor.utc)`; root-key compromise is recovered only by
     redistributing a new out-of-band anchor (section 13.1);
   - section 13.1: the registry signature verifies against the anchor's SPKI;
     a consumer persists the highest `registry_seq` and refuses a lower one;
   - section 13.3: `re-anchor {old_rappid, new_rappid, case, utc, sig,
     old_key_sig?}`, `old_key_sig` required for `rotation`; `tombstone
     {rappid, revoked_utc, sig}`; every entry is append-only;
   - section 6.3: a `compromise` re-anchor needs a tombstone "registered in
     the same append"; the estate owner's own record is signed by the
     outgoing owner key; root-key compromise is recovered only out of band;
   - section 10: a superseded `kid` is refused on artifacts with `utc` at or
     after the re-anchor, and a tombstoned key at or after `revoked_utc`;
   - section 14: `utc` is producer-controlled, so a key can still sign frames
     dated inside its own validity; the owner SHOULD advance affected heads;
     and "persisting only `registry_seq` does not preserve" accepted entries
     across a malicious higher-sequence registry (the Grail-kernel rule);
   - Constitution Art. 6: owner authority is evaluated against the owner in
     effect at the artifact's time; succession never rewrites history.
2. **The pinned reference verifier exists upstream.** `rapp_registry.py` at
   `kody-w/rapp-1@591e014` implements the owner-succession walk
   (`Registry.owner_at`), lifecycle signature checks
   (`check_lifecycle_signatures`), superseded-key and tombstone refusal at a
   time, fresh-tail and single-predecessor rules, key-tail alias matching, and
   the explicit authenticated `tombstone_issued_at` resolver. It states that a
   snapshot cannot prove same-append provenance and that the caller retains
   high-water marks (`EXTENDING.md`, "The reference will check your estate").
3. **Finding, which also fixes drift: the vendored copy here was stale.**
   `vendor/rapp-1/rapp_registry.py` on `main` (SHA-256 `f055a4f9…`) equals
   `kody-w/rapp-1@35278ef`, older than the accepted pin `591e014` (SHA-256
   `eec22844…`). It lacked `check_lifecycle_signatures`, the issuance
   resolver, alias matching, and the fresh-tail rules. Nothing pinned it:
   `RAPP1_PIN.json` covers only `SPEC.md` and `rapp.py`. This branch needs the
   accepted bytes, so it keeps the sync; the zero-drift lead may land the sync
   separately first.
4. **The Hive reference fails closed.**
   `protocols/rapp-hive/1/reference/hive_acceptance.py` `RegistryAuthority`
   verifies the registry against one anchored owner SPKI, verifies tombstones
   against that key, and raises "registry: succession requires a full
   section-13 tenure verifier" on any `re-anchor` entry. `HiveAcceptance`
   compares declaration, reconciliation, convergence, and projection signers
   with that single `registry.owner`. SPEC section 8.1 item 2 scopes this as
   "the direct-owner profile"; section 14.2 says the reference "fails closed on
   owner succession records requiring a full time-scoped section 13 tenure
   verifier" and that a production adapter must supply "the full parent
   verifier where those features are needed".
5. **The Hive reference copies are standalone.** The reference imports its own
   `protocols/rapp-hive/1/reference/rapp.py` (byte-identical to
   `vendor/rapp-1/rapp.py`, SHA-256 `1a04362b…`). The legacy project skill
   vendors a byte-exact copy under
   `.github/skills/rapp-private-hive/vendor/hive/`, enforced by
   `test_vendored_authenticated_profile_is_byte_exact_and_standalone` and its
   checksum lock `rapp/agent.lock.json`. The wheel ships the reference as
   `rapp_work._protocols` and the vendored parent as `rapp_work._vendor_rapp1`.
   A downstream consumer can run the default gate from only `rapp.py`,
   `rapp_hive.py`, `rapp_profile.py`, `hive_acceptance.py`, and `SPEC.md`.
6. **The SDK refuses owner rotation** in three places:
   `protocols/rapp-work-sdk/1/SPEC.md` section 12 ("owner rotation … are
   explicit refusals"); `docs/API.md` "Explicitly deferred"; and the legacy
   `rotate-owner` command, which `rapp_work.compat.run_private_hive_cli`
   passes to `.github/skills/rapp-private-hive/scripts/deploy_hive.py`, where
   it is refused before effects. `HiveVector.from_verified_bundle`
   (`src/rapp_work/hive.py`) and `verify_source_estate`
   (`src/rapp_work/profiles.py`) verify registry signatures against one
   anchored key. The legacy Private Hive publisher refuses every
   non-direct-owner registry (`lib/private_hive/authority.py`), so a legacy
   bundle can never contain a succession.

## Design decisions

1. **Reuse the pinned reference; do not re-type it (Art. 10).** Sync
   `vendor/rapp-1/rapp_registry.py` to the exact bytes of the already accepted
   commit `591e014` (cross-checked against `raw.githubusercontent.com`) and
   pin them with a new additive record, `RAPP1_REGISTRY_PIN.json`. The
   accepted canonical revision does not change.
2. **Keep the Hive reference standalone, and keep its default minimal.** Carry
   a byte-exact `protocols/rapp-hive/1/reference/rapp_registry.py` beside its
   `rapp.py` copy. `hive_acceptance.py` imports it only inside the succession
   path, so the default gate still runs from the five files of context item 5.
   `tools/check.py` and Hive check H21 require every copy to equal the pin.
3. **Default stays fail-closed; succession is an explicit opt-in.** The
   `rapp-hive/1` text does not already require succession by default.
   Section 1 item 8 ("refuse in favor of RAPP/1 whenever this profile
   conflicts") is a fail-closed tie-break: a verifier that refuses a registry
   it cannot fully evaluate never accepts what RAPP/1 forbids, and it never
   evaluates authority against "only the current" owner, because it refuses
   instead. Section 8.1 item 2 scopes the reference to the direct-owner
   profile, and section 14.2 delegates the full tenure verifier. So
   `RegistryAuthority(...)` without the new arguments behaves exactly as on
   `main`: its direct-owner branch and `checkpoint()` are unchanged, and every
   new check is guarded by the opt-in. `RegistryAuthority(...,
   succession="rapp1-13.2", tombstone_issued_at=resolver,
   retained_registry=state)` selects the new path. Any other `succession`
   value, a missing or non-callable resolver, or a resolver or retained state
   passed without `succession` is refused.
4. **Anchor semantics: the original anchor may walk forward, but only with
   retained state.** RAPP/1 section 13.1 distributes the owner anchor once,
   and section 6.3 reserves out-of-band re-anchoring for root-key compromise,
   so a routine rotation should not force every consumer to fetch a new
   anchor. The anchor may therefore be the current estate owner or any
   predecessor in the owner lineage, provided every transition from the
   anchor forward is `case:"rotation"` (outgoing-owner `sig` and
   `old_key_sig`, checked by the pinned reference). This reads section 13.1's
   "verify against the anchor's SPKI" as satisfied transitively, and it
   bypasses the pinned loader's own "names any other owner" refusal
   (`EXTENDING.md` rule 4) by passing it the verified current owner. Because
   that relaxation is exactly what a leaked predecessor key would exploit, it
   is accepted only together with the consumer's retained registry state
   (decision 7); open question 1 asks the owner to confirm the reading. An
   owner `compromise` transition cannot extend an old anchor: sections 13.1
   and 13.2 say root-key compromise "cannot be expressed inside the registry
   it signs". Owner transitions of `case` `upgrade` or `tag-migrate` are
   refused: the pinned reference does not check their historical evidence.
5. **The pinned reference decides every section 13 question.** In succession
   mode the Hive authority calls `rapp_registry.Registry` and
   `rapp_registry.load_document(..., trust_anchor=<current owner>,
   persisted_seq=..., tombstone_issued_at=...)`: exact entry member sets,
   one estate owner, the registry signature by the current owner, lifecycle
   signatures by the owner in tenure (the outgoing owner for its own
   transition), nonempty forward tenure, rotation continuity from a key not
   already retired, a registered tombstone for every compromise, single
   predecessors, and fresh (never ancestral or renamed) key tails. The
   resolver maps the exact signed tombstone's particle hash to an
   authenticated issuance UTC; it is never inferred from `revoked_utc`, and
   lookup failures are refusals.
6. **Hive signatures use the key history at the artifact's `utc`.**
   `verify_signature` calls the pinned reference's
   `Registry._signer_acceptable(kid, utc, match_key_aliases=True)`, the same
   primitive the reference applies to rotation continuity proofs, so a
   superseded or tombstoned SPKI is refused under any RAPPID name. Owner checks
   in `HiveAcceptance._authorized` use `registry.owner_at(frame["utc"])` for
   declarations, reconciliations, convergences, and projection receipts; in
   direct-owner mode `owner_at` returns the one anchored owner, so the default
   is unchanged. A projection's signed egg (an `invite` egg must be signed by
   the estate owner) is checked with the owner at its `created_utc`.
7. **One retained registry state; succession never rewrites history (Art. 6,
   RAPP/1 sections 13.3 and 14).** Under succession the persisted floor, its
   same-sequence commitment, the verified owner lineage, and the sorted
   particle hashes of every `re-anchor` and `tombstone` entry form one value,
   `retained_registry` (`RETAINED_REGISTRY_KEYS`). `checkpoint()` carries it
   under succession, so the caller persists it atomically with the head, and
   it is the only way to pass a floor in that mode (`minimum_registry_seq` and
   `same_sequence_hash` are refused there). It is required whenever the anchor
   is not the current owner; such a consumer starts from the state of a
   registry it verified while its anchor was the current owner, and a Hive
   switching from direct-owner mode takes it from that authority's
   `retained_registry`. A later registry must extend the retained lineage and
   keep every retained lifecycle entry byte for byte, whoever signs it. This is
   the Hive counterpart of the rule RAPP/1 section 14 states for Grail-kernel
   entries. The SDK takes the same state as `retained` (a `VerifiedRegistry`
   or its `to_dict()` record).
8. **Causal bounds: an owner act cannot reach state created after its own
   time.** RAPP/1 lets a key sign frames dated inside its tenure. Under
   succession the Hive therefore requires that a convergence be strictly later
   than the Mother head it extends and not earlier than any candidate it lists
   (by summary and by authenticated bytes); that a reconciliation not be
   earlier than the Mother head it resolves; and that a current receipt not be
   earlier than its convergence or than the latest `re-anchor` `utc` or trusted
   tombstone issuance in the registry it names. With those bounds, and with
   each key's tenure half-open, a retired, superseded, or compromised key can
   only sign acts over state that existed inside its own tenure; the successor
   closes even that window by advancing the Mother stream and every receipt
   stream past the boundary (Migration).
9. **Same-append provenance: enforce where observable, fail closed across
   gaps.** RAPP/1 section 6.3 requires a compromise re-anchor's tombstone "in
   the same append", which one snapshot cannot show. Given retained state, a
   `compromise` record that is new since that state is accepted only in the
   registry exactly one sequence later and only with a tombstone for its
   `old_rappid` that is also new. Across skipped sequences it is refused; the
   caller verifies each intermediate registry in order. A first verification,
   which no retained state precedes, relies on the trusted issuance context,
   as the pinned reference documents.
10. **Membership is not inherited.** The declaration is immutable and names
    member RAPPIDs. A successor owner receives the owner *authority* that
    `rapp-hive/1` defines against the registry owner (Mother convergence,
    reconciliation, projection receipts). It does not silently inherit the
    predecessor's member record, area, or room audience; a re-anchored member
    likewise. Changing the roster is G1 (an owner-signed later declaration);
    see Related proposals.
11. **The SDK verifies; it does not rotate.** Performing a rotation or a
    compromise recovery means minting keys and signing and appending registry
    records: an estate owner's signing act that the SDK SPEC already refuses as
    a parent-authority change. Routing it through a plan-hash-gated operation
    would add a seventh operation or overload `scaffold`, `update`, or `migrate`
    with signed-authority effects. The legacy `rotate-owner` command therefore
    stays refused. What G6 needs from the SDK is lawful *verification*: the
    explicit submodule `rapp_work.registry` verifies a registry or a registry
    lineage across owner succession through the pinned reference, read-only,
    offline, with no new JSON operation and no change to `rapp_work.__all__`.
    `verify_source_estate` and `HiveVector.from_verified_bundle` are unchanged:
    the first verifies this repository's frozen evidence, which has no
    succession; the second consumes legacy bundles, which cannot contain one.

## Proposed change

### A. `rapp-hive/1` normative text (activation owner-blocked)

Activation owner-blocked: the signed registry pins the SPEC hash; the owner
must accept the text and re-sign.

**Section 8.1 item 1.** Replace:

> 1. A verified, fresh section 13 registry anchored out of band, with persisted
>    sequence/hash protection against rollback and same-sequence forks.

with:

> 1. A verified, fresh section 13 registry anchored out of band, with persisted
>    sequence/hash protection against rollback and same-sequence forks. Under
>    owner succession (RAPP/1 section 13.2) the persisted state also holds the
>    verified owner lineage and the particle hash of every accepted
>    `re-anchor` and `tombstone` entry. A later registry, whoever signs it,
>    must extend that lineage and keep every such entry byte for byte. An
>    out-of-band anchor that is not the current estate owner is accepted only
>    together with that state.

**Section 8.1 item 2.** Replace:

> 2. The owner-signed declaration at the Mother's registered creation genesis.
>    In the direct-owner profile, the declaration owner is the anchored estate
>    owner. Mother Hive `stream_id` is exactly `hive_rappid`.

with:

> 2. The owner-signed declaration at the Mother's registered creation genesis.
>    The declaration owner is the estate owner in effect at the declaration's
>    `utc` (RAPP/1 section 13.2): in the direct-owner profile, the anchored
>    estate owner; under owner succession, the owner whose tenure contains that
>    time. Declarations, reconciliations, convergences, and projection
>    receipts are signed by the owner in effect at their own `utc`. A
>    successor never re-signs or invalidates history signed inside a
>    predecessor's tenure and does not inherit a predecessor's declared
>    membership. Mother Hive `stream_id` is exactly `hive_rappid`.

**Section 8.1, new paragraph after item 5.** Insert:

> Under owner succession an owner act cannot reach state created after its own
> `utc`, so a retired, superseded, or compromised owner key cannot back-date
> authority over later state. A convergence is strictly later than the Mother
> head it extends, and no candidate it lists is later than it, whether that
> time is read from the candidate summary or from the candidate's
> authenticated bytes. A reconciliation earlier than the Mother head named by
> its `base_head_frame_hash` is quarantined as `invalid-reconciliation`. A key
> may still sign frames dated inside its own tenure (RAPP/1 section 14). After
> a rotation or a compromise re-anchor the successor owner SHOULD promptly
> append a Mother convergence, and a receipt on every receipt stream, at or
> after the boundary; RAPP/1 section 7.5 step 4 then refuses any earlier-dated
> successor on those streams.

**Section 9.1, new paragraph after the numbered list.** Insert:

> Under owner succession a `current` receipt is not earlier than the
> convergence it names, nor than the latest `re-anchor` `utc` or trusted
> tombstone issuance time in the registry whose `registry_seq` it names.

**Section 14.2, third paragraph.** Replace:

> The direct-owner registry reference checks real detached JWS/SPKI binding,
> the exact profile pin, kinds, active genesis, sequence floor/same-sequence
> commitment, and signed tombstones. It fails closed on owner succession
> records requiring a full time-scoped section 13 tenure verifier. A production
> adapter must supply fresh registry retrieval, persistent high-water marks,
> distributed storage CAS, retention, and the full parent verifier where those
> features are needed. These are trust prerequisites, not Boolean payload
> flags. No result here certifies key release, plaintext consent, global DOGG
> publication, or full estate-wide RAPP/1 conformance.

with:

> The registry reference checks real detached JWS/SPKI binding, the exact
> profile pin, kinds, active genesis, sequence floor/same-sequence commitment,
> and signed tombstones. By default it is direct-owner, fails closed on any
> `re-anchor` record, and does not load the parent registry reference. With
> `succession="rapp1-13.2"` and a trusted tombstone issuance resolver, it
> verifies RAPP/1 section 13.2 owner tenure and section 13.3 `re-anchor` and
> `tombstone` records through the pinned RAPP/1 registry reference
> (`reference/rapp_registry.py`, pinned by `RAPP1_REGISTRY_PIN.json`):
>
> - the out-of-band anchor is the current estate owner or a predecessor
>   reachable only through signed `rotation` records; an owner `compromise`
>   record requires a newly distributed anchor (RAPP/1 sections 13.1 and
>   13.2); owner transitions of any other case are refused;
> - each owner succession record is signed by the outgoing owner; owner
>   tenures are nonempty and forward; a successor identity has exactly one
>   predecessor and a fresh key tail;
> - a tombstone is signed by the owner in effect at its authenticated issuance
>   time, which the trusted resolver supplies and `revoked_utc` never does; a
>   compromise record requires a registered tombstone;
> - every Hive signature is refused at or after its key's supersession or
>   revocation time, matching the key by SPKI tail so that a renamed RAPPID
>   cannot revive it; history before those times keeps verifying;
> - the current estate owner key is live;
> - the persisted floor, same-sequence commitment, owner lineage, and
>   lifecycle entry hashes travel together as one retained registry state,
>   which `checkpoint()` carries; a later registry must extend that lineage
>   and keep every retained entry, and the state is required whenever the
>   anchor is not the current estate owner;
> - a `compromise` record that is new since the retained state is accepted
>   only in the registry one sequence later and only together with a new
>   tombstone for its `old_rappid` (RAPP/1 section 6.3); a first
>   verification, which no retained state precedes, relies on the trusted
>   issuance context for that provenance; and
> - the causal bounds of sections 8.1 and 9.1 hold.
>
> A production adapter must supply fresh registry retrieval, persistent
> high-water marks with their retained registry state, append provenance for a
> first verification, distributed storage CAS, and retention. These are trust
> prerequisites, not Boolean payload flags. No result here certifies key
> release, plaintext consent, global DOGG publication, or full estate-wide
> RAPP/1 conformance.

Optional editorial change, section 8.2 second bullet: "registry SPKI/RAPPID
binding, and time-scoped revocation" becomes "registry SPKI/RAPPID binding,
and time-scoped supersession and revocation".

### B. `rapp-work-sdk/1` normative text (on this branch)

New section 5.1, inserted after section 5:

> ### 5.1 Registry authority and owner succession
>
> `RAPP1_REGISTRY_PIN.json` pins the exact `rapp_registry.py` of the same
> accepted `kody-w/rapp-1` revision named by `RAPP1_PIN.json`. The SDK verifies
> those bytes, and binds their `rapp` import to the already verified parent,
> before use.
>
> `rapp_work.registry` verifies a signed `rapp/1-registry` document read-only.
> The caller supplies the entries member name, the out-of-band anchor RAPPID
> and SPKI, a trusted tombstone issuance resolver keyed by the exact signed
> tombstone's particle hash, and the registry state it retained from its last
> verification. None of these is read from the document. The pinned reference
> decides every section 13.3 entry, owner tenure, lifecycle signature, and
> time-scoped key retirement. The SDK additionally requires that:
>
> 1. the anchor is the current estate owner or a predecessor reachable only
>    through `case:"rotation"` re-anchor records; an owner `compromise` record
>    requires a newly distributed out-of-band anchor (RAPP/1 sections 13.1 and
>    13.2);
> 2. every owner transition is a `rotation` or `compromise` record;
> 3. the current estate owner key is registered and never deprecated,
>    superseded, or tombstoned;
> 4. key retirement matches the SPKI tail, so a renamed RAPPID cannot revive a
>    superseded or tombstoned key;
> 5. an anchor that is not the current estate owner is accepted only together
>    with retained state: the caller's last verified registry, which also
>    carries the persisted sequence floor and same-sequence commitment;
> 6. a registry verified after retained state keeps every retained `re-anchor`
>    and `tombstone` entry byte for byte and extends, never rewrites, the
>    retained owner lineage, so no later registry, whoever signs it, can undo a
>    succession or a revocation;
> 7. a `compromise` re-anchor that is new since the retained state appears in a
>    registry exactly one sequence later, together with a new tombstone for its
>    `old_rappid` (the RAPP/1 section 6.3 same-append rule; a single snapshot
>    cannot show it, so a first verification relies on the trusted issuance
>    context); and
> 8. a registry lineage is contiguous, and each snapshot is verified with the
>    previous one as its retained state.
>
> A verified registry reports the owner in effect at an artifact time and
> supplies a signature verifier for `validate_frame` and `validate_chain`. This
> is verification only. The SDK never mints keys or signs, appends, or rewrites a
> registry, re-anchor, or tombstone, and adds no JSON operation.

Section 12, insert before its existing paragraph, which stays byte-identical:

> In the list below, owner rotation means performing it: minting keys, or
> signing or appending a registry, re-anchor, or tombstone record. The SDK also
> refuses owner succession that does not descend from the out-of-band anchor
> through signed rotation or that does not extend the caller's retained registry
> state. Read-only verification of lawful RAPP/1 owner succession (section 5.1)
> is supported.

## Token and compatibility analysis

- **Frozen `rapp/1` forms (Art. 18):** unchanged. No frame key, canonical form,
  hash tag, RAPPID rule, consumer-checklist step, wire form, or egg form moves.
  No new envelope, endpoint, kind, or registry entry type (Art. 4).
- **`rapp-hive/1`:** no payload schema, kind, catalog, manifest, or receipt
  shape changes; `schema.json` is untouched. The proposed text evaluates the
  existing word "owner" by the parent's own section 13.2 rule and adds
  refusals that apply only under succession. Every existing direct-owner
  artifact keeps verifying because a registry without `re-anchor` records has
  exactly one owner in effect at all times. No token move is needed (Art. 2
  concerns shapes; this is Art. 6 authority evaluation).
- **`RegistryAuthority` default:** unchanged in behavior. The direct-owner
  branch, its refusals, and `checkpoint()` (exactly `registry_seq`,
  `registry_hash`, `hive_rappid`, `mother_head_frame_hash`, `catalog_hash`)
  are as on `main`; every new check is guarded by `succession`; and the
  default no longer needs `rapp_registry.py` importable (vector
  `test_default_path_runs_without_the_registry_reference`). The existing
  H1–H20, including all 64 authenticated vectors, pass unmodified. New
  keyword arguments default to `None`; `owner_at()`, `anchor`,
  `owner_lineage`, `lifecycle`, `retained_registry`, `epoch` (succession
  only), and `succession` are additive attributes.
- **Under succession:** `checkpoint()` (and the `accept_convergence`,
  `restore`, and `accept_projection` results built from it) gains
  `owner_lineage` and `registry_lifecycle`. This is an in-process Python value
  of the reference gate, not a versioned wire record; the default mode's value
  is unchanged. A differential run of the 56 direct-owner authenticated test
  methods with succession forced on (same single owner) gives identical
  results except one refusal whose message wording differs.
- **New token `rapp-work-parent-registry-pin/1`:** a new closed record
  (`schema`, `protocol`, `repository`, `commit`, `reference_path`,
  `reference_sha256`) rather than widening `rapp-work-parent-pin/1` (Art. 2).
  `RAPP1_PIN.json` and `RAPP_WORK_PIN.json` are unchanged, and the canonical
  commit stays `591e014`.
- **`rapp-work-sdk/1`:** the six-operation closed JSON API, its inputs, its
  envelopes, plan-hash apply, offline default, no-follow effects, and inert
  discovery are unchanged. `rapp_work.registry` is an explicit submodule; the
  top-level `rapp_work.__all__` contract test is unchanged. The SPEC edit is
  two insertions; it refreshes `protocols/index.json` and
  `src/rapp_work/data/profiles.json` (`rapp-work-sdk/1` `spec_sha256`
  `cf64a90f…` → `19802755…`).
- **Vendored `rapp_registry.py` sync:** stricter validation (fresh tails,
  single predecessors, alias matching, lifecycle signatures). The frozen
  `registry.json` has no `re-anchor` or `tombstone` entries, so
  `tools/check.py` is unaffected.
- **Legacy skill:** the vendored reference is re-synced byte-exact (plus the
  new `rapp_registry.py`), and `rapp/agent.lock.json` gains the new hashes. The
  skill's own authority layer still refuses every succession and uses the
  default path, so its behavior is unchanged. Its lock `version` stays `3.2.0`
  (open question 11).
- **Downstream pins:** a consumer that pins `hive_acceptance.py` or the
  `rapp-work-sdk/1` SPEC by SHA-256 at `main` keeps working at that commit; if
  it adopts this branch it must re-pin both (`hive_acceptance.py`
  `88184a7e…` → `4ef87e44…`; SDK SPEC `cf64a90f…` → `19802755…`). The
  five-file default deployment of context item 5 keeps working without
  `rapp_registry.py`. See Owner actions for the estate-lead items.
- **Python:** the 3.10 floor and 3.13 are verified. `cryptography` stays the
  only runtime dependency.

## Security and privacy analysis

- **Trust inputs are explicit and never read from the document:** the anchor
  RAPPID and SPKI (tail-bound), the tombstone issuance resolver, and the
  retained registry state. Resolver failures and invalid UTC values are
  refusals, never a fallback to `revoked_utc`.
- **No registry rollback undoes a rotation.** With retained state, a later
  registry is refused if it drops or rewrites any retained `re-anchor` or
  `tombstone` entry or does not extend the retained owner lineage, whoever
  signed it: a leaked retired anchor key that re-signs a higher registry
  without the rotation, a current owner who drops a tombstone or a member
  re-anchor, or a re-signed rotation that moves an owner boundary (review
  experiments E3–E7, E9, now vectors). Retained state is mandatory in exactly
  the cases where it matters: whenever a floor exists (it is the only carrier
  of the floor under succession) and whenever the anchor is a predecessor,
  which is the key a leaked retired key would impersonate.
- **Anchor strength is still the anchor key's strength.** A consumer that
  keeps no state is a fresh consumer: whatever its anchor key signs is
  authoritative to it, including a forged registry from a leaked anchor key
  that shows no rotation (vector: the forgetful consumer). RAPP/1 section
  13.1 already implies this. A consumer anchored at the current owner is not
  exposed to a leaked predecessor key, because that key cannot sign a registry
  whose lineage contains the current owner.
- **Back-dating (RAPP/1 section 14).** The causal bounds of design decision 8
  mean a retired, superseded, or compromised owner key can only sign owner acts
  over state that existed inside its own tenure: it cannot converge a later
  frame (even behind a false candidate summary), resolve a conflict recorded
  by a later Mother head, attest a later convergence, attest any registry that
  records its own retirement, or append at the instant of the head it extends
  (review experiments E1, E2 and the compromise variant, now vectors). Inside
  its tenure it can still act until the successor advances the Mother stream
  and every receipt stream past the boundary (vector: the residual, then
  refused after the heir's advancing convergence).
- **Residual risks that remain (documented, not claimed closed).** (1) A
  predecessor that is also a declared member can still sign member frames
  dated inside its tenure; they reach the catalog only if an owner in tenure
  converges them, and G1 is the way to retire that member. (2) Standalone
  artifacts dated inside a tenure, such as an owner-signed `invite` egg,
  verify forever. (3) The pinned reference refuses a rotation whose outgoing
  key carries a tombstone dated at or before the rotation, even when that
  tombstone is issued later, so a key that leaks after a routine rotation
  cannot be revoked for its own tenure without invalidating the registry
  (open question 3).
- **Same-append provenance (RAPP/1 section 6.3)** is enforced exactly when the
  retained state is one sequence behind, refused across skipped sequences, and
  delegated to the trusted issuance context for a first verification, as the
  pinned reference documents.
- **Forward security:** a superseded key is refused at and after the re-anchor
  `utc`, and a tombstoned key at and after `revoked_utc`, including every
  renamed RAPPID with the same SPKI tail. Between a compromise cutoff and its
  re-anchor time no key holds owner authority, which fails closed.
- **Denial of service:** lineage walks are bounded by the number of re-anchor
  records; registry documents stay within the RAPP/1 one-MiB I-JSON bound;
  retained-state arrays are capped at 65536 items; an SDK lineage is capped at
  4096 snapshots. The receipt bound makes a future-dated lifecycle record block
  current receipts until its time (fail closed; open question 4).
- **Loading the pinned reference:** the SDK reads the bytes once, checks their
  SHA-256 against the pin, and executes exactly those bytes with their single
  `import rapp` bound to the already verified parent module, as
  `rapp_work.rapp1` does for `rapp.py`. It does not touch `sys.path` or
  `sys.modules`. The Hive reference imports its pinned copy only under
  succession.
- **Privacy:** no new data flow, network access, credential, or storage.
  Vectors use published `PUBLIC TEST VECTOR ONLY` seeds and `example.invalid`
  locators. DOGG/GODD boundaries, rooms, and sealed eggs are unchanged.

## Migration

- **Existing direct-owner Hives and SDK users:** nothing changes, including
  `checkpoint()`.
- **Opting an existing Hive in:** take the first retained state from the
  direct-owner authority you last accepted (`gate.registry.retained_registry`:
  its sequence, commitment, `(owner,)`, and tombstone hashes), then construct
  `RegistryAuthority(..., succession="rapp1-13.2", tombstone_issued_at=...,
  retained_registry=state)` and persist `checkpoint()` from then on; pass its
  `RETAINED_REGISTRY_KEYS` members back each time. Existing history that meets
  the causal bounds (all 56 direct-owner test methods do) restores unchanged
  across the boundary; history that violates them is refused, fail closed.
- **Planned rotation (owner process, outside the SDK):** register the
  successor `spki`; append `re-anchor {case:"rotation"}` signed by the outgoing
  owner (`sig` and `old_key_sig`); name the successor in the single
  `estate_owner` entry, as the pinned reference requires; increment
  `registry_seq`; sign with the successor key. The successor then promptly
  appends a Mother convergence (re-offering a settled frame is enough) and a
  receipt on every receipt stream, at or after the boundary. Consumers keep
  their original anchor and their retained state.
- **Owner compromise:** append `re-anchor {case:"compromise"}` and a tombstone
  with the compromise cutoff in one registry revision (one `registry_seq`
  step), redistribute the new anchor out of band, and have the successor
  advance the same heads at or after the re-anchor `utc`. Consumers re-anchor
  to the new owner and keep their retained state; one that skipped that
  revision verifies each intermediate registry in order.
- **Member rotation or compromise:** the same registry steps, signed by the
  owner in tenure; the same-append rule applies to a member compromise.
- **This repository's own estate:** `registry.json` and root `SPEC.md` stay
  frozen. Adopting succession for it is the estate owner's signing decision.

## Rollback

Revert the branch. The default direct-owner path is unchanged, so rollback
only removes the opt-in: registries with `re-anchor` records fail closed again
(the safe direction), and `(registry_seq, registry_hash)` checkpoints stay
valid. A Hive that ran under succession keeps its extra checkpoint members as
unused data. The `vendor/rapp-1/rapp_registry.py` sync and its pin can be
kept independently, because they restore the accepted canonical bytes.

## Conformance and test vectors

All identities are real Ed25519 keys from published fixture seeds.

**Hive (`python3 protocols/rapp-hive/1/reference/hive_conformance.py`, 22
checks):** H21 requires the reference's `rapp.py` and `rapp_registry.py` to
equal their pins; H22 runs `succession_conformance.py` (31 vectors):

| Vector | Result |
|---|---|
| default authority on a member re-anchor, on a succeeded registry anchored at the heir, and at the original owner | refused (fails closed) |
| default gate loaded with `rapp_registry` unimportable: authority, gate, convergence; succession requested in that process | accepted with the five-member checkpoint; `ImportError` |
| unsupported mode; resolver or retained state without the opt-in; missing or non-callable resolver | refused |
| predecessor anchor without retained state; `minimum_registry_seq` or `same_sequence_hash` under succession; eight malformed retained states | refused |
| default checkpoint; succession checkpoint | exactly five members; plus `owner_lineage` and `registry_lifecycle`, equal to `retained_registry` |
| planned rotation A→B from the original anchor A with retained state; from anchor B | accepted; `owner_at` is A before and B at the boundary |
| history accepted under the direct-owner registry, restored under the succeeded registry | accepted |
| post-boundary object and convergence by A | quarantined / refused (superseded); state unchanged |
| post-boundary convergence by B; fresh gate restored from the persisted checkpoint's retained state | accepted; identical checkpoint and catalog |
| declarations dated after the boundary: B naming B; A naming A; B naming A; A naming B | accepted; refused ×3 |
| post-boundary reconciliation by B, by A; projection receipt by A, by B | accepted, quarantined; refused, current |
| succession record signed by B, continuity by B, registry signed by an outsider (anchored at A or B) | refused |
| next owner at, before, or after the boundary (empty, backwards, forward tenure) | refused, refused, accepted |
| retained state vs a registry inventing an earlier owner; vs a forward extension | refused; accepted |
| retained state vs a leaked retired anchor key's higher registry without the rotation (E3); a bare floor; that registry for a consumer with no state | refused; refused; accepted (fresh consumer) |
| retained state vs a dropped tombstone (E4), a dropped member re-anchor (E6), a moved owner boundary (E5); an unchanged successor | refused ×3; accepted |
| anchor outside the lineage (outsider, member); anchor SPKI not bound; anchor key not registered | refused |
| owner compromise with tombstone and resolver: old anchor; without tombstone; new anchor | refused; refused; accepted |
| under compromise: history before the cutoff; object and convergence by A after it; B before the re-anchor; B after it; fresh `restore()` | accepted; refused; refused; accepted; identical |
| back-dated convergence by retired A over a post-boundary frame (E1): live gate; fresh `restore()`; behind a false candidate summary | refused ×3; state unchanged |
| back-dated convergence by A over pre-boundary state (the residual); after B's convergence at the boundary, A dated before it, A at it | accepted; refused (time order), refused (superseded) |
| compromised A back-dated below its cutoff over a frame from after the cutoff | refused |
| convergence at the instant of its base head: direct-owner default; under succession; B one instant later | accepted; refused; accepted |
| reconciliation by retired A dated before the Mother head it resolves; by B after it | quarantined, conflict kept; accepted, parents superseded |
| current receipt by A inside A's tenure, for A's head, naming the registry that retires A; by B at the boundary | refused; current |
| receipt by A or by B dated before B's convergence it attests (E2) | refused ×2 |
| new compromise record across a skipped sequence; one sequence later with its tombstone; reusing a tombstone from an earlier append | refused; accepted; refused |
| succession registry with a wrong profile spec hash; with a deprecated Hive kind | refused ×2 |
| owner-signed `invite` egg carried after the boundary: by A dated in A's tenure; by B in B's tenure; by B dated in A's tenure; by A after its retirement | current, current, refused, refused |
| resolver: missing entry, invalid UTC, `None`, issuance in the successor's tenure | refused (never guessed) |
| tombstone signed by the stale owner vs the owner in tenure at issuance | refused; accepted |
| predecessor tombstoned before its own rotation | refused |
| member compromise: object before the cutoff, after it, by the successor identity; forged record; no tombstone | accepted, quarantined, quarantined; refused; refused |
| ambiguous predecessor | refused |
| rotation to a renamed alias of the same key; back to an ancestral tail; alias member before and after the boundary | refused; refused; accepted, quarantined |
| `upgrade` or `tag-migrate` owner transition | refused |
| current owner key tombstoned | refused |
| predecessor SPKI deprecated after rotation | history still restores |
| rollback and same-sequence fork through retained state; identical same-sequence; tampered sequence | refused; accepted; refused |

**SDK (`python3 -m pytest -q tests/test_registry_succession.py`, 22 test
functions, 32 tests):** the pinned-reference hash and `rapp` binding;
tampered reference bytes and a wrong pin refused before use; rotation from
the original anchor with retained state (as a `VerifiedRegistry` or its
`to_dict()` record) and from the current anchor, and without retained state
refused; `validate_chain` across the boundary (A before accepted, A after
refused as superseded, B after accepted, wrong expected signer refused);
records not signed by the outgoing owner; empty and backwards tenure; owner
compromise (old anchor, missing resolver, missing entry, missing tombstone
refused; new anchor accepted; A acceptable before the cutoff and refused
after); member compromise and stale-owner tombstones; ambiguous predecessor;
renamed-alias revival; anchor lineage, SPKI binding, and an unregistered
anchor key; a live owner key; rollback and same-sequence fork through
retained state; a non-record and 11 malformed retained records refused; a
leaked retired anchor key's rollback registry (E7) refused for both retained
forms, a moved boundary (E9) refused by `verify_registry` and
`verify_registry_lineage`, and the same rollback accepted only by a consumer
with no state; same-append (E8) refused across one step, accepted together,
and refused across a skipped sequence; `upgrade` and `tag-migrate` owner
transitions refused; a lineage across the boundary feeding `HiveVector`
high-water; lineage gaps, dropped revocations, and rewritten owner history
refused; a lineage continued under a new anchor after compromise; and
performing rotation still refused (`execute("rotate-owner")` and the legacy
`rotate-owner` command).

**Differential against the default suite.** The 56 direct-owner authenticated
test methods (64 with subtests) were also run with succession forced on for
the same single owner (a trivial issuance resolver and an HTTPS profile
locator, which the pinned reference requires): 55 give identical results and
one refusal differs only in its message. The causal bounds refuse none of that
lawful history.

**Controlled mutations.** Each mutation was applied to a scratch copy (the
clone was never modified), the targeted suite run, and the copy discarded.
The SDK suite ran against the copy's `src` (checked by printing the imported
module path). All 45 turned the suite red:

| Mutation | Killed by |
|---|---|
| H-M1 Hive retirement by exact RAPPID, not SPKI tail | `test_renamed_alias_cannot_become_a_fresh_owner_or_revive_a_retired_key` |
| H-M2 old anchor may walk through an owner compromise | `test_owner_compromise_recovers_only_through_a_new_anchor` |
| H-M3 owner checks use the current owner, not the owner in tenure | 12 vectors, including the declaration, back-dating, receipt, egg, and compromise vectors |
| H-M4 default authority skips `re-anchor` | `test_default_authority_still_fails_closed_on_reanchor` |
| H-M5 succession mode without a resolver | `test_succession_mode_is_explicit_closed_and_needs_trusted_issuance` |
| H-M6 anchor need not descend to the current owner | `test_anchor_must_be_in_the_owner_lineage_and_bind_its_key` |
| H-M7 current owner key need not be live | `test_current_owner_key_must_be_live` |
| H-M8 retained owner lineage may be rewritten | `test_retained_registry_state_refuses_rewritten_succession_history`, `..._rollback_of_succession_and_revocation` |
| H-M9 `upgrade`/`tag-migrate` owner transitions accepted | `test_unverifiable_owner_succession_cases_fail_closed` |
| H-M10 anchor SPKI need not be the registered anchor key | `test_anchor_must_be_in_the_owner_lineage_and_bind_its_key` |
| H-M11 convergence may list a candidate summary later than itself | `test_backdated_owner_acts_cannot_reach_state_after_the_boundary` |
| H-M11b convergence bound ignores authenticated candidate bytes | same test (false-summary assertion) |
| H-M11c convergence may share the instant of its base head | `test_convergence_is_strictly_later_than_the_head_it_extends` |
| H-M12 receipt may predate its convergence | `test_current_receipt_cannot_predate_its_convergence_or_registry` |
| H-M13 reconciliation may predate the Mother head it resolves | `test_backdated_reconciliation_cannot_resolve_a_later_mother_head` |
| H-M14 current receipt may predate its registry's latest lifecycle record | `test_current_receipt_cannot_predate_its_convergence_or_registry` |
| H-M15 a retained re-anchor or tombstone may be dropped | `test_retained_registry_state_refuses_rollback_of_succession_and_revocation` |
| H-M16 a predecessor anchor needs no retained state | `test_retained_registry_state_is_required_closed_and_checkpointed` |
| H-M17 a bare floor accepted under succession | same test, and the rollback test |
| H-M18 a compromise may reuse an earlier-appended tombstone | `test_compromise_and_its_tombstone_share_one_observed_append` |
| H-M19 a new compromise may arrive across skipped sequences | same test |
| H-M20 `rapp_registry` imported eagerly on the default path | `test_default_path_runs_without_the_registry_reference` |
| H-M21 succession index ignores the Hive profile spec hash | `test_succession_index_keeps_the_profile_pin_and_live_kinds` |
| H-M22 succession index keeps deprecated kinds | same test |
| H-M23 signed egg checked against the current owner | `test_signed_invite_egg_is_checked_against_the_owner_at_its_creation` |
| H-M24 checkpoint omits the retained registry state | four vectors that restore from a persisted checkpoint |
| H-M25 retained registry state not shape-checked | `test_retained_registry_state_is_required_closed_and_checkpointed` |
| S-M1 SDK loads `rapp_registry.py` without its pinned hash | `test_tampered_registry_reference_or_pin_is_refused_before_use` |
| S-M2 SDK retirement by exact RAPPID | `test_renamed_alias_cannot_revive_a_retired_key` |
| S-M3 SDK old anchor may walk through a compromise | `test_owner_compromise_needs_a_new_anchor_and_trusted_issuance`, `test_lineage_continues_under_a_new_anchor_after_owner_compromise` |
| S-M4 SDK may drop a retained lifecycle record | `test_lineage_refuses_gaps_dropped_revocations_and_rewritten_owner_history`, `test_retained_state_refuses_rollback_by_a_retired_anchor_key_or_a_moved_boundary` |
| S-M5 SDK may rewrite retained owner succession | same two tests |
| S-M6 SDK lineage need not be contiguous | `test_lineage_refuses_gaps_dropped_revocations_and_rewritten_owner_history` |
| S-M7 SDK without a resolver | `test_owner_compromise_needs_a_new_anchor_and_trusted_issuance` |
| S-M8 SDK owner key need not be live | `test_current_owner_key_must_be_live` |
| S-M9 SDK same-sequence fork accepted | `test_registry_high_water_and_same_sequence_fork` |
| S-M10 SDK anchor need not descend | `test_anchor_must_descend_and_bind_its_key` |
| S-M11 SDK owner transitions of any case | `test_unverifiable_owner_succession_cases_are_refused` |
| S-M12 SDK predecessor anchor needs no retained state | `test_planned_rotation_extends_the_original_out_of_band_anchor` |
| S-M13 SDK compromise may reuse an earlier-appended tombstone | `test_compromise_re_anchor_and_its_tombstone_share_one_append` |
| S-M14 SDK new compromise may arrive across skipped sequences | same test |
| S-M15 SDK retained record not shape-checked | `test_malformed_retained_state_is_refused` |
| S-M16 SDK registry rollback accepted | `test_registry_high_water_and_same_sequence_fork` |
| S-M17 SDK anchor SPKI need not be the registered anchor key | `test_anchor_must_descend_and_bind_its_key` |
| P-M1 the Hive reference's `rapp_registry.py` altered | `tools/check.py` ("pinned rapp_registry.py copy differs") |

Unchanged suites: H1–H20 (including the 64 authenticated vectors), the
Federation conformance, the legacy skill suites, and every existing SDK test.

## Reference implementation and gating

| File | Change |
|---|---|
| `vendor/rapp-1/rapp_registry.py` | exact `kody-w/rapp-1@591e014` bytes (also fixes drift) |
| `RAPP1_REGISTRY_PIN.json`, `src/rapp_work/data/RAPP1_REGISTRY_PIN.json` | new additive pin |
| `protocols/rapp-hive/1/reference/rapp_registry.py` | byte copy for standalone execution |
| `protocols/rapp-hive/1/reference/hive_acceptance.py` | opt-in succession (lazy import); `owner_at`; tenure-scoped owner checks; retained registry state; causal bounds; same-append |
| `protocols/rapp-hive/1/reference/succession_conformance.py` | new vectors |
| `protocols/rapp-hive/1/reference/hive_conformance.py` | H21, H22 |
| `protocols/rapp-hive/1/reference/README.md` | opt-in documentation |
| `.github/skills/rapp-private-hive/vendor/hive/reference/{hive_acceptance,rapp_registry}.py`, `rapp/agent.lock.json` | byte-exact re-sync and lock |
| `src/rapp_work/registry.py` | read-only SDK verifier with `retained` (explicit submodule) |
| `tests/test_registry_succession.py` | SDK vectors |
| `tools/check.py`, `tools/verify_package.py`, `MANIFEST.in` | pin, copy, and wheel checks |
| `protocols/rapp-work-sdk/1/SPEC.md`, `protocols/index.json`, `src/rapp_work/data/profiles.json` | SDK SPEC insertions and pins |
| `README.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/RELEASE.md`, `protocols/README.md`, `CHANGELOG.md`, `RELEASE-INVENTORY.json` | documentation and inventory |

Gating: the Hive behavior requires `succession="rapp1-13.2"` plus a callable
resolver; the default is the unchanged direct-owner path, which does not
import `rapp_registry.py`. The SDK behavior requires an explicit
`import rapp_work.registry`; `import rapp_work` does not load it and no JSON
operation reaches it. Neither path signs or writes.

## Related proposals

Sibling draft branches in `kody-w/rapp-work` touch some of the same files.
Nothing here edits them. A trial `git merge-tree` of this branch with each
sibling (against `main` at `29ead23`) reports:

| Branch (proposal) | Conflicting files | How to resolve |
|---|---|---|
| `experimental/gap-g1-roster-declaration` (0001) | `protocols/rapp-hive/1/reference/hive_acceptance.py`, its vendored skill copy and `rapp/agent.lock.json`, `hive_conformance.py`, `CHANGELOG.md`, `RELEASE-INVENTORY.json` | code overlap in `HiveAcceptance._authorized` and the constructor, and both branches add a check named H21 (see below) |
| `experimental/gap-g2-move-action` (0002) | `protocols/index.json`, `src/rapp_work/data/profiles.json`, `protocols/README.md`, `CHANGELOG.md`, `RELEASE-INVENTORY.json` | recompute the `rapp-work-sdk/1` SPEC hash after both SPEC insertions; union the conformance test lists; keep both changelog entries; regenerate the inventory |
| `experimental/gap-g3-agent-discovery` (0003) | `protocols/index.json`, `src/rapp_work/data/profiles.json`, `docs/API.md`, `CHANGELOG.md`, `RELEASE-INVENTORY.json` | as for G2; keep both `docs/API.md` sections |
| `experimental/gap-g7-instruction-inventory` (0007) | `protocols/index.json`, `src/rapp_work/data/profiles.json`, `protocols/README.md`, `CHANGELOG.md`, `RELEASE-INVENTORY.json` | as for G2 |
| `experimental/gap-g4-migration-successors` (0004), `experimental/gap-g11-workspace-index` (0011), `experimental/gap-g17-brainstem-sdk-agent` (0017) | `CHANGELOG.md`, `RELEASE-INVENTORY.json` | keep both entries; regenerate the inventory |

`protocols/rapp-work-sdk/1/SPEC.md` itself merges cleanly with G2, G3, and
G7: this branch's section 12 change is now an insertion before the paragraph
that G7 edits.

**G1 interaction.** G1 lets the owner sign later roster declarations and keeps
the owner RAPPID immutable across them ("an owner change is succession (gap
G6)"). With both merged: (1) G1's later-declaration owner check must use
`registry.owner_at(frame["utc"])` (this branch's `tenured`) rather than
`registry.owner`, or a declaration dated inside a predecessor's tenure is
misjudged; (2) until G1's owner-immutability invariant is relaxed to accept a
later declaration whose owner is the owner in effect at its `utc`, a successor
holds Mother authority but cannot re-declare the roster (design decision 10);
and (3) G1 already makes later declarations strictly later than the Mother
head, which matches this branch's rule for convergences under succession.
Recommended order: merge G6 first (the registry authority layer), then rebase
G1 onto it: adopt `tenured` in its declaration check, renumber one of the two
H21 checks, and regenerate the vendored copy, the lock, and the inventory;
relax the owner invariant for succession in that rebase or a follow-up. The
other siblings can merge in any order relative to G6, recomputing the SDK SPEC
pins and the inventory after each.

## Open questions for the owner

1. **Anchoring at an earlier owner.** RAPP/1 section 13.1 says the registry
   signature verifies against the anchor's SPKI, and the pinned loader refuses
   a registry naming another owner (`EXTENDING.md` rule 4). This proposal
   lets an old anchor walk forward through signed `rotation` records, and only
   with retained state (design decision 4), because section 6.3 reserves
   out-of-band re-anchoring for root-key compromise. Accept this reading;
   or require the literal reading (every consumer re-anchors after any owner
   rotation, which removes the walk-forward path and the need for retained
   state to accept a predecessor anchor); or raise it upstream?
2. Should `rapp-hive/1` make succession the default after the section 14.2
   text is accepted? This proposal keeps it opt-in.
3. **Retroactive revocation (upstream).** The pinned reference refuses a
   rotation whose outgoing key has a tombstone with `revoked_utc` at or before
   the rotation, even if that tombstone is issued later, so a key that leaks
   after a routine rotation cannot be revoked for its own tenure without
   invalidating the whole registry. Should a later-issued tombstone be allowed
   to cut into a predecessor's tenure without voiding its continuity proof?
4. **Receipt bound on the registry.** A current receipt must not predate the
   latest `re-anchor` `utc` or trusted tombstone issuance in the registry it
   names. A future-dated lifecycle record therefore blocks current receipts
   until its time. Keep this fail-closed bound?
5. **Strict convergence order under succession.** A convergence must be
   strictly later than its base head (RAPP/1 section 7.5 step 4 allows equal
   `utc`; G1 uses the same strict rule for later declarations). Keep it?
6. Should a re-anchored member or owner inherit declared membership? This
   proposal says no; with G1, a successor owner re-declares the roster (see
   Related proposals).
7. Upstream (RAPP/1 section 13.3): `estate_owner` is "exactly one
   non-deprecated" but its member set has no `deprecated`, and the pinned
   reference accepts exactly one `estate_owner` entry. A successor registry
   therefore replaces that entry, against "every entry is append-only (never
   removed/renamed)". Which reading is intended?
8. Upstream: key-tail retirement is the reference's private
   `_signer_acceptable(..., match_key_aliases=True)`; section 10 speaks of a
   "tombstoned key". Should the public `signer_acceptable` match by tail?
9. Upstream: a compromise tombstone's same-append provenance and issuance time
   remain unspecified (`rapp-backlog.md`). Should RAPP/1 define an
   issuance/append record, which would also let a first verification check the
   same-append rule?
10. Upstream: the reference requires the estate owner's own `compromise` record
    to be signed by the outgoing, compromised key (section 6.3). Is that
    intended for root-key compromise?
11. Bump the legacy skill lock `version` (`3.2.0`) because vendored bytes
    changed?
12. The `rapp-federation/1` reference also fails closed on succession
    (`RegistryAuthority` in `reference/rapp_federation.py`). Follow-up gap?
13. Should the `verify` JSON operation later accept registry lineages? That
    needs a closed input extension and a data form of the issuance resolver.

## Owner actions needed

1. Accept or refuse this proposal and the `rapp-work-sdk/1` insertions on the
   branch.
2. Accept the `rapp-hive/1` section 8.1, 9.1, and 14.2 text, then update
   `protocols/rapp-hive/1/SPEC.md` and its pins (`protocols/index.json`,
   `src/rapp_work/data/profiles.json`, the legacy skill's `vendor/hive/SPEC.md`
   copy and lock `protocol.spec_sha256`) and re-sign `registry.json`.
   Activation owner-blocked: the signed registry pins the SPEC hash; the owner
   must accept the text and re-sign.
3. Decide the `1.1.0` release, the merge order with G1 (Related proposals),
   and whether to raise open questions 1, 3, and 7–10 in `kody-w/rapp-1`
   (draft below).

**Estate-lead actions (relayed; nothing here edits estate material).**

1. A downstream estate signing kit pins `protocols/rapp-hive/1/reference/hive_acceptance.py`
   (`88184a7e…`) and the `rapp-work-sdk/1` SPEC (`cf64a90f…`) at `29ead23`,
   fetches only `hive_acceptance.py`, `rapp_hive.py`, `rapp.py`,
   `rapp_profile.py`, and the `rapp-hive/1` `SPEC.md`, and imports
   `hive_acceptance`. It keeps working at `29ead23`, and with this branch's
   lazy import that five-file set also runs this branch's default gate. If the
   kit adopts this branch it re-pins `hive_acceptance.py` (`4ef87e44…`) and the
   SDK SPEC (`19802755…`); it needs `rapp_registry.py` (`eec22844…`) only to
   enable succession.
2. The G16 registry entry pins the `rapp-hive/1` spec hash (`79aeef7b…`).
   Owner action 2 changes that file, so the G16 entry and its signature need
   the estate lead's re-pin and re-sign when the text lands.

### Ready-to-file upstream note (not filed)

> **Title:** Registry lifecycle: predecessor anchors, retroactive revocation,
> estate_owner append-only reading, tail-matched retirement, and compromise
> provenance
>
> A PII-free Hive verifier adopting `rapp_registry.py@591e014` for owner
> succession found six places where RAPP/1 sections 6.3, 10, and 13 are
> ambiguous. It fails closed meanwhile. (1) Section 13.1 verifies the registry
> against the anchor's SPKI, and `load_document` refuses a registry naming
> another owner, yet section 6.3 reserves out-of-band re-anchoring for
> root-key compromise. May a consumer walk forward from its original anchor
> through signed rotations if it retains the lineage it accepted? (2) A
> tombstone dated before a rotation voids that rotation's continuity proof
> even when issued later, so a key that leaks after its rotation cannot be
> revoked for its own tenure. Should a later-issued tombstone cut into a
> predecessor's tenure without voiding the proof? (3) Section 13.3 says
> `estate_owner` is "exactly one non-deprecated" but defines no `deprecated`
> member; the reference accepts one entry, so succession replaces it, against
> append-only. (4) Section 10 refuses a "tombstoned key"; the reference matches
> by SPKI tail only in the private `_signer_acceptable(...,
> match_key_aliases=True)`. Should public `signer_acceptable` match by tail?
> (5) Compromise tombstones need same-append provenance and an issuance time
> that a snapshot cannot prove. (6) The estate owner's own compromise record is
> signed by the compromised key. Is that intended when the anchor must be
> redistributed anyway?

## References

- RAPP/1 `SPEC.md` (pinned, `vendor/rapp-1/SPEC.md`): sections 6.2, 6.3, 7.4,
  7.5, 10, 12.1, 13.1, 13.2, 13.3, 14.
- RAPP/1 `CONSTITUTION.md` Articles 2, 4, 5, 6, 8, 10, 18.
- `kody-w/rapp-1@591e014`: `rapp_registry.py`, `test_registry_lifecycle.py`,
  `EXTENDING.md` ("The rules that keep the wire shared", "The reference will
  check your estate", "What is not yet closed"),
  `examples/07_your_own_estate.py`.
- `rapp-hive/1` `SPEC.md` sections 1, 8.1, 8.2, 8.3, 9.1, 14.2;
  `reference/hive_acceptance.py`; `reference/README.md`.
- `rapp-work-sdk/1` `SPEC.md` sections 5, 8, 12; `docs/API.md`;
  `docs/ARCHITECTURE.md`; `CONTRIBUTING.md`; `docs/RELEASE.md`.
- Gap G6: `kody-w/rapp-work` branch `experimental/rapp-work-constitution`,
  `organism/gaps/G06.md`; related G1 (`organism/gaps/G01.md`) and G16
  (`organism/gaps/G16.md`).
- Proposal 0001 (`experimental/gap-g1-roster-declaration`).
