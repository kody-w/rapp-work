# Private Hive: single-owner deployment MVP

This is an executable, bounded deployment profile, not a promise that every
capability described by `rapp-hive/1` is deployed. It signs and publishes
explicitly approved DOGG/neutral files into an access-restricted artifact
store. An independent client verifies the entire publication before copying
any file into its own managed generation. **Nothing downloaded is executed.**

## Supported boundary

| Capability | Implemented behavior |
|---|---|
| Owner custody | Explicit Ed25519 creation/load; private directory 0700, PKCS8 PEM and identity record 0600; no symlinks, hardlinks, implicit creation, replacement, or remint |
| Workspace migration | Existing preparation CLI; all original files, workspace/Hive/dimension RAPPIDs, baselines and migration receipts remain local and unchanged |
| Authority | Self-signed out-of-band owner anchor; signed direct-owner `rapp/1-registry`; exact vendored Hive SPEC SHA-256, all eight body kinds, owner SPKI, exact stream genesis entries |
| Convergence | Authenticated owner declaration and one linear owner dimension; native Hive convergence evaluation; immutable catalogs/manifests; one signed projection stream per configured channel |
| Approval | Frozen local plan, SHA-256 approval and owner signature over that exact plan; publishing reads frozen bytes, not live workspace files |
| Filesystem | Private POSIX store, immutable same-byte puts, file/directory fsync, atomic replacement of `refs/current.json` under flock/CAS |
| Private Git | Existing private GitHub.com repository; pinned repository/owner/actor IDs; fresh API evidence; isolated bare Git plumbing; explicit expected old ref; force-with-lease CAS |
| Independent client | Separately supplied anchor and compared fingerprint; monotonic registry, Mother, release and per-channel projection checks; exact artifact verification; local SQLite cache; managed data generations |
| Recovery | Immutable artifacts may precede pointer publication; durable Git commit intent; retry after lost acknowledgements; client artifacts/checkpoints commit together; partial materialization resumes only from matching bytes |

**Refused before effects:** SharePoint, public Git, federation activation,
GODD sealing, key release, owner/key rotation, membership/topology changes,
reconciliation/multi-writer conflict activation, unrecognized object types,
unmanaged overwrites, and unsupported authority succession. Windows is not a
supported deployment host. Preparation remains a separate, more portable layer.

## Install and inspect

Use Python 3.10+ and Git. Install dependencies explicitly; the CLI never
installs packages or launches a service:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/deploy_hive.py --preflight
python3 scripts/deploy_hive.py --help
```

Every deployment command verifies the complete checksum lock **before importing
deployment code**. `--preflight` checks integrity; it is not an owner approval,
transport reachability check, or proof of remote privacy.

All paths below are operator-supplied examples. There are no default personal
paths, repository names, credentials, network gateways, or anchors. Use
disjoint workspace, custody, publisher, staging, channel, and client locations.
The parent of each new private location must already exist.

## 1. Explicit owner key; then migration/preparation

Create a new owner only when you intentionally have no existing owner key:

```bash
python3 scripts/deploy_hive.py key create \
  --key-dir /path/to/owner-custody --owner-label example-owner --slug owner
```

Record the printed **owner RAPPID and SPKI SHA-256** independently. The key
directory must not exist. Repeating `create`, missing key material in an
existing directory, permissive modes, ambiguous custody, and symlink/hardlink
substitutions all refuse. Loading never falls back to creating:

```bash
python3 scripts/deploy_hive.py key load \
  --key-dir /path/to/owner-custody --expected-rappid '<existing keyed owner RAPPID>'

python3 scripts/prepare_workspace.py migrate \
  --workspace /path/to/workspace \
  --member-rappid '<existing keyed owner RAPPID>' \
  --hive-name example-hive --world-id example-world
