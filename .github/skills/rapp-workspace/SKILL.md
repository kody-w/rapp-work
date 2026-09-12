---
name: rapp-workspace
description: Operate or upgrade a RAPP Workspace. Use for local-first workspace organization, append-only project frames, Private Hive migration/deployment, DOGG/GODD boundaries, or Hive Mind federation.
---

# RAPP Workspace

This root file is the compatibility entry point. Current GitHub Copilot CLI
project skills ship with the workspace:

- `.github/skills/rapp-workspace/SKILL.md`
- `.github/skills/rapp-private-hive/SKILL.md`

When the repository is cloned or shared, Copilot discovers those capabilities
automatically after the workspace is trusted. In an existing session, run
`/skills reload`.

Read `SPEC.md` for the protocol. Use:

- `.github/skills/rapp-workspace/append_frame.py` for project frames and leases.
- `.github/skills/rapp-private-hive/scripts/prepare_workspace.py migrate` to
  upgrade an older local-first workspace without changing its existing data.
- `.github/skills/rapp-private-hive/scripts/deploy_hive.py` for signed Private
  Hive authority, private filesystem/NAS or private GitHub publication, and
  independent client verification.

Never publish workspace content merely because the tooling exists. Local data
stays local unless explicitly selected, DOGG-cleared, approved, signed, and
published through a configured private channel.
