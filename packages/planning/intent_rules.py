"""Engineering intent resolution rules.

Deterministic rules that map user query patterns to engineering
sub-intents (retrieval profiles). These rules produce **retrieval
hints** that improve repository retrieval quality before ranking
begins.

Architecture
------------

User Messages
       |
       v
IntentRuleEngine.resolve(query_text, intent)
       |
       v
ContextPlan retrieval hints

No LLM. No ML. No embeddings. Fully deterministic.

Engineering Retrieval Profiles
-------------------------------

| Profile              | Description                      |
|----------------------|----------------------------------|
| IMPLEMENTATION       | Locate concrete implementation   |
| INTERFACE            | Locate interface/abstract def.   |
| REGISTRY             | Find registration/registry       |
| ENTRY_POINT          | Find application entry point     |
| EXECUTION_FLOW       | Trace execution flow             |
| CONFIGURATION        | Find configuration logic         |
| TEST                 | Find tests                       |
| DEPENDENCY_INJECTION | Find DI container/wiring         |
| API_BOUNDARY         | Find API endpoint definitions    |
| SERIALIZER           | Find serializer/deserializer     |
| WORKFLOW             | Find workflow definition         |
| TASK                 | Find task definition             |
| CAPABILITY           | Find capability registration     |
| PROVIDER             | Find provider hierarchy          |
| VALIDATION           | Find validation logic            |
| FACTORY              | Find factory pattern             |
| EXTENSION            | Find extension point             |
| ARCHITECTURE         | Find architecture docs + modules |
| SIMILAR              | Find similar implementation      |
| DEFAULT              | Fallback — no engineering goal   |

Constraints
-----------

- Rules are evaluated in priority order (lower = higher priority).
- First matching rule wins.
- No side effects during rule evaluation.
- No repository access.
- No AST parsing.
- Pure function: same input always produces same output.

Public API
----------

.. code-block:: python

    from packages.planning.intent_rules import (
        EngineeringIntentRule,
        IntentRuleEngine,
        BUILTIN_INTENT_RULES,
    )

    engine = IntentRuleEngine()
    plan = engine.resolve("where is ProviderFactory", "SEARCH")
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.planning.plan import ContextPlan


# ---------------------------------------------------------------------------
# EngineeringIntentRule model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineeringIntentRule:
    """A deterministic rule mapping query patterns to engineering sub-intents.

    Attributes:
        trigger_patterns: Patterns checked against user query text.
            Checked as substring matches (case-insensitive).
        retrieval_profile: Engineering goal label. Examples:
            IMPLEMENTATION, INTERFACE, REGISTRY, WORKFLOW, etc.
        preferred_symbol_types: Symbol types to prioritize.
            Examples: ("CLASS",), ("CLASS", "FUNCTION").
        preferred_module_patterns: Module path patterns to prioritize.
            Examples: ("providers/", "api/").
        relationship_preferences: Relationship types to prioritize.
            Examples: ("CALLS",), ("DEFINES", "CALLS").
        excluded_patterns: Patterns to exclude from results.
            Examples: ("tests/", "generated/").
        priority_packages: Packages to rank highest.
        secondary_packages: Packages to rank as secondary.
        priority: Rule priority (lower = evaluated first).
            Used for conflict resolution when multiple rules match.
    """

    trigger_patterns: tuple[str, ...]
    retrieval_profile: str
    preferred_symbol_types: tuple[str, ...] = ()
    preferred_module_patterns: tuple[str, ...] = ()
    relationship_preferences: tuple[str, ...] = ()
    excluded_patterns: tuple[str, ...] = ()
    priority_packages: tuple[str, ...] = ()
    secondary_packages: tuple[str, ...] = ()
    priority: int = 50


# ---------------------------------------------------------------------------
# Built-in intent rules
# ---------------------------------------------------------------------------

BUILTIN_INTENT_RULES: tuple[EngineeringIntentRule, ...] = (
    # --- Interface queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "interface",
            "abstract",
            "protocol",
            "base class",
            "abstract class",
        ),
        retrieval_profile="INTERFACE",
        preferred_symbol_types=("CLASS",),
        preferred_module_patterns=("*_interface*", "*_abstract*", "*base*"),
        priority=5,
    ),

    # --- Registry queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "register",
            "registry",
            "registration",
            "registry of",
            "registered",
        ),
        retrieval_profile="REGISTRY",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        preferred_module_patterns=("*registry*", "*register*"),
        priority=5,
    ),

    # --- Entry point queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "entry point",
            "entrypoint",
            "startup",
            "bootstrap",
            "application starts",
        ),
        retrieval_profile="ENTRY_POINT",
        preferred_symbol_types=("FUNCTION", "CLASS"),
        preferred_module_patterns=("*main*", "*startup*", "*bootstrap*"),
        priority=5,
    ),

    # --- Serializer queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "serializer",
            "serialize",
            "deserialize",
            "serialization",
            "encoder",
            "decoder",
        ),
        retrieval_profile="SERIALIZER",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        preferred_module_patterns=("*serial*", "*encode*", "*decode*"),
        priority=5,
    ),

    # --- Workflow queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "workflow",
            "pipeline",
            "orchestration",
        ),
        retrieval_profile="WORKFLOW",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        preferred_module_patterns=("*workflow*", "*pipeline*"),
        priority=5,
    ),

    # --- Task queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "background task",
            "scheduled task",
        ),
        retrieval_profile="TASK",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        preferred_module_patterns=("*task*"),
        priority=5,
    ),

    # --- Capability queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "capability",
            "capabilities",
            "feature",
            "features",
        ),
        retrieval_profile="CAPABILITY",
        preferred_symbol_types=("CLASS",),
        preferred_module_patterns=("*capability*", "*feature*"),
        priority=5,
    ),

    # --- Provider queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "provider",
            "provider hierarchy",
            "provider registration",
            "providers",
        ),
        retrieval_profile="PROVIDER",
        preferred_symbol_types=("CLASS",),
        preferred_module_patterns=("*provider*"),
        priority=5,
    ),

    # --- Factory queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "factory",
            "factory pattern",
            "builder",
        ),
        retrieval_profile="FACTORY",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        preferred_module_patterns=("*factory*", "*builder*"),
        priority=5,
    ),

    # --- Extension point queries (priority 5) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "extension",
            "extension point",
            "plugin",
            "plugins",
            "hook",
            "hooks",
        ),
        retrieval_profile="EXTENSION",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        preferred_module_patterns=("*extension*", "*plugin*", "*hook*"),
        priority=5,
    ),

    # --- Execution flow queries (priority 10) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "execution flow",
            "call flow",
            "call chain",
            "how does",
            "how do",
            "flow of",
            "flow through",
        ),
        retrieval_profile="EXECUTION_FLOW",
        preferred_symbol_types=("FUNCTION", "METHOD"),
        relationship_preferences=("CALLS",),
        priority=10,
    ),

    # --- Configuration queries (priority 10) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "config",
            "configuration",
            "settings",
            "configure",
            "setup",
        ),
        retrieval_profile="CONFIGURATION",
        preferred_symbol_types=("CLASS", "FUNCTION", "VARIABLE"),
        preferred_module_patterns=("*config*", "*setting*"),
        priority=10,
    ),

    # --- Test queries (priority 10) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "test",
            "tests",
            "unit test",
            "integration test",
            "e2e",
            "spec",
        ),
        retrieval_profile="TEST",
        preferred_symbol_types=("FUNCTION", "CLASS"),
        preferred_module_patterns=("*test*"),
        priority=10,
    ),

    # --- Dependency injection queries (priority 10) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "dependency injection",
            "di container",
            "wire",
            "wiring",
            "inject",
            "container",
        ),
        retrieval_profile="DEPENDENCY_INJECTION",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        preferred_module_patterns=("*container*", "*wire*", "*inject*"),
        priority=10,
    ),

    # --- API boundary queries (priority 10) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "endpoint",
            "route",
            "handler",
            "controller",
            "view",
            "router",
        ),
        retrieval_profile="API_BOUNDARY",
        preferred_symbol_types=("FUNCTION", "CLASS"),
        preferred_module_patterns=("*api*", "*route*", "*handler*", "*controller*"),
        priority=10,
    ),

    # --- Validation queries (priority 10) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "validation",
            "validate",
            "validator",
            "verify",
        ),
        retrieval_profile="VALIDATION",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        preferred_module_patterns=("*valid*"),
        priority=10,
    ),

    # --- Implementation queries (priority 15) ---
    # Only matches when no more specific profile matched.
    # Uses specific implementation keywords, NOT generic phrases.
    EngineeringIntentRule(
        trigger_patterns=(
            "implement",
            "implementation",
            "locate",
        ),
        retrieval_profile="IMPLEMENTATION",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        priority=15,
    ),

    # --- Architecture queries (priority 15) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "architecture",
            "overview",
            "design",
            "why",
            "reason",
            "purpose",
            "describe",
        ),
        retrieval_profile="ARCHITECTURE",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        relationship_preferences=("DEFINES", "CALLS"),
        priority=15,
    ),

    # --- Debug/fix queries (priority 20) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "fix",
            "debug",
            "error",
            "bug",
            "diagnose",
            "broken",
            "crash",
            "fail",
            "failing",
            "traceback",
            "exception",
            "throw",
            "fault",
            "resolve",
        ),
        retrieval_profile="IMPLEMENTATION",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        relationship_preferences=("CALLS", "DEFINES"),
        excluded_patterns=("*test*", "*generated*"),
        priority=20,
    ),

    # --- Similar implementation queries (priority 25) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "similar",
            "like",
            "example",
            "implement like",
            "same as",
        ),
        retrieval_profile="SIMILAR",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        priority=25,
    ),

    # --- Refactor queries (priority 20) ---
    EngineeringIntentRule(
        trigger_patterns=(
            "refactor",
            "restructure",
            "reorganize",
            "rename",
            "cleanup",
            "simplify",
            "redesign",
        ),
        retrieval_profile="IMPLEMENTATION",
        preferred_symbol_types=("CLASS", "FUNCTION"),
        relationship_preferences=("CALLS", "DEFINES"),
        priority=20,
    ),

    # --- Default fallback (priority 100) ---
    EngineeringIntentRule(
        trigger_patterns=(),
        retrieval_profile="DEFAULT",
        priority=100,
    ),
)


# ---------------------------------------------------------------------------
# IntentRuleEngine
# ---------------------------------------------------------------------------


class IntentRuleEngine:
    """Evaluates engineering intent rules and produces retrieval hints.

    Rules are evaluated in priority order (lower priority value =
    higher priority = evaluated first). First matching rule wins.

    The engine is stateless and deterministic. Same input always
    produces the same output.

    Attributes:
        _rules: Ordered list of engineering intent rules to evaluate.
    """

    def __init__(self, rules: tuple[EngineeringIntentRule, ...] | None = None) -> None:
        """Initialize the intent rule engine.

        Args:
            rules: Optional custom rule list. Defaults to BUILTIN_INTENT_RULES.
        """
        self._rules = rules if rules is not None else BUILTIN_INTENT_RULES
        # Sort by priority (lower = higher priority) for evaluation order.
        self._rules = tuple(sorted(self._rules, key=lambda r: r.priority))

    @property
    def rules(self) -> tuple[EngineeringIntentRule, ...]:
        """The ordered list of engineering intent rules."""
        return self._rules

    def match(self, query_text: str) -> EngineeringIntentRule:
        """Find the first matching rule for the query text.

        Rules are evaluated in priority order. First match wins.
        If no rule matches, returns the DEFAULT rule.

        Args:
            query_text: The user query text to analyze.

        Returns:
            The first matching EngineeringIntentRule.
        """
        query_lower = query_text.lower()

        for rule in self._rules:
            if not rule.trigger_patterns:
                # No trigger patterns = default fallback.
                return rule
            for pattern in rule.trigger_patterns:
                if pattern.lower() in query_lower:
                    return rule

        # Fallback: return the rule with no trigger patterns (DEFAULT).
        for rule in self._rules:
            if not rule.trigger_patterns:
                return rule

        # Last resort: return the highest priority rule.
        return self._rules[-1] if self._rules else BUILTIN_INTENT_RULES[-1]

    def resolve(
        self,
        query_text: str,
        intent: str,
    ) -> ContextPlan:
        """Resolve engineering intent and produce a ContextPlan with retrieval hints.

        Evaluates the query against engineering intent rules, then
        produces a ContextPlan with retrieval hints populated.

        Args:
            query_text: The user query text.
            intent: The detected high-level intent (EXPLAIN, DEBUG, etc.).

        Returns:
            A ContextPlan with retrieval hints populated.
        """
        rule = self.match(query_text)

        return ContextPlan(
            intent=intent,
            retrieval_profile=rule.retrieval_profile,
            preferred_symbol_types=rule.preferred_symbol_types,
            preferred_module_patterns=rule.preferred_module_patterns,
            relationship_preferences=rule.relationship_preferences,
            excluded_patterns=rule.excluded_patterns,
            priority_packages=rule.priority_packages,
            secondary_packages=rule.secondary_packages,
            estimated_complexity="MODERATE",
        )