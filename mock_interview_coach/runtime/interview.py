"""Live interview runtime (M12).

`InterviewSession` wraps `ConversationState` and the agent calls behind a small
step machine that both the Streamlit app and the headless simulator drive. The
app submits human answers; the simulator submits scripted candidate answers.
Both consume the same event stream produced by every submit:

    {"type": "question", "question": {...}, "reason": str}   -> new turn, answer it
    {"type": "probe",    "probe": {...}, "stage": int}       -> answer the probe
    {"type": "end",      "reason": str}                      -> call finish()

Every decision comes from the deterministic orchestrator; the step dispatch
makes no LLM calls of its own, so the flow stays reproducible and explainable.
"""

from typing import Any, Callable

from mock_interview_coach.agents import (
    ask_question,
    build_persona,
    evaluate_answer,
    generate_probe,
    write_coach_narrative,
)
from mock_interview_coach.analysis.root_cause import coach_summary
from mock_interview_coach.orchestrator import decide
from mock_interview_coach.state.conversation_state import ConversationState, InterviewConfig

DEFAULT_AGENTS: dict[str, Callable[..., Any]] = {
    "build_persona": build_persona,
    "ask_question": ask_question,
    "evaluate_answer": evaluate_answer,
    "generate_probe": generate_probe,
    "write_coach_narrative": write_coach_narrative,
}


class InterviewSession:
    """Step-driven live interview. Create it, then `next_question()` and submit
    answers; consume the returned events to drive the UI."""

    def __init__(
        self,
        role: str,
        config: InterviewConfig,
        agents: dict[str, Callable[..., Any]] | None = None,
        config_obj: Any | None = None,
        history_limit: int = 6,
    ) -> None:
        self.role = role
        self.config = config
        self.agents = agents or DEFAULT_AGENTS
        self.config_obj = config_obj
        self.history_limit = history_limit
        self.state = ConversationState(config)
        self.decisions: list[dict[str, Any]] = []
        self._difficulty = config.difficulty
        self._active_probe: dict[str, Any] | None = None
        self._finished = False
        self._report: tuple[dict[str, Any], str] | None = None
        self.persona = self.agents["build_persona"](role, self.state, config=config_obj)
        self.state.set_persona(self.persona)
        self.state.start()

    @property
    def current_question(self) -> dict[str, Any] | None:
        turn = self.state.current_turn
        return turn.question if turn else None

    @property
    def difficulty(self) -> float:
        return self._difficulty

    @property
    def finished(self) -> bool:
        return self._finished

    def next_question(self) -> dict[str, Any]:
        """Ask the interviewer for the next question and open a new turn."""
        question_type = self.state.next_question_type()
        question = self.agents["ask_question"](
            self.role,
            self.state,
            question_type=question_type,
            difficulty=self._difficulty,
            history_limit=self.history_limit,
            config=self.config_obj,
        )
        self.state.start_turn(question)
        return question

    def submit_answer(self, answer_text: str) -> dict[str, Any]:
        """Record a top-level answer, evaluate it, and return the next event."""
        if self._finished:
            raise RuntimeError("interview already finished")
        self.state.record_answer(answer_text)
        return self._evaluate_and_dispatch()

    def submit_probe_answer(self, answer_text: str) -> dict[str, Any]:
        """Record an answer to the active probe and return the next event."""
        if self._finished:
            raise RuntimeError("interview already finished")
        if self._active_probe is None:
            raise RuntimeError("no active probe; nothing to answer")
        self.state.record_answer(answer_text, probe=self._active_probe)
        self._active_probe = None
        return self._evaluate_and_dispatch()

    def finish(self) -> tuple[dict[str, Any], str]:
        """Complete the state and produce the (deterministic summary, coach
        narrative) pair. Idempotent — the coach narrative LLM call runs once."""
        if self.state.status == "in_progress":
            self.state.complete()
        self._finished = True
        if self._report is None:
            summary = coach_summary(self.state)
            narrative = self.agents["write_coach_narrative"](
                self.role,
                self.state,
                summary=summary,
                history_limit=self.history_limit,
                config=self.config_obj,
            )
            self._report = (summary, narrative)
        return self._report

    def _evaluate_and_dispatch(self) -> dict[str, Any]:
        question = self.current_question
        last = self.state.current_turn.last_answer
        evaluation = self.agents["evaluate_answer"](
            self.role,
            self.state,
            question=question,
            answer_text=last["answer_text"],
            config=self.config_obj,
        )
        self.state.record_evaluation(evaluation)
        decision = decide(self.state)
        self.decisions.append(decision.to_dict())
        return self._dispatch(decision)

    def _dispatch(self, decision: Any) -> dict[str, Any]:
        if decision.action == "end_interview":
            self._finished = True
            return {"type": "end", "reason": decision.reason}
        if decision.action == "follow_up_probe":
            question = self.current_question
            last = self.state.current_turn.last_answer
            stage = (decision.probe_context or {}).get("escalation_stage", 0)
            probe = self.agents["generate_probe"](
                self.role,
                self.state,
                question=question,
                answer_text=last["answer_text"],
                evaluation=last["evaluation"],
                escalation_stage=stage,
                config=self.config_obj,
            )
            self._active_probe = probe
            return {"type": "probe", "probe": probe, "stage": stage}
        self._difficulty = max(1.0, min(10.0, self._difficulty + decision.difficulty_delta))
        question = self.next_question()
        return {"type": "question", "question": question, "reason": decision.reason}
