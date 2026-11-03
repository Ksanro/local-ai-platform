"""Paired-delta microbenchmark for roadmap E3 item 3 (cost of C1 per request).

Two arms of the same production code path are timed inside one process against the
same message objects:

* ``candidate`` - ``RepositoryContextStage(file_activity=FileActivityTracker(...),
  repository_root=...)``, i.e. C1 running.
* ``control`` - the identical stage constructed with ``file_activity=None``, where
  ``_observe_file_activity`` returns at its first statement.

Nothing is patched, no runtime toggle is invented and no gateway is started: the
only difference between the arms is a constructor argument.

Freshness protocol
------------------

An object may be timed once.  Every timed invocation builds its own
:class:`~packages.pipeline.stages.repository_context.RepositoryContextStage`, its own
:class:`~packages.pipeline.file_activity.FileActivityTracker`, its own
:class:`~packages.pipeline.pipeline_context.PipelineContext` and its own context
package, so nothing a sample measures can benefit from work an earlier sample left
behind.  A warm cell pays for that history *outside* the timer, by replaying its
conversation's earlier requests through the same production method.  Because a
tracker's conversation state is a chain - each request finding the state the one
before it stored - the replay has to be complete, and a complete replay of a
thousand-turn conversation would cost a hundred times what it measures.  So the
fixture groups the conversation's earlier calls into
:data:`CALLS_PER_TURN` calls per assistant turn, which changes how many turns the
*earlier* requests had and changes nothing about the request being timed: same
messages, same envelopes, same distinct paths, same remembered state.  Each block
records the identities it constructed so the rule can be checked after the fact, and
the arm order of each timed group alternates between ``ABBA`` and ``BAAB`` under the
block's recorded seed, so no position in the group carries the same order every time.

Every timed call goes through the real
``RepositoryContextStage._observe_file_activity`` (or ``execute`` for the
``*-exec`` cells), so ``supplied_files_of``, ``module_files_of``, the envelope
resolution, the fingerprinting and the correlation all ride in the number.

Only counts ever leave this script: file names in the synthetic transcripts are
generated from a fixed pattern and are never printed, and no path from a real
conversation is read.

Usage::

    uv run python scripts/calibrate_c1_shapes.py --paste
    uv run python scripts/bench_c1_latency.py --pass estimate --cell R-p99-warm
    uv run python scripts/bench_c1_latency.py --pass correctness --cell R-p99-warm --block 1
    uv run python scripts/bench_c1_latency.py --pass latency --cell R-p99-warm --block 1
    uv run python scripts/bench_c1_latency.py --sweep latency --filter R-p50 --out build/e3lat_v2
    uv run python scripts/bench_c1_latency.py --pass diag --cell N-count-100 --block 1
    uv run python scripts/bench_c1_latency.py --report --out build/e3lat_v2
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import gc
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.context.context_package import (  # noqa: E402
    ContextPackage,
    ModuleDescription,
    SymbolContext,
)
from packages.pipeline.cline_activity import (  # noqa: E402
    MAX_ENVELOPES_PER_REQUEST,
    MAX_NATIVE_RESULT_CHARS,
    MAX_PATH_CHARS,
)
from packages.pipeline.context import PipelineContext  # noqa: E402
from packages.pipeline.file_activity import (  # noqa: E402
    FILE_ACTIVITY_CORRELATION_STATES,
    FILE_ACTIVITY_STATES,
    INERT_FILE_ACTIVITY,
    NEW_CONVERSATION_KEY,
    FileActivityTracker,
    transcript_fingerprints,
)
from packages.pipeline.stages.repository_context import (  # noqa: E402
    RepositoryContextStage,
)

#: Longest transcript this script will build, as a guard against an accidental
#: multi-gigabyte fixture.  Every decision cell is checked against it before timing.
MAX_TRANSCRIPT_BYTES: int = 32 * 1024 * 1024

#: A timed sample shorter than this would be dominated by timer and call overhead,
#: so batch sizes are chosen to keep samples above it.
MIN_SAMPLE_MS: float = 60.0

#: How much wall clock one block may spend, timed work and warm-up together.  A
#: block is a separate process, and its fixed cost is that process plus the
#: conversation replay that keeps a warm arm honest; a block that overshoots this is
#: a block the harness would cut off.
TARGET_BLOCK_SECONDS: float = 8.0

#: The preregistered thresholds, in milliseconds of per-request wall clock.
NEGLIGIBLE_MS: float = 2.0
ACTIONABLE_MS: float = 5.0

#: How many calls the fixture puts in one assistant turn.  A real conversation's
#: newest request is what is timed, and grouping its earlier calls does not change
#: one envelope, message or byte of that request; it only changes how many
#: requests the warm-up has to replay, which is quadratic in the transcript's
#: length.  Twenty-four is the largest batch of parallel calls this repository's
#: own client sends, so the fixture's earlier turns are a plausible shape and the
#: replay stays affordable.
CALLS_PER_TURN: int = 24

#: The tools each transcript form uses to name a file, and the two that are recognized
#: without naming one.  These are exactly the names ``packages.pipeline.cline_activity``
#: maps to an activity, so a generated envelope is one the production parser accepts.
NATIVE_FILE_TOOLS: tuple[str, str] = ("read_files", "editor")
NATIVE_OTHER_TOOLS: tuple[str, ...] = ("search_codebase", "run_commands")
TEXT_FILE_TOOLS: tuple[str, str] = ("read_file", "write_to_file")
TEXT_OTHER_TOOLS: tuple[str, ...] = ("search_files", "list_files", "execute_command")

#: The two group orders, used in alternation.  A group is four invocations, two per
#: arm, and the mirror order exists so that nothing about the first or last slot of a
#: group can land on one arm every time.
ORDER: tuple[str, str, str, str] = ("candidate", "control", "control", "candidate")
ORDER_FLIPPED: tuple[str, str, str, str] = ("control", "candidate", "candidate", "control")

#: What a hand-built cell's shape was in an actual conversation, as counts only, keyed by
#: cell name.  ``chars`` is the mean characters of one result block, ``result_chars`` the
#: mean characters of the block a file call returns, ``messages`` the length of the
#: transcript holding the request, and ``distinct`` how many different files its calls
#: name.  :func:`_claim_row` reads this table for one kind of cell and no other: a
#: ``builder`` cell whose own name is a key here, which in this matrix is ``X-empty``
#: alone.  The other four ``X-`` cells carry their expectation inside their own
#: :data:`CELLS` entry, a calibrated cell is paired against its row of logged sessions in
#: :data:`OBSERVED_SHAPES`, and every remaining cell is generated from a shape, so
#: :func:`claimed_shape` works its figures out by arithmetic instead of remembering them.
#: The rows this table used to hold under names no cell carries - ``N-count-50``,
#: ``N-p99``, ``T-count-999``, ``X-malformed-200`` and the rest - were never read: a key
#: that matches no cell decides nothing, and grading a generated cell against the
#: conversation it merely resembles is the mistake :func:`_claim_row` exists to avoid.  The
#: ``None`` the four ``N-warm-*`` rows held said that a stored session cannot tell which
#: of its requests replayed an earlier one; the warm cells answer that from
#: :data:`OBSERVED_SHAPES` now, and the report prints "off" beside any field a cell has no
#: claim to make.
#:
#: Two properties of the surviving row must be said plainly.  It is read from Anthropic-form
#: session storage, which :func:`packages.pipeline.cline_activity.parse_message_envelope`
#: does not recognize, so it says how large a conversation gets rather than which
#: transcript dialect a live gateway receives.  And ``calls`` and ``others`` are counted
#: across a session, where a live transcript would spread them over many requests; the
#: envelope counts here are the per-request ones, which is the honest smaller number.
CELL_SHAPES: dict[str, dict[str, int]] = {
    "X-empty": {"messages": 2, "turns": 0, "envelopes": 0, "chars": 110,
                "result_chars": 0, "calls": 0, "others": 0, "distinct": 0},
}

#: The distribution shapes, keyed by the name a cell carries in ``shape``.  These are the
#: rows ``scripts/calibrate_c1_shapes.py --paste`` prints, in the order it prints them:
#: the same percentile names, the same ``SHAPE_KEYS`` columns, the same counts, re-wrapped
#: onto several lines because that script puts one row on one line and this file keeps to
#: 100 columns.  Rerunning the calibration and re-pasting it replaces this table wholesale.
#: These are whole-session totals, so a cell built from one is a transcript as long as the
#: busiest conversation the scan found, not one request inside it; that is what makes the
#: realistic cells a scale reference rather than a replay of traffic.  It is the builder's
#: table, unlike :data:`CELL_SHAPES`, which the report reads.
OBSERVED_SHAPES: dict[str, dict[str, int]] = {
    "p50": {"block_results": 110, "calls": 43, "distinct_targets": 21, "envelope_calls": 0,
            "envelope_messages": 0, "file_turns": 39, "max_result": 94464, "messages": 217,
            "native_calls": 0, "others": 67, "result_chars": 746734, "tool_turns": 100,
            "turns": 103},
    "p90": {"block_results": 1132, "calls": 457, "distinct_targets": 42, "envelope_calls": 0,
            "envelope_messages": 0, "file_turns": 457, "max_result": 123496,
            "messages": 2274, "native_calls": 0, "others": 675, "result_chars": 3635476,
            "tool_turns": 1132, "turns": 1137},
    "p95": {"block_results": 993, "calls": 508, "distinct_targets": 60, "envelope_calls": 0,
            "envelope_messages": 0, "file_turns": 477, "max_result": 145595,
            "messages": 1912, "native_calls": 0, "others": 485, "result_chars": 4273802,
            "tool_turns": 912, "turns": 915},
    "p99": {"block_results": 1354, "calls": 659, "distinct_targets": 81, "envelope_calls": 0,
            "envelope_messages": 0, "file_turns": 653, "max_result": 120701,
            "messages": 2706, "native_calls": 0, "others": 695, "result_chars": 4903424,
            "tool_turns": 1340, "turns": 1346},
}

#: How close a generated shape must sit to :data:`OBSERVED_SHAPES` for a cell to
#: count as measuring that shape.  Result characters are allocated exactly, so this
#: slack is for the rounding a message list forces: one envelope is one message.
SHAPE_TOLERANCE: float = 0.02

#: The 17 fields one recorded request carries, in the order ``INERT_FILE_ACTIVITY``
#: orders them.  A correctness gate compares a payload with an expectation over
#: exactly these keys, so a field that appeared or vanished fails.
INERT_KEYS: list[str] = list(INERT_FILE_ACTIVITY)


def inert_payload(**overrides: Any) -> dict[str, Any]:
    """Return the whole count-only payload with these few fields changed.

    Args:
        overrides: The fields a cell is expected to report, by name.

    Returns:
        A payload holding every key of :data:`INERT_KEYS`, so a cell's expectation
        also states what its other counters must be - zero - instead of leaving them
        unstated.
    """
    payload = dict(INERT_FILE_ACTIVITY)
    payload.update(overrides)
    return payload

#: One entry per measurement cell.  ``calls`` and ``others`` count *recognized*
#: envelopes (what ``MAX_ENVELOPES_PER_REQUEST`` bounds), not messages.
CELLS: dict[str, dict[str, Any]] = {
    "N-count-10": {"form": "native", "calls": 10, "others": 0, "chars": 1000, "distinct": 10},
    "N-count-100": {"form": "native", "calls": 100, "others": 0, "chars": 1000, "distinct": 100},
    "N-count-256": {"form": "native", "calls": 256, "others": 0, "chars": 1000, "distinct": 256},
    "N-count-500": {"form": "native", "calls": 500, "others": 0, "chars": 1000, "distinct": 500},
    "N-count-1000": {"form": "native", "calls": 1000, "others": 0, "chars": 1000, "distinct": 1000},
    "N-size-1K": {"form": "native", "calls": 24, "others": 0, "chars": 1_024, "distinct": 24},
    "N-size-100K": {"form": "native", "calls": 24, "others": 0, "chars": 100_000, "distinct": 24},
    "N-size-1M": {"form": "native", "calls": 24, "others": 0, "chars": 1_000_000, "distinct": 24},
    "N-size-3M": {"form": "native", "calls": 8, "others": 0, "chars": 3_000_000, "distinct": 8},
    "T-text-500": {"form": "text", "calls": 500, "others": 0, "chars": 1000, "distinct": 500},
    "T-text-100K": {"form": "text", "calls": 64, "others": 0, "chars": 100_000, "distinct": 64},
    "A-none-256": {"form": "native", "calls": 0, "others": 256, "chars": 1000,
                   "distinct": 256},
    "N-mix-256": {"form": "native", "calls": 256, "others": 256, "chars": 1000, "distinct": 256},
    "P-repeat-256": {"form": "native", "calls": 256, "others": 0, "chars": 1000, "distinct": 1},
    "P-distinct-256": {"form": "native", "calls": 256, "others": 0, "chars": 1000,
                       "distinct": 256},
    "X-empty": {"form": "native", "builder": "empty", "calls": 0, "others": 0, "chars": 0,
                "distinct": 0, "gate_only": True},
    "X-malformed": {"form": "native", "builder": "malformed", "calls": 12, "others": 1,
                    "chars": 1000, "distinct": 3, "gate_only": True,
                    "expected": inert_payload(
                        state="measured", files_read=1, files_modified=1, files_touched=2,
                        read_attempts=1, modification_attempts=2, modifications_unknown=1,
                        paths_rejected=9, other_events=1)},
    "X-oversize": {"form": "native", "builder": "oversize", "calls": 4, "others": 0,
                   "chars": MAX_NATIVE_RESULT_CHARS + 1, "distinct": 4, "gate_only": True},
    "X-oversize-under": {"form": "native", "builder": "oversize", "calls": 4, "others": 0,
                         "chars": MAX_NATIVE_RESULT_CHARS, "distinct": 4, "gate_only": True},
    "X-badroot": {"form": "native", "builder": "outside", "calls": 8, "others": 0,
                  "chars": 1000, "distinct": 8, "gate_only": True},
    "R-p50-warm": {"form": "native", "shape": "p50", "warm": True, "package_files": 8,
                   "changed_files": 2},
    "R-p90-warm": {"form": "native", "shape": "p90", "warm": True, "package_files": 10,
                   "changed_files": 2},
    "R-p99-warm": {"form": "native", "shape": "p99", "warm": True, "package_files": 10,
                   "changed_files": 2, "decision": True},
    "R-p99-exec": {"form": "native", "shape": "p99", "warm": True, "entry": "execute"},
    "R-p99-cold": {"form": "native", "shape": "p99"},
}

#: Timed groups per block, chosen from the estimate pass so a block stays inside
#: :data:`TARGET_BLOCK_SECONDS` while its samples stay above :data:`MIN_SAMPLE_MS`.  A
#: warm cell's group costs four conversation replays as well as four timed calls, which is
#: what keeps these numbers low where the transcript is long: measured on this machine one
#: group of ``R-p50-warm`` costs 0.06 s, of ``R-p90-warm`` 1.2 s, of ``R-p99-warm`` 2.1 s
#: and of ``R-p99-exec`` 2.3 s.  Three of those four sit at 5, 3 and 2 - which come to 5.9,
#: 6.4 and 4.6 s a block - because the value they carried before (19, 22 and 19) was never
#: checked against the budget at its own depth: a block of ``R-p90-warm`` at 19 measures
#: 23 s, and the two p99 cells cost so much per group that 22 and 19 would each have run to
#: the better part of a minute.  This is what a latency run uses when ``--batch`` is not
#: given, for every cell, warm ones included.  A ``--batch`` on the command line overrides
#: it, which is how the decision cell is run at a deeper sample count than the pilot cells
#: around it.
BATCHES: dict[str, int] = {
    "N-count-10": 165, "N-count-100": 18, "N-count-256": 8, "N-count-500": 7,
    "N-count-1000": 7, "N-size-1K": 70, "N-size-100K": 45, "N-size-1M": 15,
    "N-size-3M": 6, "T-text-500": 4, "T-text-100K": 24, "A-none-256": 225,
    "N-mix-256": 13, "P-repeat-256": 105, "P-distinct-256": 9, "R-p50-warm": 80,
    "R-p90-warm": 5, "R-p99-warm": 3, "R-p99-exec": 2, "R-p99-cold": 22,
    "X-empty": 0, "X-malformed": 0, "X-oversize": 0, "X-oversize-under": 0, "X-badroot": 0,
}

#: The cells whose numbers decompose the cost, run at the shallow sample count that
#: answers the question they ask.
PILOT_CELLS: tuple[str, ...] = (
    "N-count-10", "N-count-100", "N-count-256", "N-count-500",
    "N-size-1K", "N-size-100K", "N-size-1M",
    "T-text-500", "T-text-100K", "A-none-256", "N-mix-256",
    "P-repeat-256", "P-distinct-256", "R-p50-warm", "R-p90-warm",
)

#: Every cell a correctness pass runs, in the order a gate report should read.  The
#: ``X-`` cells are here and not in :data:`PILOT_CELLS`: they have a payload to
#: check and no timing to pool.
GATE_CELLS: tuple[str, ...] = (
    "N-count-10", "N-count-100", "N-count-256", "N-count-500", "N-count-1000",
    "N-size-1K", "N-size-100K", "N-size-1M", "N-size-3M",
    "T-text-500", "T-text-100K", "A-none-256", "N-mix-256",
    "P-repeat-256", "P-distinct-256",
    "X-empty", "X-malformed", "X-oversize", "X-oversize-under", "X-badroot",
    "R-p50-warm", "R-p90-warm", "R-p99-warm", "R-p99-exec", "R-p99-cold",
)


#: How many characters a native result wrapper adds around a result body, so a
#: generated transcript's result characters can be stated exactly.
RESULT_JSON_OVERHEAD: int = len(json.dumps({"success": True, "result": ""}))

#: The shortest result body this script will generate.  An envelope with no body
#: would still be a recognized envelope, but a transcript made only of wrappers
#: would measure the wrapper rather than the file text a read returns.
MIN_RESULT_CHARS: int = 32

#: The text of the transcript's opening message and of the follow-up messages that
#: pad a generated conversation out to the message count it is calibrated against.
#: Neither carries an envelope header, so neither adds activity to count.
OPENING_TEXT: str = "task " * 64
FILLER_TEXT: str = "follow up " * 32

#: The result body a generated native call answers with: success, and a body short
#: enough that a cell which is not about size does not pay for one.
RESULT_OK: str = json.dumps({"success": True, "result": "x" * 256})


def allocate_chars(total: int, count: int, maximum: int = 0) -> list[int]:
    """Split ``total`` result characters across ``count`` envelopes, exactly.

    Args:
        total: The characters the transcript's results must carry in sum.
        count: How many envelopes carry them.
        maximum: The size one of them should reach, which is how a shape's largest
            single result survives into the fixture instead of being averaged away.

    Returns:
        ``count`` lengths summing to ``total``.  The largest sits at the middle of
        the conversation rather than at either end, so it is inside the window a
        bounded parse keeps and inside the prefix a warm-up replays.
    """
    if count <= 0:
        return []
    if count == 1:
        return [max(total, MIN_RESULT_CHARS)]
    room = total - (count - 1) * MIN_RESULT_CHARS
    if room <= 0:
        return [MIN_RESULT_CHARS] * count
    biggest = min(maximum, room) if maximum >= MIN_RESULT_CHARS else MIN_RESULT_CHARS
    base, extra = divmod(total - biggest, count - 1)
    sizes = [base + (1 if position < extra else 0) for position in range(count - 1)]
    sizes.insert((count - 1) // 2, biggest)
    return sizes


def envelope_sizes(spec: dict[str, Any]) -> list[int]:
    """Return the result length of each envelope in a cell, in message order."""
    count = int(spec["calls"]) + int(spec.get("others", 0))
    if spec.get("shape") in OBSERVED_SHAPES:
        observed = OBSERVED_SHAPES[spec["shape"]]
        return allocate_chars(observed["result_chars"], count, observed["max_result"])
    return allocate_chars(int(spec["chars"]) * count, count, int(spec["chars"]))


def _distribute(total: int, slots: int) -> list[int]:
    """Spread ``total`` whole things over ``slots`` places as evenly as one can."""
    if slots <= 0:
        return [total]
    base, extra = divmod(max(total, 0), slots)
    return [base + (1 if position < extra else 0) for position in range(slots)]


def _pair_native(tool: str, target: str, is_file: bool, index: int,
                 chars: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return one ``tool_calls`` entry and the ``role: "tool"`` message answering it.

    Args:
        tool: The native tool name, which decides the activity the parser records.
        target: The file the call names, or the empty string for a call that names
            none.  Its length is not counted: only the result body is.
        is_file: Whether this call names a file.
        index: The envelope's position in the transcript, which names its call id.
        chars: How many characters its result's content must carry, exactly.

    Returns:
        The announced call and the tool message answering it.  The answer reports
        ``success`` because a transcript of failed calls would measure the failure
        path rather than the one a working conversation takes.
    """
    call_id = f"call_{index:05d}"
    args: dict[str, Any] = {"path": target} if is_file else {"query": "pattern" * 8}
    body = "x" * max(chars - RESULT_JSON_OVERHEAD, MIN_RESULT_CHARS)
    call = {"id": call_id, "type": "function",
            "function": {"name": tool, "arguments": json.dumps(args)}}
    result = {"role": "tool", "tool_call_id": call_id,
              "content": json.dumps({"success": True, "result": body})}
    return call, result


