# Connecting a garage's WhatsApp number — owner checklist

Run this **with the owner, in person or on a call**. It takes about 20 minutes.
He does every tap himself: Meta does not allow us to run this flow on his behalf.

---

## Before the day — tell him this first

His number keeps working exactly as it does now. He keeps using the WhatsApp Business app on his phone. But a few things change, and he should hear it from you before he agrees, not after:

**Stops working on this number**
- **Broadcast lists** — he cannot create new ones, and existing ones become read-only. *(Ask him directly: does he send promos this way? If yes, this is the real cost of the deal — say so.)*
- Disappearing messages, view-once messages, and live location in 1:1 chats.
- **WhatsApp Web / linked devices** — his sessions are unlinked once during setup, and he must re-link afterwards. Some companion-device logins stay restricted.

**Keeps working normally**
- Voice and video calls in WhatsApp. Normal phone calls too, obviously — same SIM.
- Group chats (but the bot cannot see them, so the bot will never reply in a group).
- Status, catalog, orders.
- All his existing chats and contacts.

**Also worth saying out loud**
- The bot replies only about prices on his own sheet, hours, location, and bookings. It never guesses a price and never diagnoses a problem.
- The moment *he* replies to a customer from his phone, the bot goes quiet in that chat for 2 hours. He is always in charge.
- He gets a WhatsApp alert for every booking and every handoff, plus a 6 pm daily summary.

---

## Rehearse it first

Before the owner is anywhere near it, have the conversation yourself:

```bash
python -m app.cli chat --garage care
```

Same engine, same guard, same booking rules - it prints instead of sending. Each reply is
followed by what happened behind it: which price came off the sheet, whether the guard
blocked anything, whether it handed over. Run his real top-30 questions through this before
he ever sees it.

## The day before

- [ ] Owner updates the **WhatsApp Business app to 2.24.17 or newer** (App Store / Play Store). Check the version with him — an old app is the #1 reason this flow fails.
- [ ] Confirm the number is on the **WhatsApp Business** app, not personal WhatsApp, and is not already connected to any other API or chatbot tool.
- [ ] Confirm he can log into a **Meta Business Portfolio** as admin (business.facebook.com). If he has none, we create one during the flow — have his trade licence handy.
- [ ] Phone charged, on wifi, and he has the number's SIM in hand for OTP.
- [ ] We have: his **personal** WhatsApp number for owner alerts, the garage's price sheet loaded in `garages/<id>/prices.yaml`, hours + address + maps link in `info.yaml`.

## On the day — the flow

1. We open **your own onboarding page** (`/onboard` on your domain) and start the connection
   for his number. That page is the Embedded Signup button you host as a Tech Provider — see
   `docs/META-DIRECT.md`. If your Meta approval has not landed yet and you are using a BSP for
   this pilot, it is their hub instead; everything from step 2 is identical either way.
2. He signs in with **his own** Facebook/Meta account and picks his Business Portfolio.
3. He chooses **"Connect your existing WhatsApp Business app"** — not "use a new number".
4. He types the number again and verifies it (OTP).
5. A message from Meta arrives **inside his WhatsApp Business app**. He opens it and follows the prompt.
6. He **scans the QR code** shown on our screen.
7. He is asked whether to **sync chat history** — say **yes**. It gives the bot recent context and it is where our top-30-questions list comes from.
8. Wait for the hub to show the number as connected.

## Right after connecting

- [ ] He re-links **WhatsApp Web** if he uses it.
- [ ] Send a test message from a different phone: "brake pads Camry 2019?" — expect the sheet price back in under 5 seconds.
- [ ] Book a slot end to end. Confirm the maps link opens correctly.
- [ ] Confirm the **owner alert** lands on his personal number.
- [ ] Owner replies to the test chat from his phone. Confirm the bot goes silent in that chat. **This is the riskiest assumption in the whole build — verify it here, not in production.** If it fails, check `journalctl` for the `display_phone_number` Meta actually sent: matching it is what decides whether a message is his.
- [ ] Owner sends `/bot on <customer number>` from his phone. Confirm the bot resumes.
- [ ] Send a **voice note** and a **photo** from the test phone. Expect the bot to say an
      advisor will look and call - not to guess. Garage customers send these constantly.
- [ ] Leave him a note with the commands below, and your number for anything odd.

## The commands he can send

He types these from his own phone, either **inside a customer's chat** (where a command
with no number means that chat) or **to the garage number from his personal phone**
(where no number means every chat).

| He sends | What happens |
|---|---|
| `/bot off` | Bot stops replying - that chat, or everywhere |
| `/bot on` | Bot starts again |
| `/bot off 0501234567` | Bot stays out of that one customer's chat |
| `/bot on 0501234567` | Bot takes that chat back |
| `/status` | Today's numbers, in a message |
| `/help` | The list above |

It is forgiving about format: capitals, spacing, `+971`, `050`, brackets and dashes all work.
Tell him `/bot off` is the brake pedal, and that he does not need it - the bot already goes
quiet on its own the moment he types a normal reply to a customer.

## If something goes wrong

| Symptom | Cause |
|---|---|
| QR step never appears | App below 2.24.17, or number is on personal WhatsApp |
| "Number already registered" | Number is on another API / chatbot tool — must be released there first |
| Flow blocked at portfolio step | He is not an admin of the Business Portfolio |
| Bot silent after connecting | Webhook URL / verify token, or the paused-conversation flag is stuck |
| Bot talks over the owner | Outbound echo not arriving — check webhook payloads for his own sent messages |

## Undo

Coexistence can be disconnected from the WhatsApp Manager / hub. The number goes back to being app-only. Chats stay on his phone. Tell him this up front — it makes saying yes much easier.
