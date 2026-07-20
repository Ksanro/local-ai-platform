"""Workflow Evaluator.

Consumes existing public APIs and produces EvaluationReport objects.
The evaluator never calls providers, parses repositories, builds context,
or performs planning.

Architecture
------------

WorkflowPlan      -->  \
ExecutionReport   -->  WorkflowEvaluator  -->  EvaluationReport
CapabilityResult  -->  /
TaskPlan          -->  /
ProviderResponse  -->  /

Responsibilities
----------------

- Validate input types (public API compliance).
- Compute deterministic metrics from platform outputs.
- Calculate category scores from metrics.
- Compute overall weighted score.
- Produce immutable EvaluationReport.

Non-responsibilities
--------------------

- No provider calls.
- No repository inspection.
- No AST parsing.
- No context building.
- No planning.
- No ranking.
- No semantic evaluation.

Public API
----------

.. code-block:: python

    from packages.evaluation.evaluator import WorkflowEvaluator

    report = WorkflowEvaluator.evaluate(
        workflow_plan=workflow_plan,
        execution_report=execution_report,
        capability_result=capability_result,
    )

"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from packages.evaluation.metrics import (
    compute_architecture_findings_count,
    compute_context_compression_ratio,
    compute_context_utilization,
    compute_diagnostics_collected,
    compute_execution_consistency,
    compute_execution_duration_ms,
    compute_identifier_stability,
    compute_selected_modules_count,
    compute_selected_relationships_count,
    compute_selected_symbols_count,
    compute_throughput,
    compute_total_tokens,
    compute_workflow_completeness,
)
from packages.evaluation.models import (
    EvaluationMetric,
    EvaluationReport,
    EvaluationScore,
)
from packages.evaluation.scoring import (
    CATEGORY_DEFINITIONS,
    CATEGORY_WEIGHTS,
    calculate_category_score,
    calculate_overall_score,
)

if TYPE_CHECKING:
    from packages.capabilities.models import CapabilityResult  # noqa: F401
    from packages.workflows.models import WorkflowPlan  # noqa: F401

__all__ = [
    "WorkflowEvaluator",
]


# ---------------------------------------------------------------------------
# WorkflowEvaluator
# ---------------------------------------------------------------------------


class WorkflowEvaluator:
    """Evaluates engineering workflow executions.

    The evaluator consumes only public interfaces. It never knows
    which implementation is behind any input.

    Constraints
    -----------

    - Must NOT call providers.
    - Must NOT inspect repositories.
    - Must NOT parse AST.
    - Must NOT build context.
    - Must NOT perform planning.
    - Must NOT rank symbols.
    - Must NOT modify inputs.
    - Must consume only public interfaces.

    Usage
    -----

    .. code-block:: python

        from packages.evaluation.evaluator import WorkflowEvaluator
        from packages.workflows.models import WorkflowPlan
        from packages.execution.runtime_models import ExecutionReport

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )
    """

    @staticmethod
    def evaluate(
        workflow_plan: Any,
        execution_report: Any,
        capability_result: Any = None,
        task_plan: Any = None,
        provider_response: Any = None,
    ) -> EvaluationReport:
        """Evaluate a workflow execution and produce an EvaluationReport.

        This is the main entry point for the WorkflowEvaluator. It
        validates input types, computes metrics, calculates scores,
        and returns an immutable EvaluationReport.

        Args:
            workflow_plan: A WorkflowPlan-like object with:
                - workflow_name: str
                - task_plans: tuple
                - metrics: object with estimated_tokens: int
            execution_report: An ExecutionReport-like object with:
                - workflow_name: str
                - execution_status: str
                - total_duration_ms: int
                - step_results: tuple of dicts with 'duration_ms'
                - success: bool
                - failures: tuple
            capability_result: Optional CapabilityResult-like object with:
                - selected_symbols: tuple[str, ...]
                - selected_modules: tuple[str, ...]
                - estimated_tokens: int
            task_plan: Optional TaskPlan-like object with:
                - task_name: str
                - constraints: tuple
            provider_response: Optional dict-like object with:
                - completion_tokens: int
                - prompt_tokens: int

        Returns:
            An immutable EvaluationReport with computed metrics and scores.
        """
        started_at = datetime.now(timezone.utc).isoformat()

        # Extract workflow name
        workflow_name = _get_workflow_name(workflow_plan, execution_report)
        task_name = _get_task_name(task_plan)

        # Extract provider and model info
        provider = _get_provider(provider_response)
        model = _get_model(provider_response)

        # Compute metrics
        metrics = WorkflowEvaluator._compute_all_metrics(
            capability_result=capability_result,
            execution_report=execution_report,
            provider_response=provider_response,
        )

        # Compute scores
        scores = WorkflowEvaluator._compute_all_scores(metrics)

        # Compute overall score
        overall_score = calculate_overall_score(scores)

        # Generate summary
        summary = WorkflowEvaluator._generate_summary(
            workflow_name=workflow_name,
            task_name=task_name,
            overall_score=overall_score,
            scores=scores,
            execution_report=execution_report,
        )

        completed_at = datetime.now(timezone.utc).isoformat()

        report = EvaluationReport(
            workflow_name=workflow_name,
            task_name=task_name,
            provider=provider,
            model=model,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
            scores=scores,
            overall_score=overall_score,
            summary=summary,
        )

        return report

    @staticmethod
    def _compute_all_metrics(
        capability_result: Any,
        execution_report: Any,
        provider_response: Any,
    ) -> tuple[EvaluationMetric, ...]:
        """Compute all evaluation metrics from platform outputs.

        Args:
            capability_result: CapabilityResult-like object.
            execution_report: ExecutionReport-like object.
            provider_response: Provider response dict-like object.

        Returns:
            Tuple of all computed EvaluationMetric objects.
        """
        metrics: list[EvaluationMetric] = []

        # Context Quality Metrics
        metrics.extend(WorkflowEvaluator._compute_context_metrics(
            capability_result,
            provider_response,
        ))

        # Execution Quality Metrics
        metrics.extend(WorkflowEvaluator._compute_execution_metrics(
            execution_report,
            provider_response,
        ))

        # Engineering Quality Metrics
        metrics.extend(WorkflowEvaluator._compute_engineering_metrics(
            capability_result,
            execution_report,
        ))

        # Performance Metrics
        metrics.extend(WorkflowEvaluator._compute_performance_metrics(
            execution_report,
            provider_response,
        ))

        # Determinism Metrics (placeholder — real values come from
        # repeated executions stored externally)
        metrics.extend(WorkflowEvaluator._compute_determinism_metrics())

        return tuple(metrics)

    @staticmethod
    def _compute_context_metrics(
        capability_result: Any,
        provider_response: Any = None,
    ) -> list[EvaluationMetric]:
        """Compute context quality metrics.

        Args:
            capability_result: CapabilityResult-like object.
            provider_response: Provider response dict-like object.

        Returns:
            List of context quality EvaluationMetric objects.
        """
        result: list[EvaluationMetric] = []

        if capability_result is None:
            return result

        # Get selected symbols count
        symbols = getattr(capability_result, "selected_symbols", ())
        if symbols:
            value = compute_selected_symbols_count(symbols)
            result.append(EvaluationMetric(
                name="selected_symbols_count",
                value=value,
                weight=0.25,
                passed=value > 0,
                metadata={"description": "Count of selected symbols"},
            ))

        # Get selected modules count
        modules = getattr(capability_result, "selected_modules", ())
        if modules:
            value = compute_selected_modules_count(modules)
            result.append(EvaluationMetric(
                name="selected_modules_count",
                value=value,
                weight=0.25,
                passed=value > 0,
                metadata={"description": "Count of selected modules"},
            ))

        # Get estimated tokens from capability result
        estimated_tokens = getattr(capability_result, "estimated_tokens", 0)

        # Context compression ratio and utilization
        if estimated_tokens and provider_response is not None:
            actual_prompt_tokens = 0
            if isinstance(provider_response, dict):
                actual_prompt_tokens = provider_response.get(
                    "prompt_tokens", 0
                )

            if estimated_tokens > 0 or actual_prompt_tokens > 0:
                compression = compute_context_compression_ratio(
                    estimated_tokens, actual_prompt_tokens
                )
                result.append(EvaluationMetric(
                    name="context_compression_ratio",
                    value=compression,
                    weight=0.50,
                    passed=compression >= 0.5,
                    metadata={
                        "description": "Compression ratio of context",
                        "estimated": estimated_tokens,
                        "actual": actual_prompt_tokens,
                    },
                ))

                utilization = compute_context_utilization(
                    estimated_tokens, actual_prompt_tokens
                )
                result.append(EvaluationMetric(
                    name="context_utilization",
                    value=utilization,
                    weight=0.50,
                    passed=0.5 <= utilization <= 1.5,
                    metadata={
                        "description": "Context utilization ratio",
                        "estimated": estimated_tokens,
                        "actual": actual_prompt_tokens,
                    },
                ))

        return result

    @staticmethod
    def _compute_execution_metrics(
        execution_report: Any,
        provider_response: Any,
    ) -> list[EvaluationMetric]:
        """Compute execution quality metrics.

        Args:
            execution_report: ExecutionReport-like object.
            provider_response: Provider response dict-like object.

        Returns:
            List of execution quality EvaluationMetric objects.
        """
        result: list[EvaluationMetric] = []

        # Execution duration
        step_results = getattr(execution_report, "step_results", ())
        if step_results:
            # Convert to list of dicts for metric computation
            step_dicts = []
            for sr in step_results:
                if isinstance(sr, dict):
                    step_dicts.append(sr)
                elif hasattr(sr, "__dict__"):
                    step_dicts.append(sr.__dict__)
                elif hasattr(sr, "metadata"):
                    step_dicts.append({"duration_ms": sr.metadata.get("duration_ms", 0)})
                else:
                    step_dicts.append({"duration_ms": 0})

            duration = compute_execution_duration_ms(tuple(step_dicts))
            result.append(EvaluationMetric(
                name="execution_duration_ms",
                value=duration,
                weight=0.30,
                passed=duration < 300000,  # Less than 5 minutes
                metadata={"description": "Total execution duration"},
            ))

        # Total tokens
        if provider_response is not None:
            completion_tokens = 0
            prompt_tokens = 0
            if isinstance(provider_response, dict):
                completion_tokens = provider_response.get(
                    "completion_tokens", 0
                )
                prompt_tokens = provider_response.get(
                    "prompt_tokens", 0
                )

            if completion_tokens > 0 or prompt_tokens > 0:
                total = compute_total_tokens(completion_tokens, prompt_tokens)
                result.append(EvaluationMetric(
                    name="total_tokens",
                    value=total,
                    weight=0.30,
                    passed=total < 100000,  # Less than 100K tokens
                    metadata={
                        "description": "Total token count",
                        "completion_tokens": completion_tokens,
                        "prompt_tokens": prompt_tokens,
                    },
                ))

        return result

    @staticmethod
    def _compute_engineering_metrics(
        capability_result: Any,
        execution_report: Any,
    ) -> list[EvaluationMetric]:
        """Compute engineering quality metrics.

        Args:
            capability_result: CapabilityResult-like object.
            execution_report: ExecutionReport-like object.

        Returns:
            List of engineering quality EvaluationMetric objects.
        """
        result: list[EvaluationMetric] = []

        # Workflow completeness
        success = getattr(execution_report, "success", False)
        if success:
            completeness = 1.0
        else:
            # Partial credit based on success
            failures = getattr(execution_report, "failures", ())
            total_steps = len(getattr(execution_report, "step_results", ()))
            completed_steps = total_steps - len(failures) if failures else total_steps
            completeness = compute_workflow_completeness(
                completed_steps, total_steps
            )

        result.append(EvaluationMetric(
            name="workflow_completeness",
            value=completeness,
            weight=0.40,
            passed=completeness >= 0.8,
            metadata={"description": "Workflow completion ratio"},
        ))

        # Diagnostics collected (from capability result investigation report)
        if capability_result is not None:
            investigation_report = getattr(
                capability_result, "investigation_report", None
            )
            if investigation_report:
                diagnostics = compute_diagnostics_collected(
                    investigation_report
                )
                result.append(EvaluationMetric(
                    name="diagnostics_collected",
                    value=diagnostics,
                    weight=0.30,
                    passed=diagnostics > 0,
                    metadata={"description": "Count of diagnostics collected"},
                ))

                # Architecture findings
                arch_findings = compute_architecture_findings_count(
                    investigation_report
                )
                result.append(EvaluationMetric(
                    name="architecture_findings_count",
                    value=arch_findings,
                    weight=0.30,
                    passed=arch_findings >= 0,
                    metadata={
                        "description": "Count of architecture findings"
                    },
                ))

        return result

    @staticmethod
    def _compute_performance_metrics(
        execution_report: Any,
        provider_response: Any,
    ) -> list[EvaluationMetric]:
        """Compute performance metrics.

        Args:
            execution_report: ExecutionReport-like object.
            provider_response: Provider response dict-like object.

        Returns:
            List of performance EvaluationMetric objects.
        """
        result: list[EvaluationMetric] = []

        # Throughput
        if provider_response is not None:
            completion_tokens = 0
            prompt_tokens = 0
            if isinstance(provider_response, dict):
                completion_tokens = provider_response.get(
                    "completion_tokens", 0
                )
                prompt_tokens = provider_response.get(
                    "prompt_tokens", 0
                )

            total_tokens = completion_tokens + prompt_tokens
            total_duration_ms = getattr(
                execution_report, "total_duration_ms", 0
            )

            if total_tokens > 0 and total_duration_ms > 0:
                throughput = compute_throughput(total_tokens, total_duration_ms)
                result.append(EvaluationMetric(
                    name="throughput",
                    value=throughput,
                    weight=0.50,
                    passed=throughput > 0,
                    metadata={
                        "description": "Token throughput (tokens/second)",
                        "total_tokens": total_tokens,
                        "duration_ms": total_duration_ms,
                    },
                ))

        return result

    @staticmethod
    def _compute_determinism_metrics() -> list[EvaluationMetric]:
        """Compute determinism metrics.

        These metrics require repeated execution data which is
        typically stored externally. Returns placeholder metrics
        with neutral values.

        Returns:
            List of determinism EvaluationMetric objects.
        """
        result: list[EvaluationMetric] = []

        # Execution consistency — requires repeated execution data
        # stored externally. Placeholder returns 1.0 (perfect).
        result.append(EvaluationMetric(
            name="execution_consistency",
            value=1.0,
            weight=0.50,
            passed=True,
            metadata={
                "description": "Execution consistency across runs",
                "note": "Real values require external repeated execution data",
            },
        ))

        # Identifier stability — requires repeated execution data
        # stored externally. Placeholder returns 1.0 (perfect).
        result.append(EvaluationMetric(
            name="identifier_stability",
            value=1.0,
            weight=0.50,
            passed=True,
            metadata={
                "description": "Identifier stability across runs",
                "note": "Real values require external repeated execution data",
            },
        ))

        return result

    @staticmethod
    def _compute_all_scores(
        metrics: tuple[EvaluationMetric, ...],
    ) -> tuple[EvaluationScore, ...]:
        """Compute all category scores from metrics.

        Args:
            metrics: All computed evaluation metrics.

        Returns:
            Tuple of EvaluationScore objects, one per category.
        """
        scores: list[EvaluationScore] = []

        for category_name in CATEGORY_WEIGHTS:
            score_value = calculate_category_score(
                metrics, category_name
            )
            weight = CATEGORY_WEIGHTS[category_name]

            scores.append(EvaluationScore(
                category=category_name,
                score=score_value,
                maximum=1.0,
                weight=weight,
            ))

        return tuple(scores)

    @staticmethod
    def _generate_summary(
        workflow_name: str,
        task_name: str,
        overall_score: float,
        scores: tuple[EvaluationScore, ...],
        execution_report: Any,
    ) -> str:
        """Generate a human-readable evaluation summary.

        Args:
            workflow_name: Name of the workflow.
            task_name: Name of the task.
            overall_score: Overall weighted score.
            scores: All category scores.
            execution_report: ExecutionReport-like object.

        Returns:
            Human-readable summary string.
        """
        status = "PASSED" if getattr(execution_report, "success", False) else "FAILED"

        lines: list[str] = [
            f"Evaluation: {workflow_name}/{task_name} — {status}",
            f"Overall Score: {overall_score:.3f}/1.000",
        ]

        for score_entry in scores:
            lines.append(
                f"  {score_entry.category}: {score_entry.score:.3f}"
                f" (weight: {score_entry.weight:.2f})"
            )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _get_workflow_name(
    workflow_plan: Any,
    execution_report: Any,
) -> str:
    """Extract workflow name from available sources.

    Args:
        workflow_plan: WorkflowPlan-like object.
        execution_report: ExecutionReport-like object.

    Returns:
        Workflow name string.
    """
    name = getattr(workflow_plan, "workflow_name", None)
    if name:
        return name
    return getattr(execution_report, "workflow_name", "unknown")


def _get_task_name(task_plan: Any) -> str:
    """Extract task name from available sources.

    Args:
        task_plan: TaskPlan-like object.

    Returns:
        Task name string.
    """
    if task_plan is not None:
        return getattr(task_plan, "task_name", "unknown")
    return "unknown"


def _get_provider(provider_response: Any) -> str:
    """Extract provider name from available sources.

    Args:
        provider_response: Provider response dict-like object.

    Returns:
        Provider name string.
    """
    if isinstance(provider_response, dict):
        return provider_response.get("provider", "unknown")
    return "unknown"


def _get_model(provider_response: Any) -> str:
    """Extract model name from available sources.

    Args:
        provider_response: Provider response dict-like object.

    Returns:
        Model name string.
    """
    if isinstance(provider_response, dict):
        return provider_response.get("model", "unknown")
    return "unknown"