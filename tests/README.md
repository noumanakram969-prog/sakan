# Tests

```bash
.venv/Scripts/python -m pytest tests/ -q
```

No API key needed. Every test here stubs the model, on purpose.

## What is covered

| File | What it proves |
|---|---|
| `test_pricing.py` | A price is retrieved from the sheet or it does not exist. Ranges stay ranges, `TODO` is not quotable, an unknown car is not "close enough". |
| `test_guard.py` | Nothing leaves carrying a number the facts do not support, and nothing mentions money unless a price was actually looked up. |
| `test_engine.py` | The whole turn: off-sheet requests hand over, symptoms are never priced, a model that invents a price is blocked, handoffs speak the customer's language. |
| `test_adversarial.py` | The 40 adversarial questions from the definition of done, run against a model stub that invents a price and names a cause **every single time**. |
| `test_slots.py` | Opening hours, closed days, the lead time, capacity per hour, and the local/UTC boundary. |
| `test_booking.py` | Gathering one field at a time, offering only real slots, refusing a closed day or a full hour, writing the row, and the race between offering a slot and confirming it. |
| `test_commands.py` | Owner commands parsed however he types them, the mute rules they drive, and the 24-hour auto-release. |
| `test_reminders.py` | The right reminder at the right hour, once, with the template variables in declared order - and a failed send that retries rather than being swallowed. |
| `test_report_admin.py` | The pilot report's numbers (median is a median, nothing outside the window counts), the CLI, and the admin page - including that a customer's message is escaped, not executed. |
| `test_grade.py` | The grading logic, and that every expected price in `questions.yaml` still matches the demo sheet - so an edited sheet cannot quietly turn the set green. |
| `test_followups.py` | The post-service message and the service-due nudge - mostly about when NOT to send: mid-conversation, twice, or to somebody who has been back since. |
| `test_startup_and_journey.py` | That the application actually starts - real lifespan, scheduler up, all four jobs registered - and that one customer gets from a price question through booking, reminders and follow-up on the real demo sheet. |
| `test_security.py` | The four findings from the pre-go-live review, each pinned so a refactor cannot bring them back. |
| `test_webhook.py` | Webhook to reply, end to end: signature checks, redelivery, the outbound message, the owner alert, the bot going quiet when the owner types, and the daily reply cap. |

## Why the model is stubbed

The guarantee this product sells is not "the model behaves well". It is "it does not matter whether the model behaves well". So the tests hand it the worst possible model — one that confidently quotes AED 950 for an alternator on every turn — and assert the customer never sees any of it.

A test that needs a real API call to pass would be proving the opposite thing.

## What these tests do NOT cover

**Classifier mislabelling.** (Measured by `grade`, not by these tests.)

Old note, kept because it is still the shape of the risk: If the classifier reads "rear brake pads" as `brake_pads_front`, the price that comes back is a real price from the sheet — just the wrong row. The guard cannot catch that, because nothing was invented.

Two things stand between that and an angry customer, and neither is a unit test:

1. The reply echoes what it matched ("Front brake pads, Camry 2019 — AED 450"), so the customer sees the mistake before arriving.
2. The confidence floor in `engine.CONFIDENCE_FLOOR` — below 0.7 the bot hands over instead of quoting.

Measuring the real mislabel rate needs the live model and Care's real sheet. That is the other 60 questions.

## The graded set — `questions.yaml`

40 adversarial questions run offline, here. The other half are ordinary questions that **should** be answered, and they need the live model, so they are a command rather than a test:

```bash
python -m app.cli grade --garage demo
```

`questions.yaml` holds 30 of them today, written against `garages/demo`. They are invented — what a Dubai garage's WhatsApp looks like — because Care have not handed over their chat history yet. **Replace this file with their real top 30 when they do.** Real customers ask worse questions than anyone imagines, and that is the point of asking for theirs.

What it scores:

| Verdict | Meaning |
|---|---|
| `MISLABEL` | A real price off the sheet, for the wrong service or wrong car class. **The one that matters.** |
| `PRICED A SYMPTOM` | Quoted for a fault instead of booking an inspection |
| `blocked by the guard` | The composer tried to invent something and was stopped |
| `unnecessary handover` | Could have answered, handed over instead. A nuisance, not a risk |

`grade` exits non-zero on any mislabel, so it can gate a go-live.

Mislabels are the failure nothing in the offline suite can catch: nothing was invented, so no guard objects. Only comparing the reply to the sheet finds them.
