# Mistri — START HERE

**Mistri** (مستري / मिस्त्री) is what half of Dubai already calls the mechanic. The name travels
across all four languages the bot speaks, and it never says "bot" or "AI" on purpose — what is
being sold here is trust, not technology.

WhatsApp assistant for car garages. First customer: **Care Auto Repair Services, Dubai** (careautorepair.ae).
Runs on the garage's existing WhatsApp Business number in **coexistence mode**. Multi-garage from day one.

## Read in this order
1. `GO-LIVE.md` — **what to do next, in order.** The rest is reference.
2. `BRIEF.md` — the original build brief (source of truth for scope).
3. `docs/Mistri-Documentation.pdf` — what the tool is, every feature, what it will never do. The one to send someone.
4. `docs/META-DIRECT.md` — going direct with Meta as a Tech Provider. **This is the route.**
5. `docs/STEP0-ONBOARDING-PATH.md` — the original 360dialog decision, kept for the reasoning — **decision made: go via a BSP (360dialog), not direct Tech Provider.** Read this before touching Meta.
6. `ONBOARDING.md` — the checklist you run *with the garage owner* when connecting his real number.
7. `templates/SUBMIT.md` — the twelve template submissions, paste-ready. Do this tonight.
8. `docs/MESSAGES.md` — what to send the owner, and when — the 3 message templates to submit early (they gate reminders).
9. `LATER.md` — parked ideas. Do not build them in v1.

## Doing the remaining work

**[GO-LIVE.md](GO-LIVE.md)** is the whole of it on one page, in order. Start there.

## Where it stands

Everything in the brief is built, plus the v1.1 follow-ups. 296 tests pass, and
`tests/README.md` says what each file proves. Two review passes are in the git
log - read those commit messages before changing anything in `whatsapp.py` or
`guard.py`, because they explain defects that were invisible to a green suite.

What is left needs Care, not code, and it is all sequenced in `GO-LIVE.md`:
templates submitted tonight, one visit to get the prices and the real 30
questions, one evening typing them in, then the number connected.

`garages/care/` is already pre-filled with their published address, hours and
service list, so the owner is correcting rather than dictating. Every price is
a TODO on purpose - none of them are published, and none are guessed.

## Status
- [x] Step 0.1 — onboarding path researched and decided (2026-09-01)
- [ ] Step 0.2 — Meta business verification / BSP account started  ← **Noman, do this first, it is the only step with a queue**
- [ ] Step 0.3 — 3 message templates submitted
- [x] Step 0.4 — `ONBOARDING.md` written
- [ ] Days 1–2 — webhook + DB + logging
- [x] Days 3–5 — reply engine, price guardrails, 40 adversarial tests (needs Care's sheet + 30 questions to finish)
- [x] Days 6–8 — booking flow, slots, confirmation, owner alerts
- [x] Days 9–10 — handoff, owner commands, auto-release, reminders, 6 pm summary
- [x] Days 11–12 — admin page, report + check commands, systemd/nginx deploy
- [x] v1.1 — post-service follow-up and service-due nudge
- [ ] Days 13–14 — Care's real number live

## The demo garage

`garages/demo/` is a complete, invented Dubai garage — 14 services, every price filled,
hours, warranty, pickup. It exists so `chat`, `grade` and a sales demo all work before any
real garage has handed over a sheet. It is flagged `demo: true`, so a live WhatsApp number
can never be routed to it.

## Two things Noman must supply before Days 3–5
- Care's price sheet (services x sedan / SUV / luxury, or per model).
- Top 30 real questions from Care's WhatsApp chat history.
