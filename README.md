# Collections reply triage

When an invoice goes overdue, customers reply with all sorts of things: we paid, we'll pay Friday,
we need a new PO, this line is wrong. This reads each reply, checks what the customer said against
the actual invoices, handles the routine ones, and sends the rest to a person with the reason.

Built on made-up customers and invoices. Every outcome is carried out in a stand-in AR system and
then checked there. Nothing goes to customers: emails are saved as drafts.

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
| 2. Find | Plain code (`triage.py`) | ✅ Built |
| 3. Check | Plain code, no model (`triage.py`) | ✅ Built |
| 4. Route | Plain code, two outcomes (`triage.py`) | ✅ Built |
| The one screen | Streamlit (`app.py`) | ✅ Built |

The model never checks its own work. It doesn't see the invoice list at all.

## The checks

A reply is **Handled** only if it's routine and every check passes. Otherwise it **Needs a person**,
and the first thing that failed is the reason.

1. **Disputes and unclear replies always go to a person.**
2. **The invoice is on that customer's account.** With no invoice number, the customer must have
   exactly one open invoice.
3. **Any amount they mention matches the invoice.**
4. **A promised payment date** is a real date, not before the email arrived, and within 30 days.
5. **Only routine documents are routine:** a new PO, a W-9 or an invoice copy. A request for a
   corrected invoice means they disagree with the bill, so it goes to a person.

## The actions, and the proof they happened

Every outcome does work in a stand-in AR system: one JSON file per run, `runs/ar-system-<model>.json`,
built fresh from `data/invoices.json` (`actions.py`).

| Outcome | What it does in the AR system |
|---|---|
| Will pay by a date | Records the promise to pay on the invoice |
| Already paid | Records the reported payment and its reference; pauses reminders |
| New PO or W-9 | Records the document request; drafts the email (not sent); pauses reminders |
| Invoice copy | Records the request; drafts the email (not sent) |
| Needs a person | Adds the reply to the collector's queue with the reason |

After the run, the file is read back from disk and every action is checked against what is actually
stored. The screen does the same check again when it loads, and shows ✓ only for what it finds. On
the test run: 9 of 9 actions confirmed for both models. Against an untouched AR system the same
check finds 0 of 9, so it isn't a check that always passes.

"We already paid" counts as routine: the next step logs the payment and pauses reminders until it
arrives.

## The data

- `data/invoices.json`: 6 open invoices across 4 customers.
- `data/replies.json`: 7 short customer replies.
- `data/expected.json`: the expected status and reason for every reply, written before the pipeline
  ran. The checks are judged against this file.

## Run it

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the two keys
python read.py        # calls the model; costs about 3 cents for both models
python triage.py      # plain code, free: decides, acts, then verifies
streamlit run app.py  # opens the screen in the browser
```

For a demo, only the last command is needed: `app.py` reads the saved run in `runs/` and makes no
model calls.

## The screen

One row per reply: the customer's own email on the left, the decision and reason on the right. The
Cedar reply (the caught wrong invoice) comes first. The summary line reads "3 of 7 handled · 4 need
a person · $10,550 of overdue cash has a next step today". A switch at the top shows the same
replies read by the cheaper or the mid-tier model, with the cost of each.

`read.py` reads every reply with two models, a cheap one (`claude-haiku-4-5`) and a mid-tier one
(`claude-sonnet-5-5`), and writes `runs/readings-<model>.json`. Each call is traced in LangSmith
(project `collections-triage`) with its tokens and cost.

`triage.py` finds, checks and routes every reading, prints each outcome against `expected.json`, and
writes `runs/triage-<model>.json`. It makes no model calls, so it's free to rerun.

## Result so far

Both models: **7 of 7 replies match `expected.json`**, status and reason. 3 handled, 4 to a person.
Reading all 7 replies cost about $0.01 with Haiku and $0.02 with Sonnet 5.5.

- **The caught mistake:** Cedar quoted invoice INV-1007, which isn't theirs. Both models copied it
  faithfully; the invoice check caught it.
- **The cheap model's slip:** on one of three runs, Haiku read Delta's dispute as a request for a
  corrected invoice. The document check (5) sends that to a person too, so the outcome is still
  right. Sonnet 5.5 called it a dispute every time.

`anthropic` is pinned below 1.0 because LangSmith's `wrap_anthropic` does not yet work with the 1.x
SDK (it looks for the removed `client.completions`).

`read.py` calls `client.beta.messages.parse` rather than `client.messages.parse`. Both do the same
thing, but LangSmith's wrapper only records the beta one; with the plain one, the traces have no
token counts or cost.
