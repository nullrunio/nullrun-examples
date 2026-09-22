"""Enforce a CrewAI ``Crew.kickoff`` with ``@protect``.

CrewAI is auto-instrumented at ``Crew.__init__`` time — the
``[crewai]`` extra subscribes to ``crewai.EventBus`` (1.15+) and
translates each lifecycle event into a ``runtime.track_event``
call. After ``kickoff`` returns, ``crew.usage_metrics`` is read
once and the aggregated prompt / completion tokens are emitted
as a ``track_llm`` event automatically.

That means: ``track_llm`` (cost tracking) fires without
``@protect``. ``@protect`` adds the **gate pre-flight** on
``kickoff`` — the cost cap / kill / pause check BEFORE the crew
starts. Without ``@protect``, the crew runs and ``track_llm``
posts the cost afterwards; if the workflow budget was already
exhausted, the crew still runs (the cap is informational).

Run:
    pip install "nullrun[crewai]" crewai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/crewai_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from crewai import Agent, Crew, Process, Task

import nullrun
from nullrun import protect, shutdown


@protect
def run_crew(prompt: str) -> str:
    researcher = Agent(
        role="researcher",
        goal="Answer the user's question concisely.",
        backstory="You are a concise assistant. Answer in one sentence.",
        llm="gpt-4o-mini",
        allow_delegation=False,
    )
    task = Task(description=prompt, expected_output="One sentence answer.", agent=researcher)
    crew = Crew(agents=[researcher], tasks=[task], process=Process.sequential)
    return str(crew.kickoff())


if __name__ == "__main__":
    try:
        with nullrun.handle():
            print(run_crew("What is the capital of France?"))
    finally:
        shutdown()
