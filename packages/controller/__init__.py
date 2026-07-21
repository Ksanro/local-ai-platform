"""Engineering Controller package — Single public orchestration entry point.

The EngineeringController is the ONLY public API exposed to future:
- CLI
- VSCode Extension
- JetBrains Plugin
- Web UI
- REST API
- MCP Server
- Agent integrations

Everything else becomes internal implementation.

Architecture
------------

User Request
      │
      ▼
EngineeringController
      │
      ├── SessionManager
      ├── WorkflowEngine
      ├── ExecutionEngine
      ├── EvaluationFramework
      ├── PatchGenerator
      ├── CodeModificationEngine
      ├── SelfVerification
      ├── Observability
      └── AutonomousEngineering (optional)
      │
      ▼
EngineeringResult

Public API
----------

.. code-block:: python

    from packages.controller import (
        # Models
        EngineeringRequest,
        EngineeringResult,
        OperationType,
        RequestValidationResult,
        ValidationStatus,
        ValidationSeverity,
        # Controller
        EngineeringController,
        # Registry
        OperationRegistry,
        # Validator
        RequestValidator,
    )

    # Create controller
    controller = EngineeringController()

    # Create request
    request = EngineeringRequest(
        request_id="req-001",
        operation=OperationType.EXECUTE,
        description="Fix the bug in module X",
        workspace_path="/path/to/workspace",
    )

    # Execute
    result = controller.execute(request)

    # Access result
    print(f"Status: {result.status}")
    print(f"Session: {result.session_id}")
    print(f"Error: {result.error_message}")

"""

from __future__ import annotations

__all__ = [
    # Models
    "EngineeringRequest",
    "EngineeringResult",
    "OperationType",
    "RequestValidationResult",
    "ValidationSeverity",
    "ValidationStatus",
    # Controller
    "EngineeringController",
    # Registry
    "OperationRegistry",
    # Validator
    "RequestValidator",
]

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

from packages.controller.models import (
    EngineeringRequest,
    EngineeringResult,
    OperationType,
    RequestValidationResult,
    ValidationSeverity,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

from packages.controller.controller import EngineeringController

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from packages.controller.registry import OperationRegistry

# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

from packages.controller.validator import RequestValidator