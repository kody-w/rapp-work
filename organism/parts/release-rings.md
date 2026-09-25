---
name: Release rings
column: out
beside: 2
role: "Estate-named stages over `rapp-cicd/1` §3: here canary, nightly, alpha, beta, the Preprod gate, then the production ring (the grail)"
home: "`rapp-cicd/1` §3 and `rapp-deploy/1` in `kody-w/rapp-1`"
health: specified; the kody-w estate pins `rapp-cicd/1` and `rapp-deploy/1`, but no estate names these rings or has run a release through them (G16)
lines:
  - canary → nightly → alpha → beta
  - → preprod → grail · rapp-cicd/1 · rapp-deploy/1
---
Releases move through stages that each estate names over `rapp-cicd/1` §3. Here they are canary, nightly, alpha and beta, then the Preprod gate, then the production ring, which this project calls the grail and which needs the owner's approval. That grail is not the Grail kernel.

- Each stage carries `rapp-cicd/1` evidence. User traffic after the production promotion carries `rapp-deploy/1` health evidence.
