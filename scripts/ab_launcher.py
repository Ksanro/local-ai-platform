r"""Deterministic A/B launcher configuration for isolated-worktree arms.

An isolated-worktree A/B is the clean way to measure one configuration
difference: both gateways index the same commit of the same tree, so the only
thing that can move an answer is the setting under test. That holds only if
every *other* value the gateway and its provider use is one the launcher
declared. ``apps/gateway/main.py:52-54`` loads ``.env`` with ``override=True``,
and a worktree has no ``.env`` (it is gitignored), so a value that is not handed
to the process silently becomes a code default instead.

The 2026-10-13 changed-files run paid for exactly that: the harness was started
with ``--timeout 300`` while the arm's provider kept its unset default of 60
seconds (``packages/providers/vllm.py:71-78``,
``packages/providers/openai.py:74-80``) and aborted first with an HTTP 503 at
about 61 seconds, three times out of nine, while the harness still had minutes
of patience left to spend on an answer the gateway had already given up on
(docs/live-gateway-runbook.md, "Isolated-worktree changed-file A/B, 2026-10-13"
and "Interpreting long runs").

This module is configuration and validation only: it never starts a process,
never contacts a backend, never opens a connection, and never reads a ``.env``
file in order to copy it - it only reads the *names* a worktree's ``.env``
declares, to refuse a tree that could override what it is about to print.

The contract
-----------

``AbExperiment`` holds one shared block that both arms receive identically
(provider ``REQUEST_TIMEOUT``, the harness/client timeout, the model and provider
settings, and every ``APP_`` setting README.md:58-70 lists for a gateway, plus the
relationship-ranking switches that ``packages/context`` reads straight from the
process environment) plus two ``AbArm`` records holding the only differences an
A/B is allowed to have: its own port, its own absolute
``APP_SESSION_LOG_PATH``, and ``APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED``.
Anything else that differs between the arms is a bug, and is reported before
either gateway starts. Nothing in the shared block is left to the terminal that
starts an arm: a setting the launcher does not print is a code default, and a
setting the terminal carries by accident is one half of the pair measured on it.

The tree both arms run from is checked without asking Git anything, because
starting a process is outside this launcher's contract: it must be a directory
holding a ``.git`` file whose ``gitdir:`` line reaches a worktree administration
directory whose ``HEAD`` is a commit, and it must hold the gateway entrypoint, the
harness script and ``uv.exe`` that the rendered commands start with. An empty
folder, the main clone, a pruned worktree, or a tree checked out on a branch is
refused.

Secrets (``OPENAI_API_KEY``, ``VLLM_API_KEY``, anything ending in ``_API_KEY``,
``_TOKEN`` or ``_SECRET``) are never part of the configuration file and never
appear in a rendered command, a validation message, or ``--json`` output. An
arm inherits them from the terminal that runs its rendered block, so both arms
must be started from terminals holding the same values; ``show`` reports only
whether the launcher's own environment has each one set.

Usage
-----

.. code-block:: powershell

    .\uv.exe run python scripts\ab_launcher.py template --out build\ab-4330e8f\experiment.json
    .\uv.exe run python scripts\ab_launcher.py validate --config build\ab-4330e8f\experiment.json
    .\uv.exe run python scripts\ab_launcher.py show --config build\ab-4330e8f\experiment.json
    .\uv.exe run python scripts\ab_launcher.py show --config build\ab-4330e8f\experiment.json `
        --arm on
    .\uv.exe run python scripts\ab_launcher.py show --config build\ab-4330e8f\experiment.json --json

``show`` exits 2 with the reason on stderr when the experiment is invalid. Without
``--arm`` it prints one block per arm in launch order; with it, the two terminal
blocks for that arm alone - ``Set-Location`` into the validated worktree, the
session log created, the environment, then the blocking gateway command, and the
harness command for the second terminal below it, whose ``--timeout`` comes from
the validated configuration so it cannot drift away from the provider timeout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

# ---------------------------------------------------------------------------
# The launcher contract, as constants.
# ---------------------------------------------------------------------------

#: Uvicorn entrypoint both arms serve, from the arm's own source tree
#: (docs/live-gateway-runbook.md:40).
GATEWAY_APP = "apps.gateway.main:create_app"

#: Launcher used in the rendered commands, relative to a gateway tree.
UV_COMMAND = r".\uv.exe"

#: Harness the arms are measured with; rendered so both arms run the same one.
HARNESS_SCRIPT = str(Path("scripts") / "quality_harness.py")

#: The gateway module the rendered entrypoint resolves to, as a path inside a
#: tree (docs/live-gateway-runbook.md:40). Its presence is what makes a
#: directory a checkout of this project rather than a folder.
GATEWAY_ENTRYPOINT_PATH = str(Path("apps") / "gateway" / "main.py")

#: Launcher the rendered commands start with; tracked in Git, so a real worktree
#: checkout holds it.
UV_EXECUTABLE_NAME = "uv.exe"

#: Every path a tree must hold for an arm to start from it. An A/B measured in a
#: tree missing one of these is not this experiment: there would be no gateway to
#: run, no harness to measure it, or no launcher to start either with.
REQUIRED_WORKTREE_PATHS: tuple[str, ...] = (
    GATEWAY_ENTRYPOINT_PATH,
    HARNESS_SCRIPT,
    UV_EXECUTABLE_NAME,
)

#: Name a Git checkout keeps its administration data under: a directory in the
#: main clone, and a one-line file in a tree made by ``git worktree add``.
GIT_ADMIN_NAME = ".git"

#: Prefix of that file's single line, which names the administration directory of
#: the linked worktree inside the parent clone.
GITDIR_MARKER = "gitdir:"

#: Segment a linked worktree's administration path contains
#: (``<clone>/.git/worktrees/<name>``), which is what distinguishes a worktree
#: from a checkout of some other kind.
WORKTREE_ADMIN_SEGMENT = "worktrees"

#: What :func:`inspect_worktree` concluded from a tree's Git marker. A tree with
#: no marker is not Git's; a marker that is a directory is the main clone, which
#: is neither isolated nor ``.env``-free; a marker whose ``gitdir:`` target is
#: gone was removed or pruned.
WORKTREE_MARKER_NONE = "none"
WORKTREE_MARKER_LINKED = "linked"
WORKTREE_MARKER_CLONE = "clone"
WORKTREE_MARKER_STALE = "stale"

#: What an arm loses when one of ``REQUIRED_WORKTREE_PATHS`` is absent, so the
#: problem names the file and the reason it matters.
WORKTREE_PATH_REASONS: Mapping[str, str] = MappingProxyType(
    {
        GATEWAY_ENTRYPOINT_PATH: "uvicorn would have no application to start",
        HARNESS_SCRIPT: "the rendered harness command would have nothing to run",
        UV_EXECUTABLE_NAME: "neither rendered command could start with .\\uv.exe",
    }
)

#: A ``HEAD`` holding one of these is detached, which is what
#: ``git worktree add --detach`` leaves behind; a ``ref:`` line is a branch.
_COMMIT_ID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")

#: Timeout a provider uses when ``REQUEST_TIMEOUT`` is absent from the arm's
#: environment: ``packages/providers/vllm.py:77`` and
#: ``packages/providers/openai.py:80`` both fall back to 60.0 seconds.
PROVIDER_DEFAULT_TIMEOUT_SECONDS = 60.0

#: How much longer the harness must be willing to wait than the arm's provider
#: (docs/roadmap.md, item A2). The client must never give up first, or a timed
#: out probe reads as a retrieval failure; the margin also covers the gateway's
#: own overhead around the backend call.
HARNESS_TIMEOUT_MARGIN_SECONDS = 30.0

#: Timeout ``scripts/quality_harness.py:73`` uses when no ``--timeout`` is given.
#: Used only as a fallback when the harness cannot be imported to read its own
#: default.
HARNESS_DEFAULT_TIMEOUT_SECONDS = 120.0

#: Environment keys whose *values* are secrets. Never declared in an experiment
#: file, never printed.
SECRET_ENV_KEYS: tuple[str, ...] = ("OPENAI_API_KEY", "VLLM_API_KEY")

#: Key-name suffixes treated as secret, so a new credential key cannot be added
#: to a config file and echoed by ``show``.
SECRET_ENV_SUFFIXES: tuple[str, ...] = ("_API_KEY", "_ACCESS_TOKEN", "_TOKEN", "_SECRET")

#: Shared settings both arms must receive with identical values. This is the
#: environment block README.md:58-70 documents for a gateway, plus the
#: relationship-ranking switches that ``packages/context`` reads straight from the
#: process environment, minus the provider timeout (its own field) and the keys
#: that are intentionally per-arm. Every entry here exists because the one thing
#: an arm does not get from a worktree is a ``.env``: a setting that is absent is
#: a code default the experiment never declared, and a setting the terminal
#: happens to carry is a difference between the arms nobody wrote down.
REQUIRED_SHARED_ENV_KEYS: tuple[str, ...] = (
    "DEFAULT_MODEL",
    "APP_LOG_LEVEL",
    "APP_DEFAULT_MODEL",
    "APP_DEFAULT_PROVIDER",
    "APP_MODELS_CONFIG",
    "APP_REPOSITORY_PATH",
    "APP_REPOSITORY_CONTEXT_ENABLED",
    "APP_REPOSITORY_CONTEXT_MAX_TOKENS",
    "APP_REPOSITORY_CONTEXT_INTENT_BUDGETS",
    "APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS",
    "APP_REPOSITORY_EXCLUDE_TESTS",
    "APP_REPOSITORY_EXCLUDE_GLOBS",
    "APP_CONTEXT_DELTA_INJECTION",
    "APP_CONTEXT_DELTA_CACHE_SIZE",
    "APP_CONTEXT_INTENT_RULES",
    "RELATIONSHIP_RANKING_ENABLED",
    "RELATIONSHIP_EXPANSION_ENABLED",
    "APP_SESSION_LOG_ENABLED",
    "APP_HISTORY_CAP_ENABLED",
    "APP_HISTORY_CAP_TOKENS",
)

#: The five settings that used to be inherited from whichever terminal started an
#: arm, each with the value the source falls back to when it is unset. They are in
#: ``REQUIRED_SHARED_ENV_KEYS`` for real, and this names what the value is worth:
#:
#: * ``APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS`` (``0``,
#:   ``apps/gateway/core/config.py:102``) - with ``0`` the changed-files snapshot is
#:   taken once at startup; any other number lets a background task move it mid-run
#:   (docs/live-gateway-runbook.md:416), which makes the dirty set a function of
#:   when a probe happened to run.
#: * ``APP_CONTEXT_INTENT_RULES`` (``{}``, ``apps/gateway/core/config.py:103``,
#:   README.md:66) - custom phrases redirect a request to another intent, so a
#:   leftover rule in a terminal changes the retrieval profile of one arm.
#: * ``APP_CONTEXT_DELTA_CACHE_SIZE`` (``256``, ``apps/gateway/core/config.py:106``)
#:   - the number of conversation keys ``SentSymbolTracker`` holds
#:   (``packages/pipeline/stages/repository_context.py:392``); a smaller one evicts
#:   mid-run and re-sends symbols the arm had already sent.
#: * ``RELATIONSHIP_RANKING_ENABLED`` and ``RELATIONSHIP_EXPANSION_ENABLED``
#:   (``true``, ``packages/context/builder.py:205,209`` and
#:   ``packages/context/ranking.py:193,197``) - they reorder and widen the
#:   candidates, and are read outside the ``APP_`` settings, so nothing but the
#:   arm's environment can say what they were.
TEMPLATE_MEASUREMENT_ENV: Mapping[str, str] = MappingProxyType(
    {
        "APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS": "0",
        "APP_CONTEXT_INTENT_RULES": "{}",
        "APP_CONTEXT_DELTA_CACHE_SIZE": "256",
        "RELATIONSHIP_RANKING_ENABLED": "true",
        "RELATIONSHIP_EXPANSION_ENABLED": "true",
    }
)

#: The only keys allowed to hold different values in the two arms.
ALLOWED_ARM_ENV_KEYS: tuple[str, ...] = (
    "APP_SESSION_LOG_PATH",
    "APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED",
)

#: Keys whose value must be an absolute path - a relative path would be read
#: against whichever directory the arm happens to run from.
ABSOLUTE_PATH_ENV_KEYS: tuple[str, ...] = ("APP_REPOSITORY_PATH",)

#: Keys whose value must be the literal ``true``/``false`` a gateway boolean
#: setting parses, rather than PowerShell's ``True``/``1``.
BOOL_ENV_KEYS: tuple[str, ...] = (
    "APP_REPOSITORY_CONTEXT_ENABLED",
    "APP_REPOSITORY_EXCLUDE_TESTS",
    "APP_CONTEXT_DELTA_INJECTION",
    "APP_SESSION_LOG_ENABLED",
    "APP_HISTORY_CAP_ENABLED",
    "APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED",
)

#: Keys read straight from the process environment by a comparison with the text
#: ``false`` (``packages/context/builder.py:205,209`` and
#: ``packages/context/ranking.py:193,197``) instead of by a boolean parser. Only
#: the exact lowercase word disables one, so ``True``, ``1`` and ``no`` all leave a
#: ranking switch on; the launcher writes the two spellings that cannot be
#: misread, and refuses anything else.
LITERAL_BOOL_ENV_KEYS: tuple[str, ...] = (
    "RELATIONSHIP_RANKING_ENABLED",
    "RELATIONSHIP_EXPANSION_ENABLED",
)

#: Exact values ``LITERAL_BOOL_ENV_KEYS`` accept: the first spelling of
#: ``BOOL_TRUE_VALUES`` and ``BOOL_FALSE_VALUES`` below, lowercase and unpadded,
#: since those are the two a ``!= "false"`` comparison reads the way a boolean
#: parser would.
LITERAL_BOOL_VALUES: tuple[str, ...] = ("true", "false")

#: Keys whose value must parse as a JSON object. ``apps/gateway/core/config.py``
#: reads these as a plain string and drops anything it cannot parse, in silence.
JSON_OBJECT_ENV_KEYS: tuple[str, ...] = ("APP_CONTEXT_INTENT_RULES",)

#: Keys every ``APP_MODELS_CONFIG`` entry must carry. ``model``, ``provider``
#: and ``base_url`` are required by the registry
#: (``packages/providers/registry_models.py:82-86``); ``backend_model`` is
#: required here because the served name is deliberately different from the
#: client alias, and an entry without it sends the alias upstream.
MODEL_CONFIG_REQUIRED_ENTRY_KEYS: tuple[str, ...] = (
    "model",
    "provider",
    "base_url",
    "backend_model",
)

#: Shared settings that must also hold a non-empty value. An experiment may
#: declare ``APP_REPOSITORY_CONTEXT_INTENT_BUDGETS`` empty on purpose, meaning
#: the budgets the code already ships with.
ALLOW_EMPTY_ENV_KEYS: tuple[str, ...] = ("APP_REPOSITORY_CONTEXT_INTENT_BUDGETS",)

#: Keys whose value must parse as an integer greater than zero.
#: ``APP_CONTEXT_DELTA_CACHE_SIZE`` is the number of conversation keys the
#: already-sent tracker keeps (``apps/gateway/core/config.py:106``, applied at
#: ``packages/pipeline/stages/repository_context.py:392``); zero would remember
#: nothing and re-send the whole context on every turn.
POSITIVE_INT_ENV_KEYS: tuple[str, ...] = (
    "APP_REPOSITORY_CONTEXT_MAX_TOKENS",
    "APP_CONTEXT_DELTA_CACHE_SIZE",
)

#: Keys whose value must parse as an integer that is not negative; ``0`` means
#: the setting derives its own value (``apps/gateway/core/config.py:110``) or
#: acts once (``apps/gateway/core/config.py:102``, the changed-files snapshot
#: taken at startup).
NON_NEGATIVE_INT_ENV_KEYS: tuple[str, ...] = (
    "APP_HISTORY_CAP_TOKENS",
    "APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS",
)

#: Arm-specific environment keys that ``AbArm`` already owns, so they must not
#: also appear in ``AbArm.env``.
ARM_FIELD_FOR_ENV_KEY: Mapping[str, str] = MappingProxyType(
    {
        "APP_SESSION_LOG_PATH": "session_log_path",
        "APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED": "changed_files_enabled",
    }
)

#: Spellings of a boolean that pydantic-settings accepts for the ``bool`` fields
#: in ``apps/gateway/core/config.py:95-110``; checked case-insensitively, and
#: verified against the installed pydantic (``yes``, ``on`` and ``1`` all parse
#: as true). The first of each tuple is the spelling the launcher writes.
BOOL_TRUE_VALUES: tuple[str, ...] = ("true", "t", "yes", "y", "on", "1")
BOOL_FALSE_VALUES: tuple[str, ...] = ("false", "f", "no", "n", "off", "0")

#: Loopback host both arms bind, matching the harness's own default base URL
#: (``scripts/quality_harness.py:67``).
GATEWAY_HOST = "127.0.0.1"

#: Marker for "this arm does not set this key at all" in a comparison.
_MISSING = "\x00missing"

#: Shown everywhere a credential value would otherwise appear in a report, a
#: rendered command, or a printed document.
SECRET_PLACEHOLDER = "<not shown>"


def _format_seconds(value: float) -> str:
    """Render a timeout the way ``REQUEST_TIMEOUT`` and ``--timeout`` take it.

    Whole seconds stay whole (``300`` not ``300.0``) so a rendered command is
    comparable with the numbers written in the runbook.

    Args:
        value: Seconds.

    Returns:
        The shortest decimal string that round-trips as a float.
    """
    return f"{float(value):g}"


def _format_bool(value: bool) -> str:
    """Render a boolean in the one spelling a gateway setting accepts."""
    return BOOL_TRUE_VALUES[0] if value else BOOL_FALSE_VALUES[0]


class AbLaunchError(Exception):
    """An A/B experiment that must not be started.

    Attributes:
        problems: Secret-free reasons, one per entry, in the order they were
            found. Never contains a value for a key ``is_secret_key`` accepts.
    """

    def __init__(self, problems: Sequence[str] | str) -> None:
        """Initialize with one problem or the full list of them."""
        if isinstance(problems, str):
            problems = [problems]
        self.problems: tuple[str, ...] = tuple(problems)
        super().__init__("; ".join(self.problems))


# ---------------------------------------------------------------------------
# Experiment shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AbArm:
    """One side of an A/B experiment: the intentional differences only.

    Attributes:
        arm_id: Short name used in rendered commands and reports ("off"/"on").
        port: Port this arm's uvicorn listens on; it must differ between arms.
        session_log_path: Absolute JSONL this arm writes its own sessions to,
            given to the gateway as ``APP_SESSION_LOG_PATH`` and to the harness
            as ``--session-log-path``.
        changed_files_enabled: This arm's
            ``APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED``, the setting a
            changed-files A/B is about.
        env: Extra per-arm settings. Each key is checked against the shared
            block, so an accidental difference is reported instead of launched.
    """

    arm_id: str
    port: int
    session_log_path: str
    changed_files_enabled: bool
    env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze the extra mapping so the arms cannot drift after validation."""
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))


