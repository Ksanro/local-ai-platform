"""Engineering Controller — Single public orchestration entry point.

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

Responsibilities
----------------

- Session lifecycle management
- Workflow selection based on operation type
- Error handling and aggregation
- Artifact aggregation into EngineeringResult
- Telemetry recording
- Deterministic execution

Non-responsibilities (MUST NEVER do)
-------------------------------------

- Inspect repositories
- Perform architecture analysis
- Modify code directly
- Generate patches
- Invoke providers directly
- Duplicate workflow logic

Public API
----------

.. code-block:: python

    from packages.controller import EngineeringController, EngineeringRequest, OperationType

    controller = EngineeringController()

    # Execute an engineering request
    result = controller.execute(request)

    # Review code
    result = controller.review(request)

    # Implement a feature
    result = controller.implement(request)

    # Refactor code
    result = controller.refactor(request)

    # Debug an issue
    result = controller.debug(request)

    # Explain code
    result = controller.explain(request)

"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from packages.controller.models import (
    EngineeringRequest,
    EngineeringResult,
    OperationType,
)
from packages.controller.registry import OperationRegistry
from packages.controller.validator import RequestValidator

if TYPE_CHECKING:
    from packages.session.manager import SessionManager  # noqa: F401
    from packages.observability.collector import EngineeringTelemetry  # noqa: F401


# Default workflow mappings for each operation type
_DEFAULT_WORKFLOW_MAP: dict[OperationType, str] = {
    OperationType.EXECUTE: "default-engineering",
    OperationType.REVIEW: "code-review",
    OperationType.IMPLEMENT: "implement-feature",
    OperationType.REFACTOR: "large-refactoring",
    OperationType.DEBUG: "bug-investigation",
    OperationType.EXPLAIN: "code-explanation",
}


class EngineeringController:
    """Single public orchestration entry point of the platform.

    The Controller is the ONLY facade exposed to external consumers.
    Everything else (Workflows, Tasks, Evaluation, Verification, Sessions,
    Execution) is internal implementation.

    The Controller:
    - Accepts EngineeringRequest from any consumer
    - Creates and manages session lifecycle
    - Selects appropriate workflow based on operation type
    - Delegates to internal engines (no duplicated logic)
    - Aggregates all artifacts into EngineeringResult
    - Records telemetry events
    - Handles errors gracefully
    - Enforces deterministic execution

    Attributes:
        validator: Request validator instance.
        registry: Operation registry instance.
        _session_manager: Session lifecycle manager (injected or internal).
        _telemetry: Telemetry collector instance.
    """

    def __init__(
        self,
        session_manager: Any = None,
        telemetry: Any = None,
    ) -> None:
        """Initialize the engineering controller.

        Args:
            session_manager: Optional session manager. Creates internal one if not provided.
            telemetry: Optional telemetry collector. Creates internal one if not provided.
        """
        self.validator = RequestValidator()
        self.registry = OperationRegistry()
        self._session_manager = session_manager
        self._telemetry = telemetry
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if the controller is properly initialized.

        Returns:
            True if the controller is initialized, False otherwise.
        """
        return self._initialized

    def _ensure_initialized(self) -> None:
        """Ensure the controller is properly initialized.

        Registers default operation handlers and validates setup.

        Raises:
            RuntimeError: If the controller cannot be initialized.
        """
        if self._initialized:
            return

        # Register default operations
        self._register_default_operations()
        self._initialized = True

    def _register_default_operations(self) -> None:
        """Register all default operation handlers.

        Each operation maps to a handler method and a default workflow.
        """
        operations = [
            (OperationType.EXECUTE, self._execute_impl, "default-engineering"),
            (OperationType.REVIEW, self._review_impl, "code-review"),
            (OperationType.IMPLEMENT, self._implement_impl, "implement-feature"),
            (OperationType.REFACTOR, self._refactor_impl, "large-refactoring"),
            (OperationType.DEBUG, self._debug_impl, "bug-investigation"),
            (OperationType.EXPLAIN, self._explain_impl, "code-explanation"),
        ]

        for operation, handler, workflow in operations:
            self.registry.register_handler(operation, handler, workflow)

    def execute(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Execute an engineering request.

        The primary entry point for general engineering execution.
        Delegates to the execute_impl internal handler.

        Args:
            request: The engineering request to execute.

        Returns:
            An EngineeringResult with all artifacts.

        Example:
            .. code-block:: python

                request = EngineeringRequest(
                    request_id="req-001",
                    operation=OperationType.EXECUTE,
                    description="Fix the bug in module X",
                    workspace_path="/path/to/workspace",
                )
                result = controller.execute(request)
        """
        return self._process_request(request)

    def review(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Review code and produce a review report.

        Performs code review operations using the code-review workflow.

        Args:
            request: The engineering request for review.

        Returns:
            An EngineeringResult with review artifacts.

        Example:
            .. code-block:: python

                request = EngineeringRequest(
                    request_id="req-002",
                    operation=OperationType.REVIEW,
                    description="Review changes in module X",
                    workspace_path="/path/to/workspace",
                )
                result = controller.review(request)
        """
        return self._process_request(request)

    def implement(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Implement a feature or fix.

        Performs feature implementation using the implement-feature workflow.
        This is a full pipeline operation including autonomous execution.

        Args:
            request: The engineering request for implementation.

        Returns:
            An EngineeringResult with implementation artifacts.

        Example:
            .. code-block:: python

                request = EngineeringRequest(
                    request_id="req-003",
                    operation=OperationType.IMPLEMENT,
                    description="Implement feature X",
                    workspace_path="/path/to/workspace",
                )
                result = controller.implement(request)
        """
        return self._process_request(request)

    def refactor(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Refactor code.

        Performs code refactoring using the large-refactoring workflow.
        This is a full pipeline operation including autonomous execution.

        Args:
            request: The engineering request for refactoring.

        Returns:
            An EngineeringResult with refactoring artifacts.

        Example:
            .. code-block:: python

                request = EngineeringRequest(
                    request_id="req-004",
                    operation=OperationType.REFACTOR,
                    description="Refactor module X",
                    workspace_path="/path/to/workspace",
                )
                result = controller.refactor(request)
        """
        return self._process_request(request)

    def debug(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Debug an issue and investigate bugs.

        Performs bug investigation using the bug-investigation workflow.

        Args:
            request: The engineering request for debugging.

        Returns:
            An EngineeringResult with debugging artifacts.

        Example:
            .. code-block:: python

                request = EngineeringRequest(
                    request_id="req-005",
                    operation=OperationType.DEBUG,
                    description="Debug the crash in module X",
                    workspace_path="/path/to/workspace",
                )
                result = controller.debug(request)
        """
        return self._process_request(request)

    def explain(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Explain code (read-only operation).

        Performs code explanation without any modifications.
        This is a read-only operation that does not modify the workspace.

        Args:
            request: The engineering request for explanation.

        Returns:
            An EngineeringResult with explanation artifacts.

        Example:
            .. code-block:: python

                request = EngineeringRequest(
                    request_id="req-006",
                    operation=OperationType.EXPLAIN,
                    description="Explain how module X works",
                )
                result = controller.explain(request)
        """
        return self._process_request(request)

    def _process_request(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Process an engineering request through the full pipeline.

        This is the core request processing method that:
        1. Validates the request
        2. Ensures controller is initialized
        3. Creates a session
        4. Delegates to the appropriate handler
        5. Aggregates artifacts
        6. Records telemetry
        7. Returns EngineeringResult

        Args:
            request: The engineering request to process.

        Returns:
            An EngineeringResult with all artifacts.
        """
        # Record start telemetry
        self._record_event("controller", "request_received", {
            "request_id": request.request_id,
            "operation": request.operation.value,
        })

        # Step 1: Validate the request
        validation_result = self.validator.validate(request)
        if validation_result.status.value == "INVALID":
            error_msg = "Invalid request: " + "; ".join(validation_result.errors)
            self._record_event("controller", "validation_failed", {
                "request_id": request.request_id,
                "errors": validation_result.errors,
            })
            return EngineeringResult(
                request_id=request.request_id,
                session_id="",
                operation=request.operation,
                status="FAILED",
                error_message=error_msg,
            )

        # Step 2: Ensure controller is initialized
        self._ensure_initialized()

        # Step 3: Get the handler for this operation
        handler = self.registry.get_handler(request.operation)
        if handler is None:
            error_msg = f"No handler registered for operation: {request.operation.value}"
            self._record_event("controller", "handler_not_found", {
                "request_id": request.request_id,
                "operation": request.operation.value,
            })
            return EngineeringResult(
                request_id=request.request_id,
                session_id="",
                operation=request.operation,
                status="FAILED",
                error_message=error_msg,
            )

        # Step 4: Execute the handler
        try:
            self._record_event("controller", "execution_started", {
                "request_id": request.request_id,
                "operation": request.operation.value,
            })

            result = handler(request)

            self._record_event("controller", "execution_completed", {
                "request_id": request.request_id,
                "operation": request.operation.value,
            })

            return result

        except Exception as exc:
            self._record_event("controller", "execution_failed", {
                "request_id": request.request_id,
                "operation": request.operation.value,
                "error": str(exc),
            })
            return EngineeringResult(
                request_id=request.request_id,
                session_id="",
                operation=request.operation,
                status="FAILED",
                error_message=str(exc),
            )

    # -----------------------------------------------------------------------
    # Internal handler implementations
    # -----------------------------------------------------------------------

    def _execute_impl(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Internal execute handler implementation.

        Delegates to the full engineering pipeline:
        WorkflowEngine -> ExecutionEngine -> Evaluation -> Patches -> Modification -> Verification

        Args:
            request: The engineering request.

        Returns:
            An EngineeringResult with all artifacts.
        """
        # Create session
        session_id = self._create_session(request)

        # Delegate to workflow engine
        workflow_plan = self._delegate_to_workflow_engine(request)

        # Delegate to execution engine
        execution_report = self._delegate_to_execution_engine(request, workflow_plan)

        # Delegate to evaluation framework
        evaluation_report = self._delegate_to_evaluation(request, workflow_plan, execution_report)

        # Delegate to patch generator
        patch_set = self._delegate_to_patch_generator(request, workflow_plan, execution_report)

        # Delegate to code modification engine
        workspace_changes = self._delegate_to_modification_engine(patch_set)

        # Delegate to self-verification
        verification_report = self._delegate_to_verification(workspace_changes)

        # Record telemetry
        self._record_event("controller", "execute_completed", {
            "request_id": request.request_id,
            "session_id": session_id,
            "has_workflow_plan": workflow_plan is not None,
            "has_execution_report": execution_report is not None,
            "has_evaluation_report": evaluation_report is not None,
            "has_patch_set": patch_set is not None,
            "has_workspace_changes": workspace_changes is not None,
            "has_verification_report": verification_report is not None,
        })

        return EngineeringResult(
            request_id=request.request_id,
            session_id=session_id,
            operation=request.operation,
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            evaluation_report=evaluation_report,
            patch_set=patch_set,
            workspace_changes=workspace_changes,
            verification_report=verification_report,
            telemetry=self._get_telemetry(),
        )

    def _review_impl(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Internal review handler implementation.

        Delegates to workflow engine and execution engine for review.

        Args:
            request: The engineering request.

        Returns:
            An EngineeringResult with review artifacts.
        """
        session_id = self._create_session(request)

        workflow_plan = self._delegate_to_workflow_engine(request)
        execution_report = self._delegate_to_execution_engine(request, workflow_plan)
        evaluation_report = self._delegate_to_evaluation(request, workflow_plan, execution_report)

        self._record_event("controller", "review_completed", {
            "request_id": request.request_id,
            "session_id": session_id,
        })

        return EngineeringResult(
            request_id=request.request_id,
            session_id=session_id,
            operation=request.operation,
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            evaluation_report=evaluation_report,
            telemetry=self._get_telemetry(),
        )

    def _implement_impl(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Internal implement handler implementation.

        Full pipeline with autonomous execution capability.

        Args:
            request: The engineering request.

        Returns:
            An EngineeringResult with implementation artifacts.
        """
        session_id = self._create_session(request)

        # Full pipeline with autonomous loop
        workflow_plan = self._delegate_to_workflow_engine(request)
        execution_report = self._delegate_to_execution_engine(request, workflow_plan)
        evaluation_report = self._delegate_to_evaluation(request, workflow_plan, execution_report)
        patch_set = self._delegate_to_patch_generator(request, workflow_plan, execution_report)
        workspace_changes = self._delegate_to_modification_engine(patch_set)
        verification_report = self._delegate_to_verification(workspace_changes)

        self._record_event("controller", "implement_completed", {
            "request_id": request.request_id,
            "session_id": session_id,
        })

        return EngineeringResult(
            request_id=request.request_id,
            session_id=session_id,
            operation=request.operation,
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            evaluation_report=evaluation_report,
            patch_set=patch_set,
            workspace_changes=workspace_changes,
            verification_report=verification_report,
            telemetry=self._get_telemetry(),
        )

    def _refactor_impl(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Internal refactor handler implementation.

        Full pipeline with autonomous execution for refactoring.

        Args:
            request: The engineering request.

        Returns:
            An EngineeringResult with refactoring artifacts.
        """
        session_id = self._create_session(request)

        workflow_plan = self._delegate_to_workflow_engine(request)
        execution_report = self._delegate_to_execution_engine(request, workflow_plan)
        evaluation_report = self._delegate_to_evaluation(request, workflow_plan, execution_report)
        patch_set = self._delegate_to_patch_generator(request, workflow_plan, execution_report)
        workspace_changes = self._delegate_to_modification_engine(patch_set)
        verification_report = self._delegate_to_verification(workspace_changes)

        self._record_event("controller", "refactor_completed", {
            "request_id": request.request_id,
            "session_id": session_id,
        })

        return EngineeringResult(
            request_id=request.request_id,
            session_id=session_id,
            operation=request.operation,
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            evaluation_report=evaluation_report,
            patch_set=patch_set,
            workspace_changes=workspace_changes,
            verification_report=verification_report,
            telemetry=self._get_telemetry(),
        )

    def _debug_impl(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Internal debug handler implementation.

        Bug investigation workflow.

        Args:
            request: The engineering request.

        Returns:
            An EngineeringResult with debugging artifacts.
        """
        session_id = self._create_session(request)

        workflow_plan = self._delegate_to_workflow_engine(request)
        execution_report = self._delegate_to_execution_engine(request, workflow_plan)
        verification_report = self._delegate_to_verification(None)

        self._record_event("controller", "debug_completed", {
            "request_id": request.request_id,
            "session_id": session_id,
        })

        return EngineeringResult(
            request_id=request.request_id,
            session_id=session_id,
            operation=request.operation,
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            verification_report=verification_report,
            telemetry=self._get_telemetry(),
        )

    def _explain_impl(
        self,
        request: EngineeringRequest,
    ) -> EngineeringResult:
        """Internal explain handler implementation.

        Read-only code explanation. No modifications.

        Args:
            request: The engineering request.

        Returns:
            An EngineeringResult with explanation artifacts.
        """
        session_id = self._create_session(request)

        # Explain is read-only - only workflow planning, no execution
        workflow_plan = self._delegate_to_workflow_engine(request)

        self._record_event("controller", "explain_completed", {
            "request_id": request.request_id,
            "session_id": session_id,
        })

        return EngineeringResult(
            request_id=request.request_id,
            session_id=session_id,
            operation=request.operation,
            workflow_plan=workflow_plan,
            telemetry=self._get_telemetry(),
        )

    # -----------------------------------------------------------------------
    # Session lifecycle
    # -----------------------------------------------------------------------

    def _create_session(
        self,
        request: EngineeringRequest,
    ) -> str:
        """Create a session for an engineering request.

        Args:
            request: The engineering request.

        Returns:
            The session ID.
        """
        if self._session_manager is not None:
            # Use injected session manager
            session = self._session_manager.create(
                request_id=request.request_id,
                workflow_name=request.workflow_name
                or request.operation.value,
            )
            return session.session_id

        # Generate session ID directly
        return f"sess-{request.request_id}"

    # -----------------------------------------------------------------------
    # Delegation methods (these call existing public APIs)
    # -----------------------------------------------------------------------

    def _delegate_to_workflow_engine(
        self,
        request: EngineeringRequest,
    ) -> Any:
        """Delegate to the WorkflowEngine.

        This method calls the existing WorkflowEngine public API.
        It does NOT perform repository analysis or planning itself.

        Args:
            request: The engineering request.

        Returns:
            WorkflowPlan or None if not applicable.
        """
        # This would import and call:
        # from packages.workflows import WorkflowEngine, WorkflowFactory, WorkflowRegistry
        # The actual implementation would:
        # 1. Create registry
        # 2. Register workflows
        # 3. Create factory
        # 4. Create workflow instance
        # 5. Generate plan
        # For now, return None as placeholder
        return None

    def _delegate_to_execution_engine(
        self,
        request: EngineeringRequest,
        workflow_plan: Any,
    ) -> Any:
        """Delegate to the ExecutionEngine.

        This method calls the existing ExecutionEngine public API.
        It does NOT execute providers directly.

        Args:
            request: The engineering request.
            workflow_plan: The workflow plan from WorkflowEngine.

        Returns:
            ExecutionReport or None if not applicable.
        """
        # This would import and call:
        # from packages.execution import ExecutionEngine
        # The actual implementation would execute the workflow plan
        return None

    def _delegate_to_evaluation(
        self,
        request: EngineeringRequest,
        workflow_plan: Any,
        execution_report: Any,
    ) -> Any:
        """Delegate to the WorkflowEvaluator.

        This method calls the existing EvaluationFramework public API.
        It does NOT perform evaluation itself.

        Args:
            request: The engineering request.
            workflow_plan: The workflow plan.
            execution_report: The execution report.

        Returns:
            EvaluationReport or None if not applicable.
        """
        # This would import and call:
        # from packages.evaluation import WorkflowEvaluator
        return None

    def _delegate_to_patch_generator(
        self,
        request: EngineeringRequest,
        workflow_plan: Any,
        execution_report: Any,
    ) -> Any:
        """Delegate to the PatchGenerator.

        This method calls the existing PatchGenerator public API.
        It does NOT generate patches itself.

        Args:
            request: The engineering request.
            workflow_plan: The workflow plan.
            execution_report: The execution report.

        Returns:
            PatchSet or None if not applicable.
        """
        # This would import and call:
        # from packages.patches import PatchGenerator
        return None

    def _delegate_to_modification_engine(
        self,
        patch_set: Any,
    ) -> Any:
        """Delegate to the CodeModificationEngine.

        This method calls the existing CodeModificationEngine public API.
        It does NOT modify code itself.

        Args:
            patch_set: The patch set to apply.

        Returns:
            WorkspaceChanges or None if not applicable.
        """
        # This would import and call:
        # from packages.modification import CodeModificationEngine
        return None

    def _delegate_to_verification(
        self,
        workspace_changes: Any,
    ) -> Any:
        """Delegate to the SelfVerificationEngine.

        This method calls the existing SelfVerificationEngine public API.
        It does NOT verify itself.

        Args:
            workspace_changes: The workspace changes to verify.

        Returns:
            VerificationReport or None if not applicable.
        """
        # This would import and call:
        # from packages.verification import SelfVerificationEngine
        return None

    # -----------------------------------------------------------------------
    # Telemetry
    # -----------------------------------------------------------------------

    def _record_event(
        self,
        category: str,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Record a telemetry event.

        Args:
            category: Event category (controller, workflow, execution, etc.).
            event_type: Event type name.
            data: Optional event data.
        """
        if self._telemetry is not None:
            try:
                self._telemetry.record_event(category, event_type, data or {})
            except Exception:
                # Telemetry should never break the main flow
                pass

    def _get_telemetry(self) -> Any:
        """Get current telemetry data.

        Returns:
            Telemetry data or None.
        """
        if self._telemetry is not None:
            try:
                return self._telemetry.snapshot()
            except Exception:
                return None
        return None