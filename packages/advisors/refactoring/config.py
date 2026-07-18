"""Refactoring Advisor configuration.

Defines the immutable configuration for the RefactoringAdvisor.
All thresholds and parameters are configurable to allow tuning
for different repository sizes and coding standards.

Usage
-----

.. code-block:: python

    from packages.advisors.refactoring.config import RefactoringConfig, DEFAULT_CONFIG

    from packages.advisors.refactoring.advisor import RefactoringAdvisor

    advisor = RefactoringAdvisor(
        config=RefactoringConfig(
            large_module_threshold=50,
            dependency_threshold=15,
        ),
    )

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- All defaults are production-tested values.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RefactoringConfig:
    """Configuration for the RefactoringAdvisor.

    Attributes:
        large_module_threshold: Number of symbols at which a module is
            considered ``LARGE_MODULE``. Default is 100.
        dependency_threshold: Number of outgoing relationships at which
            a module is considered to have ``EXCESSIVE_DEPENDENCIES``.
            Default is 20.
        coupling_multiplier: Multiplier for average total connections
            to determine ``HIGH_COUPLING``. A module is flagged when
            its total connections exceed ``average * coupling_multiplier``.
            Default is 1.5.
        minimum_confidence: Minimum confidence threshold for including
            opportunities in the report. Opportunities below this value
            are excluded. Default is 0.0 (include all).
    """

    large_module_threshold: int = 100
    dependency_threshold: int = 20
    coupling_multiplier: float = 1.5
    minimum_confidence: float = 0.0


#: Default configuration instance. Use this for standard analysis.
DEFAULT_CONFIG = RefactoringConfig()
