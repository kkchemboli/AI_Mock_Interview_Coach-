"""Run labelled, live LLM evaluations and write JSON + Markdown reports.

Examples:
  python scripts/run_evals.py
  python scripts/run_evals.py --model openai/gpt-oss-120b --model openai/gpt-oss-20b
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mock_interview_coach.agents import evaluate_answer
from mock_interview_coach.evals.evaluator_harness import assess_case, assess_score_order, markdown_report, summarize
from mock_interview_coach.state.conversation_state import ConversationState, DEFAULT_PERSONA, InterviewConfig
from mock_interview_coach.utils.llm import LLMConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evals" / "evaluator_cases.json"


def make_state(seniority: str) -> ConversationState:
    state = ConversationState(InterviewConfig(seniority=seniority))
    state.set_persona(DEFAULT_PERSONA)
    state.start()
    return state


def run_model(cases: list[dict], config) -> dict:
    results = []
    for case in cases:
        state = make_state(case["seniority"])
        meta: dict = {}
        evaluation = evaluate_answer(case["role"], state, question=case["question"], answer_text=case["answer"], config=config, meta=meta)
        result = assess_case(case, evaluation)
        result["provenance"] = meta
        results.append(result)
        status = "UNAVAILABLE" if meta.get("error_type") else ("PASS" if result["passed"] else "FAIL")
        print(f"{status} {config.model}: {case['id']} ({evaluation.get('overall')}, {evaluation.get('response_type')})")
    comparisons = assess_score_order(results)
    return summarize(config.model, results, comparisons)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the evaluator's labelled LLM eval suite.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--model", action="append", help="Model to evaluate; repeat to compare models.")
    parser.add_argument("--case", action="append", help="Case id to run; repeat to select a small diagnostic subset.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evals" / "reports")
    args = parser.parse_args()
    try:
        base_config = load_config()
    except LLMConfigError as exc:
        print(f"SKIP: {exc}")
        return 0
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.case:
        requested = set(args.case)
        cases = [case for case in cases if case["id"] in requested]
        unknown = requested - {case["id"] for case in cases}
        if unknown:
            parser.error("unknown case id(s): " + ", ".join(sorted(unknown)))
    models = args.model or [base_config.model]
    reports = [run_model(cases, replace(base_config, model=model)) for model in models]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "reports": reports, "config": {"models_requested": models, "fallback_model": base_config.fallback_model, "evaluator_fallback_enabled": False}}
    json_path = args.output_dir / f"evaluator_eval_{stamp}.json"
    markdown_path = args.output_dir / f"evaluator_eval_{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(reports), encoding="utf-8")
    print(f"Wrote {json_path.relative_to(ROOT)}")
    print(f"Wrote {markdown_path.relative_to(ROOT)}")
    return 0 if all(report["passed"] == report["cases"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
