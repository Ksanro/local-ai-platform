"""A question that names two files asks one question of each of them.

Scoring cannot tell the definitions of a named module apart: the file's own name is
an exact segment of every one of their qualified names, so it is a module-wide bonus
rather than a per-symbol signal, and the tie-break that picks the module's single
representative reads the names alphabetically.  A budget sized for several named
files then holds one symbol's text and nothing else, which is how
``scripts/quality_harness.py`` ``search_file_activity_two_modules`` scored 0/2: the
file named first was represented by a dataclass whose docstring alone filled the
SEARCH budget, and the other named file's best-matching symbol - first in the whole
ranking - was trimmed as the tail.

The rule under test is that a module named by path contributes a short run of its own
definitions, read in the order the file presents them, each named file contributing in
turn.  The fixture separates the two behaviours on purpose: in each file the
definition near the top is the one whose name sorts *last*, and the one that sorts
first is documented long enough to spend the budget on its own.  So the old rule
delivered that one symbol, and the new rule delivers both files' definitions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from packages.pipeline.context import PipelineContext
from packages.pipeline.stages.planning_stage import PlanningStage
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.index.models import RepositoryIndex

#: Long enough that delivering it costs most of a SEARCH budget, which is what the
#: dataclass the alphabetical tie-break chose in the real probe does.
TALL_DOCSTRING = "\n".join(
    [
        "    \"\"\"What this ledger holds, stated at length.",
        "",
        "    Attributes:",
    ]
    + [
        f"        attribute_{row}: A ledger row, counted when it is read."
        for row in range(60)
    ]
    + ['    """']
)

FIRST_MODULE = f'''"""The first module of a two-module fixture."""
from __future__ import annotations


def tally_up_almanac(value: object) -> int:
    """Fold what a caller hands in to one number."""
    return value if isinstance(value, int) else 0


class FirstLedger:
{TALL_DOCSTRING}

    def add(self, value: int) -> None:
        """Keep one row."""
'''

SECOND_MODULE = f'''"""The second module of a two-module fixture."""
from __future__ import annotations


def settle_down_quorum(value: object) -> str:
    """Turn untrusted text into the one row a record keeps."""
    return str(value)


class SecondLedger:
{TALL_DOCSTRING}

    def add(self, value: int) -> None:
        """Keep one row."""
'''

QUERY = (
    "In pkg/first.py and pkg/second.py: which function folds what a caller hands in "
    "to one number, and which function turns untrusted text into one row?"
)

#: The budget ``scripts/probe_replay.py`` gives a SEARCH request.
SEARCH_BUDGET = 2048


def _index(tmp_path: Path) -> RepositoryIndex:
    """Index two fixture modules the way the gateway indexes a repository."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "first.py").write_text(FIRST_MODULE, encoding="utf-8")
    (tmp_path / "pkg" / "second.py").write_text(SECOND_MODULE, encoding="utf-8")
    return RepositoryIndexBuilder().build(tmp_path)


def _sent_symbols(index: RepositoryIndex) -> list[str]:
    """Run the query through PlanningStage and RepositoryContextStage."""
    context = PipelineContext(
        request_id="named-module-context",
        request={"messages": [{"role": "user", "content": QUERY}]},
    )
    context.set_metadata("context_intent", "SEARCH")
    asyncio.run(PlanningStage().execute(context))
    stage = RepositoryContextStage(
        index=index,
        context_delta_injection=True,
        max_context_tokens=SEARCH_BUDGET,
        intent_context_budgets={"SEARCH": SEARCH_BUDGET},
    )
    result = asyncio.run(stage.execute(context))
    package = (result.data or {}).get("package")
    if package is None:
        return []
    return [name for name in (package.primary_symbol, *package.supporting_symbols) if name]


def test_both_named_files_reach_a_search_budget(tmp_path: Path) -> None:
    """A SEARCH budget sized for several contributions holds several contributions.

    One symbol per named file is what the rule used to deliver, and here one symbol
    is also all the budget could hold: the file's alphabetically first symbol carries
    the long documentation, so spending the run on it leaves nothing for the file the
    question named second.
    """
    sent = _sent_symbols(_index(tmp_path))

    modules = {name.split(".", 1)[0] for name in sent}
    assert modules == {"pkg/first", "pkg/second"}, sent
    assert len(sent) > 1, sent


def test_a_named_file_contributes_the_definition_at_its_top(tmp_path: Path) -> None:
    """The run is read from the top of the file, not from the A of its names."""
    sent = _sent_symbols(_index(tmp_path))

    assert sent[0] == "pkg/first.tally_up_almanac", sent
    assert "pkg/second.settle_down_quorum" in sent, sent
