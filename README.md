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
- **Evidence:** on the 4 demo replies, both models' facts were enough for the checks to reach the
  expected outcome every time. On 30 harder cases, only the mid-tier model's were: the cheaper one
  missed required escalations in 15 of 150 test runs, concentrated in disguised disputes (see "The
  evaluation set").

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
| Tests of the rules, including the known gap | Plain code | `test_checks.py` |
| The repeat test: 4 demo emails, 5 runs per model | Model + rules | `repeat.py` |
| The evaluation: 30 harder emails, 5 runs per model | Model + rules, results in LangSmith | `eval_cases.py` |

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
| Cost per reply | about $0.0013 | about $0.0033 |

- **The caught wrong invoice:** Cedar quoted INV-1007, which isn't theirs. Both models copied it
  faithfully, every time; the invoice check caught it every time.
- **The cheaper model's slip:** in run 3, it read Delta's dispute as "needs a document" (a corrected
  invoice), even though its own summary said the line "is disputed". Check 5 still sent it to a
  person, so the outcome was right and only the reason differed.

That is 4 emails and 5 runs: enough to show how it behaves, not to rate a model in general.

## The evaluation set: 30 harder cases

The 4 demo replies show how it works; they can't show how far it can be trusted. `eval_cases.py`
runs both models on 30 cases (`eval/cases.json`, expected outcomes reviewed by Andrew), 5 times
each: 150 readings per model, the full pipeline every time. A third of the cases are aimed at the
known gap (disputes worded as promises, deductions, two invoices with the same amount). Results are
in LangSmith (dataset `collections-triage-eval`, one experiment per model) and `eval/results.json`.

| | Cheaper (`claude-haiku-4-5`) | Mid-tier (`claude-sonnet-5-5`) |
|---|---|---|
| Correct outcome | 135 of 150 | **150 of 150** |
| **False Handled** (should have gone to a person) | **15 of 150** test runs | **0 of 150** |
| False escalation (sent to a person needlessly) | 0 | 0 |
| Cost per reply | about $0.0013 | about $0.0037 |

**Every false Handled was the known gap.** The cheaper model read a dispute as a promise to pay
("will pay by Oct 30, but apply the 10% your rep promised"; "less the onboarding charge"; "as soon
as you fix the training charge") or as a document request ("send a new PO form; also, line 1 is
priced above contract"). The invoice and the date were real, so every rule passed. The mid-tier
model read all four as disputes, every time.

**What it means:** on the 4 demo emails the two models looked equal. On harder cases the cheaper
one missed required escalations in 15 of 150 test runs, all of them disguised disputes. The
mid-tier model costs about $24 more per 10,000 replies; one disputed invoice marked Handled (these
were $950 to $7,450) costs more than that in collector time and customer trust. So the reading step
should use the mid-tier model.

**The finding about the rules:** rules protect the workflow only when they get complete, accurate
facts. If the reading step misses a dispute entirely, the rules can't see what's missing. That's
the most important result here, and the reason the reading model matters even though it doesn't
decide.

**What it doesn't mean:** 15 of 150 is not a real-world miss rate. The 150 runs are 30 emails
read 5 times each, not 150 different customers, and the hard cases were deliberately
over-represented. A real rate needs real replies. Likewise, 0 of 150 is not "never". The 5 runs
repeat the same 30 emails, so they aren't independent; with 30 distinct cases, a rough upper bound
on the mid-tier model's miss rate
is about 1 in 10 (the rule of three: 3 ÷ 30). More, and real, cases would narrow it. That is what
the pilot's side-by-side period is for.

**Not built, worth testing in a real deployment:** the cheaper model for reading, plus a separate,
independent check that looks only for disputes. If that matched the mid-tier model's reliability, it
would be cheaper. It's an optimization for later, not part of this demo.

## Run it

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the two keys

python repeat.py            # reads the 4 emails 5 times per model (40 calls, about 10 cents) and scores them
python test_checks.py       # tests the checks, no model calls
python eval_cases.py        # the 30-case evaluation (300 calls, under a dollar), results to LangSmith
```

To put a run on the screen, copy it into place, then run the checks and actions on it:

```
cp runs/repeats/claude-haiku-4-5-run3.json runs/readings-claude-haiku-4-5.json
cp runs/repeats/claude-sonnet-5-5-run1.json runs/readings-claude-sonnet-5-5.json
python triage.py            # plain code: decides, acts in the AR system, then verifies
streamlit run app.py        # opens the screen
```

The screen shows mid-tier run 1, the model the evaluation chose. `read.py` on its own reads the
emails once per model and writes `runs/readings-<model>.json` directly.

For a demo, only `streamlit run app.py` is needed: it reads the saved runs and makes no model calls.

## The screen

One list: each customer's email beside its outcome and the reason. Handled replies show the actions
done, each with a ✓ only if it's found in the saved AR system. Cedar's caught wrong invoice comes
first. It shows the mid-tier model's run, the model the evaluation chose.

The rest of the evidence (the AR system before and after, the cheaper model's Delta misread, the
evaluation) lives in `runs/`, `eval/results.json` and LangSmith, not on the screen.

## Notes

Every model call is traced in LangSmith (project `collections-triage`) with tokens and cost.

`anthropic` is pinned below 1.0 because LangSmith's `wrap_anthropic` does not yet work with the 1.x
SDK (it looks for the removed `client.completions`).

`read.py` calls `client.beta.messages.parse` rather than `client.messages.parse`. Both do the same
thing, but LangSmith's wrapper only records the beta one; with the plain one, the traces have no
token counts or cost.
