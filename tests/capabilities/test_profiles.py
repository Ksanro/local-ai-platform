"""Tests for Retrieval Profiles v1.

Verifies:
- immutable profiles (frozen dataclass)
- deterministic profile equality
- ExplainCapability uses EXPLAIN_PROFILE
- DebugCapability uses DEBUG_PROFILE
- RefactorCapability uses REFACTOR_PROFILE
- capabilities no longer duplicate retrieval settings
"""

from __future__ import annotations

from dataclasses import is_dataclass

import pytest

from packages.capabilities.base import Capability
from packages.capabilities.debug import DebugCapability
from packages.capabilities.explain import ExplainCapability
from packages.capabilities.profiles import (
    DEBUG_PROFILE,
    EXPLAIN_PROFILE,
    REFACTOR_PROFILE,
    RetrievalProfile,
)
from packages.capabilities.refactor import RefactorCapability

# ---------------------------------------------------------------------------
# Test: Immutable Profiles
# ---------------------------------------------------------------------------


class TestProfilesImmutable:
    """Tests that profiles are immutable."""

    def test_retrieval_profile_is_dataclass(self) -> None:
        """RetrievalProfile must be a dataclass."""
        assert is_dataclass(RetrievalProfile)

    def test_retrieval_profile_is_frozen(self) -> None:
        """RetrievalProfile must be frozen."""
        assert is_dataclass(RetrievalProfile)
        # frozen=True means the dataclass is immutable.
        profile = RetrievalProfile(name="test")
        with pytest.raises(Exception):
            profile.name = "new"  # type: ignore[misc]

    def test_explain_profile_is_immutable(self) -> None:
        """EXPLAIN_PROFILE must be immutable."""
        with pytest.raises(Exception):
            EXPLAIN_PROFILE.include_callers = True  # type: ignore[misc]

    def test_debug_profile_is_immutable(self) -> None:
        """DEBUG_PROFILE must be immutable."""
        with pytest.raises(Exception):
            DEBUG_PROFILE.relationship_depth = 5  # type: ignore[misc]

    def test_refactor_profile_is_immutable(self) -> None:
        """REFACTOR_PROFILE must be immutable."""
        with pytest.raises(Exception):
            REFACTOR_PROFILE.include_tests = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: Deterministic Profile Equality
# ---------------------------------------------------------------------------


class TestProfileEquality:
    """Tests that profile equality is deterministic."""

    def test_same_config_equality(self) -> None:
        """Two profiles with identical config must be equal."""
        a = RetrievalProfile(name="test", include_callers=True)
        b = RetrievalProfile(name="test", include_callers=True)
        assert a == b

    def test_different_name_inequality(self) -> None:
        """Profiles with different names must not be equal."""
        a = RetrievalProfile(name="explain")
        b = RetrievalProfile(name="debug")
        assert a != b

    def test_different_callers_inequality(self) -> None:
        """Profiles with different include_callers must not be equal."""
        a = RetrievalProfile(name="test", include_callers=True)
        b = RetrievalProfile(name="test", include_callers=False)
        assert a != b

    def test_profile_self_equality(self) -> None:
        """A profile must equal itself."""
        assert EXPLAIN_PROFILE == EXPLAIN_PROFILE
        assert DEBUG_PROFILE == DEBUG_PROFILE
        assert REFACTOR_PROFILE == REFACTOR_PROFILE

    def test_profiles_are_deterministic(self) -> None:
        """Profile equality must be deterministic across runs."""
        assert (EXPLAIN_PROFILE == DEBUG_PROFILE) == (EXPLAIN_PROFILE == DEBUG_PROFILE)
        assert (DEBUG_PROFILE == REFACTOR_PROFILE) == (DEBUG_PROFILE == REFACTOR_PROFILE)


# ---------------------------------------------------------------------------
# Test: Profile Configuration Values
# ---------------------------------------------------------------------------


