---
name: Workspaces
layer: 4
order: 3
role: Your private, local-first workspaces (GODD), changed only by exact SDK plans
home: RAPP Workspace/1; `rapp-work-sdk/1`
health: in force
check:
  - "`python3 tools/check.py`, `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`"
  - "For `rapp-hive/1` and Workspace/1: the `kody-w/rapp-workspace` CI jobs (core pins and conformance, Private Hive suite)"
lines:
  - private GODD
  - local-first
  - SDK plans
---
Your workspaces are private and local-first. They never go into a Hive unless you bring something by signed copy.

- The SDK plans every change. It applies a plan only with that plan's exact hash (`plan_sha256`).
