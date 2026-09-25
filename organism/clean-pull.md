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
door:
  - "planned: the installer README's “Start here” leads with the RAPP/1 LTS install (`kody-w/rapp-installer#48`, open)"
  - "planned: every RAPP repo shows its earned RAPP/1 badge and a “Start here” link (PRs open in 13 of the stack's 15 repos)"
  - "experimental: the drift sweep sets each status, and `kody-w/rapp-hive-public` publishes the portfolio: the RAPP/1 stack is 12 of 15 certified"
---
Raw word hits, and some are legitimate, such as folder names: mentions, not problems. Run it again at lock time.
