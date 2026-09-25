# Create-only migration

`rapp-work migrate` creates a successor integration directory. It never
rewrites or deletes the source.

## Plan

```bash
rapp-work migrate \
  --source /absolute/path/legacy \
  --target /absolute/path/successor \
  > migration-plan.json
```

The `MigrationPlan` binds:

- lexical source and target paths;
- source filesystem device/inode identity;
- source RAPPID, world, kind, and prior workspace profile;
- exact SHA-256 and byte length of allowlisted identity, SDK, Organization, and
  Private Hive authority files;
- every create-only successor file byte; and
- `network: false`.

Workspace content is not copied into the routing successor or printed into the
plan. The successor carries an inert source pointer with the source binding and
an instruction inventory (`rapp-work-sdk/1` §7) of the instruction files it
creates.

## Apply

```bash
rapp-work migrate \
  --source /absolute/path/legacy \
  --target /absolute/path/successor \
  --apply \
  --plan migration-plan.json \
  --plan-sha256 '<exact result.plan_sha256>'
```

Before its first write, apply verifies the plan hash, closed plan shape, source
and target arguments, current source filesystem identity, every bound source
authority byte, target absence, and qualified output bytes.

## Recovery

Staging is a sibling directory named from the exact plan hash. Its retained
`.rapp-work/migration-recovery.json` binds the source, target, plan, and source
binding. A rerun may resume only if that marker is exact. Foreign staging is
refused and left untouched.

## Receipt and completed replay

The target contains `.rapp-work/migration-receipt.json`. A replay against an
existing target performs all checks before any write:

1. receipt has the exact closed schema;
2. receipt plan/source/target binding matches;
3. target inventory commitment matches;
4. every inventoried regular file has the exact byte length and SHA-256; and
5. the source authority still matches the plan.

An exact replay returns `unchanged` with `effects: false`. Missing, tampered, or
foreign state is refused; it is never repaired automatically.

## Historical Private Hive migration

The older additive `.rapp-hive` migration remains available through:

```python
from rapp_work.compat import private_hive_prepare
legacy = private_hive_prepare()
```

That compatibility surface preserves its existing profile and fixtures. New
SDK migration does not duplicate or silently invoke it.

## Adopting the instruction inventory in place

A Workspace or Organization integrated before the instruction inventory
existed keeps its files and keeps verifying, with
`status: "verified-without-instruction-inventory"` and
`instruction_inventory: "absent"`; with `require_instruction_inventory`
(`--require-instruction-inventory`) it is refused with
`REFUSE_INSTRUCTION_INVENTORY_ABSENT`. One reviewed update adds the
inventory:

```bash
rapp-work update --root /absolute/path/workspace > update-plan.json
# review result.instruction_review: every instruction path and its SHA-256
rapp-work update --root /absolute/path/workspace \
  --apply --plan update-plan.json --plan-sha256 '<exact result.plan_sha256>'
```

The plan creates `.rapp-work/instructions.json` and replaces the SDK-owned
`.rapp-work/managed.json`; it never rewrites an instruction file. From then on
verification refuses an unreviewed instruction change, and the same reviewed
update is the only way to accept an edit, addition, or removal.

If `result.instruction_review.planned_inventory` is `absent`, the tree cannot
be inventoried as it stands (`scan_refusal` says why: for example a directory
link that leaves the tree, an unreadable directory, or a scan bound). The plan
then changes only what an SDK without the inventory would change, and the
workspace stays `verified-without-instruction-inventory` until the cause is
removed and a new plan is reviewed.

## Recovering an interrupted update

An interrupted update apply leaves `.rapp-work/update-recovery.json`, which
holds the plan being applied and its SHA-256. While it exists, a refused apply
of another plan names it (`REFUSE_RECOVERY_BINDING` with
`pending_plan_sha256`), and managed-file refusals name it as
`recovery_pending`. Resume by applying the same plan again; the CLI accepts the
marker itself as the plan file:

```bash
rapp-work update --root /absolute/path/workspace \
  --apply --plan /absolute/path/workspace/.rapp-work/update-recovery.json \
  --plan-sha256 '<plan_sha256 from the marker>'
```

The resumed apply completes only the reviewed writes. If an instruction file
changed during the interruption, the result is `updated-unverified` with the
drift in `verification_refusal`; plan and review a new update to accept it.