def _pair_text(tool: str, activity: str, target: str, is_file: bool, chars: int) -> dict[str, str]:
    """Return one user-role message carrying a legacy Cline envelope.

    Args:
        tool: The legacy tool name, which the header anchors the parse on.
        activity: ``"read"`` or ``"modified"``, deciding the body's status text.
        target: The file the header names.
        is_file: Whether this envelope names a file.
        chars: How many characters the whole message must carry, exactly.

    Returns:
        The message, whose header length is subtracted from ``chars`` so a text-form
        transcript hits its calibrated character total as precisely as a native one.
    """
    head = f"[{tool} for {target}] " if is_file else f"[{tool} for something] "
    marker = "Result:\n"
    status = "Successfully saved the file. " if activity == "modified" else ""
    body = "z" * max(chars - len(head) - len(marker) - len(status), MIN_RESULT_CHARS)
    return {"role": "user", "content": f"{head}{marker}{status}{body}"}


def _pad_messages(messages: list[dict[str, Any]], count: int) -> None:
    """Insert ``count`` envelope-free follow-up messages, spread through the transcript.

    Args:
        messages: The message list to extend, in place.
        count: How many messages to add.  Zero or fewer adds none.

    Returns:
        ``None``.  The padding is placed after the opening message and after the last
        tool reply of each assistant turn, so a conversation keeps its turn structure and
        the newest envelopes stay newest; the messages carry no header and no
        ``tool_calls``, so they add nothing for the envelope parser to recognize.  They
        exist because a real conversation holds questions and explanations between its
        calls, and a fixture that skipped them would walk a shorter list than the stage
        walks in production.  Between the calls and their replies, though, they go nowhere:
        a client that announced a batch of calls answers it with the tool results and
        nothing else, so an intervening user message would be a request shape no traffic
        produces - and one the envelope parser would still have to walk past.

        They are user messages, deliberately: the fingerprint a warm conversation is
        chained by is taken over everything before the *newest assistant turn*, so an
        assistant message inserted after the last tool call would move that boundary
        and the cell would quietly stop being the warm request it claims to time.  The
        anchors are the ends of the turns rather than their beginnings for the same
        reason: a filler after the newest turn's last reply still sits past that
        boundary, and nothing inserted here shifts the assistant turn itself.
    """
    if count <= 0:
        return
    turns = [index for index, message in enumerate(messages) if "tool_calls" in message]
    anchors = [0]
    for start in turns:
        end = start + 1
        while end < len(messages) and messages[end].get("role") == "tool":
            end += 1
        # The turn's last tool reply, or the turn itself if it announced no call that
        # came back; an anchor that repeats one already listed would slice nothing.
        anchor = end - 1 if end - 1 > start else start
        if anchor != anchors[-1]:
            anchors.append(anchor)
    sizes = _distribute(count, len(anchors))
    padded: list[dict[str, Any]] = []
    previous = 0
    for anchor, size in zip(anchors, sizes, strict=True):
        padded.extend(messages[previous:anchor + 1])
        padded.extend({"role": "user", "content": FILLER_TEXT} for _ in range(size))
        previous = anchor + 1
    padded.extend(messages[previous:])
    messages[:] = padded


