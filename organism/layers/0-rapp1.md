---
layer: 0
name: RAPP/1
role: "Bytes and identity: RAPPIDs, the eleven-key frame, hashes, signatures, eggs, registries"
decides: The protocol itself (frozen forms)
signed_with: Ed25519 (or ES256) detached JWS
home: "[`kody-w/rapp-1`](https://github.com/kody-w/rapp-1) `SPEC.md`"
health: in force
color: purple
check: Its conformance suite in `kody-w/rapp-1`
lines:
  - RAPPIDs · the eleven-key frame · hashes · Ed25519 (or ES256) signatures · eggs · registries
  - Frozen forms
---
RAPP/1 is the floor. It fixes how bytes are written, hashed and signed, so two machines that never met agree on what they hold.

- A RAPPID names a thing once, forever.
- A frame has exactly eleven keys. Its shape checks never change; only a later tombstone can flip its signature check.
- An egg packs a unit of an estate. A registry says who may sign as whom.

Every layer above builds on these forms and never redefines them.
