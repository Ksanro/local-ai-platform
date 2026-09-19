# Agent Handoff: ImplementFeature Capability v1

## Summary of Changes

### Files Created

1. **`packages/capabilities/implement_feature.py`** — New file containing `ImplementFeatureCapability`
   - Implements the `Capability` ABC with `PlannerIntent.IMPLEMENT`
   - Name: `"implement-feature"`
   - Pipeline stages: Planning → Repository Search → Context Building → Package Assembly → Serialization → Result
   - Stateless orchestration only — no duplicated logic
   - **Dormant**: exported from the package root, not registered or invoked by the gateway or pipeline

2. **`tests/capabilities/test_implement_feature.py`** — 85 tests covering all requirements

### Files Modified

3. **`packages/capabilities/__init__.py`** — Added imports and `__all__` entries for
   `ImplementFeatureCapability` and `IMPLEMENT_PROFILE`

4. **`packages/capabilities/profiles.py`** — Added `IMPLEMENT_PROFILE`
   (`name="implement-feature"`, depth 2, `include_dead_code=False`)

5. **`docs/capabilities.md`** — Added the Implement Feature Capability section,
   the `IMPLEMENT_PROFILE` row in the built-in profiles table, and marked the
   "Future Capabilities" entry as implemented (dormant)

## ImplementFeatureCapability Details

### Public API

```python
from packages.capabilities import ImplementFeatureCapability

capability = ImplementFeatureCapability()
result = capability.execute(
    query="Implement the new retrieval profile in the gateway pipeline",
    repository_index=index,
)
```

### Key Attributes

- **name**: `"implement-feature"`
- **intent**: `PlannerIntent.IMPLEMENT`
- **profile**: `IMPLEMENT_PROFILE`

### Pipeline Stages

1. **Planning** — `ContextPlanner.build(user_messages=[query], repository_index=index,
   intent_override="IMPLEMENT")` produces the `ContextPlan`; the capability never
   constructs plans, requests, budgets, or candidates itself
2. **Repository Search** — `repository_index.find(query)` returns symbol matches in
   repository order (no sorting, filtering, trimming, or ranking)
3. **Context Building** — `ContextBuilder.build()` receives a `ContextQuery` built from the
   profile: `maximum_depth=IMPLEMENT_PROFILE.relationship_depth` (2),
   `max_tokens=IMPLEMENT_PROFILE.max_context_tokens` (4096), and
   `relationship_expansion=include_callers or include_callees` (True). `max_symbols` is not
   passed, so it keeps the established `ContextQuery` default (20 candidates) — the plan's
   `maximum_depth` is traversal depth (1 for the IMPLEMENT rule), never a candidate count.
   `include_tests` / `include_dependencies` / `include_dependents` / `include_diagnostics` /
   `include_dead_code` have no `ContextQuery` counterpart and are not forwarded
4. **Package Assembly** — Construct `ContextPackage` from `ContextResult` (primary symbol,
   supporting symbols, related modules, plus `related_callees` copied from the score
   order of same-module candidates). That last item is fabricated relationship data, not
   a `CALLS` lookup, and `related_callers` can never fill because the primary is always
   the first candidate — see the "Sibling defect" note under *Generate-Tests Capability
   (this session) -> Notes For The Next Agent*.
5. **Serialization** — `SerializerFactory.create(ProviderType.openai).serialize()`
6. **Result** — Aggregate into immutable `CapabilityResult`

### Retrieval Profile

- Name: `"implement-feature"`
- `relationship_depth`: 2, `max_context_tokens`: 4096 (same ceiling as `REFACTOR_PROFILE`)
- `include_callers` / `include_callees` are True, which is what turns
  `ContextQuery.relationship_expansion` on
- `include_dependencies`, `include_dependents`, `include_tests`,
  `include_diagnostics` and `include_dead_code` are **declarative profile intent**: the
  current `ContextQuery` API has no such fields, so the capability does not forward them
- Excludes: dead code (the only difference from `REFACTOR_PROFILE` other than depth)

### Constraints

- No ranking, no AST inspection, no filesystem access
- No provider calls, no HTTP execution, no imports from `packages.providers`
- No mutation of `RepositoryIndex` or `ContextPackage`
- No graph traversal, no symbol ranking, no dependency computation
- Only orchestration of existing public APIs

### Dormancy

- No module under `apps/gateway` or `packages/pipeline` references
  `ImplementFeatureCapability` or `IMPLEMENT_PROFILE` (statically asserted in tests)
