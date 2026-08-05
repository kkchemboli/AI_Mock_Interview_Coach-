"""Agents package: PersonaBuilder, Interviewer, Evaluator, Prober, Coach.

Every agent exposes a `build_messages(...)` (offline-testable message builder)
and a `run(...)` that calls the LLM with strict structured outputs (except the
Coach, which emits markdown prose).
"""

from mock_interview_coach.agents.coach import run as write_coach_narrative
from mock_interview_coach.agents.evaluator import run as evaluate_answer
from mock_interview_coach.agents.interviewer import run as ask_question
from mock_interview_coach.agents.persona_builder import run as build_persona
from mock_interview_coach.agents.prober import run as generate_probe

__all__ = [
    "build_persona",
    "ask_question",
    "evaluate_answer",
    "generate_probe",
    "write_coach_narrative",
]
