"""Explicit, privacy-safe client session correlation.

This is the gateway half of a design whose client half has not shipped yet.
Cline 3.0.74 already creates one opaque identifier per session - a value of the
shape ``<unix-ms>_<5 random base36>``, 19 characters - but for the
``openai-compatible`` provider it does not transmit it, so today's live records
cannot be grouped by actual client session.  When a future client change sends
that existing value in a dedicated header for a configured endpoint, this module
is what reads it.

The feature is opt-in and off by default (``APP_SESSION_CORRELATION_ENABLED``).
When it is off, nothing here runs: the header is not read and no ``session``
field reaches a record, so records stay byte-compatible with the ones written
before this existed.

What this module does:

* reads exactly one input - the raw value of :data:`SESSION_CORRELATION_HEADER` -
  and never consults a message, a transcript, an index, a pipeline stage or a
  provider request;
* accepts a string that is non-empty, at most :data:`MAX_SESSION_ID_LENGTH`
  characters long, and built only from ASCII letters, digits and ``.``, ``_``,
  ``:``, ``-``.  That charset excludes whitespace and control characters by
  construction, and Unicode is refused rather than folded.  An accepted value is
  recorded **as sent**: nothing is trimmed, truncated, normalised or otherwise
  repaired, because a repaired near-match is how two different sessions end up
  sharing one logged identifier.  Anything else - missing, empty, too long,
  padded, non-ASCII, or not a string at all - is unavailable, exactly like no
  header at all;
* returns a versioned object for the session log, or ``None`` when the feature
  is disabled.

What it must never be used for: authentication, authorization, routing, rate
limiting, model selection, retrieval, planning or caching.  The value is a log
field.  Correlation and control cannot share an input, because a
client-controlled string is the first thing an attacker can choose.  It is also
never forwarded upstream: the gateway's providers build their own request
headers, and nothing here enters a ``PipelineRequest``, its ``kwargs`` or its
``metadata``, so there is no path from this header to a backend call.

There is no state here of any kind - no cache, no lock, no map, no randomness,
no secret, no per-instance salt.  That absence is the determinism property: two
independently created gateway instances, and the same instance either side of a
restart, log the same ``session.id`` for the same client-supplied value.  It is
also why nothing is hashed - a keyed digest with a process-local salt would move
the logged identifier on every restart and every worker, which is the exact
instability this design exists to remove.
"""

from __future__ import annotations

import re
from typing import Any

#: The dedicated request header this gateway reads, and the only channel it
#: reads.  The name is fixed rather than configurable on purpose: a configurable
#: header turns one narrow contract into an arbitrary header-copying feature.
SESSION_CORRELATION_HEADER = "X-Cline-Session-ID"

#: The version token inside every object this module emits, so a reader knows
#: what a record promises without dating the log file.
SESSION_CORRELATION_SCHEMA = "session-correlation-v1"

#: The ``request.scope`` key the chat endpoint writes the resolved object to,
#: which is how it reaches the session-log middleware.
SESSION_CORRELATION_SCOPE_KEY = "session_correlation"

#: The client stated this session.
SOURCE_CLIENT = "client"

#: Nobody stated this session - no header, or a header that was refused.  There
#: is deliberately no third value: an inferred source would mean inferred ids.
SOURCE_ABSENT = "absent"

#: Longest identifier accepted.  Cline's own shape is 19 characters, so this is
#: headroom, not a truncation target: longer is refused, never cut down.
MAX_SESSION_ID_LENGTH = 64

# Only characters from the allowed set, and nothing else.  The class is written
# out as ASCII ranges precisely so ``re`` cannot accept a Unicode letter or digit
# as "alphanumeric"; ``fullmatch`` is what makes a leading or trailing space,
# tab or control byte unusable rather than invisible.
_SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9._:\-]+")


def is_valid_client_session_id(value: object) -> bool:
    """Return whether ``value`` is an acceptable client session identifier.

    Args:
        value: The raw header value.  Declared ``object`` because a header
            channel can hand over anything, and a non-string is unavailable
            rather than an error.

    Returns:
        ``True`` only for a non-empty, length-conforming, charset-conforming
        ASCII string.  ``False`` for everything else, including ``None``.
    """
    if not isinstance(value, str):
        return False
    if not 0 < len(value) <= MAX_SESSION_ID_LENGTH:
        return False
    return _SESSION_ID_PATTERN.fullmatch(value) is not None


def client_session(session_id: str) -> dict[str, str]:
    """Build the object that records a client-stated session.

    Args:
        session_id: A value that already passed
            :func:`is_valid_client_session_id`.

    Returns:
        ``{"schema": ..., "source": "client", "id": <value as sent>}`` and
        nothing else - no reason, no tracker, no derived field of any kind.
    """
    return {
        "schema": SESSION_CORRELATION_SCHEMA,
        "source": SOURCE_CLIENT,
        "id": session_id,
    }


def absent_session() -> dict[str, str]:
    """Build the object that states that nobody stated this session.

    Returns:
        ``{"schema": ..., "source": "absent"}`` with no ``id`` key at all, so an
        invalid value cannot be echoed back from the log that refused it.
    """
    return {"schema": SESSION_CORRELATION_SCHEMA, "source": SOURCE_ABSENT}


def resolve_client_session(
    *,
    enabled: bool,
    header_value: object,
) -> dict[str, str] | None:
    """Resolve a raw header value into the session-log object, or ``None``.

    Args:
        enabled: The value of ``session_correlation_enabled``.  ``False`` makes
            this return ``None`` without judging the value at all, which is what
            keeps a disabled gateway from inspecting a header it was asked not
            to read.
        header_value: The raw, untouched value of
            :data:`SESSION_CORRELATION_HEADER`, or ``None`` when it is absent.

    Returns:
        The client object, the absent object, or ``None`` when disabled.
    """
    if not enabled:
        return None
    if is_valid_client_session_id(header_value):
        # A ``str`` by that predicate's own contract; the cast is for mypy.
        return client_session(str(header_value))
    return absent_session()


def session_record_field(value: object) -> dict[str, str] | None:
    """Rebuild the record's ``session`` field from a scope channel value.

    The scope is a channel, not an authority.  What arrives here is serialized
    only if it is an object this module could itself have produced, and the
    ``id`` inside it has to validate a second time.  That keeps a stray or
    hand-built scope entry from putting an arbitrary string - including the
    refused raw value of a header - into a session log line.

    Args:
        value: The object read from ``scope[SESSION_CORRELATION_SCOPE_KEY]``.

    Returns:
        A freshly built client or absent object, or ``None`` when the channel
        holds nothing this schema can state.
    """
    if not isinstance(value, dict):
        return None

    candidate: dict[Any, Any] = value
    if candidate.get("schema") != SESSION_CORRELATION_SCHEMA:
        return None

    source = candidate.get("source")
    if source == SOURCE_ABSENT:
        return absent_session()
    if source == SOURCE_CLIENT:
        session_id = candidate.get("id")
        if not is_valid_client_session_id(session_id):
            return None
        return client_session(str(session_id))
    return None

