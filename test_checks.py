"""Tests for the checks in triage.py. No model calls: each test hands the
checks a reading written by hand, as if a model had produced it.

Two kinds of test:
  CAUGHT   a mistake the checks catch, because they have independent
           evidence (the invoice records) to compare against.
  KNOWN GAP  a mistake the checks do NOT catch. The test passes when the
           gap is still there, so the limit is written down and can't be
           forgotten. If someone closes the gap, this test fails and should
           be moved to CAUGHT.

Run:  python test_checks.py
"""

import json
from pathlib import Path

from triage import HANDLED, NEEDS_A_PERSON, triage

INVOICES = json.loads(Path("data/invoices.json").read_text())

ACME = {"id": "T", "from": "Acme Corp", "received": "2026-10-05", "email": "(test)"}
CEDAR = {"id": "T", "from": "Cedar Inc", "received": "2026-10-05", "email": "(test)"}
DELTA = {"id": "T", "from": "Delta Co", "received": "2026-10-06", "email": "(test)"}


def reading(**facts) -> dict:
    """A reading with every fact empty, except the ones given."""
    empty = {
        "intent": "unclear", "summary": "(test)", "invoice_number": None, "amount": None,
        "promised_date": None, "document_needed": None, "reference": None,
    }
    return empty | facts


def outcome(reply: dict, facts: dict) -> tuple[str, str]:
    status, reason, _ = triage(reply, facts, INVOICES)
    return status, reason


# --- CAUGHT -----------------------------------------------------------------


def test_invoice_not_on_the_customers_account():
    status, reason = outcome(CEDAR, reading(intent="paid", invoice_number="INV-1007"))
    assert status == NEEDS_A_PERSON
    assert reason == "No invoice INV-1007 on Cedar Inc's account. Their open invoice is INV-1006."


def test_another_customers_invoice_number():
    status, reason = outcome(CEDAR, reading(intent="paid", invoice_number="INV-1001"))
    assert status == NEEDS_A_PERSON
    assert reason.startswith("No invoice INV-1001 on Cedar Inc's account")


def test_amount_does_not_match_the_invoice():
    status, reason = outcome(ACME, reading(intent="paid", invoice_number="INV-1001", amount=4500.00))
    assert status == NEEDS_A_PERSON
    assert reason == "Customer says they paid $4,500.00, but INV-1001 is for $4,800.00"


def test_promised_date_too_far_out():
    status, reason = outcome(ACME, reading(intent="will_pay", invoice_number="INV-1001", promised_date="2026-12-15"))
    assert status == NEEDS_A_PERSON
    assert reason == "Promised date Dec 15 is more than 30 days out"


def test_promised_date_before_the_email():
    status, reason = outcome(ACME, reading(intent="will_pay", invoice_number="INV-1001", promised_date="2026-09-01"))
    assert status == NEEDS_A_PERSON
    assert reason == "Promised date Sep 1 is before the email arrived"


def test_promise_with_no_date():
    status, reason = outcome(ACME, reading(intent="will_pay", invoice_number="INV-1001"))
    assert status == NEEDS_A_PERSON
    assert reason == "Promises to pay but gives no date"


def test_dispute_misread_as_a_corrected_invoice_request():
    # The cheaper model's real slip in the repeat test (run 3, Delta).
    status, reason = outcome(DELTA, reading(intent="needs_document", invoice_number="INV-1009",
                                            document_needed="corrected invoice"))
    assert status == NEEDS_A_PERSON
    assert reason == "Asks for a corrected invoice, which means they disagree with the bill"


def test_clean_promise_is_handled():
    status, reason = outcome(ACME, reading(intent="will_pay", invoice_number="INV-1001", promised_date="2026-10-30"))
    assert status == HANDLED
    assert reason == "Promise to pay logged for Oct 30"


# --- KNOWN GAP --------------------------------------------------------------


def test_known_gap_dispute_misread_as_a_promise_to_pay():
    # Delta's dispute, misread as "will pay by Oct 30". The invoice is real and
    # theirs, the date is valid, so every check passes and it is Handled:
    # a promise gets recorded on an invoice the customer is disputing.
    # Nothing in the invoice records can show the model misread the email.
    status, _ = outcome(DELTA, reading(intent="will_pay", invoice_number="INV-1009", promised_date="2026-10-30"))
    assert status == HANDLED


# ----------------------------------------------------------------------------

TESTS = [
    test_invoice_not_on_the_customers_account,
    test_another_customers_invoice_number,
    test_amount_does_not_match_the_invoice,
    test_promised_date_too_far_out,
    test_promised_date_before_the_email,
    test_promise_with_no_date,
    test_dispute_misread_as_a_corrected_invoice_request,
    test_clean_promise_is_handled,
    test_known_gap_dispute_misread_as_a_promise_to_pay,
]

if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"passed: {test.__name__}")
    print(f"\nAll {len(TESTS)} passed.")