- Activation is a one-line registration:
  `registry.register("implement-feature", ImplementFeatureCapability)`
- **Name overlap (pre-existing, benign)**: `packages/pipeline/stages/workflow_stage.py`
  registers a live default *workflow* named `"implement-feature"`
  (`_DEFAULT_WORKFLOW = "implement-feature"`). That is the `Workflow` / `WorkflowRegistry`
  abstraction, not `Capability` / `CapabilityRegistry`, and the pipeline never imports
  `packages.capabilities`. Asserted by
  `test_pipeline_implement_feature_workflow_is_a_different_abstraction`.

## Test Results

Re-run in this session with captured output:

```
.\uv.exe run python -m pytest tests\capabilities\test_implement_feature.py -q
  85 passed in 0.27s

.\uv.exe run python -m pytest tests\capabilities -q
  419 passed in 3.18s

.\uv.exe run python -m pytest tests\pipeline tests\gateway -q
  200 passed in 6.33s

.\uv.exe run python -m pytest tests\workflows\test_pull_request_review.py tests\planning tests\context -q
  666 passed in 1.22s

.\uv.exe run python -m ruff check packages\capabilities tests\capabilities
  All checks passed!

.\uv.exe run python -m mypy packages\capabilities
  Success: no issues found in 13 source files
  (note: "unused section(s)" notice for unrelated mypy overrides)

git --no-pager diff --check
  clean (only pre-existing "LF will be replaced by CRLF" warnings for
  README.md, docs/capabilities.md, architecture_review.py, bug_investigation.py)

.\uv.exe run python -c "import packages.capabilities as c; print(c.ImplementFeatureCapability().name, c.ImplementFeatureCapability().intent, c.IMPLEMENT_PROFILE)"
  implement-feature PlannerIntent.IMPLEMENT RetrievalProfile(name='implement-feature', include_callers=True,
  include_callees=True, include_dependencies=True, include_dependents=True, include_tests=True,
  include_dead_code=False, include_diagnostics=True, relationship_depth=2, max_context_tokens=4096)
```

**Environment notes**: `uv run mypy` fails to spawn here; `python -m mypy` is used instead.
`pytest --cov` is unavailable (`pytest-cov` is not installed). The full `pytest tests` run is
still not executed here because it exceeds the command timeout; run it in CI.

## Correctness Pass (this session)

Focused review fixes on `ImplementFeatureCapability` v1. Four findings, all applied; the
capability stays dormant and no other package changed.

1. **Intent was not pinned** — `_stage_planning()` called
   `ContextPlanner.build(user_messages=[query], repository_index=index)` and trusted keyword
   detection, so "debug the crashing gateway" produced a `DEBUG` plan and
   `CapabilityResult.intent` followed it. The call now passes
   `intent_override=self.intent.value`, so the plan and the result are always `IMPLEMENT`
   (`packages/capabilities/implement_feature.py`, `_stage_planning`).

2. **`maximum_depth` was misused as `max_symbols`** — `_stage_context_building()` set
   `max_symbols=context_plan.maximum_depth if > 0 else 20`. The IMPLEMENT planning rule
   carries `maximum_depth=1` (traversal depth), so every real run silently clamped retrieval
   to a single candidate. `max_symbols` is no longer passed at all: the `ContextQuery` keeps
   its established default ceiling (20), while the profile still owns
   `maximum_depth=IMPLEMENT_PROFILE.relationship_depth`, `max_tokens=IMPLEMENT_PROFILE.max_context_tokens`,
   and `relationship_expansion` derived from `include_callers or include_callees`.

3. **Test that rewarded the old bug replaced** — `test_planner_output_drives_the_result_intent`
   (asserted a `DEBUG` plan leaked into `result.intent`) is deleted. In its place,
   `TestPlannerIntentAndCandidateCeiling` proves: `intent_override="IMPLEMENT"` reaches
   `ContextPlanner.build`; debug-like (`DEBUG`), find-style (`SEARCH`) and explain-style
   (`EXPLAIN`) wording still yields an `IMPLEMENT` result against the *real* planner;
   `max_symbols` never tracks `maximum_depth` (parametrized over 0/1/2/3); and an
   `IMPLEMENT` plan with `maximum_depth=1` still returns several candidates (both with a
   mocked plan and with the real planner). The helper
   `patched_context_and_serializer()` runs the real planner while patching only retrieval
   and serialization.

