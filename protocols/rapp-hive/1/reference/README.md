# Authenticated Hive acceptance

Run the complete profile gate from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 protocols/rapp-hive/1/reference/hive_conformance.py
```

`HiveAcceptance` consumes exact signed RAPP/1 frames through an immutable-byte
resolver and an independently anchored `RegistryAuthority`. Structural payload
validation is not acceptance. The [SPEC](../SPEC.md) defines the unchanged frame,
catalog, convergence, and projection contracts.

## Durable fork quarantine

An authenticated same-stream/sequence fork is not a mutation conflict that an
ordinary owner reconciliation can merge. The gate compares candidate ancestry
(including signed cross-stream sources) with previously retained history.
Once a Mother convergence accepts that evidence, it retains both signed
branches and their causal ancestry and latches the earliest conflicting
position of the stream. Retrying either branch alone, a later successor, or a
transitive dependent cannot escape quarantine.

The accepted Mother history already commits candidate wave addresses and
decisions; no new envelope or payload fields are added. `stream-fork` and
`fork-ancestor` diagnostics must agree with authenticated evaluation. They
assert retained fork evidence, not permission or an owner resolution. Other
reason codes remain descriptive. A signer cannot erase these diagnostics or
invent them for unauthenticated candidates.

The artifact manifest includes authenticated fork evidence, even though those
quarantined frames do not enter the accepted catalog. Unauthenticated frames
and false candidate summaries cannot create a latch or inject manifest entries.
Previously accepted catalog entries remain immutable historical evidence;
faulted branches and their dependents no longer participate as active effects.

Persist `checkpoint()` and all manifest artifacts atomically. A new verifier's
`restore(mother_head_frame_hash)` re-verifies the signed history and rebuilds the
fork frontier. Missing or invalid recorded fork evidence fails restoration; it
cannot silently become an ordinary invalid-candidate quarantine with a clean
frontier. A failed restore disables further acceptance and projection on that
verifier. Recover the complete authenticated history before using a fresh one.

Previewing a convergence or refusing its signature, decisions, or commitments
does not change accepted state or latch a fault. Only successful serialized
Mother acceptance does. Neither registry refresh nor ordinary reconciliation
clears a known fork. Owner resolution/re-genesis is not implemented by this
bounded gate; no reset API is provided.

## Draft proposal 0001: owner-signed later declarations (opt-in, not accepted)

[`docs/proposals/0001-rapp-hive-roster-declaration.md`](../../../../docs/proposals/0001-rapp-hive-roster-declaration.md)
proposes letting the owner change a Hive's members, room membership and
channels with a later signed `hive.declaration` on the Mother stream. The SPEC
has not accepted it, so `HiveAcceptance(...)` keeps refusing every declaration
after the genesis. Only `HiveAcceptance(..., roster_declarations=True)` enables
`accept_declaration(frame_hash)`, which accepts an owner-signed declaration
using the same closed `rapp-hive/1-declaration` schema only as the single next
Mother frame, strictly later than the Mother head. The world, policy and owner
stay the same, and every declared room keeps its area and access. With the
opt-in, the roster that authorizes an unsettled mutation is the one in effect
at the Mother head being extended, never the frame's self-asserted time.
Accepted history is never re-evaluated. `roster-revoked` marks unsettled
frames that an earlier accepted roster authorized but the current one does not.

`roster_declaration_conformance.py` holds the default-refusal, positive and
refusal vectors. It also replays every authenticated vector with the opt-in
enabled. `hive_conformance.py` runs it as check H21.
