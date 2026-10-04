# Go live — the remaining work, in order

Everything in the brief is built. What is left needs Care, not code. This is the
whole of it on one page, ordered so nothing waits on something you could have
started days earlier.

Rough shape: **one evening of admin, one visit to the garage, one evening of
typing, one hour connecting the number.**

---

## Tonight — start the Meta application

Going **direct with Meta**, not through a BSP. 360dialog's Partner Program starts at
EUR 250 a month, which is about AED 1,100 before a single garage has paid you anything.
Direct costs nothing per month; the garage pays Meta for what it sends.

**`docs/META-DIRECT.md` is the step by step.** Tonight, in about 45 minutes:

- [ ] Create the Meta app with the WhatsApp use case, on **your** business portfolio.
- [ ] Submit business verification. Trade licence plus proof of address. Two to ten working
      days, and it is the only wait you do not control — everything else runs alongside it.
- [ ] Fill in the app's basic settings: icon, category, and the privacy policy URL.
      The service serves one at `/privacy`; set `OPERATOR_NAME` and `OPERATOR_EMAIL` in `.env`.

That is genuinely all that is unblocked tonight.

**App review comes later**, once you have something to film — Meta wants two screen
recordings, one of a message being sent and one of a template being created, both against
their free test number. And **Embedded Signup is yours to build**: coexistence onboarding
runs through a button you host, which is the one piece of real work in going direct and the
reason BSPs can charge for it. An evening, while verification is in the queue.

**Templates cannot be submitted yet, and this is worth understanding before you plan around it.**
They belong to a WhatsApp Business Account, and Care's account does not exist until his number is
connected. A template approved against a test number does not carry across. So template submission
is step 6 below, not step 1 — and reminders stay silent for the first day or two of the pilot while
Meta reviews them. Everything else works from the first minute.

---

## Ask for the visit

- [ ] Send the first message in `docs/MESSAGES.md` — worded so he can say no easily, which is
      exactly why he will say yes.
- [ ] Send the day-before message the evening before you go. It gets his app updated, which is the
      commonest reason a connection fails at the workshop.

## Before you visit Care

- [ ] Read `docs/STEP0-ONBOARDING-PATH.md`. It is the decision you are executing.
- [ ] Rehearse the bot yourself so you can show it, not describe it:

```bash
python -m app.cli chat --garage demo
```

Ask it a price, book a car, send `/voice`. Each reply prints what happened
behind it. **Do not demo the `care` garage** — its sheet is empty and it will
hand over on everything.

- [ ] Print or open `garages/care/prices.yaml`. It already has Care's own service
      list from their website, with every price left as TODO.

---

## At the garage — one visit, bring a laptop

Everything here is a question only the owner can answer.

**The price sheet** — the whole product depends on this being right.

- [ ] Delete any service he does not actually do.
- [ ] For each one he does: sedan, SUV, luxury. A range is fine and stays a range.
- [ ] If a price genuinely depends on the car, leave it TODO. It hands over, and
      an honest handover beats a wrong number.
- [ ] Add his common jobs that are missing from the website list.

**The five things in `info.yaml` still marked TODO:**

- [ ] His **personal** WhatsApp number for alerts — not the garage number. Alerts
      sent to the garage number arrive in the bot's own inbox and he never sees them.
- [ ] The Google Maps link, sent from Maps rather than typed.
- [ ] `max_cars_per_hour` — how many cars he can genuinely *start* in an hour, not
      how many fit in the workshop. This is what stops the bot filling his morning.
- [ ] Warranty wording, payment methods, and whether he does pickup.
- [ ] Confirm the opening hours. The website says Mon–Sat 08:00–19:00, closed
      Sunday. Websites go stale, and Friday and Ramadan are usually different.

**Before you demo anything, ask the question that decides it:** *"Scroll your WhatsApp back two
weeks. How many messages came in after 7pm, and how many did you answer the same night?"* Forty
against five means you have a business. Three means the premise is wrong for a garage his size,
and better to know now. It costs nothing and it is the most useful hour in this project.

