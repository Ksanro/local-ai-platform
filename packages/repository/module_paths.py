"""One deterministic conversion between index module keys and repository files.

The repository index keys Python modules by what the AST extractor computes from
the file's location relative to the index root
(``packages/repository/symbols/python_ast.py``):

.. code-block:: text

    str(rel.with_suffix("")).replace("\\", "/")      # packages/context/delta

so a key is repository relative, forward slashed and **without** the ``.py``
suffix, while every other consumer of the repository - Git, the filesystem, and
a Cline envelope - names the same file *with* the suffix.  This module is the
only place allowed to move between the two spellings, in either direction, so no
caller can invent a slightly different rule and quietly stop matching.

Both directions are idempotent on their own domain and preserve case: the
extractor derives keys from real paths, so a key's spelling is the repository's
own.  Case-insensitive *identity* comparison is a separate concern and belongs
to the caller that normalizes untrusted paths
(``packages.pipeline.cline_activity.file_identity``).

Constraints
-----------

- Pure string work: no filesystem access, no Git, no process, no I/O of any kind.
- No gateway, pipeline, provider, or context imports.
- Nothing here validates containment; a key is not a path a client sent and must
  never be treated as one.  Use :func:`packages.repository.changed_files` to turn
  a working-tree path into a key, and reject anything that cannot be made
  repository relative there.

Public API
----------

.. code-block:: python

    from packages.repository.module_paths import module_key_to_path

    module_key_to_path("packages/context/delta")   # "packages/context/delta.py"
    module_key_to_path("packages/context/delta.py")  # unchanged - already a file
"""

from __future__ import annotations

from typing import Final

__all__ = ["MODULE_SUFFIX", "module_key_to_path", "path_to_module_key"]

#: The suffix the index drops from a module key, and the only one a key can grow
#: back into.  The extractor indexes ``*.py`` files and nothing else, so a path
#: that does not end in it has no module key.
MODULE_SUFFIX: Final = ".py"


def module_key_to_path(module_key: str) -> str:
    """Return the repository-relative file an index module key names.

    Args:
        module_key: An index module key, or an already-suffixed module path.
            Both spellings are accepted, so the function is safe to apply to a
            value whose origin is uncertain.

    Returns:
        A repository-relative, forward-slashed path ending in ``.py``, or ``""``
        for a key that names nothing.  Case is preserved; an empty result means
        the caller should skip the value rather than compare against it.
    """
    cleaned = _relative(module_key)
    if not cleaned:
        return ""
    if cleaned.lower().endswith(MODULE_SUFFIX):
        return cleaned
    return f"{cleaned}{MODULE_SUFFIX}"


def path_to_module_key(file_path: str) -> str | None:
    """Return the index module key a repository-relative file belongs to.

    Args:
        file_path: A repository-relative path in either slash or platform form.
            The ``.py`` suffix is **required**: this is the reverse of what the
            extractor computes, and a path without it is not a Python module the
            index can hold, so guessing one would invent a module for a document,
            a fixture or a build artifact.

    Returns:
        The module key, or ``None`` when the path names no Python module the
        index could hold - an empty path, the repository root, or a non-``.py``
        file such as a document, a test fixture or a build artifact.  Case is
        preserved: a key is derived from a real path, so its spelling is the
        repository's own.
    """
    cleaned = _relative(file_path)
    if not cleaned.lower().endswith(MODULE_SUFFIX):
        return None
    return cleaned[: -len(MODULE_SUFFIX)] or None


def _relative(text: str) -> str:
    """Return the forward-slashed, root-relative spelling of one path.

    Args:
        text: Any spelling of a repository-relative path.

    Returns:
        The path with backslashes converted, leading ``./`` segments removed and
        a trailing separator dropped; whitespace-only input yields ``""``.
    """
    path = text.replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    return path.rstrip("/")
