"""Report generation (M11): Markdown + PDF export of a finished interview.

Deterministic export, no LLM calls: `report_markdown` builds the full report
from a completed ConversationState (persona, transcript with probes,
dimension scores, decisions log, root-cause summary, coach narrative), and the
PDF renderers translate that Markdown via fpdf2 so there is a single source of
truth for both formats.
"""

import re
from pathlib import Path
from typing import Any

from mock_interview_coach.analysis.root_cause import coach_summary
from mock_interview_coach.state.conversation_state import ConversationState, InterviewConfig
from mock_interview_coach.utils.parser import DIMENSIONS

_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)")
_ORDERED_RE = re.compile(r"^(\d+)\.\s+")

_SANITIZE_MAP = {
    "\u2014": "-",
    "\u2013": "-",
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "\u2026": "...",
}


def _sanitize(text: str) -> str:
    for src, dst in _SANITIZE_MAP.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def report_markdown(
    role: str,
    config: InterviewConfig,
    state: ConversationState,
    *,
    decisions: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
    narrative: str = "",
) -> str:
    """Build the full Markdown report. `summary` defaults to the deterministic
    root-cause summary; `narrative` is the Coach agent's prose (may be empty)."""
    summary = summary or coach_summary(state)
    persona = state.persona or {}
    p = persona.get("persona", {})
    parts = [
        f"# Mock Interview Report — {role}",
        "",
        f"- Interviewer: **{p.get('title', '?')}** ({p.get('company_type', '?')})",
        f"- Seniority: {config.seniority} · Focus: {config.focus} · Base difficulty: {config.difficulty}",
        f"- Status: {state.status} · Turns: {len(state.turns)}",
        f"- Optimizes for: {', '.join(p.get('what_they_optimize_for', []))}",
        f"- Vibe: {p.get('vibe', '')}",
        "",
        "## Transcript",
    ]
    for turn in state.turns:
        q = turn.question
        parts.append("")
        parts.append(
            f"### Turn {turn.turn_index} — {q.get('question_type')} (difficulty {q.get('difficulty')})"
        )
        if q.get("expects_code"):
            parts.append("*Expects code*")
        parts.append(f"**Q:** {q.get('question_text')}")
        if q.get("context"):
            parts.append(f"*Context:* {q.get('context')}")
        for answer in turn.answers:
            if answer["probe"]:
                probe = answer["probe"]
                parts.append(f"**[Probe {probe.get('probe_type')}] {probe.get('question_text')}**")
            else:
                parts.append("**A:**")
            parts.append(answer["answer_text"])
            evaluation = answer["evaluation"]
            if evaluation:
                dims = " · ".join(
                    f"{d}: {evaluation['dimension_scores'][d]:.1f}" for d in DIMENSIONS
                )
                parts.append(f"*Score {evaluation['overall']:.1f} — {evaluation.get('response_type')}*")
                parts.append(f"*{dims}*")
    parts.append("")
    parts.append("## Decisions")
    if decisions:
        for decision in decisions:
            parts.append(f"- `{decision['action']}` ({decision['reason']})")
    else:
        parts.append("- *No decision log supplied.*")
    parts.append("")
    parts.append("## Summary")
    parts.append(f"- Root cause: **{summary['root_cause']}**")
    parts.append(
        f"- Drill: **{summary['drill']['label']}** (targets {summary['drill']['target_dimension']})"
    )
    parts.append(f"- Trend: {summary['trend']} · Overall average: {summary['overall_average']}")
    parts.append("")
    parts.append("## Coach")
    parts.append(narrative or "*Coach narrative not available.*")
    return "\n".join(parts)


def report_pdf(
    role: str,
    config: InterviewConfig,
    state: ConversationState,
    *,
    decisions: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
    narrative: str = "",
    out_path: str | Path = "interview_report.pdf",
) -> Path:
    """Render the report to PDF via fpdf2 and write it to `out_path`."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(
        report_pdf_bytes(
            role, config, state, decisions=decisions, summary=summary, narrative=narrative
        )
    )
    return out_path


def report_pdf_bytes(
    role: str,
    config: InterviewConfig,
    state: ConversationState,
    *,
    decisions: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
    narrative: str = "",
) -> bytes:
    """Render the report to PDF and return the raw bytes (for in-memory
    downloads)."""
    markdown = report_markdown(
        role, config, state, decisions=decisions, summary=summary, narrative=narrative
    )
    return _render_pdf_bytes(markdown)


def _inline_segments(text: str) -> list[tuple[str, str]]:
    segments = []
    for part in _INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            segments.append((part[2:-2], "B"))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            segments.append((part[1:-1], "C"))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            segments.append((part[1:-1], "I"))
        else:
            segments.append((part, ""))
    return segments


def _render_pdf_bytes(markdown: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    def rich(text: str, size: int = 10, x_start: float | None = None) -> None:
        if x_start is not None:
            pdf.set_x(x_start)
        for seg, style in _inline_segments(text):
            family = "Courier" if style == "C" else "Helvetica"
            bold = style in ("B",)
            italic = style in ("I",)
            if family == "Courier":
                pdf.set_font("Courier", "", size - 1)
            elif bold and italic:
                pdf.set_font("Helvetica", "BI", size)
            elif bold:
                pdf.set_font("Helvetica", "B", size)
            elif italic:
                pdf.set_font("Helvetica", "I", size)
            else:
                pdf.set_font("Helvetica", "", size)
            pdf.write(5, seg)
        pdf.ln(5)

    in_code = False
    for raw in markdown.splitlines():
        line = _sanitize(raw).rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            pdf.ln(1)
            continue
        if in_code:
            pdf.set_font("Courier", "", 8.5)
            pdf.set_x(16)
            pdf.multi_cell(0, 4, line)
            continue
        stripped = line.strip()
        if not stripped:
            pdf.ln(2)
            continue
        if stripped.startswith("### "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.ln(1)
            pdf.multi_cell(0, 6, stripped[4:])
            pdf.ln(1)
            continue
        if stripped.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.ln(1)
            pdf.multi_cell(0, 7, stripped[3:])
            pdf.ln(1)
            continue
        if stripped.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 9, stripped[2:])
            pdf.ln(2)
            continue
        if stripped.startswith("> "):
            pdf.set_x(16)
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(0, 5, stripped[2:])
            pdf.ln(1)
            continue
        match = _ORDERED_RE.match(stripped)
        if stripped.startswith("- ") or stripped.startswith("* "):
            marker = stripped[0] + " "
            text = stripped[2:]
        elif match:
            marker = f"{match.group(1)}. "
            text = stripped[match.end():]
        else:
            rich(line)
            continue
        x0 = 16
        pdf.set_x(x0)
        pdf.set_font("Helvetica", "", 10)
        width = pdf.get_string_width(marker)
        pdf.write(5, marker)
        rich(text, x_start=x0 + width)

    return bytes(pdf.output(name="", dest="S"))
