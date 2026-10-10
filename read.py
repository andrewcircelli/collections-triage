"""Step 1, READ: the only step that uses the model.

For each customer reply, the model returns a fixed structure: what the
customer is saying, plus any facts they mention (invoice number, amount,
date, check or payment reference). It does not see the invoice list.
Checking those facts is the job of plain code in the next steps.

Every model call is traced in LangSmith, with its token counts and cost.

Run:  python read.py
Writes one file per model to runs/, e.g. runs/readings-claude-haiku-4-5.json
"""

import json
from pathlib import Path
from typing import Literal

from anthropic import Anthropic
from dotenv import load_dotenv
from langsmith import get_current_run_tree, traceable
from langsmith.wrappers import wrap_anthropic
from pydantic import BaseModel, Field

load_dotenv(override=True)

# wrap_anthropic makes every call through this client show up in LangSmith.
client = wrap_anthropic(Anthropic())

# The cheap model and the mid-tier model, run on the same replies.
MODELS = ["claude-haiku-4-5", "claude-sonnet-5-5"]

# Dollars per million tokens, from Anthropic's price list (September 2026).
PRICES = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
}

REPLIES_PATH = Path("data/replies.json")
RUNS_DIR = Path("runs")


# ---------------------------------------------------------------------------
# The fixed structure the model must fill in. The API enforces this shape,
# so every reply comes back with the same fields, whichever model read it.
# ---------------------------------------------------------------------------


class Reading(BaseModel):
    intent: Literal["paid", "will_pay", "needs_document", "dispute", "unclear"] = Field(
        description="What the customer is saying, as one of five choices."
    )
    summary: str = Field(
        description="One short sentence a finance person would understand, "
        "e.g. 'Will pay INV-1001 by Oct 30'."
    )
    invoice_number: str | None = Field(
        description="The invoice number exactly as the customer wrote it, or null."
    )
    amount: float | None = Field(
        description="A dollar amount the customer mentions, or null."
    )
    promised_date: str | None = Field(
        description="The date they promise to pay by, as YYYY-MM-DD, or null."
    )
    document_needed: Literal[
        "new PO", "W-9", "invoice copy", "corrected invoice", "other"
    ] | None = Field(
        description="The document they ask for, as one of five choices, or null."
    )
    reference: str | None = Field(
        description="A check number or payment reference they mention, or null."
    )


SYSTEM = """You read customer replies to overdue-invoice reminders for a
software company's collections team.

For each reply, say what the customer is saying, using one of these:
- paid: they say they have already paid.
- will_pay: they promise to pay by a date.
- needs_document: they need a document (a new PO, a W-9, a copy of the
  invoice) before they can pay.
- dispute: they disagree with the invoice or a line on it.
- unclear: none of the above, or you can't tell.

Then record the facts they mention. Copy each fact exactly as the customer
wrote it, even if it looks wrong. Do not fix or guess anything. If a fact
is not in the email, use null.

For dates, use the date the email was received to turn words like
"Friday" or "next week" into a calendar date (YYYY-MM-DD)."""


def cost_in_dollars(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICES[model]
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


@traceable(name="read_reply")
def read_reply(model: str, reply: dict) -> dict:
    # Give the trace a name you can find in LangSmith, e.g. "read R3 claude-haiku-4-5".
    run = get_current_run_tree()
    if run:
        run.name = f"read {reply['id']} {model}"

    message = (
        f"From: {reply['from']}\n"
        f"Received: {reply['received']}\n\n"
        f"{reply['email']}"
    )

    # client.beta.messages.parse, not client.messages.parse: they do the same
    # thing, but LangSmith's wrapper only records the beta one. With the
    # plain one, the trace has no token counts.
    response = client.beta.messages.parse(
        model=model,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": message}],
        output_format=Reading,
    )

    reading = response.parsed_output
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    return {
        "id": reply["id"],
        "from": reply["from"],
        "model": model,
        "reading": reading.model_dump(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost_in_dollars(model, input_tokens, output_tokens),
    }


def main() -> None:
    replies = json.loads(REPLIES_PATH.read_text())
    RUNS_DIR.mkdir(exist_ok=True)

    for model in MODELS:
        results = []
        for reply in replies:
            result = read_reply(model, reply)
            r = result["reading"]
            print(f"{model}  {reply['id']}  {r['intent']:<15} {r['summary']}  (${result['cost']:.4f})")
            results.append(result)

        out_path = RUNS_DIR / f"readings-{model}.json"
        out_path.write_text(json.dumps(results, indent=2))
        print(f"Wrote {out_path}\n")


if __name__ == "__main__":
    main()
