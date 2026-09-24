---
name: Release rings
column: out
beside: 2
role: Canary, nightly, alpha, beta, then each track's grail
home: "`rapp-cicd/1` and `rapp-deploy/1` in `kody-w/rapp-1`"
health: in force
lines:
  - canary → nightly
  - → alpha → beta
  - → each grail
---
Releases move through rings: canary, nightly, alpha, beta, then each track's grail.

- Each step carries `rapp-cicd/1` and `rapp-deploy/1` evidence.
