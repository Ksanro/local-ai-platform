"""Engineering Controller v2 — Central orchestration component.

Implements the deterministic control loop for autonomous engineering sessions.
The controller coordinates existing platform components without duplicating
their responsibilities.

Execution Flow
--------------

EngineeringRequest
    │
    ▼
Planning ──────────────────→ WorkflowPlan
    │
    ▼
Workflow Selection ─────────→ Select workflow from registry
    │
    ▼
Workflow Engine ────────────→ Generate WorkflowPlan
    │
    ▼
Execution Engine ───────────→ ExecuteWorkflow → ExecutionReport
    │
    ▼
Self Verification ──────────→ Verify → VerificationReport
    │
    ▼
Evaluation ─────────────────→ Evaluate → EvaluationReport
    │
    ▼
Controller Decision ────────→ COMPLETE / RETRY / REQUEST_REVIEW / FAIL
    │
    ├── COMPLETE → Final Engineering Result
    ├── RETRY → Loop back to Workflow Engine (if retries available)
    ├── REQUEST_REVIEW → Human review gate
    └── FAIL → Terminate session

Architecture
------------

Gateway ──→ EngineeringControllerV2 ──→ EngineeringSessionV2
                    │
                    ├── WorkflowEngine (public API only)
                    ├── ExecutionEngine (public API only)
                    ├── SelfVerificationEngine (public API only)
                    ├── WorkflowEvaluator (public API only)
                    └── ControllerDecisionMaker (internal)

Responsibilities
----------------

- Select next workflow
- Stop execution
- Retry execution
- Request human review

Non-responsibilities (MUST NEVER do)
-------------------------------------

- Modify repository
- Generate patches
- Invoke providers directly
- Perform verification
- Perform evaluation
- Analyze repositories
- Parse code

Public API
----------

.. code-block:: python

    from packages.controller.controller_v2 import EngineeringControllerV2
    from packages.controller.models_v2 import EngineeringRequestV2

    controller = EngineeringControllerV2()
    result = controller.execute(request)

"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from packages.engineering_memory.memory import EngineeringMemory
    from packages.engineering_memory.models import EngineeringSessionRecord

__all__ = [
    "EngineeringControllerV2",
]


class EngineeringControllerV2:
    """Central orchestration component for autonomous engineering sessions.

    The EngineeringControllerV2 implements a deterministic control loop that
    coordinates existing platform components. It receives engineering requests
    and produces engineering results through a series of orchestrated steps.

    The controller is the SINGLE source of truth for session state and decisions.

    Control Loop Algorithm
    ----------------------

    .. code-block:: python

        def execute(request):
            session = create_session(request)

            while session.iteration < session.max_iterations:
                # 1. Select workflow
                workflow_plan = select_workflow(request, session)

                # 2. Execute workflow (via public API)
                execution_report = execute_workflow(request, workflow_plan)

                # 3. Verify (via public API)
                verification_report = verify(execution_report)

                # 4. Evaluate (via public API)
                evaluation_report = evaluate(workflow_plan, execution_report)

                # 5. Record history
                session = append_history(session, iteration, ...)

                # 6. Make decision
                report = make_decision(...)
                session = append_decision(session, report)

                # 7. Handle decision
                if report.decision == COMPLETE:
                    return build_complete_result(session)
                elif report.decision == FAIL:
                    return build_fail_result(session)
                elif report.decision == REQUEST_REVIEW:
                    return build_review_result(session)
                elif report.decision == RETRY:
                    if should_retry(session.retry_count):
                        session = increment_retry(session)
                        continue  # Loop back
                    else:
                        return build_fail_result(session)

            # Max iterations reached
            return build_fail_result(session)

    Usage
    -----

    .. code-block:: python

        from packages.controller.controller_v2 import EngineeringControllerV2
        from packages.controller.models_v2 import EngineeringRequestV2

        controller = EngineeringControllerV2()

        request = EngineeringRequestV2(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Implement feature X",
        )

        result = controller.execute(request)
        assert result.decision in (
            ControllerDecision.COMPLETE,
            ControllerDecision.RETRY,
            ControllerDecision.REQUEST_REVIEW,
            ControllerDecision.FAIL,
        )
    """

    def __init__(
        self,
        config: ControllerConfig | None = None,
        workflow_selector: Any | None = None,
        workflow_engine: Any | None = None,
        execution_engine: Any | None = None,
        verification_engine: Any | None = None,
        evaluator: Any | None = None,
        memory: Any | None = None,
    ) -> None:
        """Initialize the controller.

        All engines are optional — when not provided, the controller
        uses mock implementations for testing. In production, inject
        real implementations.

        Args:
            config: Controller configuration. When None, uses defaults.
            workflow_selector: Component that selects workflows.
            workflow_engine: Component that generates workflow plans.
            execution_engine: Component that executes workflows.
            verification_engine: Component that verifies execution.
            evaluator: Component that evaluates execution quality.
            memory: EngineeringMemory instance for session persistence.
        """
        self._config = config or ControllerConfig()
        self._workflow_selector = workflow_selector
        self._workflow_engine = workflow_engine
        self._execution_engine = execution_engine
        self._verification_engine = verification_engine
        self._evaluator = evaluator
        self._memory = memory

    @property
    def config(self) -> ControllerConfig:
        """Controller configuration."""
        return self._config

    @property
    def workflow_selector(self) -> Any | None:
        """Workflow selector component (if injected)."""
        return self._workflow_selector

    @property
    def workflow_engine(self) -> Any | None:
        """Workflow engine component (if injected)."""
        return self._workflow_engine

    @property
    def execution_engine(self) -> Any | None:
        """Execution engine component (if injected)."""
        return self._execution_engine

    @property
    def verification_engine(self) -> Any | None:
        """Verification engine component (if injected)."""
        return self._verification_engine

    @property
    def evaluator(self) -> Any | None:
        """Evaluator component (if injected)."""
        return self._evaluator

    @property
    def memory(self) -> Any | None:
        """EngineeringMemory instance (if injected)."""
        return self._memory

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def execute(self, request: EngineeringRequestV2) -> EngineeringResultV2:
        """Execute an engineering request through the control loop.

        This is the main entry point for the controller. It creates a session,
        runs the control loop, and returns the final result.

        Args:
            request: The engineering request to process.

        Returns:
            An EngineeringResultV2 with the final decision and all artifacts.
        """
        session = EngineeringSessionV2.create(
            session_id=f"sess-{uuid.uuid4().hex[:8]}",
            request_id=request.request_id,
            config=request.config,
        )

        try:
            result = self._run_control_loop(request, session)
            return result
        except Exception as exc:
            return EngineeringResultV2(
                request_id=request.request_id,
                session_id=session.session_id,
                decision=ControllerDecision.FAIL,
                status=SessionStatusV2.FAILED,
                session=session,
                error_message=str(exc),
            )

    def execute_with_session(
        self,
        request: EngineeringRequestV2,
        session: EngineeringSessionV2,
    ) -> EngineeringResultV2:
        """Execute an engineering request with an existing session.

        This method allows resuming or continuing an existing session.

        Args:
            request: The engineering request to process.
            session: An existing EngineeringSessionV2 to continue.

        Returns:
            An EngineeringResultV2 with the final decision and all artifacts.
        """
        try:
            result = self._run_control_loop_with_session(request, session)
            return result
        except Exception as exc:
            return EngineeringResultV2(
                request_id=request.request_id,
                session_id=session.session_id,
                decision=ControllerDecision.FAIL,
                status=SessionStatusV2.FAILED,
                session=session,
                error_message=str(exc),
            )

    # -----------------------------------------------------------------------
    # Internal control loop
    # -----------------------------------------------------------------------

    def _run_control_loop(
        self,
        request: EngineeringRequestV2,
        session: EngineeringSessionV2,
    ) -> EngineeringResultV2:
        """Run the deterministic control loop.

        Args:
            request: The engineering request.
            session: The initial session state.

        Returns:
            The final EngineeringResultV2.
        """
        config = request.config or self._config
        retry_count = session.retry_count

        while session.iteration < session.max_iterations:
            session = session.with_iteration(session.iteration + 1)

            # Step 1: Select workflow
            workflow_name = self._select_workflow(request, session)

            # Step 2: Execute workflow (via public API)
            workflow_plan, execution_report = self._execute_workflow(
                request, workflow_name, session
            )

            # Step 3: Verify (via public API)
            verification_report = self._verify(execution_report)

            # Step 4: Evaluate (via public API)
            evaluation_report = self._evaluate(workflow_plan, execution_report)

            # Step 5: Record history
            iteration_entry = SessionHistoryEntry(
                iteration=session.iteration,
                workflow_name=workflow_name,
                workflow_plan=workflow_plan,
                execution_report=execution_report,
                verification_report=verification_report,
                evaluation_report=evaluation_report,
            )
            session = session.append_history(iteration_entry)

            # Step 6: Make decision
            report = ControllerDecisionMaker.make_decision(
                config=config,
                execution_report=execution_report,
                verification_report=verification_report,
                evaluation_report=evaluation_report,
                retry_count=retry_count,
                iteration=session.iteration,
            )

            session = session.append_history(
                SessionHistoryEntry(
                    iteration=session.iteration,
                    workflow_name=workflow_name,
                    controller_report=report,
                )
            )

            # Step 7: Handle decision
            if report.decision == ControllerDecision.COMPLETE:
                session = session.with_status(SessionStatusV2.COMPLETED)
                return self._build_complete_result(request, session, report, workflow_plan, execution_report, verification_report, evaluation_report)

            elif report.decision == ControllerDecision.FAIL:
                session = session.with_status(SessionStatusV2.FAILED)
                return self._build_fail_result(request, session, report, workflow_plan, execution_report, error_message=report.reason)

            elif report.decision == ControllerDecision.REQUEST_REVIEW:
                session = session.with_status(SessionStatusV2.REVIEW_REQUIRED)
                return self._build_review_result(request, session, report, workflow_plan, execution_report, evaluation_report)

            elif report.decision == ControllerDecision.RETRY:
                if RetryPolicy.should_retry(config, retry_count, ControllerDecision.RETRY):
                    retry_count = RetryPolicy.increment_retry(retry_count)
                    session = session.with_retry_count(retry_count)
                    continue  # Loop back to step 2

                # Max retries reached — transition to FAIL
                session = session.with_status(SessionStatusV2.FAILED)
                return self._build_fail_result(
                    request,
                    session,
                    ControllerReport(
                        decision=ControllerDecision.FAIL,
                        reason=f"Max retries ({config.max_retries}) exhausted",
                        iteration=session.iteration,
                        retry_count=retry_count,
                    ),
                    workflow_plan,
                    execution_report,
                )

        # Max iterations reached
        session = session.with_status(SessionStatusV2.FAILED)
        return self._build_fail_result(
            request,
            session,
            ControllerReport(
                decision=ControllerDecision.FAIL,
                reason=f"Max iterations ({session.max_iterations}) reached",
                iteration=session.iteration,
                retry_count=retry_count,
            ),
            workflow_plan if 'workflow_plan' in dir() else None,
            execution_report if 'execution_report' in dir() else None,
        )

    def _run_control_loop_with_session(
        self,
        request: EngineeringRequestV2,
        session: EngineeringSessionV2,
    ) -> EngineeringResultV2:
        """Run the control loop with an existing session state.

        This is used for session resumption and testing.

        Args:
            request: The engineering request.
            session: An existing session with state.

        Returns:
            The final EngineeringResultV2.
        """
        return self._run_control_loop(request, session)

    # -----------------------------------------------------------------------
    # Internal orchestration methods
    # -----------------------------------------------------------------------

    def _select_workflow(
        self,
        request: EngineeringRequestV2,
        session: EngineeringSessionV2,
    ) -> str:
        """Select the next workflow to execute.

        Uses the workflow selector if injected, otherwise falls back to
        the workflow_name from the request or a default.

        Args:
            request: The engineering request.
            session: Current session state.

        Returns:
            The selected workflow name.
        """
        if self._workflow_selector is not None:
            workflow_name = self._workflow_selector.select(
                request, session
            )
            if workflow_name:
                return workflow_name

        # Fall back to request workflow_name
        if request.workflow_name:
            return request.workflow_name

        # Default workflow name
        return "default-engineering-workflow"

    def _execute_workflow(
        self,
        request: EngineeringRequestV2,
        workflow_name: str,
        session: EngineeringSessionV2,
    ) -> tuple[Any, Any]:
        """Execute the workflow via the execution engine.

        This method calls the Execution Engine public API. It NEVER
        bypasses the Execution Engine.

        Args:
            request: The engineering request.
            workflow_name: Selected workflow name.
            session: Current session state.

        Returns:
            Tuple of (workflow_plan, execution_report).
        """
        if self._execution_engine is not None:
            workflow_plan, execution_report = self._execution_engine.execute(
                request, workflow_name, session
            )
            return workflow_plan, execution_report

        # Default mock implementation for testing
        workflow_plan = self._create_mock_workflow_plan(workflow_name)
        execution_report = self._create_mock_execution_report(
            workflow_name, success=True
        )
        return workflow_plan, execution_report

    def _verify(
        self,
        execution_report: Any,
    ) -> Any:
        """Verify execution via the verification engine.

        This method calls the SelfVerificationEngine public API. It NEVER
        performs verification directly.

        Args:
            execution_report: The execution report to verify.

        Returns:
            Verification report.
        """
        if self._verification_engine is not None:
            return self._verification_engine.verify(execution_report)

        # Default mock implementation
        from packages.verification.models import (
            VerificationReport,
            VerificationStatus,
            VerificationStatistics,
        )

        return VerificationReport(
            workflow_name=getattr(execution_report, "workflow_name", "unknown"),
            execution_id=getattr(execution_report, "execution_id", "unknown"),
            verification_status=VerificationStatus.PASSED,
            findings=(),
            statistics=VerificationStatistics(),
            score=1.0,
        )

    def _evaluate(
        self,
        workflow_plan: Any,
        execution_report: Any,
    ) -> Any:
        """Evaluate execution via the evaluator.

        This method calls the WorkflowEvaluator public API. It NEVER
        performs evaluation directly.

        Args:
            workflow_plan: The workflow plan.
            execution_report: The execution report.

        Returns:
            Evaluation report.
        """
        if self._evaluator is not None:
            return self._evaluator.evaluate(workflow_plan, execution_report)

        # Default mock implementation
        from packages.evaluation.models import EvaluationReport

        return EvaluationReport(
            workflow_name=getattr(workflow_plan, "workflow_name", "unknown"),
            task_name="default",
            provider="mock",
            model="mock",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            metrics=(),
            scores=(),
            overall_score=0.9,
            summary="Mock evaluation",
        )

    # -----------------------------------------------------------------------
    # Mock implementations (for testing without real engines)
    # -----------------------------------------------------------------------

    def _create_mock_workflow_plan(self, workflow_name: str) -> Any:
        """Create a mock workflow plan for testing.

        Args:
            workflow_name: Workflow name.

        Returns:
            Mock workflow plan object.
        """
        from types import SimpleNamespace

        return SimpleNamespace(
            workflow_name=workflow_name,
            task_plans=(),
            workflow_steps=(),
            metrics=None,
        )

    def _create_mock_execution_report(
        self,
        workflow_name: str,
        success: bool = True,
    ) -> Any:
        """Create a mock execution report for testing.

        Args:
            workflow_name: Workflow name.
            success: Whether execution succeeded.

        Returns:
            Mock execution report object.
        """
        from types import SimpleNamespace

        return SimpleNamespace(
            workflow_name=workflow_name,
            execution_id=f"exec-{workflow_name}",
            execution_status="COMPLETED" if success else "FAILED",
            total_duration_ms=1000,
            step_results=(),
            adapter_name="mock",
            success=success,
            failures=(),
        )

    # -----------------------------------------------------------------------
    # Result builders
    # -----------------------------------------------------------------------

    def _store_session_record(
        self,
        request: EngineeringRequestV2,
        session: EngineeringSessionV2,
        workflow_name: str,
        execution_report: Any,
        verification_report: Any,
        evaluation_report: Any,
        controller_decision: str,
    ) -> None:
        """Store an engineering session record in memory.

        Called after the control loop completes to persist session facts.

        Args:
            request: Original request.
            session: Final session state.
            workflow_name: Name of the workflow executed.
            execution_report: Execution report.
            verification_report: Verification report.
            evaluation_report: Evaluation report.
            controller_decision: Final controller decision string.
        """
        if self._memory is None:
            return

        # Serialize reports to dicts
        exec_report_dict = self._serialize_report(execution_report)
        verif_report_dict = self._serialize_report(verification_report)
        eval_report_dict = self._serialize_report(evaluation_report)

        # Extract modified modules from metadata
        modified_modules = []
        if hasattr(session, "metadata") and session.metadata:
            modified_modules = session.metadata.get("modified_modules", [])

        # Create the record
        record = EngineeringSessionRecord(
            session_id=session.session_id,
            workflow_name=workflow_name,
            request_summary=getattr(request, "description", ""),
            transaction_id=getattr(request, "request_id", ""),
            execution_report=exec_report_dict,
            verification_report=verif_report_dict,
            evaluation_report=eval_report_dict,
            controller_decision=controller_decision,
            completed_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "modified_modules": modified_modules,
                "iteration_count": session.iteration,
                "request_id": request.request_id,
            },
        )

        # Store in memory
        self._memory.store(record)

    @staticmethod
    def _serialize_report(report: Any) -> dict[str, Any]:
        """Serialize a report object to a dictionary.

        Handles both dict objects and objects with __dict__ or to_dict.

        Args:
            report: The report to serialize.

        Returns:
            Dictionary representation of the report.
        """
        if report is None:
            return {}

        if isinstance(report, dict):
            return report

        # Try to_dict method
        if hasattr(report, "to_dict") and callable(getattr(report, "to_dict")):
            try:
                return report.to_dict()  # type: ignore[no-any-return]
            except Exception:
                pass

        # Try __dict__
        if hasattr(report, "__dict__"):
            try:
                return dict(report.__dict__)  # type: ignore[no-any-return]
            except Exception:
                pass

        # Fallback: empty dict
        return {}

    def _build_complete_result(
        self,
        request: EngineeringRequestV2,
        session: EngineeringSessionV2,
        report: ControllerReport,
        workflow_plan: Any,
        execution_report: Any,
        verification_report: Any,
        evaluation_report: Any,
    ) -> EngineeringResultV2:
        """Build a COMPLETE result.

        Args:
            request: Original request.
            session: Final session state.
            report: Controller decision report.
            workflow_plan: Last workflow plan.
            execution_report: Last execution report.
            verification_report: Last verification report.
            evaluation_report: Last evaluation report.

        Returns:
            EngineeringResultV2 with COMPLETE decision.
        """
        # Store session in memory
        self._store_session_record(
            request=request,
            session=session,
            workflow_name=getattr(workflow_plan, "workflow_name", "unknown"),
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            controller_decision="COMPLETE",
        )

        return EngineeringResultV2(
            request_id=request.request_id,
            session_id=session.session_id,
            decision=ControllerDecision.COMPLETE,
            status=SessionStatusV2.COMPLETED,
            session=session,
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            error_message="",
        )

    def _build_fail_result(
        self,
        request: EngineeringRequestV2,
        session: EngineeringSessionV2,
        report: ControllerReport,
        workflow_plan: Any,
        execution_report: Any,
        error_message: str = "",
    ) -> EngineeringResultV2:
        """Build a FAIL result.

        Args:
            request: Original request.
            session: Final session state.
            report: Controller decision report.
            workflow_plan: Last workflow plan (may be None).
            execution_report: Last execution report (may be None).
            error_message: Error message.

        Returns:
            EngineeringResultV2 with FAIL decision.
        """
        # Store failed session in memory
        self._store_session_record(
            request=request,
            session=session,
            workflow_name=getattr(workflow_plan, "workflow_name", "unknown") if workflow_plan else "unknown",
            execution_report=execution_report,
            verification_report=None,
            evaluation_report=None,
            controller_decision="FAIL",
        )

        return EngineeringResultV2(
            request_id=request.request_id,
            session_id=session.session_id,
            decision=ControllerDecision.FAIL,
            status=SessionStatusV2.FAILED,
            session=session,
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            error_message=error_message or report.reason,
        )

    def _build_review_result(
        self,
        request: EngineeringRequestV2,
        session: EngineeringSessionV2,
        report: ControllerReport,
        workflow_plan: Any,
        execution_report: Any,
        evaluation_report: Any,
    ) -> EngineeringResultV2:
        """Build a REQUEST_REVIEW result.

        Args:
            request: Original request.
            session: Final session state.
            report: Controller decision report.
            workflow_plan: Last workflow plan.
            execution_report: Last execution report.
            evaluation_report: Last evaluation report.

        Returns:
            EngineeringResultV2 with REQUEST_REVIEW decision.
        """
        # Store REQUEST_REVIEW session in memory
        self._store_session_record(
            request=request,
            session=session,
            workflow_name=getattr(workflow_plan, "workflow_name", "unknown"),
            execution_report=execution_report,
            verification_report=None,
            evaluation_report=evaluation_report,
            controller_decision="REQUEST_REVIEW",
        )

        return EngineeringResultV2(
            request_id=request.request_id,
            session_id=session.session_id,
            decision=ControllerDecision.REQUEST_REVIEW,
            status=SessionStatusV2.REVIEW_REQUIRED,
            session=session,
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            evaluation_report=evaluation_report,
            error_message=report.reason,
        )
