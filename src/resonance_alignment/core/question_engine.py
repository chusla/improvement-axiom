"""Generates contextual follow-up questions instead of instant judgments.

At t=0 the system's job is NOT to label.  It is to *observe and ask*.
Not 'this is consumptive' but 'what happened next?' and 'what did this
lead to?' and 'did anything come out of this?'

The QuestionEngine generates questions tailored to:
  - The specific experience
  - The user's trajectory history
  - The appropriate time horizon

Answers feed back into the VectorTracker, raising confidence and
revealing the true vector over time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from resonance_alignment.core.models import (
    Experience,
    HORIZON_DURATIONS,
    PendingQuestion,
    TimeHorizon,
    UserTrajectory,
)


class QuestionEngine:
    """Generates follow-up questions at appropriate time horizons.

    Questions are gentle inquiries, not judgments.  They seek to
    understand what happened *after* the experience and whether
    the resonance propagated into creative behaviour.
    """

    def generate_questions(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
    ) -> list[PendingQuestion]:
        """Generate follow-up questions for a newly recorded experience.

        Returns questions scheduled at SHORT_TERM, MEDIUM_TERM, and
        LONG_TERM horizons.
        """
        questions: list[PendingQuestion] = []
        now = experience.timestamp

        # Short-term (1-2 days later)
        q_short = self._short_term_question(experience, trajectory)
        q_short.ask_after = now + HORIZON_DURATIONS[TimeHorizon.SHORT_TERM]
        q_short.horizon = TimeHorizon.SHORT_TERM
        questions.append(q_short)

        # Medium-term (2 weeks later)
        q_med = self._medium_term_question(experience, trajectory)
        q_med.ask_after = now + HORIZON_DURATIONS[TimeHorizon.MEDIUM_TERM]
        q_med.horizon = TimeHorizon.MEDIUM_TERM
        questions.append(q_med)

        # Long-term (3 months later)
        q_long = self._long_term_question(experience, trajectory)
        q_long.ask_after = now + HORIZON_DURATIONS[TimeHorizon.LONG_TERM]
        q_long.horizon = TimeHorizon.LONG_TERM
        questions.append(q_long)

        return questions

    def get_due_questions(
        self,
        pending: list[PendingQuestion],
        as_of: datetime | None = None,
    ) -> list[PendingQuestion]:
        """Return questions that are due to be asked."""
        now = as_of or datetime.now(timezone.utc)
        return [q for q in pending if not q.asked and q.ask_after <= now]

    # ------------------------------------------------------------------
    # Question generators (contextual, non-judgmental)
    # ------------------------------------------------------------------

    def _short_term_question(
        self, experience: Experience, trajectory: UserTrajectory
    ) -> PendingQuestion:
        """1-2 day follow-up: immediate aftermath."""
        desc = self._truncate(experience.description, 80)

        # Vary the question based on whether user has history
        if trajectory.has_history and trajectory.creation_rate > 0.3:
            # User has a pattern of creating after experiences
            question = (
                f"You mentioned '{desc}' recently. "
                f"Did it spark any new ideas or projects?"
            )
        else:
            # Neutral, open-ended
            question = (
                f"A couple of days ago you experienced '{desc}'. "
                f"Has anything come out of that -- any thoughts, ideas, "
                f"or things you've started doing differently?"
            )

        return PendingQuestion(
            experience_id=experience.id,
            user_id=experience.user_id,
            question=question,
        )

    def _medium_term_question(
        self, experience: Experience, trajectory: UserTrajectory
    ) -> PendingQuestion:
        """~2 week follow-up: pattern emergence."""
        desc = self._truncate(experience.description, 80)

        # Check if the experience was rated highly
        if experience.user_rating > 0.7:
            question = (
                f"A couple of weeks back you experienced '{desc}' "
                f"and rated it highly. Looking back, did that experience "
                f"lead to anything -- something you created, shared, or "
                f"a change in how you spend your time?"
            )
        else:
            question = (
                f"Reflecting on '{desc}' from a couple of weeks ago: "
                f"did it influence anything you've done since?  Sometimes "
                f"effects aren't obvious right away."
            )

        return PendingQuestion(
            experience_id=experience.id,
            user_id=experience.user_id,
            question=question,
        )

    def _long_term_question(
        self, experience: Experience, trajectory: UserTrajectory
    ) -> PendingQuestion:
        """~3 month follow-up: the long arc reveals itself."""
        desc = self._truncate(experience.description, 80)

        question = (
            f"A few months ago you experienced '{desc}'. "
            f"Looking back now with the benefit of time: did that "
            f"experience contribute to anything meaningful in your life?  "
            f"Any skills built, relationships deepened, or creative "
            f"output that traces back to it?"
        )

        return PendingQuestion(
            experience_id=experience.id,
            user_id=experience.user_id,
            question=question,
        )

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """Truncate text for inclusion in questions."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."
