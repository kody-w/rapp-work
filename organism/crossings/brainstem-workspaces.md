---
from: brainstem
to: workspaces
what: Status, verify, discover, scaffold, update, migrate
authorized_by: "`plan_sha256`, applied explicitly"
home: "`rapp-work-sdk/1` §2"
health: specified for the SDK; the Brainstem integration is not built (G17)
arrow: both
label: SDK operations (not wired to the Brainstem yet, G17)
---
The RAPP Work SDK works on your private workspaces through six operations. The first three only read. The other three plan first, and apply only with the plan's exact hash. The SDK is built and specified, but no estate activates it yet, and the Brainstem does not call it: that is gap G17.
