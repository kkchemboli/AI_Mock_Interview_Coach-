"""AI Mock Interview Coach — Streamlit app (M12).

Live interview driven by the runtime `InterviewSession`: persona presets, probe
follow-ups, a monospace editor for code questions, and a final Markdown + PDF
report with download buttons.

Run:  streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_interview_coach.runtime.interview import InterviewSession
from mock_interview_coach.state.conversation_state import InterviewConfig
from mock_interview_coach.utils.parser import FOCUS_AREAS, SENIORITY_BANDS
from mock_interview_coach.utils.report import report_markdown, report_pdf_bytes

from scripts.personas import find_preset, preset_labels

PRESET_LABELS = ["Custom"] + preset_labels()

_ERROR_PREFIX = "The interview agent hit an error (rate limit?)"


def _init_state() -> None:
    st.session_state.setdefault("session", None)
    st.session_state.setdefault("phase", "setup")  # setup | question | probe | done
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("report", None)
    st.session_state.setdefault("error", None)


def _append(role: str, text: str) -> None:
    st.session_state.messages.append({"role": role, "text": text})


def _format_question(q: dict) -> str:
    parts = []
    if q.get("expects_code"):
        parts.append("*This question expects code.*")
    parts.append(str(q.get("question_text", "")))
    if q.get("context"):
        parts.extend(["", f"*Context:* {q['context']}"])
    return "\n\n".join(parts)


def _start(role: str, seniority: str, focus: str, difficulty: float) -> None:
    config = InterviewConfig(seniority=seniority, focus=focus, difficulty=difficulty)
    session = InterviewSession(role, config)
    st.session_state.session = session
    question = session.next_question()
    st.session_state.messages = [{"role": "assistant", "text": _format_question(question)}]
    st.session_state.phase = "question"
    st.session_state.report = None
    st.session_state.error = None


def _submit_response(text: str) -> None:
    _append("user", text)
    session = st.session_state.session
    try:
        if st.session_state.phase == "probe":
            event = session.submit_probe_answer(text)
        else:
            event = session.submit_answer(text)
    except Exception as exc:  # noqa: BLE001
        st.session_state.error = f"{_ERROR_PREFIX}: {exc}"
        st.rerun()
    st.session_state.error = None
    _consume_event(event)


def _consume_event(event: dict) -> None:
    if event["type"] == "probe":
        st.session_state.phase = "probe"
        _append("assistant", str(event["probe"].get("question_text")))
    elif event["type"] == "question":
        st.session_state.phase = "question"
        _append("assistant", _format_question(event["question"]))
    else:
        st.session_state.phase = "done"
        _append("assistant", "The interview has ended — generating your report.")


def _ensure_report() -> dict:
    if st.session_state.report is None:
        session = st.session_state.session
        summary, narrative = session.finish()
        markdown = report_markdown(
            session.role, session.config, session.state,
            decisions=session.decisions, summary=summary, narrative=narrative,
        )
        pdf = report_pdf_bytes(
            session.role, session.config, session.state,
            decisions=session.decisions, summary=summary, narrative=narrative,
        )
        st.session_state.report = {
            "markdown": markdown,
            "pdf": pdf,
            "summary": summary,
            "narrative": narrative,
        }
    return st.session_state.report


def _reset() -> None:
    for key in ("session", "phase", "messages", "report", "error"):
        st.session_state.pop(key, None)
    st.rerun()


def _render_sidebar() -> None:
    st.sidebar.header("Setup")
    session = st.session_state.session
    if session is None:
        preset_label = st.sidebar.selectbox("Preset", PRESET_LABELS, index=0)
        locked = preset_label != "Custom"
        if locked:
            preset = find_preset(preset_label)
            role = st.sidebar.text_input("Role", preset["role"], disabled=True)
            seniority = st.sidebar.selectbox(
                "Seniority", SENIORITY_BANDS, index=SENIORITY_BANDS.index(preset["seniority"]),
                disabled=True,
            )
            focus = st.sidebar.selectbox(
                "Focus", FOCUS_AREAS, index=FOCUS_AREAS.index(preset["focus"]), disabled=True,
            )
            difficulty = preset["difficulty"]
            st.sidebar.info(
                f"{preset['role']} · {preset['seniority']}/{preset['focus']} · {preset['difficulty']}"
            )
        else:
            role = st.sidebar.text_input("Role", "Backend Engineer")
            seniority = st.sidebar.selectbox("Seniority", SENIORITY_BANDS, index=1)
            focus = st.sidebar.selectbox("Focus", FOCUS_AREAS, index=3)
            difficulty = 5.0
        if st.sidebar.button(
            "Start interview", type="primary", icon=":material/play_arrow:",
            width="stretch",
        ):
            try:
                _start(role, seniority, focus, difficulty)
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.sidebar.error(f"Could not start: {exc}")
    else:
        state = session.state
        st.sidebar.write(f"**{session.role}**")
        st.sidebar.caption(f"status {state.status} · turn {len(state.turns)}/{state.config.max_turns}")
        if st.sidebar.button(
            "End early", icon=":material/stop:", width="stretch",
        ):
            _ensure_report()
            st.session_state.phase = "done"
            st.rerun()
        if st.sidebar.button(
            "New interview", icon=":material/refresh:", width="stretch",
        ):
            _reset()


def _render_input() -> None:
    session = st.session_state.session
    if st.session_state.phase not in ("question", "probe") or session is None:
        return
    expects_code = bool(session.current_question and session.current_question.get("expects_code"))
    try:
        if expects_code:
            turn_index = session.state.current_turn.turn_index
            with st.form(f"answer_{turn_index}", clear_on_submit=True):
                text = st.text_area(
                    "Your answer (code)", height=220, key=f"code_{turn_index}",
                    placeholder="Write your full answer here, including any code.",
                )
                submitted = st.form_submit_button(
                    "Submit answer", type="primary", icon=":material/send:", width="stretch",
                )
            if submitted and text.strip():
                with st.spinner("Buffering the next question…"):
                    _submit_response(text.strip())
                st.rerun()
        else:
            text = st.chat_input("Type your answer…", submit_mode="disable")
            if text:
                with st.spinner("Buffering the next question…"):
                    _submit_response(text)
                st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"{_ERROR_PREFIX}: {exc}")


def _render_done() -> None:
    if st.session_state.phase != "done" or st.session_state.report is None:
        return
    report = st.session_state.report
    summary = report["summary"]
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Overall average", f"{summary['overall_average']:.1f}")
        c2.metric("Trend", summary["trend"])
        c3.metric("Root cause", summary["root_cause"])
    st.markdown(report["markdown"])
    st.download_button(
        "Download Markdown", report["markdown"],
        file_name="interview_report.md", mime="text/markdown",
        icon=":material/description:",
    )
    st.download_button(
        "Download PDF", report["pdf"],
        file_name="interview_report.pdf", mime="application/pdf",
        icon=":material/picture_as_pdf:",
    )


def main() -> None:
    st.set_page_config(page_title="AI Mock Interview Coach", layout="wide")
    _init_state()
    _render_sidebar()
    st.title("AI Mock Interview Coach")
    if st.session_state.session is None:
        st.write(
            "Configure the interview on the left and hit **Start interview**. "
            "Answer the interviewer turn by turn; follow-up probes will appear "
            "when an answer needs more substance. A report (Markdown + PDF) is "
            "generated at the end."
        )
        return
    for msg in st.session_state.messages:
        with st.chat_message(
            msg["role"],
            avatar=":material/record_voice_over:" if msg["role"] == "assistant" else None,
        ):
            st.markdown(msg["text"])
    if st.session_state.error:
        st.error(st.session_state.error)
    _render_input()
    _render_done()


if __name__ == "__main__":
    main()
