# Proposal 0001: owner-signed later declarations for `rapp-hive/1`

## Proposal-only acceptance note

Merging this proposal accepts the design only. It does **not** activate later
declarations, change any signed `rapp-hive/1` SPEC byte, re-sign the registry,
or ship the reference implementation. The reference implementation stays on
`experimental/gap-g1-roster-declaration` until the owner accepts this proposal;
its implementation pull request is then opened as a draft and linked back here.
The owner should apply the SPEC text and re-sign only after that reference
branch has merged and passed its own review.


| Field | Value |
| --- | --- |
| Status | **Draft, not accepted.** Nothing here is normative until the `rapp-hive/1` owner accepts it and re-signs the registry. |
| Gap | **G1**: a `rapp-hive/1` roster can never change. Once declared, nobody can be added or removed. |
| Home spec | [`protocols/rapp-hive/1/SPEC.md`](../../protocols/rapp-hive/1/SPEC.md) §3 (declaration), with consequential text in §3.1, §7, §8.1, §8.2, §9.1, §10 item 5, §12 and §14 |
| Pinned bytes today | `SPEC.md` SHA-256 `79aeef7bc5000f4a7b09483844b035c66adf817475540e583138f2e6b432c822`; `schema.json` SHA-256 `9b383535d6a2ad379e8c70b1a1cb3ab6ed3f9ca71114c37695e24fd8560415e0` (both unchanged by this proposal) |
| Base | `kody-w/rapp-work` `main` at `29ead23b21645f8d7682ee00414930ffa9ce0ca6` |
| Fix | The owner signs a later declaration, and the Mother stream carries it as the single next frame |
| Blocks | The organism's **Private Hive** part |
| Intended release | `rapp-work` 1.1.0. The reference gains an additive, opt-in mode, the SDK API is unchanged, and the package version is not bumped on this branch. |
| Activation | **Owner-blocked.** The signed `registry.json` pins the SPEC hash, so the owner must accept the text and re-sign. |

## 1. Summary

A `rapp-hive/1` Private Hive has exactly one declaration today: the
owner-signed frame at the Mother Hive's registered creation genesis. After
that, the members, rooms and channels are fixed forever. The only way to
change any of them is a new Hive with a new `hive_rappid`. An organization
binds its one Private Hive by that `hive_rappid`, so a new Hive breaks the
binding.

This proposal lets the **owner** sign a **later declaration**. That is an
ordinary `hive.declaration` frame on the Mother stream, carrying the
**unchanged closed `rapp-hive/1-declaration` schema**. It is accepted only as
the **single next Mother frame**, through the same compare-and-swap that
accepts a convergence. It can add or remove members, change roles and member
areas, change room membership, add rooms, and switch channels. It cannot change
the Hive identity, the world, the policy or the owner. An owner change is
succession, which is gap G6.

Its effect is **prospective from its Mother position**. Every unsettled
mutation is authorized against the roster in effect at the Mother head being
extended, never against the frame's self-asserted time. Accepted history is
never re-evaluated. No key set, field grammar, hash rule, kind, envelope or
schema changes, so no token moves (§6). A declaration changes the roster, never
the RAPP/1 registry: admitting an identity also needs its registry key and
stream genesis, and a removed member's key stays registered (§3 item 13).

The reference implementation is opt-in: `HiveAcceptance(...,
roster_declarations=True)`. The default gate still refuses every later
declaration, exactly as today. 96 new vectors cover both modes, and 20
controlled mutations each turn critical vectors red.

## 2. Context: what is true today

All references are to `protocols/rapp-hive/1/SPEC.md` at the pinned hash
above, and to the reference in `protocols/rapp-hive/1/reference/`.

- **§3 (Declaration).** "`rapp-hive/1-declaration` names one Hive, its hard
  `world_id`, one owner, its members, sealed rooms, channels, and policy." The
  schema `$defs/declaration` is closed: `schema`, `hive_rappid`, `world_id`,
  `created_utc`, `authority_channel_id`, `members`, `rooms`, `channels` and
  `policy`. The policy members are constants. The §3 text defines no way to
  change a declaration.
- **§3.1 (Sealed rooms).** Key release requires "a current member of the
  declared room" and membership in the slice audience. "Current" is undefined
  when there is only one declaration.
- **§7.** "The Mother Hive is the one registered authority stream. Its signed
  `hive.convergence` frame is the linearization point that accepts a new
  canonical successor."
- **§8.1 item 2.** Authenticated acceptance requires "the owner-signed
  declaration at the Mother's registered creation genesis". Item 3 requires
  "the locally accepted Mother frame head, last convergence particle hash (or
  null immediately after the declaration), and derived catalog commitment".
  Item 5 says a signed `hive.convergence` must be "the single next Mother
  frame", with `base_head_frame_hash`, `base_convergence_payload_hash` and
  `base_catalog_hash` equal to the accepted state. It adds: "A competing
  successor prepared against the same old base is refused after the first
  commits."
- **§8.2.** The producer's "current role is owner/member (not viewer) and
  [its] identity is in the selected room". "Channel observations must name
  declared channels." Declarations "are not disguised catalog candidates".
- **§9/§9.1.** A current receipt binds "the latest accepted convergence's
  particle hash" and "the actual current Mother **frame** hash, not the
  convergence particle". Today these always name the same frame.
- **§10 item 5.** A migration "switches an authority locator only through an
  owner-signed declaration". The SPEC already anticipates a later declaration
  but defines no rule for one.
- **§12.** "Revocation stops future key release but cannot erase plaintext
  already decrypted by an authorized member."
