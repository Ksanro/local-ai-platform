"""Count-only transcript-shape calibration for roadmap E3 item 3.

The benchmark in ``scripts/bench_c1_latency.py`` has to ask a realistic request to
C1, and "realistic" cannot be invented: it has to be measured.  This script reads
the transcripts this machine's own Cline sessions stored and reports what they
*count* - messages, turns, tool calls, result characters, distinct file targets.

Nothing else is reported.  A path or a target that appears in a transcript is
reduced to a one-way digest used only to count how many distinct ones there were,
and no digest is printed.  Message text, ``say`` and ``ask`` field values, session
identifiers and tool names never reach the output, so this script's stdout is safe
to paste into an issue or a commit.

Two transcript dialects are read, because a stored session is not a request:

* the OpenAI chat form a gateway actually receives - ``tool_calls`` on an assistant
  turn answered by a ``role: "tool"`` message, which
  :func:`packages.pipeline.cline_activity.parse_envelopes` recognizes;
* the Anthropic block form Cline's own storage uses - ``tool_use`` and
  ``tool_result`` content blocks, which that parser does not recognize.

The block-form numbers are a *count-only shape proxy*: they say how big a real
conversation gets.  They do not show what a live gateway's request bodies contain,
and nothing here should be read as evidence that a request carries one form or the
other.

Usage::

    uv run python scripts/calibrate_c1_shapes.py
    uv run python scripts/calibrate_c1_shapes.py --root "C:\\path\\to\\sessions"
    uv run python scripts/calibrate_c1_shapes.py --paste
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.pipeline.cline_activity import NATIVE_TOOL_ACTIVITY  # noqa: E402

#: The tool names whose call or block names a file, in either dialect.  The readers
#: read and the writers modify; a tool outside this set is activity naming no file.
FILE_TOOLS: frozenset[str] = frozenset({
    "read_files", "editor", "write_files", "read_file", "write_to_file",
    "replace_in_file",
})

#: The percentile ranks reported as shapes.  ``p99`` of 39 sessions is its most
#: expensive member, which is the point of reporting one: a joint shape.
PERCENTILES: tuple[float, ...] = (0.50, 0.90, 0.95, 0.99)

#: How far below an exact rank the rounding slack reaches, in rank units.  A rank times a
#: count is a whole number when the rank divides the count, and binary fractions put it a
#: hair above; this slack is what keeps ``p99`` of 100 sessions on its 99th row.
RANK_SLACK: float = 1e-9

#: Every key :func:`percentile_shapes` reports.  Listing it here lets the privacy
#: test assert that a shape row holds integers and nothing else.
SHAPE_KEYS: tuple[str, ...] = (
    "calls", "others", "messages", "turns", "tool_turns", "file_turns",
    "result_chars", "max_result", "distinct_targets", "native_calls",
    "envelope_calls", "envelope_messages", "block_results",
)

#: The marker that closes a legacy envelope header, kept here so this script counts
#: the same headers the production parser recognizes.
LEGACY_TAIL = "] Result:"


def default_root() -> Path:
    """Return the session-data directory this platform keeps transcripts in."""
    return Path.home() / ".cline" / "data" / "sessions"


def digest(value: object) -> str:
    """Return a one-way marker for one target's identity.

    Args:
        value: Anything found where a transcript names a file.  Never returned to a
            caller's output and never printed: the digest only lets a caller count
            how many distinct targets a transcript named.

    Returns:
        A hex digest that cannot be turned back into the value.
    """
    return hashlib.sha256(repr(value).encode("utf-8", "replace")).hexdigest()


def _text_of(content: object) -> str:
    """Return the content of one message as the text whose length is counted."""
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def _arguments_of(call: object) -> object:
    """Return the decoded arguments of one native tool call, or ``None``."""
    function = call.get("function") if isinstance(call, dict) else None
    if not isinstance(function, dict):
        return None
    raw = function.get("arguments")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return None
    return None


def _targets_of(arguments: object) -> list[object]:
    """Return the file targets one decoded argument object names, unvalidated."""
    if not isinstance(arguments, dict):
        return []
    found: list[object] = []
    files = arguments.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and "path" in item:
                found.append(item["path"])
    for key in ("path", "file_path"):
        if key in arguments:
            found.append(arguments[key])
    return found


def _legacy_head(text: str) -> str | None:
    """Return a legacy envelope's header text, or ``None`` if it has none.

    Args:
        text: One user message's content.

    Returns:
        The text between the opening bracket and the ``"] Result:"`` marker.  Only
        the first 4,000 characters are examined, and what is returned is counted
        and never printed.
    """
    marker = text.find(LEGACY_TAIL, 0, 4000)
    if marker < 0 or not text.startswith("["):
        return None
    return text[1:marker]


def scan_native(messages: list[Any], targets: set[str] | None = None) -> dict[str, int]:
    """Count the OpenAI-form activity of one stored or replayed transcript.

    Args:
        messages: A chat ``messages`` list.
        targets: An optional set to add each distinct file target's digest to, so a
            caller scanning both dialects can count the union rather than the sum.

    Returns:
        Counts only: recognized file-naming and non-file calls, the characters their
        results carry, the largest single result and how many distinct files were
        named.  The legacy text form - a user message with a
        ``"[tool for path] Result:"`` header - is counted here too, because that is
        how an older Cline reported the same activity.
    """
    out = {"calls": 0, "others": 0, "result_chars": 0, "max_result": 0,
           "distinct_targets": 0, "envelope_calls": 0, "envelope_messages": 0}
    if targets is None:
        targets = set()
    announced: dict[str, tuple[str, object]] = {}
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "assistant":
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                name = function.get("name") if isinstance(function, dict) else None
                call_id = call.get("id") if isinstance(call, dict) else None
                if not isinstance(name, str) or name not in NATIVE_TOOL_ACTIVITY:
                    continue
                if not isinstance(call_id, str):
                    continue
                announced[call_id] = (name, _arguments_of(call))
            continue
        if role == "tool":
            call = announced.get(str(message.get("tool_call_id", "")))
            if call is None:
                continue
            name, arguments = call
            named_file = name in FILE_TOOLS
            out["calls" if named_file else "others"] += 1
            length = len(_text_of(message.get("content")))
            out["result_chars"] += length
            out["max_result"] = max(out["max_result"], length)
            if named_file:
                for target in _targets_of(arguments):
                    targets.add(digest(target))
            continue
        if role == "user":
            text = message.get("content")
            if not isinstance(text, str):
                # A user message whose content is a block list is Anthropic-form, and
                # :func:`scan_blocks` counts its results; serializing it here to look
                # for a legacy header would count one result in both dialects.
                continue
            head = _legacy_head(text)
            if head is None:
                continue
            out["envelope_messages"] += 1
            out["envelope_calls"] += 1
            out["result_chars"] += len(text)
            out["max_result"] = max(out["max_result"], len(text))
            for piece in head.replace("{", " ").replace("}", " ").split(","):
                if "path" in piece:
                    targets.add(digest(piece))
    out["distinct_targets"] = len(targets)
    return out


def scan_blocks(messages: list[Any], targets: set[str] | None = None) -> dict[str, int]:
    """Count the Anthropic block form of one stored transcript.

    Args:
        messages: A chat ``messages`` list in the shape Cline's own storage uses.
        targets: An optional set to add each distinct file target's digest to.

    Returns:
        Counts of ``tool_use`` blocks by whether they name a file, of
        ``tool_result`` blocks and their characters, of assistant turns of each
        kind, and of distinct file targets.  These numbers describe a *stored*
        conversation: ``parse_envelopes`` recognizes neither block kind, so a
        gateway handed this shape would report no activity at all.
    """
    out = {"calls": 0, "others": 0, "block_results": 0, "result_chars": 0,
           "max_result": 0, "distinct_targets": 0, "tool_turns": 0, "file_turns": 0}
    if targets is None:
        targets = set()
    for message in messages:
        blocks = message.get("content") if isinstance(message, dict) else None
        if not isinstance(blocks, list):
            continue
        named_file = False
        announced = False
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "tool_use":
                announced = True
                name = str(block.get("name"))
                if name in FILE_TOOLS:
                    named_file = True
                    out["calls"] += 1
                    for target in _targets_of(block.get("input")):
                        targets.add(digest(target))
                else:
                    out["others"] += 1
            elif kind == "tool_result":
                out["block_results"] += 1
                length = len(_text_of(block.get("content")))
                out["result_chars"] += length
                out["max_result"] = max(out["max_result"], length)
        if announced:
            out["tool_turns"] += 1
        if named_file:
            out["file_turns"] += 1
    out["distinct_targets"] = len(targets)
    return out


def scan_transcript(messages: list[Any]) -> dict[str, int]:
    """Return one session's counts in both dialects, merged into one shape row.

    Args:
        messages: The session's stored ``messages`` list.

    Returns:
        A row carrying the keys of :data:`SHAPE_KEYS`.  The two dialects are summed,
        not chosen between: a stored conversation keeps its results in one form or
        the other, and a transcript that carries both has activity in both.  The
        per-dialect columns are kept separate as well, so a reader can see which
        form produced a number.
    """
    targets: set[str] = set()
    native = scan_native(messages, targets)
    blocks = scan_blocks(messages, targets)
    roles = [str(m.get("role")) for m in messages if isinstance(m, dict)]
    row = {"messages": len(messages), "turns": sum(1 for role in roles if role == "assistant")}
    for key in ("calls", "others", "result_chars"):
        row[key] = native[key] + blocks[key]
    row["max_result"] = max(native["max_result"], blocks["max_result"])
    row["distinct_targets"] = len(targets)
    row["block_results"] = blocks["block_results"]
    row["tool_turns"] = blocks["tool_turns"]
    row["file_turns"] = blocks["file_turns"]
    # Two columns, two dialects, and one number each: ``native_calls`` counts the calls a
    # chat-form assistant turn announced and a ``role: "tool"`` message answered, while
    # ``envelope_calls`` counts the legacy text headers a user message carried.  They were
    # once one column, and it carried the first of these numbers under the second's name.
    row["native_calls"] = native["calls"] + native["others"]
    row["envelope_calls"] = native["envelope_calls"]
    row["envelope_messages"] = native["envelope_messages"]
    return row


def _document(path: Path) -> Any | None:
    """Return one file's parsed JSON, or ``None`` when it cannot be read.

    Args:
        path: A file inside a session directory.

    Returns:
        The parsed document.  A failure is reported as ``None`` and never described,
        because an exception's text can carry a path and a path is the one thing
        this script must not print.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def _messages_of(document: Any) -> list[Any] | None:
    """Return the message list a parsed document carries, or ``None``."""
    if isinstance(document, dict):
        document = document.get("messages")
    return document if isinstance(document, list) else None


