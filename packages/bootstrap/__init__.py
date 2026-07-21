"""Bootstrap Framework — Platform assembly and dependency injection.

The Bootstrap Framework is the central assembly point for the entire
engineering platform. It constructs all registries, factories, engines,
and components, then validates and returns a ready-to-use
EngineeringController.

Architecture
------------

PlatformBootstrap
    │
    ├── build(configuration) -> EngineeringController
    │
    ├── Steps:
    │   1. Construct all registries
    │   2. Construct all factories
    │   3. Construct all engines
    │   4. Register providers
    │   5. Register workflows
    │   6. Register capabilities
    │   7. Register tasks
    │   8. Validate platform
    │   9. Return ready-to-use EngineeringController
    │
    ▼
EngineeringController

Public API
----------

.. code-block:: python

    from packages.bootstrap import PlatformBootstrap, build
    from packages.bootstrap.configuration import PlatformConfiguration

    # Using the class
    bootstrap = PlatformBootstrap()
    config = PlatformConfiguration.default()
    controller = bootstrap.build(config)

    # Using the convenience function
    controller = build()

"""

from __future__ import annotations

from packages.bootstrap.builder import PlatformBootstrap, build

__all__ = [
    "PlatformBootstrap",
    "build",
]