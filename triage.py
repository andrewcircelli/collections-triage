"""Steps 2 to 4, FIND, CHECK and ROUTE: plain code, no model.

Takes what the model read from each reply (runs/readings-<model>.json),
finds the invoice, checks every fact the customer mentioned against the
invoice records, and gives each reply one of two outcomes:

  Handled         a routine reply where every check passed. The next step
                  is written out. Nothing is sent.
  Needs a person  anything else, with the reason.

Then it compares every outcome with data/expected.json, which was written
before this code ran.

Then it does the work in a stand-in AR system (see actions.py), reads the
saved records back, and confirms every action is really there.

Run:  python triage.py
Writes runs/triage-<model>.json and runs/ar-system-<model>.json for each model.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from actions import apply_action, describe, fresh_ar_system, load, save, verify_action

INVOICES_PATH = Path("data/invoices.json")
REPLIES_PATH = Path("data/replies.json")
EXPECTED_PATH = Path("data/expected.json")
RUNS_DIR = Path("runs")

MODELS = ["claude-haiku-4-5", "claude-sonnet-5-5"]

HANDLED = "Handled"
NEEDS_A_PERSON = "Needs a person"

# A promised payment date further out than this goes to a person.
MAX_PROMISE_DAYS = 30

# Documents we can send without a person looking. A "corrected invoice"
# is not on this list: asking for one means they disagree with the bill.
ROUTINE_DOCUMENTS = ["new PO", "W-9", "invoice copy"]


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def short_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"  # e.g. "Oct 30"


# ---------------------------------------------------------------------------
# Step 2, FIND: which invoice is the customer talking about?
# Returns (invoice, None) if found, or (None, reason) if not.
# ---------------------------------------------------------------------------


def find_invoice(customer: str, invoice_number: str | None, invoices: list[dict]):
    customers_invoices = [inv for inv in invoices if inv["customer"] == customer]
    open_numbers = " and ".join(inv["invoice"] for inv in customers_invoices)

    if invoice_number:
        for inv in customers_invoices:
            if inv["invoice"] == invoice_number:
                return inv, None
        if len(customers_invoices) == 1:
            return None, f"No invoice {invoice_number} on {customer}'s account. Their open invoice is {open_numbers}."
        return None, f"No invoice {invoice_number} on {customer}'s account. Their open invoices are {open_numbers}."

    # No invoice number in the reply: only safe if they have exactly one.
    if len(customers_invoices) == 1:
        return customers_invoices[0], None
    if len(customers_invoices) == 0:
        return None, f"No open invoices on {customer}'s account"
    return None, f"No invoice number given, and {customer} has {len(customers_invoices)} open invoices"


# ---------------------------------------------------------------------------
# Step 3, CHECK: every fact the customer mentioned, against the invoice.
# Each check returns None if it passes, or the reason if it fails.
# ---------------------------------------------------------------------------


def check_amount(reading: dict, invoice: dict) -> str | None:
    amount = reading["amount"]
    if amount is None:
        return None  # they didn't mention one, so there's nothing to check
    if abs(amount - invoice["amount"]) > 0.005:
        return f"Customer says they paid {money(amount)}, but {invoice['invoice']} is for {money(invoice['amount'])}"
    return None


def check_promised_date(reading: dict, received: date) -> str | None:
    if reading["promised_date"] is None:
        return "Promises to pay but gives no date"
    try:
        promised = date.fromisoformat(reading["promised_date"])
    except ValueError:
        return f"Promised date {reading['promised_date']} isn't a real date"
    if promised < received:
        return f"Promised date {short_date(promised)} is before the email arrived"
    if promised > received + timedelta(days=MAX_PROMISE_DAYS):
        return f"Promised date {short_date(promised)} is more than {MAX_PROMISE_DAYS} days out"
    return None


def check_document(reading: dict) -> str | None:
    document = reading["document_needed"]
    if document in ROUTINE_DOCUMENTS:
        return None
    if document == "corrected invoice":
        return "Asks for a corrected invoice, which means they disagree with the bill"
    return "Asks for a document we don't send automatically"


# ---------------------------------------------------------------------------
# Step 4, ROUTE: put it together. The first thing that fails is the reason.
# ---------------------------------------------------------------------------


def next_step(reading: dict, invoice: dict, customer: str) -> str:
    intent = reading["intent"]
    number = invoice["invoice"]

    if intent == "will_pay":
        promised = date.fromisoformat(reading["promised_date"])
        return f"Promise to pay logged for {short_date(promised)}"

    if intent == "paid":
        if reading["reference"]:
            return f"Payment logged as sent ({reading['reference']}); pause reminders on {number} until it arrives"
        return f"Payment logged as sent; pause reminders on {number} until it arrives"

    # intent == "needs_document"
    document = reading["document_needed"]
    if document == "new PO":
        return f"Request a new PO from {customer}; pause reminders on {number}"
    if document == "W-9":
        return f"Send a W-9 to {customer}; pause reminders on {number}"
    return f"Send a copy of {number} to {customer}"


def triage(reply: dict, reading: dict, invoices: list[dict]):
    """Returns (status, reason, invoice). The invoice is None if none was found."""
    customer = reply["from"]
    received = date.fromisoformat(reply["received"])
    intent = reading["intent"]

    # These two never get handled automatically, whatever the facts say.
    if intent == "dispute":
        return NEEDS_A_PERSON, "Disputes always go to a person", None
    if intent == "unclear":
        return NEEDS_A_PERSON, "No clear request in the reply", None

    invoice, reason = find_invoice(customer, reading["invoice_number"], invoices)
    if reason:
        return NEEDS_A_PERSON, reason, None

    reason = check_amount(reading, invoice)
    if reason:
        return NEEDS_A_PERSON, reason, invoice

    if intent == "will_pay":
        reason = check_promised_date(reading, received)
        if reason:
            return NEEDS_A_PERSON, reason, invoice

    if intent == "needs_document":
        reason = check_document(reading)
        if reason:
            return NEEDS_A_PERSON, reason, invoice

    return HANDLED, next_step(reading, invoice, customer), invoice


def actions_for(status: str, reason: str, reading: dict, invoice: dict | None, customer: str) -> list[dict]:
    """The work each outcome does in the AR system. Matches the next step written out above."""
    if status == NEEDS_A_PERSON:
        return [{"type": "send_to_collector", "customer": customer, "reason": reason}]

    intent = reading["intent"]
    number = invoice["invoice"]

    if intent == "will_pay":
        return [{"type": "log_promise_to_pay", "invoice": number, "date": reading["promised_date"]}]

    if intent == "paid":
        return [
            {"type": "record_payment_reported", "invoice": number, "reference": reading["reference"] or "no reference given"},
            {"type": "pause_reminders", "invoice": number},
        ]

    # intent == "needs_document"
    document = reading["document_needed"]
    request = {"type": "request_document", "invoice": number, "document": document, "customer": customer}
    if document in ["new PO", "W-9"]:
        return [request, {"type": "pause_reminders", "invoice": number}]
    return [request]  # an invoice copy: send it, and keep reminders on


# ---------------------------------------------------------------------------
# Run every reply for each model, and compare with expected.json.
# ---------------------------------------------------------------------------


def main() -> None:
    invoices = json.loads(INVOICES_PATH.read_text())
    replies = {r["id"]: r for r in json.loads(REPLIES_PATH.read_text())}
    expected = {e["id"]: e for e in json.loads(EXPECTED_PATH.read_text())}

    for model in MODELS:
        readings = json.loads((RUNS_DIR / f"readings-{model}.json").read_text())
        outcomes = []
        ar_system = fresh_ar_system(invoices)
        status_matches = 0
        reason_matches = 0

        print(f"\n{model}")
        for r in readings:
            reply = replies[r["id"]]
            status, reason, invoice = triage(reply, r["reading"], invoices)
            outcome = {
                "id": r["id"],
                "from": reply["from"],
                "email": reply["email"],
                "said": r["reading"]["summary"],
                "status": status,
                "reason": reason,
                "invoice": invoice["invoice"] if invoice else None,
                "amount_due": invoice["amount"] if invoice else None,
                "cost": r["cost"],
                "actions": actions_for(status, reason, r["reading"], invoice, reply["from"]),
            }
            outcomes.append(outcome)

            for action in outcome["actions"]:
                apply_action(ar_system, r["id"], action)

            want = expected[r["id"]]
            status_ok = outcome["status"] == want["status"]
            reason_ok = outcome["reason"] == want["reason"]
            status_matches += status_ok
            reason_matches += reason_ok

            mark = "ok  " if status_ok and reason_ok else ("ok* " if status_ok else "FAIL")
            print(f"  {mark} {r['id']}  {outcome['status']:<15} {outcome['reason']}")
            if not reason_ok:
                print(f"            expected: {want['status']}: {want['reason']}")

        n = len(readings)
        print(f"  Status matches expected: {status_matches} of {n}. Reason matches: {reason_matches} of {n}.")

        # Save the AR system, then read it back from disk and check every
        # action against what is actually stored, not against what we meant to do.
        ar_path = RUNS_DIR / f"ar-system-{model}.json"
        save(ar_system, ar_path)
        saved = load(ar_path)

        done, total = 0, 0
        for outcome in outcomes:
            for action in outcome["actions"]:
                total += 1
                if verify_action(saved, outcome["id"], action):
                    done += 1
                else:
                    print(f"  NOT FOUND in AR system: {outcome['id']} {describe(action)}")
        print(f"  Actions verified in the saved AR system: {done} of {total}.")

        out_path = RUNS_DIR / f"triage-{model}.json"
        out_path.write_text(json.dumps(outcomes, indent=2))


if __name__ == "__main__":
    main()
