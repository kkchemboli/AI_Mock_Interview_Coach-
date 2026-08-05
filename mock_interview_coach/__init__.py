"""AI Mock Interview Coach.

A multi-agent adaptive mock interview system: a dynamic persona is built for the
target role, an interviewer asks adaptive questions, every answer is scored
across five dimensions (calibrated to seniority), messy answers are triaged and
recovered with dedicated probes, and a coach delivers root-cause feedback.

Agents: PersonaBuilder, Interviewer, Evaluator, Prober, Coach.
"""

__version__ = "0.1.0"