@dataclass(frozen=True)
class AbExperiment:
    """One A/B experiment: a shared block and exactly two arms.

    Attributes:
        name: Experiment identifier, used in rendered comments only.
        worktree: Isolated gateway tree both arms run from. It must exist and
            must hold no ``.env``, or ``apps/gateway/main.py:52-54`` would
            override whatever this configuration declares.
        shared_env: Settings both arms receive identically, except the provider
            timeout, which is ``provider_request_timeout_seconds``.
        arms: The two ``AbArm`` records, in launch order.
        provider_request_timeout_seconds: Provider timeout the arms get as
            ``REQUEST_TIMEOUT``. ``None`` means the experiment never said, and
            that is the failure this launcher exists to prevent.
        harness_timeout_seconds: The ``--timeout`` the harness must be run with
            against either arm.
        harness_probes: Probe ids to run, empty meaning the harness's whole
            fixed set. Rendered as ``--probe``, repeated.
        harness_repeat: Times each probe set is repeated against an arm,
            rendered as ``--repeat`` so a run cannot quietly become a single
            sample (docs/live-gateway-runbook.md repeats every arm three times).
        harness_max_tokens: The ``--max-tokens`` both arms are measured with.
            ``None`` leaves it to the harness default
            (``scripts/quality_harness.py:71``), which ``show`` prints so the
            number is never invisible.
    """

    name: str
    worktree: str
    shared_env: Mapping[str, str]
    arms: tuple[AbArm, ...]
    provider_request_timeout_seconds: float | None = None
    harness_timeout_seconds: float | None = None
    harness_probes: tuple[str, ...] = ()
    harness_repeat: int = 1
    harness_max_tokens: int | None = None

    def __post_init__(self) -> None:
        """Freeze the mappings and normalise the arm tuple."""
        object.__setattr__(self, "shared_env", MappingProxyType(dict(self.shared_env)))
        object.__setattr__(self, "arms", tuple(self.arms))
        object.__setattr__(self, "harness_probes", tuple(self.harness_probes))

    @property
    def arm_ids(self) -> tuple[str, ...]:
        """Return the arm names in launch order."""
        return tuple(arm.arm_id for arm in self.arms)


@dataclass(frozen=True)
class WorktreeState:
    """What the launcher can see of an isolated gateway tree.

    Attributes:
        path: The configured tree.
        exists: Whether it is a directory right now.
        dotenv_path: The tree's ``.env``, if it has one.
        dotenv_keys: Names that ``.env`` declares. Never its values.
        marker: What the tree's ``.git`` entry says it is, one of the
            ``WORKTREE_MARKER_`` constants. It is ``WORKTREE_MARKER_NONE`` both
            when there is no marker and when the marker points somewhere that is
            not a worktree, in which case ``git_dir`` says where it pointed.
        git_dir: The administration directory a linked worktree's ``gitdir:``
            line names, when the tree has one.
        detached: ``True`` when that directory's ``HEAD`` holds a commit rather
            than a branch reference, ``False`` for a branch worktree, and
            ``None`` when it could not be read.
        missing_paths: The entries of ``REQUIRED_WORKTREE_PATHS`` the tree does
            not hold, in that constant's order.
    """

    path: str
    exists: bool
    dotenv_path: str | None = None
    dotenv_keys: tuple[str, ...] = ()
    marker: str = WORKTREE_MARKER_NONE
    git_dir: str | None = None
    detached: bool | None = None
    missing_paths: tuple[str, ...] = ()

    @property
    def has_dotenv(self) -> bool:
        """Whether the tree holds a ``.env`` that could override the launcher."""
        return self.dotenv_path is not None

    @property
    def is_isolated_worktree(self) -> bool:
        """Whether the marker says detached linked worktree, and nothing else."""
        return self.marker == WORKTREE_MARKER_LINKED and self.detached is True

    @property
    def can_run_an_arm(self) -> bool:
        """Whether a gateway could actually be started from this tree."""
        return self.is_isolated_worktree and not self.missing_paths


