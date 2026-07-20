# Patch Generator Framework v1

## Architecture

The Patch Generator is a deterministic transformation layer that converts engineering artifacts into immutable patch descriptions.

```
WorkflowPlan      -->  \
ExecutionPlan     -->  PatchGenerator  -->  PatchSet
EvaluationReport  -->  /
```

The PatchSet becomes the ONLY contract consumed later by the Code Modification Engine.

## Architecture

```
packages/patches/
    __init__.py          # Package entry point, re-exports public API
    models.py            # Immutable dataclass definitions
    generator.py         # PatchGenerator class
    formatter.py         # PatchFormatter class
    validator.py         # PatchValidator class

tests/patches/
    __init__.py          # Test package init
    test_models.py       # Model immutability, construction, edge cases
    test_generator.py    # Deterministic generation, duplicate elimination, statistics
    test_formatter.py    # Deterministic diff formatting
    test_validator.py    # Validation rules, edge cases

docs/patch-generator.md # Architecture documentation
```

## Responsibilities

### What PatchGenerator DOES

- Accepts WorkflowPlan, ExecutionPlan, and optional EvaluationReport as inputs
- Produces deterministic, ordered PatchSet output
- Computes patch statistics (files_changed, hunks, added_lines, removed_lines)
- Generates warnings for edge cases
- Eliminates duplicates
- Returns immutable PatchSet

### What PatchGenerator DOES NOT DO

- Edit files
- Write files
- Inspect the repository
- Parse AST
- Call providers
- Execute git
- Duplicate repository analysis logic

## Public API

### PatchGenerator.generate()

```python
from packages.patches import PatchGenerator

patch_set = PatchGenerator.generate(
    workflow_plan=workflow_plan,
    execution_plan=execution_plan,
    evaluation_report=None,  # optional
)
```

**Responsibilities:**
- Validate input types (public API compliance)
- Build deterministic PatchFile list from engineering artifacts
- Compute statistics (files_changed, hunks, added_lines, removed_lines)
- Generate warnings for edge cases
- Return immutable PatchSet
- Eliminate duplicates
- Produce deterministic ordering (sorted by file_path)

**Constraints:**
- Must NOT call providers
- Must NOT inspect repositories
- Must NOT parse AST
- Must NOT build context
- Must NOT perform planning
- Must NOT write files
- Must NOT execute git
- Must NOT modify inputs
- Must consume only public interfaces
- Must produce deterministic output
- Must eliminate duplicates

### PatchFormatter.format()

```python
from packages.patches import PatchFormatter

diff_text = PatchFormatter.format(patch_set)
```

**Produces:** Deterministic Git unified diff text.

**Constraints:**
- Formatting only
- No validation
- No file system operations
- No repository analysis
- Deterministic output

### PatchValidator.validate()

```python
from packages.patches import PatchValidator

result = PatchValidator.validate(patch_set)
if not result.is_valid:
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
```

**Validation Rules:**

1. **Duplicate files:** No two files with the same path
2. **Duplicate hunks:** No two hunks with identical content in same file
3. **Overlapping hunks:** Hunks in same file must not overlap
4. **Invalid operations:** Operation must be a valid PatchOperation
5. **Invalid line ranges:** old_start, old_count, new_start, new_count >= 0
6. **Empty patches:** Files with no hunks are flagged as warnings
7. **Invalid statistics:** Statistics must match actual file counts

**Constraints:**
- Validation only
- Must NOT modify PatchSet
- No file system operations
- No repository inspection
- Must produce deterministic output

## Patch Lifecycle

```
1. WorkflowPlan created by Planner
2. ExecutionPlan created by ExecutionEngine
3. (Optional) EvaluationReport created by Evaluator
4. PatchGenerator.generate() produces PatchSet
5. PatchValidator.validate() checks PatchSet integrity
6. PatchFormatter.format() produces diff text
7. PatchSet consumed by Code Modification Engine
```

## PatchSet Contract

The PatchSet is the canonical output artifact of the Patch Generator. It is consumed by the Code Modification Engine as the sole source of truth for patch operations.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | `str` | The workflow name that generated this patch set |
| `execution_id` | `str` | Unique execution identifier |
| `generated_from` | `tuple[str, ...]` | Originating engineering artifact references |
| `files` | `tuple[PatchFile, ...]` | All patch files in deterministic order |
| `statistics` | `PatchStatistics` | Aggregate statistics for the patch set |
| `warnings` | `tuple[str, ...]` | Warning messages for this patch set |

### PatchFile

| Field | Type | Description |
|-------|------|-------------|
| `path` | `str` | File path relative to repository root |
| `operation` | `PatchOperation` | ADD, DELETE, MODIFY, or RENAME |
| `hunks` | `tuple[PatchHunk, ...]` | Diff hunks for this file |
| `estimated_changed_lines` | `int` | Estimated total changed lines |
| `metadata` | `dict[str, Any]` | Additional metadata |

### PatchHunk

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | `str` | Path to the file this hunk belongs to |
| `old_start` | `int` | Starting line number in the old file (1-based) |
| `old_count` | `int` | Number of lines in the old file |
| `new_start` | `int` | Starting line number in the new file (1-based) |
| `new_count` | `int` | Number of lines in the new file |
| `diff_lines` | `tuple[str, ...]` | Unified diff content lines |

### PatchOperation

| Value | Description |
|-------|-------------|
| `ADD` | New file being added |
| `DELETE` | Existing file being deleted |
| `MODIFY` | Existing file being modified |
| `RENAME` | File being renamed (delete old + add new) |

### PatchStatistics

| Field | Type | Description |
|-------|------|-------------|
| `files_changed` | `int` | Number of files with patches |
| `hunks` | `int` | Total number of hunks across all files |
| `added_lines` | `int` | Total number of added lines |
| `removed_lines` | `int` | Total number of removed lines |
| `modified_lines` | `int` | Total number of modified files |

## Future Integration with Code Modification Engine

The PatchSet is designed to be consumed by the Code Modification Engine, which will:

1. Receive the PatchSet as input
2. Validate the PatchSet using `PatchValidator.validate()`
3. Apply each PatchFile's hunks to the corresponding file
4. Handle ADD, DELETE, MODIFY, and RENAME operations
5. Report success or failure for each operation

The Code Modification Engine will never need to:
- Parse source code
- Inspect the repository directly
- Execute shell commands
- Call providers

All patch information is contained within the PatchSet.

## Testing

Comprehensive test coverage (>95%) is provided for:

- **test_models.py:** Immutability, construction, edge cases
- **test_generator.py:** Deterministic generation, duplicate elimination, statistics
- **test_formatter.py:** Deterministic diff formatting
- **test_validator.py:** Validation rules, edge cases

## Project Convention Compliance

| Convention | Implementation |
|------------|----------------|
| `frozen=True`, `slots=True` | All dataclasses |
| Strict typing | All public methods fully typed |
| Deterministic behaviour | Sorted output, no randomness |
| Explicit `__all__` | All modules export `__all__` |
| No hidden state | Stateless functions |
| No singleton | No module-level mutable state |
| No global mutable state | Pure functions |
| Consume only public APIs | WorkflowPlan, ExecutionPlan, EvaluationReport |
| No architectural layer violations | Patches only consumes Workflow/Execution/Evaluation |
| Comprehensive docstrings | All modules, classes, methods documented |
| Production-quality | Full error handling, edge cases |