def load_transcript(path: Path) -> list[Any] | None:
    """Return the message list one session file holds or points at, or ``None``.

    Args:
        path: A ``*.json`` file inside a session directory.  It is either the
            transcript itself or the metadata naming where the transcript lives.

    Returns:
        The messages, or ``None`` when the file cannot be read or carries no message
        list either directly or through a pointer.
    """
    document = _document(path)
    if isinstance(document, dict) and "messages_path" in document:
        try:
            document = _document(Path(str(document["messages_path"])))
        except (OSError, ValueError, TypeError):
            return None
    return _messages_of(document)


def session_transcript(session_dir: Path) -> list[Any] | None:
    """Return the one transcript a session directory stores, or ``None``.

    Args:
        session_dir: A directory holding one conversation's storage.

    Returns:
        The conversation's messages.  A directory can hold more than one file with
        a message list - a compaction or an export writes a copy of part of the same
        conversation beside the original - and counting both would weigh one
        conversation twice, so the file the directory's own metadata points at wins
        and the rest are ignored.
    """
    files = sorted(session_dir.glob("*.json"))
    for path in files:
        document = _document(path)
        if isinstance(document, dict) and "messages_path" in document:
            messages = load_transcript(path)
            if messages is not None:
                return messages
    for path in files:
        messages = _messages_of(_document(path))
        if messages is not None:
            return messages
    return None