```

Back up custody using your own protected recovery mechanism. This MVP stores
unencrypted PKCS8 behind POSIX custody; it does not claim hardware-backed key
protection. A crash leaving incomplete custody refuses automatic repair, and
missing state is not authorization to invent a new identity.

Already prepared with a keyless placeholder member? Keep the existing
workspace/Hive/dimension identities and controls. During the **first unsigned
preparation-to-authority binding only**, explicitly supply
`--adopt-prepared-owner '<exact prepared member RAPPID>'` to `authority init`.
The signed declaration binds the loaded keyed owner; it does not rewrite the
preparation sidecar. This is not an owner-rotation mechanism.

## 2. Select and privately stage

Use `trust-scanner`, `select`, and `stage` from [SKILL.md](SKILL.md).
**Both DOGG and neutral plaintext require signed PII-clearance evidence.**
Scanner identity/SPKI must have been explicitly trusted by the prepared
workspace. The deployment does not generate a fabricated scanner attestation
or pretend that owner approval itself detects PII.

```bash
python3 scripts/prepare_workspace.py stage \
  --workspace /path/to/workspace --outbox /path/to/private-outbox
```

Use the returned `outbox` value (the derived `hive-…` directory) as
`--stage-root`, not its parent. Building checks the complete stage commitment,
selection generation, prepared identities/topology, source bytes and staged
copies. Stale or modified safe selections refuse.

The preparation manifest contains **local-only** pending-seal metadata.
Never copy that outbox to a channel. The publisher reads it locally, excludes
every sealed selection, and reconstructs its publication from a closed
allowlist. Pending paths, path hashes, content hashes, contents, controls,
baselines, migration receipts and private keys never enter that allowlist.
Only the **count** of excluded selections appears in the local review plan.

## 3. Declare immutable channel topology and initialize authority

Create a JSON configuration matching
[`schemas/deployment.schema.json`](schemas/deployment.schema.json).
For a private filesystem:

```json
{
  "schema": "rapp-private-hive-channels/1",
  "channels": [
    {
      "id": "primary",
      "kind": "filesystem",
      "role": "authority",
      "path": "/path/to/private-publication"
    }
  ]
}
```

One channel must be `authority`; up to seven others may be `mirror`. The
signed filesystem locator is the generic `private-filesystem:<channel-id>`,
not the local mount path. GitHub locators are the explicitly configured
repository URL. There is no automatic public channel.

```bash
python3 scripts/deploy_hive.py authority init \
  --workspace /path/to/workspace --publisher-dir /path/to/publisher \
  --key-dir /path/to/owner-custody --channels /path/to/channels.json

python3 scripts/deploy_hive.py authority anchor \
  --publisher-dir /path/to/publisher --out /path/to/out-of-band-anchor.json
```

Initialization signs and persists local bootstrap authority. It does not
publish. Repeating it with exactly the same configuration returns the existing
anchor; changing the key, members, room policy, or channels does not silently
create a replacement. The owner anchor commits the initial registry and
Mother genesis. Its self-signature proves key possession, **not provenance**:
its provenance comes from independent delivery and fingerprint comparison.

The initial registry includes genesis for the preserved Mother and dimension
identities and for each once-bound projection stream. Projection genesis is
explicitly `stale`, never a false success receipt. File object identities are
deterministic keyed aliases; no existing workspace identity is reminted.

### Existing authority

Never bootstrap over a known authority. Recognized workspace registry/anchor
locations and existing filesystem channel authority are rejected even when
incomplete or unauthenticated. Supply the
existing owner custody, independently supplied anchor, and a complete
previous publication:

```bash
python3 scripts/deploy_hive.py authority import \
  --workspace /path/to/workspace --publisher-dir /path/to/new-local-state \
  --key-dir /path/to/existing-owner-custody --channels /path/to/channels.json \
  --source /path/to/existing-private-publication \
  --anchor /path/to/independently-supplied-anchor.json \
  --expected-spki-sha256 '<independently compared fingerprint>'
