"""Coach agent: writes the markdown debrief.

The only agent that emits free-form prose (not JSON). Uses the deterministic
`summary` from analysis.root_cause as its structured input (trusted data). The
debrief must contain the four required sections; if validation (or the LLM
call) fails, the narrative is skipped (`""`) and the report shows a fallback
notice.
"""

from typing import Any

from mock_interview_coach.agents._common import (
    compact_history,
    make_agent,
)
from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.validation import sections_present

_REQUIRED_HEADERS = (
    "## What went well",
    "## The pattern",
    "## Drill",
    "## Next session",
)


def _build_context(
    role: str,
    state: ConversationState,
    *,
    summary: dict[str, Any],
    history_limit: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "trusted_task": {
            "action": "write_debrief",
            "seniority": state.config.seniority,
        },
        "trusted_summary": {
            "source": "deterministic_analysis",
            "content": summary,
        },
        "untrusted_persona": {
            "source": "persona_llm",
            "content": state.persona_for("coach"),
        },
        "untrusted_history": compact_history(
            state, include_evaluations=True, limit=history_limit
        ),
    }


def _validate(text: str, request: dict[str, Any]) -> str | None:
    return sections_present(text, _REQUIRED_HEADERS)


def _repair_hint(data: dict[str, Any], request: dict[str, Any]) -> str:
    return (
        "Your debrief was rejected because it is missing a required section. "
        "Rewrite it with exactly these four markdown headers in order: "
        + ", ".join(_REQUIRED_HEADERS)
        + "."
    )


def _fallback(request: dict[str, Any]) -> str:
    return ""


build_messages, run = make_agent(
    "coach",
    _build_context,
    temperature=0.4,
    max_tokens=2048,
    text_validator=_validate,
    repair_hint=_repair_hint,
    text_fallback=_fallback,
    on_error=_fallback,
)
