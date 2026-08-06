# Evaluator LLM evals

`evaluator_cases.json` is a small, hand-labelled golden set for the answer
evaluator.  It measures the product contracts that unit tests cannot verify:

- A strong answer scores higher than its matched vague answer.
- `off_topic` and `i_dont_know` answers are classified correctly.
- Each dimension rationale contains an exact quotation from the candidate
  answer, rather than invented evidence.
- An instruction embedded in a candidate answer does not earn perfect scores
  or leak into candidate-facing feedback.

These cases are deliberately held out from the evaluator prompt's calibration
examples. Do not copy prompt examples into this file: that would measure
example recall rather than generalization.

Run the configured model:

```bash
.venv/bin/python scripts/run_evals.py
```

Compare model candidates (including the configured fallback) directly:

```bash
.venv/bin/python scripts/run_evals.py \
  --model openai/gpt-oss-120b \
  --model openai/gpt-oss-20b
```

The runner writes timestamped JSON (machine-readable details) and Markdown
(human-readable summary) files under `evals/reports/`.  It exits non-zero if a
model fails any labelled case, making it suitable for a separate, API-keyed CI
job.  Keep this separate from the offline test suite, as it calls Groq and
model output can legitimately need human review.

The evaluator intentionally has fallback disabled in production to preserve
score consistency.  To decide whether a fallback model is acceptable, run it
as a separate `--model` candidate and compare its pass rate, response-type
accuracy, grounding rate, and strong-versus-vague ordering against the primary
model.