```

To import directly from a configured private GitHub channel, replace
`--source …` with `--source-channel-id <id> --read-state-dir /path/to/private-git-read-cache`.
This path uses the same pinned repository/actor/privacy gates as publishing,
supports the explicit `--github-evidence` option, reads a fixed commit
snapshot, and performs no push.

Import verifies the complete signed history and object closure before creating
publisher state, preserves the anchor/genesis/history, and requires the
existing prepared identities and topology. A loose `registry.json`, a different
key, or a partial set of chains is not sufficient. The library additionally
accepts an already authenticated `VerifiedBundle` from either adapter; it
never accepts caller-provided “verified” summaries instead of artifact bytes.

## 4. Freeze, review, approve, publish

```bash
python3 scripts/deploy_hive.py release build \
  --publisher-dir /path/to/publisher --key-dir /path/to/owner-custody \
  --stage-root /path/to/private-outbox/hive-<derived-id>

python3 scripts/deploy_hive.py release show \
  --publisher-dir /path/to/publisher --plan-hash '<exact printed plan hash>'

python3 scripts/deploy_hive.py release approve \
  --publisher-dir /path/to/publisher --key-dir /path/to/owner-custody \
  --plan-hash '<exact reviewed plan hash>'

python3 scripts/deploy_hive.py release publish \
  --publisher-dir /path/to/publisher --key-dir /path/to/owner-custody \
  --plan-hash '<exact approved plan hash>'

python3 scripts/deploy_hive.py release status --publisher-dir /path/to/publisher
```

Review `approved_files`, data classes, hashes, counts, channels, expected base,
and all artifact commitments. Approval is bound to the whole immutable plan,
not a yes/no environment variable. A changed plan or frozen byte refuses.
Changing workspace files after approval does not change what that approval
publishes. Restage/rebuild for a new release.

The exact Hive profile requires a non-empty convergence candidate array. An
empty file release therefore converges an owner-signed, generated **empty
inventory marker**. The marker is unambiguous application metadata, has no
private source information, and is never materialized as a user file.
Ordinary releases contain approved file candidates plus a final inventory
marker, evaluated by the same authenticated Hive acceptance gate.

Only one unfinished release is allowed per publisher state. To abandon a plan
that has never been approved:

```bash
python3 scripts/deploy_hive.py release discard \
  --publisher-dir /path/to/publisher --plan-hash '<unapproved plan hash>'
```

Discard retains its local immutable bytes. Approved or published releases
cannot be discarded. No command deletes original workspace data.

### Filesystem requirements

The adapter requires an owner-only, 0700 directory and 0600 regular files.
It rejects symlinks, hardlinks, unmanaged root entries, collisions and stale
current pointers. Only an identical existing immutable value is idempotent.
`refs/current.json` is the **linearization point**, replaced only after all
approved immutable artifacts have been written, fsynced and read back.

Use a local POSIX filesystem or an operator-validated mounted filesystem that
actually supports coherent flock, atomic link/rename and fsync semantics.
POSIX mode checks are not a claim about NAS ACLs, LAN gateway authorization,
tenant configuration or remote mount correctness. No HTTP server is started.

### Private GitHub

Use an existing private GitHub.com repository; the tool does not create a
repository, change visibility, grant collaborators, or use workspace Git.

```json
{
  "schema": "rapp-private-hive-channels/1",
  "channels": [
    {
      "id": "private-github",
      "kind": "github",
      "role": "authority",
      "repository": "example-owner/example-private-hive",
      "repository_id": 12345,
      "owner_id": 67890,
      "actor_id": 24680,
      "actor_login": "example-actor",
      "ref": "refs/heads/hive"
    }
  ]
}
```

**The IDs above are fictional placeholders, not defaults.** Obtain and
independently confirm your real immutable repository, owner and actor IDs.
Authenticate the `gh` CLI separately. The adapter retrieves
`gh api repos/<owner>/<repository>` and `gh api user`, checks exact identities,
`private:true`, `visibility:"private"`, `fork:false`, `archived:false` and
`disabled:false`, then checks again immediately before push. Evidence must be
at most five minutes old and no more than thirty seconds in the future.

Every Git build requires an explicit expected ref per Git channel:

```bash
python3 scripts/deploy_hive.py release build \
  --publisher-dir /path/to/publisher --key-dir /path/to/owner-custody \
  --stage-root /path/to/private-outbox/hive-<derived-id> \
  --expected-ref 'private-github=absent'