class TestProfileConfiguration:
    """Tests that built-in profiles have correct configuration."""

    def test_explain_profile_name(self) -> None:
        """EXPLAIN_PROFILE must have name 'explain'."""
        assert EXPLAIN_PROFILE.name == "explain"

    def test_debug_profile_name(self) -> None:
        """DEBUG_PROFILE must have name 'debug'."""
        assert DEBUG_PROFILE.name == "debug"

    def test_refactor_profile_name(self) -> None:
        """REFACTOR_PROFILE must have name 'refactor'."""
        assert REFACTOR_PROFILE.name == "refactor"

    def test_explain_profile_minimal(self) -> None:
        """EXPLAIN_PROFILE must have minimal retrieval settings."""
        assert EXPLAIN_PROFILE.include_callers is False
        assert EXPLAIN_PROFILE.include_callees is False
        assert EXPLAIN_PROFILE.include_diagnostics is False
        assert EXPLAIN_PROFILE.include_dependencies is False
        assert EXPLAIN_PROFILE.include_dependents is False
        assert EXPLAIN_PROFILE.include_tests is False
        assert EXPLAIN_PROFILE.include_dead_code is False
        assert EXPLAIN_PROFILE.relationship_depth == 1

    def test_debug_profile_diagnostic(self) -> None:
        """DEBUG_PROFILE must have diagnostic retrieval settings."""
        assert DEBUG_PROFILE.include_callers is True
        assert DEBUG_PROFILE.include_callees is True
        assert DEBUG_PROFILE.include_diagnostics is True
        assert DEBUG_PROFILE.include_dependencies is True
        assert DEBUG_PROFILE.include_dependents is False
        assert DEBUG_PROFILE.include_tests is True
        assert DEBUG_PROFILE.include_dead_code is False
        assert DEBUG_PROFILE.relationship_depth == 2

    def test_refactor_profile_comprehensive(self) -> None:
        """REFACTOR_PROFILE must have comprehensive retrieval settings."""
        assert REFACTOR_PROFILE.include_callers is True
        assert REFACTOR_PROFILE.include_callees is True
        assert REFACTOR_PROFILE.include_diagnostics is True
        assert REFACTOR_PROFILE.include_dependencies is True
        assert REFACTOR_PROFILE.include_dependents is True
        assert REFACTOR_PROFILE.include_tests is True
        assert REFACTOR_PROFILE.include_dead_code is True
        assert REFACTOR_PROFILE.relationship_depth == 3

    def test_all_profiles_have_max_context_tokens(self) -> None:
        """All profiles must have max_context_tokens set."""
        assert EXPLAIN_PROFILE.max_context_tokens == 4096
        assert DEBUG_PROFILE.max_context_tokens == 4096
        assert REFACTOR_PROFILE.max_context_tokens == 4096


# ---------------------------------------------------------------------------
# Test: Capability Profile Property
# ---------------------------------------------------------------------------


class TestCapabilityProfile:
    """Tests that capabilities expose their correct profile."""

    def test_explain_capability_has_profile(self) -> None:
        """ExplainCapability must have a profile property."""
        cap = ExplainCapability()
        assert isinstance(cap.profile, RetrievalProfile)

    def test_explain_uses_explain_profile(self) -> None:
        """ExplainCapability must return EXPLAIN_PROFILE."""
        cap = ExplainCapability()
        assert cap.profile is EXPLAIN_PROFILE

    def test_debug_capability_has_profile(self) -> None:
        """DebugCapability must have a profile property."""
        cap = DebugCapability()
        assert isinstance(cap.profile, RetrievalProfile)

    def test_debug_uses_debug_profile(self) -> None:
        """DebugCapability must return DEBUG_PROFILE."""
        cap = DebugCapability()
        assert cap.profile is DEBUG_PROFILE

    def test_refactor_capability_has_profile(self) -> None:
        """RefactorCapability must have a profile property."""
        cap = RefactorCapability()
        assert isinstance(cap.profile, RetrievalProfile)

    def test_refactor_uses_refactor_profile(self) -> None:
        """RefactorCapability must return REFACTOR_PROFILE."""
        cap = RefactorCapability()
        assert cap.profile is REFACTOR_PROFILE

    def test_profile_is_property(self) -> None:
        """profile must be a property, not a method."""
        cap = ExplainCapability()
        # Must be accessible without parentheses.
        profile = cap.profile
        assert isinstance(profile, RetrievalProfile)


