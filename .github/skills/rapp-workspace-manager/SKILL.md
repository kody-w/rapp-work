---
name: rapp-workspace-manager
description: Main RAPP Work entrypoint for creating, registering, listing, and opening local RAPP Workspaces. Use when a user wants to start or organize workspaces, route work by world, or add Private Hive capability.
---

# RAPP Workspace Manager

This is the front door for RAPP Work.

Use `scripts/manage.py` to create and register local workspaces. The manager
stores pointers only—never workspace content—under
`~/.config/rapp-work/workspaces.json` unless `--registry` is supplied.

## Create a workspace

```bash
python3 scripts/manage.py create \
  --path /path/to/workspace \
  --owner-label owner \
  --slug workspace-name \
  --world-id world-name
```

The new workspace includes:

- a mint-once RAPPID;
- the `rapp-workspace/2.0` specification;
- the `rapp-workspace`, `rapp-private-hive`, and
  `rapp-workspace-manager` project skills;
- the append-only project-frame tool; and
- a private/local-only guard.

## Register an existing workspace

```bash
python3 scripts/manage.py register --path /path/to/workspace
```

Registration stores only its path, RAPPID, world, mode, and active state.

## List workspaces

```bash
python3 scripts/manage.py list
```

The manager never reads one workspace's content to answer a request for another
world. Private Hive publication remains explicit and owner-approved.

