"""Dependency container — lightweight deterministic DI container.

Provides a strict, explicit dependency injection container that supports
constructor injection only. No reflection, no runtime discovery, no magic.

Architecture
------------

DependencyContainer
    │
    ├── register(name, factory, dependencies)
    ├── resolve(name) -> instance
    ├── contains(name) -> bool
    ├── all() -> resolved instances
    └── validate() -> errors

Public API
----------

.. code-block:: python

    from packages.bootstrap.container import DependencyContainer

    container = DependencyContainer()
    container.register(
        name="validator",
        factory=lambda: RequestValidator(),
        dependencies=(),
    )

    # Resolve
    validator = container.resolve("validator")

    # Check existence
    if container.contains("validator"):
        print("Registered")

    # Validate
    errors = container.validate()

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    pass  # No additional imports needed


__all__ = [
    "DependencyContainer",
    "RegistrationError",
    "ResolutionError",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RegistrationError(Exception):
    """Raised when a registration fails."""


class ResolutionError(Exception):
    """Raised when a resolution fails."""


# ---------------------------------------------------------------------------
# DependencyContainer
# ---------------------------------------------------------------------------


class DependencyContainer:
    """Deterministic dependency injection container.

    This container enforces strict dependency management:

    - Constructor injection only
    - No reflection
    - No runtime discovery
    - No magic
    - Deterministic ordering
    - Cycle detection via DFS

    All registrations are explicit — the container never guesses.

    Usage
    -----

    .. code-block:: python

        from packages.bootstrap.container import DependencyContainer

        container = DependencyContainer()

        # Register with no dependencies
        container.register(
            name="validator",
            factory=lambda: RequestValidator(),
            dependencies=(),
        )

        # Register with dependencies
        container.register(
            name="controller",
            factory=lambda validator, registry: EngineeringController(validator, registry),
            dependencies=("validator", "registry"),
        )

        # Resolve
        controller = container.resolve("controller")

    Attributes
    ----------
    _registrations: Mapping of name to (factory, dependencies) tuples.
    _resolved: Cache of resolved instances.
    """

    def __init__(self) -> None:
        """Initialize an empty dependency container."""
        self._registrations: dict[str, tuple[Callable[..., Any], tuple[str, ...]]] = {}
        self._resolved: dict[str, Any] = {}

    def register(
        self,
        name: str,
        factory: Callable[..., Any],
        dependencies: tuple[str, ...] = (),
    ) -> None:
        """Register a dependency factory.

        Registers a factory function that will be called during resolution
        to create the dependency. Dependencies are other registered names
        that will be passed as arguments to the factory.

        Args:
            name: Unique identifier for this dependency.
            factory: Callable that creates the dependency instance.
            dependencies: Tuple of dependency names to inject.

        Raises:
            RegistrationError: If name is empty, factory is not callable,
                or a dependency with the same name is already registered.

        Example
        -------

        .. code-block:: python

            container.register(
                name="my_service",
                factory=MyService,
                dependencies=("repo", "config"),
            )
        """
        if not name:
            raise RegistrationError("Dependency name cannot be empty.")

        if not callable(factory):
            raise RegistrationError(
                f"Factory for '{name}' must be callable, got {type(factory).__name__}."
            )

        if name in self._registrations:
            raise RegistrationError(
                f"Dependency '{name}' is already registered. "
                "Use unregister() first if you need to replace it."
            )

        # Validate all dependencies reference existing registrations
        for dep in dependencies:
            if dep == name:
                raise RegistrationError(
                    f"Dependency '{name}' cannot depend on itself."
                )
            if dep not in self._registrations and dep not in dependencies:
                # Only warn about dependencies that haven't been registered yet
                # This is not an error since dependencies may be registered later
                pass

        self._registrations[name] = (factory, dependencies)

    def unregister(self, name: str) -> None:
        """Unregister a dependency.

        Removes a dependency from the container. Also removes it from
        the resolved cache if it was already resolved.

        Args:
            name: The dependency name to unregister.

        Example
        -------

        .. code-block:: python

            container.unregister("old_service")
        """
        self._registrations.pop(name, None)
        self._resolved.pop(name, None)

    def resolve(self, name: str) -> Any:
        """Resolve a dependency by name.

        Creates the dependency instance by calling its factory with
        all resolved dependencies as arguments. Results are cached
        for subsequent calls (singleton behavior per container).

        Args:
            name: The dependency name to resolve.

        Returns:
            The resolved dependency instance.

        Raises:
            ResolutionError: If the dependency is not registered,
                has unmet dependencies, or circular dependencies are detected.

        Example
        -------

        .. code-block:: python

            service = container.resolve("my_service")
        """
        if name in self._resolved:
            return self._resolved[name]

        if name not in self._registrations:
            raise ResolutionError(
                f"Dependency '{name}' is not registered. "
                f"Available: {tuple(sorted(self._registrations.keys()))}"
            )

        factory, dependencies = self._registrations[name]

        # Check for circular dependencies
        visiting: set[str] = set()
        if self._has_cycle(name, visiting, set()):
            raise ResolutionError(
                f"Circular dependency detected involving '{name}'."
            )

        # Resolve all dependencies first
        resolved_deps: dict[str, Any] = {}
        for dep_name in dependencies:
            if dep_name not in self._registrations:
                raise ResolutionError(
                    f"Dependency '{name}' requires '{dep_name}', "
                    f"which is not registered. Available: {tuple(sorted(self._registrations.keys()))}"
                )
            resolved_deps[dep_name] = self.resolve(dep_name)

        # Call the factory with resolved dependencies
        try:
            instance = factory(**resolved_deps)
        except TypeError as exc:
            raise ResolutionError(
                f"Failed to resolve '{name}': {exc}"
            ) from exc

        self._resolved[name] = instance
        return instance

    def contains(self, name: str) -> bool:
        """Check if a dependency is registered.

        Args:
            name: The dependency name to check.

        Returns:
            True if the dependency is registered, False otherwise.

        Example
        -------

        .. code-block:: python

            if container.contains("validator"):
                print("Validator is available")
        """
        return name in self._registrations

    def all(self) -> dict[str, Any]:
        """Resolve all registered dependencies.

        Resolves all dependencies in deterministic topological order.
        Returns a dictionary mapping names to resolved instances.

        Returns:
            Dictionary mapping dependency names to instances.

        Raises:
            ResolutionError: If any dependency cannot be resolved.

        Example
        -------

        .. code-block:: python

            all_deps = container.all()
            controller = all_deps["controller"]
        """
        # Get topologically sorted names
        sorted_names = self._topological_sort()

        result: dict[str, Any] = {}
        for name in sorted_names:
            result[name] = self.resolve(name)

        return result

    def validate(self) -> list[str]:
        """Validate all registrations.

        Checks for:
        - Missing dependencies (dependencies that reference unregistered names)
        - Circular dependencies
        - Self-referencing dependencies

        Returns:
            List of validation error messages. Empty list means valid.

        Example
        -------

        .. code-block:: python

            errors = container.validate()
            if errors:
                for error in errors:
                    print(f"Error: {error}")
        """
        errors: list[str] = []

        # Check for missing dependencies
        for name, (_, dependencies) in self._registrations.items():
            for dep in dependencies:
                if dep not in self._registrations:
                    errors.append(
                        f"Dependency '{name}' requires '{dep}', "
                        f"which is not registered."
                    )

        # Check for circular dependencies
        visited: set[str] = set()
        for name in self._registrations:
            if name not in visited:
                cycle_errors = self._detect_cycles(name, set(), set())
                errors.extend(cycle_errors)
                visited.update(self._get_reachable(name))

        # Check for self-dependencies
        for name, (_, dependencies) in self._registrations.items():
            if name in dependencies:
                errors.append(
                    f"Dependency '{name}' depends on itself."
                )

        return errors

    def clear(self) -> None:
        """Clear all registrations and resolved instances.

        This is a destructive operation. Use with caution.

        Example
        -------

        .. code-block:: python

            container.clear()
            # Start fresh
        """
        self._registrations.clear()
        self._resolved.clear()

    @property
    def registered_names(self) -> tuple[str, ...]:
        """Get all registered dependency names in sorted order.

        Returns:
            Tuple of registered dependency names.

        Example
        -------

        .. code-block:: python

            names = container.registered_names
            # ('controller', 'registry', 'validator')
        """
        return tuple(sorted(self._registrations.keys()))

    @property
    def count(self) -> int:
        """Get the number of registered dependencies.

        Returns:
            Integer count of registered dependencies.
        """
        return len(self._registrations)

    # -----------------------------------------------------------------------
    # Internal methods
    # -----------------------------------------------------------------------

    def _has_cycle(
        self,
        name: str,
        visiting: set[str],
        visited: set[str],
    ) -> bool:
        """Check if a dependency graph has cycles starting from name.

        Uses DFS with three-color marking:
        - White (unvisited): not in visited or visiting
        - Gray (visiting): in visiting set
        - Black (visited): in visited set

        Args:
            name: Current dependency name.
            visiting: Set of currently visiting (gray) names.
            visited: Set of fully visited (black) names.

        Returns:
            True if a cycle is detected.
        """
        if name in visiting:
            return True
        if name in visited:
            return False

        visiting.add(name)

        if name in self._registrations:
            _, dependencies = self._registrations[name]
            for dep in dependencies:
                if self._has_cycle(dep, visiting, visited):
                    return True

        visiting.discard(name)
        visited.add(name)
        return False

    def _detect_cycles(
        self,
        start: str,
        path: set[str],
        errors: set[str],
    ) -> list[str]:
        """Detect circular dependencies using DFS.

        Args:
            start: Starting dependency name.
            path: Current DFS path.
            errors: Set to accumulate error messages.

        Returns:
            List of error messages for cycles found.
        """
        cycle_errors: list[str] = []

        if start not in self._registrations:
            return cycle_errors

        _, dependencies = self._registrations[start]

        for dep in dependencies:
            if dep in path:
                cycle_errors.append(
                    f"Circular dependency detected: {' -> '.join([dep, start])}."
                )
            elif dep in self._registrations:
                cycle_errors.extend(
                    self._detect_cycles(dep, path | {start}, errors)
                )

        return cycle_errors

    def _get_reachable(self, start: str) -> set[str]:
        """Get all reachable dependencies from start.

        Args:
            start: Starting dependency name.

        Returns:
            Set of all reachable dependency names.
        """
        reachable: set[str] = set()

        if start not in self._registrations:
            return reachable

        _, dependencies = self._registrations[start]
        for dep in dependencies:
            if dep in self._registrations:
                reachable.add(dep)
                reachable.update(self._get_reachable(dep))

        return reachable

    def _topological_sort(self) -> list[str]:
        """Sort dependencies in topological order.

        Uses Kahn's algorithm for topological sorting. Dependencies with
        no dependencies come first.

        Returns:
            List of dependency names in topological order.
        """
        # Build in-degree map
        in_degree: dict[str, int] = {name: 0 for name in self._registrations}
        adj: dict[str, list[str]] = {name: [] for name in self._registrations}

        for name, (_, dependencies) in self._registrations.items():
            for dep in dependencies:
                if dep in self._registrations:
                    adj[dep].append(name)
                    in_degree[name] = in_degree.get(name, 0) + 1

        # Start with nodes that have no dependencies
        queue = sorted([
            name for name, degree in in_degree.items() if degree == 0
        ])
        result: list[str] = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in sorted(adj[current]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            queue.sort()

        return result