4. **Documentation overclaims corrected** — `include_tests`, `include_dependencies`,
   `include_dependents`, `include_diagnostics` and `include_dead_code` are now described as
   declarative profile intent, because `ContextQuery` has no such fields
   (`text`, `max_symbols`, `max_modules`, `max_tokens`, `maximum_depth`,
   `relationship_expansion`). Fixed in the module docstring, `docs/capabilities.md`
   (RetrievalProfile note, Implement Feature flow diagram, pipeline stages, profile table
   row label `relationship_depth`, implementation snippet comments), and this handoff.
   `ContextQuery` and the live context builder were **not** extended.

## Fixes Applied

1. **Import purity** — The provider-boundary test previously asserted that
   `packages.providers` was absent from `sys.modules`, which fails because unrelated
   test modules import providers first. It now asserts that executing the capability
   does not add new `packages.providers` modules.

2. **Profile contract tests** — Sibling-profile assertions relied on guessed field
   values (`exclude_dead_code`, `minimum_depth`, `max_results`) that do not exist on
   `RetrievalProfile`. Replaced with assertions over the real dataclass fields.

3. **Serializer assertion** — Renamed to describe what it actually proves: the
   serializer is invoked exactly once with the assembled messages, and the returned
   `ProviderRequest` is the value placed on `CapabilityResult`.

4. **Stage coverage** — Added a test that the pipeline stage methods are defined and
   ordered as documented.

5. **Dormancy scan tokens** — A first draft of `test_pipeline_never_registers_the_capability`
   searched the pipeline for the bare string `"implement-feature"` and failed:
   `packages/pipeline/stages/workflow_stage.py` already registers a default *workflow* with
   that name. The scan now looks for capability-specific symbols only, and a dedicated test
   pins the distinction between the workflow registry and the capability registry.

6. **Handoff file encoding** — Truncating this file with `Get-Content`/`Set-Content`
   introduced a UTF-8 BOM, doubled CR characters, and mojibake on em dashes and arrows.
   Repaired byte-for-byte; the file now contains only U+2014 and U+2192 as non-ASCII.

## Final State

- 85 capability tests; every public surface of `packages/capabilities/implement_feature.py`
  (`name`, `intent`, `profile`, `execute`) is exercised through the real `execute` path and
  the per-stage contract tests
- `IMPLEMENT` intent is pinned at the planner boundary, and the retrieval ceiling no longer
  depends on relationship traversal depth
- Coverage percentage not reported: `pytest --cov` is unavailable in this environment
  (`pytest-cov` is not installed)
- Capability implemented, exported, tested, and dormant
- Not gateway-integrated, not pipeline-registered
- Ruff: clean
- Mypy: clean
- No regressions in `tests/capabilities`, `tests/pipeline`, `tests/gateway`,
  `tests/planning`, `tests/context`, or `tests/workflows`


## Generate-Tests Capability (this session)

Finished the dormant, context-assembly-only `GenerateTestsCapability` and its
test suite, then ran a focused correctness pass on it: serializer availability
and fabricated call relationships. No gateway, pipeline, workflow, or controller
wiring changed.

### Files

- `packages/capabilities/generate_tests.py` — the capability (untracked, new)
- `tests/capabilities/test_generate_tests.py` — 136 tests in 14 classes
- `packages/capabilities/__init__.py` — exports `GenerateTestsCapability`,
  `GENERATE_TESTS_PROFILE`
- `packages/capabilities/profiles.py` — `GENERATE_TESTS_PROFILE`
- `docs/capabilities.md` — "Generate Tests Capability" section (now with
  *Relationship Fields* and *Serializer Availability* subsections), profile table
  row, Future Capabilities row, corrected Implement Feature stage-4 note

### Behaviour Pinned

- Five stages, in order: planning, repository search, context building, package
  assembly, serialization.
- Vocabulary split: the planner receives `intent_override="TEST"`
  (`PLANNER_INTENT_FOR_TESTS`) because `packages.planning.intent.Intent` has no
  `GENERATE_TESTS` member and an unknown override is ignored silently;
  `CapabilityResult.intent` still reports `GENERATE_TESTS`.
- Profile wiring: `max_tokens=4096`, `maximum_depth=2`,
  `relationship_expansion=True`; `max_symbols` keeps the `ContextBuilder`
  ceiling and is never taken from `ContextPlan.maximum_depth`. The
  `include_callers` / `include_callees` pair is declarative retrieval intent;
  its only live effect is the `relationship_expansion` switch it feeds.
