---
name: mistri-project
description: Mistri - WhatsApp assistant for Dubai car garages (first customer Care Auto Repair); repo in OneDrive\FRESH DATA\mistri, read START-HERE.md first.
metadata:
  type: project
---

Mistri (working name until 2026-09-08: Garage Bot) — WhatsApp assistant running on a garage's existing WhatsApp Business number in
Meta coexistence mode. First customer: Care Auto Repair Services, Dubai. Built multi-garage
from day one (`garage_id` everywhere) to resell to other Dubai garages.

Repo: `C:\Users\user\OneDrive\FRESH DATA\mistri` (see
[[projects-live-under-onedrive-root]]). Read `START-HERE.md`, then
`docs/STEP0-ONBOARDING-PATH.md`. `BRIEF.md` in the repo is the scope source of truth.
Python 3.11 / FastAPI / SQLAlchemy+SQLite / Anthropic API, deployed to Noman's AlmaLinux VPS.

Named **Mistri** on 2026-09-08 (the Hindi/Urdu word for mechanic), chosen over Warsha,
Service Advisor and Second Bay. Started 2026-09-01. Step 0 done (onboarding path, ONBOARDING.md, template drafts) plus
Days 1–2 (webhook, DB, logging). Target: live on Care's real number in ~2 weeks, evenings only.

**Why:** Two decisions that are expensive to re-derive. (1) Onboarding goes through 360dialog
as BSP, not direct Meta Tech Provider — App Review + business verification would consume the
whole build window. (2) The product IS the rules: never invent a price, never diagnose, hand
over when unsure. Those are not polish, they are the sales pitch.

**How to apply:** Keep all WhatsApp traffic inside `app/whatsapp.py` so the BSP→Meta-direct
switch stays a two-env-var change. Never let the model quote a price that is not literally in
`garages/<id>/prices.yaml`. The riskiest untested assumption is that coexistence echoes the
owner's own phone-sent replies to the webhook — the bot-pause behaviour depends on it entirely.
Plain wording in all customer-facing copy, per [[user-prefers-simple-plain-wording]].
