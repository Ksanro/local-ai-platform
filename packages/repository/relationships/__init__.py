"""Relationship extraction package.

Provides language-independent relationship extractors that enrich the
RepositoryIndex with developer intelligence — how symbols interact.

Architecture
------------

Repository

    |

    v

Repository Index

    |

    v

Relationship Extractors

    |

    |-- CallExtractor

    |-- ImportExtractor (future)

    |-- ReferenceExtractor (future)

    |-- TypeUsageExtractor (future)

    +-- DataFlowExtractor (future)

            |

            v

Relationship Graph

            |

            v

Context Builder

Usage
-----

Register an extractor and build:

    from packages.repository.relationships import RelationshipRegistry
    from packages.repository.relationships.call_extractor import CallExtractor
    from packages.repository.index.builder import RepositoryIndexBuilder

    registry = RelationshipRegistry()
    registry.register(CallExtractor())

    builder = RepositoryIndexBuilder()
    index = builder.build(path, registry=registry)

Or use the default registry (CallExtractor is registered by default):

    from packages.repository import build_index

    index = build_index(path)
"""

from __future__ import annotations

from packages.repository.relationships.base import RelationshipExtractor
from packages.repository.relationships.registry import RelationshipRegistry

__all__ = [
    "RelationshipExtractor",
    "RelationshipRegistry",
]
