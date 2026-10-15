"""The one screen: each customer's email beside what happened to it.

Handled replies show the actions done, each with a tick only if
verify_action() finds it in the saved AR system. Replies that need a
person show the reason.

Shows the mid-tier model's run, the model the evaluation chose
(eval_cases.py). Reads saved runs from runs/. It makes no model calls,
so it opens instantly and shows the same thing every time.

Run:  streamlit run app.py
"""

import json
from datetime import date
from pathlib import Path

import streamlit as st

from actions import describe, load, verify_action

RUNS_DIR = Path("runs")
REPLIES_PATH = Path("data/replies.json")

# The run on screen: the mid-tier model, which the evaluation chose.
SHOWN_MODEL = "claude-sonnet-5-5"

# Show the caught mistake first, then the routine replies, then the dispute.
ROW_ORDER = ["R3", "R1", "R2", "R4"]


def load_run(model: str) -> list[dict]:
    outcomes = json.loads((RUNS_DIR / f"triage-{model}.json").read_text())
    by_id = {o["id"]: o for o in outcomes}
    return [by_id[i] for i in ROW_ORDER]


def show_date(value: str) -> str:
    """'2026-10-05' as 'Oct 5'."""
    d = date.fromisoformat(value)
    return f"{d.strftime('%b')} {d.day}"


st.set_page_config(page_title="Collections reply triage", layout="wide")

st.subheader("Collections reply triage")
st.caption("Made-up customers and invoices. Saved runs, no live model calls. Emails to customers are drafted, never sent.")

outcomes = load_run(SHOWN_MODEL)
received = {r["id"]: r["received"] for r in json.loads(REPLIES_PATH.read_text())}
after = load(RUNS_DIR / f"ar-system-{SHOWN_MODEL}.json")

for o in outcomes:
    with st.container(border=True):
        email, decision = st.columns([1, 1])
        with email:
            st.markdown(f"**{o['from']}** · {show_date(received[o['id']])}")
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
