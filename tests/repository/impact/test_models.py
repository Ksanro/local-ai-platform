"""Tests for the impact data models.

Verifies immutability, ordering, and behavior of ImpactNode and ImpactReport.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from packages.repository.impact.models import ImpactNode, ImpactReason, ImpactReport

# ---------------------------------------------------------------------------
# ImpactNode tests
# ---------------------------------------------------------------------------


class TestImpactNode:
    """Tests for ImpactNode."""

    def test_create_node(self) -> None:
        """Verify basic ImpactNode creation."""
        node = ImpactNode(
            qualified_name="main.App",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )
        assert node.qualified_name == "main.App"
        assert node.module == "main.py"
        assert node.distance == 1
        assert node.reason == "CALLEE"

    def test_node_is_frozen(self) -> None:
        """ImpactNode should be immutable."""
        node = ImpactNode(
            qualified_name="main.App",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )
        with pytest.raises(FrozenInstanceError):
            node.qualified_name = "other"  # type: ignore[misc]

    def test_node_ordering_by_distance(self) -> None:
        """Nodes should be ordered by distance first."""
        node1 = ImpactNode(
            qualified_name="main.B",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )
        node2 = ImpactNode(
            qualified_name="main.A",
            module="main.py",
            distance=2,
            reason="CALLEE",
        )
        assert node1 < node2

    def test_node_ordering_by_qualified_name(self) -> None:
        """Nodes with same distance should be ordered by qualified_name."""
        node_a = ImpactNode(
            qualified_name="main.A",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )
        node_b = ImpactNode(
            qualified_name="main.B",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )
        assert node_a < node_b

    def test_node_ordering_equal(self) -> None:
        """Nodes with same distance and name should compare equal when all fields match."""
        node_a = ImpactNode(
            qualified_name="main.A",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )
        node_b = ImpactNode(
            qualified_name="main.A",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )
        assert node_a == node_b

    def test_node_different_reason_not_equal(self) -> None:
        """Nodes with same distance and name but different reason should NOT be equal."""
        node_a = ImpactNode(
            qualified_name="main.A",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )
        node_b = ImpactNode(
            qualified_name="main.A",
            module="main.py",
            distance=1,
            reason="CALLER",
        )
        assert node_a != node_b

    def test_all_reason_values(self) -> None:
        """Verify all valid reason values."""
        valid_reasons: list[ImpactReason] = [
            "CALLER",
            "CALLEE",
            "IMPORT",
            "DEPENDENCY",
            "INHERITANCE",
            "TEST",
        ]
        for reason in valid_reasons:
            node = ImpactNode(
                qualified_name=f"main.{reason}",
                module="main.py",
                distance=1,
                reason=reason,
            )
            assert node.reason == reason


# ---------------------------------------------------------------------------
# ImpactReport tests
# ---------------------------------------------------------------------------


class TestImpactReport:
    """Tests for ImpactReport."""

    def test_create_report(self) -> None:
        """Verify basic ImpactReport creation."""
        report = ImpactReport(
            root_symbols=("main.App",),
            impacted_symbols=(
                ImpactNode(
                    qualified_name="main.helper",
                    module="main.py",
                    distance=1,
                    reason="CALLEE",
                ),
            ),
            impacted_modules=("main.py",),
            impacted_tests=(),
            dependency_distance=1,
            confidence=0.9,
        )
        assert report.root_symbols == ("main.App",)
        assert len(report.impacted_symbols) == 1
        assert report.dependency_distance == 1
        assert report.confidence == 0.9

    def test_report_is_frozen(self) -> None:
        """ImpactReport should be immutable."""
        report = ImpactReport(
            root_symbols=("main.App",),
            impacted_symbols=(),
            impacted_modules=(),
            impacted_tests=(),
            dependency_distance=0,
            confidence=1.0,
        )
        with pytest.raises(FrozenInstanceError):
            report.root_symbols = ()  # type: ignore[misc]

    def test_report_sorts_impacted_symbols(self) -> None:
        """ImpactReport should sort impacted_symbols by (distance, qualified_name)."""
        report = ImpactReport(
            root_symbols=("main.App",),
            impacted_symbols=(
                ImpactNode(
                    qualified_name="main.Z",
                    module="main.py",
                    distance=2,
                    reason="CALLEE",
                ),
                ImpactNode(
                    qualified_name="main.A",
                    module="main.py",
                    distance=1,
                    reason="CALLEE",
                ),
                ImpactNode(
                    qualified_name="main.M",
                    module="main.py",
                    distance=1,
                    reason="CALLER",
                ),
            ),
            impacted_modules=(),
            impacted_tests=(),
            dependency_distance=2,
            confidence=0.8,
        )
        names = [n.qualified_name for n in report.impacted_symbols]
        assert names == ["main.A", "main.M", "main.Z"]

    def test_report_sorts_modules(self) -> None:
        """ImpactReport should sort impacted_modules."""
        report = ImpactReport(
            root_symbols=("main.App",),
            impacted_symbols=(),
            impacted_modules=("z.py", "a.py", "m.py"),
            impacted_tests=(),
            dependency_distance=0,
            confidence=1.0,
        )
        assert report.impacted_modules == ("a.py", "m.py", "z.py")

    def test_report_sorts_tests(self) -> None:
        """ImpactReport should sort impacted_tests."""
        report = ImpactReport(
            root_symbols=("main.App",),
            impacted_symbols=(),
            impacted_modules=(),
            impacted_tests=("tests/test_z.py", "tests/test_a.py"),
            dependency_distance=0,
            confidence=1.0,
        )
        assert report.impacted_tests == ("tests/test_a.py", "tests/test_z.py")

    def test_report_sorts_root_symbols(self) -> None:
        """ImpactReport should sort root_symbols."""
        report = ImpactReport(
            root_symbols=("main.Z", "main.A"),
            impacted_symbols=(),
            impacted_modules=(),
            impacted_tests=(),
            dependency_distance=0,
            confidence=1.0,
        )
        assert report.root_symbols == ("main.A", "main.Z")

    def test_confidence_validation(self) -> None:
        """ImpactReport should validate confidence range."""
        with pytest.raises(ValueError, match="confidence must be between"):
            ImpactReport(
                root_symbols=(),
                impacted_symbols=(),
                impacted_modules=(),
                impacted_tests=(),
                dependency_distance=0,
                confidence=1.5,
            )

        with pytest.raises(ValueError, match="confidence must be between"):
            ImpactReport(
                root_symbols=(),
                impacted_symbols=(),
                impacted_modules=(),
                impacted_tests=(),
                dependency_distance=0,
                confidence=-0.1,
            )

    def test_confidence_boundary_0(self) -> None:
        """Confidence 0.0 should be valid."""
        report = ImpactReport(
            root_symbols=(),
            impacted_symbols=(),
            impacted_modules=(),
            impacted_tests=(),
            dependency_distance=0,
            confidence=0.0,
        )
        assert report.confidence == 0.0

    def test_confidence_boundary_1(self) -> None:
        """Confidence 1.0 should be valid."""
        report = ImpactReport(
            root_symbols=(),
            impacted_symbols=(),
            impacted_modules=(),
            impacted_tests=(),
            dependency_distance=0,
            confidence=1.0,
        )
        assert report.confidence == 1.0

    def test_generated_at_timestamp(self) -> None:
        """ImpactReport should have a generated_at timestamp."""
        report = ImpactReport(
            root_symbols=(),
            impacted_symbols=(),
            impacted_modules=(),
            impacted_tests=(),
            dependency_distance=0,
            confidence=1.0,
        )
        assert report.generated_at is not None
        # Verify it parses as ISO 8601
        datetime.fromisoformat(report.generated_at)

    def test_empty_report(self) -> None:
        """Verify empty ImpactReport creation."""
        report = ImpactReport(
            root_symbols=(),
            impacted_symbols=(),
            impacted_modules=(),
            impacted_tests=(),
            dependency_distance=0,
            confidence=0.0,
        )
        assert report.root_symbols == ()
        assert report.impacted_symbols == ()
        assert report.impacted_modules == ()
        assert report.impacted_tests == ()
        assert report.dependency_distance == 0
        assert report.confidence == 0.0

    def test_report_deterministic_with_sorted_input(self) -> None:
        """Same input should produce same output ordering."""
        nodes = (
            ImpactNode(
                qualified_name="main.Z",
                module="main.py",
                distance=2,
                reason="CALLEE",
            ),
            ImpactNode(
                qualified_name="main.A",
                module="main.py",
                distance=1,
                reason="CALLEE",
            ),
        )
        report1 = ImpactReport(
            root_symbols=("main.App",),
            impacted_symbols=nodes,
            impacted_modules=("main.py", "other.py"),
            impacted_tests=(),
            dependency_distance=2,
            confidence=0.8,
        )
        report2 = ImpactReport(
            root_symbols=("main.App",),
            impacted_symbols=nodes,
            impacted_modules=("main.py", "other.py"),
            impacted_tests=(),
            dependency_distance=2,
            confidence=0.8,
        )
        assert report1.impacted_symbols == report2.impacted_symbols
        assert report1.impacted_modules == report2.impacted_modules
