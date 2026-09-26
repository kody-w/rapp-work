---
name: RAR
column: in
beside: 5
role: The public registry of single-file agents
home: "[`kody-w/RAR`](https://github.com/kody-w/RAR) (`rapp-registry/1.1`; its README still says 1.0)"
health: specified; no estate pins `rapp-registry/1.1` yet, and the LTS kernel installs from RAR's moving `main`
check: Each repository's own test suite and runner
lines:
  - one-file agents
  - you add one to agents/
---
RAR is the public registry of single-file agents.

- Read an agent before you use it; nothing makes you.
- You add it yourself: copy it into your Brainstem's `agents/` folder, or press Add in the LTS kernel's RAR browser, which loads it at once. The Brainstem then installs any missing Python package it imports.
- Nothing pins it yet. No estate pins `rapp-registry/1.1`, and the LTS kernel reads RAR's moving `main`, which RAPP/1 treats as discovery, never authority (§11.2). The newest kernel, `brainstem-v0.6.16`, pins RAR to a commit and asks before it installs.