```

For a successor, replace `absent` with the exact 40-hex old commit OID.
Publishing uses isolated bare repositories, shallow Git commit fetches
(complete signed RAPP history remains in the bundle), explicit trees and parent
commits, scrubbed inherited Git configuration, disabled hooks/automatic maintenance, no checkout/filter/
submodule execution, HTTPS transport, and
`--force-with-lease=<ref>:<expected-old-oid>`. It never stages, commits, resets
or pushes the workspace repository. Credentials come from `gh`, are passed
only in the Git child environment, and are not put in URLs, arguments, config
files, plans, logs, or artifacts.

For explicit operator evidence injection, pass `--github-evidence <file>` to
`release publish` or `client pull`. The closed evidence document is:

```json
{
  "schema": "rapp-private-hive-github-evidence/1",
  "checked_utc": "<fresh RAPP/1 UTC timestamp>",
  "repository": {
    "id": 12345, "full_name": "example-owner/example-private-hive",
    "owner_id": 67890, "private": true, "visibility": "private",
    "fork": false, "archived": false, "disabled": false
  },
  "actor": {"id": 24680, "login": "example-actor"}
}
```

This flag is a deliberate **trusted operator-supplied API snapshot**, not a
cryptographically signed GitHub attestation. It is checked twice and must
remain fresh; `gh` still supplies real transport credentials. The default
queries live evidence twice. Unit tests instead inject a provider and an
explicit local bare-repository transport; the CLI has no local-transport
bypass for GitHub privacy gates.

Git visibility and ref CAS are not one server transaction. The MVP cannot
prevent an authorized administrator changing visibility immediately after the
last check or undo copies already read by collaborators. It never promises
continuous confidentiality or organization-policy enforcement beyond the
observed evidence and server authorization.

## 5. Independent anchor-pinned client

Install a separate copy of the skill. Do **not** copy publisher SQLite state,
private custody, the preparation controls, or a cached trusted summary.
Deliver the anchor independently of the channel and compare its fingerprint:

```bash
python3 scripts/deploy_hive.py client init \
  --client-dir /path/to/client \
  --anchor /path/to/independently-supplied-anchor.json \
  --expected-spki-sha256 '<independently compared owner fingerprint>'

python3 scripts/deploy_hive.py client pull \
  --client-dir /path/to/client --channels /path/to/client-channels.json \
  --channel-id primary

python3 scripts/deploy_hive.py client verify --client-dir /path/to/client

python3 scripts/deploy_hive.py client materialize \
  --client-dir /path/to/client --destination /path/to/new-managed-output

python3 scripts/deploy_hive.py client verify \
  --client-dir /path/to/client --destination /path/to/new-managed-output
