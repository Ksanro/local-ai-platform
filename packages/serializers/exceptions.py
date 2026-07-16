"""Serialization layer exceptions.

Defines a hierarchy of exceptions for different failure modes
in the serialization layer.
"""

from __future__ import annotations


class SerializationError(Exception):
    """Base serialization error.

    All serialization-specific exceptions inherit from this class
    so they can be caught collectively.
    """


class UnknownSerializerError(SerializationError):
    """Raised when a serializer is not registered in the registry."""


class SerializationFormatError(SerializationError):
    """Raised when message formatting fails.

    Covers invalid message shapes, missing required fields,
    or incompatible message combinations.
    """
