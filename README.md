# Collections reply triage

When an invoice goes overdue, customers reply with all sorts of things: we paid, we'll pay Friday,
we need a new PO, this line is wrong. This reads each reply, checks what the customer said against
the actual invoices, handles the routine ones, and sends the rest to a person with the reason.

Built on made-up customers and invoices. Every outcome is carried out in a stand-in AR system and
then checked there. Nothing goes to customers: emails are saved as drafts.

## What it shows, and what it doesn't

- **Capability:** the model turns free-text replies into structured facts.
- **Control:** written business rules, not the model, decide every outcome and authorize every
  action.
- **Evidence:** in the tested cases, the cheaper model's facts were enough for the checks to reach
  the expected outcome every time, including the run where it misread a dispute.

It does **not** show that the system is safe in general. The checks only catch a model error when
the invoice records give independent evidence of it. Some errors they can't see (see
"Known gaps" below).

## How it works

```
Reply → 1. READ           → 2. FIND            → 3. CHECK             → 4. ROUTE
        the model says       the invoice in       plain code checks      routine + all checks pass
        what the customer    the open-invoice     the customer's claim   → Handled: actions done
        means + the facts    list                 against the invoice    anything else
                                                                         → Needs a person + reason
```

| Step | Who does it | File |
|---|---|---|
| 1. Read | The model | `read.py` |
| 2. Find, 3. Check, 4. Route | Plain code, no model | `triage.py` |
| Actions, and the proof they happened | Plain code | `actions.py` |
| The one screen | Streamlit | `app.py` |

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

"We already paid" counts as routine: it records the payment and pauses reminders until it arrives.

`test_checks.py` tests each check with hand-written readings, including the ones the demo data
doesn't hit (a wrong amount, a date too far out). `python test_checks.py` runs them; no model calls.

## Known gaps

The checks catch a misread only when the invoice records contradict it.

| If the model… | Caught? |
|---|---|
| Copies an invoice number that isn't the customer's | ✅ The invoice list contradicts it |
| States an amount that doesn't match the invoice | ✅ The invoice contradicts it |
| Reads a dispute as a request for a corrected invoice | ✅ Check 5 sends it to a person |
| **Reads a dispute as "will pay by Oct 30"** | ❌ A real invoice and a valid date pass every check; the promise gets recorded on a disputed invoice |
| **Picks a different invoice that belongs to the same customer** | ❌ It's on their account, so it passes |
| Misses a request in the email entirely | ❌ Nothing to compare against |

The first ❌ row is written down as a test (`test_known_gap_dispute_misread_as_a_promise_to_pay`): it
passes while the gap exists. In a pilot, the side-by-side period with the collectors is where these
would be measured.

## The actions, and the proof they happened

Every outcome does work in a stand-in AR system: one JSON file per run, `runs/ar-system-<model>.json`,
built fresh from `data/invoices.json` each time (`actions.py`). It is not a live system: nothing
else reads it, and each run starts from blank.

| Outcome | What it does in the AR system |
|---|---|
| Will pay by a date | Records the promise to pay on the invoice |
| Already paid | Records the reported payment and its reference; pauses reminders |
| New PO or W-9 | Records the document request; drafts the email (not sent); pauses reminders |
| Invoice copy | Records the request; drafts the email (not sent) |
| Needs a person | Adds the reply to the collector's queue with the reason |

After the run, the file is read back from disk and every action is checked against what is actually
stored. The screen does the same check again when it loads, and shows ✓ only for what it finds.
Against an untouched AR system the same check finds nothing, so it isn't a check that always passes.

## The data

- `data/invoices.json`: 4 open invoices, one each for Acme, Birch, Cedar and Delta.
- `data/replies.json`: 4 short customer replies: a promise to pay, a new-PO request, a payment
  claim quoting the wrong invoice number, and a dispute.
- `data/expected.json`: for every reply, the expected outcome and reason, committed before the
  checks existed (the git history shows the order). The field for how each email should be read
  (`intent`) was added later, for the repeat test.

## The result: the repeat test

A model can read the same email differently from run to run, so `repeat.py` read the 4 emails
5 times with each model and scored every reading against `expected.json`.

| | Cheaper (`claude-haiku-4-5`) | Mid-tier (`claude-sonnet-5-5`) |
|---|---|---|
| Emails read as expected | 19 of 20 | 20 of 20 |
| Expected outcome | **20 of 20** | **20 of 20** |
| Exact expected reason | 19 of 20 | 20 of 20 |
| Cost per reply | about $0.0013 | about $0.0034 |

- **The caught wrong invoice:** Cedar quoted INV-1007, which isn't theirs. Both models copied it
  faithfully, every time; the invoice check caught it every time.
- **The cheaper model's slip:** in run 3, it read Delta's dispute as "needs a document" (a corrected
  invoice), even though its own summary said the line "is disputed". Check 5 still sent it to a
  person, so the outcome was right and only the reason differed.

That is 4 emails and 5 runs: enough to show how it behaves, not to rate a model in general.

## Run it

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the two keys

python repeat.py            # reads the 4 emails 5 times per model (40 calls, about 10 cents) and scores them
python test_checks.py       # tests the checks, no model calls
```

To put a run on the screen, copy it into place, then run the checks and actions on it:

```
cp runs/repeats/claude-haiku-4-5-run3.json runs/readings-claude-haiku-4-5.json
cp runs/repeats/claude-sonnet-5-5-run1.json runs/readings-claude-sonnet-5-5.json
python triage.py            # plain code: decides, acts in the AR system, then verifies
streamlit run app.py        # opens the screen
```

The screen shows cheaper-model run 3 (the one with the slip) and mid-tier run 1; `SHOWN_RUN` in
`app.py` says which. `read.py` on its own reads the emails once per model and writes
`runs/readings-<model>.json` directly.

For a demo, only `streamlit run app.py` is needed: it reads the saved runs and makes no model calls.

## The screen

One screen. Across the top, the business results for the run shown: 50% of replies handled without
a collector (2 of 4), 4 of 4 customer replies processed (every action confirmed in the AR system),
2 exceptions routed for review with the reason, and $8,400 of the $21,050 overdue handled
automatically. These come from 4 made-up replies, so they show how it works, not a forecast; the
screen says so. Below that, on the left, each customer's email beside its outcome, the reason, and the actions done,
each with a ✓ checked against the AR system. Cedar's caught wrong invoice comes first. Where the
model misread an email, the row says so. On the right, the AR system after the run: what changed is
in bold, the old value struck through, plus the collector's queue and the outbox. A switch at the
top shows the cheaper or the mid-tier model's run.

## Notes

Every model call is traced in LangSmith (project `collections-triage`) with tokens and cost.

`anthropic` is pinned below 1.0 because LangSmith's `wrap_anthropic` does not yet work with the 1.x
SDK (it looks for the removed `client.completions`).

`read.py` calls `client.beta.messages.parse` rather than `client.messages.parse`. Both do the same
thing, but LangSmith's wrapper only records the beta one; with the plain one, the traces have no
token counts or cost.
