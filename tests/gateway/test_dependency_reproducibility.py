"""Regression guard for clean-checkout dependency reproducibility.

Context: the A1 gateway-start task hit two reproducibility defects at once.
``pyproject.toml`` declared ``httpx2`` (a separate distribution that does not
provide the ``httpx`` top-level module) while ``packages/providers/{openai,vllm}.py``
import ``httpx``, and ``uv.lock`` was gitignored so a fresh worktree had no lock to
install from. A bare ``uv run`` there failed with ``ModuleNotFoundError: No module
named 'httpx'``. These checks keep that class of bug from coming back; they are
static/pydoc checks only and never contact the SGLang backend or start a live
quality run.
"""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
LOCKFILE = REPO_ROOT / "uv.lock"
GITIGNORE = REPO_ROOT / ".gitignore"

# Third-party top-level modules imported by the live runtime path: the provider
# modules the gateway imports at startup (``packages.providers._load_providers``)
# plus the gateway entry point itself.
LIVE_RUNTIME_MODULES = (
    "packages.providers.openai",
    "packages.providers.vllm",
    "apps.gateway.main",
)

# Distributions that only existed to satisfy the mistyped ``httpx2`` declaration.
HTTPX2_ONLY_PACKAGES = ("httpx2", "httpcore2")

# PEP 503 name normalization: lowercase, runs of -_. collapsed to a single -.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_dependencies() -> list[str]:
    """Return the normalized direct runtime dependency names."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    declared: list[str] = []
    for spec in data["project"]["dependencies"]:
        match = _NAME_RE.match(spec.strip())
        assert match is not None, f"unparsable dependency specifier: {spec!r}"
        declared.append(_normalized(match.group(0)))
    return declared


def _locked_packages() -> list[str]:
    """Return the normalized package names present in the committed lock."""
    data = tomllib.loads(LOCKFILE.read_text(encoding="utf-8"))
    return [_normalized(str(pkg["name"])) for pkg in data["package"]]


def test_declared_runtime_dependencies_include_httpx_not_httpx2() -> None:
    declared = _declared_dependencies()

    assert "httpx" in declared, f"httpx is not a declared runtime dependency: {declared}"
    for mistyped in HTTPX2_ONLY_PACKAGES:
        assert mistyped not in declared, f"{mistyped} is declared but nothing imports it"


def test_committed_lock_resolves_httpx_without_httpx2() -> None:
    assert LOCKFILE.is_file(), f"missing lockfile: {LOCKFILE}"

    locked = _locked_packages()
    assert "httpx" in locked, f"lock does not resolve httpx: {sorted(locked)}"
    for mistyped in HTTPX2_ONLY_PACKAGES:
        assert mistyped not in locked, f"lock still carries {mistyped} from the stale resolve"


def test_uv_lock_is_version_controlled() -> None:
    """The lock must be committed; an ignored lock is what broke the A1 checkout."""
    ignored_patterns = [
        line.strip()
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    locking_patterns = {"uv.lock", "/uv.lock", "**/uv.lock"}
    assert not locking_patterns.intersection(ignored_patterns), (
        "uv.lock must not be gitignored; commit the lock so clean worktrees "
        "install a reproducible environment"
    )


def test_live_runtime_path_imports_from_the_working_tree() -> None:
    """Every live-path third-party import must resolve in this environment."""
    for dotted in LIVE_RUNTIME_MODULES:
        module = importlib.import_module(dotted)
        origin = module.__file__
        assert origin is not None, f"{dotted} has no source file to import from"
        resolved = Path(origin).resolve()
        assert resolved.is_relative_to(REPO_ROOT), (
            f"{dotted} resolved outside the working tree: {resolved}"
        )
