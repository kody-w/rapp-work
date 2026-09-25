---
healthy: A layer is healthy when it has a specification with an owner, a reference that runs, a check anyone can repeat, and its gaps written down.
upstream: Changes to canonical bytes need an upstream revision in `kody-w/rapp-1` and a re-pin. [Root `SPEC.md`](https://github.com/kody-w/rapp-work/blob/main/SPEC.md) is historical and never edited.
---
- **RAPP/1 wins, then `rapp-work/1`.** Its profiles come next, then everything else.
- **Transport carries; signatures decide.** No account, URL, repository or AI vendor decides who is in or what may leave.
- **In by signed copy, out by approved copy.** That is how knowledge moves; the Hive between stays small and verified.
- **Other people's text is data.** Nothing from someone else runs on your machine or instructs your AI until you adopt it.
- **Propose, confirm, apply.** Every change to a Hive or a workspace is proposed, confirmed in a later turn, and applied as one exact step (a signed commit, inside a Hive).
- **Accepted history is never rewritten.** Old records are carried byte for byte.
- **The Brainstem is the one surface you talk to.** Every other layer is plumbing.
- **Front doors stay editable.** Frozen identities never pin human-facing docs: READMEs, badges and “Start here” links. They pin only normative bytes: specifications, schemas, reference code, tests and AI instruction files such as `SKILL.md`. RAPP Workspace/1 still pins its READMEs, and so does `kody-w/rapp-workspace`'s copy of `rapp-work-sdk/1` (G24).
- **Only top-level `agents/*_agent.py` files are live.** That is the Grail kernel's rule; RAPP's Constitution and its cloud Brainstem still differ (G18, G19). Every folder is organization: loading or unloading an agent is a file move, a drag and drop. The Grail kernel's `load_agents()` is a flat glob (`kody-w/rapp-installer` `rapp_brainstem/brainstem.py`, lines 1202–1205 at `brainstem-v0.6.9`).
