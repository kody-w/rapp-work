---
name: Keep the default pull clean
phase: 2
command: "`git grep -l -i experimental origin/HEAD`"
measured: 2026-09-26
mentions:
  - "rapp-hive-public: 342"
  - "RAR: 50"
  - "RAPP: 46"
  - "rapp-workspace: 26"
  - "rapp-hive-hub: 19"
  - "rapp-installer: 9"
  - "rapp-model-hive: 9"
  - "hive-hub: 6"
  - "lisppy: 1"
  - "rapp-1: 0"
  - "rapp-work: 0"
  - "rapp-drift-lint: 0"
  - "hive-hub-join: 0"
  - "hive-hub-mcp: 0"
  - "rapp-hive-hub-join: 0"
door:
  - "proposed: the installer's “Start here”, where every header links, leads with the RAPP/1 LTS install (`kody-w/rapp-installer#48`, open; only the owner merges it)"
  - "experimental: 13 of the stack's 15 default branches show their RAPP/1 status badge (10 certified, 3 not yet) and a “Start here” link; `rapp-installer` waits on #48, `rapp-workspace` on G24"
  - "experimental: the drift sweep sets each status; the portfolio in `kody-w/rapp-hive-public`, the network's notice board, shows 12 of the stack's 15 certified, and every repo's channel and lifecycle"
---
Mentions, not problems; some are legitimate. Recount at lock time.
