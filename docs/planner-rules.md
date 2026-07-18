# Planner Rules

## Overview

Planning rules define deterministic retrieval strategies for each intent.
The `RuleEngine` evaluates rules in order — first matching rule wins.
Rules are evaluated independently of intent detection; the planner feeds
a detected intent string and the engine returns the matching rule.

```
ContextPlanner
    |
    v
Intent Detection (keyword matching)
    |
    v
RuleEngine.match(intent)
    |
    v
PlanningRule → ContextPlan
```

## PlanningRule

```python
@dataclass(frozen=True)
class PlanningRule:
    intent: str
    relationship_expansion: bool
    maximum_depth: int
    include_callers: bool
    include_callees: bool
    include_modules: bool
    include_diagnostics: bool
    ranking_profile: str
    estimated_complexity: str = "MODERATE"
```

**Constraints:**

- Immutable (`frozen=True`)
- No side effects during rule evaluation
- Rules are evaluated in order (tuple, not list)

## Built-in Rules

| Intent | Expansion | Max Depth | Callers | Callees | Modules | Diagnostics | Profile | Complexity |
|--------|-----------|-----------|---------|---------|---------|-------------|---------|------------|
| `EXPLAIN` | True | 1 | True | True | True | False | EXPLAIN | MODERATE |
| `IMPLEMENT` | True | 1 | False | True | True | False | IMPLEMENT | MODERATE |
| `REFACTOR` | True | 1 | True | True | True | False | REFACTOR | COMPLEX |
| `DEBUG` | True | 2 | True | True | True | True | DEBUG | COMPLEX |
| `TEST` | True | 1 | True | False | True | True | TEST | MODERATE |
| `SEARCH` | False | 0 | False | False | False | False | SEARCH | SIMPLE |
| `DEFAULT` | False | 0 | False | False | True | False | DEFAULT | SIMPLE |

### Rule Semantics

- **EXPLAIN** — Minimal context for understanding code. Expands relationships
  one hop to show callers and callees.
- **IMPLEMENT** — Context for adding new functionality. Shows callees (what
  the code calls) but not callers (who calls it).
- **REFACTOR** — Full context for restructuring code. Same depth as EXPLAIN
  but marked as COMPLEX due to the breadth of relationships.
- **DEBUG** — Diagnostic context with maximum depth (2 hops) and diagnostics
  enabled. Shows callers, callees, and diagnostic information.
- **TEST** — Test generation context. Shows callers but not callees, with
  diagnostics enabled for understanding expected behavior.
- **SEARCH** — Minimal context for finding information. No relationship
  expansion, no diagnostics.
- **DEFAULT** — Fallback rule. No expansion, no diagnostics, but includes
  module-level context.

## RuleEngine

```python
class RuleEngine:
    def __init__(self, rules: tuple[PlanningRule, ...] | None = None) -> None:
        """Initialize with BUILTIN_RULES or custom rules.

        Raises ValueError if custom rules are provided without a DEFAULT rule.
        """

    @property
    def rules(self) -> tuple[PlanningRule, ...]:
        """The ordered list of planning rules."""

    def match(self, intent: str) -> PlanningRule:
        """Find the first matching rule for the given intent.

        If no rule matches, returns the DEFAULT rule.
        Raises ValueError if no DEFAULT rule exists.
        """

    def build_plan(self, intent: str) -> ContextPlan:
        """Build a ContextPlan from the matched rule.

        Creates an immutable ContextPlan with primary_symbols=().
        """
```

### Behavior

- **Order matters:** Rules are evaluated in tuple order. First match wins.
- **DEFAULT fallback:** If no rule matches the intent, the DEFAULT rule is
  returned. This prevents silent failures.
- **Custom rules:** Custom rule lists must include a DEFAULT rule to prevent
  silent fallback to undefined behavior per-request.

### Usage

```python
from packages.planning.rules import RuleEngine, PlanningRule

# Default: use built-in rules
engine = RuleEngine()
rule = engine.match("EXPLAIN")
plan = engine.build_plan("EXPLAIN")

# Custom rules with DEFAULT fallback
custom_rules = (
    PlanningRule(
        intent="CUSTOM",
        relationship_expansion=True,
        maximum_depth=1,
        include_callers=True,
        include_callees=True,
        include_modules=True,
        include_diagnostics=False,
        ranking_profile="CUSTOM",
        estimated_complexity="SIMPLE",
    ),
    # MUST include DEFAULT
    PlanningRule(
        intent="DEFAULT",
        relationship_expansion=False,
        maximum_depth=0,
        include_callers=False,
        include_callees=False,
        include_modules=True,
        include_diagnostics=False,
        ranking_profile="DEFAULT",
        estimated_complexity="SIMPLE",
    ),
)
engine = RuleEngine(rules=custom_rules)
```

## Integration with ContextPlanner

The `ContextPlanner` uses the `RuleEngine` to convert detected intents into
`ContextPlan` objects:

```python
from packages.planning.planner import ContextPlanner
from packages.planning.intent import detect_intent

planner = ContextPlanner()
plan = planner.build(
    user_messages=["Explain how ProviderFactory works"],
    repository_index=index,
)
# Internally:
#   1. detect_intent(messages) → "EXPLAIN"
#   2. RuleEngine().build_plan("EXPLAIN") → ContextPlan
```

## Constraints

- Rules are pure data — no logic, no side effects.
- The engine is stateless and deterministic.
- No filesystem access, no AST, no LLM calls.
- Rule evaluation is O(n) where n is the number of rules.

## File Structure

```
packages/planning/
    rules.py    — PlanningRule, RuleEngine, BUILTIN_RULES
    plan.py     — ContextPlan model
    intent.py   — Intent enum + detection
    planner.py  — ContextPlanner

tests/planning/
    test_rules.py    — RuleEngine tests
```
