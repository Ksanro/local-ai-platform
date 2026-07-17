"""Context Planner.

Selects the retrieval strategy before context construction begins.
No AI or LLM inference is performed. Planning is entirely deterministic.

Architecture
------------

User Messages
    ↓
Intent Detection (intent.py)
    ↓
Rule Matching (rules.py)
    ↓
ContextPlan

The planner does NOT:
- access providers
- execute repository analysis
- parse source files
- modify RepositoryIndex
- modify ContextBuilder
- search RepositoryIndex
- resolve symbol names
- perform fuzzy matching

The planner only produces a ContextPlan.

Public API
----------

.. code-block:: python

    planner = ContextPlanner()
    plan = planner.build(
        user_messages=["Explain ProviderFactory"],
        repository_index=index,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.planning.intent import Intent
from packages.planning.plan import ContextPlan
from packages.planning.rules import RuleEngine

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex


class ContextPlanner:
    """Deterministic context planner.

    Detects intent from user messages, matches planning rules,
    and produces an immutable ContextPlan.

    The planner is stateless and deterministic. Same input always
    produces the same output.

    Attributes:
        _rule_engine: The rule engine used for rule matching.
    """

    def __init__(self, rule_engine: RuleEngine | None = None) -> None:
        """Initialize the planner.

        Args:
            rule_engine: Optional custom rule engine. Defaults to
                RuleEngine() with BUILTIN_RULES.
        """
        self._rule_engine = rule_engine if rule_engine is not None else RuleEngine()

    def build(
        self,
        user_messages: list[str],
        repository_index: RepositoryIndex | None = None,
    ) -> ContextPlan:
        """Build a ContextPlan from user messages.

        Detects intent from messages, matches against planning rules,
        and returns an immutable ContextPlan.

        The repository_index parameter is accepted for API compatibility
        but is not used. Planning is not retrieval.

        Args:
            user_messages: List of user message strings.
            repository_index: Optional RepositoryIndex (not used).

        Returns:
            An immutable ContextPlan.
        """
        # Detect intent from user messages.
        intent = Intent.detect(user_messages)

        # Match rule and build plan.
        plan = self._rule_engine.build_plan(intent)

        return plan
