"""The one screen: what the collector sees.

Left: each customer's email beside what happened to it.
Right: the AR system itself, showing what the run changed.

Reads a saved run (runs/). It makes no model calls, so it opens instantly
and shows the same thing every time.

Run:  streamlit run app.py
"""

import json
from datetime import date
from pathlib import Path

import streamlit as st

from actions import describe, fresh_ar_system, load, verify_action

RUNS_DIR = Path("runs")
REPLIES_PATH = Path("data/replies.json")
INVOICES_PATH = Path("data/invoices.json")
EXPECTED_PATH = Path("data/expected.json")
SUMMARY_PATH = RUNS_DIR / "repeats" / "summary.json"

MODELS = {
    "claude-haiku-4-5": "Cheaper model",
    "claude-sonnet-5-5": "Mid-tier model",
}

# Which of the 5 repeat-test runs is on screen (copied into runs/readings-<model>.json).
# For the cheaper model it's the run where it misread Delta's dispute.
SHOWN_RUN = {"claude-haiku-4-5": 3, "claude-sonnet-5-5": 1}

INTENT_WORDS = {
    "paid": "already paid",
    "will_pay": "will pay by a date",
    "needs_document": "needs a document",
    "dispute": "a dispute",
    "unclear": "unclear",
}

# Show the caught mistake first, then the routine replies, then the dispute.
ROW_ORDER = ["R3", "R1", "R2", "R4"]


def load_run(model: str) -> list[dict]:
    outcomes = json.loads((RUNS_DIR / f"triage-{model}.json").read_text())
    by_id = {o["id"]: o for o in outcomes}
    return [by_id[i] for i in ROW_ORDER]


def cost_per_reply(model: str) -> float:
    outcomes = load_run(model)
    return sum(o["cost"] for o in outcomes) / len(outcomes)


def show(value) -> str:
    """A cell value as the screen shows it: dates as 'Oct 30', empty as a dash."""
    if value is None:
        return "—"
    try:
        d = date.fromisoformat(value)
        return f"{d.strftime('%b')} {d.day}"
    except ValueError:
        return value


def cell(before, after) -> str:
    """Unchanged: the value. Changed: the old value struck through, the new one in bold."""
    if before == after:
        return show(after)
    if before is None:
        return f"**{show(after)}**"
    return f"~~{show(before)}~~ **{show(after)}**"


st.set_page_config(page_title="Collections reply triage", layout="wide")

title, picker = st.columns([3, 2])
with title:
    st.subheader("Collections reply triage")
    st.caption("Made-up customers and invoices. Emails to customers are drafted, never sent.")
with picker:
    model = st.radio(
        "Which model read the replies", list(MODELS), format_func=lambda m: MODELS[m], horizontal=True,
    )

outcomes = load_run(model)
received = {r["id"]: r["received"] for r in json.loads(REPLIES_PATH.read_text())}
expected_intent = {e["id"]: e["intent"] for e in json.loads(EXPECTED_PATH.read_text())}
summary = json.loads(SUMMARY_PATH.read_text())

# Before: the AR system as the run found it. After: the saved file, read now.
# Every tick on this page is checked against the saved file when the page loads.
before = fresh_ar_system(json.loads(INVOICES_PATH.read_text()))
after = load(RUNS_DIR / f"ar-system-{model}.json")

# The business results. A reply counts as processed when it got an outcome
# and every action for it is confirmed in the AR system.
handled = 0
processed = 0
total_actions = 0
confirmed = 0
cash_handled = 0.0
cash_overdue = 0.0
for o in outcomes:
    all_done = True
    for action in o["actions"]:
        total_actions += 1
        if verify_action(after, o["id"], action):
            confirmed += 1
        else:
            all_done = False
    if all_done:
        processed += 1
    if o["status"] == "Handled":
        handled += 1
        cash_handled += o["amount_due"]

for inv in json.loads(INVOICES_PATH.read_text()):
    cash_overdue += inv["amount"]

exceptions = len(outcomes) - handled

handled_tile, processed_tile, exceptions_tile, cash_tile = st.columns(4)
handled_tile.metric("Handled without a collector", f"{handled / len(outcomes):.0%}",
                    f"{handled} of {len(outcomes)} replies", delta_color="off")
