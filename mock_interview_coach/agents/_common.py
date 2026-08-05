"""Shared helpers for the agent modules: prompt loading and message building.

Prompt text lives in `mock_interview_coach/prompts/*.txt` so prompt engineering
is separate from code. Dynamic values always travel in the user message as a
JSON blob, keeping system prompts static (no brace-interpolation pitfalls).
"""

import json
from pathlib import Path
from typing import Any

from mock_interview_coach.state.conversation_state import ConversationState

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8").strip()


def build_messages(system: str, context: dict[str, Any]) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(context)},
    ]


def compact_history(
    state: ConversationState,
    include_evaluations: bool = False,
) -> list[dict[str, Any]]:
    entries = []
    for turn in state.turns:
        entry = {
            "turn": turn.turn_index,
            "question_type": turn.question.get("question_type"),
            "question": turn.question.get("question_text"),
            "answers": [],
        }
        for answer in turn.answers:
            item: dict[str, Any] = {"answer": answer["answer_text"]}
            if answer["probe"]:
                item["probe"] = answer["probe"].get("question_text")
            evaluation = answer["evaluation"]
            if include_evaluations and evaluation:
                item["overall"] = evaluation.get("overall")
                item["response_type"] = evaluation.get("response_type")
            entry["answers"].append(item)
        entries.append(entry)
    return entries


def recent_evaluations(state: ConversationState, limit: int = 3) -> list[dict[str, Any]]:
    out = []
    for turn in state.turns:
        for answer in turn.answers:
            evaluation = answer["evaluation"]
            if evaluation:
                out.append(
                    {
                        "overall": evaluation.get("overall"),
                        "response_type": evaluation.get("response_type"),
                        "gaps": evaluation.get("gaps"),
                    }
                )
    return out[-limit:]
