# Parked — not in v1

Out of scope per brief section 11. Written down so they stop taking up space.

- Full web dashboard for the owner (v1 is WhatsApp alerts + a bare /admin page).
- Payments / deposits on booking.
- CRM and dealer-software integrations.
- Mobile app.
- Voice or AI phone calls.
- Marketing broadcasts. *(Note: coexistence kills broadcast lists on the owner's phone, so if he
  wants promos later, template-based sends via the API become the replacement — a real v2 feature.)*
- Multi-branch (several locations under one garage_id).
- RAG / vector search over the price sheet. Only if a garage turns up with a sheet too big for the prompt.
- Google Maps garage scraper for outreach — separate repo, separate brief.

## Built after all

- Post-service follow-up and the service-due nudge. Parked as v1.1, then built, because
  the service-due nudge is the difference between a garage liking the bot and a garage
  renewing: cancelling stops the thing that refills his bay. See `app/followups.py`.

## Ideas that came up during the build
- Owner command to add a price to the sheet from his phone (`/price brake pads suv 450`). Tempting,
  but it is a write path into the one file the "never invent a price" rule depends on. Needs care.
