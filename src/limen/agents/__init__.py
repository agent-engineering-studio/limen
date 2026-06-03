"""MAF-shaped agents, executors and workflows for Limen.

The Microsoft ``agent-framework`` Python SDK API is still evolving; rather
than coupling Phase 4 to a moving target, this package ships a thin
**in-house runtime** under :mod:`limen.agents.workflow_runtime` that
mirrors MAF conventions:

* :class:`Executor` base class with a canonical async ``run`` method;
* an ``@handler`` decorator (currently a no-op marker, kept so swapping
  to real MAF requires no signature changes);
* a :class:`WorkflowBuilder` that wires sequential nodes with optional
  conditional edges (``enable_insitu`` gates the IoT branch);
* a vendor-agnostic :class:`ChatClient` Protocol with concrete factories
  per provider (Anthropic / OpenAI / Foundry / Ollama) plus a
  deterministic :class:`StubChatClient` used in tests.

The pure scoring engine from Phase 3 remains authoritative: the two
ChatAgents (RiskAnalyst + Briefing) only *reformulate* the numeric
breakdown — they never invent figures.
"""
