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
plan. The successor carries an inert source pointer with the source binding.

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

## Pointer-only successors (proposal 0004, not accepted)

[Proposal 0004](proposals/0004-sdk-migration-successors.md) adds an explicit,
opt-in successor form for sources that the workspace successor cannot
represent: a Hive seeded from a repository (no `rappid.json`), or a source
whose world id is longer than the 64 characters that `rapp-work-sdk/1`
records allow. Without `successor`, `migrate` runs its 1.0.0 code and refuses
`hive` like any unknown input.

A source with its own Workspace or Organization `rappid.json` is described by
that identity:

```bash
rapp-work migrate \
  --source /absolute/path/legacy \
  --target /absolute/path/successor \
  --successor pointer-only \
  > pointer-plan.json
```

A source without `rappid.json` needs a closed, reviewed description:

```json
{
  "authority_channel": {
    "id": "origin",
    "kind": "github",
    "locator": "https://github.com/example-owner/example-hive"
  },
  "authority_paths": ["POLICY.md", "requests/example-member.json"],
  "hive_rappid": "rappid:@example-owner/example-hive:<64 lowercase hex>",
  "world_id": "example-world"
}
```

```bash
rapp-work migrate \
  --source /absolute/path/seeded-hive \
  --target /absolute/path/successor \
  --successor pointer-only \
  --hive hive-description.json \
  > pointer-plan.json

rapp-work migrate \
  --source /absolute/path/seeded-hive \
  --target /absolute/path/successor \
  --successor pointer-only \
  --apply \
  --plan pointer-plan.json \
  --plan-sha256 '<exact result.plan_sha256>'
```

Apply uses the reviewed plan, so `--hive` is refused with `--apply`, and
`--hive` without `--successor` is refused before the file is read.

The plan (`rapp-work-pointer-successor-plan/1`) binds the source path and
filesystem identity, the described or identity-file RAPPID and world, the
credential-free authority channel, and the exact SHA-256 and byte length of
every bound authority file: every path the description names and the
recognized control files that are present. For a checkout of a historical
Private Hive publication, naming `refs/current.json` is enough: when it is a
Private Hive current pointer, its Mother chain index and the Hive's genesis
declaration frame are bound too. A source that is, or is inside, a Git
directory is refused, a bound file inside a Git directory of any name below
the source is refused, and Git internals are never read. A target that is the
source, or lies inside it, under another spelling of its path is refused. The
successor contains exactly:

```text
.rapp-work/pointer-successor.json   # rapp-work-pointer-successor/1
.rapp-work/migration-receipt.json   # rapp-work-migration-receipt/1
.rapp-work/migration-recovery.json  # rapp-work-migration-recovery/1
```

No Hive state, key, history, frame, GODD, credential, prompt, or instruction
file is copied, no identity is minted or derived, and the source is never
written. The pointer records `execution: "never"`, `content_copied: false`,
and `grants_authority: false`. A described identity is corroborated against a
bound `rapp-hive/1` declaration, `hive.declaration` frame, Private Hive owner
anchor or Private Hive current pointer when one exists, but it is never
authenticated Hive authority.

The pointer's `source_world_id` accepts 1 to 128 assigned NFC characters
without control, format, separator or default-ignorable characters, the RAPP
Workspace/1 world length. That wider grammar exists only inside
`rapp-work-pointer-successor/1`, and a pointer-only successor has no identity
that could be registered in an Organization. Nothing else changes: the
workspace successor and `scaffold` keep their 64-character world ids, `update`,
`verify`, `status` and Organization pointers behave as in SDK 1.0.0, and
`rapp-hive/1` and canonical `rapp-work/1` payloads keep their 64-character
labels.

Plan-hash apply, the source-binding recheck before the first write and during
staging, recovery from an exact plan-bound marker, and the read-only completed
replay are the same as for the workspace successor.