- Relationship honesty: `related_callers` and `related_callees` are always
  empty, and `RelationshipSummary.caller_count` / `callee_count` stay `0` with
  them. Candidate ranking order and same-module membership are no longer
  reported as `CALLS` relationships. The previous module-relative rule labelled
  every lower-ranked same-module neighbour a callee and could never produce a
  caller, because the primary is `candidates[0]`. Primary symbol, supporting
  symbols, and `related_modules` assembly are unchanged.
- Serializer availability: stage 5 calls `SerializerFactory.create(ProviderType.openai)`
  and the registry behind it is populated by the serialization layer itself. In
  this session the capability carried a bootstrap import of
  `packages.serializers.openai` inside stage 5; the following session moved that
  import into `packages.serializers/__init__.py`, so no capability needs one
  (see *Capability Framework Consistency Pass*). The serializer is still created
  by the factory; nothing is instantiated directly and no provider is contacted.
- Execution stops at `ProviderRequest`; no provider call, no file write, no test
  execution, no index mutation.
- Dormant: exported and constructible, registered only by explicit test
  registries.

### Verification

| Command | Result |
|---------|--------|
| `.\uv.exe run python -m pytest tests\capabilities\test_generate_tests.py -q` | 136 passed |
| `.\uv.exe run python -m pytest tests\capabilities -q` | 555 passed |
| `.\uv.exe run python -m pytest tests\serializers tests\planning tests\context -q` | 685 passed |
| `.\uv.exe run python -m pytest tests\capabilities tests\planning tests\context tests\serializers tests\pipeline tests\workflows tests\gateway -q` | 1604 passed |
| `.\uv.exe run python -m ruff check packages\capabilities tests\capabilities` | All checks passed |
| `.\uv.exe run python -m mypy packages\capabilities packages\serializers` | Success: no issues found in 22 source files |

`ruff check packages\capabilities packages\serializers tests\capabilities
tests\serializers` additionally reported 2 pre-existing `W292` findings (no
newline at end of file) in `packages\serializers\openai.py:459` and
`tests\serializers\test_openai.py:547`. `git diff` for both files was empty, so
that was committed state; they were left untouched in this session because the
task did not change either file. The following session added the two missing
final newlines, and that ruff command is now clean.

Fresh-process proof, run from the repository root (the documented import path
only -- no serializer import anywhere in the command):

```powershell
.\uv.exe run python -c "import sys; sys.path.insert(0, '.'); from packages.capabilities.generate_tests import GenerateTestsCapability; from packages.repository.index.models import RepositoryIndex; r = GenerateTestsCapability().execute(query='retry policy', repository_index=RepositoryIndex()); print(r.provider_request.provider_type, len(r.provider_request.messages), r.context_package.related_callers, r.context_package.related_callees)"
```

Output:

```text
ProviderType.openai 1 [] []
```

The same command failed inside `execute()` before registration was owned by the
serialization layer, with `UnknownSerializerError: Serializer for provider type
'openai' is not registered` raised from `_stage_serialization`.
`tests/capabilities/test_generate_tests.py::TestFreshProcessImportPath` repeats
the check through `tests/capabilities/assembly_probes.py`: a separate
interpreter imports only the documented capability path, records that
`packages.serializers.openai` was absent from `sys.modules` before that import
and present after it, executes against a three-module index whose candidates
share one symbol name, and asserts the real serializer injected a
repository-context message while callers/callees and their counts stay empty.
The same probe runs for `ImplementFeatureCapability` and `ExplainCapability`, and
it fails loudly if the layer-level registration is removed.

### Notes For The Next Agent

1. **Serializer registration is import-driven and now owned by the
   serialization layer (RESOLVED in *Capability Framework Consistency Pass*).**
   `packages.serializers/__init__.py` imports the built-in serializer modules
   after the public names, so any import that reaches `SerializerFactory` also
   registers them. `generate_tests.py` no longer carries the stage-5 bootstrap
   import, and the six siblings
   (`explain`, `debug`, `refactor`, `implement_feature`,
   `architecture_review`, `bug_investigation`) now serialize in a fresh
   interpreter through their documented import path. Registry semantics are
   untouched: `register()` still rejects duplicates, `unregister()` still
   removes entries, and `create()` still raises `UnknownSerializerError` for a
   provider type with no serializer.
