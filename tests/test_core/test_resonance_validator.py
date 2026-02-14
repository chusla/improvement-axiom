"""Tests for ResonanceValidator -- multi-timescale validation."""

from resonance_alignment.core.resonance_validator import ResonanceValidator
from resonance_alignment.core.models import (
    Experience,
    HorizonAssessment,
    TimeHorizon,
    UserTrajectory,
)


class TestResonanceValidator:
    """Test the updated validator with temporal arc + propagation awareness."""

    def test_validate_normal_score(self, validator):
        """With no trajectory or horizon data, score should pass through."""
        score = validator.validate_resonance(0.6, {"user_history": []})
        assert isinstance(score, float)
        assert 0.5 <= score <= 0.7  # may get minor adjustments

    def test_validate_penalizes_high_dependency(self):
        """High dependency risk should heavily penalise the score."""
        validator = ResonanceValidator()
        exp = Experience(resonance_score=0.8)
        traj = UserTrajectory()

        # Mock dependency detection to return high risk
        validator._assess_dependency = lambda t: 0.9
        score = validator.validate(exp, traj)
        assert score < 0.4  # heavy penalty

    def test_declining_arc_penalises(self):
        """If scores drop across horizons (sugar hit), resonance is discounted."""
        validator = ResonanceValidator()
        exp = Experience(resonance_score=0.8)
        traj = UserTrajectory()

        # High immediate, low medium-term → sugar hit
        assessments = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.9),
            HorizonAssessment(horizon=TimeHorizon.MEDIUM_TERM, score=0.3),
        ]
        score = validator.validate(exp, traj, assessments)
        assert score < 0.8

    def test_improving_arc_boosts(self):
        """If scores improve across horizons (genuine quality), slight boost."""
        validator = ResonanceValidator()
        exp = Experience(resonance_score=0.6)
        traj = UserTrajectory()

        assessments = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.3),
            HorizonAssessment(horizon=TimeHorizon.MEDIUM_TERM, score=0.7),
        ]
        score = validator.validate(exp, traj, assessments)
        assert score >= 0.6  # should get a small boost

    def test_low_propagation_rate_discounts(self):
        """A user whose resonance never propagates should be discounted."""
        validator = ResonanceValidator()
        exp = Experience(resonance_score=0.8)
        traj = UserTrajectory(
            propagation_rate=0.05,
            experiences=[Experience() for _ in range(5)],
        )

        score = validator.validate(exp, traj)
        assert score < 0.8

    def test_high_propagation_rate_trusts(self):
        """A user whose resonance consistently propagates should be trusted."""
        validator = ResonanceValidator()
        exp = Experience(resonance_score=0.6)
        traj = UserTrajectory(
            propagation_rate=0.7,
            experiences=[Experience() for _ in range(5)],
        )

        score = validator.validate(exp, traj)
        assert score >= 0.6
