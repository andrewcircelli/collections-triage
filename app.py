"""The one screen: what the collector sees.

Reads a saved run (runs/triage-<model>.json). It makes no model calls, so
it opens instantly and shows the same thing every time.

Run:  streamlit run app.py
"""

import json
from pathlib import Path

import streamlit as st

RUNS_DIR = Path("runs")
REPLIES_PATH = Path("data/replies.json")

MODELS = {
    "claude-haiku-4-5": "Cheaper model (Claude Haiku 4.5)",
    "claude-sonnet-5-5": "Mid-tier model (Claude Sonnet 5.5)",
}

# Show the caught mistake first, then the routine replies, then the rest.
ROW_ORDER = ["R3", "R1", "R2", "R5", "R4", "R6", "R7"]


def load_run(model: str) -> list[dict]:
    outcomes = json.loads((RUNS_DIR / f"triage-{model}.json").read_text())
    by_id = {o["id"]: o for o in outcomes}
    return [by_id[i] for i in ROW_ORDER]


def total_cost(outcomes: list[dict]) -> float:
    return sum(o["cost"] for o in outcomes)


st.set_page_config(page_title="Collections reply triage", layout="wide")
st.title("Collections reply triage")
st.caption("Made-up customers and invoices. \"Handled\" means the next step is written out. Nothing is sent.")

model = st.radio(
    "Model", list(MODELS), format_func=lambda m: MODELS[m], horizontal=True,
    label_visibility="collapsed",
)
outcomes = load_run(model)
received = {r["id"]: r["received"] for r in json.loads(REPLIES_PATH.read_text())}

handled = [o for o in outcomes if o["status"] == "Handled"]
to_a_person = [o for o in outcomes if o["status"] != "Handled"]
cash_with_next_step = sum(o["amount_due"] for o in handled)

# The summary line.
st.subheader(
    f"{len(handled)} of {len(outcomes)} handled · {len(to_a_person)} need a person · "
    f"${cash_with_next_step:,.0f} of overdue cash has a next step today"
)

# One line comparing the two models on the same replies.
costs = {m: total_cost(load_run(m)) for m in MODELS}
st.write(
    f"Cost to read all {len(outcomes)} replies: "
    f"cheaper model ${costs['claude-haiku-4-5']:.3f}, "
    f"mid-tier model ${costs['claude-sonnet-5-5']:.3f}. "
    f"This run: ${total_cost(outcomes) / len(outcomes):.4f} per reply."
)

st.divider()

# One row per reply: the customer's own email on the left, the decision on the right.
for o in outcomes:
    with st.container(border=True):
        left, right = st.columns([1, 1])
        with left:
            st.markdown(f"**{o['from']}** · received {received[o['id']]}")
            st.markdown(f"> {o['email']}")
        with right:
            if o["status"] == "Handled":
                st.markdown("✅ **Handled**")
            else:
                st.markdown("⚠️ **Needs a person**")
            st.markdown(o["reason"])
            st.caption(f"AI read it as: {o['said']} · cost ${o['cost']:.4f}")