def percentile_shapes(
    rows: list[dict[str, int]],
    percentiles: tuple[float, ...] = PERCENTILES,
) -> dict[str, dict[str, int]]:
    """Return one count-only shape row per named percentile.

    Args:
        rows: Per-session results of :func:`scan_transcript`.
        percentiles: The ranks to report, keyed ``"p50"`` and so on.

    Returns:
        ``{name: counts}``, where a session's rank is its place in the ordering by
        total result characters - the quantity C1's cost grows with.  A row is one
        session's transcript, not a percentile of every column: taking each
        statistic at its own rank would describe a conversation that does not exist.

        The place is the nearest rank, which is what the name of a percentile states:
        ``p99`` of 39 sessions is the 39th of them, the most expensive conversation the
        scan found, and reporting anything else would report a rank the name did not
        ask for.
    """
    ranked = sorted(rows, key=lambda row: row["result_chars"])
    total = len(ranked)
    shapes: dict[str, dict[str, int]] = {}
    if not total:
        return shapes
    for position in percentiles:
        rank = max(math.ceil(position * total - RANK_SLACK) - 1, 0)
        row = ranked[min(rank, total - 1)]
        shapes[f"p{round(position * 100)}"] = {key: int(row.get(key, 0)) for key in SHAPE_KEYS}
    return shapes


