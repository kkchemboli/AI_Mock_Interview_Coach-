"""Preset interview personas for the simulator and the Streamlit app (M9).

Each preset is a ready-made combination of role, seniority band, focus area and
base difficulty. The PersonaBuilder still generates the full interviewer persona
at runtime — these presets only pin the inputs.
"""

from mock_interview_coach.utils.parser import FOCUS_AREAS, SENIORITY_BANDS

PRESETS: list[dict] = [
    {
        "label": "Backend Engineer — Mid — Mixed",
        "role": "Backend Engineer",
        "seniority": "mid",
        "focus": "mixed",
        "difficulty": 5.0,
    },
    {
        "label": "Senior Backend Engineer — Senior — Technical",
        "role": "Senior Backend Engineer",
        "seniority": "senior",
        "focus": "technical",
        "difficulty": 6.0,
    },
    {
        "label": "Frontend Engineer — Early — Behavioral",
        "role": "Frontend Engineer",
        "seniority": "early",
        "focus": "behavioral",
        "difficulty": 4.0,
    },
    {
        "label": "Data Scientist — Senior — Mixed",
        "role": "Data Scientist",
        "seniority": "senior",
        "focus": "mixed",
        "difficulty": 6.0,
    },
    {
        "label": "Product Manager — Mid — Case",
        "role": "Product Manager",
        "seniority": "mid",
        "focus": "case",
        "difficulty": 5.5,
    },
    {
        "label": "Engineering Manager — Executive — Mixed",
        "role": "Engineering Manager",
        "seniority": "executive",
        "focus": "mixed",
        "difficulty": 7.0,
    },
]


def find_preset(selector: str | int) -> dict:
    if isinstance(selector, int):
        return PRESETS[selector]
    for preset in PRESETS:
        if preset["label"] == selector:
            return preset
    raise KeyError(f"no preset matching {selector!r}; choose from {preset_labels()}")


def preset_labels() -> list[str]:
    return [preset["label"] for preset in PRESETS]


def _validate() -> None:
    labels = set()
    for preset in PRESETS:
        assert preset["seniority"] in SENIORITY_BANDS, preset
        assert preset["focus"] in FOCUS_AREAS, preset
        assert 1.0 <= preset["difficulty"] <= 10.0, preset
        assert preset["role"] and preset["label"], preset
        assert preset["label"] not in labels, preset
        labels.add(preset["label"])


_validate()
