"""The evaluation set: 30 harder cases, with wrong calls counted in dollars.

The 4 demo replies show how it works. These 30 test how far it can be
trusted (eval/cases.json, approved by Andrew 10/10). A third of them are
aimed at the known gap: disputes worded like promises, deductions, two
invoices with the same amount.

Each model runs on all 30 cases, 5 times. Each run is the full pipeline:
the model reads the email (read.py), then the plain-code rules decide
(triage.py), using the evaluation invoices (eval/invoices.json).

Scores, all against the expected outcome in eval/cases.json:
  correct outcome   Handled or Needs a person, as expected
  false handled     Handled when it should have gone to a person. This is
                    the expensive mistake, so it is also counted in dollars:
                    the amount of the invoice it acted on.
  false escalation  sent to a person when it could have been handled.
                    Cheap: it costs a collector a few minutes.

Results go to LangSmith as one experiment per model (dataset
"collections-triage-eval"), where the two can be compared side by side,
and to eval/results.json.

Run:  python eval_cases.py      (300 model calls, under a dollar)
"""

import json
from pathlib import Path

from langsmith import Client, evaluate

from read import MODELS, read_reply
from triage import HANDLED, NEEDS_A_PERSON, triage

CASES_PATH = Path("eval/cases.json")
INVOICES_PATH = Path("eval/invoices.json")
RESULTS_PATH = Path("eval/results.json")

DATASET_NAME = "collections-triage-eval"
RECEIVED = "2026-10-06"  # every case email arrived on this date
RUNS_PER_MODEL = 5

INVOICES = json.loads(INVOICES_PATH.read_text())
CASES = json.loads(CASES_PATH.read_text())


def make_dataset(client: Client) -> None:
    """Upload the 30 cases to LangSmith once. Later runs reuse the same dataset."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        return
    client.create_dataset(dataset_name=DATASET_NAME, description="30 collections replies, expected outcome for each")
    examples = []
    for case in CASES:
        examples.append({
            "inputs": {"id": case["id"], "from": case["from"], "received": RECEIVED, "email": case["email"]},
            "outputs": {"expected": case["expected"], "group": case["group"]},
        })
    client.create_examples(dataset_name=DATASET_NAME, examples=examples)


# Every run's result, collected for eval/results.json as the experiments run.
ALL_RESULTS = []


def run_pipeline(model: str, reply: dict) -> dict:
    """One case through the whole pipeline: the model reads it, the rules decide."""
    result = read_reply(model, reply)
    status, reason, invoice = triage(reply, result["reading"], INVOICES)
    outcome = {
        "model": model,
        "id": reply["id"],
        "status": status,
        "reason": reason,
        "read_as": result["reading"]["intent"],
        "invoice": invoice["invoice"] if invoice else None,
        "amount_acted_on": invoice["amount"] if invoice else 0.0,
        "cost": result["cost"],
    }
    ALL_RESULTS.append(outcome)
    return outcome


# --- The scores. LangSmith calls each one with what the pipeline returned
# --- (outputs) and the expected answer from the dataset (reference_outputs).


def correct_outcome(outputs: dict, reference_outputs: dict) -> dict:
    return {"key": "correct_outcome", "score": int(outputs["status"] == reference_outputs["expected"])}


def false_handled(outputs: dict, reference_outputs: dict) -> dict:
    wrong = outputs["status"] == HANDLED and reference_outputs["expected"] == NEEDS_A_PERSON
    return {"key": "false_handled", "score": int(wrong)}


def dollars_at_risk(outputs: dict, reference_outputs: dict) -> dict:
    wrong = outputs["status"] == HANDLED and reference_outputs["expected"] == NEEDS_A_PERSON
    return {"key": "dollars_at_risk", "score": outputs["amount_acted_on"] if wrong else 0.0}


def false_escalation(outputs: dict, reference_outputs: dict) -> dict:
    wrong = outputs["status"] == NEEDS_A_PERSON and reference_outputs["expected"] == HANDLED
    return {"key": "false_escalation", "score": int(wrong)}


def run_haiku(inputs: dict) -> dict:
    return run_pipeline("claude-haiku-4-5", inputs)


def run_sonnet(inputs: dict) -> dict:
    return run_pipeline("claude-sonnet-5-5", inputs)


TARGETS = {"claude-haiku-4-5": run_haiku, "claude-sonnet-5-5": run_sonnet}


def summarize() -> dict:
    expected = {c["id"]: c for c in CASES}
    summary = {}
    for model in MODELS:
        rows = [r for r in ALL_RESULTS if r["model"] == model]
        correct = 0
        false_handled_rows = []
        false_escalations = 0
        for r in rows:
            want = expected[r["id"]]["expected"]
            if r["status"] == want:
                correct += 1
            elif r["status"] == HANDLED:
                false_handled_rows.append({"case": r["id"], "read_as": r["read_as"],
                                           "invoice": r["invoice"], "amount": r["amount_acted_on"],
                                           "reason": r["reason"]})
            else:
                false_escalations += 1
        cost = sum(r["cost"] for r in rows)
        summary[model] = {
            "readings": len(rows),
            "correct_outcome": correct,
            "false_handled": len(false_handled_rows),
            "false_handled_cases": sorted({f["case"] for f in false_handled_rows}),
            "dollars_at_risk": sum(f["amount"] for f in false_handled_rows),
            "false_escalations": false_escalations,
            "cost_per_reply": cost / len(rows),
            "false_handled_detail": false_handled_rows,
        }
    return summary


def main() -> None:
    client = Client()
    make_dataset(client)

    for model in MODELS:
        print(f"\nRunning {model} on {len(CASES)} cases, {RUNS_PER_MODEL} times each...")
        evaluate(
            TARGETS[model],
            data=DATASET_NAME,
            evaluators=[correct_outcome, false_handled, dollars_at_risk, false_escalation],
            experiment_prefix=model,
            num_repetitions=RUNS_PER_MODEL,
            max_concurrency=4,
            client=client,
        )

    summary = summarize()
    RESULTS_PATH.write_text(json.dumps({"summary": summary, "all_results": ALL_RESULTS}, indent=2))

    print()
    for model, s in summary.items():
        print(f"{model}: correct outcome {s['correct_outcome']} of {s['readings']} · "
              f"false handled {s['false_handled']} (cases {', '.join(s['false_handled_cases']) or 'none'}; "
              f"${s['dollars_at_risk']:,.0f} acted on wrongly) · "
              f"false escalations {s['false_escalations']} · ${s['cost_per_reply']:.4f} per reply")


if __name__ == "__main__":
    main()