def _malformed_transcript() -> tuple[list[dict[str, Any]], list[int]]:
    """Return one transcript holding every way a client can send a broken envelope.

    The shapes are chosen from what :class:`~packages.pipeline.cline_activity.
    RepositoryPathNormalizer` refuses, one of each: arguments that are not JSON, a
    path that is not a string, an empty path, a path too long, a path with a NUL, a
    UNC share, a path with a control character, a path with an NTFS stream colon, and
    the repository root named as a file.  Alongside them sit the three calls a real
    transcript would also hold - one read that worked, one write that worked, one
    write whose result the parser could not read - and one call that names no file.

    Returns:
        A twelve-message transcript in one assistant turn, and its turn index.  All
        thirteen envelopes are inside the bound, so nothing is dropped and the
        reported numbers are the whole story rather than the newest part of it.
    """
    first, second, third = (synth_file(index) for index in range(3))
    defects: list[tuple[str, dict[str, Any] | str, str]] = [
        ("read_files", "arguments that were never json", RESULT_OK),
        ("editor", {"path": 42}, RESULT_OK),
        ("editor", {"path": ""}, RESULT_OK),
        ("read_files", {"path": "a" * (MAX_PATH_CHARS + 1)}, RESULT_OK),
        ("editor", {"path": f"{first}\x00tail"}, RESULT_OK),
        ("read_files", {"path": "//server/share/outside.py"}, RESULT_OK),
        ("editor", {"path": "packages\tpipeline"}, RESULT_OK),
        ("read_files", {"path": "docs:notes"}, RESULT_OK),
        ("editor", {"path": "."}, RESULT_OK),
    ]
    accepted: list[tuple[str, dict[str, Any] | str, str]] = [
        ("read_files", {"path": first}, RESULT_OK),
        ("editor", {"path": second}, RESULT_OK),
        ("editor", {"path": third}, "the tool said something no parser could read"),
        (NATIVE_OTHER_TOOLS[0], {"query": "what"}, '{"output": "matches"}'),
    ]
    calls: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for index, (tool, arguments, content) in enumerate(defects + accepted):
        args = arguments if isinstance(arguments, str) else json.dumps(arguments)
        calls.append({
            "id": f"call_bad_{index:04d}",
            "type": "function",
            "function": {"name": tool, "arguments": args},
        })
        results.append({"role": "tool", "tool_call_id": f"call_bad_{index:04d}",
                        "content": content})
    return ([{"role": "user", "content": OPENING_TEXT},
             {"role": "assistant", "content": "thinking " * 24, "tool_calls": calls},
             *results], [1])


def build_messages(spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[int]]:

    """Return the transcript for a cell and the index of every assistant turn in it.

    Turns are emitted so that the transcript ends with tool results, which is what a
    request that answers the previous turn looks like on the wire.  The assistant
    indices are the boundaries of the requests of this conversation: the messages
    before index ``s`` are exactly the request that produced the reply at ``s``,
    which is what a warm cell replays to build a lineage.  A cell calibrated against
    a real conversation gets that conversation's envelope count and its message
    count; how many assistant turns the messages take is :data:`CALLS_PER_TURN`'s
    business, and the padding messages that make up the difference carry no
    envelope, so they change what a request walks and fingerprints and change
    nothing about the activity it reports.
    """
    builder = spec.get("builder")
    if builder == "empty":
        return [], []
    if builder == "malformed":
        return _malformed_transcript()
    calls = _make_calls(spec)
    sizes = envelope_sizes(spec)
    messages: list[dict[str, Any]] = [{"role": "user", "content": OPENING_TEXT}]
    if not calls:
        return messages, []
    if spec["form"] == "text":
        for index, (tool, activity, target, is_file) in enumerate(calls):
            messages.append({"role": "assistant", "content": f"using {tool}"})
            messages.append(_pair_text(tool, activity, target, is_file, sizes[index]))
        return messages, []
    per_turn = int(spec.get("calls_per_turn", CALLS_PER_TURN))
    for start in range(0, len(calls), per_turn):
        batch: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        for offset, (tool, activity, target, is_file) in enumerate(calls[start:start + per_turn]):
            announced, result = _pair_native(tool, target, is_file, start + offset,
                                            sizes[start + offset])
            batch.append(announced)
            results.append(result)
        messages.append({"role": "assistant", "content": "thinking " * 24, "tool_calls": batch})
        messages.extend(results)
    _pad_messages(messages, int(spec.get("fillers", 0)))
    return messages, [index for index, message in enumerate(messages) if "tool_calls" in message]


def build_seeds(spec: dict[str, Any], messages: list[dict[str, Any]],
                starts: list[int]) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """Return the immediate predecessor transcript and the chain of earlier requests.

    The predecessor is ``messages[:starts[-1]]`` - the request that produced the newest
    assistant turn - and not ``messages[:-1]``, which for a transcript ending in tool
    results fingerprints to a conversation nothing ever stored.  The chain is every
    request before that one, replayed in order so the tracker's lineage stays complete
    and the last seeding call stores the state the timed call looks up.
    """
    if spec["form"] == "text" or not starts:
        return (messages[:-1] if len(messages) > 1 else list(messages)), []
    return messages[:starts[-1]], [messages[:start] for start in starts[:-1]]


def build_package(files: tuple[str, ...]) -> ContextPackage:
    """Return a package that supplies exactly ``files`` and nothing else.

    A composed ``ContextPackage`` names its modules in three places and
    :func:`supplied_files_of` reads all three; a package assembled by a capability may
    fill only one, so the fixture fills the module list and the descriptions.  The
    derivation work is what the measurement is supposed to include.
    """
    primary = files[0] if files else ""
    return ContextPackage(
        primary_symbol=f"{primary[:-3]}.Main" if primary else "",
        related_modules=list(files),
        primary_symbol_context=(SymbolContext(qualified_name="m.Main", location=(primary, 1, 20))
                                if primary else None),
        module_descriptions=[ModuleDescription(module_path=f, purpose="p", symbol_count=1)
                             for f in files],
    )


