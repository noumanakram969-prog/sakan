"""Command line entry points.

    python -m app.cli report --garage care --from 2026-09-01 --to 2026-09-30
    python -m app.cli garages
    python -m app.cli check --garage care
    python -m app.cli chat --garage care
    python -m app.cli grade --garage demo
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import date, timedelta

from . import engine, garages, grade, pricing, report
from .config import settings
from .db import (
    Conversation, Message, SessionLocal, init_db, utcnow,
)


def _report(args) -> int:
    start = report.parse_day(args.start)
    end = report.parse_day(args.end, end_of_day=True)
    if end <= start:
        print("--to must be on or after --from", file=sys.stderr)
        return 2
    print(report.render(report.build(args.garage, start, end)))
    return 0


def _garages(_args) -> int:
    for gid in garages.all_ids():
        info = garages.load(gid).get("info") or {}
        print("%-12s %s" % (gid, info.get("name") or "(no name)"))
    return 0


def _check(args) -> int:
    """Is this garage's knowledge actually usable? Run it before go-live.

    Every unfilled price is a question the bot will hand to the owner instead of
    answering, so he should know the number before the number surprises him.
    """
    try:
        garage = garages.load(args.garage)
    except garages.GarageNotFound:
        print("no such garage: %s" % args.garage, file=sys.stderr)
        return 2

    info = garage.get("info") or {}
    sheet = garage.get("prices") or {}
    problems, quotable, unfilled = [], 0, []

    for field in ("name", "address", "maps_link", "owner_alert_number", "hours"):
        value = info.get(field)
        if not value or (isinstance(value, str) and ("X" in value or value.startswith("TODO"))):
            problems.append("info.yaml: %s is missing or still a placeholder" % field)

    services = sheet.get("services") or []
    if not services:
        problems.append("prices.yaml: no services at all")

    for svc in services:
        for category in pricing.CATEGORIES:
            try:
                pricing.quote(sheet, svc.get("id"), category)
                quotable += 1
            except pricing.NotOnSheet:
                unfilled.append("%s / %s" % (svc.get("id"), category))

    print("%s: %d services, %d prices quotable, %d unfilled"
          % (args.garage, len(services), quotable, len(unfilled)))
    for item in unfilled:
        print("  unfilled: %s" % item)
    for item in problems:
        print("  %s" % item)

    if not quotable:
        print("\nNothing can be quoted. The bot will hand over every price question.")
        return 1
    return 1 if problems else 0


SIM_NUMBER = "971500000000"


def _chat(args) -> int:
    """Talk to the bot in a terminal, with no WhatsApp in the way.

    Same engine, same guard, same booking rules as the real thing - it just
    prints instead of sending. This is how you rehearse before the owner's
    number is connected, and how you show a garage what it does without asking
    them to trust a live number.
    """
    try:
        garage = garages.load(args.garage)
    except garages.GarageNotFound:
        print("no such garage: %s" % args.garage, file=sys.stderr)
        return 2

    if not settings.anthropic_api_key:
        print("No ANTHROPIC_API_KEY set - every turn will hand over.\n", file=sys.stderr)

    with SessionLocal() as db:
        conv = (
            db.query(Conversation)
            .filter_by(garage_id=args.garage, customer_number=args.number)
            .one_or_none()
        )
        if conv is None:
            conv = Conversation(garage_id=args.garage, customer_number=args.number)
            db.add(conv)
            db.commit()
        conversation_id = conv.id

    print("Chatting with %s as +%s. /image or /voice to send media, /quit to stop.\n"
          % ((garage.get("info") or {}).get("name") or args.garage, args.number))

    while True:
        try:
            line = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/quit", "/exit"):
            return 0

        msg_type, body = "text", line
        if line in ("/image", "/voice"):
            msg_type = "image" if line == "/image" else "audio"
            body = ""

        with SessionLocal() as db:
            row = Message(garage_id=args.garage, conversation_id=conversation_id,
                          direction="in", sender="customer", body=body, msg_type=msg_type)
            db.add(row)
            conv = db.get(Conversation, conversation_id)
            conv.last_message_at = utcnow()
            db.commit()
            history = [
                {"role": "user" if m.sender == "customer" else "assistant", "content": m.body}
                for m in db.query(Message)
                .filter(Message.conversation_id == conversation_id, Message.id != row.id)
                .order_by(Message.id).all()
                if m.body
            ]
            language = conv.language

        reply = engine.build_reply(
            garage, body, history,
            conversation_id=conversation_id,
            customer_number=args.number,
            msg_type=msg_type,
            language_hint=language,
        )

        with SessionLocal() as db:
            db.add(Message(garage_id=args.garage, conversation_id=conversation_id,
                           direction="out", sender="bot", body=reply.text, intent=reply.intent))
            conv = db.get(Conversation, conversation_id)
            if reply.language:
                conv.language = reply.language
            db.commit()

        print("bot > %s" % reply.text)

        notes = ["intent=%s" % reply.intent]
        if reply.quote:
            notes.append("quoted %s from the sheet" % reply.quote.display)
        if reply.booking:
            notes.append("BOOKED #%d" % reply.booking.id)
        if reply.blocked:
            notes.append("GUARD BLOCKED: %s %s" % (reply.blocked.reason, reply.blocked.offending))
        if reply.is_handoff:
            notes.append("HANDOFF: %s" % reply.handoff_reason)
        print("      [%s]\n" % ", ".join(notes))


def _grade(args) -> int:
    """Run the question set against the LIVE model. Costs API calls, on purpose.

    Exits non-zero if anything mislabelled, so it can gate a go-live.
    """
    if not settings.anthropic_api_key:
        print("grade needs ANTHROPIC_API_KEY - it is the model being measured",
              file=sys.stderr)
        return 2

    path = pathlib.Path(args.questions) if args.questions else None
    print("Grading %s against the live model. This makes one call per question.\n"
          % args.garage)

    def show(result):
        mark = "." if not result.bad else "X"
        print(mark, end="", flush=True)

    try:
        card = grade.run(args.garage, path, on_case=show)
    except garages.GarageNotFound:
        print("\nno such garage: %s" % args.garage, file=sys.stderr)
        return 2

    print(grade.render(card))
    return 1 if card.count(grade.MISLABEL) or card.count(grade.PRICED_A_SYMPTOM) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mistri")
    sub = parser.add_subparsers(dest="command", required=True)

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    thirty = (date.today() - timedelta(days=30)).isoformat()

    p = sub.add_parser("report", help="pilot numbers for a date range")
    p.add_argument("--garage", required=True)
    p.add_argument("--from", dest="start", default=thirty, help="YYYY-MM-DD")
    p.add_argument("--to", dest="end", default=yesterday, help="YYYY-MM-DD")
    p.set_defaults(func=_report)

    p = sub.add_parser("garages", help="list configured garages")
    p.set_defaults(func=_garages)

    p = sub.add_parser("chat", help="talk to the bot in the terminal")
    p.add_argument("--garage", required=True)
    p.add_argument("--number", default=SIM_NUMBER, help="pretend to be this customer")
    p.set_defaults(func=_chat)

    p = sub.add_parser("grade", help="run the question set against the live model")
    p.add_argument("--garage", required=True)
    p.add_argument("--questions", help="path to a questions.yaml (default: tests/questions.yaml)")
    p.set_defaults(func=_grade)

    p = sub.add_parser("check", help="is this garage ready to go live?")
    p.add_argument("--garage", required=True)
    p.set_defaults(func=_check)

    args = parser.parse_args(argv)
    init_db()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
