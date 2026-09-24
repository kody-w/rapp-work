---
name: Release rings
column: out
beside: 2
role: Canary, nightly, alpha, beta, then each track's grail
home: "`rapp-cicd/1` and `rapp-deploy/1` in `kody-w/rapp-1`"
health: in force
lines:
  - canary → nightly → alpha → beta → grail
  - rapp-cicd/1 · rapp-deploy/1
---
Releases move through rings: canary, nightly, alpha, beta, then each track's grail.

- Each step carries `rapp-cicd/1` and `rapp-deploy/1` evidence.
