"""Background jobs.

Two of them, and both exist because of the same failure: a lead that was
answered perfectly and then sat there.

* **Chase an unclaimed hot lead.** Somebody said "cash, this month" at 9pm, the
  agent graded them hot, and no human has picked it up two hours later. The
  expensive mistake in a brokerage is not a bad reply, it is a good lead going
  cold while everyone assumes somebody else called.
* **The evening summary.** What came in, what it cost, what is still unclaimed.
  One message at 6pm beats a dashboard nobody opens.

The scheduler is APScheduler in-process, which suits one box. If this ever runs
on more than one, the jobs move to a worker with a lock - two instances both
sending the evening summary is the obvious first bug, so it is written here
rather than discovered later.
"""

from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, store, whatsapp
from .config import settings
from .property.qualify import Lead as LeadState, summary

log = logging.getLogger("sakan.jobs")

CHASE_AFTER_HOURS = 2


async def chase_unclaimed_hot_leads(agency_id: str) -> int:
    """Nudge the sales floor about hot leads nobody has taken."""
    with db.session() as s:
        agency = s.get(db.Agency, agency_id)
        alert_to = agency.agent_alert_number if agency else ""
        leads = store.stale_hot_leads(s, agency_id, older_than_hours=CHASE_AFTER_HOURS)

        if not leads:
            return 0

        lines = [f"{len(leads)} hot lead(s) nobody has called yet:"]
        for row in leads:
            lines.append(summary(store.to_state(row)) + f"  {row.wa_number}")

        if alert_to:
            try:
                await whatsapp.send_text(alert_to, "\n".join(lines))
            except Exception:
                log.exception("could not send the unclaimed-lead nudge")
                return 0

        # Marked only once the nudge is actually out, so a failed send is
        # retried on the next run instead of being silently dropped.
        for row in leads:
            store.mark_handover(s, row, "chased")
        s.commit()

    log.info("chased %d unclaimed hot lead(s)", len(leads))
    return len(leads)


async def evening_summary(agency_id: str) -> str:
    """What today looked like. Sent at 6pm local."""
    with db.session() as s:
        agency = s.get(db.Agency, agency_id)
        alert_to = agency.agent_alert_number if agency else ""
        counts = store.counts_by_grade(s, agency_id, since_hours=24)
        calls, usd = store.spend_month(s, agency_id, date.today().strftime("%Y-%m"))
        unclaimed = len(store.stale_hot_leads(s, agency_id, older_than_hours=0))

    text = (
        f"Today: {counts.get('hot', 0)} hot, {counts.get('warm', 0)} warm, "
        f"{counts.get('cold', 0)} cold.\n"
        f"Unclaimed hot: {unclaimed}.\n"
        f"Month so far: {calls} replies, ${usd:.2f}."
    )

    if alert_to:
        try:
            await whatsapp.send_text(alert_to, text)
        except Exception:
            log.exception("could not send the evening summary")

    log.info("evening summary: %s", text.replace("\n", " "))
    return text


def start(agency_id: str) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=settings.timezone)

    sched.add_job(
        chase_unclaimed_hot_leads, "interval", minutes=30, args=[agency_id],
        id="chase_hot", replace_existing=True, max_instances=1,
        # A run that overlaps the previous one would nudge twice about the same
        # lead; coalescing a backlog into one run is the behaviour we want.
        coalesce=True, misfire_grace_time=600,
    )
    sched.add_job(
        evening_summary, CronTrigger(hour=18, minute=0), args=[agency_id],
        id="evening_summary", replace_existing=True, max_instances=1,
        coalesce=True, misfire_grace_time=3600,
    )

    sched.start()
    log.info("scheduler started: %s", ", ".join(j.id for j in sched.get_jobs()))
    return sched