def render_python(shapes: dict[str, dict[str, int]]) -> str:
    """Return the shapes as a Python literal the benchmark can hold.

    Args:
        shapes: The result of :func:`percentile_shapes`.

    Returns:
        A paste-ready ``OBSERVED_SHAPES`` assignment.  It carries counts only, so it
        is safe to commit: no transcript text, path or name appears in it.
    """
    lines = ["OBSERVED_SHAPES: dict[str, dict[str, int]] = {"]
    for name in sorted(shapes):
        body = ", ".join(f"{key!r}: {value}" for key, value in sorted(shapes[name].items()))
        lines.append(f"    {name!r}: {{{body}}},")
    lines.append("}")
    return "\n".join(lines)


def scan_root(root: Path) -> tuple[list[dict[str, int]], dict[str, int]]:
    """Return the count-only rows and read totals for every session under ``root``.

    Args:
        root: A directory holding one subdirectory per conversation.

    Returns:
        A ``(rows, totals)`` pair with one row per session directory.  ``totals``
        counts what was found, read and refused; a session that cannot be read
        contributes no row, and its failure is a count and not a description.
    """
    rows: list[dict[str, int]] = []
    totals = {"found": 0, "read": 0, "unreadable": 0, "with_envelopes": 0}
    if not root.is_dir():
        return rows, totals
    for session_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        totals["found"] += 1
        messages = session_transcript(session_dir)
        if messages is None:
            totals["unreadable"] += 1
            continue
        totals["read"] += 1
        row = scan_transcript(messages)
        if row["native_calls"] or row["envelope_messages"]:
            totals["with_envelopes"] += 1
        rows.append(row)
    return rows, totals


def main(argv: list[str] | None = None) -> int:
    """Run the calibration and print counts, as JSON or as a Python literal.

    Args:
        argv: Command-line arguments.

    Returns:
        ``0`` when at least one session was read, ``3`` when none were, so a caller
        can tell "no transcripts here" from a measurement.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(default_root()),
                        help="the session-data directory to scan")
    parser.add_argument("--paste", action="store_true",
                        help="print the shapes as a Python literal instead of JSON")
    args = parser.parse_args(argv)
    rows, totals = scan_root(Path(args.root))
    shapes = percentile_shapes(rows)
    if not shapes:
        print(json.dumps({"status": "no_sessions_readable", **totals}))
        return 3
    if args.paste:
        print(render_python(shapes))
    else:
        print(json.dumps({"status": "ok", "totals": totals, "sessions": len(rows),
                          "shapes": shapes}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
