"""JSON extraction helpers and shared constants.

Agent outputs are produced in Groq strict `json_schema` mode, so extraction only
needs a plain decode of the returned content string. `clamp_score` and
`compute_overall` are app-level math used by the evaluator/orchestrator.
"""

import json
from typing import Any

DIMENSIONS = ("substance", "structure", "relevance", "credibility", "differentiation")
QUESTION_TYPES = ("behavioral", "technical", "case")
RESPONSE_TYPES = ("substantive", "vague", "off_topic", "i_dont_know", "short")
PROBE_TYPES = ("deepen", "redirect", "scaffold", "hint")
FOCUS_AREAS = ("behavioral", "technical", "case", "mixed")
SENIORITY_BANDS = ("early", "mid", "senior", "executive")
ROOT_CAUSES = (
    "inability-to-identify-question-core",
    "reflexive-we",
    "conflict-avoidance",
    "status-anxiety",
    "narrative-hoarding",
    "fear-of-being-wrong",
)


class JSONParseError(ValueError):
    pass


def clamp_score(value: Any, low: float = 1.0, high: float = 5.0) -> float:
    try:
        return min(high, max(low, float(value)))
    except (TypeError, ValueError):
        return low


def compute_overall(dim_scores: dict) -> float:
    values = [dim_scores[d] for d in DIMENSIONS if d in dim_scores]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def extract_json(text: str) -> dict:
    data = None
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise JSONParseError(_snippet(text)) from exc
    if not isinstance(data, dict):
        raise JSONParseError(_snippet(text))
    return data


def _snippet(text: str) -> str:
    return f"Could not parse a JSON object from: {text.strip()[:120]!r}"


def structured_schema(name: str, schema: dict) -> dict:
    """Wrap a JSON Schema for Groq's strict `json_schema` mode."""
    return {"name": name, "schema": schema}


PERSONA_SCHEMA = structured_schema(
    "persona",
    {
        "type": "object",
        "properties": {
            "persona": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company_type": {"type": "string"},
                    "what_they_optimize_for": {"type": "array", "items": {"type": "string"}},
                    "vibe": {"type": "string"},
                },
                "required": ["title", "company_type", "what_they_optimize_for", "vibe"],
                "additionalProperties": False,
            },
            "scoring_lens": {"type": "string"},
            "difficulty_anchors": {
                "type": "object",
                "properties": {
                    "low": {"type": "string"},
                    "medium": {"type": "string"},
                    "high": {"type": "string"},
                },
                "required": ["low", "medium", "high"],
                "additionalProperties": False,
            },
            "topic_areas": {"type": "array", "items": {"type": "string"}},
            "edge_case_style": {"type": "string"},
        },
        "required": ["persona", "scoring_lens", "difficulty_anchors", "topic_areas", "edge_case_style"],
        "additionalProperties": False,
    },
)

QUESTION_SCHEMA = structured_schema(
    "question",
    {
        "type": "object",
        "properties": {
            "question_text": {"type": "string"},
            "question_type": {"type": "string", "enum": list(QUESTION_TYPES)},
            "expects_code": {"type": "boolean"},
            "context": {"type": "string"},
        },
        "required": ["question_text", "question_type", "expects_code", "context"],
        "additionalProperties": False,
    },
)

EVALUATION_SCHEMA = structured_schema(
    "evaluation",
    {
        "type": "object",
        "properties": {
            "dimension_scores": {
                "type": "object",
                "properties": {d: {"type": "number", "minimum": 1.0, "maximum": 5.0} for d in DIMENSIONS},
                "required": list(DIMENSIONS),
                "additionalProperties": False,
            },
            "strengths": {"type": "array", "items": {"type": "string"}},
            "gaps": {"type": "array", "items": {"type": "string"}},
            "suspected_root_cause": {"type": "string", "enum": [*ROOT_CAUSES, "none"]},
            "response_type": {"type": "string", "enum": list(RESPONSE_TYPES)},
            "interviewer_note": {"type": "string"},
        },
        "required": [
            "dimension_scores",
            "strengths",
            "gaps",
            "suspected_root_cause",
            "response_type",
            "interviewer_note",
        ],
        "additionalProperties": False,
    },
)

PROBE_SCHEMA = structured_schema(
    "probe",
    {
        "type": "object",
        "properties": {
            "probe_type": {"type": "string", "enum": list(PROBE_TYPES)},
            "target_dimension": {"type": "string", "enum": list(DIMENSIONS)},
            "question_text": {"type": "string"},
        },
        "required": ["probe_type", "target_dimension", "question_text"],
        "additionalProperties": False,
    },
)

EXEMPLAR_SCHEMA = structured_schema(
    "exemplars",
    {
        "type": "object",
        "properties": {
            "exemplars": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "turn": {"type": "integer"},
                        "question": {"type": "string"},
                        "model_answer": {"type": "string"},
                        "target_dimension": {"type": "string"},
                    },
                    "required": ["turn", "question", "model_answer", "target_dimension"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["exemplars"],
        "additionalProperties": False,
    },
)