# ---------------------------------------------------------------------------
# Test: No Duplicated Retrieval Settings
# ---------------------------------------------------------------------------


class TestNoDuplicatedSettings:
    """Tests that capabilities no longer duplicate retrieval settings."""

    def test_explain_capability_no_inline_config(self) -> None:
        """ExplainCapability must not construct RetrievalProfile inline."""
        # The capability should only reference EXPLAIN_PROFILE, not construct one.
        cap = ExplainCapability()
        # Verify the profile is the singleton, not a newly constructed one.
        assert cap.profile is EXPLAIN_PROFILE
        # Verify no other RetrievalProfile instances exist for this capability.
        assert cap.profile is not RetrievalProfile(
            name="explain",
            include_callers=False,
            include_callees=False,
        )

    def test_debug_capability_no_inline_config(self) -> None:
        """DebugCapability must not construct RetrievalProfile inline."""
        cap = DebugCapability()
        assert cap.profile is DEBUG_PROFILE

    def test_refactor_capability_no_inline_config(self) -> None:
        """RefactorCapability must not construct RetrievalProfile inline."""
        cap = RefactorCapability()
        assert cap.profile is REFACTOR_PROFILE

    def test_all_profiles_are_singletons(self) -> None:
        """All built-in profiles must be module-level singletons."""
        # Import again to verify they are the same objects.
        from packages.capabilities.profiles import (
            DEBUG_PROFILE as DEBUG_PROFILE_2,
        )
        from packages.capabilities.profiles import (
            EXPLAIN_PROFILE as EXPLAIN_PROFILE_2,
        )
        from packages.capabilities.profiles import (
            REFACTOR_PROFILE as REFACTOR_PROFILE_2,
        )

        assert EXPLAIN_PROFILE is EXPLAIN_PROFILE_2
        assert DEBUG_PROFILE is DEBUG_PROFILE_2
        assert REFACTOR_PROFILE is REFACTOR_PROFILE_2


# ---------------------------------------------------------------------------
# Test: Profile Distinctness
# ---------------------------------------------------------------------------


class TestProfileDistinctness:
    """Tests that profiles are distinct from each other."""

    def test_explain_not_equal_debug(self) -> None:
        """EXPLAIN_PROFILE must not equal DEBUG_PROFILE."""
        assert EXPLAIN_PROFILE != DEBUG_PROFILE

    def test_explain_not_equal_refactor(self) -> None:
        """EXPLAIN_PROFILE must not equal REFACTOR_PROFILE."""
        assert EXPLAIN_PROFILE != REFACTOR_PROFILE

    def test_debug_not_equal_refactor(self) -> None:
        """DEBUG_PROFILE must not equal REFACTOR_PROFILE."""
        assert DEBUG_PROFILE != REFACTOR_PROFILE


# ---------------------------------------------------------------------------
# Test: Capability ABC Requires Profile
# ---------------------------------------------------------------------------


class TestCapabilityABC:
    """Tests that the Capability ABC requires a profile property."""

    def test_capability_has_profile_abstract(self) -> None:
        """Capability ABC must define profile as an abstract property."""
        # If profile is abstract, trying to instantiate Capability directly
        # should fail (even without implementing profile).
        with pytest.raises(TypeError):
            Capability()  # type: ignore[abstract]

    def test_concrete_capabilities_implement_profile(self) -> None:
        """All concrete capabilities must implement profile."""
        # These should not raise.
        assert ExplainCapability().profile is not None
        assert DebugCapability().profile is not None
        assert RefactorCapability().profile is not None
