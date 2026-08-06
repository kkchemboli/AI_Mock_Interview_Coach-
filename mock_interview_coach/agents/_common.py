"""Shared helpers for the agent modules: prompt loading, message building, and
the `make_agent` factory that collapses each agent's message-builder + runner
into one call.

Prompt text lives in `mock_interview_coach/prompts/*.txt` so prompt engineering
is separate from code. Dynamic values always travel in the user message as a
JSON blob, keeping system prompts static (no brace-interpolation pitfalls).
"""

import json
from pathlib import Path
from typing import Any, Callable

from mock_interview_coach.state.conversation_state import ConversationState
from mock_interview_coach.utils.llm import LLMConfig, chat_json, chat_text

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8").strip()


def build_messages(system: str, context: dict[str, Any]) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(context)},
    ]


def make_agent(
    prompt_name: str,
    build_context: Callable[..., dict[str, Any]],
    *,
    schema: dict | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    postprocess: Callable[[dict], dict] | None = None,
) -> tuple[Callable[..., list[dict]], Callable[..., Any]]:
    """Build a `(build_messages, run)` pair for one agent. `build_context`
    turns (role, state, kwargs) into the user-message context dict; `schema`
    makes `run` use strict `chat_json`, otherwise it returns plain text.
    `postprocess` is applied to the parsed dict when `schema` is given."""
    system = load_prompt(prompt_name)
    pack = build_messages

    def build_messages(role: str, state: ConversationState, **kwargs: Any) -> list[dict]:
        return pack(system, build_context(role, state, **kwargs))

    def run(
        role: str,
        state: ConversationState,
        *,
        config: LLMConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        messages = build_messages(role, state, **kwargs)
        if schema is not None:
            data = chat_json(
                messages, schema=schema, config=config,
                temperature=temperature, max_tokens=max_tokens,
            )
            return postprocess(data) if postprocess is not None else data
        return chat_text(
            messages, config=config, temperature=temperature, max_tokens=max_tokens,
        )

    return build_messages, run


def compact_history(
    state: ConversationState,
    include_evaluations: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    turns = state.turns[-limit:] if limit is not None else state.turns
    entries = []
    for turn in turns:
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
