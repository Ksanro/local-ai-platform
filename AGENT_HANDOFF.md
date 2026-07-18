# Agent Handoff: Refactor Capability v1

## Summary of Changes

### Files Created

1. **`packages/capabilities/refactor.py`** — New file containing `RefactorCapability`
   - Implements the `Capability` ABC with `PlannerIntent.REFACTOR`
   - Name: `"refactor"`
   - Pipeline stages: Planning → Repository Search → Context Building → Package Assembly → Serialization → Result
   - Stateless orchestration only — no duplicated logic

### Files Modified

2. **`packages/capabilities/__init__.py`** — Updated to export `RefactorCapability`
   - Added import: `from packages.capabilities.refactor import RefactorCapability`
   - Added to `__all__`: `"RefactorCapability"`

3. **`tests/capabilities/test_refactor.py`** — 71 tests covering all requirements

## RefactorCapability Details

### Public API
```python
from packages.capabilities.refactor import RefactorCapability

capability = RefactorCapability()
result = capability.execute(
    query="Refactor ProviderFactory",
    repository_index=index,
)
```

### Key Attributes
- **name**: `"refactor"`
- **intent**: `PlannerIntent.REFACTOR`

### Pipeline Stages
1. **Planning** — `ContextPlanner.build()` produces `ContextPlan` with REFACTOR intent
2. **Repository Search** — `repository_index.find(query)` returns symbol matches
3. **Context Building** — `ContextBuilder.build()` with deeper depth and relationship expansion
4. **Package Assembly** — Construct `ContextPackage` from `ContextResult`
5. **Serialization** — `SerializerFactory.create(ProviderType.openai).serialize()`
6. **Result** — Aggregate into immutable `CapabilityResult`

### Retrieval Profile
- Maximum depth: from ContextPlan (typically 3 for refactor)
- Relationship expansion: True
- Includes: callers, callees, diagnostics, dependencies, dead code, tests

### Constraints
- No ranking, no AST inspection, no filesystem access
- No provider calls, no HTTP execution
- No mutation of RepositoryIndex or ContextPackage
- No graph traversal, no symbol ranking, no dependency computation
- Only orchestration of existing public APIs

## Test Results

```
============================= test session starts ==============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
collected 71 items

tests/capabilities/test_refactor.py::TestRefactorRegistration ... PASSED
tests/capabilities/test_refactor.py::TestRefactorIntent ... PASSED
tests/capabilities/test_refactor.py::TestPlannerInvoked ... PASSED
tests/capabilities/test_refactor.py::TestRepositoryQueried ... PASSED
tests/capabilities/test_refactor.py::TestContextBuilt ... PASSED
tests/capabilities/test_refactor.py::TestSerializerInvoked ... PASSED
tests/capabilities/test_refactor.py::TestRefactorExecution ... PASSED
tests/capabilities/test_refactor.py::TestDeterministicExecution ... PASSED
tests/capabilities/test_refactor.py::TestImmutableResult ... PASSED
tests/capabilities/test_refactor.py::TestRepeatedExecutionIdentical ... PASSED
tests/capabilities/test_refactor.py::TestRefactorContextConfiguration ... PASSED
tests/capabilities/test_refactor.py::TestExplainDebugUnchanged ... PASSED
tests/capabilities/test_refactor.py::TestRefactorStages ... PASSED
tests/capabilities/test_refactor.py::TestRegistryEdgeCases ... PASSED
tests/capabilities/test_refactor.py::TestCapabilityResultFields ... PASSED

============================== 71 passed in 0.26s ===============================
```

**Coverage**: 97% (packages/capabilities/refactor.py: 117 stmts, 4 missing)

**Ruff**: All checks passed

**Mypy**: All checks passed

STATUS: PASSED — fixes applied

## Fixes Applied

1. **Dead callers loop removed** — The callers loop in `_stage_assemble_package` was unreachable dead code. The primary is always `candidates[0]` (first/highest score), so `primary_index` is always 0. The loop was kept in `ExplainCapability` for symmetry; the same comment was added to `RefactorCapability`.

2. **Lint fix** — Split the 104-char docstring on line 1089 to fit the 100-char limit.

3. **New test** — `test_stage_assemble_package_primary_is_first_candidate` verifies that the primary is always the first candidate, callers are empty, and remaining same-module candidates become callees.

4. **Stale line references** — 10 test comments referenced old line numbers (e.g. "lines 342-350", "lines 357-360") that had shifted after the dead callers loop was removed. All 10 references updated to current line numbers.

5. **Misleading `supporting_candidates` references** — Multiple test comments said "looked up in supporting_candidates" as if it were a `ContextResult` field. It's actually a local variable (`candidates[1:]`) in the capability code. Comments updated to clarify this.

6. **Missing `profile` property tests** — Added `test_profile_is_refactor_profile` and `test_profile_is_retrieval_profile` to verify the `profile` property returns `REFACTOR_PROFILE`. Also added `cap.profile is REFACTOR_PROFILE` to the factory stateless instance test.

7. **Missing `__init__.py` exports** — Added exports for `REFACTOR_PROFILE`, `DEBUG_PROFILE`, `EXPLAIN_PROFILE`, and `RetrievalProfile` to `packages/capabilities/__init__.py` so they're accessible from the package root as documented.

## Final State

- 71 tests (was 68, +3 new)
- 1133 total tests (was 1097, +36 new)
- Ruff: clean
- Mypy: clean
- No regressions
