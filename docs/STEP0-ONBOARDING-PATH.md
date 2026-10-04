# Step 0.1 — How to get Care's number onto the Cloud API in coexistence mode

Researched 2026-09-01. Sources at the bottom. **Re-check the two Meta doc links before you act — this area changes every few months.**

## SUPERSEDED — 8 September 2026

This recommended 360dialog for pilot #1 on the basis that their fee was about EUR 49 a
month. That is their *client* price per number. Their **Partner Program**, which is what a
developer onboarding other people's numbers actually needs, starts at **EUR 250 a month** —
around AED 1,100 before a single garage has paid anything.

**The route is now direct with Meta. See `META-DIRECT.md`.** The reasoning below is kept
because the comparison is still sound; only the price was wrong, and it was the price the
whole decision turned on.

## The original decision

**Use a BSP that already supports coexistence (360dialog) for pilot #1.**
Do **not** register as a Meta Tech Provider yet.

## Why

Meta's coexistence onboarding is only reachable through **Embedded Signup run by an approved Tech Provider or Solution Partner**. There is no "self-serve" coexistence button in WhatsApp Manager. So the options are:

| | Route A — BSP (360dialog) | Route B — direct Meta Tech Provider |
|---|---|---|
| Who runs Embedded Signup | 360dialog (already approved) | You — after Meta approves your app |
| Meta App Review for `whatsapp_business_messaging` + `whatsapp_business_management` | not needed by you | **required**, advanced access, before any real customer |
| Meta Business Verification of *your* business | not needed by you | **required** |
| Wait time before pilot #1 can go live | days | weeks, and it is a queue you do not control |
| Cost | ~EUR 49/mo + Meta's own per-conversation fees | Meta fees only |
| Code impact | one module, `app/whatsapp.py` | same module, different base URL + auth header |

For a solo dev doing evenings with a 2-week target, Route B's App Review alone can eat the whole window. Route A gets Care live now.

## Portability — this is why the choice is cheap to reverse

360dialog is a thin proxy over the Cloud API: same `/messages` request bodies, same webhook payload shape. The differences are the **base URL** and the **auth header** (`D360-API-KEY` instead of `Authorization: Bearer`). Keep both behind one interface:

- `app/whatsapp.py` exposes `send_text()`, `send_template()`, `parse_webhook()` and nothing else.
- Provider is chosen by `WA_PROVIDER=meta|d360` in `.env`.
- **No other file in the repo imports `requests` for WhatsApp, ever.**

Switching to direct Meta later = change two env vars. Build the Meta branch too, since the free test number is Meta-direct anyway (see below).

## Do this now — exact steps

### A. Immediately (this is the only queued step)
1. Create a Meta developer app + Business Portfolio at developers.facebook.com, and **start Meta Business Verification** for your own entity. Even on Route A you will want it eventually, and the queue runs in the background while you build. Have trade licence + proof of address ready.
2. Sign up at `hub.360dialog.com` as a **Partner** (Tech Provider Program, free). This gives you the Partner Hub where Care's number will live.

### B. Build against Meta's free test number (parallel, no waiting)
Meta gives every developer app a free test phone number with a handful of free recipient numbers. Point `WA_PROVIDER=meta` at it and build Days 1–12 against it. It behaves like the real Cloud API for everything except coexistence.

### C. When the bot is ready (Days 13–14) — connecting Care's real number
Coexistence onboarding **must be run by the garage owner himself**, on his own phone, signed into his own Meta Business Portfolio. Third parties are not allowed to drive the Embedded Signup flow on the business's behalf. You sit next to him and read `ONBOARDING.md` out loud.

Requirements on his side:
- WhatsApp Business **app version 2.24.17 or newer** (make him update it the day before).
- The number is currently on the **WhatsApp Business app**, not the personal WhatsApp app, and not already on any API.
- He is admin of his own Meta Business Portfolio (create one during the flow if he has none).
- UAE (+971) is a supported country code.

Flow: 360dialog hub -> "Connect your existing WhatsApp Business app" -> enter + verify the number -> a message arrives *inside his WhatsApp Business app* -> he taps it and scans the QR -> chooses whether to sync chat history (say yes: it gives the bot context) -> done. Number is now on the API and still on his phone.

### D. One deadline to know about
Embedded Signup **v2 is deprecated on 15 October 2026** — v4 required, and coexistence onboarding is one of the things that must be re-tested on migration. If you are on 360dialog this is their problem, not yours. If you ever move to Route B, build straight onto v4.

## Limits that apply once coexistence is on (design constraints for us)
- **Throughput caps at ~5 messages/second** on a coexistence number. Fine for one garage; remember it when the daily summary or reminders fan out.
- The owner's replies from his phone are echoed to the API as outbound messages — this is what our handoff pause in section 6 of the brief keys off. Confirm the echo actually arrives during the live test on day 13; it is the single riskiest assumption in the build.
- Group chats are **not** carried over the API. The bot will never see them. Ignore group webhooks entirely.

## Correction to the brief
Section 8.4 of `BRIEF.md` says voice/video calls, group chats and catalog "stop working" on a coexistence number. **That is out of date.** Current behaviour:

- Voice + video calls, Status, catalog/orders and group chats **keep working normally in his app**.
- What actually breaks: **broadcast lists** (existing ones become read-only, no new ones), **disappearing messages**, **view-once**, and **live location** in 1:1 chats; and most **companion-device / WhatsApp Web** logins are restricted — existing Web sessions are unlinked once during setup and must be re-linked.

`ONBOARDING.md` states the corrected list. Verify it against Meta's own coexistence page on the day you onboard, and tell the owner *before* he scans the QR — broadcast lists are the one a garage might actually use for promos.

## Sources
- https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview/
- https://docs.360dialog.com/docs/hub/embedded-signup/coexistence-onboarding
- https://docs.360dialog.com/partner/onboarding/whatsapp-coexistence
- https://docs.360dialog.com/partner/get-started/tech-provider-program
- https://www.infobip.com/docs/whatsapp/manage-integration/coexistence
