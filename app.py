"""The one screen, framed as a process change: before and after.

Top: the change in one line, then three results for the run shown:
  efficiency     replies closed without a collector
  effectiveness  exceptions that reached a person, out of those that should
  proof          actions done and confirmed in the AR system
Below that, three tabs, one per point in the conversation:
  1. The replies: each customer's email beside what happened to it.
  2. The AR system: what the run changed, before and after.
  3. Which model to trust: the rules catch some model mistakes, not all;
     the evaluation on 30 harder emails (from eval/results.json).

The first two tabs show the mid-tier model's run, the model the evaluation
chose. Tab 3 uses the cheaper model's run for the Delta example.

Reads saved runs (runs/ and eval/). It makes no model calls, so it opens
instantly and shows the same thing every time.

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
EVAL_RESULTS_PATH = Path("eval/results.json")
EVAL_CASES_PATH = Path("eval/cases.json")
EVAL_EXAMPLE = "E23"  # "apply the 10% your rep promised": the cheaper model missed it on every run

CHEAPER = "claude-haiku-4-5"
MID_TIER = "claude-sonnet-5-5"

# The run on the first two tabs: the mid-tier model, which the evaluation chose.
SHOWN_MODEL = MID_TIER

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

st.subheader("Collections reply triage")
large("<b>Before:</b> a collector reads every reply to an overdue reminder and updates the AR system by hand.<br>"
      "<b>After:</b> routine replies are done and checked automatically. The collector reads only the "
      "exceptions, each with the reason.")
st.caption("Made-up customers and invoices. Saved runs, no live model calls. Emails to customers are drafted, never sent.")

outcomes = load_run(SHOWN_MODEL)
expected = {e["id"]: e for e in json.loads(EXPECTED_PATH.read_text())}
received = {r["id"]: r["received"] for r in json.loads(REPLIES_PATH.read_text())}
invoices = json.loads(INVOICES_PATH.read_text())

# Before: the AR system as the run found it. After: the saved file, read now.
# Every tick on this page is checked against the saved file when the page loads.
before = fresh_ar_system(invoices)
after = load(RUNS_DIR / f"ar-system-{SHOWN_MODEL}.json")

# The three results.
handled = 0
cash_actioned = 0.0
exceptions_expected = 0
exceptions_caught = 0
total_actions = 0
confirmed = 0
for o in outcomes:
    if o["status"] == "Handled":
        handled += 1
        cash_actioned += o["amount_due"]
    if expected[o["id"]]["status"] == "Needs a person":
        exceptions_expected += 1
        if o["status"] == "Needs a person":
            exceptions_caught += 1
    for action in o["actions"]:
        total_actions += 1
        if verify_action(after, o["id"], action):
            confirmed += 1

cash_overdue = 0.0
for inv in invoices:
    cash_overdue += inv["amount"]

efficiency_tile, effectiveness_tile, proof_tile = st.columns(3)
efficiency_tile.metric("Efficiency: replies closed without a collector", f"{handled} of {len(outcomes)}",
                       f"\\${cash_actioned:,.0f} of \\${cash_overdue:,.0f} overdue actioned",
                       delta_color="off", delta_arrow="off")
effectiveness_tile.metric("Effectiveness: exceptions that reached a person",
                          f"{exceptions_caught} of {exceptions_expected}", "each with the reason",
                          delta_color="off", delta_arrow="off")
proof_tile.metric("Proof: actions confirmed in the AR system", f"{confirmed} of {total_actions}",
                  "read back from the saved records", delta_color="off", delta_arrow="off")
st.caption("Four made-up replies show how it works, not a forecast. A pilot measures the real rates.")

replies_tab, system_tab, model_tab = st.tabs(
    ["1 · The replies", "2 · The AR system, before and after", "3 · Which model to trust"]
)

# Tab 1: one row per reply, the customer's own email beside what happened to it.
with replies_tab:
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
                for action in o["actions"]:
                    if verify_action(after, o["id"], action):
                        st.caption(f"✓ Done: {describe(action)}")
                    else:
                        st.caption(f"✗ Not found in the AR system: {describe(action)}")

# Tab 2: the AR system itself.
with system_tab:
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

# Tab 3: the rules catch some model mistakes, not all, so the reading model matters.
with model_tab:
    # A mistake the rules caught: the cheaper model's run where it misread Delta.
    delta = None
    for o in load_run(CHEAPER):
        if o["id"] == "R4":
            delta = o
    if delta["read_as"] != expected["R4"]["intent"] and delta["status"] == "Needs a person":
        large(f"<b>The rules catch some model mistakes.</b> In one run, the cheaper model read "
              f"{delta['from']}'s dispute as “{INTENT_WORDS[delta['read_as']]}” "
              f"(a {delta['document_read']}). The document rule still sent it to a person: "
              f"a {delta['document_read']} means they disagree with the bill.")

    # A mistake no rule can catch: the evaluation on 30 harder emails, 5 runs per model.
    # Every number here comes from eval/results.json.
    evaluation = json.loads(EVAL_RESULTS_PATH.read_text())
    cheap_eval = evaluation["summary"][CHEAPER]
    mid_eval = evaluation["summary"][MID_TIER]
    cases = {c["id"]: c for c in json.loads(EVAL_CASES_PATH.read_text())}

    example = cases[EVAL_EXAMPLE]
    cheap_example_misses = 0
    mid_example_misses = 0
    for r in evaluation["all_results"]:
        if r["id"] == EVAL_EXAMPLE and r["status"] != example["expected"]:
            if r["model"] == CHEAPER:
                cheap_example_misses += 1
            else:
                mid_example_misses += 1

    extra_cost = (mid_eval["cost_per_reply"] - cheap_eval["cost_per_reply"]) * 10_000

    large(f"<b>Not all.</b> “{html.escape(example['email'])}”")
    large(f"✗ <b>Cheaper model</b>, {cheap_example_misses} of 5 runs: read a promise to pay, "
          f"missed the dispute → handled as routine")
    large(f"✓ <b>Mid-tier model</b>, {5 - mid_example_misses} of 5 runs: caught the dispute "
          f"→ sent to a person")

    with st.container(border=True):
        large(f"<b>Evaluation</b> · {len(cases)} harder test emails with an answer key, 5 runs each")
        cheap_col, mid_col = st.columns(2)
        with cheap_col:
            st.metric("Cheaper model", f"{cheap_eval['correct_outcome'] / cheap_eval['readings']:.0%}",
                      f"{cheap_eval['correct_outcome']} of {cheap_eval['readings']} correct",
                      delta_color="off", delta_arrow="off")
            st.progress(cheap_eval["correct_outcome"] / cheap_eval["readings"])
        with mid_col:
            st.metric("Mid-tier model", f"{mid_eval['correct_outcome'] / mid_eval['readings']:.0%}",
                      f"{mid_eval['correct_outcome']} of {mid_eval['readings']} correct",
                      delta_color="off", delta_arrow="off")
            st.progress(mid_eval["correct_outcome"] / mid_eval["readings"])
        large(f"<b>So the mid-tier model reads the replies:</b> about &#36;{extra_cost:,.0f} more per "
              f"10,000 emails, less than one missed dispute costs.", highlight=True)
        st.caption(
            f"Missed escalations: {cheap_eval['false_handled']} vs {mid_eval['false_handled']} of "
            f"{cheap_eval['readings']} test runs, concentrated in disguised disputes. "
            f"Cost per reply: \\${cost_per_reply(CHEAPER):.4f} cheaper, \\${cost_per_reply(MID_TIER):.4f} mid-tier."
        )
