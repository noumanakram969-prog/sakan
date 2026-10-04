# Message templates — submit these on day 1

Reminders and follow-ups go **outside** the 24-hour customer service window, so they must be
pre-approved templates. Approval is usually minutes to a day, but a rejection costs a round trip —
submit early, before the code that uses them exists.

All four are used by running code. Nothing sends until Meta approves them.

**To submit them, use [SUBMIT.md](SUBMIT.md)** — every field paste-ready, three languages each, plus what gets them rejected. The files in this folder are the source; that one is the form.

Submit in **English, Arabic, and Hindi**. Same template name, three language versions.
Category matters: get it wrong and it is rejected or billed wrong.

| Name | Category | Used by | Status |
|---|---|---|---|
| `booking_reminder_day_before` | UTILITY | scheduler, 1 day before | not submitted |
| `booking_reminder_morning` | UTILITY | scheduler, morning of | not submitted |
| `service_due_nudge` | MARKETING | scheduler, N months after the last visit | not submitted |
| `post_service_followup` | UTILITY | scheduler, 2 days after the job | not submitted |

Rules that get templates rejected: promotional wording in a UTILITY template; a variable at the
very start or very end of the body; two variables side by side; unfilled sample values.

Store the approved template names + variable order in `garages/<id>/info.yaml` — never hard-code them.
