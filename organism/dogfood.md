---
name: "Dogfood: the RAPP Hive, our public example"
health: experimental
tree:
  - "HIVE.md: members: the maintainers (AIs are tools)"
  - "shared/organism/canon/: one canonical fact per file, hash-stamped"
  - "shared/organism/drift/: one verdict per repo: aligned or drifted"
  - "shared/organism/map/: layers 0–6 · crossings · this page"
  - "shared/organism/gaps/: one file per gap"
  - "(your device): references: every estate repo, read-only"
loop:
  - "Canon: one fact, once, from its repo"
  - "Sweep: rapp_check.py, not in the Hive"
  - "Record: one verdict per repo, signed"
  - "Fix upstream: the next sweep flips it"
---
**Built locally, not yet published.** Its first sweep ran rapp-1's own `rapp_check.py` over 10 public estate repos: 7 were compliant or clean and 3 showed drift (non-conformant eggs in RAPP and RAR; frozen frames in rapp-model-hive's main that cannot be signature-checked, gap G8). Each verdict is one signed file. **How it scales:** the same one agent and the same rules run the 6-person Contoso model and 10 real repos, on the way to about 30.