# ---------------------------------------------------------------------------
# Secret handling and the worktree probe
# ---------------------------------------------------------------------------


def is_secret_key(key: str) -> bool:
    """Whether an environment key holds a value that must never be printed.

    Args:
        key: Environment variable name.

    Returns:
        ``True`` for a registered credential key or a credential-looking name.
    """
    upper = key.upper()
    if upper in SECRET_ENV_KEYS:
        return True
    return any(upper.endswith(suffix) for suffix in SECRET_ENV_SUFFIXES)


def secret_env_status(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Report which secret keys the launcher's own environment carries.

    Args:
        environ: Environment to test; defaults to ``os.environ``. Tests pass a
            mapping of their own.

    Returns:
        Secret key name to ``True`` when set. Only presence is derived; values
        never enter the result.
    """
    env = os.environ if environ is None else environ
    return {key: bool(env.get(key)) for key in SECRET_ENV_KEYS}


def dotenv_key_names(path: Path) -> tuple[str, ...]:
    """Return the setting names a ``.env`` declares, without its values.

    Args:
        path: The ``.env`` file to inspect.

    Returns:
        Sorted unique key names. An unreadable file yields an empty tuple, so
        it is still reported as present.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    names: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name = stripped.split("=", 1)[0].strip()
        if name.lower().startswith("export "):
            name = name[len("export ") :].strip()
        if name:
            names.add(name)
    return tuple(sorted(names))


def inspect_worktree(path: str | Path) -> WorktreeState:
    """Report what an isolated gateway tree looks like to the launcher.

    Every check here is a directory entry or a small text file. The launcher never
    asks Git what a tree is, because that would mean starting a process, and
    because a tree that cannot prove its own shape is not one to measure an A/B
    on: ``git worktree add --detach <path> <commit>`` leaves a ``.git`` file whose
    ``gitdir:`` line reaches an administration directory under ``worktrees``, and
    holds the tracked checkout that both commands rendered for it.

    Args:
        path: The worktree both arms would run from.

    Returns:
        A ``WorktreeState`` describing the tree, its ``.env``, what its Git marker
        says it is, and which required files it lacks.
    """
    root = Path(path)
    if not root.is_dir():
        return WorktreeState(str(root), False)
    dotenv = root / ".env"
    dotenv_path: str | None = str(dotenv) if dotenv.is_file() else None
    dotenv_keys = dotenv_key_names(dotenv) if dotenv_path else ()
    marker, git_dir = _git_marker(root)
    detached: bool | None = None
    if marker == WORKTREE_MARKER_LINKED and git_dir is not None:
        detached = _head_is_detached(git_dir)
    return WorktreeState(
        str(root),
        True,
        dotenv_path,
        dotenv_keys,
        marker,
        git_dir,
        detached,
        _missing_worktree_paths(root),
    )


def _git_marker(root: Path) -> tuple[str, str | None]:
    """Classify a directory by its ``.git`` entry, without asking Git anything.

    Args:
        root: The tree both arms would run from.

    Returns:
        The ``WORKTREE_MARKER_`` verdict and the administration directory a
        ``.git`` file names, when the tree has one to read.
    """
    marker = root / GIT_ADMIN_NAME
    if marker.is_dir():
        return WORKTREE_MARKER_CLONE, None
    if not marker.is_file():
        return WORKTREE_MARKER_NONE, None
    git_dir = _gitdir_target(marker)
    if git_dir is None:
        return WORKTREE_MARKER_NONE, None
    admin = Path(git_dir)
    if not admin.is_dir():
        return WORKTREE_MARKER_STALE, git_dir
    if WORKTREE_ADMIN_SEGMENT not in {part.lower() for part in admin.parts}:
        return WORKTREE_MARKER_NONE, git_dir
    return WORKTREE_MARKER_LINKED, git_dir


def _gitdir_target(marker: Path) -> str | None:
    """Resolve the ``gitdir:`` line of a worktree's ``.git`` file.

    Args:
        marker: The ``.git`` file to read.

    Returns:
        The directory the line names, joined to the tree when it is relative, or
        ``None`` when the file cannot be read or holds no ``gitdir:`` line. The
        path is joined lexically: a pruned worktree's target must be reported as
        missing rather than resolved into something else.
    """
    try:
        text = marker.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.lower().startswith(GITDIR_MARKER):
            return None
        target = stripped[len(GITDIR_MARKER) :].strip().strip("\"'")
        if not target:
            return None
        # Git writes the target with forward slashes even on Windows, and Path
        # reads either spelling once the separators are normalised.
        path = Path(target.replace("\\", "/"))
        if not path.is_absolute():
            path = marker.parent / path
        return str(path)
    return None


def _head_is_detached(git_dir: str) -> bool | None:
    """Report whether a linked worktree's ``HEAD`` names a commit, not a branch.

    Args:
        git_dir: The worktree's administration directory.

    Returns:
        ``True`` for a commit id, which is what ``git worktree add --detach``
        leaves, ``False`` for a ``ref:`` line, and ``None`` when ``HEAD`` cannot be
        read or holds neither.
    """
    try:
        text = (Path(git_dir) / "HEAD").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    line = text.strip()
    if line.lower().startswith("ref:"):
        return False
    if _COMMIT_ID_RE.fullmatch(line.lower()):
        return True
    return None


def _missing_worktree_paths(root: Path) -> tuple[str, ...]:
    """Return the required tree contents that are not readable files.

    Args:
        root: The tree both arms would run from.

    Returns:
        The names from ``REQUIRED_WORKTREE_PATHS`` absent from the tree, in that
        constant's order.
    """
    return tuple(name for name in REQUIRED_WORKTREE_PATHS if not (root / name).is_file())


# ---------------------------------------------------------------------------
# What each arm would actually receive
# ---------------------------------------------------------------------------


def arm_environment(experiment: AbExperiment, arm: AbArm) -> dict[str, str]:
    """Return the complete, explicit environment one arm must run with.

    The provider timeout and the two intentional arm differences are added from
    the typed fields, so a rendered command can never carry a
    ``REQUEST_TIMEOUT`` that disagrees with the timeout the experiment was
    validated against. Secret keys are dropped here as a last line of defence:
    an arm inherits them from the terminal that runs the rendered block.

    Args:
        experiment: The experiment being launched.
        arm: One of ``experiment.arms``.

    Returns:
        The arm's environment as a plain dict, secrets excluded.
    """
    env = dict(experiment.shared_env)
    env.update(arm.env)
    if experiment.provider_request_timeout_seconds is not None:
        env["REQUEST_TIMEOUT"] = _format_seconds(experiment.provider_request_timeout_seconds)
    env["APP_SESSION_LOG_PATH"] = arm.session_log_path
    env["APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED"] = _format_bool(arm.changed_files_enabled)
    return {key: value for key, value in env.items() if not is_secret_key(key)}


def arm_env_diff(experiment: AbExperiment) -> dict[str, tuple[str, ...]]:
    """Return each key whose value is not identical across the arms.

    Args:
        experiment: The experiment to compare.

    Returns:
        Key to that key's value per arm, in ``experiment.arm_ids`` order, for
        keys where the values disagree. ``_MISSING`` marks an arm that does not
        set the key at all.
    """
    envs = [arm_environment(experiment, arm) for arm in experiment.arms]
    diff: dict[str, tuple[str, ...]] = {}
    for key in sorted({key for env in envs for key in env}):
        values = tuple(env.get(key, _MISSING) for env in envs)
        if len(set(values)) > 1:
            diff[key] = values
    return diff


# ---------------------------------------------------------------------------
# Validation - all of it happens before either gateway is started
# ---------------------------------------------------------------------------


def _config_problems(experiment: AbExperiment) -> list[str]:
    """Return every problem with an experiment that needs no tree to exist.

    Split out of :func:`validate_experiment` so ``template`` can refuse to write a
    file whose fields are already wrong, while still writing one whose worktree has
    not been made yet - which is the normal state of a starting point.

    Args:
        experiment: The configuration to check.

    Returns:
        Secret-free problems in the order they were found, empty when the
        configuration itself is sound.
    """
    problems: list[str] = list(_shape_problems(experiment))
    problems.extend(_shared_setting_problems(experiment))
    problems.extend(_timeout_problems(experiment))
    problems.extend(_arm_problems(experiment))
    problems.extend(_symmetry_problems(experiment))
    problems.extend(_model_selection_problems(experiment))
    problems.extend(_harness_problems(experiment))
    return problems


def validate_experiment(
    experiment: AbExperiment,
    worktree: WorktreeState | None = None,
) -> tuple[str, ...]:
    """Return every reason this experiment must not be started.

    Args:
        experiment: The configuration to check.
        worktree: Pre-computed view of the isolated tree. When ``None``, the
            tree named by the experiment is inspected.

    Returns:
        Secret-free problems in the order they were found, empty when the
        experiment is sound.
    """
    problems = _config_problems(experiment)
    state = inspect_worktree(experiment.worktree) if worktree is None else worktree
    problems.extend(_worktree_problems(experiment, state))
    return tuple(problems)


def require_valid_experiment(
    experiment: AbExperiment,
    worktree: WorktreeState | None = None,
) -> WorktreeState:
    """Return the checked worktree, or raise ``AbLaunchError``.

    Args:
        experiment: The configuration to launch.
        worktree: Pre-computed view of the isolated tree.

    Returns:
        The ``WorktreeState`` the verdict was made against.

    Raises:
        AbLaunchError: If anything about the experiment must be fixed first,
            which is always before either gateway is started.
    """
    state = inspect_worktree(experiment.worktree) if worktree is None else worktree
    problems = validate_experiment(experiment, state)
    if problems:
        raise AbLaunchError(problems)
    return state


def _shape_problems(experiment: AbExperiment) -> list[str]:
    """Check the fields that decide whether this is an A/B at all."""
    problems: list[str] = []
    if not experiment.name.strip():
        problems.append("the experiment needs a name; it labels both arms in every report")
    if not experiment.worktree.strip():
        problems.append(
            "the experiment needs a worktree; both arms must run from the same isolated tree"
        )
    if len(experiment.arms) != 2:
        problems.append(
            f"an A/B experiment needs exactly two arms, found {len(experiment.arms)}"
            f" ({', '.join(experiment.arm_ids) or 'none'})"
        )
    return problems


def _shared_setting_problems(experiment: AbExperiment) -> list[str]:
    """Check the block both arms must receive identically."""
    problems: list[str] = []
    for key in REQUIRED_SHARED_ENV_KEYS:
        value = experiment.shared_env.get(key)
        if value is None:
            problems.append(
                f"missing required shared setting {key}; both arms must get it from the"
                " experiment file, because a worktree has no .env to inherit it from"
            )
        elif not value.strip() and key not in ALLOW_EMPTY_ENV_KEYS:
            problems.append(f"required shared setting {key} is empty")
    if "REQUEST_TIMEOUT" in experiment.shared_env:
        problems.append(
            "REQUEST_TIMEOUT is declared in shared_env and as a field; declare it once,"
            " as provider_request_timeout_seconds"
        )
    for key in sorted(experiment.shared_env):
        if is_secret_key(key):
            continue
        problems.extend(_value_problems(key, experiment.shared_env[key]))
    for key in sorted(set(experiment.shared_env) & _secret_keys_in(experiment.shared_env)):
        problems.append(
            f"{key} is a credential; the launcher never stores or prints one, and the arms"
            " inherit it from the terminal that starts them"
        )
    return problems


def _secret_keys_in(mapping: Mapping[str, str]) -> frozenset[str]:
    """Return the keys of ``mapping`` whose values must not be written down."""
    return frozenset(key for key in mapping if is_secret_key(key))


def provider_default_timeout() -> float:
    """Return the provider timeout a gateway uses when ``REQUEST_TIMEOUT`` is unset.

    Both provider layers inline the same fallback (``packages.providers.vllm``
    in ``_resolve_config_value`` and ``packages.providers.openai`` in
    ``build_openai_config``), so the constant here is the authority; the tests
    assert it matches what the providers fall back to.

    Returns:
        The seconds the provider layer would cut a request off at.
    """
    return PROVIDER_DEFAULT_TIMEOUT_SECONDS


def harness_timeout_default() -> float:
    """Return the timeout ``quality_harness.py`` uses without ``--timeout``.

    Returns:
        The seconds the harness would wait for one request.
    """
    try:
        import scripts.quality_harness as quality_harness
    except ImportError:
        return HARNESS_DEFAULT_TIMEOUT_SECONDS
    return float(quality_harness.DEFAULT_TIMEOUT)


def _timeout_problems(experiment: AbExperiment) -> list[str]:
    """Check that both timeout layers are declared and ordered correctly."""
    problems: list[str] = []
    provider = experiment.provider_request_timeout_seconds
    harness = experiment.harness_timeout_seconds
    if provider is None:
        problems.append(
            "provider_request_timeout_seconds is not declared, so REQUEST_TIMEOUT falls back to"
            f" {_format_seconds(provider_default_timeout())} s"
            " (packages/providers/vllm.py:77, packages/providers/openai.py:77)"
            " while the harness waits"
            " longer - that mismatch is what makes a slow model look like it timed out"
        )
    elif provider <= 0:
        problems.append(
            "provider_request_timeout_seconds must be a positive number of seconds, got"
            f" {provider:g}"
        )
    if harness is None:
        problems.append(
            "harness_timeout_seconds is not declared; the rendered harness command would use the"
            f" harness default of {_format_seconds(harness_timeout_default())} s"
        )
    elif harness <= 0:
        problems.append(
            f"harness_timeout_seconds must be a positive number of seconds, got {harness:g}"
        )
    elif provider is not None and provider > 0:
        needed = provider + HARNESS_TIMEOUT_MARGIN_SECONDS
        if harness < needed:
            problems.append(
                f"harness_timeout_seconds {harness:g} s must exceed"
                f" provider_request_timeout_seconds {provider:g} s by at least"
                f" {HARNESS_TIMEOUT_MARGIN_SECONDS:g} s, so an arm can finish its own provider"
                f" timeout and flush its session log before the harness gives up; set"
                f" harness_timeout_seconds to {needed:g} or raise the provider timeout"
            )
    return problems


def _arm_problems(experiment: AbExperiment) -> list[str]:
    """Check that the two arms are addressable and genuinely paired."""
    problems: list[str] = []
    ids: dict[str, str] = {}
    ports: dict[int, str] = {}
    logs: dict[str, str] = {}
    for position, arm in enumerate(experiment.arms, start=1):
        label = arm.arm_id.strip() or f"arm {position}"
        if not arm.arm_id.strip():
            problems.append(f"arm {position} needs an arm_id; it labels the rendered command")
        elif arm.arm_id in ids:
            problems.append(f"arm_id {arm.arm_id} is used twice; the two arms must be named apart")
        else:
            ids[arm.arm_id] = label
        problems.extend(_port_problems(label, arm.port, ports))
        problems.extend(_session_log_problems(label, arm.session_log_path, logs))
        problems.extend(_arm_env_problems(label, arm))
    if len(experiment.arms) == 2:
        flags = {arm.changed_files_enabled for arm in experiment.arms}
        if len(flags) == 1:
            problems.append(
                "both arms set APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED="
                f"{_format_bool(next(iter(flags)))}; an A/B has to change the setting under test,"
                " or there is nothing to compare"
            )
    return problems


def _port_problems(label: str, port: int, seen: dict[int, str]) -> list[str]:
    """Check one arm's port, and that no two arms claim the same one."""
    if isinstance(port, bool) or not isinstance(port, int):
        return [f"{label} port must be an integer, got {port!r}"]
    if not 1 <= port <= 65535:
        return [f"{label} port {port} is not a usable TCP port"]
    owner = seen.get(port)
    if owner is not None:
        return [
            f"arms {owner} and {label} both use port {port}; only one gateway can bind it, so one"
            " arm would answer on the other arm's settings"
        ]
    seen[port] = label
    return []


def _session_log_problems(label: str, path: str, seen: dict[str, str]) -> list[str]:
    """Check one arm's session log path, and that no two arms share one."""
    if not path.strip():
        return [
            f"{label} needs its own session_log_path; the harness reads the arm's run by that path"
        ]
    if not _is_absolute(path):
        return [
            f"{label} session_log_path must be absolute;"
            " a relative one lands in whichever directory the arm was started from"
        ]
    normalised = str(Path(path))
    owner = seen.get(normalised)
    if owner is not None:
        return [
            f"arms {owner} and {label} share the session log {path}; the harness would read the two"
            " runs as one"
        ]
    seen[normalised] = label
    return []


def _arm_env_problems(label: str, arm: AbArm) -> list[str]:
    """Check the narrow space one arm may differ in."""
    problems: list[str] = []
    for key in sorted(arm.env):
        if is_secret_key(key):
            problems.append(
                f"{label} declares the credential {key} in its arm env; the arms inherit"
                " credentials from the terminal that starts them, so one cannot be written"
                " into an experiment file"
            )
        elif key == "REQUEST_TIMEOUT":
            problems.append(
                f"{label} declares REQUEST_TIMEOUT in its arm env; the provider timeout is declared"
                " once for both arms, because a difference there is not the thing under test"
            )
        elif key in ARM_FIELD_FOR_ENV_KEY:
            problems.append(
                f"{label} sets {key} in its arm env; give it as the arm's"
                f" {ARM_FIELD_FOR_ENV_KEY[key]} instead"
            )
        elif key in REQUIRED_SHARED_ENV_KEYS:
            problems.append(
                f"{label} overrides the shared setting {key} per arm;"
                f" {key} must be identical in both arms, so declare it in shared_env"
            )
        else:
            problems.extend(_value_problems(key, arm.env[key]))
    return problems


def _symmetry_problems(experiment: AbExperiment) -> list[str]:
    """Reject every arm difference outside the allowlist."""
    problems: list[str] = []
    for key, values in sorted(arm_env_diff(experiment).items()):
        if key in ALLOWED_ARM_ENV_KEYS:
            continue
        shown = " / ".join(_describe_env_value(key, value) for value in values)
        problems.append(
            f"unexpected arm difference: {key} is {shown} across arms"
            f" {' and '.join(experiment.arm_ids)};"
            f" only {', '.join(ALLOWED_ARM_ENV_KEYS)} may differ"
        )
    return problems


def _describe_env_value(key: str, value: str) -> str:
    """Describe one side of an arm difference without ever revealing a secret."""
    if value == _MISSING:
        return "unset in one arm"
    if is_secret_key(key):
        return SECRET_PLACEHOLDER
    return value


def _same_directory(first: str, second: str) -> bool:
    """Return whether two path spellings name one directory.

    Both sides are resolved before they are compared, the way ``packages/
    repository/changed_files.py:188-192`` compares a Git working tree with
    ``APP_REPOSITORY_PATH``: on Windows the same directory is reachable through a
    symlink, a junction, a ``subst`` drive or an 8.3 short name, and comparing
    those spellings as text is wrong in silence.

    Args:
        first: The first path spelling, possibly with environment references.
        second: The second path spelling, possibly with environment references.

    Returns:
        ``True`` when the two name the same directory.
    """
    return _resolve_directory(first) == _resolve_directory(second)


def _resolve_directory(value: str) -> str:
    """Return one comparable spelling of the directory ``value`` names.

    Args:
        value: A path as written in a configuration file.

    Returns:
        The expanded, absolute, resolved, case-folded path. Nothing here starts a
        process or requires the directory to exist; a name that does not resolve
        simply compares unequal to one that does.
    """
    expanded = os.path.expandvars(os.path.expanduser(value))
    return os.path.normcase(os.path.realpath(os.path.abspath(expanded)))


def _tree_identity_problems(experiment: AbExperiment, state: WorktreeState) -> list[str]:
    """Check that the tree the gateway indexes is the tree the arms run from.

    ``APP_REPOSITORY_PATH`` is what ``apps/gateway/core/config.py:98`` hands the
    repository and retrieval stages, while :attr:`AbExperiment.worktree` is the tree
    both terminal blocks move into and where the harness runs. The file holds them as
    two separate entries, so one can be edited and the other forgotten, and the arm
    then indexes a tree nothing validated: the changed-file set, the index, and the
    session log would describe different code.

    Args:
        experiment: The configuration to check.
        state: What :func:`inspect_worktree` saw of the tree the arms run from.

    Returns:
        Zero or one problem. A setting that is absent is not reported here, because
        :func:`_shared_setting_problems` already refuses it.
    """
    declared = experiment.shared_env.get("APP_REPOSITORY_PATH")
    if declared is None:
        return []
    if _same_directory(str(declared), state.path):
        return []
    return [
        f"APP_REPOSITORY_PATH is {declared} while both arms run from {state.path};"
        " make the two the same tree, or the gateway indexes code neither command"
        " was validated against"
    ]


def _worktree_problems(experiment: AbExperiment, state: WorktreeState) -> list[str]:
    """Check the isolated tree both arms would run from.

    A directory is not an experiment's isolation. The launcher is asked to be sure
    the tree is a detached ``git worktree`` checkout of *this* project: an ordinary
    folder, the main clone, a pruned worktree, or a tree the rendered commands
    cannot run in would each leave an arm reading source that has nothing to do
    with the commit under test, and say so only after the measurements.

    Args:
        experiment: The experiment being checked.
        state: What :func:`inspect_worktree` saw of the tree.

    Returns:
        Every reason an arm must not start there.
    """
    problems = _tree_identity_problems(experiment, state)
    if not state.exists:
        problems.append(
            f"the isolated worktree {state.path} is not a directory; create it with"
            " 'git worktree add --detach <path> <commit>'"
        )
        return problems
    problems.extend(_dotenv_problems(experiment, state))
    problems.extend(_marker_problems(state))
    problems.extend(_missing_path_problems(state))
    return problems


def _dotenv_problems(experiment: AbExperiment, state: WorktreeState) -> list[str]:
    """Report a ``.env`` in the tree, which would outrank this configuration."""
    if not state.has_dotenv:
        return []
    overlapping = sorted(set(state.dotenv_keys) & _declared_env_keys(experiment))
    detail = (
        f" It declares settings this experiment also declares: {', '.join(overlapping)}."
        if overlapping
        else ""
    )
    return [
        f"{state.dotenv_path} exists, and apps/gateway/main.py:52-54 loads it with override=True,"
        f" so it would replace what this launcher passes to the arm.{detail}"
        " Use a tree without a .env, as 'git worktree add' produces."
    ]


def _marker_problems(state: WorktreeState) -> list[str]:
    """Say what the tree's Git marker proves, or that it proves nothing."""
    if state.marker == WORKTREE_MARKER_LINKED:
        if state.detached is True:
            return []
        if state.detached is False:
            return [
                f"{state.path} is a worktree checked out on a branch, not detached from one"
                f" ({state.git_dir}); a commit somewhere else can move the source an arm is"
                " reading mid-run. Create it with 'git worktree add --detach <path> <commit>'"
            ]
        return [
            f"the HEAD in {state.git_dir} cannot be read, so this launcher cannot tell that"
            f" {state.path} is detached from a branch, and an arm must not start on a tree it"
            " cannot prove"
        ]
    if state.marker == WORKTREE_MARKER_CLONE:
        return [
            f"{state.path} has a {GIT_ADMIN_NAME} directory, which makes it a clone rather than"
            " an isolated worktree: it sits on a branch that moves, and a clone is where a .env"
            " lives. Create the arms' tree with 'git worktree add --detach <path> <commit>'"
        ]
    if state.marker == WORKTREE_MARKER_STALE:
        return [
            f"{state.path}'s {GIT_ADMIN_NAME} file points at {state.git_dir}, which no longer"
            " exists; the worktree was removed or pruned, so Git reports the tree as missing and"
            " an arm would run from source nothing owns"
        ]
    if state.git_dir is not None:
        return [
            f"{state.path}'s {GIT_ADMIN_NAME} file points at {state.git_dir}, which is not a"
            f" linked worktree's administration directory ({WORKTREE_ADMIN_SEGMENT!r} is not in"
            " it). A submodule checkout or a hand-written marker is not an isolated A/B tree;"
            " create it with 'git worktree add --detach <path> <commit>'"
        ]
    return [
        f"{state.path} holds no {GIT_ADMIN_NAME} marker, so it is an ordinary directory rather"
        " than a checkout of this repository. Create the arms' tree with 'git worktree add"
        " --detach <path> <commit>'"
    ]


def _missing_path_problems(state: WorktreeState) -> list[str]:
    """Name each required tree file that is not there."""
    if not state.missing_paths:
        return []
    reasons = "; ".join(
        f"{name} ({WORKTREE_PATH_REASONS.get(name, 'an arm needs it')})"
        for name in state.missing_paths
    )
    return [
        f"{state.path} is not a checkout this experiment can run in: it does not hold {reasons};"
        " 'git worktree add --detach <path> <commit>' carries every tracked file, including"
        " these"
    ]


def _declared_env_keys(experiment: AbExperiment) -> frozenset[str]:
    """Return every key the launcher would put into an arm's environment."""
    keys = set(experiment.shared_env)
    for arm in experiment.arms:
        keys.update(arm.env)
    keys.update(REQUIRED_SHARED_ENV_KEYS)
    keys.update(ALLOWED_ARM_ENV_KEYS)
    if experiment.provider_request_timeout_seconds is not None:
        keys.add("REQUEST_TIMEOUT")
    return frozenset(keys)


def _is_absolute(path: str) -> bool:
    """Report whether ``path`` is absolute here, or is an absolute POSIX path."""
    return Path(path).is_absolute() or path.startswith(("/", "\\\\"))


def _value_problems(key: str, value: str) -> list[str]:
    """Check one config value the way the gateway would read it."""
    if not value.strip():
        return []
    if key in ABSOLUTE_PATH_ENV_KEYS and not _is_absolute(value):
        return [
            f"{key} must be an absolute path; a relative one is read against the arm's working"
            " directory, not the worktree"
        ]
    if key in BOOL_ENV_KEYS and value.strip().lower() not in BOOL_TRUE_VALUES + BOOL_FALSE_VALUES:
        return [
            f"{key} is not a boolean pydantic-settings accepts;"
            f" apps/gateway/core/config.py:95-110 declares it as a bool field, so {value!r} makes"
            " the arm fail to start (write 'true' or 'false')"
        ]
    if key in LITERAL_BOOL_ENV_KEYS and value.strip() not in LITERAL_BOOL_VALUES:
        return [
            f"{key} is not the exact word 'true' or 'false'; packages/context reads it as"
            f" os.environ.get('{key}', 'true') != 'false' (packages/context/builder.py:205,"
            f" packages/context/ranking.py:193), so {value!r} leaves the switch set the way the"
            " comparison happens to fall rather than the way it was written"
        ]
    if key in JSON_OBJECT_ENV_KEYS:
        return _json_object_problems(key, value)
    if key in POSITIVE_INT_ENV_KEYS or key in NON_NEGATIVE_INT_ENV_KEYS:
        return _int_problems(key, value)
    if key == "APP_MODELS_CONFIG":
        return _models_config_problems(value)
    if key == "APP_REPOSITORY_CONTEXT_INTENT_BUDGETS":
        return _intent_budget_problems(value)
    return []


def _json_object_problems(key: str, value: str) -> list[str]:
    """Check a setting the gateway parses into a mapping, in silence.

    ``apps/gateway/core/config.py:45-54`` hands back an empty mapping for anything
    that is not JSON and skips every entry it does not recognise, so a half-right
    value starts the arm and quietly means the built-in behaviour.
    """
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        return [
            f"{key} is not valid JSON: {exc.msg} at character {exc.pos}."
            " apps/gateway/core/config.py:45-54 ignores a value it cannot parse, so the arm"
            " would run the built-in rules while this experiment says it set its own"
        ]
    if not isinstance(parsed, dict):
        return [
            f"{key} must be a JSON object, not {type(parsed).__name__};"
            " apps/gateway/core/config.py:53-54 keeps no rules from anything that is not a"
            " mapping, so the value would not reach the arm"
        ]
    return []


def _int_problems(key: str, value: str) -> list[str]:
    """Check an integer setting the gateway would otherwise replace with its default."""
    try:
        number = int(value.strip(), 10)
    except ValueError:
        return [
            f"{key} must be an integer; apps/gateway/core/config.py:99-110 declares these as int"
            f" fields, so {value!r} makes pydantic-settings refuse to start the arm at all"
        ]
    if number <= 0 and key in POSITIVE_INT_ENV_KEYS:
        return [f"{key} must be greater than zero, got {number}"]
    if number < 0:
        return [f"{key} must not be negative, got {number}"]
    return []


def _intent_budget_problems(value: str) -> list[str]:
    """Check every ``INTENT:tokens`` pair, because the gateway drops bad ones silently."""
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        return ["APP_REPOSITORY_CONTEXT_INTENT_BUDGETS has no INTENT:tokens pair in it"]
    problems: list[str] = []
    for item in items:
        intent, separator, tokens = item.partition(":")
        if not separator or not intent.strip():
            problems.append(
                f"APP_REPOSITORY_CONTEXT_INTENT_BUDGETS item '{item}' is not INTENT:tokens;"
                " apps/gateway/core/config.py:18-34 skips it silently, so that intent runs on the"
                " default budget"
            )
            continue
        try:
            number = int(tokens.strip(), 10)
        except ValueError:
            number = 0
        if number <= 0:
            problems.append(
                f"APP_REPOSITORY_CONTEXT_INTENT_BUDGETS item '{item}' has a token count"
                " that is not a positive integer;"
                " apps/gateway/core/config.py:18-34 skips it silently"
            )
    return problems


def _models_config_problems(value: str) -> list[str]:
    """Check the registry the arms would build from ``APP_MODELS_CONFIG``.

    ``packages/providers/registry_models.py:135-154`` ignores an entry that lacks
    a usable ``model``/``backend_model``, and ``packages/providers/router.py:51``
    hands the provider the entry's own ``timeout`` ahead of ``REQUEST_TIMEOUT``,
    so a per-entry timeout would outrank the relationship this experiment was
    validated on.
    """
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        return [f"APP_MODELS_CONFIG is not valid JSON: {exc.msg} at character {exc.pos}"]
    if not isinstance(parsed, list):
        return ["APP_MODELS_CONFIG must be a JSON array of model entries"]
    if not parsed:
        return ["APP_MODELS_CONFIG is an empty array, so the arms would have no model to serve"]
    problems: list[str] = []
    for index, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            problems.append(f"APP_MODELS_CONFIG entry {index} is not a JSON object")
            continue
        alias = entry.get("model")
        label = f"'{alias}'" if isinstance(alias, str) and alias.strip() else f"entry {index}"
        for key in MODEL_CONFIG_REQUIRED_ENTRY_KEYS:
            field = entry.get(key)
            if not isinstance(field, str) or not field.strip():
                problems.append(
                    f"APP_MODELS_CONFIG {label} needs a non-empty string '{key}';"
                    " packages/providers/registry_models.py:135-154 ignores an entry without it, so"
                    " the arms would not serve that model at all"
                )
        base_url = entry.get("base_url")
        if isinstance(base_url, str) and base_url.strip():
            if not base_url.startswith(("http://", "https://")):
                problems.append(
                    f"APP_MODELS_CONFIG {label} has a base_url that is not an http(s) URL, so every"
                    " request would fail long before the provider timeout"
                )
        if "timeout" in entry:
            problems.append(
                f"APP_MODELS_CONFIG {label} declares a per-model timeout;"
                " packages/providers/router.py:51 passes it to the provider ahead of"
                " REQUEST_TIMEOUT, so declare provider_request_timeout_seconds instead"
            )
        if "api_key" in entry:
            problems.append(
                f"APP_MODELS_CONFIG {label} declares an api_key,"
                " which would then be printed in every rendered command;"
                " the arms inherit that credential from the terminal anyway"
            )
        for key in ("context_window", "max_output_tokens"):
            if key in entry and (not isinstance(entry[key], int) or entry[key] <= 0):
                problems.append(
                    f"APP_MODELS_CONFIG {label} has a '{key}' that is not a positive integer"
                )
    return problems


def _model_selection_problems(experiment: AbExperiment) -> list[str]:
    """Check that the model the harness will ask for exists in the registry."""
    raw = experiment.shared_env.get("APP_MODELS_CONFIG")
    default_model = experiment.shared_env.get("DEFAULT_MODEL", "")
    if raw is None or not default_model:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    aliases = {
        entry["model"]
        for entry in parsed
        if isinstance(entry, dict) and isinstance(entry.get("model"), str)
    }
    if not aliases or default_model in aliases:
        return []
    return [
        f"DEFAULT_MODEL '{default_model}' is not one of the aliases APP_MODELS_CONFIG declares"
        f" ({', '.join(sorted(aliases))}); scripts/quality_harness.py:68 asks the arm for"
        " DEFAULT_MODEL by name, and packages/providers/registry_models.py:200-201 raises"
        " UnknownModelError for every probe"
    ]


def _harness_problems(experiment: AbExperiment) -> list[str]:
    """Check the harness-side inputs that decide how long an arm is measured for."""
    problems: list[str] = []
    if isinstance(experiment.harness_repeat, bool) or not isinstance(
        experiment.harness_repeat, int
    ):
        problems.append(
            f"harness_repeat must be an integer number of repeats,"
            f" got {experiment.harness_repeat!r}"
        )
    elif experiment.harness_repeat < 1:
        problems.append(
            f"harness_repeat must be at least 1, got {experiment.harness_repeat}; an arm measured"
            " zero times has no result to compare"
        )
    for index, probe in enumerate(experiment.harness_probes):
        if not isinstance(probe, str) or not probe.strip():
            problems.append(f"harness_probes entry {index} is not a probe id")
    if experiment.harness_max_tokens is not None:
        if isinstance(experiment.harness_max_tokens, bool) or not isinstance(
            experiment.harness_max_tokens, int
        ):
            problems.append(
                "harness_max_tokens must be an integer token count, got"
                f" {experiment.harness_max_tokens!r}"
            )
        elif experiment.harness_max_tokens <= 0:
            problems.append(
                f"harness_max_tokens must be greater than zero, got {experiment.harness_max_tokens}"
            )
    return problems


# ---------------------------------------------------------------------------
# What ``show`` prints - deterministic text, never a live call
# ---------------------------------------------------------------------------


def _quote(value: object) -> str:
    """Quote one value for PowerShell, doubling any embedded single quote."""
    return "'" + str(value).replace("'", "''") + "'"


def _gateway_url(arm: AbArm) -> str:
    """Return the base URL the harness must point at for one arm."""
    return f"http://{GATEWAY_HOST}:{arm.port}/v1"


def _declared_timeouts(experiment: AbExperiment) -> tuple[float, float]:
    """Return the two timeouts, refusing a render that would leave one to a default.

    The pair is returned rather than checked in place so that every renderer
    prints the numbers it was forced to read from the typed fields, and mypy can
    see that a rendered command never holds a ``None`` that came out as the word
    ``None`` in a shell line.

    Args:
        experiment: The experiment about to be rendered.

    Returns:
        The provider timeout the arms get as ``REQUEST_TIMEOUT`` and the harness
        ``--timeout``, both in seconds, both declared.

    Raises:
        AbLaunchError: If either timeout layer was never declared, which is the
            one thing a rendered command must never paper over.
    """
    provider = experiment.provider_request_timeout_seconds
    harness = experiment.harness_timeout_seconds
    missing: list[str] = []
    if provider is None:
        missing.append("provider_request_timeout_seconds")
    if harness is None:
        missing.append("harness_timeout_seconds")
    if provider is None or harness is None:
        raise AbLaunchError(
            f"cannot render a command: {', '.join(missing)} is not declared, and leaving it out"
            " would hand the arm a timeout default instead of the tested value"
        )
    return provider, harness


def render_environment_block(experiment: AbExperiment, arm: AbArm) -> str:
    """Render the environment one arm must be started with.

    Args:
        experiment: The experiment being launched.
        arm: One of ``experiment.arms``.

    Returns:
        One ``$env:KEY='value'`` line per setting the launcher controls, in
        sorted key order so the same experiment always prints the same text.
        Credential keys are absent by construction: an arm inherits them from
        the terminal, and ``show`` reports only whether they are set there.

    Raises:
        AbLaunchError: If a timeout was never declared.
    """
    _declared_timeouts(experiment)
    env = arm_environment(experiment, arm)
    return "\n".join(f"$env:{key}={_quote(env[key])}" for key in sorted(env))


def render_gateway_command(experiment: AbExperiment, arm: AbArm) -> str:
    """Render the uvicorn command that starts one arm.

    Args:
        experiment: The experiment being launched.
        arm: One of ``experiment.arms``.

    Returns:
        The command line, with the port from the arm and the entrypoint from
        ``GATEWAY_APP``, to be run inside the arm's own worktree.

    Raises:
        AbLaunchError: If a timeout was never declared.
    """
    _declared_timeouts(experiment)
    return (
        f"{UV_COMMAND} run python -m uvicorn {GATEWAY_APP} --factory"
        f" --host {GATEWAY_HOST} --port {arm.port}"
    )


def render_harness_command(experiment: AbExperiment, arm: AbArm) -> str:
    """Render the harness command that measures one arm.

    Args:
        experiment: The experiment being launched.
        arm: The arm to measure; it decides ``--base-url`` and
            ``--session-log-path``.

    Returns:
        The command line. ``--timeout`` comes from the validated configuration,
        so it cannot drift away from the provider timeout the arms run with.

    Raises:
        AbLaunchError: If a timeout was never declared.
    """
    _provider, harness = _declared_timeouts(experiment)
    parts = [UV_COMMAND, "run", "python", HARNESS_SCRIPT, "--base-url", _gateway_url(arm)]
    for probe in experiment.harness_probes:
        parts += ["--probe", _quote(probe)]
    parts += ["--repeat", str(experiment.harness_repeat)]
    if experiment.harness_max_tokens is not None:
        parts += ["--max-tokens", str(experiment.harness_max_tokens)]
    model = experiment.shared_env.get("DEFAULT_MODEL") or experiment.shared_env.get(
        "APP_DEFAULT_MODEL", ""
    )
    if model:
        parts += ["--model", _quote(model)]
    parts += [
        "--session-log-path",
        _quote(arm.session_log_path),
        "--timeout",
        _quote(_format_seconds(harness)),
        "--json",
    ]
    return " ".join(parts)


def render_arm_script(
    experiment: AbExperiment,
    arm: AbArm,
    worktree: WorktreeState | None = None,
) -> str:
    """Render one arm as the two terminal blocks that run and measure it.

    This is what ``show --arm`` prints, and it is written to be pasted. The first
    line moves the terminal into the validated tree, because the launcher, the
    harness script and any relative report path are read against the directory the
    terminal stands in - leaving that to whoever opens the terminal is how an arm
    ends up serving the main checkout while its own file says an isolated
    worktree. The session log is created before the gateway starts, and the
    command that blocks is kept apart from the command that measures, because the
    two cannot share a terminal.

    Args:
        experiment: The experiment the arm belongs to.
        arm: The arm to render.
        worktree: Pre-computed view of the isolated tree.

    Returns:
        Comments and commands in paste order, for this arm only.

    Raises:
        AbLaunchError: If the experiment must not be started, or a timeout was
            never declared.
    """
    state = require_valid_experiment(experiment, worktree)
    provider, harness = _declared_timeouts(experiment)
    log_dir = Path(arm.session_log_path).parent
    report_path = log_dir / f"quality_{arm.arm_id}.json"
    lines = [
        f"# arm '{arm.arm_id}': port {arm.port},"
        f" changed files {_format_bool(arm.changed_files_enabled)}",
        "#",
        "# Terminal 1 - paste all of this into one PowerShell and leave it running; the last",
        "# line is this arm's gateway, and it does not return.",
        f"Set-Location {_quote(state.path)}",
        "# The arm's own session log, created empty so the first request cannot fail on a",
        "# directory that was never made.",
        f"New-Item -ItemType Directory -Force {_quote(log_dir)} | Out-Null",
        f"New-Item -ItemType File -Force {_quote(arm.session_log_path)} | Out-Null",
        render_environment_block(experiment, arm),
        render_gateway_command(experiment, arm),
        "",
        "# Terminal 2 - a second PowerShell, started only once this arm answers a health",
        f"# check: curl http://{GATEWAY_HOST}:{arm.port}/health",
        "# It runs from the same tree so its relative paths, and any report it redirects,",
        "# belong to this experiment. It waits the number of seconds below per request,",
        f"# {harness:g} rather than the {provider:g} this arm's provider is allowed, so an arm",
        "# that gives up says so instead of being mistaken for a slow retrieval.",
        f"Set-Location {_quote(state.path)}",
        render_harness_command(experiment, arm),
        "",
        f"# Add '> {_quote(report_path)}' to the line above to keep the report for",
        "# scripts/evaluate_quality_harness.py. Neither block touches the quality store;",
        "# only that script's --persist writes to it.",
    ]
    return "\n".join(lines)


def render_launch_script(experiment: AbExperiment, worktree: WorktreeState | None = None) -> str:
    """Render the whole experiment as PowerShell a person can paste and run.

    Validation happens first, so an experiment that would silently run one arm
    on a different setting prints nothing but the reasons.

    Args:
        experiment: The experiment to launch.
        worktree: Pre-computed view of the isolated tree.

    Returns:
        A comment header, then one block per arm in launch order, each block the
        pair of terminals that arm needs: its own environment and gateway command,
        and the harness command that measures it with the validated timeout.

    Raises:
        AbLaunchError: If the experiment must not be started.
    """
    state = require_valid_experiment(experiment, worktree)
    provider, harness = _declared_timeouts(experiment)
    lines = [
        f"# A/B experiment '{experiment.name}', arms {' and '.join(experiment.arm_ids)}.",
        f"# Both arms run from {state.path}, a detached worktree holding no .env, so every",
        "# setting below is the setting the arm actually gets (apps/gateway/main.py:52-54",
        "# would otherwise let a .env replace it).",
        f"# Provider REQUEST_TIMEOUT = {provider:g} s; harness --timeout = {harness:g} s, which is",
        f"# at least {HARNESS_TIMEOUT_MARGIN_SECONDS:g} s longer,"
        " so the arm always gives up first.",
        "# Credentials are not here: start both terminals from one that already has "
        + ", ".join(
            f"{key}={'set' if present else 'not set'}"
            for key, present in sorted(secret_env_status().items())
        ),
    ]
    for arm in experiment.arms:
        lines.append("")
        lines.append(f"# ---- arm '{arm.arm_id}': port {arm.port} ----")
        lines.append(render_arm_script(experiment, arm, state))
    return "\n".join(lines)


def experiment_document(
    experiment: AbExperiment,
    worktree: WorktreeState | None = None,
) -> dict[str, Any]:
    """Return the machine-readable view of one experiment.

    Args:
        experiment: The experiment to describe.
        worktree: Pre-computed view of the isolated tree.

    Returns:
        A JSON-ready mapping holding the shared settings, each arm's complete
        environment, the rendered commands, the arm differences, and the
        credential keys by name only. No value of a key ``is_secret_key``
        accepts appears anywhere in it.
    """
    problems = validate_experiment(experiment, worktree)
    state = worktree if worktree is not None else inspect_worktree(experiment.worktree)
    document: dict[str, Any] = {
        "valid": not problems,
        "problems": list(problems),
        "experiment": _redacted_config(experiment),
        "worktree": {
            "path": state.path,
            "exists": state.exists,
            "has_dotenv": state.has_dotenv,
            "dotenv_path": state.dotenv_path,
            "dotenv_keys": list(state.dotenv_keys),
            "marker": state.marker,
            "git_dir": state.git_dir,
            "detached": state.detached,
            "missing_paths": list(state.missing_paths),
            "can_run_an_arm": state.can_run_an_arm,
        },
        "timeouts": {
            "provider_request_timeout_seconds": experiment.provider_request_timeout_seconds,
            "harness_timeout_seconds": experiment.harness_timeout_seconds,
            "required_margin_seconds": HARNESS_TIMEOUT_MARGIN_SECONDS,
            "provider_default_without_env": provider_default_timeout(),
            "harness_default_without_flag": harness_timeout_default(),
        },
        "credentials": {
            key: "set" if present else "not set"
            for key, present in sorted(secret_env_status().items())
        },
        "arms": {},
        "arm_differences": {
            key: [
                None if value == _MISSING else ("<not shown>" if is_secret_key(key) else value)
                for value in values
            ]
            for key, values in sorted(arm_env_diff(experiment).items())
        },
    }
    if not problems:
        document["arms"] = {
            arm.arm_id: {
                "port": arm.port,
                "base_url": _gateway_url(arm),
                "session_log_path": arm.session_log_path,
                "changed_files_enabled": arm.changed_files_enabled,
                "environment": arm_environment(experiment, arm),
                "gateway_command": render_gateway_command(experiment, arm),
                "harness_command": render_harness_command(experiment, arm),
                "launch_script": render_arm_script(experiment, arm, state),
            }
            for arm in experiment.arms
        }
    return document


def _redacted_config(experiment: AbExperiment) -> dict[str, Any]:
    """Return the experiment as written, with credential values replaced.

    ``experiment_document`` embeds the config so a report shows exactly what the
    file said; a secret belongs there as a marker, because the same document is
    what gets pasted into an A/B record.

    Args:
        experiment: The experiment to describe.

    Returns:
        JSON-ready data in the config-file shape, secret values redacted.
    """
    config = experiment_to_dict(experiment)
    config["shared_env"] = _redacted_env(config["shared_env"])
    for entry in config["arms"]:
        entry["env"] = _redacted_env(entry["env"])
    return config


def _redacted_env(env: Mapping[str, str]) -> dict[str, str]:
    """Replace credential values with a marker, keeping everything else.

    Args:
        env: The settings to describe.

    Returns:
        The same keys, with a credential value shown as ``<not shown>``.
    """
    return {key: SECRET_PLACEHOLDER if is_secret_key(key) else value for key, value in env.items()}


# ---------------------------------------------------------------------------
# The experiment file
# ---------------------------------------------------------------------------

#: Marker written into every generated file so a stale or hand-rolled file is
#: reported instead of half-trusted.
CONFIG_SCHEMA_VERSION = 1

#: The runbook's reference model alias, from ``README.md`` and the
#: isolated-worktree A/B section of ``docs/live-gateway-runbook.md``.
TEMPLATE_MODEL = "qwen38-27b"

#: The alias's context window and output ceiling, the two numbers the runbook's A/B
#: records calibrate the index budgets at. They are named because
#: ``harness_max_tokens`` is meant to be exactly the entry's ceiling, and a value
#: read back out of a mixed-type dict is easy to get wrong in silence.
TEMPLATE_MODEL_CONTEXT_WINDOW = 262144
TEMPLATE_MODEL_MAX_OUTPUT_TOKENS = 8192

#: The backend that alias routes to, with the calibration the index budgets at.
TEMPLATE_MODEL_ENTRY: dict[str, Any] = {
    "model": TEMPLATE_MODEL,
    "backend_model": "qwen3.8-flash-next",
    "provider": "openai",
    "base_url": "http://100.106.236.88:18300/v1",
    "context_window": TEMPLATE_MODEL_CONTEXT_WINDOW,
    "max_output_tokens": TEMPLATE_MODEL_MAX_OUTPUT_TOKENS,
    "chars_per_token": 3.5,
}

#: Ports the runbook says are free: the gateway owns 8001-8010.
TEMPLATE_PORTS = (8011, 8012)

#: The provider timeout the documented benefit A/B ran with. Declared here
#: rather than left to ``PROVIDER_DEFAULT_TIMEOUT_SECONDS``, because an arm that
#: never says is an arm that quietly got 60 seconds.
TEMPLATE_PROVIDER_REQUEST_TIMEOUT_SECONDS = 300.0

#: The harness ``--timeout`` that keeps above it, per
#: ``HARNESS_TIMEOUT_MARGIN_SECONDS``.
TEMPLATE_HARNESS_TIMEOUT_SECONDS = 345.0

#: Repeats per arm; the runbook's A/B records measure three each.
TEMPLATE_HARNESS_REPEAT = 3


def experiment_to_dict(experiment: AbExperiment) -> dict[str, Any]:
    """Return one experiment as JSON-ready data.

    Args:
        experiment: The experiment to serialise.

    Returns:
        A mapping ``experiment_from_dict`` reads back. Validation refuses to
        accept a secret-bearing setting, so writing a checked experiment out
        never puts a credential in a file.
    """
    return {
        "schema": CONFIG_SCHEMA_VERSION,
        "name": experiment.name,
        "worktree": experiment.worktree,
        "provider_request_timeout_seconds": experiment.provider_request_timeout_seconds,
        "harness_timeout_seconds": experiment.harness_timeout_seconds,
        "harness_probes": list(experiment.harness_probes),
        "harness_repeat": experiment.harness_repeat,
        "harness_max_tokens": experiment.harness_max_tokens,
        "shared_env": dict(experiment.shared_env),
        "arms": [
            {
                "arm_id": arm.arm_id,
                "port": arm.port,
                "session_log_path": arm.session_log_path,
                "changed_files_enabled": arm.changed_files_enabled,
                "env": dict(arm.env),
            }
            for arm in experiment.arms
        ],
    }


def experiment_from_dict(raw: Mapping[str, Any]) -> AbExperiment:
    """Build one experiment from parsed file data.

    Args:
        raw: The parsed JSON mapping.

    Returns:
        The ``AbExperiment`` the mapping describes, unvalidated - call
        ``validate_experiment`` or ``load_experiment`` before trusting it.

    Raises:
        AbLaunchError: If the mapping is not an experiment at all. Setting
            values are never echoed back, only the names of the ones at fault.
    """
    problems: list[str] = []
    if not isinstance(raw, Mapping):
        raise AbLaunchError("an experiment file must hold one JSON object")
    version = raw.get("schema", CONFIG_SCHEMA_VERSION)
    if version != CONFIG_SCHEMA_VERSION:
        problems.append(
            f"the file declares schema {version}, which this launcher's template does not match"
        )
    arms = _arms_from_dict(raw.get("arms"), problems)
    if raw.get("harness_repeat") is None:
        problems.append(
            "'harness_repeat' is missing from the file; one sample per arm is not a comparison"
        )
    experiment = AbExperiment(
        name=_string_field("name", raw, problems),
        worktree=_string_field("worktree", raw, problems),
        arms=arms,
        shared_env=_env_from_dict("shared_env", raw.get("shared_env"), problems),
        provider_request_timeout_seconds=_seconds_field(
            "provider_request_timeout_seconds", raw, problems
        ),
        harness_timeout_seconds=_seconds_field("harness_timeout_seconds", raw, problems),
        harness_probes=tuple(_string_list("harness_probes", raw.get("harness_probes"), problems)),
        harness_repeat=_int_field("harness_repeat", raw, 1, problems),
        harness_max_tokens=_optional_int_field("harness_max_tokens", raw, problems),
    )
    if problems:
        raise AbLaunchError(problems)
    return experiment


def _arms_from_dict(raw: object, problems: list[str]) -> tuple[AbArm, ...]:
    """Build the arm tuple from a file's ``arms`` value."""
    if not isinstance(raw, list) or not raw:
        problems.append("the file has no 'arms' list, and an A/B needs two arm objects")
        return ()
    arms: list[AbArm] = []
    for index, entry in enumerate(raw, start=1):
        if not isinstance(entry, Mapping):
            problems.append(f"arm {index} must be a JSON object")
            continue
        label = str(entry.get("arm_id") or f"arm {index}")
        where = f"{label}."
        arms.append(
            AbArm(
                arm_id=_string_field("arm_id", entry, problems, where),
                port=_port_field("port", entry, problems, where),
                session_log_path=_string_field("session_log_path", entry, problems, where),
                changed_files_enabled=_bool_field(
                    "changed_files_enabled", entry, False, problems, where
                ),
                env=_env_from_dict(f"{where}env", entry.get("env"), problems),
            )
        )
    return tuple(arms)


def _string_field(
    key: str,
    raw: Mapping[str, Any],
    problems: list[str],
    where: str = "",
) -> str:
    """Read one required string field, collecting a problem instead of raising.

    Args:
        key: The name to read from ``raw``.
        raw: The mapping to read.
        problems: Accumulated problems; appended to when the field is absent or
            is not text.
        where: Prefix naming whose field it is, such as ``"off."``.

    Returns:
        The text, or ``""`` when there was a problem.
    """
    label = f"{where}{key}"
    value = raw.get(key)
    if value is None or value == "":
        problems.append(f"'{label}' is missing from the file")
        return ""
    if not isinstance(value, str):
        problems.append(f"'{label}' must be a string, not {type(value).__name__}")
        return ""
    return value


def _port_field(
    key: str,
    raw: Mapping[str, Any],
    problems: list[str],
    where: str = "",
) -> int:
    """Read one port field, collecting a problem instead of raising."""
    label = f"{where}{key}"
    value = raw.get(key)
    if value is None:
        problems.append(f"'{label}' is missing from the file")
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(f"'{label}' must be a number, not {type(value).__name__}")
        return 0
    return value


def _int_field(label: str, raw: Mapping[str, Any], default: int, problems: list[str]) -> int:
    """Read one optional integer field, falling back to ``default``."""
    value = raw.get(label)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(f"'{label}' must be a whole number, not {type(value).__name__}")
        return default
    return value


def _optional_int_field(label: str, raw: Mapping[str, Any], problems: list[str]) -> int | None:
    """Read one optional integer field that has no default to fall back to."""
    value = raw.get(label)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(f"'{label}' must be a whole number, not {type(value).__name__}")
        return None
    return value


def _seconds_field(label: str, raw: Mapping[str, Any], problems: list[str]) -> float | None:
    """Read one seconds field, where absent means 'not declared', never zero."""
    value = raw.get(label)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(f"'{label}' must be a number of seconds, not {type(value).__name__}")
        return None
    return float(value)


def _bool_field(
    key: str,
    raw: Mapping[str, Any],
    default: bool,
    problems: list[str],
    where: str = "",
) -> bool:
    """Read one boolean field, accepting the spellings the launcher writes."""
    label = f"{where}{key}"
    value = raw.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return parse_bool_setting(value, problems=problems, label=label)
    problems.append(f"'{label}' must be true or false, not {type(value).__name__}")
    return default


def _string_list(label: str, value: object, problems: list[str]) -> list[str]:
    """Read one optional list of strings."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        problems.append(f"'{label}' must be a list of strings")
        return []
    return [item for item in value if item]


def _env_from_dict(label: str, value: object, problems: list[str]) -> dict[str, str]:
    """Read one mapping of setting names to values as the gateway sees them.

    Booleans become ``true``/``false`` and numbers print without a trailing
    ``.0``, so a file written by ``template`` and one written by hand render the
    identical environment.
    """
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        problems.append(f"'{label}' must be a JSON object of setting names to values")
        return {}
    env: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            problems.append(f"'{label}' has a setting name that is not a string")
            continue
        if isinstance(item, bool):
            env[key] = _format_bool(item)
        elif isinstance(item, (int, float)):
            env[key] = _format_seconds(float(item))
        elif isinstance(item, str):
            env[key] = item
        else:
            problems.append(
                f"'{label}' setting {key} must be a string or a number, not {type(item).__name__}"
            )
    return env


def parse_bool_setting(value: str, problems: list[str], label: str) -> bool:
    """Resolve one textual boolean from a file.

    Args:
        value: The text found in the file.
        problems: Accumulated problems; appended to when the text is neither
            spelling.
        label: The field name to name in that problem.

    Returns:
        ``True`` or ``False`` for the two accepted spellings, ``False`` when the
        text was not one of them.
    """
    lowered = value.strip().lower()
    if lowered in BOOL_TRUE_VALUES:
        return True
    if lowered in BOOL_FALSE_VALUES:
        return False
    problems.append(f"'{label}' must be true or false, not {value.lower() or 'an empty string'}")
    return False


def load_experiment(path: str | Path) -> AbExperiment:
    """Read one experiment file.

    Args:
        path: The JSON file to read.

    Returns:
        The experiment it describes.

    Raises:
        AbLaunchError: If the file cannot be read, is not valid JSON, or is not
            an experiment. File contents are never included in the message, in
            case a credential was put in one by hand.
    """
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AbLaunchError(
            f"{target} cannot be read: {exc.strerror or exc.__class__.__name__}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AbLaunchError(
            f"{target} is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"
        ) from exc
    return experiment_from_dict(raw)


def save_experiment(experiment: AbExperiment, path: str | Path) -> Path:
    """Write one experiment file.

    Args:
        experiment: The experiment to write.
        path: The destination; parent directories are created.

    Returns:
        The path written to.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(experiment_to_dict(experiment), indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def template_experiment(
    name: str = "changed_files_benefit",
    worktree: str = r"..\lap-ab",
) -> AbExperiment:
    """Return a ready-to-check experiment holding the runbook's A/B defaults.

    Args:
        name: The experiment name, used in the session log file names.
        worktree: The detached worktree both arms start from.

    Returns:
        An experiment carrying the settings the 2026-10-13 benefit A/B ran with
        (``docs/live-gateway-runbook.md``), including ``REQUEST_TIMEOUT=300`` and
        a harness timeout above it, so it is valid the moment ``worktree`` is a
        detached worktree of this project that holds no ``.env``. The settings in
        ``TEMPLATE_MEASUREMENT_ENV`` are spelled out rather than left to the
        terminal, because each one moves an answer and none of them has a
        worktree to be read from. ``worktree`` is stored resolved and absolute: an
        arm started from elsewhere would otherwise read a relative
        ``APP_REPOSITORY_PATH`` against its own working directory. The two arms
        differ only in keys ``ALLOWED_ARM_ENV_KEYS`` permits.
    """
    log_dir = Path(worktree).expanduser().resolve() / "logs"
    repository = str(Path(worktree).expanduser().resolve())
    return AbExperiment(
        name=name,
        worktree=repository,
        arms=(
            AbArm(
                arm_id="off",
                port=TEMPLATE_PORTS[0],
                session_log_path=str(log_dir / f"sessions_{name}_off.jsonl"),
                changed_files_enabled=False,
            ),
            AbArm(
                arm_id="on",
                port=TEMPLATE_PORTS[1],
                session_log_path=str(log_dir / f"sessions_{name}_on.jsonl"),
                changed_files_enabled=True,
            ),
        ),
        shared_env={
            "DEFAULT_MODEL": TEMPLATE_MODEL,
            "APP_LOG_LEVEL": "INFO",
            "APP_DEFAULT_MODEL": TEMPLATE_MODEL,
            "APP_DEFAULT_PROVIDER": "openai",
            "APP_MODELS_CONFIG": json.dumps([TEMPLATE_MODEL_ENTRY], separators=(",", ":")),
            "APP_REPOSITORY_PATH": repository,
            "APP_REPOSITORY_CONTEXT_ENABLED": "true",
            "APP_REPOSITORY_CONTEXT_MAX_TOKENS": "4096",
            "APP_REPOSITORY_CONTEXT_INTENT_BUDGETS": (
                "SEARCH:2048,TEST:2048,DEBUG:2048,REFACTOR:4096,IMPLEMENT:4096,EXPLAIN:4096"
            ),
            "APP_REPOSITORY_EXCLUDE_TESTS": "false",
            "APP_REPOSITORY_EXCLUDE_GLOBS": "scripts/**",
            "APP_CONTEXT_DELTA_INJECTION": "true",
            "APP_SESSION_LOG_ENABLED": "true",
            "APP_HISTORY_CAP_ENABLED": "true",
            "APP_HISTORY_CAP_TOKENS": "3000",
            **TEMPLATE_MEASUREMENT_ENV,
        },
        provider_request_timeout_seconds=TEMPLATE_PROVIDER_REQUEST_TIMEOUT_SECONDS,
        harness_timeout_seconds=TEMPLATE_HARNESS_TIMEOUT_SECONDS,
        harness_probes=(),
        harness_repeat=TEMPLATE_HARNESS_REPEAT,
        harness_max_tokens=TEMPLATE_MODEL_MAX_OUTPUT_TOKENS,
    )


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

#: Where generated experiment files are expected to live.
DEFAULT_CONFIG_DIR = Path("configs") / "ab_experiments"


def render_diff(experiment: AbExperiment) -> str:
    """Return the keys the two arms disagree on, one line per key.

    Args:
        experiment: The experiment to compare.

    Returns:
        A heading naming the arms, then each differing key with its value per
        arm in launch order. The value of a key ``is_secret_key`` accepts is
        replaced by a marker, so the diff is safe to paste into a report.
    """
    diff = arm_env_diff(experiment)
    lines = [f"# arm differences in '{experiment.name}' ({' / '.join(experiment.arm_ids)})"]
    if not diff:
        lines.append("# none - both arms would run the same experiment twice")
    for key, values in sorted(diff.items()):
        lines.append(f"  {key}: " + " | ".join(_describe_env_value(key, v) for v in values))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Return the parser for the three subcommands, none of which launch."""
    parser = argparse.ArgumentParser(
        prog="ab_launcher",
        description=(
            "Build and validate the configuration two isolated-worktree A/B arms"
            " start with. Nothing here starts a process or contacts a backend."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser(
        "template",
        help="write or print an experiment file holding the runbook's A/B defaults",
    )
    template.add_argument("--name", default="changed_files_benefit", help="experiment name")
    template.add_argument(
        "--worktree",
        default=r"..\lap-ab",
        help="detached worktree both arms run from, as 'git worktree add --detach' made it",
    )
    template.add_argument(
        "--out",
        help="file to write; without it the JSON goes to stdout and nothing is written",
    )

    validate = commands.add_parser("validate", help="check one experiment file and exit")
    validate.add_argument("--config", required=True, help="the experiment JSON to check")

    show = commands.add_parser("show", help="print the commands each arm must be started with")
    show.add_argument("--config", required=True, help="the experiment JSON to render")
    show.add_argument(
        "--arm",
        help=(
            "render only this arm, as the two paste-ready terminal blocks that run and measure it"
        ),
    )
    show.add_argument(
        "--diff",
        action="store_true",
        help="print the keys the arms disagree on instead of the commands",
    )
    show.add_argument("--json", action="store_true", dest="as_json", help="emit the JSON document")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the launcher.

    Args:
        argv: Arguments after the script name; ``None`` reads ``sys.argv``.

    Returns:
        ``0`` when the experiment is valid and was rendered, ``2`` when anything
        about it must be fixed first. No exit code here ever means a run was
        attempted: the launcher never starts a process.
    """
    args = build_parser().parse_args(argv)
    try:
        if args.command == "template":
            return _command_template(args)
        if args.command == "validate":
            return _command_validate(args)
        return _command_show(args)
    except AbLaunchError as exc:
        for problem in exc.problems:
            print(f"ab-launcher: {problem}", file=sys.stderr)
        return 2


def _command_template(args: argparse.Namespace) -> int:
    """Handle ``template``: write a starting point, then report the tree it names.

    The fields are checked before anything is written, so the file handed over is
    never one the loader would refuse. The tree is not: a template names a worktree
    that usually does not exist yet, and writing the file is the point of the
    command. What follows the file name is therefore the same worktree verdict
    ``validate`` would reach for that tree right now, which is how ``template``
    reports whether ``git worktree add`` still has to run before either arm starts.

    Args:
        args: Parsed arguments; ``name``, ``worktree``, and the optional ``out``.

    Returns:
        ``0``, because a written template is a usable starting point whatever the
        tree looks like. A non-startable tree is said, not failed.
    """
    experiment = template_experiment(name=str(args.name), worktree=str(args.worktree))
    raise_on_problems(_config_problems(experiment))
    state = inspect_worktree(experiment.worktree)
    if args.out:
        path = save_experiment(experiment, str(args.out))
        print(f"ab-launcher: wrote {path}")
    else:
        print(json.dumps(experiment_to_dict(experiment), indent=2))
    problems = _worktree_problems(experiment, state)
    if not problems:
        print(f"ab-launcher: {state.path} can run either arm as it stands")
        return 0
    print(f"ab-launcher: {state.path} cannot run an arm yet:", file=sys.stderr)
    for problem in problems:
        print(f"ab-launcher:   {problem}", file=sys.stderr)
    print(
        "ab-launcher: fix the tree, then run 'validate' on this file; nothing is"
        " started until it comes back with no reasons",
        file=sys.stderr,
    )
    return 0


def _command_validate(args: argparse.Namespace) -> int:
    """Handle ``validate``: report every reason the arms must not start."""
    experiment = load_experiment(str(args.config))
    state = require_valid_experiment(experiment)
    provider, harness = _declared_timeouts(experiment)
    print(f"ab-launcher: '{experiment.name}' is valid; both arms may be started from {state.path}")
    print(
        f"ab-launcher: the tree is a {'detached ' if state.detached else ''}worktree,"
        f" administered at {state.git_dir}"
    )
    print(
        "ab-launcher: REQUEST_TIMEOUT="
        f"{provider:g} s in both arms, harness --timeout={harness:g} s against either, at least"
        f" {HARNESS_TIMEOUT_MARGIN_SECONDS:g} s more"
    )
    return 0


def _command_show(args: argparse.Namespace) -> int:
    """Handle ``show``: print the commands, never run them."""
    experiment = load_experiment(str(args.config))
    if args.as_json:
        print(json.dumps(experiment_document(experiment), indent=2))
        return 0
    if args.diff:
        raise_on_problems(validate_experiment(experiment))
        print(render_diff(experiment))
        return 0
    if args.arm:
        arm = _find_arm(experiment, str(args.arm))
        print(render_arm_script(experiment, arm))
        return 0
    print(render_launch_script(experiment))
    return 0


def raise_on_problems(problems: Sequence[str]) -> None:
    """Turn a list of problems into an ``AbLaunchError``.

    Args:
        problems: The reasons collected by ``validate_experiment``; empty means
            nothing to report.

    Raises:
        AbLaunchError: If there was at least one problem.
    """
    if problems:
        raise AbLaunchError(problems)


def _find_arm(experiment: AbExperiment, arm_id: str) -> AbArm:
    """Return one arm by name.

    Args:
        experiment: The experiment to search.
        arm_id: The name given on the command line.

    Returns:
        The matching ``AbArm``.

    Raises:
        AbLaunchError: If no arm carries that name, listing the ones that do.
    """
    for arm in experiment.arms:
        if arm.arm_id == arm_id:
            return arm
    raise AbLaunchError(
        f"'{arm_id}' is not one of this experiment's arms ({', '.join(experiment.arm_ids)})"
    )


if __name__ == "__main__":
    raise SystemExit(main())
