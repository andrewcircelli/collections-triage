"""Doing the work, and proving it was done.

A stand-in for the collections system (the AR system) lives in one JSON file
per run: runs/ar-system-<model>.json. It holds:

  invoices         each open invoice's record: are reminders on, is there a
                   promise to pay, has a payment been reported, has a
                   document been requested
  outbox           emails drafted to customers. Drafts only: nothing is sent.
  collector_queue  replies a person needs to look at, with the reason
  log              every action, in order, with the time it happened

Each run starts from a fresh copy built from data/invoices.json.

apply_action() changes the records. verify_action() reads them back and
confirms the change is really there. The screen shows a tick only for
actions verify_action() finds in the saved file.
"""

import json
from datetime import datetime
from pathlib import Path


def fresh_ar_system(invoices: list[dict]) -> dict:
    """The AR system before any reply is handled: every reminder on, nothing recorded."""
    records = {}
    for inv in invoices:
        records[inv["invoice"]] = {
            "customer": inv["customer"],
            "reminders": "on",
            "promise_to_pay": None,
            "payment_reported": None,
            "document_requested": None,
        }
    return {"invoices": records, "outbox": [], "collector_queue": [], "log": []}


def save(ar_system: dict, path: Path) -> None:
    path.write_text(json.dumps(ar_system, indent=2))


def load(path: Path) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# The five actions. Each one is a small dict, e.g.
#   {"type": "pause_reminders", "invoice": "INV-1004"}
# ---------------------------------------------------------------------------


def apply_action(ar_system: dict, reply_id: str, action: dict) -> None:
    kind = action["type"]

    if kind == "log_promise_to_pay":
        ar_system["invoices"][action["invoice"]]["promise_to_pay"] = action["date"]

    elif kind == "pause_reminders":
        ar_system["invoices"][action["invoice"]]["reminders"] = "paused"

    elif kind == "record_payment_reported":
        ar_system["invoices"][action["invoice"]]["payment_reported"] = action["reference"]

    elif kind == "request_document":
        ar_system["invoices"][action["invoice"]]["document_requested"] = action["document"]
        ar_system["outbox"].append({
            "reply": reply_id,
            "to": action["customer"],
            "subject": f"{action['document']} for {action['invoice']}",
            "status": "draft, not sent",
        })

    elif kind == "send_to_collector":
        ar_system["collector_queue"].append({
            "reply": reply_id,
            "customer": action["customer"],
            "reason": action["reason"],
        })

    else:
        raise ValueError(f"Unknown action: {kind}")

    ar_system["log"].append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "reply": reply_id,
        "action": action,
    })


def verify_action(ar_system: dict, reply_id: str, action: dict) -> bool:
    """True only if the change this action should have made is in the records."""
    kind = action["type"]

    if kind == "log_promise_to_pay":
        return ar_system["invoices"][action["invoice"]]["promise_to_pay"] == action["date"]

    if kind == "pause_reminders":
        return ar_system["invoices"][action["invoice"]]["reminders"] == "paused"

    if kind == "record_payment_reported":
        return ar_system["invoices"][action["invoice"]]["payment_reported"] == action["reference"]

    if kind == "request_document":
        recorded = ar_system["invoices"][action["invoice"]]["document_requested"] == action["document"]
        drafted = any(email["reply"] == reply_id for email in ar_system["outbox"])
        return recorded and drafted

    if kind == "send_to_collector":
        return any(item["reply"] == reply_id for item in ar_system["collector_queue"])

    return False


def describe(action: dict) -> str:
    """The action as a sentence for the screen."""
    kind = action["type"]
    if kind == "log_promise_to_pay":
        return f"Promise to pay recorded on {action['invoice']} for {action['date']}"
    if kind == "pause_reminders":
        return f"Reminders on {action['invoice']} paused"
    if kind == "record_payment_reported":
        return f"Payment {action['reference']} recorded as reported on {action['invoice']}"
    if kind == "request_document":
        return f"Email to {action['customer']} drafted: {action['document']} for {action['invoice']} (not sent)"
    if kind == "send_to_collector":
        return "Added to the collector's queue with the reason"
    return kind
