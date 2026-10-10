# Collections reply triage

When an invoice goes overdue, customers reply with all sorts of things: we paid, we'll pay Friday,
we need a new PO, this line is wrong. This reads each reply, checks what the customer said against
the actual invoices, handles the routine ones, and sends the rest to a person with the reason.

**Status: work in progress.** Built on made-up customers and invoices. Nothing is ever sent.

## How it works

```
Reply → 1. READ           → 2. FIND            → 3. CHECK             → 4. ROUTE
        the model says       the invoice in       plain code checks      routine + all checks pass
        what the customer    the open-invoice     the customer's claim   → Handled, next step
        means + the facts    list                 against the invoice    anything else
                                                                         → Needs a person + reason
```

| Step | Who does it | Built? |
|---|---|---|
| 1. Read | The model (`read.py`) | ✅ Built |
| 2. Find | Plain code | ⏳ Not built yet |
| 3. Check | Plain code, no model | ⏳ Not built yet |
| 4. Route | Plain code, two outcomes | ⏳ Not built yet |
| The one-screen table | Streamlit | ⏳ Not built yet |

The model never checks its own work. It doesn't see the invoice list at all.

## The data

- `data/invoices.json`: 6 open invoices across 4 customers.
- `data/replies.json`: 7 short customer replies.
- `data/expected.json`: the expected status and reason for every reply, written before the pipeline
  runs. The checks are judged against this file. (Draft: the exact reasons are finalised when the
  checks are built.)

## Run it

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the two keys
python read.py
```

`read.py` reads every reply with two models, a cheap one (`claude-haiku-4-5`) and a mid-tier one
(`claude-sonnet-5-5`), and writes `runs/readings-<model>.json`. Each call is traced in LangSmith
(project `collections-triage`) with its tokens and cost.

`anthropic` is pinned below 1.0 because LangSmith's `wrap_anthropic` does not yet work with the 1.x
SDK (it looks for the removed `client.completions`).

`read.py` calls `client.beta.messages.parse` rather than `client.messages.parse`. Both do the same
thing, but LangSmith's wrapper only records the beta one; with the plain one, the traces have no
token counts or cost.
