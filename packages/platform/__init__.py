"""Platform Validation Framework — integrity validation of the assembled platform.

Architecture
------------

The Platform Validation Framework performs a complete integrity validation
of the assembled engineering platform. It is executed after Platform Bootstrap
and before the Engineering Controller accepts requests.

    PlatformBootstrap
            │
            ▼
    PlatformValidator
            │
            ├── Dependency Validation
            ├── Registry Validation
            ├── Provider Validation
            ├── Workflow Validation
            ├── Task Validation
            ├── Capability Validation
            ├── Configuration Validation
            ├── Public API Validation
            └── Health Report

    PlatformValidator
            │
            ▼
    PlatformHealthChecker
            │
            ├── health() — compute health status
            ├── summary() — one-line summary
            └── details() — multi-line details

Public API
----------

.. code-block:: python

    from packages.platform.validator import PlatformValidator
    from packages.platform.health import PlatformHealthChecker
    from packages.platform.models import (
        ValidationIssue,
        PlatformHealth,
        ValidationReport,
        HealthReport,
        Severity,
    )

    # Validate platform
    validator = PlatformValidator()
    report = validator.validate(registries, configuration, container)

    # Check health
    checker = PlatformHealthChecker()
    health = checker.health(report)

    if health.status == PlatformHealth.HEALTHY:
        print("Platform is healthy")

Constraints
-----------

- NEVER performs engineering work.
- NEVER invokes providers.
- NEVER analyzes repositories.
- ONLY validates platform consistency.

"""

from __future__ import annotations

from packages.platform.diagnostics import DiagnosticsEngine
from packages.platform.health import PlatformHealthChecker
from packages.platform.models import (
    HealthReport,
    PlatformHealth,
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationStatistics,
)
from packages.platform.validator import PlatformValidator

__all__ = [
    # Models
    "HealthReport",
    "PlatformHealth",
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "ValidationStatistics",
    # Validator
    "PlatformValidator",
    # Health
    "PlatformHealthChecker",
    # Diagnostics
    "DiagnosticsEngine",
]