"""Engineering Memory v1 — Deterministic engineering session memory.

Engineering Memory stores engineering facts only, never model conversations.
It records every completed engineering session and enables future sessions
to learn from previous work — without using embeddings, vector databases,
or semantic search.

Architecture
------------

Engineering Controller
    ↓
Engineering Transaction
    ↓
Execution Report
    ↓
Verification Report
    ↓
Evaluation Report
    ↓
Engineering Memory
    ↓
Future Engineering Sessions

Public API
----------

.. code-block:: python

    from packages.engineering_memory import (
        EngineeringMemory,
        EngineeringSessionRecord,
        MemoryStatistics,
    )

    # Create memory instance
    memory = EngineeringMemory()

    # Store a completed session
    record = EngineeringSessionRecord(
        session_id="sess-001",
        workflow_name="bug-fix",
        request_summary="Fix null pointer in ModuleX",
        transaction_id="txn-001",
        execution_report={"status": "COMPLETED"},
        verification_report={"status": "PASSED"},
        evaluation_report={"overall_score": 0.9},
        controller_decision="COMPLETE",
        completed_at="2026-07-21T14:55:00+00:00",
    )
    memory.store(record)

    # Query sessions
    session = memory.find_session("sess-001")
    sessions = memory.find_by_workflow("bug-fix")
    successful = memory.find_successful()
    failed = memory.find_failed()
    module_sessions = memory.find_by_module("module_x")
    recent = memory.recent(limit=10)

    # Get statistics
    stats = memory.statistics()

Constraints
-----------

- No vector database.
- No embeddings.
- No semantic search.
- No repository analysis.
- No provider calls.
- Deterministic behaviour.

"""

from packages.engineering_memory.memory import EngineeringMemory
from packages.engineering_memory.models import (
    EngineeringSessionRecord,
    MemoryStatistics,
)

__all__ = [
    # Service
    "EngineeringMemory",
    # Models
    "EngineeringSessionRecord",
    "MemoryStatistics",
    # Version
]

__version__ = "1.0.0"