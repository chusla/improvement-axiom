"""Tests for TemporalEvaluator -- the 'long arc' of Better."""

import pytest
from datetime import datetime, timedelta

from resonance_alignment.core.temporal_evaluator import TemporalEvaluator
from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    HorizonAssessment,
    TimeHorizon,
    UserTrajectory,
    VectorSnapshot,
)


class TestArcTrend:
    """The arc trend should reflect whether 'Better' holds up over time."""

    def test_insufficient_data_returns_insufficient(self):
        evaluator = TemporalEvaluator()
        assessments = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.8),
        ]
        assert evaluator.compute_arc_trend(assessments) == "insufficient_data"

    def test_improving_arc(self):
        """Scores that rise across horizons = genuine quality."""
        evaluator = TemporalEvaluator()
        assessments = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.4),
            HorizonAssessment(horizon=TimeHorizon.SHORT_TERM, score=0.5),
            HorizonAssessment(horizon=TimeHorizon.MEDIUM_TERM, score=0.7),
        ]
        assert evaluator.compute_arc_trend(assessments) == "improving"

    def test_declining_arc(self):
        """Scores that drop across horizons = sugar hit / wireheading."""
        evaluator = TemporalEvaluator()
        assessments = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.9),
            HorizonAssessment(horizon=TimeHorizon.SHORT_TERM, score=0.6),
            HorizonAssessment(horizon=TimeHorizon.MEDIUM_TERM, score=0.3),
        ]
        assert evaluator.compute_arc_trend(assessments) == "declining"

    def test_stable_arc(self):
        """Roughly constant scores across horizons = stable."""
        evaluator = TemporalEvaluator()
        assessments = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.5),
            HorizonAssessment(horizon=TimeHorizon.SHORT_TERM, score=0.52),
            HorizonAssessment(horizon=TimeHorizon.MEDIUM_TERM, score=0.48),
        ]
        assert evaluator.compute_arc_trend(assessments) == "stable"

    def test_pending_horizons_are_skipped(self):
        """Horizons without data (score=None) should not affect the trend."""
        evaluator = TemporalEvaluator()
        assessments = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.4),
            HorizonAssessment(horizon=TimeHorizon.SHORT_TERM, score=None),
            HorizonAssessment(horizon=TimeHorizon.MEDIUM_TERM, score=0.7),
            HorizonAssessment(horizon=TimeHorizon.LONG_TERM, score=None),
        ]
        assert evaluator.compute_arc_trend(assessments) == "improving"


class TestWeightedScore:
    """Longer horizons should carry more weight."""

    def test_longer_horizons_weighted_higher(self):
        evaluator = TemporalEvaluator()

        # High immediate, low medium-term
        assessments_sugar_hit = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.9),
            HorizonAssessment(horizon=TimeHorizon.MEDIUM_TERM, score=0.2),
        ]

        # Low immediate, high medium-term
        assessments_genuine = [
            HorizonAssessment(horizon=TimeHorizon.IMMEDIATE, score=0.3),
            HorizonAssessment(horizon=TimeHorizon.MEDIUM_TERM, score=0.9),
        ]

        score_sugar = evaluator.weighted_score(assessments_sugar_hit)
        score_genuine = evaluator.weighted_score(assessments_genuine)

        # The genuine quality experience should score higher because
        # medium-term is weighted 4x more than immediate.
        assert score_genuine > score_sugar


class TestHorizonEvaluation:
    """Individual horizon evaluations."""

    def test_immediate_uses_user_rating(self):
        evaluator = TemporalEvaluator()
        exp = Experience(user_rating=0.8)
        traj = UserTrajectory()

        assessments = evaluator.evaluate(exp, traj)
        immediate = next(a for a in assessments if a.horizon == TimeHorizon.IMMEDIATE)

        assert immediate.score == 0.8

    def test_short_term_pending_without_follow_ups(self):
        evaluator = TemporalEvaluator()
        exp = Experience(user_rating=0.8)
        traj = UserTrajectory()

        assessments = evaluator.evaluate(exp, traj)
        short_term = next(a for a in assessments if a.horizon == TimeHorizon.SHORT_TERM)

        assert short_term.score is None  # pending -- no follow-up data

    def test_short_term_with_creative_follow_up(self):
        evaluator = TemporalEvaluator()
        ts = datetime.utcnow()
        exp = Experience(user_rating=0.8, timestamp=ts)
        exp.follow_ups.append(FollowUp(
            timestamp=ts + timedelta(hours=12),
            created_something=True,
            shared_or_taught=True,
            inspired_further_action=True,
        ))
        traj = UserTrajectory()

        assessments = evaluator.evaluate(exp, traj)
        short_term = next(a for a in assessments if a.horizon == TimeHorizon.SHORT_TERM)

        assert short_term.score is not None
        assert short_term.score > 0.5  # creation evidence → positive
