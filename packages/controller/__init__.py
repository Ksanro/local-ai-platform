"""Engineering Controller package — Single public orchestration entry point.

The EngineeringController is the ONLY public API exposed to future:
- CLI
- VSCode Extension
- JetBrains Plugin
- Web UI
- REST API
- MCP Server
- Agent integrations

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
        # Controller
        EngineeringController,
        # Registry
        OperationRegistry,
        # Validator
        RequestValidator,
        # v2 Controller
        EngineeringControllerV2,
        # v2 Models
        ControllerConfig,
        ControllerDecision,
        EngineeringRequestV2,
        EngineeringResultV2,
        EngineeringSessionV2,
    )

    # Legacy controller
    controller = EngineeringController()

    # v2 controller (new)
    controller_v2 = EngineeringControllerV2()

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
    # v2 Controller
    "EngineeringControllerV2",
    # v2 Models
    "ControllerConfig",
    "ControllerDecision",
    "ControllerReport",
    "EngineeringRequestV2",
    "EngineeringResultV2",
    "EngineeringSessionV2",
    "SessionHistoryEntry",
    "SessionStatusV2",
    # v2 Components
    "ControllerDecisionMaker",
    "RetryPolicy",
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

# ---------------------------------------------------------------------------
# v2 Controller
# ---------------------------------------------------------------------------

from packages.controller.controller_v2 import EngineeringControllerV2
from packages.controller.decision import ControllerDecisionMaker
from packages.controller.models_v2 import (
    ControllerConfig,
    ControllerDecision,
    ControllerReport,
    EngineeringRequestV2,
    EngineeringResultV2,
    EngineeringSessionV2,
    SessionHistoryEntry,
    SessionStatusV2,
)
from packages.controller.retry_policy import RetryPolicy