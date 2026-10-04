# WhatsApp AI Assistant for Garages — v1 Build Brief

**Project:** Mistri (working name). First customer: Care Auto Repair Services, Dubai (careautorepair.ae).
**Developer:** Noman — solo, evenings only. Target: working v1 on the garage's real number in ~2 weeks.
**Read this whole file, then start with Step 0 (section 8).**

---

## 1. What we are building

A WhatsApp assistant that runs on a garage's **existing WhatsApp Business number** through Meta's Cloud API in **coexistence mode**: the owner keeps using the WhatsApp Business app on his phone as always, and the bot runs on the same number behind it.

Customers message the garage's normal number. The bot:

- answers price questions from the garage's own price sheet
- answers hours / location / payment / warranty / pickup questions from a FAQ
- books appointments and sends a confirmation with a maps link
- sends booking reminders
- hands over to a human for anything outside the sheet

Nothing installs on anyone's phone. The bot is a Python service on Noman's existing AlmaLinux VPS.

Build it **multi-garage from day one** (`garage_id` on every table and every config): the same product will be sold to other Dubai garages.

---

## 2. Non-negotiable rules — these ARE the product

1. **Never invent a price.** Quote only what is in the garage's price sheet, exactly as written (fixed price or range). If the service or car is not on the sheet → offer a free inspection and alert the owner.
2. **Never diagnose.** Messages like "noise", "smell", "warning light", "not starting", "problem" → collect car make / model / year + the symptom → book an inspection. No guessing causes, no guessing prices.
3. **Hand over when unsure.** Anything outside sheet + FAQ → reply "Our service advisor will call you shortly" → send the owner a WhatsApp alert with a 3-line chat summary and the customer's number → bot stops replying in that conversation until released (see section 6).
4. **Speak the customer's language.** English, Arabic, Hindi/Urdu (script or Roman). Reply in the same language and script the customer used.
5. **WhatsApp tone.** 1–4 short lines per reply. No essays, no bullet lists, no marketing voice. One question at a time.
6. **Log everything.** Every inbound and outbound message with timestamps. The pilot metrics (section 7) depend on this.

---

## 3. Stack

