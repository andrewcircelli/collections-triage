"""The repeat test: is the cheaper model good enough, and how often does it slip?

A model can read the same email differently from one run to the next, so one
run proves little. This reads the same 4 emails 5 times with each model and
saves every run. Then it scores the saved runs: each reading goes through the
same plain-code checks, and is compared with data/expected.json on three
things:

  read     did the model read the email the way it should have
           (e.g. Delta's email as a dispute)?
  outcome  did the reply get the expected outcome (Handled or Needs a person)?
  reason   was the reason exactly the expected one?

A misread with the right outcome means a check caught it. A misread with the
wrong outcome would be a model error the checks missed.

Run:  python repeat.py          read 5 times with each model (40 calls, about
                                10 cents), save the runs, then score them
      python repeat.py score    score the saved runs again, no model calls
Writes runs/repeats/<model>-run<N>.json and runs/repeats/summary.json.
"""

import json
import sys
from pathlib import Path

from read import MODELS, read_reply
from triage import triage

RUNS_PER_MODEL = 5

INVOICES_PATH = Path("data/invoices.json")
REPLIES_PATH = Path("data/replies.json")
EXPECTED_PATH = Path("data/expected.json")
REPEATS_DIR = Path("runs/repeats")


def run_path(model: str, run: int) -> Path:
    return REPEATS_DIR / f"{model}-run{run}.json"


def read_all() -> None:
    """Read every email RUNS_PER_MODEL times with each model, and save each run."""
    replies = json.loads(REPLIES_PATH.read_text())
    REPEATS_DIR.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        for run in range(1, RUNS_PER_MODEL + 1):
            print(f"reading: {model} run {run}")
            results = [read_reply(model, reply) for reply in replies]
            run_path(model, run).write_text(json.dumps(results, indent=2))


def score() -> None:
    """Put every saved reading through the checks and compare with expected.json."""
    invoices = json.loads(INVOICES_PATH.read_text())
    replies = {r["id"]: r for r in json.loads(REPLIES_PATH.read_text())}
    expected = {e["id"]: e for e in json.loads(EXPECTED_PATH.read_text())}

    summary = {}
    for model in MODELS:
        total = 0
        read_right = 0
        outcome_right = 0
        reason_right = 0
        misreads = []

        print(f"\n{model}")
        for run in range(1, RUNS_PER_MODEL + 1):
            for result in json.loads(run_path(model, run).read_text()):
                reply = replies[result["id"]]
                reading = result["reading"]
                want = expected[result["id"]]
                status, reason, _ = triage(reply, reading, invoices)

                total += 1
                if status == want["status"]:
                    outcome_right += 1
                if reason == want["reason"]:
                    reason_right += 1
                if reading["intent"] == want["intent"]:
                    read_right += 1
                else:
                    misreads.append({
                        "run": run,
                        "reply": result["id"],
                        "from": reply["from"],
                        "read_as": reading["intent"],
                        "should_be": want["intent"],
                        "outcome_still_right": status == want["status"],
                        "outcome": status,
                        "reason": reason,
                    })
                    print(f"  run {run} {result['id']}: read as {reading['intent']}, "
                          f"should be {want['intent']} -> {status}: {reason}")

        print(f"  Emails read as expected: {read_right} of {total}. "
              f"Outcome as expected: {outcome_right} of {total}. "
              f"Exact reason as expected: {reason_right} of {total}.")
        summary[model] = {
            "runs": RUNS_PER_MODEL,
            "total": total,
            "read_right": read_right,
            "outcome_right": outcome_right,
            "reason_right": reason_right,
            "misreads": misreads,
        }

    (REPEATS_DIR / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score()
    else:
        read_all()
        score()
