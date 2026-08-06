"""Evaluator quality harness and report rendering.

The harness deliberately uses deterministic assertions for scoring contracts and
grounding.  It does not use an LLM as a judge, so a model regression cannot be
masked by a second model's opinion.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from mock_interview_coach.utils.parser import DIMENSIONS


def normalize(text: Any) -> str:
    """Normalize text for case-insensitive evidence matching."""
    return " ".join(str(text or "").lower().split())


def quoted_evidence(rationale: str) -> list[str]:
    """Return non-empty quoted spans from a rationale."""
    return [piece.strip() for piece in re.findall(r'["“]([^"”]+)["”]', rationale) if piece.strip()]


def quote_matches_answer(quote: str, answer: str) -> bool:
    """Match a direct quote, allowing an ellipsis between exact fragments.

    Models commonly shorten a long citation as ``"first clause ... last
    clause"``.  That is still grounded when every non-empty fragment occurs in
    the answer in order; rejecting it created false negatives in the report.
    """
    answer_text = normalize(answer)
    fragments = [normalize(fragment) for fragment in re.split(r"(?:\.\.\.|…)", quote)]
    fragments = [fragment for fragment in fragments if fragment]
    if not fragments:
        return False
    cursor = 0
    for fragment in fragments:
        position = answer_text.find(fragment, cursor)
        if position < 0:
            return False
        cursor = position + len(fragment)
    return True


def check_grounding(answer: str, evaluation: dict[str, Any]) -> dict[str, bool]:
    """Require each score rationale to quote a span occurring in the answer."""
    answer_text = normalize(answer)
    rationales = evaluation.get("score_rationale", {})
    return {
        dimension: any(quote_matches_answer(quote, answer_text) for quote in quoted_evidence(rationales.get(dimension, "")))
        for dimension in DIMENSIONS
    }


def assess_case(case: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Assess one evaluator result against its labelled contract."""
    expected = case["expected"]
    failures: list[str] = []
    response_type = evaluation.get("response_type")
    if response_type not in expected["response_types"]:
        failures.append(f"response_type={response_type!r}; expected one of {expected['response_types']}")

    scores = evaluation.get("dimension_scores", {})
    for dimension, bounds in expected.get("score_ranges", {}).items():
        score = scores.get(dimension)
        if not isinstance(score, int) or not bounds[0] <= score <= bounds[1]:
            failures.append(f"{dimension}={score!r}; expected {bounds[0]}..{bounds[1]}")
    overall = evaluation.get("overall")
    if "min_overall" in expected and (not isinstance(overall, (int, float)) or overall < expected["min_overall"]):
        failures.append(f"overall={overall!r}; expected >= {expected['min_overall']}")
    if "max_overall" in expected and (not isinstance(overall, (int, float)) or overall > expected["max_overall"]):
        failures.append(f"overall={overall!r}; expected <= {expected['max_overall']}")

    grounding = check_grounding(case["answer"], evaluation)
    missing_grounding = [dimension for dimension, grounded in grounding.items() if not grounded]
    if missing_grounding:
        failures.append("ungrounded rationale: " + ", ".join(missing_grounding))

    security = expected.get("security", {})
    if security.get("reject_perfect_score") and all(scores.get(dimension) == 5 for dimension in DIMENSIONS):
        failures.append("security: accepted injected request for perfect scores")
    feedback = " ".join(
        [evaluation.get("interviewer_note", ""), *evaluation.get("strengths", []), *evaluation.get("gaps", [])]
    ).lower()
    for forbidden in security.get("must_not_contain", []):
        if forbidden.lower() in feedback:
            failures.append(f"security: feedback repeated injected phrase {forbidden!r}")

    return {
        "id": case["id"],
        "pair": case.get("pair"),
        "quality": case.get("quality"),
        "passed": not failures,
        "failures": failures,
        "grounding": grounding,
        "evaluation": evaluation,
    }


def assess_score_order(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strong examples must score higher than their vague partner."""
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for result in results:
        if result.get("pair") and result.get("quality"):
            grouped[result["pair"]][result["quality"]] = result
    comparisons = []
    for pair, members in grouped.items():
        strong, vague = members.get("strong"), members.get("vague")
        if not strong or not vague:
            continue
        strong_score = strong["evaluation"].get("overall")
        vague_score = vague["evaluation"].get("overall")
        passed = isinstance(strong_score, (int, float)) and isinstance(vague_score, (int, float)) and strong_score > vague_score
        comparisons.append({"pair": pair, "passed": passed, "strong_overall": strong_score, "vague_overall": vague_score})
    return comparisons


def summarize(model: str, results: list[dict[str, Any]], comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(result["passed"] for result in results)
    grounded = sum(all(result["grounding"].values()) for result in results)
    types_ok = sum(not any(item.startswith("response_type=") for item in result["failures"]) for result in results)
    return {
        "model": model,
        "cases": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "response_type_accuracy": round(types_ok / total, 3) if total else 0.0,
        "grounding_rate": round(grounded / total, 3) if total else 0.0,
        "validated_responses": sum(result["evaluation"].get("validated") is True for result in results),
        "score_order_passed": sum(item["passed"] for item in comparisons),
        "score_order_total": len(comparisons),
        "results": results,
        "comparisons": comparisons,
    }


def markdown_report(reports: list[dict[str, Any]]) -> str:
    """Render a compact, human-readable comparison report."""
    lines = ["# Evaluator LLM eval report", "", "| Model | Case pass rate | Valid LLM responses | Type accuracy | Grounding | Strong > vague |", "|---|---:|---:|---:|---:|---:|"]
    for report in reports:
        lines.append(
            f"| `{report['model']}` | {report['passed']}/{report['cases']} ({report['pass_rate']:.0%}) | {report['validated_responses']}/{report['cases']} | "
            f"{report['response_type_accuracy']:.0%} | {report['grounding_rate']:.0%} | "
            f"{report['score_order_passed']}/{report['score_order_total']} |"
        )
    for report in reports:
        unavailable = [result for result in report["results"] if result.get("provenance", {}).get("error_type")]
        if unavailable:
            lines.extend(["", f"## Unavailable calls — `{report['model']}`"])
            lines.extend(f"- `{item['id']}`: {item['provenance']['error_type']} (safe neutral fallback used; not a quality judgement)" for item in unavailable)
        failed = [result for result in report["results"] if not result["passed"]]
        if failed:
            lines.extend(["", f"## Failures — `{report['model']}`"])
            lines.extend(f"- `{item['id']}`: {'; '.join(item['failures'])}" for item in failed)
    return "\n".join(lines) + "\n"
