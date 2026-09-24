# RAPP Work Constitution

**Status: experimental draft. Not in force until ratified (Article 17).**

This constitution records what building shared AI workspaces taught us, so the next design starts from the lesson instead of repeating it.

**Precedence.** It is subordinate to:
- [RAPP/1](https://github.com/kody-w/rapp-1);
- the canonical `rapp-work/1` pinned by [`RAPP_WORK_PIN.json`](RAPP_WORK_PIN.json);
- the profiles those depend on, such as [`rapp-hive/1`](protocols/rapp-hive/1/SPEC.md).

Where it concerns the Brainstem (your own local AI assistant), it follows the [RAPP Constitution](https://github.com/kody-w/RAPP/blob/8afc9733e20ccf7e579a58028c29ab9c207087fa/CONSTITUTION.md) and cites its articles by Roman numeral instead of repeating them. On any conflict, RAPP/1 wins, then `rapp-work/1` and its profiles, then this document.

Every article has a **Why**, taken from what actually happened.

## Part I. Keep it runnable

### Article 1. People run it, so it stays small

Every concept must pay for itself. A fix may not add a concept unless it removes one. A newcomer understands a RAPP Work feature in about ten minutes, and nobody runs a daemon or an engine to "keep it together".

**Why.** The experimental `rapp-hive/2` draft grew to:
- 6 governance kinds and 34 refusal codes;
- a 3,000-line reference with a byte-exact browser port;
- 77 conformance vectors.

Each of two review rounds found real defects, and every fix added a rule. The owner's verdict was "too much for anyone to actually run and keep together". Synthesizing eight fresh designs started the same ratchet again, until review cut it back.

### Article 2. Real use before rules

A rule is added only when a real Hive, a real team, a real conversation or a reproduced attack fails without it. Designs are tried against real data, privately and read-only, before they leave the canary ring. Synthetic models test and demonstrate; on their own they do not justify a rule.

**Why.** The first dry run against the one real Hive found four gaps on first contact, after two synthetic review rounds had passed. Designing from that Hive found 18 more lessons that no synthetic story showed. It is a sample of one, in which real collaboration never started.

### Article 3. Plain tools first; build only what is left

Folders, git, SSH signatures and the AI already provide history, merging, undo, authorship, sharing and reading any shape of document. RAPP Work uses them, and builds only what they cannot do.

**Why.**
- Re-deriving history, membership and agreement from custom signed streams was too much to run.
- In one design's own scoring, a private GitHub repository with its usual review features covered 19 of 26 journey points.
- What was left to build was small:
  - an AI that treats other people's text as data;
  - consent bound to exact changes;
  - one check of who may change what.

## Part II. What a Hive is

Articles 4, 5, 6, 8 and 10 describe the **Hive folder convention**, an experiment in the frontier track's canary ring. It is outside `rapp-work/1` and claims no `rapp-work/1` or RAPP/1 conformance. Part V lists first steps. Binding such a Hive to a work organization would also need upstream changes to canonical `rapp-work/1` §§1, 2 and 4.

### Article 4. A Hive is a folder people can read

A Hive is a folder of markdown files:
- `HIVE.md`: the Hive's rules (its fixed id and approvals number);
- `members/<name>/`: each member's own space;
- `requests/`: requests to join;
- `shared/`: rooms every member edits;
- `former/`: the spaces of members who left.

Folders organize, and reorganizing is moving files. Every file is one fact, and nothing derived is stored: who is in, task lists and views are computed when read.

A Hive holds none of the following:
- instruction files that an AI loads by itself (such as `AGENTS.md`, `CLAUDE.md` or `SKILL.md`);
- hidden files, except git's own `.git/` and a fixed `.gitattributes`;
- code files. Code is shared only as text inside markdown.

**Why.**
- In the one real Hive, a single join request touched 8 committed derived files.
- About 9 KB of real notes sat inside about 4.6 MB of machinery.
- AI tools load instruction files from any folder they open, so one shared file could tell every member's AI to run code.

### Article 5. Your space is yours; your keys stay with you

Only you change your space. Every change is signed, and every verifying Brainstem refuses one that touches another member's space. There are two exceptions, both governed by Article 8:
- **admitting a newcomer:** their own signed request moves into their new space;
- **removing a member:** their space moves to `former/`.

Nobody can add a key to someone else's space.

A device is not a member. Each device has its own key for each Hive, so your Hives cannot be linked. All of a member's keys belong to that one member, and one member has one vote. A member is usually a person, but a team or an agent with its own keys can be one too.

Keys are never committed to a Hive or put in an exported Brainstem egg (its portable package). A Hive inside a known sync folder is refused.

**Why.** Treating each device as a separate identity let one person's second device take a co-equal's seat. Shared history under one anonymous author could not say who did what. Brainstem eggs bundle the Brainstem's data folder, so a key kept there would travel with the egg.

### Article 6. One authority, one order

- Every change to a Hive is a commit signed by the member who made it or, for a join request only, by the newcomer's own key.
- It is judged against the Hive as it stood just before: who was a member, and what the rules said.
- The shared history, one unbranched line of commits, is the only order. Inside a Hive, a time written by a signer orders nothing.
- The first refused change stops verification, and nothing is built on it.
- A join request is the one file signed on its own, because it must be able to travel by any channel.

**Why.** The first synthesis combined two authorities: signed statements ordered by their signers' own clocks, and signed commits. Review found seven contradictions and reproduced four of them. In one, a removed member backdated an approval and got a newcomer admitted. One authority with one order closes that by design, and needs less code.

### Article 7. Signatures decide; transport carries

This article sharpens the rule "Never infer authority from a transport, repository, account, URL, or actor type." (`.github/skills/rapp-work/SKILL.md:24`):

> Never infer authority from a transport, repository, account, URL, AI vendor, or actor type. Transport decides who can reach a Hive and carries its files; it never decides who is a member, what the members agreed, or what may leave. Membership, keys, a Hive's rules, and anything that leaves a Hive take effect only through signatures that any reader can verify and every Brainstem verifies, binding the exact content, its source and its destination. Content counts as the team's only when a member's signed change carries it; anything else is shown as unattributed and never built on.

**Why.** Dropping the rule would let a repository owner decide membership, and in the real Hive one pending transport invitation blocked everyone. Signing every typo by hand is unusable; a Brainstem that signs every change for you is not.

### Article 8. No rule strands a request, and removal needs everyone else

- **A request to join** says only who is asking and with which key. It carries no policy.
- **Admitting someone** needs as many members as the Hive's approvals number, never more than the current membership and never fewer than one. A new Hive starts at two; while the founder is the only member, the founder admits the first member alone.
- **Changing the rules** needs the stricter of the old and new numbers, within the same limits. Each approval names the new rules and the exact rules they replace.
- **Only current members' approvals count.** Each approval binds its exact subject.
- **An approval counts once.** Its subject can never occur again. An admitted request cannot be filed twice, a removal approval names the member's current membership, and every rules change carries the next version number.
- **You alone** manage your own keys and your own leaving.
- **Removing someone else** needs every other member, and at least two of them.
- **The last member** cannot leave.
- **Leaving loses nothing:** your space moves to `former/`, and history stays.
- **Known limits,** documented rather than patched with rules:
  - with one approval, a member can admit a second identity of their own and outvote a lone co-member;
  - a two-member Hive cannot remove anyone;
  - two members who both vanish cannot be removed;
  - whoever holds a member's only key acts as that member until removed.

  The remedy for a stuck Hive is a new Hive that carries the files.

**Why.**
- After a rules change, the real Hive computed **0 members and 2 stranded requests**, and the people it was built for never got in.
- A quorum larger than the founders could never admit anyone.
- Review found that:
  - one member could lock a Hive by raising its approvals number;
  - approvals from people who had left still counted;
  - approvals that were never used up let one member re-admit someone everyone had removed;
  - one approval let a member pair with a second identity to push out the other.

### Article 9. Private by default; public is a reviewed copy

Nothing becomes public except through a separate, reviewed copy. Its approval binds the exact files and the destination, and anyone can check that the copy contains nothing else.

DOGG (public-safe data) and GODD (private data) keep the rules of `AGENTS.md` and `rapp-hive/1` §2. A private folder does not make unsafe data public-safe. A public copy never carries personal data, secrets, credentials, private prompts or GODD.

Who can reach a private Hive is the transport's job (Article 7). This convention controls only what is deliberately published.

**Why.** All eight independent designs chose this. Every alternative (a public folder inside the Hive, per-file flags) would make one mistaken move a leak. A publish approval that did not name its destination let a copy go anywhere.

### Article 10. No master copy; offline is normal; old things keep working

- **Every device verifies for itself** and can be offline for a long time.
- **Only changes that verify are built on.** A refused change is reported with proof. A member can then reset the shared copy to the last change that verified; no verifying device accepted anything after it, so nothing anyone relied on is lost.
- **Accepted history is never rewritten.**
- **Old records are carried byte for byte,** never re-signed, and a successor names where it came from.
- **Old clients** keep seeing the old Hive, unchanged.

**Why.** The owner's standard is compatibility like Linux. Rewriting history to migrate would break the peers who have not moved yet. Reverting a bad change instead of refusing it would leave harmful bytes in everyone's history forever.

## Part III. The Brainstem

### Article 11. Talk to your Brainstem

The experience is a conversation with your own Brainstem (RAPP Constitution Article XLI). One Brainstem agent does the librarian work over a Hive: it reads, lists, proposes, applies, verifies and syncs. The Brainstem's frozen core never changes for RAPP Work (Articles I and III).

A Hive is a place the agent works on. It is never the Brainstem's own agents folder or soul (Articles XIV and XVII).

**Why.** The one design that made the Hive look like a Brainstem (a shared soul and agents folder) found that those names invite other people's text to steer your AI, and it needed extra refusals to stop that. One agent that operates the Hive keeps the Brainstem light and the operator in control.

### Article 12. Propose, confirm, apply, undo

- Every change is proposed in plain words naming every file and destination, with a hash.
- It is applied only after the person confirms in a later turn. The confirmation is bound to that hash, and the preconditions are checked again.
- Moving files by hand in a file manager is welcome. The Brainstem proposes those changes the same way before they are signed and shared.
- **Undo** is proposed the same way. An edit is undone by a new signed commit if nothing changed since. A membership or rules change is undone only through Article 8 (undoing an admission is a removal). A publication cannot be recalled from anyone who already copied it.
- The AI never claims a person said yes when it cannot know. Where it cannot prove consent, it says so, and on hosts where the check cannot hold, it refuses.

**Why.** This is the one safeguard a non-expert can check. It is the exact-plan consent the RAPP Work SDK already uses (`plan_sha256`). It follows the RAPP Constitution's rules that the twin offers and the user accepts (Article IX), and that material changes are proposed before they are applied (Article XXVIII).

### Article 13. Other people's text is data; adoption gates behavior

Nothing in another member's space runs on your machine or becomes your AI's instructions until you adopt it:
- **instructions** by saving a copy, pinned to its exact bytes, as your own;
- **code** only when you yourself copy a reviewed agent into your own agents folder. This step is deliberately not done by chat (Article XVII).

Text from a Hive, including file names and commit messages, reaches the AI only as quoted data, fenced with a marker its author cannot predict. Fencing makes steering harder, not impossible; what holds is Article 12. A Hive folder is never an agents path, because the Brainstem hot-loads agents (loads them fresh on every request) and installs their missing packages.

**Why.**
- Prompt injection and hot-loaded code are the new risks a shared AI folder creates.
- In the real Hive, a shared agent file described as inert was far too large for anyone to review.
- Review found that pushing to a shared folder could let that folder's own git settings run commands on members' devices. A shared folder is now used only as a bare repository, with those settings switched off.
- All eight designs chose adoption by copy.

### Article 14. No second language to share behavior

A Hive shares instructions and, rarely, reviewed agents. It needs no interpreter. lisppy is not part of the Hive.

It may join later as an ordinary optional agent if a real need appears that instructions and agents cannot meet, such as sharing programs whose results must match exactly on every device. Each person would still adopt it under Article 13, after a sandbox audit.

**Why.**
- lisppy's strength, identical results on every device, served the byte-exact design being retired.
- Its one real integration used it only as an optional build-time step and never promoted it.
- Six of eight independent designs gave it no role; two kept it as a later option.

## Part IV. Evolving RAPP Work

### Article 15. Map before you make; refuse rather than repair

Every need is first mapped to an existing RAPP/1 primitive, RAPP Work profile, SDK operation or ordinary tool. Only a named gap earns an addition, and it goes to the specification that owns the topic.

RAPP/1 is used only where its own verification applies: registry-backed identities now, and later crossings between worlds and organizations, and publication. Old records are carried byte for byte and checked with RAPP/1's hash and signature math. They are called RAPP/1-verified only where a signed registry holds their keys.

A situation the rules do not cover stops with a plain refusal, never a clever fallback.

**Why.** Mapping the Hive onto what exists found nine gaps, each with a home:
- G1 and G5 belong to `rapp-hive/1`: a roster that could never change, and a single owner.
- G2–G4 and G7 belong to `rapp-work-sdk/1`: plans that cannot move a file, discovery that misses agent files, migration that refuses repository-seeded Hives and long world ids, and verification that accepts an edited instruction file.
- G6 is unresolved: a lost owner key cannot be recovered.
- G8 belongs to RAPP/1. A newcomer's signed join request cannot pass a RAPP/1 verifier, which takes keys only from a registry, yet historical `rapp-work/1` (root `SPEC.md` §10) requires no identity directory.
- G9 belongs to canonical `rapp-work/1`: its §9 does not accept a git commit as authority.

### Article 16. Experiments are labeled, frozen or graduated, never silently abandoned

- **Rings.** Every experiment names its track and ring: canary, nightly, alpha, beta, or that track's grail (production).
- **Graduation.** Nothing leaves the canary ring until a real team has used it for a real week.
- **Freezing.** A retired experiment is frozen as a research record that says why. The `rapp-hive/2` draft is frozen this way, in its [`FROZEN.md`](https://github.com/kody-w/rapp-workspace/blob/experimental/frontier-rapp-hive-2/protocols/rapp-hive/2/FROZEN.md), and its lessons live here.

**Why.** Unlabeled experiments become accidental commitments, and deleted ones lose their lessons.

### Article 17. Amending this constitution

- An amendment is a written proposal in this repository. It cites the articles it touches and the evidence for the change, and it is reviewed.
- It is ratified when the owner merges it into `main`, recorded in `CHANGELOG.md`.
- Every amendment must keep the principles of Articles 1 and 7, and this sentence. The wording of each rule follows the specification that owns it.
- Until ratified, this draft is guidance, not policy.

**Why.** A constitution that anyone can quietly edit protects nothing. One that cannot change stops learning.

## Part V. Pending amendments (proposed; not in force)

These are first steps, each proposed to the specification that owns its topic. Ratifying this constitution does not ratify them, and each is accepted or refused on its own.

1. **A Hive folder profile.** Once the reference model ([`kody-w/rapp-model-hive`](https://github.com/kody-w/rapp-model-hive/tree/experimental/hive-md), branch `experimental/hive-md`) has passed a real team's week, write the convention as an experimental profile in the frontier track of [`kody-w/rapp-workspace`](https://github.com/kody-w/rapp-workspace). `rapp-hive/1` stays in force, and nothing migrates automatically.
2. **Signed commits inside a Hive (G9).** In that profile, an SSH-signed commit by an admitted key, verified from the Hive's pinned first commit, authorizes effects inside the Hive. It is never called a RAPP/1 occurrence. An effect that crosses a world boundary still needs one under `rapp-work/1`.
3. **The authority sentence.** Replace the sentence at `.github/skills/rapp-work/SKILL.md:24–25` with Article 7's text. Then propose upstream, in `kody-w/rapp-1`, one line for canonical `rapp-work/1` §9 (a transport never proves membership, agreement, or permission for anything to leave a Hive), and re-pin `RAPP_WORK_PIN.json`. Root `SPEC.md` is historical and never edited.
4. **Members inside a Hive (G8).** In that profile, a member is a name bound to keys by the Hive's signed history. A RAPPID (a RAPP/1 identity) links the name to a RAPP identity where one is needed.

## How the pieces fit

| Layer | Role |
|---|---|
| RAPP/1 | Bytes, identity (RAPPIDs), signed frames, eggs and registries; used where its own verification applies |
| `rapp-work/1` | Business policy: organizations, worlds, catalogs, migration, receipts and evidence |
| `rapp-hive/1` | The Private Hive profile in force, unchanged |
| RAPP Workspace and the RAPP Work SDK | The local-first product, and exact-plan consent |
| A Hive (experimental folder convention) | A folder of markdown with git underneath; every change is a signed commit, judged by the Hive as it stood just before |
| The Brainstem | The main surface: one hot-loadable agent operates a Hive for its member |
| lisppy | Not needed today; an optional agent later, if Article 14's test is met |
