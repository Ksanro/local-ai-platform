"""Workflow pipeline stage.

Selects and executes a workflow from the workflow registry, producing
a WorkflowPlan that is consumed by the ExecutionStage.

Architecture
------------

PipelineContext
       |
       v
WorkflowStage
       |
       |-- WorkflowRegistry   (lookup registered workflows)
       |-- WorkflowFactory    (create workflow instance)
       |-- WorkflowEngine     (generate WorkflowPlan)
       |
       v
PipelineContext.workflow_plan

The stage is an orchestration layer only. It never performs repository
analysis, planning, or invokes providers.

Constraints
-----------

The stage
- must not call providers
- must not parse repositories
- must not perform ranking
- must not serialize
- must not edit source code

The stage only invokes the WorkflowEngine through its public API.
"""

from __future__ import annotations

import logging

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.tasks.models import TaskRequest
from packages.workflows.engine import WorkflowEngine
from packages.workflows.factory import WorkflowFactory
from packages.workflows.registry import WorkflowRegistry

logger = logging.getLogger(__name__)

# Default workflow name used when no explicit selection is provided.
_DEFAULT_WORKFLOW = "implement-feature"


class WorkflowStage(PipelineStage):
    """Pipeline stage that selects and executes a workflow.

    Orchestrates workflow selection from the registry, invokes the
    WorkflowEngine to generate a WorkflowPlan, and stores the result
    in PipelineContext.workflow_plan.

    Attributes:
        _registry: The workflow registry containing registered workflows.
        _engine: The workflow engine for plan generation.
    """

    def __init__(
        self,
        registry: WorkflowRegistry | None = None,
        engine: WorkflowEngine | None = None,
    ) -> None:
        """Initialize with optional registry and engine.

        Args:
            registry: The WorkflowRegistry to use. Defaults to new registry.
            engine: The WorkflowEngine to use. Defaults to new engine.
        """
        self._registry = registry if registry is not None else WorkflowRegistry()
        self._engine = engine if engine is not None else WorkflowEngine()

        # Register default workflow if registry is empty.
        if not self._registry.list_workflows():
            self._register_default_workflow()

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "workflow"

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Check if workflow execution is enabled.

        Reads the ``workflow_enabled`` flag from context metadata.
        Defaults to ``True`` when the flag is absent.

        If disabled, records a no-op result and skips ``execute()``.

        Args:
            context: The pipeline context.

        Returns:
            A no-op result if workflow is disabled, or ``None`` to
            proceed with ``execute()``.
        """
        workflow_enabled = context.get_metadata("workflow_enabled", True)
        if not workflow_enabled:
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data={"workflow_enabled": False},
            )
        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Execute the workflow and produce a WorkflowPlan.

        Reads the workflow name from context metadata (defaults to
        ``_DEFAULT_WORKFLOW``), creates a workflow instance via the
        factory, generates a TaskRequest from the context, and invokes
        the WorkflowEngine.

        Stores the WorkflowPlan in ``context.workflow_plan``.

        On any exception, logs the error and returns a failed result.

        Args:
            context: The pipeline context with request data.

        Returns:
            A PipelineStageResult with the WorkflowPlan on success.
        """
        request_id = context.request_id

        try:
            # Determine workflow name.
            workflow_name = context.get_metadata(
                "workflow_name", _DEFAULT_WORKFLOW
            )

            # Create factory from registry.
            factory = WorkflowFactory(self._registry)

            # Create workflow instance.
            workflow = factory.create(workflow_name)

            # Build TaskRequest from context.
            task_request = self._build_task_request(context)

            # Get repository index from metadata (set by repository_context stage).
            repository_index = context.get_metadata("repository_index")

            # Generate WorkflowPlan.
            workflow_plan = self._engine.generate_plan(
                workflow=workflow,
                repository_index=repository_index,
                request=task_request,
            )

            # Store in context.
            context.workflow_plan = workflow_plan

            # Also store in metadata for downstream access.
            context.set_metadata("workflow_plan", workflow_plan)

            logger.info(
                "workflow request_id=%s workflow=%s steps=%d",
                request_id,
                workflow_plan.workflow_name,
                len(workflow_plan.workflow_steps),
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=workflow_plan,
            )

        except Exception as exc:
            logger.error(
                "workflow request_id=%s error=%s",
                context.request_id,
                exc,
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=False,
                error=str(exc),
                exception=exc,
            )

    async def after(
        self, context: PipelineContext, result: PipelineStageResult
    ) -> PipelineStageResult | None:
        """Log stage completion.

        Args:
            context: The pipeline context.
            result: The result from this stage.

        Returns:
            ``None`` to keep the existing result.
        """
        if result.success:
            plan = context.workflow_plan
            if plan is not None:
                logger.info(
                    "workflow request_id=%s workflow=%s steps=%d",
                    context.request_id,
                    getattr(plan, "workflow_name", "unknown"),
                    len(getattr(plan, "workflow_steps", ())),
                )
            else:
                logger.info(
                    "workflow request_id=%s status=ok",
                    context.request_id,
                )
        else:
            logger.error(
                "workflow request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None

    @staticmethod
    def _build_task_request(context: PipelineContext) -> TaskRequest:
        """Build a TaskRequest from the pipeline context.

        Extracts the query text and repository root from the context.

        Args:
            context: The pipeline context.

        Returns:
            A TaskRequest instance.
        """
        # Extract query from messages.
        query = ""
        request = context.request
        if isinstance(request, dict):
            messages = request.get("messages", [])
            for message in messages:
                if isinstance(message, dict) and message.get("role") == "user":
                    content = message.get("content", "")
                    if isinstance(content, str):
                        query = content.strip()

        repository_root = request.get(
            "repository_root", "."
        ) if isinstance(request, dict) else "."

        return TaskRequest(
            query=query,
            repository_root=repository_root,
        )

    def _register_default_workflow(self) -> None:
        """Register the default implement-feature workflow.

        Creates a minimal workflow that represents a feature implementation
        task. This ensures the stage works even when no workflows are
        explicitly registered.
        """
        # Import here to avoid circular imports at module level.
        from packages.workflows.base import Workflow
        from packages.workflows.models import WorkflowNode

        class _ImplementFeatureWorkflow(Workflow):
            """Default implement-feature workflow."""

            @property
            def name(self) -> str:
                return "implement-feature"

            @property
            def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
                return (
                    WorkflowNode(
                        node_id="analyze",
                        task=self._make_task_class("analyze"),
                        depends_on=(),
                    ),
                )

            def _validate_request(self, request: object) -> None:
                pass

            def _do_plan(self, repository_index: object, request: object) -> object:
                from packages.workflows.models import (
                    WorkflowMetrics,
                    WorkflowPlan,
                    WorkflowStep,
                )
                from packages.tasks.models import TaskConstraint, TaskComplexity

                # Create a minimal WorkflowPlan.
                return WorkflowPlan(
                    workflow_name=self.name,
                    task_plans=(),
                    workflow_steps=(
                        WorkflowStep(
                            step_id="step-analyze",
                            order=0,
                            workflow_node="analyze",
                            task_name="analyze",
                            description="Analyze the request",
                        ),
                    ),
                    metrics=WorkflowMetrics(
                        estimated_tokens=0,
                        estimated_duration_ms=0,
                        estimated_complexity=TaskComplexity.LOW,
                    ),
                    constraints=(),
                )

            def _do_estimate(self, repository_index: object, request: object) -> object:
                from packages.workflows.models import WorkflowMetrics

                return WorkflowMetrics()

            def _make_task_class(self, name: str) -> type:
                """Create a minimal task class."""
                from packages.tasks.base import Task
                from packages.tasks.models import (
                    TaskPlan,
                    TaskRequest,
                    TaskStep,
                )

                class _MinimalTask(Task):
                    @property
                    def name(self) -> str:
                        return name

                    @property
                    def description(self) -> str:
                        return f"Minimal {name} task"

                    def plan(
                        self,
                        repository_index: object,
                        request: TaskRequest,
                    ) -> TaskPlan:
                        return TaskPlan(
                            task_name=self.name,
                            description=self.description,
                            steps=(),
                            context_package=None,
                            metrics=None,
                            constraints=(),
                        )

                return _MinimalTask

        # Register the workflow.
        self._registry.register("implement-feature", _ImplementFeatureWorkflow)