2. **Fabricated callees in every sibling capability (RESOLVED in
   *Capability Framework Consistency Pass*).** The audit in this session found
   `implement_feature.py:353-380`, `explain.py:279-313`, `debug.py:302-336`,
   `refactor.py:312-345`, `architecture_review.py:274-306`, and
   `bug_investigation.py:337-357` filling `related_callees` from the score order
   of same-module candidates, with `related_callers` structurally empty because
   the primary is `candidates[0]`. Four of them declared `include_callers=True`,
   so their caller field contradicted their own profile. All six derivations are
   now deleted: primary symbol, rank-ordered deduplicated supporting symbols and
   sorted deduplicated modules are kept, and both relationship lists -- and the
   counts computed from them -- stay empty. Assembly logic was deliberately not
   factored into a shared helper: these capabilities still own their own stage
   code, and only the two test-side probes (`tests/capabilities/assembly_probes.py`)
   are shared.
3. **`RepositoryIndex.symbols` and `.statistics` are methods, not properties.**
   `index.symbols()` / `index.statistics()`.
4. **Boundary scans strip docstrings.** `TestBoundaryRules` reads the capability
   source with `_source()`, which removes docstring lines via `ast`; the module
   docstring legitimately lists the forbidden activities ("mutate",
   "filesystem"), so raw substring scans produce false positives. Two banned
   tokens constrain edits to this file: `"openai."` (the capability never
   touches a concrete serializer module -- registration belongs to
   `packages.serializers`, so even `import packages.serializers.openai` must not
   appear) and `"SymbolGraph"` (no graph view inside a capability).
5. **`ruff format` is not a repo gate.** `ruff format --check` flags pre-existing
   files (including `tests/capabilities/test_implement_feature.py`); only
   `ruff check` (line-length 100) is enforced.
6. **Mixed line endings in `docs/capabilities.md`.** Lines 1-8 and 819 are
   LF-only in an otherwise CRLF file (pre-existing; `git diff --check` is clean).
7. **Not done / deliberate gaps:** no default registration, no workflow or
   gateway route, no test-code generation, no provider execution, and no real
   caller/callee data in `ContextPackage` (it needs a platform-level change,
   not a capability change). Coverage numbers unavailable (`pytest-cov` not
   installed).


## Capability Framework Consistency Pass (this session)

Focused pass on the two defects the previous session left open: fabricated call
relationships in the sibling capabilities, and serializer availability under each
capability's documented import path. Everything stays dormant: no gateway,
pipeline, workflow, controller, provider, or default-registry wiring, and no
graph traversal, AST inspection, or new repository-analysis logic anywhere.

### Files

- `packages/capabilities/explain.py`, `debug.py`, `refactor.py`,
  `implement_feature.py`, `architecture_review.py`, `bug_investigation.py` --
  deleted the module-relative caller/callee derivation (the `module_symbols`
  build, the `primary_index` scan, the caller/callee loops, the module-lookup
  loops they fed, and the `# pragma: no cover` markers that hid the dead
  branches). `related_callers` / `related_callees` are now plain empty lists and
  the `RelationshipSummary` counts are computed from them. Primary symbol,
  rank-ordered deduplicated `supporting_symbols`, and sorted deduplicated
  `related_modules` are unchanged, and `related_modules` now comes straight from
  the candidate list. `architecture_review.py` also dropped its now-unused
  `ContextCandidate` import.
- `packages/capabilities/generate_tests.py` -- removed the stage-5 bootstrap
  import of `packages.serializers.openai`; its docstring section is now
  *Serializer Availability* and describes the layer-level contract.
- `packages/serializers/__init__.py` -- owns built-in serializer availability: it
  imports `packages.serializers.openai` (side effect only) and documents the
  registration contract. `packages/serializers/registry.py` is untouched, so
  duplicate registration still raises `ValueError`, `unregister()` still raises
  `KeyError` for an absent type, and `SerializerFactory.create()` still raises
  `UnknownSerializerError` for a provider type with no serializer. No provider is
  imported or executed from the serialization layer.
- `packages/serializers/openai.py`, `tests/serializers/test_openai.py` -- the two
  missing final newlines only (`W292`).
- `tests/capabilities/assembly_probes.py` (new) -- shared probes:
  `assert_relationship_honesty()` assembles a package from supplied candidates
  and checks primary/supporting/dedup/modules/count consistency, and
  `run_in_fresh_interpreter()` executes a capability in a separate interpreter
  that imports nothing but the documented capability path.
