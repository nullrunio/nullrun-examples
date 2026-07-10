"""Enforce a CrewAI ``Crew.kickoff`` with @protect.

Once ``init_or_die`` runs, ``nullrun`` auto-installs
``step_callback`` and ``task_callback`` on every ``Crew`` the user
creates (unless they supplied their own). After ``kickoff`` returns,
``crew.usage_metrics`` is read once and the aggregated prompt /
completion tokens are emitted as a ``track_llm`` event.

``@protect`` adds the *gate* layer (budget / kill / pause);
``@guarded`` translates any ``NullRunError`` into a friendly exit.

Run:
    pip install "nullrun[crewai]" crewai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/crewai_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from crewai import Agent, Crew, Process, Task

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])


@guarded
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
        print(run_crew("What is the capital of France?"))
    finally:
        shutdown()