---
name: Keep the default pull clean
phase: 2
command: "`git grep -l -i experimental origin/HEAD`"
measured: 2026-09-25
mentions:
  - "rapp-hive-public: 338"
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
  - "rapp-drift-lint: 0"
  - "hive-hub-join: 0"
  - "hive-hub-mcp: 0"
  - "rapp-hive-hub-join: 0"
door:
  - "proposed: the installer's “Start here” leads with the RAPP/1 LTS install (`kody-w/rapp-installer#48`, open)"
  - "proposed: every RAPP repo shows its earned RAPP/1 badge and a “Start here” link (PRs open in 13 of the stack's 15; `rapp-hive-public` has it; `rapp-workspace` waits on G24)"
  - "experimental: the drift sweep sets each status; the portfolio in `kody-w/rapp-hive-public` shows 12 of the stack's 15 certified"
---
Mentions, not problems; some are legitimate. Recount at lock time.