**The pilot terms** — free for a month, price said out loud on day one, and how it ends agreed
before it starts. The wording is in `docs/MESSAGES.md` under "1b. The pilot terms".

**The 30 questions** — ask him to scroll his WhatsApp and read out the ones that
come up over and over. Type them verbatim, including the bad English and the
Roman Urdu. They become the FAQ *and* the test set, and invented questions produce
a bot that passes its own exam and fails on day one.

**Tell him what changes on his phone**, before he agrees to anything. Message 3 in
`docs/MESSAGES.md` is the script; say it out loud before he taps anything. The
broadcast-lists line is the one that matters — it is the only change he might
actually feel, and finding out afterwards is how a pilot dies.

---

## Back at your desk — one evening

- [ ] Type his prices into `garages/care/prices.yaml`.
- [ ] Fill the TODOs in `garages/care/info.yaml`.
- [ ] Replace `tests/questions.yaml` with his real 30, with the expected service,
      car class and price for each.

```bash
python -m app.cli check --garage care     # must print 0 unfilled and no problems
python -m app.cli grade --garage care     # needs ANTHROPIC_API_KEY
```

`grade` is the one that matters. It runs his real questions through the live
model and counts **MISLABEL** — a real price off his sheet, for the wrong
service. Nothing was invented, so no guard catches it; only comparing the reply
to the sheet does. It exits non-zero if any turn up.

- [ ] Fix any mislabels before going near his number. Usually the service names
      in the sheet are too close together and need splitting or renaming.

---

## Deploy — half an hour

Follow `docs/DEPLOY.md` end to end. It assumes nothing is set up yet.

The two settings that fail silently if you skip them:

- [ ] `ADMIN_PASSWORD` — the admin page returns 503 until it is changed.
- [ ] `WEBHOOK_TOKEN` — required with 360dialog, which does not sign its requests.
      Put it on the callback URL: `https://…/webhook?token=…`.

- [ ] `curl https://…/health` returns ok before you go any further.
- [ ] Install `deploy/backup.sh` on cron, run it once by hand, and copy the
      output off the box.

---

## Connecting Care's number — with the owner beside you

Run `ONBOARDING.md` line by line. It is about twenty minutes and he does every tap.

The checks afterwards are not optional. In order of how much they cost if wrong:

1. [ ] **He replies from his phone, and the bot goes silent in that chat.** This
       is the riskiest assumption in the whole build. It was wrong once already —
       see the review commits — and it can only be confirmed on a live number.
2. [ ] `/bot on <customer number>` from his phone brings the bot back.
3. [ ] "brake pads Camry 2019?" answers with his sheet price in under five seconds.
4. [ ] A booking goes end to end and the alert lands on his personal number.
5. [ ] A **voice note** and a **photo** get "an advisor will look and call" —
       not a guess. His customers send these constantly.
6. [ ] He re-links WhatsApp Web if he uses it.

- [ ] Send him message 4 from `docs/MESSAGES.md` — the two commands and your number, so he can
      find it in his chat later rather than on a piece of paper.
- [ ] Watch `journalctl -u mistri -f` for the first hour.

---

## The first week

- [ ] Every morning: `journalctl -u mistri | grep BLOCKED`. Each line is a
      reply the guard stopped, and each one is worth reading.
- [ ] Check `/admin/` for handoffs still open. An unanswered handoff is a customer
      who was told someone would call and nobody did — worse than no bot.
- [ ] Ask him once, on day three, whether anything has annoyed him. Fix that.

## Day thirty — the reason this was built

```bash
python -m app.cli report --garage care --from YYYY-MM-DD --to YYYY-MM-DD
```

That output is what you take to garage number two. Not "AI will transform your
business", but Care's real numbers: how many enquiries, how many arrived after
closing, how many became bookings, how fast the replies were.

Whatever his average ticket is, work out what the after-hours bookings were worth
and put that number in front of the next owner.