- **§14.2 and the reference.** `HiveAcceptance._authorized` refuses any
  declaration whose payload differs from the genesis ("declaration:
  unaccepted policy replacement"). `accept_convergence` accepts only
  `hive.convergence` Mother successors. `restore()` replays every Mother frame
  as a convergence. So a history containing a later declaration fails closed
  today, and the restore failure latches.
- **Registry pin.** The frozen signed `registry.json` pins
  `protocols/rapp-hive/1/SPEC.md` by SHA-256. `RegistryAuthority` refuses a
  registry whose `rapp-hive/1` pin differs from the local SPEC bytes, and
  `tools/check.py` refuses a checked-in SPEC that differs from the signed pin.
  Editing the SPEC therefore needs the owner's re-signature. This proposal
  does not edit it.
- **Registry keys and streams (RAPP/1 §10, §13.3).** A verifier discovers a
  signer's key only from an active registry `spki` entry, and "every stream
  registers its creation genesis". `HiveAcceptance` binds one
  `RegistryAuthority` for its lifetime, so a registry refresh is a fresh gate
  plus `restore()`. A bare `deprecated:true` retires a key for every artifact,
  history included: `RegistryAuthority` skips deprecated entries, and the
  pinned RAPP/1 registry reference (`vendor/rapp-1/rapp_registry.py`,
  `Registry.signer_acceptable`) refuses "spki entry deprecated" at any time.
  Only a RAPP/1 §10 re-anchor keeps earlier frames verifying ("earlier frames
  verify as before"), and the direct-owner reference refuses re-anchor records.

## 3. Design and its justification

The direction given for G1 was validated against the SPEC and the reference.
It holds, with six refinements (marked **R1** to **R6**).

1. **Same schema, same kind, same stream.** A later declaration is a complete
   `rapp-hive/1-declaration` payload in a signed `hive.declaration` frame on
   the Mother stream (`stream_id` is `hive_rappid`). The kind is already
   registered with this exact schema (§1), so nothing needs registering. A
   complete payload, rather than a delta, keeps the declaration
   self-describing and reuses the closed validator unchanged.
2. **Single next Mother frame.** A later declaration has `seq` equal to the
   head's `seq` + 1 and `prev` equal to the head's `payload_hash`, and it is
   accepted by the same compare-and-swap as a convergence. The Mother stream
   therefore stays one linear history of convergences and declarations. The
   first successor to commit wins; any competitor (declaration or convergence)
   prepared against the same head is refused.
3. **Immutable across declarations.** `hive_rappid` (hence the Mother stream),
   `world_id`, `schema` and the closed `policy` never change. The owner's
   RAPPID never changes, exactly one member has role `owner`, and the owner
   stays a member. An owner change is succession (G6) and is refused here with
   a message that says so. The signer is the owner in effect at the frame's
   time; in the direct-owner profile that is the anchored estate owner, with
   RAPP/1 §13 tombstones evaluated at the frame's `utc`.
4. **Time.** `created_utc` equals the envelope `utc` (the existing rule) and
   is **strictly** later than the Mother head. RAPP/1 §7.5 only requires `utc`
   ≥ head. Strictness gives every roster version a unique effective instant,
   so no roster shares an instant with the convergence it follows. It also
   makes a re-carried old declaration impossible to replay.
5. **Acceptance-position authorization (R1).** The roster in effect at a Mother
   position is the latest accepted declaration at or before it. Every
   **unsettled** object or slice (the candidate and every unsettled object or
   slice in its authenticated ancestry) is authorized against the roster in
   effect at the Mother head being extended. A removed member can stamp any
   `utc` on their own frames, so self-asserted time is never used. A
   **settled** frame (accepted, duplicate or superseded) keeps the verdict of
   the position that settled it. It is a valid causal ancestor after its
   producer leaves, and re-offering it is a `duplicate`.
   - In proposal mode the reference therefore splits verification.
     *Authentication* happens in the chain walk: envelope, signature,
     signer/producer binding, time binding, Hive binding and the
     roster-independent payload shape. *Authorization* happens once, in
     `_candidate`, at the acceptance position.
   - The split keeps decisions independent of the verifier's cache. A live
     verifier that previewed a frame before a roster change and a verifier
     restored from history reach the same decision. The same holds for
     projection receipts (item 11). The whole-ancestry scope keeps the
     existing guarantee that only authorized frames can create fork evidence
     (vector `test_revoked_ancestry_cannot_block_or_latch_fork_evidence`,
     mutation M12).
6. **Audiences follow the roster (R2).** §5 already requires an audience to be
   "a sorted, non-empty subset of both current Hive members and that room's
   members". At the acceptance position, an unsettled frame whose audience
   still names a removed identity is quarantined; the producer re-issues it
   with a current audience. This is the literal reading. It also means no
   frame accepted while an identity is out can name that identity, which
   matters because re-admission would otherwise make such slices releasable
   to it. The consequence for owners is operational: converge wanted in-flight
   work *before* signing a removal.
7. **Pending work cannot deadlock (R3).** Today a pending conflict candidate
   that fails verification aborts every later convergence ("unresolved
   candidate bytes or metadata changed"). If a removal simply invalidated
   pending frames, the Hive would stop forever. An unsettled frame that an
   earlier accepted roster authorized, but the roster in effect does not, is
   instead quarantined with the descriptive reason code `roster-revoked`. That
   covers the frame itself and any frame whose unsettled ancestry contains
   one. Such a frame leaves the backlog. The next proposal must still offer
   it, so the owner's convergence records the quarantine explicitly, and
   omitting it is still refused. Excluding it before conflict sets are built
   is the existing §8.2 rule for invalid candidates. A remaining concurrent
   frame may therefore become an independent update without a reconciliation:
   an explicit, owner-signed consequence of removal. An *accepted* frame of a
   removed member stays active and still conflicts; an owner reconciliation
   resolves that.
8. **Rooms persist (R4).** A later declaration may add rooms and change room
   membership. Every room declared in the roster in effect must remain, with
   the same `area` and `access`. Deleting a room, moving its area or changing
   its protection class would orphan or reinterpret accepted objects and
   slices. The owner retires a room by shrinking its member list (for example
   to the owner). This is the strict choice: it can be relaxed later, while a
   loose rule could never be tightened without invalidating accepted history.
   Member areas, roles (member ⇄ viewer) and channels may change freely within
   the closed §3 grammar. A role change affects only mutation authority
   (§8.2). Key release depends on room membership and the slice audience
   (§3.1), not on the role, so a member demoted to viewer who stays in a room
   and in a slice's audience stays eligible for that slice.
9. **The convergence lineage stays continuous (R5).** After a later
   declaration, `base_head_frame_hash` is the declaration frame, and
   `base_convergence_payload_hash` is the **last accepted convergence**. It is
   null only while no convergence has ever been accepted. That reads §8.1
   item 3 ("last convergence particle hash") literally, keeps a continuous
   convergence lineage, and matches §9.1 item 2 ("the latest accepted
   convergence's particle hash"). On every existing history (where the Mother
   head is always the genesis or a convergence) this equals today's
   expression exactly. A current receipt at a declaration head binds that last
   convergence and the declaration frame. Channels can therefore be
   re-projected right after a roster or channel change, which §10 needs for a
   locator switch. No current receipt exists before the first convergence,
   as today.
10. **Declarations never enter the catalog.** A later declaration is not a
    candidate, adds no catalog entry and leaves the catalog commitment
    unchanged. It is retained Mother history, so it appears in the artifact
    manifest as a `rapp/1:wave` address.
11. **Channels (§10 item 5).** A declaration may add, remove or re-role
    channels and move `authority_channel_id`. Candidate channel observations
    and projection receipts must name a channel declared in the roster in
    effect. A removed channel's receipts stay history and can never again be
    current. The reference checks a receipt's channel against the roster in
    effect each time the receipt is offered, not only in the chain walk,
    because the walk may have been cached under an earlier roster. A verifier
    that saw the receipt before the retiring declaration and one restored
    after it therefore reach the same refusal. Locators remain transport
    metadata: no Hive identity or artifact address changes.
12. **No-op declarations** (only the time changes) are permitted. They advance
    the Mother head and nothing else (open question Q3).
13. **Registry prerequisites (R6).** A later declaration changes the roster,
    never the RAPP/1 §13 registry, and a registry change never changes the
    roster. A member still signs with a key found only in an active registry
    `spki` entry, on streams whose creation genesis is registered (§2).
    - **Admission.** Registry first, always. The owner first publishes a
      higher owner-signed registry that registers the identity's key and the
      genesis of every stream it will write (for an added channel, also its
      receipt stream), adopts it in the verifier with which it signs
      convergences (a fresh gate and `restore()`), and only then signs the
      declaration. The order is required, not advisory. A convergence records
      each candidate's decision as the deciding verifier's registry makes it,
      and `restore()` re-derives every recorded decision under the restoring
      verifier's registry. A convergence that records an identity's frame as
      `invalid-candidate` only because the registry lacked its key or stream
      genesis therefore breaks every verifier that later adopts a registry
      registering them: its `restore()` finds that the decisions differ,
      fails closed, and latches (vector
      `test_a_recorded_registry_quarantine_makes_a_later_refresh_fail_closed`).
      So the owner never records such a quarantine: until its own registry
      registers the key and genesis, it leaves the identity's frames out of
      its convergences (only unresolved conflict candidates must reappear,
      `rapp-hive/1` §8.3). That hazard is a property of `rapp-hive/1`
      acceptance on `main` too (a registry change that makes a recorded
      quarantine verify, or a recorded acceptance fail, breaks `restore()`
      under that registry); a later declaration only makes it easier to
      reach, because admission is when a new key first appears.
    - **Removal** is a roster act, not a key act. The removed member's `spki`
      entry stays active. Deprecating it would retire the key for history too
      (§2): a verifier with that registry could no longer re-verify the Mother
      history, so its `restore()` fails closed and latches. Key compromise
      remains a RAPP/1 §10 tombstone.
    - The reference does **not** require declared members to hold registry
      keys. That rule would make a declaration's verdict depend on the
      verifier's registry, which changes over time (open question Q11).

Out of scope: owner succession and re-anchor (G6), folder-Hive membership
(G8), key-service implementation (§14.2 already disclaims it) and SDK
operations.

## 4. Proposed change: normative text (PROPOSED, not accepted)

The quoted text below is the exact proposed wording. "Replace" quotes the
current text first. Nothing here is in `SPEC.md` on this branch.

### 4.1 §3: insert a new §3.2 after §3.1

> **PROPOSED — insert after §3.1:**
>
> ### 3.2 Later declarations
>
> The declaration at the Mother's registered creation genesis is the Hive's
> first declaration. The owner changes members, roles, member areas, room
> membership, rooms, or channels only by signing a **later declaration**: a
> `hive.declaration` frame on the Mother Hive stream whose payload is a
> complete `rapp-hive/1-declaration`. A later declaration is accepted only
> when all of the following hold:
>
> 1. It is the **single next** Mother frame: its `seq` is the accepted Mother
>    head's `seq` + 1 and its `prev` is that head's `payload_hash`. A competing
>    successor prepared against the same head, whether a declaration or a
>    convergence, is refused after the first commits, even if it is validly
>    owner-signed.
> 2. Its JWS `kid` is the estate owner in effect at the frame's `utc` (RAPP/1
>    §13.2) and equals the RAPPID of its single `owner` member. In the
>    direct-owner profile this is the anchored estate owner.
> 3. Its `schema`, `hive_rappid`, `world_id`, and `policy` equal the first
>    declaration's, and exactly one member has role `owner` with the first
>    declaration's owner RAPPID. Changing the owner is owner succession, not a
>    roster declaration.
> 4. `created_utc` equals the envelope `utc` and is strictly later than the
>    accepted Mother head's `utc`.
> 5. Every room of the roster in effect remains declared with the same `area`
>    and `access`. Rooms may be added and room member lists may change; a room
>    is retired by reducing its members, never by removing it.
> 6. It satisfies every other §3 and §3.1 declaration rule.
>
> The **roster in effect** at a Mother position is the payload of the latest
> accepted declaration at or before that position. A later declaration is not
> a catalog candidate and does not change the catalog commitment. It takes
> effect prospectively from its Mother position: accepted Mother frames,
> catalog entries, decisions, and receipts are never re-evaluated, removed, or
> reinterpreted under a later roster. Roster authority is judged at the
> acceptance position (§8.2), never by a frame's self-asserted time.
>
> Removing an identity from the Hive ends its future authority and its future
> key release in every room. Removing it from a room ends its future authority
> in that room and its future key release for that room's slices (§3.1, §12).
> Demoting a `member` to `viewer` ends only its future mutation authority: a
> viewer that remains a member of a room and of a slice's audience remains
> eligible for that slice's key release. The owner is never removed or
> demoted (item 3). A roster change does not remove accepted frames or their
> current effects, recall bytes the identity already holds, or revoke its key.
>
> A later declaration does not change the RAPP/1 §13 registry. A member is
> still a keyed RAPPID: its frames verify only through an active registry
> `spki` entry, on streams whose creation genesis is registered (RAPP/1 §10,
> §13.3). Before admitting an identity, the owner **MUST** publish, and adopt
> in the verifier with which it signs convergences, a registry that registers
> its key and the creation genesis of every stream it will write. A
> convergence **MUST NOT** record a frame as quarantined when the only reason
> is that the deciding verifier's registry lacks the frame's signing key or
> its stream's creation genesis; the owner leaves such a frame out of the
> convergence until that registry registers them. A registry change that
> changes the verification result of any frame that an accepted convergence
> records can make every verifier holding it refuse to restore the Hive's
> history: `restore()` fails closed and latches. That includes frames recorded
> as `accepted`, `duplicate`, `conflict`, `superseded`, `quarantined`,
> `stream-fork`, and fork ancestors whose signed bytes, ancestry, and
> authorization verified when the convergence was accepted. The owner **MUST
> NOT** deprecate the `spki` entry of any key that signed such a recorded or
> retained frame, other than through a RAPP/1 §10 re-anchor, including when
> its identity is removed: a verifier that cannot resolve that key cannot
> re-verify the Mother history. Key compromise remains a RAPP/1 §10
> tombstone; its cutoff must follow the G6 rule before this history is
> extended.

### 4.2 §3.1: key release uses the roster in effect

> **Current:** "The key service releases a slice DEK only to a recipient whose
> keyed RAPPID is both: 1. a current member of the declared room; and 2.
> present in the slice's explicit audience."
>
> **PROPOSED — replace with:** "The key service releases a slice DEK only to a
> recipient whose keyed RAPPID is both: 1. a member of the declared room in the
> roster in effect (§3.2) at the key service's accepted Mother head; and 2.
> present in the slice's explicit audience. The key service **MUST** track the
> accepted Mother head with the §8.1 rollback protections and **SHOULD** refresh
> it before each release; a stale head can release a key to an identity that a
> later declaration removed."

### 4.3 §7: two kinds of Mother successor

> **Current:** "The **Mother Hive** is the one registered authority stream. Its
> signed `hive.convergence` frame is the linearization point that accepts a new
> canonical successor."
>
> **PROPOSED — replace with:** "The **Mother Hive** is the one registered
> authority stream. Its signed successors are `hive.convergence` frames, which
> accept a new canonical catalog successor, and later `hive.declaration` frames
> (§3.2), which accept a new roster. Each is a linearization point."

### 4.4 §8.1: items 2, 3, 5, and the compare-and-swap

> **Current item 2:** "The owner-signed declaration at the Mother's registered
> creation genesis. In the direct-owner profile, the declaration owner is the
> anchored estate owner. Mother Hive `stream_id` is exactly `hive_rappid`."
>
> **PROPOSED item 2:** "The owner-signed declaration at the Mother's registered
> creation genesis and every later declaration accepted on the Mother stream
> (§3.2). `owner-signed` means the signer is the estate owner in effect at
> the declaration's `utc` under the active RAPP/1 registry; in the
> direct-owner profile that owner is the anchored estate owner. A successor
> owner does not inherit declared membership unless a later declaration names
> that successor as owner under §3.2. Mother Hive `stream_id` is exactly
> `hive_rappid`."

> **Current item 3:** "The locally accepted Mother frame head, last
> convergence particle hash (or null immediately after the declaration), and
> derived catalog commitment. A bare caller-supplied catalog or accepted-frame
> list is not a checkpoint. Recovery replays signed Mother history and
> verifies all its dependencies."
>
> **PROPOSED item 3:** "The locally accepted Mother frame head (a convergence
> or a declaration), the last accepted convergence particle hash (or null
> while no convergence has been accepted), the derived catalog commitment,
> and the roster in effect. A bare caller-supplied catalog, accepted-frame
> list, or roster is not a checkpoint. Recovery replays signed Mother history,
> declarations and convergences in Mother order, and verifies all its
> dependencies."

> **Current item 5:** "A signed `hive.convergence` frame that is the **single
> next** Mother frame. Its `base_head_frame_hash`,
> `base_convergence_payload_hash`, and required `base_catalog_hash` must equal
> the locally accepted state. A competing successor prepared against the same
> old base is refused after the first commits, even if it is validly
> owner-signed."
>
> **PROPOSED item 5:** "A signed `hive.convergence` frame that is the **single
> next** Mother frame. Its `base_head_frame_hash` must equal the accepted
> Mother head frame, which may be a later declaration. Its
> `base_convergence_payload_hash` must equal the last accepted convergence
> particle hash of item 3, which a declaration does not change. Its required
> `base_catalog_hash` must equal the derived catalog. A competing successor
> prepared against the same old base, whether a convergence or a declaration,
> is refused after the first commits, even if it is validly owner-signed."

> **PROPOSED — append to the compare-and-swap paragraph:** "A later
> declaration commits the Mother head and the roster in effect through the
> same compare-and-swap; a refused declaration leaves the accepted state
> unchanged."

### 4.5 §8.2: authorization at the acceptance position

> **Current bullet:** "Bind payload Hive/world to the authenticated
> declaration and payload time to envelope time. Object/slice JWS `kid` must
> equal `producer_rappid`, whose current role is owner/member (not viewer) and
> whose identity is in the selected room. Object targets must be below the
> producer's member area or selected room area; the owner may also target
> another declared member area."
>
> **PROPOSED — replace with:** "Bind payload Hive/world to the authenticated
> declaration and payload time to envelope time. Object/slice JWS `kid` must
> equal `producer_rappid`. Judge every roster rule against the roster in effect
> at the Mother head being extended (§3.2), never against the frame's `utc`:
> the producer's role is owner/member (not viewer) and its identity is in the
> selected room; the room and every audience member are declared there; object
> targets are below the producer's member area or selected room area, and the
> owner may also target another declared member area. Apply these rules to the
> candidate and to every previously unsettled object or slice in its
> authenticated ancestry. A previously settled frame keeps the verdict of the
> Mother position that settled it."

> **Current (bullet 3, last sentence):** "Channel observations must name
> declared channels."
>
> **PROPOSED:** "Channel observations must name channels declared in the
> roster in effect at the Mother head being extended."

> **PROPOSED — insert after the paragraph that begins "An invalid candidate is
> `quarantined`":** "An unsettled candidate that an earlier accepted roster
> authorized but the roster in effect does not is quarantined with the
> descriptive reason code `roster-revoked`, as is a candidate whose unsettled
> authenticated ancestry contains such a frame. It is excluded with its
> dependents before conflict sets are built, creates no fork evidence, and
> leaves the unresolved backlog: the next proposal must still offer it, and it
> is quarantined rather than treated as changed bytes. A roster change never
> re-opens, removes, or supersedes an accepted frame; a concurrent frame still
> conflicts with an active accepted frame of a removed identity."

### 4.6 §9.1: currency after a declaration

> **Current:** "That stream is bound to one declared channel; accepted
> receipts are protected against replay/rollback/fork." and items "2. the
> latest accepted convergence's particle hash; 3. the actual current Mother
> **frame** hash, not the convergence particle;"
>
> **PROPOSED — replace with:** "That stream is bound to one channel declared in
> the roster in effect; a receipt for a channel that the roster in effect no
> longer declares is never current. Accepted receipts are protected against
> replay/rollback/fork." and "2. the latest accepted convergence's particle
> hash, which a later declaration does not change; 3. the actual current
> Mother **frame** hash, not the convergence particle; after a later
> declaration this is the declaration frame;"
>
> **PROPOSED — append to the paragraph on artifact coverage:** "A current
> receipt requires at least one accepted convergence. Accepted later
> declarations are retained Mother frames."

### 4.7 §10 item 5

> **Current:** "5. switches an authority locator only through an owner-signed
> declaration; and"
>
> **PROPOSED — replace items 4 and 5 with:** "4. records a projection receipt
> for a channel declared in the roster in effect; 5. switches an authority
> locator only through an owner-signed later declaration (§3.2) accepted as
> the single next Mother frame; and"

### 4.8 §12

> **Current:** "Revocation stops future key release but cannot erase plaintext
> already decrypted by an authorized member, as required by RAPP/1 section
> 9.2.1."
>
> **PROPOSED — replace with:** "Revocation stops future key release but cannot
> erase plaintext already decrypted by an authorized member, as required by
> RAPP/1 section 9.2.1. Removing an identity from the Hive or from a room with
> a later declaration (§3.2) is such a revocation: it ends that identity's
> future authority and future key release there, including for slices accepted
> earlier, and cannot recall ciphertext, plaintext, or keys it already holds.
> Demotion to `viewer` ends only mutation authority and does not revoke key
> release."

### 4.9 §14 and §14.2

> **PROPOSED — insert after item 8:** "9. accept a later declaration only as the
> single next owner-signed Mother frame under §3.2, and judge roster authority
> at the acceptance position;" (the following items are renumbered).
>
> **PROPOSED — append to the first §14.2 paragraph:** "`accept_declaration`
> accepts later declarations (§3.2) through the same serialized
> compare-and-swap; `restore()` replays declarations and convergences in Mother
> order."
>
> **PROPOSED — replace the last §14.2 paragraph's first sentence with:** "It runs
> the payload vectors, exact specification/schema index pins, real Ed25519
> positive/negative vectors, later-declaration vectors, and Draft
> 2020-12/Python scalar parity checks."

## 5. Why this blocks the Private Hive part

The organism's Private Hive part is `rapp-hive/1`: "one owner", "bound by
`hive_rappid`". An organization binds exactly one Private Hive by its
`hive_rappid` and records accepted checkpoints as high-water marks. A real
organization onboards and offboards people, AI agents and services. It also
has to cut off a member it no longer trusts, and it moves storage (§10).

Without G1, every one of those events needs a brand-new Hive identity. That
breaks the organization binding and its high-water history, strands accepted
history on the old identity, and gives no protocol-level way to stop future
key release to a departed member. A Private Hive that cannot change its
roster cannot be "healthy throughout" in an LTS. With this proposal, roster
changes are ordinary signed Mother history on the same `hive_rappid`. The SDK's
Hive vectors (`rapp_work.hive`) are kind-agnostic stream positions, so a
declaration is just the next Mother position; they need no change.

## 6. Token and compatibility analysis

**RAPP/1 Constitution Art. 2 (one label, one shape): no token moves.** Checked
rigorously:

- **Key set.** `rapp-hive/1-declaration` keeps its 9 closed members, and
  `schema.json` is byte-identical (pin `9b383535…`). A later declaration is a
  valid instance of the unchanged `$defs/declaration`. Vector
  `test_later_declaration_uses_the_same_closed_declaration_schema` checks this
  with Draft 2020-12 plus the format checker, `H.validate_declaration`, and
  `set(payload) == H.DECLARATION_KEYS`.
- **Field grammar.** Every field's pattern, enum and constant is unchanged.
- **Hash rules.** The particle hash of the payload and the wave hash of the
  frame are unchanged.
- **Kind.** `hive.declaration` and its body family are unchanged, as is its
  kind-to-schema binding (§1).
- **Convergence, projection, catalog and artifact manifest.** Shapes are
  unchanged. `base_convergence_payload_hash` keeps its grammar (hex64 or null)
  and its hash rule. Its value after a later declaration is newly *defined*,
  and on every existing history it equals today's value. §9.1 already speaks
  of "the latest accepted convergence" and "the actual current Mother frame".
- **Decision reason codes.** `roster-revoked` is a new value within the
  existing `label` grammar. It is descriptive, like every non-fork reason code
  (§8.3), and acceptance does not compare it.
- **What changes.** Only cross-document acceptance rules change: which Mother
  positions may carry a declaration, and which roster authorizes a mutation.
  Those are profile semantics, not shape. Art. 2 moves a token when a key set,
  field grammar or hash rule changes, and none does. Following Art. 5, the
  revised SPEC is adopted under the same name with a new signed pin: the
  estate appends a new `rapp-hive/1` protocol entry and deprecates the old
  one.

**Art. 18 (the wire is frozen).** Canonicalization, hashes and tags, RAPPID
grammar and mint, the eleven-key envelope, the consumer checklist, wire forms
and eggs are all untouched. The "strictly later" rule sits on top of RAPP/1
§7.5 step 4 (`utc` ≥ head); it never contradicts it.

**Art. 4 (growth by registration).** No new envelope, kind, endpoint or
registry entry type. `POST /chat` is untouched, and nothing even needs to be
registered.

**Art. 6 (owner authority in time).** Declarations verify against the owner in
effect at the frame's `utc`. In this profile that is the direct owner, with
tombstones gated at the artifact time; succession fails closed until G6.

**Art. 7 (identities are minted).** Members remain minted keyed RAPPIDs, and
nothing is derived from a name.

**Art. 8 (red oracles).** No check was skipped, muted or weakened. All 56
existing authenticated vectors and 8 scalar vectors pass unchanged in the
default mode. The same 56 also pass with the opt-in (§9).

**Art. 10 (one canonicalizer).** The reference uses the pinned `rapp.py`, and
no primitive is re-typed.

**Compatibility for existing conformant verifiers: they fail closed.**
Confirmed by the default-mode vectors and the registry vector:

1. With today's registry, today's gate refuses a later declaration ("declaration:
   unaccepted policy replacement"). It also refuses any convergence built on
   one, and a `restore()` of such a history fails and latches ("failed history
   recovery"). It never accepts a later declaration or a successor of one. A
   convergence that extends the old head is still accepted, leaving the
   declaration as a dead branch.
2. Once an estate re-signs its registry to the revised SPEC hash, today's
   reference refuses the registry itself: `RegistryAuthority` requires the
   `rapp-hive/1` pin to equal its local SPEC bytes (existing vector
   `test_registry_profile_pin_kind_family_and_registered_genesis`, variant
   `profile`). An old verifier therefore stops before it could misread any
   history.
3. Conversely, histories without later declarations verify identically under
   the proposal. The class `ProposalModeReplaysAuthenticatedVectors` replays
   all 56 authenticated vectors with the opt-in enabled: decisions, catalogs,
   checkpoints, manifests, forks and projections are unchanged. The proposal
   is therefore a conservative extension on existing data.

## 7. Security and privacy analysis

- **Who can change the roster.** Only the owner, signing a single-next Mother
  frame under the same serialized compare-and-swap as a convergence. The
  vectors refuse non-owner, removed-member, revoked-key, stale, competing,
  replayed and re-stamped declarations, and a declaration racing a
  convergence resolves through one compare-and-swap.
- **Back-dating.** Roster authority is decided by Mother position, not by the
  frame's `utc`. A removed member's frame dated before the removal is refused
  after it (`backdated` in
  `test_remove_member_quarantines_unsettled_frames_and_keeps_history`). This is
  stronger than the RAPP/1 §13 tombstone, which gates on producer-controlled
  time (RAPP/1 §14). The price is that honest in-flight frames of a removed
  member, and unsettled frames addressed to them, are also quarantined. The
  owner should settle wanted work first.
- **What removal can and cannot do (§12).** It **can** end future Hive
  authority, future room membership and so future key release, including for
  slices accepted before the removal. It **cannot** remove accepted frames or
  their current effects, un-publish anything, recall ciphertext, plaintext or
  keys already obtained, or revoke a key; key compromise needs a registry
  tombstone. Re-admission restores eligibility for earlier slices whose
  audience names the identity. That is an explicit owner act. Demotion to
  viewer is not removal: it ends mutation authority only, and key release
  still follows room membership and the slice audience.
- **Key-service freshness.** Mother head freshness is not self-certifying
  (RAPP/1 §14). A mirror can withhold a later declaration, and a key service
  on a stale head could still release to a removed identity. The proposed
  §3.1 text requires rollback-protected head tracking and recommends a
  refresh before each release. The reference deliberately certifies no key
  release (§14.2).
- **Removal releases conflicts.** Excluding a removed member's unsettled
  frames can turn a remaining concurrent frame into an independent update
  without a reconciliation. This is the existing exclusion rule for invalid
  candidates, and the removal is an owner-signed Mother frame. An accepted
  frame of a removed member still conflicts
  (`test_accepted_frames_of_a_removed_member_still_conflict`).
- **No fork evidence from unauthorized frames.** As in default mode, only
  frames authorized at the acceptance position enter fork detection. A removed
  member's frames, or anything depending on them, cannot latch a stream fork.
- **Verdicts do not depend on the verifier's cache.** Every roster-dependent
  verdict uses the roster in effect when it is asked: mutation authority in
  `_candidate`, and a projection receipt's channel in `accept_projection`. A
  chain walk may have been cached under an earlier roster, so it only
  authenticates. `test_a_retired_channel_is_never_current_even_after_a_cached_walk`
  walks a receipt before the declaration that retires its channel (mutation
  M19). The other walk-time checks read only what no declaration can change
  (Hive, world, owner, policy) or state that only grows (accepted
  convergences).
- **Registry side (§3 item 13).** A roster change cannot make an unregistered
  key verify: an admitted identity's frames stay `invalid-candidate` until the
  deciding verifier's registry registers its key and stream genesis
  (`test_registry_refresh_across_an_admission`); with the registry first, they
  are accepted at once (`test_registry_first_admission`). Every registry
  change that alters a recorded decision fails closed rather than
  mis-verifying. Recording a missing-registry quarantine and then registering
  the key makes a refreshed verifier refuse to restore the Hive and latch
  (`test_a_recorded_registry_quarantine_makes_a_later_refresh_fail_closed`),
  and deprecating a removed member's key does the same
  (`test_removal_keeps_the_removed_members_registry_key`). The same failure
  occurs for a key that signed a frame only listed as a conflict, duplicate,
  superseded frame, quarantine, stream-fork, or fork ancestor by an accepted
  convergence, because restore recomputes those decisions from authenticated
  bytes. Both are safe, but they stop that verifier from restoring the Hive,
  so the proposed text forbids both (registry first; never deprecate a key
  that signed any verified frame the accepted Mother history records or
  retains). A compromise tombstone keeps history verifiable only when its
  cutoff is later than every frame G6 requires it to follow; otherwise restore
  fails closed, as today.
- **Signature variants.** A settled frame's exemption applies only to its
  exact verified bytes. A re-signed variant is re-checked for signer/producer
  binding in the walk (`test_resigned_variant_of_a_settled_frame_is_not_exempt`).
  Proposal-mode walks still enforce the roster-independent payload shape, so
  unvalidated fields cannot create ancestry edges
  (`test_unvalidated_payload_shape_cannot_enter_ancestry`).
- **Owner-key compromise.** A compromised owner key could sign declarations,
  just as it can already sign convergences and reconciliations. Recovery stays
  RAPP/1's tombstone and out-of-band re-anchor. In the direct-owner profile a
  tombstoned owner key freezes the Mother stream at `revoked_utc`, and a
  declaration dated before `revoked_utc` but after the head still verifies
  (inherited RAPP/1 semantics, shown in `test_revoked_owner_key_cannot_declare`).
  G6 is the recovery path.
- **Privacy.** A later declaration carries the same classes of metadata as the
  genesis declaration: member RAPPIDs, areas, room membership and channel
  locators. It adds a history of who joined or left when, readable by
  everyone who can read the Mother stream. That is Hive-internal. §13
  templates already exclude member grants and live locators. No PII fields
  are added. Every vector uses synthetic fixture keys, `example-world` and
  `.invalid` locators.

## 8. Migration

- **Existing data.** No artifact changes, and histories without later
  declarations verify identically (§6).
- **Activation order** (all owner actions, §12):
  1. Accept the text of §4.
  2. Apply it to `protocols/rapp-hive/1/SPEC.md`.
  3. Move every pin in one change: `protocols/index.json` `spec_sha256`,
     `src/rapp_work/data/profiles.json` (`rapp-hive/1` `spec_sha256`), the
     vendored `.github/skills/rapp-private-hive/vendor/hive/SPEC.md` and its
     `rapp/agent.lock.json` protocol and file hashes, and then
     `python3 tools/release_inventory.py --write`.
  4. Re-sign `registry.json`: append the new `rapp-hive/1` `protocol` entry,
     mark the old one `deprecated:true`, and increment `registry_seq`.
  5. Decide the default (§11 Q6).
  6. Every adopting estate re-signs its own registry to the new pin, after its
     verifiers have been upgraded. An old verifier refuses the new registry,
     which fails closed.
- **Operating a roster change after activation** (§3 item 13):
  1. *Admission.* Re-sign the registry with a higher `registry_seq`, adding
     the identity's `spki` entry and the creation `genesis` of each stream it
     will write (for an added channel, also its receipt stream). Each verifier
     builds a new `RegistryAuthority` with its persisted high-water mark as
     `minimum_registry_seq`, then a fresh `HiveAcceptance`, and `restore()`s
     the accepted Mother head. Then the owner signs the later declaration.
     Until the owner's own verifier holds that registry, no convergence it
     signs lists the identity's frames (§3 item 13).
  2. *Removal.* Sign the later declaration only, and keep the removed
     identity's `spki` entry active. Converge wanted in-flight work first
     (§3 item 6).
  3. *Compromise.* Append a RAPP/1 §10 tombstone **and** remove the identity.
     The tombstone refuses the key's signatures at or after `revoked_utc`; the
     removal also refuses its unsettled frames stamped before that, which a
     tombstone alone cannot (§7, back-dating). As today, a tombstone dated at
     or before any verified frame of that key that an accepted convergence
     records or retains makes the Mother head unrestorable; G6 states the
     full cutoff rule, and RAPP/1 §14 advises advancing affected heads past
     `revoked_utc`.
  4. *Member key rotation.* A RAPP/1 re-anchor mints a new RAPPID, and the
     direct-owner reference refuses re-anchor records (G6). Until then,
     register the new key as a new identity, admit it, and remove the old
     identity while keeping its key active.
- **Private Hive skill.** `rapp-private-hive` constructs default-mode gates,
  and its bundle verifier refuses "topology replacement". Its behavior is
  unchanged. Its vendored reference bytes change, so its version moves from
  `3.2.0` to `3.2.1` (`lib/private_hive/__init__.py` and the lock): a version
  label names exactly one byte set, and `embed_project_skill` reports that
  version while it refuses a workspace embedded from other bytes (§11 Q9). The
  skill's documentation calls lock updates a maintainer action once source
  stabilizes. This one follows a deliberate reference change, not a repair.
- **Merge coordination** with sibling proposals that edit the same files:
  §13.1.

## 9. Conformance and test vectors

`protocols/rapp-hive/1/reference/roster_declaration_conformance.py` contains
96 vectors, all with real Ed25519 signatures over synthetic fixture keys.
`hive_conformance.py` runs it as check **H21**, and `tools/check.py` runs that.

- **`DefaultGateRefusesLaterDeclarations` (5), normative today.** The default
  gate refuses `accept_declaration` without the opt-in and refuses a
  non-boolean opt-in. A later declaration offered as a convergence, or any
  convergence stacked on one, is refused while the old head can still advance.
  `restore()` of a history containing a later declaration fails closed and
  latches. A byte-identical re-declaration is refused in both modes. A
  registered Mother genesis signed by a member key instead of the owner's is
  refused in both modes, by the declaration owner check.
- **`RosterDeclarationVectors` (20), proposal positives:**
  - same closed schema and envelope;
  - add a member, then accept their earlier-refused candidate;
  - remove a member: their unsettled, back-dated and dependent frames are
    `roster-revoked`, frames addressed to them are refused, a re-issued frame
    is accepted, earlier accepted frames stay in the catalog and stay active,
    and re-offering one is a `duplicate`;
  - a pending conflict of a removed member is released, not deadlocked, and
    omitting it is still refused;
  - pending dependents are released;
  - accepted frames of a removed member still conflict;
  - revoked ancestry latches no fork evidence;
  - demotion to viewer: the viewer's next frame is `roster-revoked`, while the
    roster in effect keeps it in its room, so the key-release model below
    still counts it eligible for a slice whose audience names it;
  - rooms: a room is added and a member is removed from a sealed room; the
    accepted slice stays in the catalog, and under the key-release model below
    the roster in effect no longer counts the removed member eligible;
  - authority channel switch, with current receipts at declaration heads,
    receipts for retired channels refused, and candidates' channels checked;
  - a retired channel's receipt stays refused even when a live verifier
    walked, and cached, its chain before the retiring declaration; a verifier
    restored after it refuses it too;
  - base commitments across a declaration (and every stale variant);
  - declarations before the first convergence;
  - a no-op declaration;
  - `restore()` of a history with two later declarations, from full and from
    retained-only bytes, followed by projection acceptance;
  - a reconciliation must bind the declaration head;
  - a removed member's dimension head survives re-admission, and a fork is
    still quarantined;
  - a declaration racing a convergence through one compare-and-swap;
  - signature variants;
  - payload shape in walks.

  **Key-release model.** The reference certifies no key release (§14.2). The
  two key-release assertions therefore evaluate `key_release_eligible`, a
  function defined in the vector file that models the proposed §3.1 rule, over
  the roster in effect that the gate exposes (`gate.declaration`). They show
  which roster a key service would read after the declaration. They do not
  test a key service.
- **`RosterDeclarationRefusals` (10):**
  - non-owner signers (member, viewer, outsider, a removed member);
  - a revoked owner key;
  - a changed `hive_rappid`, `world_id`, policy or schema, or an extra key;
  - the owner changed, demoted or removed, or zero or two owners;
  - an unsorted or duplicate roster, a room member who is not a Hive member,
    two authority channels, unsorted channels;
  - a room deleted, moved or re-classified (while retiring by shrinking is
    accepted);
  - a stale base, a competing declaration or convergence after the first
    commits, and replay of the head, of an older declaration and of the
    genesis;
  - an old payload replayed or re-stamped;
  - a `created_utc` that differs from the envelope, regresses, or equals the
    head;
  - declarations offered as catalog candidates, in both modes, and
    wrong-kind entry points.
- **`RegistrySideOfRosterChanges` (4)**, the registry prerequisites of §3
  item 13. Unlike the other vectors, these build their own registries instead
  of pre-registering every fixture key and stream:
  - *registry-first admission.* With the identity's key and dimension-stream
    genesis registered before the declaration, its frame is accepted as soon
    as the declaration is, and a fresh gate restores the result;
  - *a registry refresh across an admission.* Under a registry without the
    admitted identity's key and dimension-stream genesis, its frame is
    `invalid-candidate` although the roster names it. As long as no
    convergence records that quarantine, a fresh gate on a higher
    owner-signed registry, with the old sequence as its high-water mark,
    restores the same history (the later declaration included) to the same
    checkpoint except the registry fields, and then accepts the frame;
  - *a recorded registry quarantine.* Once a convergence records that
    quarantine, the same refresh makes `restore()` fail closed ("decisions
    differ") and latch, while a verifier on the old registry still restores
    the history; this is why the proposed text requires the registry first;
  - *removal keeps the removed member's key.* Re-signing the registry with
    that key deprecated makes `restore()` of the Hive's own head fail closed
    ("decisions differ") and latch. With a compromise tombstone instead,
    `restore()` reaches the same checkpoint apart from the registry fields,
    and the key's later frame is `invalid-candidate`, where the removal alone
    makes it `roster-revoked`.
- **`ProposalModeReplaysAuthenticatedVectors` (57).** All 56 existing
  authenticated vectors re-run with `roster_declarations=True`, plus a check
  that they really use the opt-in. This is the conservative-extension evidence.

Every refused declaration also asserts that the checkpoint, the roster in
effect and the head are unchanged.

### 9.1 Controlled mutations (run locally on a scratch copy, then discarded)

Each mutation changed one expression in a scratch copy of
`reference/hive_acceptance.py`, and both suites were run against the copy. The
unmutated copy passed 96 of 96 roster vectors and 64 of 64 authenticated
vectors. Under every mutation, the default-mode authenticated suite stayed
64 of 64 green. For M2 to M7 and M9 to M19 that is expected, because they
touch opt-in paths. M1 edits the declaration owner check, which also runs in
default mode on the registered Mother genesis; no authenticated vector has a
genesis signed by anyone but the owner, so the default-mode vector
`test_a_registered_genesis_not_signed_by_the_owner_is_refused_in_both_modes`
in the roster module now pins it. M8 makes the proposal the default, so its
green default suite shows that the proposal does not disturb existing vectors.
M20 changes the base `RegistryAuthority`, so it reaches the default path too.
The default suite stays green under it because no existing vector pins the
retirement of a deprecated key; the new removal vector now does.

| ID | Mutation | Red roster vectors |
| --- | --- | --- |
| M1 | Declaration signer need not be the owner (`owner == registry.owner == signer` → `owner == registry.owner`) | `test_only_the_owner_signs_a_declaration` (4 subtests) and `test_a_registered_genesis_not_signed_by_the_owner_is_refused_in_both_modes` (2 subtests, the default mode included) |
| M2 | `accept_declaration` skips the single-next-Mother-frame check | `test_a_declaration_is_the_single_next_mother_frame` |
| M3 | Declaration time may equal the head (`>` → `>=`) | `test_declaration_time_is_envelope_time_and_strictly_after_the_head`, `test_identical_redeclaration_is_not_a_successor_in_either_mode` |
| M4 | No roster check at the acceptance position | 13 vectors (15 failures counting subtests): 10 proposal vectors and 3 replayed authenticated vectors (foreign Hive or world, sealed-room plaintext, unauthorized producer/viewer/area) |
| M5 | `world_id` may change | `test_hive_world_policy_and_schema_are_immutable` |
| M6 | Explicit owner-succession boundary removed | `test_the_owner_is_unique_and_unchanged` (2 subtests: the refusal is still made by the registry-owner check, but no longer names G6) |
| M7 | A declared room may disappear or change area/access | `test_declared_rooms_persist_with_their_area_and_access` (3 subtests) |
| M8 | Proposal becomes the default | 4 of the 5 `DefaultGateRefusesLaterDeclarations` vectors (the genesis-owner vector sets the flag explicitly, so it runs in both modes either way) |
| M9 | Base convergence reverts to the head-is-convergence rule | `test_convergence_base_commitments_across_a_declaration`, `test_authority_channel_switch_and_current_projection_at_a_declaration_head`, `test_a_no_op_declaration_only_advances_the_mother_head` |
| M10 | A `roster-revoked` pending candidate still aborts the convergence | 3 vectors error (pending conflict, pending dependents, restore) |
| M11 | Current receipt must bind the head payload even at a declaration head | 2 vectors error (channel switch, restore) |
| M12 | Only the candidate tip is authorized, not its unsettled ancestry | `test_revoked_ancestry_cannot_block_or_latch_fork_evidence`, `test_pending_dependents_of_a_revoked_frame_are_released`, `test_remove_member_quarantines_unsettled_frames_and_keeps_history` |
| M13 | Proposal-mode walk drops the signer/producer check | `test_resigned_variant_of_a_settled_frame_is_not_exempt` |
| M14 | Proposal-mode walk drops the payload shape check | `test_unvalidated_payload_shape_cannot_enter_ancestry` |
| M15 | Roster revocations classified as ordinary invalid candidates | 9 vectors (6 fail, 3 error) |
| M16 | Settled history is re-authorized against the roster in effect | `test_remove_member_quarantines_unsettled_frames_and_keeps_history`, `test_demotion_to_viewer_revokes_future_mutation_only`, `test_revoked_ancestry_cannot_block_or_latch_fork_evidence` |
| M17 | `restore()` replays every Mother frame as a convergence | 7 vectors (1 failure and 8 errors counting subtests): restore, reconciliation at a declaration head, the cached retired-channel receipt, and all four registry vectors |
| M18 | No manifest while the Mother head is a declaration | 3 vectors error (channel switch, restore, the cached retired-channel receipt) |
| M19 | `accept_projection` drops the acceptance-time channel check, so a walk cached under an earlier roster decides | `test_a_retired_channel_is_never_current_even_after_a_cached_walk` |
| M20 | The base `RegistryAuthority` keeps a deprecated `spki` entry active (default path too) | `test_removal_keeps_the_removed_members_registry_key` |

## 10. Reference implementation and gating

**Files:**

- `protocols/rapp-hive/1/reference/hive_acceptance.py`
- its byte-exact vendored mirror
  `.github/skills/rapp-private-hive/vendor/hive/reference/hive_acceptance.py`
- the skill version, `3.2.0` → `3.2.1`, in
  `.github/skills/rapp-private-hive/lib/private_hive/__init__.py`, and
  `.github/skills/rapp-private-hive/rapp/agent.lock.json` (its `version` and
  the entries of the two changed files)
- `protocols/rapp-hive/1/reference/roster_declaration_conformance.py` (new)
- `protocols/rapp-hive/1/reference/hive_conformance.py` (check H21)
- `protocols/rapp-hive/1/reference/README.md`
- `CHANGELOG.md` and `RELEASE-INVENTORY.json`

The SPEC, the schema, `registry.json`, `protocols/index.json`,
`src/rapp_work/data/profiles.json` and every signed pin are unchanged.

**Gate.** `HiveAcceptance(registry, hive_rappid, resolve_chain, *,
roster_declarations=False)`. The keyword is keyword-only and must be a real
`bool`; `1`, `"true"` and `None` are refused. With the default:

- `accept_declaration` refuses before resolving anything.
- The declaration branch of `_authorized` is today's code in today's order.
- The object/slice authorization executes the same statements, extracted
  verbatim into `_mutation_authorized`.
- `_base_convergence()` returns today's expression.
- `artifact_manifest`, `accept_projection` and `restore` take today's branch.
- The existing 64 vectors, the vendored vectors, the skill suite (whose
  deployment verifier refuses "topology replacement") and the SDK tests are
  unchanged and pass.

**Opt-in additions:**

- `accept_declaration(frame_hash)`: single-next compare-and-swap,
  strictly-later time, rooms persist, and the roster in effect is updated
  atomically.
- A read-only `declaration` property: the roster in effect, and the genesis
  in default mode.
- Acceptance-position authorization in `_candidate`, over the candidate and
  its unsettled ancestry.
- A `RosterRevoked` classification and the `roster-revoked` reason code, with
  the pending backlog released for it.
- The last-accepted-convergence base rule.
- Manifest and current receipts at a declaration head.
- A projection receipt's channel checked against the roster in effect at
  acceptance, not only in a possibly cached chain walk.
- A `restore()` that dispatches declarations to `accept_declaration`.

## 11. Open questions for the owner

1. **Q1, room removal.** The draft forbids deleting a declared room or
   changing its `area`/`access`; a room is retired by shrinking it. Accept, or
   allow deletion with explicit rules for orphaned objects and slices?
2. **Q2, audiences naming a removed identity.** The draft quarantines
   unsettled frames addressed to a removed identity (the literal reading of
   §5). The alternative accepts them and treats the identity as absent for key
   release, at the cost of accepted frames that name non-members.
3. **Q3, no-op declarations.** They are permitted (they only advance the
   Mother head). Keep them, or require a change?
4. **Q4, `roster-revoked`.** It is descriptive and, like other non-fork reason
   codes, not compared at acceptance. Should it become a compared diagnostic,
   like `stream-fork`?
5. **Q5, member areas.** They may change, including reassigning a removed
   member's area to another member. Acceptable?
6. **Q6, default.** After acceptance, flip `roster_declarations` to on (and
   keep today's refusal as explicit `False` vectors), or keep the opt-in for
   the LTS?
7. **Q7, time rule.** "Strictly later" applies only to declarations;
   convergences keep RAPP/1's "≥ head". Extend it to every Mother frame that
   follows a declaration?
8. **Q8, declarations before the first convergence.** Allowed and tested. Keep?
9. **Q9, skill version.** The draft moves `rapp-private-hive` from `3.2.0` to
   `3.2.1`, because its vendored reference bytes change and a version label
   must name one byte set: `embed_project_skill` refuses a workspace embedded
   from main's bytes ("existing project skill differs") and reports the
   version in its receipt. It is a patch step because the skill's interface
   and default behavior are unchanged. Keep `3.2.1`, prefer `3.3.0` for the
   new opt-in capability, or pick one number for a combined release with G6
   (§13.1)?
10. **Q10, SDK exposure.** Should `rapp-work-sdk/1` expose roster declarations
    through its operations? This is out of scope here, and the SDK is
    unchanged.
11. **Q11, registry keys of declared members.** The draft makes registry
    first an owner duty (**MUST**, §3 item 13 and §4.1) but does not check it
    when a declaration is accepted, because that would make a declaration's
    verdict depend on the verifier's registry. Keep it an owner duty, or make
    it a checked rule for newly admitted identities?

## 12. Owner actions needed

1. Accept, amend or refuse the §4 text.
2. If accepted:
   - Apply it to `protocols/rapp-hive/1/SPEC.md`.
   - Move the pins listed in §8 in one change, and regenerate
     `RELEASE-INVENTORY.json`.
   - **Re-sign `registry.json`** with the owner key: a new `rapp-hive/1`
     protocol entry pinning the new SPEC hash, the old entry deprecated, and a
     higher `registry_seq`.
3. Decide Q6, the default. If flipping: set `roster_declarations=True` by
   default, and turn `DefaultGateRefusesLaterDeclarations` into explicit
   `roster_declarations=False` vectors.
4. Answer Q1 to Q11 (or accept the draft choices).
5. Release as `rapp-work` 1.1.0, merging in the order of §13.1.
6. **Estate lead or owner:** the estate signing kit pins
   `protocols/rapp-hive/1/reference/hive_acceptance.py` by SHA-256 at base
   `29ead23` (`88184a7e…`). The draft implementation branch changes that file, so refresh that pin
   when the reference ships; on activation the kit's `rapp-hive/1` SPEC pin
   moves too. This workstream does not edit the kit.
7. The lead relays G1's new status word, `proposed`, to the organism.

**Ready-to-file pull request text** (for the owner; this workstream opens no
PR):

> **Title:** Proposal 0001: owner-signed later declarations for rapp-hive/1 (G1)
>
> **Body:** Adds draft proposal
> `docs/proposals/0001-rapp-hive-roster-declaration.md`. The reference mode
> stays on branch `experimental/gap-g1-roster-declaration` until proposal
> acceptance, then opens as a draft implementation PR. There is no SPEC, schema or registry change;
> activation needs the owner to accept the text, merge the draft
> implementation, and only then apply the SPEC text and re-sign the registry.
> The implementation branch currently carries H23 vectors for default refusal,
> proposal positives and refusals, the registry side of roster changes, and a
> replay of authenticated vectors in proposal mode.

## 13. Interactions with other gaps

- **G6, owner succession.** This proposal keeps the owner immutable and says
  so in the refusal ("an owner change is succession (gap G6), not a roster
  declaration"). G6 can later relax that rule without a new frame form: a
  later declaration whose `owner` is the successor RAPPID, accepted only when
  the registry's time-scoped tenure (RAPP/1 §13.2) makes that successor the
  owner in effect at the declaration's `utc`. Until then, a tombstoned owner
  key freezes the Mother stream (§7). Code coordination is covered in §13.1.
- **G8, folder-Hive members are names bound to keys.** G8 concerns folder
  Hives, whose members are names bound to keys by the folder Hive's signed
  history. This proposal does not change that and does not import name-bound
  membership into `rapp-hive/1`. `rapp-hive/1` members remain minted keyed
  RAPPIDs resolved through the RAPP/1 §13 registry (Art. 7). The two designs
  only look alike: both change membership through signed history.

### 13.1 Related proposals and merge order

Sibling experimental branches in `kody-w/rapp-work` that edit the same files
as this one:

- **`experimental/gap-g6-owner-succession`** (proposal 0006, G6) edits
  `protocols/rapp-hive/1/reference/hive_acceptance.py` and its vendored
  mirror: an opt-in RAPP/1 §13.2 succession mode in `RegistryAuthority`, an
  `owner_at(utc)` method, a new `rapp_registry` import, and the tenured owner
  in the signer checks, including the declaration owner check that this
  branch also touches. It also edits `agent.lock.json` (adding
  `vendor/hive/reference/rapp_registry.py`), `protocols/rapp-hive/1/reference/README.md`
  and `hive_conformance.py`, where it adds checks **H21** and **H22**. It keeps
  the skill version at `3.2.0`.
- **`experimental/gap-g2-move-action`, `experimental/gap-g3-agent-discovery`,
  `experimental/gap-g4-migration-successors`,
  `experimental/gap-g7-instruction-inventory`,
  `experimental/gap-g11-workspace-index` and
  `experimental/gap-g17-brainstem-sdk-agent`** share only `CHANGELOG.md` (each
  adds an unreleased entry) and `RELEASE-INVENTORY.json` (regenerated). None
  touches the Hive reference.

**Recommended order, if both are accepted: G6 first, then G1.** G6 supplies
the owner-in-effect verifier that §3.2 item 2 names; in the direct-owner
profile the two coincide, so G1 is correct on its own. When G1 is merged
second:

1. In the declaration branch of `_authorized`, keep G6's tenured owner check
   (`owner == owner_at(utc) == signer`), G1's `_successor_invariants` call
   before it, and the default-mode `payload == self._declaration` refusal
   after it. Owner changes through a later declaration stay future work (G6
   bullet above), so after an owner rotation in G6's succession mode, later
   declarations are refused until that follow-up lets one name the successor.
2. Renumber G1's conformance check from H21 to H23, here, in the reference
   README and in the CHANGELOG entry.
3. Keep both README sections and both CHANGELOG entries.
4. Re-mirror the merged reference into the vendored copy, regenerate the lock
   entries, choose one skill version for the combined bytes (§11 Q9), and run
   `python3 tools/release_inventory.py --write`.
5. Rerun both suites and this proposal's mutation table, whose anchors may
   move.

If G1 is merged first, the same points apply in reverse: G6's merge replaces
`self.registry.owner` with the tenured owner in G1's declaration branch too.

## 14. Rollback

- **Before activation.** Drop the branch. Nothing normative or signed was
  changed.
- **Code.** Reverting the later implementation branch restores the previous
  reference bytes, the vendored copy, the skill version and lock, and the
  inventory. Reverting this proposal-only PR removes only this proposal and
  its inventory entry.
- **After activation.** An estate that has accepted later declarations cannot
  return to a verifier that refuses them and still verify its own Mother
  history. The old verifier fails closed; it never silently mis-verifies. The
  lawful way back is to stop signing later declarations. If the owner must
  return to a single-declaration history, the only path is a new Hive
  identity (re-genesis), because Art. 3 allows no legacy lane. Declarations
  already accepted remain immutable history.

## 15. References

- `protocols/rapp-hive/1/SPEC.md` §§3, 3.1, 5, 7, 8.1 to 8.4, 9, 9.1, 10, 12,
  14 and 14.2 (pinned hash above); `protocols/rapp-hive/1/schema.json`
  `$defs/declaration`
- `protocols/rapp-hive/1/reference/hive_acceptance.py`,
  `authenticated_conformance.py`, `hive_conformance.py`,
  `roster_declaration_conformance.py` and `README.md`
- RAPP/1 (`vendor/rapp-1/SPEC.md`) §7.4 to 7.6 (chaining, the consumer
  checklist, heads and forks), §9.2.1 (revocation limits), §10 (key discovery,
  key lifecycle and tombstones), §13.1 to 13.3 (registry, owner tenure, entry
  types) and §14 (security); the pinned RAPP/1 registry reference
  `vendor/rapp-1/rapp_registry.py` (`Registry.signer_acceptable`)
- RAPP/1 Protocol Constitution, `kody-w/rapp-1` `CONSTITUTION.md`, Articles 2,
  3, 4, 5, 6, 7, 8, 10 and 18
- `SPEC.md` (`rapp-work/1`) §§6 and 11, `CONTRIBUTING.md`, `docs/RELEASE.md`
- Organism gap G1 (source of the gap), and gaps G6 and G8

## 16. Revision history

- **Round 1** (`60cca1d`): the first draft and opt-in reference.
- **Round 2** (`d577819`): answered the round-1 independent review (the
  roster-in-effect channel check for receipts, demotion and key release, the
  registry side of roster changes, skill version 3.2.1, the key-release model
  wording, related proposals, and the estate-kit pin).
- **Round 3** (this revision): answered the round-2 review. Admission is
  registry-first as a **MUST**, and a convergence must never record a
  quarantine caused only by a missing registry key or stream genesis, because
  a later registry that registers them makes `restore()` fail closed and latch
  (new vectors `test_registry_first_admission` and
  `test_a_recorded_registry_quarantine_makes_a_later_refresh_fail_closed`;
  the same hazard exists on `main`). A default-mode vector now pins the
  declaration owner check on the registered genesis (mutation M1), and the
  status relay names only the new status word.
- **Round 3 review** (`1899e52`): clean, with one low finding (the M8 row now
  says 4 of the 5 default-gate vectors turn red).
