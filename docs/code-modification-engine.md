# Code Modification Engine

## Architecture

```
PatchSet --> CodeModificationEngine --> WorkspaceChanges
```

The Code Modification Engine is responsible for applying `PatchSet` objects to a workspace. It is a purely mechanical execution component — it **never** generates patches, performs repository intelligence, or invokes providers.

## Execution Flow

```
WorkflowPlan
      │
ExecutionPlan
      │
EvaluationReport
      │
PatchSet (input)
      │
      ▼
CodeModificationEngine.apply(patch_set, workspace_path)
      │
      ├─► ModificationValidator.validate(patch_set)
      │
      ├─► BackupManager.create_backup(workspace_path, files)
      │
      ├─► WorkspaceFileSystem operations (per PatchFile)
      │     ├─ ADD → write_file
      │     ├─ MODIFY → read_file → compute_hash → write_file
      │     ├─ DELETE → delete_file
      │     └─ RENAME → read_file → write_file(new) → delete_file(old)
      │
      ├─► Statistics collection
      │
      └─► WorkspaceChanges (output)
            │
            └─► On failure: BackupManager.restore_backup()
```

## Responsibilities

### CodeModificationEngine

- Validate `PatchSet` before execution via `ModificationValidator`.
- Create backup of affected files via `BackupManager`.
- Apply patches in deterministic order.
- Collect statistics for each applied file.
- Produce immutable `WorkspaceChanges`.
- Stop on first fatal error.
- Rollback automatically on failure.

### ModificationValidator

- Validate `PatchSet` against defined rules.
- Detect duplicate files, conflicting operations, invalid hunks, invalid rename targets, invalid delete targets, and corrupted `PatchSet`.
- Produce immutable `ValidationResult`.

### BackupManager

- Create deterministic backups before modification.
- Restore workspace from backup on failure.
- Delete backup after successful execution.

### WorkspaceFileSystem

- Read file contents.
- Write file contents.
- Delete files.
- Rename/move files.
- Check file existence.
- Compute SHA-256 hashes.

## Non-Responsibilities

The Code Modification Engine **must NOT**:

- Generate patches.
- Inspect repository semantics.
- Perform AST parsing.
- Invoke providers.
- Decide WHAT to change.
- Modify `PatchSet`.
- Create global mutable state.

## WorkspaceChanges Contract

`WorkspaceChanges` is the canonical output artifact of the Code Modification Engine. It becomes the stable contract consumed by downstream components.

```python
@dataclass(frozen=True, slots=True)
class WorkspaceChanges:
    workflow_name: str
    execution_id: str
    applied_files: tuple[ModifiedFile, ...]
    statistics: ModificationStatistics
    warnings: tuple[str, ...]
    success: bool
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | `str` | The workflow name that triggered this modification. |
| `execution_id` | `str` | Unique execution identifier. |
| `applied_files` | `tuple[ModifiedFile, ...]` | All modified file records in deterministic order. |
| `statistics` | `ModificationStatistics` | Aggregate modification statistics. |
| `warnings` | `tuple[str, ...]` | Warning messages generated during modification. |
| `success` | `bool` | Whether all modifications were applied successfully. |

## Backup Strategy

The backup system creates deterministic timestamped backup directories containing copies of all affected files with their relative paths preserved.

### Backup Directory Structure

```
.modification_backup/
  └── 20260720T220000Z/
      ├── MANIFEST.txt
      ├── src/
      │   ├── main.py
      │   └── utils.py
      └── config/
          └── settings.yaml
```

### Backup Lifecycle

1. **Create**: Before any modification, `BackupManager.create_backup()` is called with the workspace path and a dictionary of affected files.
2. **Restore**: On any failure, `BackupManager.restore_backup()` is called to restore the workspace to its pre-modification state.
3. **Delete**: After successful execution, `BackupManager.delete_backup()` removes the backup directory.

## Rollback Strategy

The engine implements automatic rollback on any fatal error:

1. **Validate**: `PatchSet` is validated before any modification.
2. **Backup**: All affected files are backed up before modification begins.
3. **Apply**: Patches are applied sequentially in deterministic order.
4. **Stop**: On any fatal error, the engine stops immediately.
5. **Rollback**: If any error occurs, the workspace is restored from backup.
6. **Report**: `WorkspaceChanges(success=False)` is returned with error details.

## Public API

### Models

```python
from packages.modification.models import (
    ModifiedFile,
    ModificationStatistics,
    ModificationStatus,
    WorkspaceChanges,
)
```

### Engine

```python
from packages.modification.engine import CodeModificationEngine

changes = CodeModificationEngine.apply(patch_set, workspace_path)
```

### Validator

```python
from packages.modification.validator import ModificationValidator

result = ModificationValidator.validate(patch_set)
```

### Backup

```python
from packages.modification.backup import BackupManager

backup_dir = BackupManager.create_backup(workspace_path, files)
BackupManager.restore_backup(backup_dir, workspace_path)
BackupManager.delete_backup(backup_dir)
```

### Workspace

```python
from packages.modification.workspace import WorkspaceFileSystem

content = WorkspaceFileSystem.read_file(path)
WorkspaceFileSystem.write_file(path, content)
WorkspaceFileSystem.delete_file(path)
WorkspaceFileSystem.rename_file(old_path, new_path)
WorkspaceFileSystem.exists(path)
WorkspaceFileSystem.compute_hash(path)
```

## Integration with Self Verification

The Code Modification Engine is designed for future integration with the Self Verification framework:

1. `WorkspaceChanges` becomes the input to the Self Verification pipeline.
2. Self Verification validates that modifications were applied correctly.
3. If Self Verification fails, the engine can be called again with a rollback `PatchSet`.

## Testing

The test suite covers:

- Model immutability (frozen=True, slots=True)
- ADD, MODIFY, DELETE, RENAME operations
- Rollback on failure
- Backup creation and restore
- Deterministic execution order
- Statistics computation
- Duplicate detection
- Invalid PatchSet rejection
- Partial failure rollback
- Empty PatchSet handling

Target coverage: >95%.