- **Python 3.11+, FastAPI, uvicorn.** Deployed as a **systemd** service on the AlmaLinux VPS behind **nginx** with HTTPS (Let's Encrypt). Meta webhooks require a public HTTPS endpoint.
- **WhatsApp:** Meta WhatsApp Cloud API — webhooks in, Graph API `/messages` out. Keep the WhatsApp layer in one module using the Cloud API message format, so a BSP (360dialog / YCloud style) can be swapped in later without touching bot logic.
- **LLM:** Anthropic API. Start with `claude-sonnet-5` for reply quality; once behaviour is stable, benchmark `claude-haiku-4-5-20251001` for cost. Confirm current model IDs at docs.claude.com before use. All prompts live in `prompts/`, nothing hard-coded in logic.
- **DB:** SQLite via SQLAlchemy for v1. Tables: `garages`, `conversations`, `messages`, `bookings`, `handoffs`. Design so moving to Postgres later is a connection-string change.
- **Garage knowledge:** one folder per garage — `garages/care/` containing `prices.yaml` (services × car category: sedan / SUV / luxury, or per-model where the garage prices that way), `faq.yaml`, `info.yaml` (hours, address, maps link, payment methods, warranty, pickup, `max_cars_per_hour`, owner alert number). Loaded into the system prompt at request time. **No vector DB / RAG in v1** — the sheet is small.
- **Scheduler:** APScheduler for reminders and the daily summary.
- **Security:** verify webhook signature (`X-Hub-Signature-256`) and verify token; secrets only in `.env`; admin page behind basic auth.

---

## 4. Conversation flows (v1)

1. **Price question** → identify service + car (ask make / model / year if missing) → quote from `prices.yaml` → offer the next available slots.
2. **Booking** → collect name, car, service, preferred day/time → check garage hours + slot capacity → confirm → write `bookings` row → send confirmation with maps link → alert owner.
3. **Info question** (open? where? pickup? card? warranty?) → answer from `faq.yaml` / `info.yaml`.
4. **Symptom / diagnosis** → rule 2 → book inspection.
5. **Anything else or unsure** → rule 3 handoff.
6. **Reminders** → 1 day before and the morning of the booking (template messages — see section 8).
7. **Follow-ups — v1.1, only if time remains** → 2 days after service: "how was it?"; service-due nudge after N months (N in `info.yaml`).

---

## 5. Owner side (no dashboard in v1)

- Alerts to the owner's personal WhatsApp number: new booking, handoff request, and a **daily 6 pm summary** (conversations, bookings, handoffs, after-hours messages).
- Minimal `/admin` page (basic auth): list of conversations with transcript, list of bookings. Nothing more.

---

## 6. Human ↔ bot handoff behaviour

- In coexistence mode, messages the owner sends from his phone app are echoed to the API. Treat any outbound message **not sent by the bot** as "owner is handling this" → pause the bot in that conversation for 2 hours (configurable). The bot never talks over the owner.
- Owner can force-release a conversation with a simple command sent to the bot from his own number (e.g. `/bot on 0501234567`).
- A handed-off conversation auto-releases after 24 hours of silence.

---

## 7. Pilot metrics — the anti-hype test (must ship in v1)

Build a CLI command `report --garage care --from YYYY-MM-DD --to YYYY-MM-DD` that prints:

- total conversations, and how many started **outside garage hours**
- price questions answered
- bookings created
- handoffs
- median bot reply time
- language breakdown

This report is the sales proof for garage #2. Design the schema so these are plain queries.

---

## 8. Step 0 — do this BEFORE writing bot code

1. **Verify the current Meta coexistence onboarding path** for a solo developer: registering as a Tech Provider with Embedded Signup vs. using a BSP that already supports coexistence. Recommend the fastest path for pilot #1 that keeps the code portable. List exact steps, required approvals (business verification, app review for `whatsapp_business_messaging` / `whatsapp_business_management`), phone-number requirements, and expected wait times.
2. **Start Meta business verification / app review immediately.** It is the only step with waiting time. Build everything else against Meta's free **test number** in the meantime.
3. **Draft and submit message templates early:** booking reminder, service-due, post-service follow-up. Reminders go outside the 24-hour customer window and need approved templates.
4. **Write `ONBOARDING.md`** — the owner-facing checklist for connecting a garage's number: WhatsApp Business app updated to 2.24.17 or newer; tap the Meta message → scan the QR code; choose chat-history sync. Include the known coexistence limits to tell the owner **before** connecting: WhatsApp voice/video calls, group chats, broadcast lists and catalog stop working on that number (normal phone calls are unaffected — same SIM); WhatsApp Web sessions are unlinked once during setup and must be re-linked.

---

## 9. Build order (~2 weeks, evenings)

1. **Days 1–2** — repo, FastAPI webhook verify / receive / send with the test number, DB, logging.
2. **Days 3–5** — Care knowledge files (Noman supplies the price sheet + top 30 questions from Care's chat history) + reply engine with the rules + language handling. Test against those 30 real questions.
3. **Days 6–8** — booking flow, slots, confirmation, owner alerts.
4. **Days 9–10** — handoff + pause behaviour, reminders via templates.
5. **Days 11–12** — `/admin` page, `report` command, systemd + nginx + HTTPS deploy.
6. **Days 13–14** — connect Care's real number (coexistence), run `ONBOARDING.md` for real, live test, fix.

---

## 10. Definition of done

- Care's **real** number answers "brake pads Camry 2019?" with the sheet price in under 5 seconds, offers slots, books one, and the owner receives the alert.
- A test set of **100 questions** — including 20 trick questions asking for prices not on the sheet and 20 symptom messages — produces **zero invented prices and zero diagnoses**. Ship the test set in `tests/`.
- `report` prints correct numbers for the test period.

---

## 11. Out of scope for v1 — do not build

Full web dashboard, payments, CRM / dealer-software integrations, mobile app, voice or AI calls, marketing broadcasts, multi-branch features, RAG / vector search. Note any of these ideas in `LATER.md` and move on.

The Google Maps garage scraper for outreach is a **separate repo with its own brief** — not part of this build.
