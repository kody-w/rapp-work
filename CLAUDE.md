# RAPP Work entrypoint

Use `.github/skills/rapp-workspace-manager/SKILL.md` as the primary workflow.
It creates and registers local RAPP Workspaces while storing pointers only.

Use `.github/skills/rapp-workspace/SKILL.md` for project-frame operation and
`.github/skills/rapp-private-hive/SKILL.md` for migration and Private Hive
deployment.

`SPEC.md` is the RAPP Work contract. RAPP/1 remains authoritative for identity,
frames, hashes, signatures, eggs, and registries.

Preserve world boundaries. DOGG is PII-free. GODD is private. Do not publish,
send, grant access, create a remote, or perform another outward action without
explicit owner approval.
