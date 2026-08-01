"""Compatibility import for the repository context pipeline stage.

The live implementation lives in ``packages.pipeline.stages.repository_context``.
This module keeps the historical import path working without maintaining a
second copy of ``RepositoryContextStage``.
"""

from __future__ import annotations

from packages.pipeline.stages.repository_context import RepositoryContextStage

__all__ = ["RepositoryContextStage"]