- `tests/capabilities/test_explain.py` (+4), `test_debug.py` (+4),
  `test_refactor.py` (+4), `test_architecture_review.py` (+4),
  `test_bug_investigation.py` (+4 after deleting one `pass`-only placeholder
  test), `test_implement_feature.py` (+4) -- a `TestRelationshipHonesty` class in
  each: candidate permutations, same-module neighbours, cross-module neighbours,
  deduplication, count consistency, deterministic assembly. The old tests that
  asserted ranked neighbours were callees now assert supporting symbols plus
  empty relationship lists; unrelated assertions were not touched.
- `tests/capabilities/test_generate_tests.py` -- the fresh-interpreter test now
  uses the shared probe and asserts `packages.serializers.openai` is absent
  before the capability import and present after it, and the source guard
  asserts the capability contains no serializer-module import.
- `docs/capabilities.md`, `AGENT_HANDOFF.md` -- corrected the sibling
  relationship claims, the Implement Feature stage-4 note, the
  serializer-bootstrap prose, and the closed `W292` note.

### Verification

| Command | Result |
|---------|--------|
| `.\uv.exe run python -m pytest tests\capabilities tests\serializers -q` | 626 passed |
| `.\uv.exe run python -m pytest tests\planning tests\context tests\pipeline tests\gateway -q` | 839 passed |
| `.\uv.exe run python -m ruff check packages\capabilities packages\serializers tests\capabilities tests\serializers` | All checks passed |
| `.\uv.exe run python -m mypy packages\capabilities packages\serializers` | Success: no issues found in 22 source files |
| `git --no-pager diff --check` | exit 0 (only pre-existing CRLF conversion warnings) |

Suite counts after the pass: capabilities 580 (`explain` 23, `debug` 50,
`refactor` 75, `implement_feature` 90, `architecture_review` 15,
`bug_investigation` 86, `generate_tests` 136) and serializers 46.

Fresh-process audit: one interpreter per capability, the documented import path
only, an empty `RepositoryIndex`:

```powershell
.\uv.exe run python -c "import sys; sys.path.insert(0, '.'); from packages.capabilities.generate_tests import GenerateTestsCapability; from packages.repository.index.models import RepositoryIndex; r = GenerateTestsCapability().execute(query='retry policy', repository_index=RepositoryIndex()); print(r.provider_request.provider_type, len(r.provider_request.messages), r.context_package.related_callers, r.context_package.related_callees)"
.\uv.exe run python -c "import sys; sys.path.insert(0, '.'); from packages.capabilities.implement_feature import ImplementFeatureCapability; from packages.repository.index.models import RepositoryIndex; r = ImplementFeatureCapability().execute(query='retry policy', repository_index=RepositoryIndex()); print(r.provider_request.provider_type, len(r.provider_request.messages), r.context_package.related_callers, r.context_package.related_callees)"
```

Both print `ProviderType.openai 1 [] []`. Before the change the same command for
`implement_feature`, `explain`, `debug`, `refactor`, `architecture_review` and
`bug_investigation` ended in `UnknownSerializerError: Serializer for provider
type 'openai' is not registered`; only `generate_tests` survived, because it
carried its own bootstrap import. The bootstrap is centralized now, so all seven
directly executable capabilities serialize in a fresh interpreter, and each
publishes `related_callers == []`, `related_callees == []` and matching counts.

### Notes For The Next Agent

1. **Serializer availability is centralized on purpose.** Do not add a
   `packages.serializers.openai` import back into a capability, and do not make
   `SerializerFactory.create()` import serializers lazily -- that would let
   `has_serializer()` and `create()` disagree about the registry. The single
   place that decides which built-ins exist is
   `packages/serializers/__init__.py`.
2. **`tests/conftest.py::_ensure_serializers_loaded` stays.** It is redundant for
   openai now, but it still restores the registry after a test that unregisters
   it; the fresh-interpreter probes, not the fixture, are what prove the layer
   owns availability.
3. **Relationship fields stay empty framework-wide.** If verified `CALLS` edges
   ever reach capabilities, the change belongs in `ContextResult` (the ranking
   engine already consumes a real graph), not in another module-relative guess
   inside a capability. `assembly_probes.assert_relationship_honesty()` is the
   shared place to teach the probes about verified edges when that happens.
4. **Assembly logic is still duplicated per capability** by design; the new
   shared module is test-side only.


## Review Capability v1 (this session)

Implemented the last planned Capability Framework v1 item: `ReviewCapability`,
dormant and context-assembly-only, built on the corrected sibling patterns (no
derived relationships, serializer availability owned by the serialization layer,
profile-over-plan retrieval).

### Files

