"""KG grounding client + briefing integration (V2.x).

Public surface:

* :class:`KgClient` — thin async client around the sidecar's
  ``POST /query`` endpoint. Short timeout, graceful degradation.
* :class:`GroundingService` — adds an ``app_cache``-backed (region,
  mechanism) layer so identical queries within the TTL don't hit the
  sidecar twice.
* :func:`format_citations` — renders a :class:`GroundingResult` into
  a Markdown citation block to splice into the briefing.

The whole module is **advisory only**: every entry point returns an
empty result on any failure and the BriefingAgent treats an empty
result as "no citations" without altering numeric breakdown.
"""

from limen.agents.grounding.format import format_citations
from limen.agents.grounding.kg_client import KgClient
from limen.agents.grounding.service import GroundingService

__all__ = ["GroundingService", "KgClient", "format_citations"]
