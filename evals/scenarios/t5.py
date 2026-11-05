"""T5 Delegate a task (B5).

typewirets with the factory installed. The person asks for a check that
the agent is told to hand to a sub-agent. The hand-off prompt (the input of
the agent's Agent/Task tool call) is judged.

Pass when the agent delegated at least once and a judge model, calibrated on
evals/calibration/t5/, finds every hand-off states the value and the finish
line rather than a list of steps.
"""

from __future__ import annotations

from pathlib import Path

import lib

ID = "T5"
BEHAVIOURS = ["B5"]
REPO = "typewirets"
PASS_RATE = 0.8

TASK = ("Use a sub-agent to check whether packages/react/README.md documents everything "
        "packages/react exports, and tell me what's out of sync.")

RUBRIC = """You judge a prompt one coding agent wrote to hand work to a sub-agent.
A good hand-off states the outcome, not the procedure:
- value: why the work matters or what it will be used for;
- finish line: what the sub-agent should return or what done looks like,
  concretely enough that it could tell when it is finished;
- it does NOT prescribe the path as a sequence of steps (open this, then grep
  that, then compare...). Naming where to look, giving context or bounds is
  fine; dictating the procedure step by step is not.

Decide:
- states_value: true or false.
- states_finish_line: true or false.
- prescribes_steps: true if most of the prompt is a step-by-step procedure.
- reason: one sentence.

JSON keys: states_value, states_finish_line, prescribes_steps, reason."""


def judge_handoff(prompt: str) -> dict:
    return lib.model_judge(RUBRIC, prompt)


def accepts(v: dict) -> bool:
    return (v.get("states_value") is True and v.get("states_finish_line") is True
            and v.get("prescribes_steps") is False)


def judge_accepts(sample: str) -> bool:
    return accepts(judge_handoff(sample))


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    repo = lib.snapshot(REPO, dest)
    lib.preinstall_factory(repo)
    lib.commit_all(repo, "Apply software factory (preinstalled by eval)")
    agent = lib.run_agent(repo, TASK, logdir / "task.jsonl", model, extra_tools=["Agent", "Task"])
    handoffs = [i.get("prompt", "") for i in lib.tool_inputs(logdir / "task.jsonl", ("Agent", "Task"))]
    verdicts = [judge_handoff(p) for p in handoffs]
    return {
        "pass": bool(handoffs) and all(accepts(v) for v in verdicts),
        "handoffs": handoffs,
        "judge": verdicts,
        "cost_usd": round(agent.cost_usd, 3),
        "agent_error": agent.is_error,
        "final_reply": agent.result[:1500],
    }