- `packages/capabilities/review.py` (new) -- `ReviewCapability` plus the module
  constant `PLANNER_INTENT_FOR_REVIEW: str = "SEARCH"`. Five stages, each one
  call into an existing public API, in the same shape and order as
  `generate_tests.py` / `implement_feature.py`.
- `packages/capabilities/profiles.py` -- added `REVIEW_PROFILE` next to
  `ARCHITECTURE_REVIEW_PROFILE`, with the values below and a note that the two
  review profiles are deliberately different. No sibling profile changed.
- `packages/capabilities/__init__.py` -- exports `ReviewCapability` and
  `REVIEW_PROFILE`; the docstring roster moved Review from "Future" to
  "Implemented (dormant)". No registration, no wiring.
- `tests/capabilities/test_review.py` (new) -- 109 focused tests, reusing
  `tests/capabilities/assembly_probes.py` for the permutation and
  fresh-interpreter probes.
- `docs/capabilities.md` -- new `## Review Capability` section, a
  `REVIEW_PROFILE` row in the built-in profiles table, the fresh-interpreter
  sentence now names `ReviewCapability`, and the Future Capabilities table marks
  Review as implemented (dormant).
- `AGENT_HANDOFF.md` -- this record.

Untouched on purpose: every other capability module, the planner, the context
builder, the serializers, and all gateway/pipeline/workflow/controller code. All
pre-existing working-tree changes from earlier sessions are preserved.

### Exact Behaviour

- `name == "review"`, `intent is PlannerIntent.REVIEW`,
  `profile is REVIEW_PROFILE`, stateless (`__dict__ == {}`), synchronous.
- Pipeline: `ContextPlanner.build(user_messages=[query],
  repository_index=index, intent_override=PLANNER_INTENT_FOR_REVIEW)` ->
  `repository_index.find(query)` ->
  `ContextBuilder(index=index).build(query=ContextQuery(...))` ->
  `_stage_assemble_package` -> `SerializerFactory.create(ProviderType.openai)` ->
  frozen `CapabilityResult`. No stage is skipped, duplicated or reordered.
- Vocabulary boundary, the four surfaces and what each reports:
  - `ReviewCapability.intent` -> `PlannerIntent.REVIEW` (`"REVIEW"`),
  - the planner call -> `intent_override="SEARCH"`,
  - `CapabilityResult.context_plan.intent` -> `"SEARCH"`,
  - `CapabilityResult.intent` -> `"REVIEW"` (taken from `self.intent.value`; the
    only result field that does not mirror the plan).
  `packages.planning.intent.Intent` has no `REVIEW` member and
  `ContextPlanner.build()` silently ignores an override outside its own
  vocabulary, so the constant is required. `SEARCH` was chosen because review is
  read-only inspection with no assumed outcome: `DEBUG` presumes a defect,
  `REFACTOR` presumes a restructure, `IMPLEMENT` and `TEST` presume writing
  something, `EXPLAIN` presumes understanding is the goal, and `DEFAULT` is the
  no-match fallback. That reasoning is in the module docstring, in
  `docs/capabilities.md`, and pinned by tests, including a parametrized case
  over debug-, implementation-, test-, refactor-, explanation- and
  gibberish-worded queries: between them they cover every planner intent except
  `SEARCH`, the planner detects six different intents for them, and the
  capability pins every one to `SEARCH` -- once with the planner stubbed (so the
  override itself is what is asserted) and once with the real planner and the
  real context builder running.
- Retrieval wiring: `ContextQuery(text=query, max_modules=10,
  max_tokens=profile.max_context_tokens, maximum_depth=profile.relationship_depth,
  relationship_expansion=profile.include_callers or profile.include_callees)`.
  `max_symbols` is never passed, so it stays at the `ContextQuery` default of 20;
  `ContextPlan.maximum_depth` is traversal depth and is never reused as a
  candidate count. This matters more here than elsewhere because the `SEARCH`
  rule ships `maximum_depth=0` and `relationship_expansion=False`: the profile
  overrides both, and a test proves a depth-0 plan still yields a
  three-candidate package.
- `REVIEW_PROFILE`: `name="review"`, `include_callers=True`,
  `include_callees=True`, `include_dependencies=True`, `include_dependents=True`,
  `include_tests=True`, `include_dead_code=False`, `include_diagnostics=True`,
  `relationship_depth=2`, `max_context_tokens=4096`; immutable (`frozen`,
  `slots`). Only `relationship_depth`, `max_context_tokens` and the
  caller/callee pair reach `ContextQuery`; a test asserts `ContextQuery` has no
  field for the other five flags, which is what makes them declarative retrieval
  intent rather than hidden behaviour.
