# Meta ads automation — architecture and runbook

The ads half of the stack: campaign automation on the Marketing API, and
server-side conversion tracking on the Conversions API. It sits beside the
WhatsApp agent deliberately — the ad produces the lead, the agent answers it, and
the booking the agent takes is the conversion the ad gets optimised on. Split
those across two systems and the optimiser never learns what a good lead was.

```
  Meta ad  ──click──▶  WhatsApp  ──▶  agent (engine.py)  ──▶  booking
     ▲                                                           │
     └──────────── Conversions API: Lead / Schedule ◀────────────┘
```

## Layout

| Module | Responsibility |
|---|---|
| `app/ads/client.py` | The only thing that speaks HTTP to Meta. Retries, errors, paging, redacted write log. |
| `app/ads/campaigns.py` | Campaign → ad set → creative → ad. Everything PAUSED. |
| `app/ads/insights.py` | Reporting. Flattens Meta's `actions` list, computes cost per lead. |
| `app/ads/rules.py` | Budget rules. `evaluate` is pure; `apply` defaults to a dry run. |
| `app/ads/capi.py` | Conversions API. Hashes personal data, deduplicates with `event_id`. |
| `app/ads/cli.py` | `check`, `build-campaign`, `report`, `rules`, `send-event`. |

Same shape as the WhatsApp side: one module owns the transport, so a Graph
version bump or a provider change is a one-file edit.

## The four guarantees

**1. Nothing is created active.** `create_campaign`, `create_ad_set` and
`create_ad` write `status=PAUSED`, with no parameter to override it. Turning
something on is `set_status(id, "ACTIVE")`, a separate call that nothing in the
build path makes, and it logs a warning naming the object. An automation that
can create a live campaign is one bad loop away from spending a month's budget
in an afternoon.

**2. Budgets are in minor units, checked.** `daily_budget_minor=5000` is AED 50.
A float is a `TypeError`, not a conversion — `50.0` means AED 50 to a person and
AED 0.50 to Meta, and silently under-spending by 100× is worse than crashing.
Below Meta's floor is a `ValueError`.

**3. Deciding is separate from doing.** `rules.evaluate` takes rows and budgets
and returns proposed `Action`s. It touches nothing. `rules.apply` carries them
out and defaults to `dry_run=True`. Rules also need a minimum sample
(1,000 impressions and AED 20 spend by default) before they form an opinion, and
no single run can move a budget more than one bounded step.

**4. Personal data is hashed before it leaves.** Every CAPI field Meta expects
hashed is normalised then SHA-256'd inside `capi.py`. There is no flag to skip
it. Hashing an already-hashed value is a no-op, so a double call cannot silently
break matching.

## Credentials

Everything lives in `.env.ads`, which is gitignored. `.env.ads.example` is the
template. Nothing ads-related is read by `app/config.py` — the bot must start and
answer customers whether or not the ads side was ever configured.

| Variable | What it is |
|---|---|
| `META_ADS_ACCESS_TOKEN` | User token with `ads_management`, `ads_read`, `read_insights` |
| `META_SANDBOX_AD_ACCOUNT_ID` | Where **writes** go. Cannot spend money. |
| `META_AD_ACCOUNT_ID` | The live account. **Reads only** — reporting. |
| `META_PAGE_ID` | The page ads run from. Required for creatives. |
| `META_PIXEL_ID` / `META_CAPI_TOKEN` | Conversions API dataset and its token |
| `META_CAPI_TEST_EVENT_CODE` | Set it and events go to Test Events only, never reporting |

`settings.write_account` returns the sandbox when one is set, falling back to the
live account. So the safe thing is the default, and using the live account for
writes takes a deliberate edit.

Tokens from the Graph API Explorer are short-lived; those from Marketing API →
Tools last about 60 days. **Rotate by regenerating on that page** — it revokes
the previous grant, so a leaked token dies when the new one is made.

## Runbook

```bash
# Prove the credentials before building anything on them
python -m app.ads.cli check

# Campaign + ad set + two creative variants, all PAUSED, in the sandbox
python -m app.ads.cli build-campaign --name "JVC buyers - Oct" --budget 5000

# A WhatsApp-destination campaign - the click opens a chat with the agent
python -m app.ads.cli build-campaign --name "JVC WhatsApp" --destination WHATSAPP

# Last 7 days, by ad set
python -m app.ads.cli report --days 7 --level adset

# What the rules would do at a target of AED 50 per lead. Dry run.
python -m app.ads.cli rules --target-cpl 50

# ... and for real
python -m app.ads.cli rules --target-cpl 50 --apply

# A server-side lead event from a WhatsApp conversation
python -m app.ads.cli send-event --event lead --phone +971588129679
```

### When something looks wrong in an ad account

The write log answers "did we do that". Every non-GET call is logged before it
is sent, with the path and the body, tokens and personal data redacted:

```
INFO mistri.ads meta write POST act_1386.../campaigns {'name': 'JVC buyers - Oct', 'status': 'PAUSED', ...}
```

### When a report shows no leads but the agent is busy

Check `LEAD_ACTIONS` in `insights.py`. Meta reports a WhatsApp conversation under
`onsite_conversion.messaging_conversation_started_7d`, not `lead`; a new
destination type can introduce an action type that is not in that set yet.

### When conversions are double counted

The browser pixel and the server are both reporting and the `event_id` does not
match. Both sides must send the same id for the same event — that is the entire
mechanism, and without it CPL reads at half its real value and the budget rules
act on a fiction.

## What is not built yet

- **Lead Ads form ingestion** (`leadgen` webhook) — would let a form submission
  land straight in the agent's queue.
- **Automated creative generation.** Variants are hand-written; the copy is the
  one part worth a human.
- **Attribution back to revenue.** `Schedule` is reported, but value is whatever
  the caller passes. Closing the loop needs the CRM's actual deal value.

## Tests

```bash
.venv/Scripts/python -m pytest tests/test_ads.py -q      # 33 tests, no network
```

Meta is stubbed with `httpx.MockTransport` throughout. The tests assert the
guarantees rather than the happy path: that a malformed request is **not**
retried while a rate limit is, that every object is created paused, that a float
budget raises, that a dry run touches nothing, that the same person hashes
identically however their phone number was typed, and that a token never reaches
a log line.
