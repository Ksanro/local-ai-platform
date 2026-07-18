"""Tests for the refactoring config."""

from __future__ import annotations

import pytest

from packages.advisors.refactoring.config import (
    DEFAULT_CONFIG,
    RefactoringConfig,
)


class TestDefaultConfig:
    """Tests for DEFAULT_CONFIG."""

    def test_default_config_exists(self) -> None:
        assert DEFAULT_CONFIG is not None

    def test_default_config_large_module_threshold(self) -> None:
        assert DEFAULT_CONFIG.large_module_threshold == 100

    def test_default_config_coupling_multiplier(self) -> None:
        assert DEFAULT_CONFIG.coupling_multiplier == 1.5

    def test_default_config_dependency_threshold(self) -> None:
        assert DEFAULT_CONFIG.dependency_threshold == 20

    def test_default_config_is_frozen(self) -> None:
        with pytest.raises(AttributeError):
            DEFAULT_CONFIG.large_module_threshold = 200  # pyright: ignore[reportAttributeAccessIssue]


class TestRefactoringConfig:
    """Tests for RefactoringConfig."""

    def test_config_creation(self) -> None:
        config = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        assert config.large_module_threshold == 50
        assert config.coupling_multiplier == 2.0
        assert config.dependency_threshold == 10

    def test_config_is_frozen(self) -> None:
        config = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        with pytest.raises(AttributeError):
            config.large_module_threshold = 200  # pyright: ignore[reportAttributeAccessIssue]

    def test_config_defaults(self) -> None:
        config = RefactoringConfig()
        assert config.large_module_threshold == 100
        assert config.coupling_multiplier == 1.5
        assert config.dependency_threshold == 20

    def test_config_equality(self) -> None:
        config1 = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        config2 = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        assert config1 == config2

    def test_config_inequality(self) -> None:
        config1 = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        config2 = RefactoringConfig(
            large_module_threshold=100,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        assert config1 != config2

    def test_config_hash(self) -> None:
        config1 = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        config2 = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        assert hash(config1) == hash(config2)

    def test_config_with_negative_threshold(self) -> None:
        config = RefactoringConfig(
            large_module_threshold=-1,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        assert config.large_module_threshold == -1

    def test_config_with_zero_multiplier(self) -> None:
        config = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=0.0,
            dependency_threshold=10,
        )
        assert config.coupling_multiplier == 0.0