- Relationship honesty: first candidate -> `primary_symbol`; remaining
  candidates -> `supporting_symbols` in rank order, deduplicated; candidate
  modules -> `related_modules`, sorted and deduplicated;
  `related_callers`/`related_callees` are empty literals and
  `RelationshipSummary.caller_count`/`callee_count` are `0` with them. Nothing is
  inferred from score order or module membership: `ContextResult` carries no
  verified `CALLS` edge, and a test walks the AST to assert both fields are
  assigned empty list literals, while the permutation probe covers every
  candidate ordering.
- Serialization goes through `SerializerFactory` only, with no capability-local
  bootstrap import of `packages.serializers.openai`; registration stays a
  serialization-layer concern, as centralized in the previous session.

### Limitations

- The capability assembles review context and stops at `ProviderRequest`. It
  produces no review text, no findings, no line comments and no verdict; that
  would need a provider step which deliberately does not live here.
- Five of the nine profile options are declarative: `ContextQuery` has no
  dependency, dependent, test, dead-code or diagnostic switch, so those flags
  document intent without changing retrieval.
- No verified call graph reaches any capability, so every directly executable
  capability publishes empty relationship lists. Supplying real edges is a
  platform change in `ContextResult`, not in a capability.
- `CapabilityResult.selected_symbols` is whatever `RepositoryIndex.find()`
  returned, verbatim: retrieval quality stays the repository layer's contract.
- `execution_time_ms` is wall-clock and the only non-deterministic field; every
  determinism assertion excludes it.

### Results

| Command | Result |
|---------|--------|
| `.\uv.exe run python -m pytest tests\capabilities tests\serializers -q` | 737 passed (626 before; `test_review.py` adds 111) |
| `.\uv.exe run python -m pytest tests\planning tests\context tests\pipeline tests\gateway -q` | 839 passed (unchanged) |
| `.\uv.exe run python -m ruff check packages\capabilities packages\serializers tests\capabilities tests\serializers` | All checks passed |
| `.\uv.exe run python -m mypy packages\capabilities packages\serializers` | Success: no issues found in 23 source files (22 before) |
| `git --no-pager diff --check` | exit 0 (only the pre-existing CRLF conversion warnings) |

Fresh-process execution through the documented import path alone.

Run A -- the shared probe (`assembly_probes.run_in_fresh_interpreter("review",
"ReviewCapability")`, which imports nothing but
`packages.capabilities.review`), three indexed modules, query `"retry policy"`:

```
serializer_module_before        False
serializer_module_after_import  True
registered                      True
primary                         gateway.retry.should_retry
supporting                      [gateway.alt_retry.should_retry, gateway.more_retry.should_retry]
callers / callees               [] / []   (caller_count 0, callee_count 0)
modules                         [gateway/alt_retry.py, gateway/more_retry.py, gateway/retry.py]
provider                        openai   roles [system, user]
context message tail            "Relationship summary: 0 callers, 0 callees, 3 modules, 3 symbols"
```

Run B -- the same import path with the real `ContextPlanner` and the real
`ContextBuilder`, query `"Review the gateway retry policy"`:

```
capability intent               REVIEW
plan intent                     SEARCH   (plan maximum_depth 0, expansion False)
callers / callees               [] / []   (caller_count 0, callee_count 0, 3 modules, 3 symbols)
provider                        openai   roles [system, user]
```

Both runs prove the same two contracts: the documented import makes the
serializer available, and review publishes ranked membership with no invented
edges. `TestFreshProcessImportPath` pins run A in the suite, and
`test_factory_is_the_only_serializer_route` keeps the capability source free of
any serializer-module import.

### Notes For The Next Agent

1. `ReviewCapability` is the general, symbol-level review context assembler. Do
   not fold `ArchitectureReviewCapability` (whole-repository analyzer, its own
   profile, plan synthesized without the planner) or
   `PullRequestReviewCapability` (`"pull-request-review"`, not a framework
   `Capability` subclass) into it, and do not make it emit review findings --
   that belongs to a downstream provider step.
2. If the planner ever gains a `REVIEW` token, `PLANNER_INTENT_FOR_REVIEW` is
   the single line to change; the tests that assert the two vocabularies differ
   are the ones that must then agree with it.
3. Wiring stays opt-in. Registering `"review"` in the gateway, the pipeline, the
   workflows or the controller, or exporting it from a default registry, is a
   separate decision with its own verification, not a cleanup follow-up here.
