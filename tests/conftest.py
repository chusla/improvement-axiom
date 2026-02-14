"""Shared fixtures for the test suite."""

import pytest

from resonance_alignment.core.resonance_tracker import ResonanceTracker
from resonance_alignment.core.intention_classifier import IntentionClassifier
from resonance_alignment.core.quality_assessor import QualityAssessor
from resonance_alignment.core.resonance_validator import ResonanceValidator
from resonance_alignment.safety.ouroboros_anchor import OuroborosAnchor
from resonance_alignment.safety.constraints import SafetyConstraints
from resonance_alignment.system import ResonanceAlignmentSystem


@pytest.fixture
def tracker():
    return ResonanceTracker()


@pytest.fixture
def classifier():
    return IntentionClassifier()


@pytest.fixture
def assessor():
    return QualityAssessor()


@pytest.fixture
def validator():
    return ResonanceValidator()


@pytest.fixture
def anchor():
    return OuroborosAnchor()


@pytest.fixture
def constraints():
    return SafetyConstraints()


@pytest.fixture
def system():
    return ResonanceAlignmentSystem()