@contextmanager
def seed_context(messages: list[dict[str, Any]], seed: list[dict[str, Any]]) -> Iterator[None]:
    """Swap the timed transcript for its predecessor for the duration of the block.

    The same list object is used so seeding costs no extra allocation, and the restore
    runs even if the seed raises: a fixture left truncated would make the *control*
    arm read a shorter transcript than the candidate and bias the delta upward.
    """
    saved = list(messages)
    del messages[:]
    messages.extend(seed)
    try:
        yield
    finally:
        del messages[:]
        messages.extend(saved)


class Arm:
    """One arm of one cell, honouring the rule that an object is timed once.

    A prepared invocation constructs a stage, a tracker, a pipeline context and a
    context package that no earlier invocation used, so a timed sample cannot inherit
    a normalization cache, a correlation state or a warm allocation from the sample
    before it.  For a warm cell the conversation's earlier requests are replayed
    through the same production method *before* the timer starts: what is measured is
    one later request of a conversation that already has history, which is what a
    gateway answers in production.

    Attributes:
        fixture: The built cell this arm runs.
        arm: ``"candidate"`` or ``"control"``.
        stage: The stage the current invocation built, kept so a correctness pass can
            read the state its tracker holds.
        identities: One ``(stage, tracker, context, package)`` tuple of object ids per
            prepared invocation - the proof, after the fact, that no object served
            twice.
    """

    def __init__(self, fixture: dict[str, Any], arm: str) -> None:
        """Bind this arm to one built fixture.

        Args:
            fixture: The cell's fixture.
            arm: ``"candidate"`` for C1 running, ``"control"`` for the same stage
                built with ``file_activity=None``.
        """
        self.fixture = fixture
        self.arm = arm
        self.messages = fixture["messages"]
        self.stage: RepositoryContextStage | None = None
        self.identities: list[tuple[int, int, int, int]] = []
        self._built: list[tuple[Any, ...]] = []
        self._package: ContextPackage | None = None
        self._context: PipelineContext | None = None

    def _call(self, stage: RepositoryContextStage, context: PipelineContext,
              package: ContextPackage | None) -> None:
        """Make the one production call this invocation is allowed, on ``context``.

        Args:
            stage: The stage built for this invocation.
            context: Where the stage writes its metadata; a throwaway for a replayed
                request, the arm's own for the timed one.
            package: The context package this invocation built, or ``None`` for a cell
                that supplies no files.
        """
        if self.fixture["spec"].get("entry") == "execute":
            context.request = {"messages": self.messages}
            _run(stage.execute(context))
        else:
            stage._observe_file_activity(context, self.messages, package,
                                         self.fixture["changed"])

    def prepare(self) -> None:
        """Build this invocation's objects and replay the conversation up to now.

        Returns:
            ``None``.  Everything built here sits outside the timed region on purpose:
            the stage's own construction and the history a warm request finds already
            made are not what the measurement asks about.
        """
        tracker = FileActivityTracker() if self.arm == "candidate" else None
        stage = RepositoryContextStage(index=None, file_activity=tracker,
                                       repository_root=REPO_ROOT)
        supplied = self.fixture["supplied"]
        package = build_package(supplied) if supplied else None
        context = PipelineContext()
        self.stage, self._package, self._context = stage, package, context
        # An id is only unique while its object lives, so every built object is held
        # until the arm is dropped; otherwise a freed stage's address is handed to the
        # next one and the record reports a reuse that never happened.  A control arm
        # has no tracker, and ``id(None)`` is one constant, so it is recorded as 0.
        self._built.append((stage, tracker, context, package))
        self.identities.append((id(stage), id(tracker) if tracker is not None else 0,
                                id(context), id(package) if package is not None else 0))
        if self.fixture["spec"]["warm"]:
            for transcript in self.fixture["chain"] + [self.fixture["seed"]]:
                with seed_context(self.messages, transcript):
                    self._call(stage, PipelineContext(), package)

    def timed(self) -> None:
        """Run the one invocation this object is allowed to serve, inside the timer.

        Returns:
            ``None``.  The call is the same production method a gateway reaches for on
            a later request of a conversation; the objects it runs on were built by
            :meth:`prepare` and serve nothing else.
        """
        assert self.stage is not None and self._context is not None
        self._call(self.stage, self._context, self._package)

    def payload(self) -> dict[str, Any]:
        """Return the activity section the timed call recorded, without a second call.

        Returns:
            The count-only payload, or an empty dict for the control arm, which writes
            nothing because its stage was built with no tracker.
        """
        assert self._context is not None
        return dict(self._context.metadata.get("file_activity", {}))


def _run(coroutine: Any) -> None:
    """Drive one coroutine of the async stage API."""
    asyncio.run(coroutine)


_REAL_TARGETS: list[str] | None = None


