"""The three things that happen without anyone sending a message.

Reminders, releasing quiet handoffs, and the 6 pm summary. Every job is written
so that failing is survivable and running twice is harmless - a scheduler on a
single VPS will be restarted mid-job sooner or later.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import conversations, followups, garages, nudges, owner, reminders, whatsapp
from .config import settings
from .db import Booking, SessionLocal

log = logging.getLogger(__name__)

SUMMARY_HOUR = 18       # local
UNCONFIRMED_HOUR = 7    # local — before the workshop opens, so he can call

_scheduler: AsyncIOScheduler | None = None


async def send_reminders() -> None:
    try:
        count = await reminders.send_due()
        if count:
            log.info("sent %d reminders", count)
    except Exception:
        log.exception("reminder job failed")


async def send_followups() -> None:
    """The v1.1 pair: how was it, and your car is due again."""
    try:
        after, nudges = await followups.send_due()
        if after or nudges:
            log.info("sent %d follow-ups and %d service-due nudges", after, nudges)
    except Exception:
        log.exception("follow-up job failed")


async def release_quiet_handoffs() -> None:
    try:
        conversations.auto_release_quiet_handoffs()
    except Exception:
        log.exception("handoff release job failed")


async def send_unconfirmed_alerts() -> None:
    """Morning nudge: today's booked cars that never confirmed the reminder."""
    for garage_id in garages.routable_ids():
        try:
            info = garages.load(garage_id).get("info") or {}
        except garages.GarageNotFound:
            continue

        number = str(info.get("owner_alert_number") or "").strip()
        if not number or "X" in number.upper() or number.upper().startswith("TODO"):
            continue

        rows = owner.unconfirmed_today(garage_id, info)
        if not rows:
            continue

        try:
            await whatsapp.send_text(number, owner.unconfirmed_alert(rows, info))
        except whatsapp.WhatsAppError as exc:
            log.error("unconfirmed alert failed for %s: %s", garage_id, exc)
            continue

        # Once per booking — a repeated "still not confirmed" reads as noise.
        with SessionLocal() as db:
            for r in rows:
                fresh = db.get(Booking, r.id)
                if fresh is not None:
                    fresh.owner_unconfirmed_alerted = True
            db.commit()


async def send_setup_reminders() -> None:
    """Nudge owners who signed up but never finished their prices."""
    try:
        await nudges.send_setup_reminders()
    except Exception:
        log.exception("setup reminder job failed")


async def daily_summary() -> None:
    """The 6 pm message. If the owner reads one thing a day, it is this."""
    for garage_id in garages.routable_ids():
        try:
            info = garages.load(garage_id).get("info") or {}
        except garages.GarageNotFound:
            continue

        number = str(info.get("owner_alert_number") or "").strip()
        if not number or "X" in number.upper() or number.upper().startswith("TODO"):
            continue

        try:
            await whatsapp.send_text(number, owner.today_summary(garage_id))
        except whatsapp.WhatsAppError as exc:
            log.error("daily summary failed for %s: %s", garage_id, exc)


def start() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    tz = settings.timezone
    sched = AsyncIOScheduler(timezone=tz)

    # Every 15 minutes rather than on the hour: a reminder is allowed to be a
    # few minutes late, and this way one missed tick does not skip a day.
    sched.add_job(send_reminders, IntervalTrigger(minutes=15), id="reminders",
                  coalesce=True, max_instances=1)
    sched.add_job(release_quiet_handoffs, IntervalTrigger(hours=1), id="release",
                  coalesce=True, max_instances=1)
    # Once a day is plenty, and it keeps a restart loop from messaging anyone twice.
    sched.add_job(send_followups, CronTrigger(hour=11, minute=30, timezone=tz),
                  id="followups", coalesce=True, max_instances=1)
    sched.add_job(send_unconfirmed_alerts,
                  CronTrigger(hour=UNCONFIRMED_HOUR, minute=30, timezone=tz),
                  id="unconfirmed", coalesce=True, max_instances=1)
    sched.add_job(send_setup_reminders, CronTrigger(hour=10, minute=0, timezone=tz),
                  id="setup_reminders", coalesce=True, max_instances=1)
    sched.add_job(daily_summary, CronTrigger(hour=SUMMARY_HOUR, minute=0, timezone=tz),
                  id="summary", coalesce=True, max_instances=1)

    sched.start()
    _scheduler = sched
    log.info("scheduler started (%s)", tz)
    return sched


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