processed_tile.metric("Customer replies processed", f"{processed} of {len(outcomes)}",
                      f"{confirmed} of {total_actions} actions confirmed", delta_color="off")
exceptions_tile.metric("Exceptions routed for review", f"{exceptions}",
                       "each with the reason", delta_color="off")
cash_tile.metric("Overdue cash handled automatically", f"${cash_handled:,.0f}",
                 f"of ${cash_overdue:,.0f} overdue", delta_color="off")

st.caption(
    f"On 4 made-up replies, so these show how it works, not a forecast; a pilot measures the real rates. "
    f"Cost per reply: \\${cost_per_reply('claude-haiku-4-5'):.4f} cheaper model, "
    f"\\${cost_per_reply('claude-sonnet-5-5'):.4f} mid-tier."
)

# The repeat test, in plain words: which run is on screen, and the totals over all 5.
ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
this_model = summary[model]
misread_here = []
for m in this_model["misreads"]:
    if m["run"] == SHOWN_RUN[model]:
        misread_here.append(m["from"])

line = f"Each model read these 4 emails 5 times. This is the {MODELS[model].lower()}'s {ORDINAL[SHOWN_RUN[model]]} run"
if misread_here:
    line += f", the one where it misread {', '.join(misread_here)}"
line += (
    f". Over all 5 runs it read {this_model['read_right']} of {this_model['total']} emails as expected "
    f"and got the right outcome {this_model['outcome_right']} of {this_model['total']} times."
)
st.caption(line)

replies_side, system_side = st.columns([3, 2], gap="large")

# Left: one row per reply, the customer's own email beside the decision.
with replies_side:
    for o in outcomes:
        with st.container(border=True):
            email, decision = st.columns([1, 1])
            with email:
                st.markdown(f"**{o['from']}** · {show(received[o['id']])}")
                st.caption(o["email"])
            with decision:
                if o["status"] == "Handled":
                    st.markdown(f"✅ **Handled.** {o['reason']}")
                else:
                    st.markdown(f"⚠️ **Needs a person.** {o['reason']}")
                if o["read_as"] != expected_intent[o["id"]]:
                    misread = (
                        f"The model labelled this \"{INTENT_WORDS[o['read_as']]}\" "
                        f"instead of \"{INTENT_WORDS[expected_intent[o['id']]]}\"."
                    )
                    if o["status"] == "Needs a person" and o["read_as"] == "needs_document":
                        st.warning(
                            f"{misread} Taken as a request for a {o['document_read']}, it would have been "
                            f"handled as routine paperwork. The document rule sent it to a person anyway: "
                            f"asking for a {o['document_read']} means they disagree with the bill."
                        )
                    elif o["status"] == "Needs a person":
                        st.warning(f"{misread} A check still sent it to a person.")
                    else:
                        st.error(f"{misread} No check caught it.")
                for action in o["actions"]:
                    if verify_action(after, o["id"], action):
                        st.caption(f"✓ Done: {describe(action)}")
                    else:
                        st.caption(f"✗ Not found in the AR system: {describe(action)}")

# Right: the AR system itself.
with system_side:
    st.markdown("**The AR system after this run**")
    rows = [
        "| Invoice | Reminders | Promise to pay | Document requested |",
        "|---|---|---|---|",
    ]
    for number, record in after["invoices"].items():
        was = before["invoices"][number]
        rows.append(
            f"| {number} {record['customer']} "
            f"| {cell(was['reminders'], record['reminders'])} "
            f"| {cell(was['promise_to_pay'], record['promise_to_pay'])} "
            f"| {cell(was['document_requested'], record['document_requested'])} |"
        )
    st.markdown("\n".join(rows))
    st.caption("Bold is what this run changed. Struck through is what it was before.")

    queue = ", ".join(item["customer"] for item in after["collector_queue"])
    st.markdown(f"**Collector's queue ({len(after['collector_queue'])}):** {queue}")

    drafts = ", ".join(f"{e['to']}: {e['subject']}" for e in after["outbox"])
    st.markdown(f"**Outbox ({len(after['outbox'])} draft, not sent):** {drafts}")
