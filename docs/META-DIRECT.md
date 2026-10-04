# Going direct with Meta — the Tech Provider application

No platform fee. No BSP in the middle. The garage pays Meta directly for what it
sends, and Meta charges nothing for you to be the provider.

The cost is time: business verification and app review both sit in Meta's queue.
Start tonight, because nothing you do afterwards makes them go faster.

**Why this and not 360dialog:** their Partner Program starts at €250/month, which
is about AED 1,100 before a single garage has paid you anything. Their client
plan (~€49/number/month) works but eats half the revenue of one garage. Direct
costs nothing per month and the garage covers its own message fees.

---

## What you are applying to be

A **Tech Provider**: a developer whose software other businesses use to message
their customers. Not a business messaging its own customers.

That distinction matters at every step. You are not connecting Mistri's number.
You are building the thing Care — and later garage two — connects *their* number to.

---

## Before you start, have these ready

- **Trade licence** for your business, and proof of address (utility bill or
  tenancy contract). Business verification will not pass without them.
- **A business email** on your own domain if you have one. A gmail address is
  accepted but slows verification down.
- **A public privacy policy URL.** This is now required before an app can be
  cleared to send. The service serves one at `/privacy` — put it behind your
  domain once deployed, e.g. `https://bot.yourdomain.ae/privacy`.
- **An app icon.** 1024×1024 PNG. Anything clean; it is shown to the garage owner
  during onboarding, so it should not look like a placeholder.

---

## Step 1 — Create the app (tonight, 15 minutes)

1. `developers.facebook.com` → My Apps → Create App.
2. Choose the **WhatsApp** use case.
3. Connect it to a **business portfolio** — yours, not Care's. Create one if you
   have none.
4. In the WhatsApp panel, note the **test phone number** Meta gives you for free.
   That is what you build and record demo videos against.

## Step 2 — Start business verification (tonight, 20 minutes)

Business Settings → Security Centre → Start Verification. Upload the trade licence
and proof of address.

**Two to ten working days.** This is the long pole. Everything else can be done
while it runs, so do not wait for it before moving on.

Until it clears you are capped at 250 business-initiated conversations per 24
hours, which is far more than one garage will ever need — so a slow verification
does not block the pilot, only growth.

## Step 3 — Fill in the app's basic settings (tonight, 10 minutes)

App Settings → Basic:

- Display name, icon, category
- **Privacy Policy URL** — required, see above
- App domain

Skip any of these and app review is refused without being read.

## Step 4 — Submit for app review (once you have something to film)

You are asking for **advanced access** to two permissions:

| Permission | Why you need it |
|---|---|
| `whatsapp_business_messaging` | To send and receive messages on the garage's number |
| `whatsapp_business_management` | To read the garage's WABA and submit templates |

The submission needs **two screen recordings**:

1. A message being sent from your software and arriving in WhatsApp.
2. A message template being created from your software.

Record both against the test number. Show the whole path — your admin page, then
the phone receiving it. Meta rejects videos that only show a terminal.

Do not describe the app as a chatbot for yourself. Describe it as what it is:
software that garages use to answer their own customers on their own numbers.

## Step 5 — Build Embedded Signup (while you wait)

This is the one piece of real work in going direct, and it is why BSPs can charge.

Coexistence onboarding is a **configuration of Embedded Signup**, and Embedded
Signup is something the Tech Provider builds into their own product. There is no
self-serve coexistence button anywhere — the garage owner has to click a button
that *you* host.

What it involves:

- A page with a "Connect your WhatsApp" button, using Meta's JavaScript SDK.
- The flow configured for **existing WhatsApp Business app users** — that is the
  coexistence option.
- Session logging turned on. Meta requires it and rejects integrations without it.
- A callback that receives the code, exchanges it for a token, and stores the
  **WABA ID** and **phone number ID** against that garage.
- Build it on **Embedded Signup v4**. v2 is deprecated on 15 October 2026, so
  starting on v2 would mean rewriting it within weeks.

Roughly an evening's work on top of what exists. It slots in beside the admin
page and stores into the `garages` table that is already there.

## Step 6 — Point Meta at the service

Callback URL `https://your-domain/webhook`, the verify token from `.env`,
subscribed to the **messages** field. `docs/DEPLOY.md` covers this.

## Step 7 — The garage adds a payment method

As a Tech Provider — unlike a Solution Partner — **the garage pays Meta directly**.
Care adds a card to their own WhatsApp Business Account.

This is better for you: no float, no invoicing anyone for message fees, no
argument about what a conversation costs. But it is one more thing the owner does
at onboarding, so tell him in advance rather than surprising him with a card form
while he is standing in the workshop.

Costs him very little in practice. Customer-initiated service conversations are
free; he pays only for template messages, which for a garage means the booking
reminders — a few fils each.

---

## Realistic timeline

| | |
|---|---|
| Tonight | App created, verification submitted, settings filled in |
| Days 2–10 | Business verification in the queue. Build Embedded Signup meanwhile |
| Once you can film it | App review submitted. Usually days, sometimes a fortnight |
| After approval | Connect Care's number through your own onboarding page |

**If Care is ready before Meta approves you**, fall back to having Care open a
360dialog *client* account (~€49/month) for the pilot, and move him across once
your own approval lands. `app/whatsapp.py` is the only file that changes, and it
changes by two environment variables.

---

## The one thing to get right

Apply as a **Tech Provider**, with the app connected to **your** business
portfolio, describing software that other businesses use.

Apply as a business wanting to message its own customers and you will be approved
for the wrong thing, find out when you try to onboard Care, and start again.