def real_targets() -> list[str]:
    """Return the repository's own tracked Python files as envelope targets.

    An envelope target in a real transcript names a file that exists: the normalizer
    resolves it with ``os.path.realpath``, and a path that exists resolves about twice
    as fast as one that does not (measured on this machine, 0.13 ms against 0.27 ms).
    A fixture made of invented paths would therefore overstate C1's cost, so the
    generated transcripts point at files this repository really has.  The names are
    never printed by this script.

    If the listing is unavailable, the pattern-generated fallback is used and the cell
    records that its targets are not real files.
    """
    global _REAL_TARGETS
    if _REAL_TARGETS is None:
        try:
            listing = subprocess.run(
                ["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True,
                check=True, timeout=10).stdout.split()
            _REAL_TARGETS = sorted(part.replace("\\", "/") for part in listing)
        except Exception:
            _REAL_TARGETS = []
    return _REAL_TARGETS


def synth_file(index: int) -> str:
    """Return the ``index``-th repository-relative envelope target.

    Targets cycle over the repository's tracked Python modules; a cell asking for more
    distinct targets than the repository holds gets a repeated spelling of a real file,
    which the per-request normalization cache then absorbs exactly as it would in a
    request that re-sends the same path many times.
    """
    paths = real_targets()
    if not paths:
        return f"packages/synth/mod{index % 997:04d}/unit{index // 997:03d}.py"
    return paths[index % len(paths)]



def synth_module_key(target: str) -> str:
    """Return the index module key of one synthetic ``.py`` target."""
    return target[: -len(".py")]


def _make_calls(spec: dict[str, Any]) -> list[tuple[str, str, str, bool]]:
    """Return ``(tool, activity, target, is_file)`` for every envelope in a cell.

    File-naming and non-file calls are interleaved rather than concatenated, so a
    transcript longer than ``MAX_ENVELOPES_PER_REQUEST`` keeps both kinds inside the
    retained window - which is what a real session's newest 256 envelopes look like.
    Three quarters of the file calls read and one writes, the ratio a coding
    conversation settles into once it has stopped asking where things are.  A cell
    with ``outside_root`` names its files as absolute paths under a scratch directory
    the stage is not rooted at, which is how a cell asks what the normalizer refuses.
    """
    distinct = max(int(spec.get("distinct", 1)), 1)
    native = spec["form"] != "text"
    reader, writer = (NATIVE_FILE_TOOLS if native else TEXT_FILE_TOOLS)
    others = NATIVE_OTHER_TOOLS if native else TEXT_OTHER_TOOLS
    outside = str(spec.get("outside_root", ""))
    file_calls: list[tuple[str, str, str, bool]] = []
    for index in range(int(spec["calls"])):
        reading = bool(index % 4)
        tool = reader if reading else writer
        target = synth_file(index % distinct)
        if outside:
            target = f"{outside}/e3_outside_{index % distinct:04d}.py"
        file_calls.append((tool, "read" if reading else "modified", target, True))
    other_calls: list[tuple[str, str, str, bool]] = []
    for index in range(int(spec.get("others", 0))):
        other_calls.append((others[index % len(others)], "none", "", False))
    calls: list[tuple[str, str, str, bool]] = []
    for index in range(max(len(file_calls), len(other_calls))):
        if index < len(file_calls):
            calls.append(file_calls[index])
        if index < len(other_calls):
            calls.append(other_calls[index])
    return calls


def expand_shape(spec: dict[str, Any]) -> dict[str, Any]:
    """Fill a calibrated cell's counts from :data:`OBSERVED_SHAPES`, in place.

    Args:
        spec: A copy of one entry of :data:`CELLS`.

    Returns:
        The same dict with ``calls``, ``others``, ``distinct``, the envelope sizes and
        the number of padding messages filled in, plus ``observed`` and ``generated``
        so a record can show what was asked for and what was built.  A cell's own
        ``chars`` is ignored when it is calibrated: the shape's character total is
        what the cell is about.
    """
    name = spec.get("shape")
    if name not in OBSERVED_SHAPES:
        spec.setdefault("others", 0)
        spec.setdefault("distinct", 1)
        spec.setdefault("warm", False)
        spec.setdefault("package_files", 0)
        spec.setdefault("changed_files", 0)
        return spec
    observed = OBSERVED_SHAPES[str(name)]
    spec["calls"] = int(observed["calls"])
    spec["others"] = int(observed["others"])
    spec["distinct"] = int(observed["distinct_targets"])
    spec["warm"] = bool(spec.get("warm", False))
    spec.setdefault("package_files", 0)
    spec.setdefault("changed_files", 0)
    spec["observed_shape"] = dict(observed)
    return spec


def claimed_shape(spec: dict[str, Any]) -> dict[str, float | None]:
    """Return what a cell's shape commits it to, before any transcript is built.

    Args:
        spec: The cell's shape, expanded by :func:`expand_shape` so a calibrated cell
            carries the ``observed_shape`` row drawn from the logged sessions.

    Returns:
        One figure per shape field, the same keys :func:`shape_report` pairs.  Where a
        cell has no statement to make about a field the claim is ``None`` rather than a
        number standing in for one, and a report skips it.

        Three kinds of cell make a claim differently, and only because they are made
        differently.  A calibrated cell's figures come from the session rows its shape
        was drawn from.  A hand-built transcript keeps the measured row beside it.  Every
        other cell is assembled by :func:`build_messages` from a shape, so its figures
        are the arithmetic that assembly performs: the batches a call count divides into,
        the turns those batches and the fillers occupy, the seed request the newest
        assistant turn came from, and the chain that precedes it.  This is the only place
        that arithmetic lives; :func:`shape_report` and the ``--shapes`` pre-flight both
        read it here rather than restating it.
    """
    envelopes = int(spec["calls"]) + int(spec.get("others", 0))
    per_turn = max(int(spec.get("calls_per_turn", CALLS_PER_TURN)), 1)
    observed = _claim_row(spec)
    # Two kinds of cell state nothing about the size of a file result.  A transcript
    # assembled by hand writes one fixed result string per call, and its sizes live in the
    # measured row kept beside it - where no such row survives, the block size a generated
    # cell's shape declares was never what the builder was asked to hold.  A text-form
    # transcript carries its file text in user messages, so the characters in its tool
    # messages are not the quantity its name declares.  Either way the field carries no
    # claim rather than a number the built side cannot be graded against.
    stated_chars = (spec.get("form") != "text"
                    and (not spec.get("builder") or bool(observed)))
    fillers = int(spec.get("fillers", 0))
    if spec.get("form") == "text":
        # A text transcript announces one call per assistant message and carries no
        # tool_calls field at all, so the turn count is the opening turn alone, the
        # messages are the announce/result pairs, and the predecessor of the newest
        # message is everything else - there is no batched request to replay.
        batches, turns = envelopes, 1
        messages_claim = 1 + 2 * envelopes + fillers
        chain_claim, seed_claim = 0, max(messages_claim - 1, 0)
    else:
        batches = -(-envelopes // per_turn)
        turns = 1 + batches if envelopes else 1
        messages_claim = 1 + batches + envelopes + fillers
        # The seed is the request that produced the newest assistant turn, so it holds
        # every batch before that one plus the opening turn; the chain is the requests
        # before the seed, which the builder cuts at the same boundary whether or not
        # the timed call replays it.
        chain_claim = max(batches - 1, 0)
        shares = _distribute(fillers, batches + 1) if fillers else [0] * (batches + 1)
        seed_claim = (1 + (per_turn + 1) * max(batches - 1, 0)
                      + sum(shares[:max(batches, 0)]))
    pool = len(real_targets())
    claimed: dict[str, float | None] = {
        "calls": int(spec["calls"]),
        "other_events": int(spec.get("others", 0)),
        "envelopes": envelopes,
        "turns": float(turns),
        "distinct_targets": float(min(int(spec.get("distinct", 0)), int(spec["calls"]),
                                      pool or int(spec["calls"]))),
        "file_chars": (None if not stated_chars else float(observed.get(
            "result_chars", int(spec.get("chars", 0)) * envelopes))),
        "messages": float(observed.get("messages", messages_claim)),
        "seed_messages": float(seed_claim),
        "chain_requests": float(chain_claim),
        # Nothing states how long the JSON of a transcript comes to: a shape gives the
        # calls and their sizes, not the key names and separators wrapped around them, and
        # the projection that guards the ceiling is a bound, not a claim.  A field with no
        # claim reports None so a report can say so instead of grading a made-up number.
        "transcript_bytes": None,
        "package_files": float(spec.get("package_files", 0)),
        "changed_files": float(spec.get("changed_files", 0)),
        "note": 0.0,
    }
    if claimed["calls"] + claimed["other_events"] == 0:
        claimed["note"] = 1.0
    if observed.get("envelopes") is not None:
        claimed["envelopes"] = float(observed["envelopes"])
    if observed.get("calls") is not None:
        claimed["calls"] = float(observed["calls"])
        claimed["other_events"] = float(observed.get("others", 0))
    return claimed


def shape_report(spec: dict[str, Any], messages: list[dict[str, Any]],
                 seed: list[dict[str, Any]], chain: list[list[dict[str, Any]]],
                 calls: list[tuple[str, str, str, bool]], changed: frozenset[str],
                 supplied: tuple[str, ...]) -> dict[str, Any]:
    """Return what the fixture built beside what the cell claims it should hold.

    Args:
        spec: The cell's expanded shape.
        messages: The timed transcript.
        seed: Its immediate predecessor, for a warm cell.
        chain: The requests before that one.
        calls: Every call made, in order, as ``(tool, activity, target, is_file)``.
        changed: The module keys handed to the stage.
        supplied: The files in the context package.

    Returns:
        ``{key: [generated, claimed]}`` for the twelve quantities that define a cell's
        shape.  Where the claim comes from depends on how the cell was made: for a
        calibrated cell it is the row of logged sessions its shape was drawn from, for a
        hand-built transcript it is the measured row kept beside that transcript, and for
        a cell generated from a shape it is the arithmetic that shape commits the builder
        to - the same batches, turns and block sizes :func:`build_messages` applies.
        Either way the pairing is what makes a claim like "realistic p99" checkable
        rather than rhetorical: a reader can see how far the fixture sits from the
        conversation it stands for, and a cell that quietly stops holding its own shape
        is caught by the report instead of by suspicion.

        A ``note`` accompanies an empty shape, because a cell with no file activity has
        no shape to pair and an empty dict alone would read as a failure to look.

        Two fields carry no claim for some cells, and a report skips a field it cannot
        grade.  ``transcript_bytes`` is the length of the JSON that was built, which no
        shape and no session row states.  ``file_chars`` counts the characters in tool
        messages, which is not what a text-form transcript declares and not what a
        hand-built one writes, so those cells state nothing there - see
        :func:`claimed_shape`.  Every other field pairs built against claimed for every
        one of the 25 cells.
    """
    claimed = claimed_shape(spec)
    generated: dict[str, float] = {
        "calls": len([pair for pair in calls if pair[3]]),
        "other_events": len(calls) - len([pair for pair in calls if pair[3]]),
        "envelopes": len(calls),
        "messages": len(messages),
        "seed_messages": len(seed),
        "chain_requests": len(chain),
        "turns": (1 if messages else 0) + sum(1 for message in messages if "tool_calls" in message),
        "distinct_targets": len({pair[2] for pair in calls if pair[3]}),
        "file_chars": sum(len(message.get("content", "")) for message in messages
                          if message.get("role") == "tool"),
        "transcript_bytes": len(json.dumps(messages)),
        "package_files": len(supplied),
        "changed_files": len(changed),
    }
    if not calls:
        # An empty transcript holds no messages, no turns and no envelopes, so the
        # arithmetic that assumes an opening turn gives way to the nothing the cell
        # builds.  A calibration row may still describe the real conversation the cell
        # stands beside; pairing a built zero against a conversation's two messages
        # would report a difference the fixture does not have.
        for key in ("messages", "turns", "seed_messages", "chain_requests", "file_chars"):
            claimed[key] = 0.0
    shapes = {key: [generated[key], claimed[key]] for key in sorted(generated)}
    if not calls:
        shapes["note"] = ["empty_transcript", "empty_transcript"]
    return shapes


def _claim_row(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the figures a cell is expected to hold, from the calibration tables.

    Args:
        spec: The cell's expanded shape, carrying its ``cell`` name and, for a
            calibrated cell, the ``observed_shape`` row :func:`expand_shape` filled.

    Returns:
        A mapping keyed as the tables are, empty when neither has a row for the cell.
        Only two kinds of cell have a row worth consulting: a calibrated one, whose
        shape came from the logged sessions, and a hand-built one, whose transcript was
        assembled by hand rather than from a shape.  For every other cell the row would
        be a coincidence - a name like ``N-count-100`` appears in the older table, but
        that cell is built from a shape now, and grading it against a conversation it
        merely resembles would be the mistake this function existed to avoid.  Those
        cells are paired against arithmetic in :func:`shape_report` instead.

    An empty row is not a failure to look: the report says "off" beside any field the
    cell cannot claim, and a real transcript can still be demanded through the
    ``--transcript`` flag, whose gate refuses a file matching nothing.
    """
    if spec.get("observed_shape"):
        return dict(spec["observed_shape"])
    if spec.get("builder"):
        return dict(CELL_SHAPES.get(str(spec.get("cell"))) or {})
    return {}


def _fit_shape(spec: dict[str, Any], messages: list[dict[str, Any]],
               starts: list[int]) -> tuple[list[dict[str, Any]], list[int]]:
    """Return the transcript adjusted to the message count the calibration observed.

    Args:
        spec: A calibrated cell's expanded shape, edited in place.
        messages: The transcript built before any padding.
        starts: Its assistant-turn indices.

    Returns:
        The rebuilt transcript and turn indices.  A generated conversation that holds
        fewer messages than the one it stands for gets follow-up messages carrying no
        envelope; one that holds more gets its calls grouped into fewer assistant
        turns, which shortens the request list without touching the newest request.
        The loop is bounded: two quantities are being matched with one dial, and a
        shape that cannot be reached is reported by the record rather than hidden.
    """
    observed = spec["observed_shape"]
    wanted = int(observed["messages"])
    for _attempt in range(6):
        deficit = wanted - len(messages)
        if deficit > 0:
            spec["fillers"] = int(spec.get("fillers", 0)) + deficit
        elif deficit < 0:
            spec["fillers"] = 0
            spec["calls_per_turn"] = int(spec.get("calls_per_turn", CALLS_PER_TURN)) * 2
        else:
            break
        messages, starts = build_messages(spec)
    return messages, starts


def _scratch_dir() -> str:
    """Return a real directory outside the repository, for the outside-root cell.

    The normalizer decides containment with ``realpath``, so a target that is to be
    refused as ``outside`` has to be an absolute path that resolves - which a made-up
    path under a invented drive cannot be.  The directory holds nothing and is removed
    when the process ends; no name of it is ever printed.

    Returns:
        The scratch directory's absolute path, with separators that survive JSON.
    """
    path = tempfile.mkdtemp(prefix="e3c1_outside_")
    atexit.register(shutil.rmtree, path, ignore_errors=True)
    return path.replace("\\", "/")


def _stats(samples: list[float]) -> dict[str, float]:
    """Return the summary a block record carries for one arm's timed samples."""
    ordered = sorted(samples)
    return {
        "n": len(samples),
        "mean_ms": statistics.fmean(samples),
        "median_ms": statistics.median(samples),
        "p05_ms": ordered[min(int(0.05 * (len(ordered) - 1)), len(ordered) - 1)],
        "p95_ms": ordered[min(int(0.95 * (len(ordered) - 1)), len(ordered) - 1)],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
    }


def _fixture_files(spec: dict[str, Any]) -> tuple[frozenset[str], tuple[str, ...]]:
    """Return the module keys and the files of one cell's context package.

    Args:
        spec: The cell's expanded shape.

    Returns:
        A ``(changed module keys, supplied files)`` pair.  ``package_files`` asks for
        files the context already supplied; ``changed_files`` asks for files the
        working tree reports as modified *and* the transcript touches.  The two sets
        are disjoint slices of the conversation's own distinct files, so a cell that
        says two changed files means two module identities - which is what the
        changed-files fields of a record count.
    """
    distinct = max(int(spec.get("distinct", 1)), 1)
    touched = sorted({synth_file(index % distinct) for index in range(int(spec["calls"]))})
    supplied = tuple(touched[: int(spec.get("package_files", 0))])
    changed_from = len(supplied)
    changed = frozenset(
        synth_module_key(path)
        for path in touched[changed_from:changed_from + int(spec.get("changed_files", 0))]
        if path.endswith(".py")
    )
    return changed, supplied


def build_fixture(cell: str) -> dict[str, Any]:
    """Return everything one cell needs: transcript, predecessor, package and counts.

    Args:
        cell: A name in :data:`CELLS`.

    Returns:
        A dict of the built fixture: its expanded ``spec``, the timed ``messages``,
        the ``seed`` transcript a warm cell replays first, the ``chain`` of requests
        before that one, the ``package`` and ``changed`` module keys handed to the
        stage, the ``supplied`` and ``touched`` files behind them, the full ``calls``
        list behind the envelopes, and the ``shape`` counts - what was generated, and,
        for a calibrated cell, what the logged sessions held.

    Where a cell's file activity points is decided here rather than named.  Only
    calibration cells keep the targets their sessions really touched; every other cell
    spreads its activity over synthetic paths under the repository root, because a cell
    that reached for the same handful of files over and over would build a chain whose
    distinct-target count is the number of files on the machine, not the number the
    cell claims.  The decision belongs with the builder, not with the table, so adding
    a cell cannot silently inherit someone else's paths.
    """
    spec = dict(CELLS[cell])
    spec["cell"] = cell
    if "files" not in spec:
        spec["files"] = "real" if spec.get("observed_shape") else "synth"
    spec = expand_shape(spec)
    if spec.get("builder") == "outside":
        spec["outside_root"] = _scratch_dir()
    messages, starts = build_messages(spec)
    if spec.get("observed_shape"):
        messages, starts = _fit_shape(spec, messages, starts)
    seed, chain = build_seeds(spec, messages, starts)
    calls = _make_calls(spec)
    touched = sorted({call[2] for call in calls if call[3]})
    changed, supplied = _fixture_files(spec)
    package = build_package(supplied) if supplied else None
    return {"spec": spec, "messages": messages, "seed": seed, "chain": chain,
            "package": package, "changed": changed, "supplied": supplied,
            "touched": touched, "calls": calls,
            "shape": shape_report(spec, messages, seed, chain, calls, changed, supplied)}


def warm_gate(fixture: dict[str, Any]) -> tuple[bool, str]:
    """Return whether the seeded prefix really is the timed transcript's predecessor.

    The tracker stores a state under the fingerprint of the transcript it saw and finds
    it again through the fingerprint of the transcript *before* the newest assistant
    turn.  If those two do not agree the cell would be measuring a cold conversation
    while claiming to measure a warm one, so the cell is invalid rather than slow.
    """
    if not fixture["spec"]["warm"]:
        return True, "cold"
    _seed_key, store_key = transcript_fingerprints(fixture["seed"])
    lookup_key, _store = transcript_fingerprints(fixture["messages"])
    if lookup_key == store_key:
        return True, "matched"
    return False, "prefix_mismatch"


def _betacf(a: float, b: float, x: float) -> float:
    """Evaluate the continued fraction of the incomplete beta function.

    The recurrence is Lentz's, in the form Numerical Recipes gives it: the odd step
    inverts, the even step does not, and getting that order wrong converges to a value
    that is very nearly right - which a benchmark would never notice and a Student-t
    critical value would.
    """
    eps, fpmin = 3.0e-9, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    total = d
    for step in range(1, 200):
        even = step * 2
        aa = step * (b - step) * x / ((qam + even) * (a + even))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        total *= d * c
        aa = -(a + step) * (qab + step) * x / ((a + even) * (qap + even))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        total *= delta
        if abs(delta - 1.0) < eps:
            break
    return total


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_beta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(log_beta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(log_beta) * _betacf(b, a, 1.0 - x) / b


def _t_cdf(t_value: float, deg: float) -> float:
    return 1.0 - 0.5 * _betainc(deg / 2.0, 0.5, deg / (deg + t_value * t_value))


def t_critical(probability: float, deg: float) -> float:
    """Return the one-sided Student-*t* quantile for ``probability`` at ``deg`` degrees."""
    if deg <= 0:
        return float("nan")
    low, high = 0.0, 100.0
    for _ in range(200):
        middle = (low + high) / 2.0
        if _t_cdf(middle, deg) < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _freshness(identities: list[tuple[int, int, int, int]]) -> dict[str, Any]:
    """Return what the constructed identities prove about one arm's block.

    Args:
        identities: The ``(stage, tracker, context, package)`` object ids recorded by
            each preparation, in the order they were built.

    Returns:
        How many invocations the block ran and, for each object that must never be
        reused, how many distinct identities appeared.  A tracker that appears once
        while four invocations ran is the failure this rule exists to catch - a
        normalized path cache or a correlation state carried from one sample into the
        next, which is free time the measurement would not show.
    """
    counts: dict[str, Any] = {"invocations": len(identities)}
    for name, position in (("stage", 0), ("tracker", 1), ("context", 2)):
        counts[f"distinct_{name}"] = len({slot[position] for slot in identities
                                          if slot[position]})
    counts["reused_packages"] = len([slot for slot in identities if slot[3]]) \
        - len({slot[3] for slot in identities if slot[3]})
    return counts


def _unique(identities: list[list[int]]) -> bool:
    """Return whether every timed invocation of a block built objects nothing else touched.

    Args:
        identities: The constructed identity tuples of both arms, pooled.

    Returns:
        ``True`` when no stage, no context and no tracker appears twice.  A package
        may repeat - a cell that supplies no files builds no package at all, and
        ``None`` has one identity - so its repetition is reported rather than judged.
    """
    slots = [tuple(entry) for entry in identities]
    trackers = [slot[1] for slot in slots if slot[1]]
    return (len({slot[0] for slot in slots}) == len(slots)
            and len({slot[2] for slot in slots}) == len(slots)
            and len(set(trackers)) == len(trackers))


def run_block(cell: str, batch: int, want_correctness: bool,
              block: int = 0) -> dict[str, Any]:
    """Time ``batch`` groups of both arms in one process and return one status record.

    Args:
        cell: The cell to run.
        batch: Groups per block; a group is four invocations, two per arm.
        want_correctness: Whether to compare what the arms recorded as well as what
            they cost.
        block: The block index, which decides the group order: an even block runs
            ``ABBA`` (candidate, control, control, candidate) and an odd block the
            mirror ``BAAB``.  Alternating them is what stops a slow start or a warming
            cache from landing on one arm every time.

    Returns:
        One block record: per-arm timings, the order actually run, what the constructed
        identities prove about freshness, and the verdict when asked for.
    """
    fixture = build_fixture(cell)
    record: dict[str, Any] = {"cell": cell, "pid": os.getpid(), "batch": batch,
                              "block": block,
                              "pass": "correctness" if want_correctness else "latency",
                              "shape": fixture["shape"]}
    if int(fixture["shape"]["transcript_bytes"][0]) > MAX_TRANSCRIPT_BYTES:
        record["status"] = "invalid_transcript_too_large"
        return record
    ok, why = warm_gate(fixture)
    record["warm_gate"] = why
    if not ok:
        record["status"] = "invalid_" + why
        return record
    arms = {"candidate": Arm(fixture, "candidate"), "control": Arm(fixture, "control")}
    order = ORDER_FLIPPED if block % 2 else ORDER
    samples: dict[str, list[float]] = {"candidate": [], "control": []}
    started = time.perf_counter()
    for _ in range(batch):
        for name in order:
            arm = arms[name]
            arm.prepare()
            # The preparation just handed the interpreter everything the replay and the
            # fresh stage stopped referring to.  Collecting it here keeps a generation
            # from being reaped inside the timed call, where it would land as a tail
            # neither arm's work made and the paired delta would have to carry.
            gc.collect()
            mark = time.perf_counter()
            arm.timed()
            samples[name].append((time.perf_counter() - mark) * 1000.0)
    record["order"] = "".join("C" if name == "candidate" else "T" for name in order)
    for name, arm in arms.items():
        record[f"{name}_states"] = (arm.stage._file_activity.state_count()
                                    if arm.stage is not None
                                    and arm.stage._file_activity is not None else None)
        record[f"{name}_freshness"] = _freshness(arm.identities)
    record["objects_fresh"] = _unique(
        [entry for arm in arms.values() for entry in arm.identities])
    record["block_seconds"] = time.perf_counter() - started
    if not samples["candidate"]:
        # A gate cell has no timed invocations: its batch is zero because the cell
        # exists to check a payload, not to produce a delta.  The record says so in its
        # status rather than averaging an empty list into a mean of zero, which would
        # read as "C1 costs nothing here" in any table that pooled it.
        record["candidate"] = record["control"] = {"n": 0, "mean_ms": 0.0}
        record["delta_ms"] = None
        record["status"] = "not_timed"
    else:
        for name in samples:
            record[name] = _stats(samples[name])
        record["delta_ms"] = record["candidate"]["mean_ms"] - record["control"]["mean_ms"]
        record["status"] = "ok"
    if want_correctness:
        record["correctness"] = check_correctness(fixture, arms)
        if not record["correctness"]["passed"]:
            record["status"] = "correctness_failed"
    return record


def derive_expected(fixture: dict[str, Any],
                    correlation: str | None = None) -> dict[str, Any]:
    """Return the payload a cell must produce, computed from the cell's own shape.

    Args:
        fixture: The built fixture, whose ``"calls"`` are the envelopes the transcript
            carries in the order they appear.
        correlation: The correlation the candidate recorded, when it is known.  Which
            correlation applies is a property of the tracker's lineage - whether it saw
            an earlier request in this conversation and whether that request carried a
            package - and re-deriving it here would mean writing the correlator a second
            time.  Given the correlation, the partition of the touched set is arithmetic,
            and that is what this function can state independently: ``measured`` splits
            touched into what the package supplied and the rest, ``no_prior_context``
            claims nothing was supplied by an earlier request so the whole set is the
            rest, and any other correlation says the pair is unknown, which the module
            renders as a pair of zeros.

    Returns:
        A full payload to compare against, every field named.  The counters are not
        copied out of an earlier run; they follow from how many envelopes the bound
        retains and what each of those envelopes says, which is the same rule the
        module documents at :func:`packages.pipeline.file_activity.build_file_activity`.

        Cells whose transcript is built by hand - the ones that probe rejection and the
        cap - carry their own ``expected`` instead, because their envelope list is not
        the shape's arithmetic.
    """
    spec = fixture["spec"]
    if "expected" in spec:
        declared = dict(spec["expected"])
        if declared.get("correlation") == INERT_FILE_ACTIVITY["correlation"]:
            # inert_payload() fills every field a cell does not probe with the control's
            # own value, and for correlation that value is the token for "no tracker at
            # all".  A gate cell runs with a tracker, so an unprobed correlation is not a
            # claim of "unavailable" - it is the cell not stating one, and the token the
            # candidate took is what this expectation has to be held to.
            declared["correlation"] = str(correlation or "tracker_miss")
        return declared
    window = int(spec.get("window", MAX_ENVELOPES_PER_REQUEST))
    retained = fixture["calls"][-window:] if len(fixture["calls"]) > window else fixture["calls"]
    reads = {synth_module_key(call[2]) for call in retained
             if call[3] and call[1] == "read" and call[2].endswith(".py")}
    modified = {synth_module_key(call[2]) for call in retained
                if call[3] and call[1] == "modified" and call[2].endswith(".py")}
    touched = reads | modified
    beyond = max(len(fixture["calls"]) - window, 0)
    others = sum(1 for call in retained if not call[3])
    # Two builder facts change what a transcript reports without changing its shape: a
    # path that resolves outside the repository root never becomes an outcome at all,
    # and a result block past the size the module is willing to read is an attempt whose
    # outcome stayed unknown.  Both are properties of how the cell was made, so stating
    # them here keeps the expectation a claim about the construction rather than a copy
    # of a recorded run.
    rejected = len(reads) + len(modified) if spec.get("builder") == "outside" else 0
    unknown = int(spec.get("chars", 0)) > MAX_NATIVE_RESULT_CHARS
    files_read = 0 if rejected or unknown else len(reads)
    files_modified = 0 if rejected or unknown else len(modified)
    correlation = str(spec.get("expect_correlation") or correlation or (
        "measured" if spec["warm"] else (
            "no_prior_context"
            if transcript_fingerprints(fixture["messages"])[0] == NEW_CONVERSATION_KEY
            else "tracker_miss")))
    supplied = {synth_module_key(path) for path in fixture["supplied"]}
    if spec.get("entry") == "execute":
        # The stage-level path runs with no index, so it hands the correlator nothing
        # to correlate against; that is a real answer and why the decision cell states
        # its own expectation rather than deriving one here.
        supplied = set()
    touched_count = 0 if rejected or unknown else len(touched)
    if correlation == "measured":
        credited = len(touched & supplied) if touched_count else 0
        without = touched_count - credited
    elif correlation == "no_prior_context":
        credited, without = 0, touched_count
    else:
        credited = without = 0
    return {
        "state": ("partial" if beyond else
                  ("measured" if touched_count or others or rejected or unknown else "none")),
        "correlation": correlation,
        "files_read": files_read,
        "files_modified": files_modified,
        "files_touched": touched_count,
        "read_attempts": 0 if rejected else len(reads),
        "modification_attempts": 0 if rejected else len(modified),
        "paths_rejected": rejected,
        "context_files_touched": credited,
        "touched_without_context": without,
        "changed_files_touched": len(touched & set(fixture["changed"])) if touched_count else 0,
        "events_beyond_bound": beyond,
        "other_events": others,
        "modifications_not_modified": 0,
        "modifications_unknown": len(modified) if unknown else 0,
        "reads_failed": 0,
        "reads_unknown": len(reads) if unknown else 0,
    }


def check_correctness(fixture: dict[str, Any],
                      arms: Mapping[str, "Arm"]) -> dict[str, Any]:
    """Compare what the two arms recorded for the same transcript, field by field.

    Args:
        fixture: The cell's built fixture.
        arms: Both arms, whose timed calls have already run.

    Returns:
        The verdict, the per-rule checks, and - when a field disagrees - both the
        expected and the observed value, so a failure names the field rather than only
        the rule.  The control arm is expected to record nothing at all, which is the
        same no-op that makes its timing a clean baseline.
    """
    payload = arms["candidate"].payload()
    expected = derive_expected(fixture, payload.get("correlation"))
    inert = arms["control"].payload()
    strings = {value for value in payload.values() if isinstance(value, str)}
    touched = int(payload.get("files_touched", -1))
    credited = int(payload.get("context_files_touched", -1))
    without = int(payload.get("touched_without_context", -1))
    partitions = expected["correlation"] in ("measured", "no_prior_context")
    mismatched = {key: {"expected": value, "observed": payload.get(key)}
                  for key, value in expected.items()
                  if key not in payload or payload[key] != value}
    checks = {
        "payload_has_exactly_the_inert_fields": sorted(payload) == sorted(INERT_KEYS),
        "every_field_equals_expectation": not mismatched,
        "candidate_state": payload.get("state") == expected["state"],
        "candidate_correlation": payload.get("correlation") == expected["correlation"],
        "control_recorded_nothing": inert == {},
        "no_path_in_payload": not any(
            ("/" in value or "\\" in value or value.endswith(".py")) for value in strings),
        "states_are_closed_tokens": strings <= set(FILE_ACTIVITY_STATES)
        | set(FILE_ACTIVITY_CORRELATION_STATES),
        "counts_are_non_negative_integers": all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for key, value in payload.items() if key not in ("state", "correlation")),
        "correlation_partitions_touched": credited + without == touched if partitions
        else (credited == 0 and without == 0),
        "correlation_bounded_by_supplied": credited <= len(fixture["supplied"]),
        "touched_bounded_by_attempts": touched <= int(payload.get("read_attempts", 0))
        + int(payload.get("modification_attempts", 0)),
    }
    return {"passed": all(checks.values()), "checks": checks, "expected": expected,
            "mismatched": mismatched, "candidate": payload, "control_payload": inert,
            "observed": {key: value for key, value in payload.items()
                         if isinstance(value, int)}}


def run_estimate(cell: str, batch: int = 1) -> dict[str, Any]:
    """Time one small group so a batch size can be chosen from a measurement.

    Returns:
        The block record plus how many invocations per arm would hold the timed region
        near :data:`MIN_SAMPLE_MS`, and how long a block at that batch would take.  The
        batch is set by arithmetic, not by preference: the gate is that a block should
        not run for minutes, and a sample should not last microseconds.
    """
    record = run_block(cell, batch, False)
    if "candidate" in record:
        target = MIN_SAMPLE_MS / max(record["candidate"]["mean_ms"], 1e-6)
        record["batch_for_60ms_sample"] = max(int(target), 1)
        record["block_seconds_at_batch"] = record["block_seconds"]
    return record


def run_diag(cell: str, batch: int) -> dict[str, Any]:
    """Record allocation and garbage-collection work per arm for one cell.

    Returns:
        Per-arm milliseconds, peak allocation, and the collection counters around the
        block.  Each invocation still builds its own stage, so the peak is what one
        request costs rather than what a reused stage amortizes away.  The collection
        counts matter because a fresh stage per invocation is also fresh garbage: a
        generation collected inside the next sample would show up as a tail the timing
        alone cannot explain.  Since that collection now runs on purpose between the
        preparation and the timer, what these counters move by is what the timed call
        itself allocated - the narrower of the two questions, and the one a sample can
        answer.
    """
    import tracemalloc

    fixture = build_fixture(cell)
    ok, why = warm_gate(fixture)
    record: dict[str, Any] = {"cell": cell, "pass": "diag", "warm_gate": why,
                              "shape": fixture["shape"], "batch": batch}
    if not ok:
        record["status"] = "invalid_" + why
        return record
    per_arm: dict[str, Any] = {}
    for name in ("candidate", "control"):
        arm = Arm(fixture, name)
        gc.collect()
        before_counts = gc.get_count()
        marks = []
        tracemalloc.start()
        for _ in range(batch):
            arm.prepare()
            # Same rule as the timed block: what the preparation stopped referring to is
            # collected before the timer starts, so a sample never pays for the last
            # one's garbage.
            gc.collect()
            mark = time.perf_counter()
            arm.timed()
            marks.append((time.perf_counter() - mark) * 1000.0)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        per_arm[name] = {"stats": _stats(marks), "peak_alloc_bytes": peak,
                         "gc_counts_delta": [a - b for a, b in zip(gc.get_count(),
                                                                   before_counts, strict=True)],
                         "states": (arm.stage._file_activity.state_count()
                                    if arm.stage is not None
                                    and arm.stage._file_activity is not None else None),
                         "freshness": _freshness(arm.identities)}
    record["arms"] = per_arm
    record["delta_ms"] = (per_arm["candidate"]["stats"]["mean_ms"]
                          - per_arm["control"]["stats"]["mean_ms"])
    record["status"] = "ok"
    return record


def _interval(deltas: list[float]) -> dict[str, float]:
    """Return the conservative two-sided interval for a cell's block deltas.

    This is the harness's one interval estimate and :func:`_verdict` its one reading;
    :func:`report` calls both, and nothing else is allowed to estimate a bound of its
    own.  A second implementation closed the same question on whichever of its two
    methods happened to answer more favorably, which is how a cell could be reported as
    measured while the other method still said it was not.

    Args:
        deltas: One candidate-minus-control millisecond figure per block.

    Returns:
        The ``lower`` and ``upper`` bounds beside each method's own pair: ``t_lower`` and
        ``t_upper`` from the Student-*t* interval on the block mean, ``order_lower`` and
        ``order_upper`` from the order statistic that keeps a block with an unlucky tail
        from being talked out of its own evidence.  ``lower`` is the *minimum* of the two
        lower bounds and ``upper`` the *maximum* of the two upper bounds, so the reported
        interval contains what both methods claimed rather than the narrower of them.
        With fewer than two blocks nothing is claimed: the interval collapses to the mean
        and ``insufficient`` says so.
    """
    mean = statistics.fmean(deltas)
    if len(deltas) < 2:
        return {"lower": mean, "upper": mean, "t_lower": mean, "t_upper": mean,
                "order_lower": mean, "order_upper": mean, "t_interval": 0.0,
                "order_rank": 0, "sd": 0.0, "se": 0.0, "insufficient": 1.0}
    spread = statistics.stdev(deltas)
    standard_error = spread / math.sqrt(len(deltas))
    critical = t_critical(0.975, len(deltas) - 1)
    t_lower, t_upper = mean - critical * standard_error, mean + critical * standard_error
    ordered = sorted(deltas)
    rank = max(int(math.ceil(0.025 * (len(ordered) + 1))) - 1, 0)
    order_lower, order_upper = ordered[rank], ordered[len(ordered) - 1 - rank]
    return {"lower": min(t_lower, order_lower), "upper": max(t_upper, order_upper),
            "t_lower": t_lower, "t_upper": t_upper,
            "order_lower": order_lower, "order_upper": order_upper,
            "t_interval": critical * standard_error, "order_rank": rank + 1,
            "sd": spread, "se": standard_error, "insufficient": 0.0}


def _verdict(interval: dict[str, float]) -> str:
    """Return the decision a conservative interval supports, in the registered words."""
    if interval["insufficient"]:
        return "insufficient_blocks"
    if interval["upper"] < NEGLIGIBLE_MS:
        return "close_measured_negligible"
    if interval["lower"] >= ACTIONABLE_MS:
        return "close_measured_actionable"
    if interval["upper"] < ACTIONABLE_MS:
        return "close_measured_not_proven_negligible"
    return "expansion_needed"


def _batch_for(cell: str) -> int:
    """Return how many timed groups per arm one block of this cell should hold.

    The table's own value, and nothing else: no cell is special-cased by name.  A warm
    cell is not run shallow because it is warm - its :data:`BATCHES` entry was chosen
    from the estimate pass, which is what keeps a block inside
    :data:`TARGET_BLOCK_SECONDS`.
    """
    return BATCHES.get(cell, 1)


def resolve_batch(requested: int, cell: str) -> int:
    """Return the groups per arm a latency run should use for ``cell``.

    Args:
        requested: The ``--batch`` value, or ``0`` when the flag was not given.
        cell: The cell being run.

    Returns:
        What the caller asked for when it asked for something, and otherwise the cell's
        :data:`BATCHES` entry.  This is the only place the two meet: a name in the cell
        cannot put the table aside, and a ``--batch`` on the command line cannot be
        quietly ignored by it.
    """
    return requested if requested > 0 else _batch_for(cell)


def projected_bytes(spec: dict[str, Any]) -> int:
    """Return the approximate size of a cell's transcript without building it.

    The 32 MB ceiling is a pre-allocation guard, so it has to be consulted before the
    fixture exists: a cell that would cross it is reported as not measurable rather
    than attempted.  The sizes come from :func:`envelope_sizes`, the same function that
    lays the transcript out, so the guard cannot disagree with the build; the JSON
    envelope around each result block is added as a flat per-envelope overhead.
    """
    sizes = envelope_sizes(expand_shape(dict(spec)))
    return sum(sizes) + 600 * len(sizes) + 4096


def sweep(pass_name: str, blocks: int, out_dir: Path, pattern: str) -> int:
    """Run every matching cell in a fresh process per block and collect the records.

    Args:
        pass_name: Which pass to run: the correctness gate or the timed comparison.
        blocks: How many times to run each cell, each in its own process.
        out_dir: Where to write the JSON-lines file, one block record per line.
        pattern: Only cells whose name contains this run.

    Returns:
        The worst exit code seen, so a caller can tell a clean sweep from one where a
        cell failed to build, failed its gate, or could not be measured.

    Each block is a separate process on purpose.  A stage that survives from one block
    to the next keeps the conversations it has already seen, so a warm replay in the
    second block would find its state already there: free time the sample would not
    show, and a chain that is no longer the conversation the cell claims to hold.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sweep-{pass_name}.jsonl"
    worst = 0
    with path.open("w", encoding="utf-8") as sink:
        for cell in sorted(name for name in CELLS if pattern in name):
            for block in range(blocks):
                completed = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--pass", pass_name,
                     "--cell", cell, "--block", str(block), "--batch", str(_batch_for(cell))],
                    capture_output=True, text=True, check=False)
                for line in completed.stdout.splitlines():
                    if line.startswith("{"):
                        record = json.loads(line)
                        record["block"] = block
                        sink.write(json.dumps(record, sort_keys=True) + "\n")
                if completed.returncode != 0:
                    worst = completed.returncode
                print(f"{cell} block {block}: exit {completed.returncode}", flush=True)
                if completed.stderr.strip():
                    print(completed.stderr.strip(), file=sys.stderr, flush=True)
    print(f"wrote {path}")
    return worst


def report(out_dir: Path, pattern: str) -> int:
    """Print what the collected blocks say, with the shape evidence beside each cell.

    Args:
        out_dir: The directory holding the ``sweep-*.jsonl`` files a sweep wrote.
        pattern: Report only the cells whose name contains this.

    Returns:
        Zero when every cell matching ``pattern`` has records, two when one has none.

    A gate reads ``pass`` only when every correctness block of that cell came back with a
    comparison that passed.  A block which refused to run - a transcript over the ceiling,
    a warm gate that matched nothing - carries no comparison at all, which is a refusal and
    not a pass, so it fails the gate and its own status is listed under ``gate_statuses``.
    """
    records: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(out_dir.glob("sweep-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                found = json.loads(line)
                if pattern in found["cell"]:
                    records.setdefault(found["cell"], []).append(found)
    for cell in sorted(records):
        found = records[cell]
        timed = [r for r in found if r.get("pass", "latency") == "latency"
                 and r.get("status") == "ok"]
        gate = [r for r in found if r.get("pass") == "correctness"]
        # A block that never reached the comparison carries no correctness object at all:
        # a transcript over the ceiling or a failed warm gate returns before either arm
        # runs.  That is a gate which refused, not a gate which passed quietly, so it fails
        # the cell, and the statuses say which rule refused it.
        refused = [r for r in gate
                   if not (r.get("correctness") or {}).get("passed")]
        row: dict[str, Any] = {"cell": cell, "blocks": len(found), "timed": len(timed),
                               "gate": ("-" if not gate else
                                        "pass" if not refused else "FAIL")}
        if refused:
            row["gate_statuses"] = sorted({str(r.get("status")) for r in refused})
        if timed:
            interval = _interval([r["delta_ms"] for r in timed])
            row.update({
                "cand_us": round(statistics.fmean(
                    r["candidate"]["mean_ms"] for r in timed) * 1000, 1),
                "ctrl_us": round(statistics.fmean(
                    r["control"]["mean_ms"] for r in timed) * 1000, 1),
                "delta_us": round(statistics.fmean(
                    [r["delta_ms"] for r in timed]) * 1000, 1),
                "lower_us": round(interval["lower"] * 1000, 1),
                "upper_us": round(interval["upper"] * 1000, 1),
                "verdict": _verdict(interval),
                "objects_fresh": all(r.get("objects_fresh") for r in timed),
            })
        else:
            row["verdict"] = "no_usable_blocks"
            row["statuses"] = sorted({str(r.get("status")) for r in found})
        shapes = found[0].get("shape") or {}
        row["shape_fields_off"] = sorted(
            key for key, pair in shapes.items()
            if key != "note" and pair[1] is not None
            and abs(pair[0] - pair[1]) / max(pair[1], 1) > SHAPE_TOLERANCE)
        print(json.dumps(row, sort_keys=True))
    missing = sorted(name for name in CELLS if pattern in name and name not in records)
    if missing:
        print(json.dumps({"cells_without_records": missing}))
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pass", dest="pass_name", default="latency",
                        choices=("latency", "correctness", "diag", "estimate"))
    parser.add_argument("--cell", default="N-count-100", choices=tuple(CELLS))
    parser.add_argument("--block", type=int, default=0)
    parser.add_argument("--batch", type=int, default=0,
                        help="timed groups per block, overriding this cell's BATCHES value")
    parser.add_argument("--out", default=str(REPO_ROOT / "build" / "e3lat"))
    parser.add_argument("--sweep", metavar="PASS", choices=("latency", "correctness"),
                        help="run every matching cell in a fresh process per block")
    parser.add_argument("--blocks", type=int, default=8, help="blocks per cell to sweep")
    parser.add_argument("--report", action="store_true",
                        help="print what the records in --out say")
    parser.add_argument("--filter", default="", help="only cells whose name contains this")
    parser.add_argument("--shapes", action="store_true")
    args = parser.parse_args(argv)

    if args.sweep:
        return sweep(args.sweep, args.blocks, Path(args.out), args.filter)

    if args.report:
        return report(Path(args.out), args.filter)

    if args.shapes:
        for cell, spec in sorted(CELLS.items()):
            expanded = expand_shape(dict(spec))
            claim = claimed_shape(expanded)
            projected = projected_bytes(expanded)
            print(json.dumps({"cell": cell, "projected_bytes": projected,
                              "warm": bool(expanded.get("warm", False)),
                              "fits_cap": projected <= MAX_TRANSCRIPT_BYTES,
                              "claim": {key: value for key, value in claim.items()
                                        if value is not None}},
                             sort_keys=True))
        return 0

    spec = CELLS[args.cell]
    if projected_bytes(spec) > MAX_TRANSCRIPT_BYTES:
        print(json.dumps({"cell": args.cell, "status": "invalid_transcript_too_large",
                          "projected_bytes": projected_bytes(spec)}, sort_keys=True))
        return 3

    if args.pass_name == "estimate":
        record = run_estimate(args.cell, max(args.batch, 1))
    elif args.pass_name == "diag":
        record = run_diag(args.cell, args.batch or 8)
    else:
        # A timed run takes the batch the caller asked for, and the table's value when it
        # asked for none.  A correctness run is not a sample of anything: two invocations
        # per arm is the comparison, so it stays at one group whatever the table says.
        record = run_block(args.cell,
                           resolve_batch(args.batch, args.cell)
                           if args.pass_name == "latency" else 1,
                           args.pass_name == "correctness", args.block)
    record["block"] = args.block
    record["pass"] = args.pass_name
    print(json.dumps(record, sort_keys=True))
    return 0 if record.get("status", "ok") in ("ok", "not_timed") else 3


if __name__ == "__main__":
    sys.exit(main())
