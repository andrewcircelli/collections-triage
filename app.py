"""The one screen: what the collector sees.

Left: each customer's email beside what happened to it.
Right: the AR system itself, showing what the run changed.

Reads a saved run (runs/). It makes no model calls, so it opens instantly
and shows the same thing every time.

Run:  streamlit run app.py
"""

import html
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
EVAL_RESULTS_PATH = Path("eval/results.json")
EVAL_CASES_PATH = Path("eval/cases.json")
EVAL_EXAMPLE = "E23"  # "apply the 10% your rep promised": the cheaper model missed it on every run

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


def large(text: str, highlight: bool = False) -> None:
    """Show a line in larger text, for the parts that must be readable over a screen share.
    Streamlit has no font-size setting for ordinary text, so this wraps the line in an
    HTML <div>. It is the only HTML on the page. Use <b> for bold inside it, and &#36;
    for a dollar sign."""
    style = "font-size: 1.15rem; line-height: 1.45; margin-bottom: 0.4rem;"
    if highlight:
        style += " background: rgba(250, 202, 21, 0.18); padding: 0.6rem 0.8rem; border-radius: 0.5rem;"
    st.markdown(f'<div style="{style}">{text}</div>', unsafe_allow_html=True)


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
                    f"{handled} of {len(outcomes)} replies", delta_color="off", delta_arrow="off")
processed_tile.metric("Customer replies processed", f"{processed} of {len(outcomes)}",
                      f"{confirmed} of {total_actions} actions confirmed", delta_color="off", delta_arrow="off")
exceptions_tile.metric("Exceptions routed for review", f"{exceptions}",
                       "each with the reason", delta_color="off", delta_arrow="off")
cash_tile.metric("Overdue receivables actioned", f"${cash_handled:,.0f}",
                 f"of ${cash_overdue:,.0f} overdue", delta_color="off", delta_arrow="off")

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
                        f"<b>The model misread this</b> as \u201c{INTENT_WORDS[o['read_as']]}\u201d, "
                        f"not \u201c{INTENT_WORDS[expected_intent[o['id']]]}\u201d."
                    )
                    if o["status"] == "Needs a person" and o["read_as"] == "needs_document":
                        large(f"{misread} <b>The document rule still sent it to a person:</b> "
                              f"a {o['document_read']} means they disagree with the bill.", highlight=True)
                    elif o["status"] == "Needs a person":
                        large(f"{misread} <b>A rule still sent it to a person.</b>", highlight=True)
                    else:
                        st.error("The model misread this, and no rule caught it.")
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

    # The model evaluation: 30 harder labelled emails, 5 runs per model (eval_cases.py).
    # Every number here comes from eval/results.json.
    evaluation = json.loads(EVAL_RESULTS_PATH.read_text())
    cheap_eval = evaluation["summary"]["claude-haiku-4-5"]
    mid_eval = evaluation["summary"]["claude-sonnet-5-5"]
    cases = {c["id"]: c for c in json.loads(EVAL_CASES_PATH.read_text())}

    # The example: how each model's 5 runs went on one disguised dispute.
    example = cases[EVAL_EXAMPLE]
    cheap_example_misses = 0
    mid_example_misses = 0
    for r in evaluation["all_results"]:
        if r["id"] == EVAL_EXAMPLE and r["status"] != example["expected"]:
            if r["model"] == "claude-haiku-4-5":
                cheap_example_misses += 1
            else:
                mid_example_misses += 1

    extra_cost = (mid_eval["cost_per_reply"] - cheap_eval["cost_per_reply"]) * 10_000

    with st.container(border=True):
        large(f"<b>Model evaluation</b> · {len(cases)} harder test emails, 5 runs each")
        cheap_col, mid_col = st.columns(2)
        with cheap_col:
            st.metric("Cheaper model", f"{cheap_eval['correct_outcome'] / cheap_eval['readings']:.0%}",
                      f"{cheap_eval['correct_outcome']} of {cheap_eval['readings']} correct", delta_color="off", delta_arrow="off")
            st.progress(cheap_eval["correct_outcome"] / cheap_eval["readings"])
        with mid_col:
            st.metric("Mid-tier model", f"{mid_eval['correct_outcome'] / mid_eval['readings']:.0%}",
                      f"{mid_eval['correct_outcome']} of {mid_eval['readings']} correct", delta_color="off", delta_arrow="off")
            st.progress(mid_eval["correct_outcome"] / mid_eval["readings"])

        large(f"<b>Example:</b> \u201c{html.escape(example['email'])}\u201d")
        large(f"\u2717 <b>Cheaper model</b>, {cheap_example_misses} of 5 runs: read a promise to pay, "
              f"missed the dispute \u2192 handled as routine")
        large(f"\u2713 <b>Mid-tier model</b>, {5 - mid_example_misses} of 5 runs: caught the dispute "
              f"\u2192 sent to a person")
        st.caption(
            f"Missed escalations: {cheap_eval['false_handled']} vs {mid_eval['false_handled']} of "
            f"{cheap_eval['readings']} test runs, concentrated in disguised disputes · "
            f"mid-tier about \\${extra_cost:,.0f} more per 10,000 emails"
        )
