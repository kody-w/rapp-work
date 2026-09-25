# Brainstem integration (proposal 0017, not accepted)

`agents/rapp_work_agent.py` is one hot-loadable Brainstem agent, `RappWork`, that
lets a person reach their private RAPP Work workspaces by talking to their
Brainstem. It is a thin client of this repository's SDK: it calls only the six
public operations (`status`, `verify`, `discover`, `scaffold`, `update`,
`migrate`) and applies only a plan whose exact SHA-256 the person confirmed in a
later turn.

- Channel: the newest Brainstem channel (`brainstem-v0.6.16`), not the LTS
  `brainstem-v0.6.9` release scope. RAR tier: Frontier (`experimental`).
- Not part of the `rapp_work` package or wheel, and not live anywhere by
  accident: a Brainstem loads only the top level of its own `agents/` folder.
- Its `__manifest__` is RAR-ready (`rapp-agent/1.0`), so the identical bytes can
  be submitted through RAR's issue front door when the owner decides.

Design, refusals, tests and how to try it:
[`docs/proposals/0017-brainstem-sdk-agent.md`](../../docs/proposals/0017-brainstem-sdk-agent.md).
Tests: `tests/test_brainstem_agent.py` and `tests/test_brainstem_agent_isolation.py`.
