---
name: Keep the default pull clean
phase: 2
command: "`git grep -l -i experimental origin/HEAD`"
measured: 2026-09-25
mentions:
  - "RAR: 50"
  - "RAPP: 45"
  - "rapp-workspace: 26"
  - "rapp-hive-hub: 19"
  - "rapp-installer: 9"
  - "rapp-model-hive: 8"
  - "hive-hub: 6"
  - "lisppy: 1"
  - "rapp-1: 0"
  - "rapp-work: 0"
---
Raw word hits, and some are legitimate, such as folder names: mentions, not problems. Run it again at lock time.