```

Client transport configuration is explicit and must match a signed channel
declaration. A filesystem client may mount the same store at a different
local path. The client verifies the registry against the independent owner
anchor, every complete registered-genesis chain, Mother convergence,
per-channel receipt, manifest, catalog, base64 file, PII receipt and exact
byte inventory. It rejects missing/extraneous artifacts, unsafe paths,
unrecognized objects, forks, rollback, same-sequence equivocation and
topology/key/genesis changes. Registry sequence-only renewals may be verified
only when the initial anchored registry is retained and all authority entries
are unchanged; this CLI does not issue renewals.

Downloaded files are bounded, inert data. PII receipts are verified at their
signed publication time; old approved data does not spontaneously fail simply
because the client fetched it more than a day later. The owner's signed
object endorses the exact scanner evidence selected at preparation; the
client does not treat an arbitrary self-signed scanner receipt as authority.

Pull stores artifacts and monotonic checkpoints in **one local SQLite
transaction**. Materialization then builds
`<destination>/generations/<pointer-sha256>/rooms/...`, verifies it, and
atomically updates the destination's `current.json`. The returned generation
path is the actual data view; no executable symlink, auto-install, import,
agent activation, `eval`, shell execution, or dependency setup occurs.
Unmanaged destinations and modifications inside an existing generation
refuse instead of being overwritten.

Unselecting a file removes it from the **next current managed view**, not from
previous immutable releases, Git history, old client generations, or the
source workspace. Treat publication as durable disclosure to the authorized
audience. A formerly published file cannot be made secret by reclassifying it
as GODD.

## Publication layout and limits

```text
objects/particle/<hash>.json       # file/inventory/catalog/signed-registry particles
objects/wave/<hash>.json           # exact signed RAPP/1 frames
objects/egg-manifest/              # reserved; this MVP emits/accepts no eggs
manifests/<hash>.json              # native Hive artifact manifests
manifests/releases/<hash>.json     # deterministic complete byte inventories
chains/<tip-frame-hash>.json       # complete immutable chain indexes
receipts/<channel>/<hash>.json     # signed projection frames
receipts/pii/<hash>.json           # exact signed approved scanner evidence
registry-history/<seq>-<hash>.json # signed monotonic registry history
refs/current.json                 # signed atomic publication pointer
```

The artifact store is a projection, not a new wire API. The exact vendored
RAPP/1 frame envelope remains eleven keys. File particles use the closed
`rapp-private-hive-file/1` schema with explicit base64, byte count, SHA-256 and
signed PII receipt. The RAPP/1 canonical-artifact limit is **1 MiB**; base64
expansion and metadata mean the honest raw-file cap is **700 KiB**, not a false
claim that a full 1 MiB file fits into one 1 MiB particle. Larger files refuse
without truncation, chunk invention, source mutation or loss.

Other bounds: 256 current files, eight channels, 4,096 frames per chain, 8,192
artifacts and 64 MiB total per bundle. Each canonical plan/index/frame also
must fit the parent 1 MiB limit; that may bind before the count limits.
Retention is append-only, so a growing estate eventually requires a separately
designed migration, not silent history pruning. Local SQLite publisher/client
stores retain history and may grow substantially.

## Recovery and limitations

- An immutable-write failure leaves the previous pointer current. Verified
  unreachable artifacts are safe to reuse; no publication success is claimed.
- A crash after a filesystem CAS retries against the exact desired pointer
  and verifies every artifact. A Git retry uses the persisted exact commit
  intent; a different ref is not interpreted as acknowledgement.
- A release is signed before transport, but a signed projection is not by
  itself proof that every mirror succeeded. Local publication receipts are
  recorded only after read-back. Multi-channel publication is **not globally
  atomic**: authority publishes first, mirrors follow. An unfinished approved
  release must finish before a successor can be built.
- A client crash before SQLite commit advances neither artifacts nor pins.
  A materialization crash can leave a named partial generation; matching bytes
  resume, mismatches refuse. The current data view changes only after complete
  verification. Old generations and source files are retained.
- Monotonic state prevents rollback relative to what this client has already
  accepted. It is not a live freshness oracle and cannot detect a server
  withholding unseen releases. Protect and back up client state; resetting it
  weakens that memory. There is no automated owner recovery or re-anchor.
- No broad RAPP repository conformance, federation, remote ACL correctness,
  PII-scanner quality, key release, automatic GitHub policy, or unattended
  publication claim is made by this MVP.

## Fictional verification suite

Install test requirements explicitly, then run from the repository root:

```bash
python3 -m pip install -r .github/skills/rapp-private-hive/requirements-test.txt
mkdir -p .hive-test-work
chmod 700 .hive-test-work
TMPDIR="$PWD/.hive-test-work" PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s .github/skills/rapp-private-hive/tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 \
  python3 .github/skills/rapp-private-hive/vendor/hive/reference/authenticated_conformance.py
```

The suite includes the existing 22 preparation tests; deployment key custody,
authority, filesystem, Git privacy/CAS/isolation, client, crash, bounded-file,
no-data-loss/no-GODD-leakage, exact vendoring and schema tests; independent CLI
processes consuming a migrated workspace with only an out-of-band anchor; and
the exact vendored authenticated Hive vectors. Git tests use only local,
fictional bare repositories, never an actual GitHub push.

Test work stays under `.hive-test-work` in the project and individual cases
clean themselves up. Checksum updates are a maintainer action after source,
documentation, schemas and tests stabilize; never regenerate a lock to
“repair” an untrusted installed skill.
