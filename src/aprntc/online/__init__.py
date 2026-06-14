"""Online evaluation — shadow + canary (A2).

Turns "the child beats the parent on a held-out set" into "…on REAL live traffic":

- :class:`ShadowRunner` — on each live request, runs the child in parallel (output
  discarded; the user only ever sees the parent), judges child-vs-parent, and
  accumulates a live win-rate. Async + **fail-open**: shadow work never affects the
  user's response.
- :class:`CanaryController` — after promotion, routes a fraction of traffic to the
  new agent and watches a live metric; **auto-rolls-back** if it degrades.
"""

from aprntc.online.shadow import ShadowRunner, ShadowStats
from aprntc.online.canary import CanaryController, CanaryStatus

__all__ = ["ShadowRunner", "ShadowStats", "CanaryController", "CanaryStatus"]
