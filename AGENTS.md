# RAPP Work agent entrypoint

RAPP Work is the business collaboration and compliance layer over RAPP/1.

Start with:

1. `.github/skills/rapp-workspace-manager/SKILL.md` to create, register, list,
   or route among local RAPP Workspaces.
2. `.github/skills/rapp-workspace/SKILL.md` to operate workspace project
   frames, leases, handoffs, and verification.
3. `.github/skills/rapp-private-hive/SKILL.md` to migrate an older workspace,
   prepare Hive selections, create signed authority, publish privately, or
   verify a Hive client.

Read `SPEC.md` before changing protocol behavior. RAPP/1 remains authoritative
for identity, frames, hashes, signatures, eggs, and registries.

Never infer authority from an AI vendor, account, URL, transport, or repository
permission. Humans, AIs, agents, and services participate through the same
RAPPID, signature, policy, and evidence rules.

DOGG must be PII-free. GODD remains private. Nothing leaves a workspace unless
it is explicitly classified, selected, approved, and sent through an
authorized channel.
