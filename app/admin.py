"""The admin page from section 5 of the brief.

Conversations with their transcript, the bookings list, and the pilot report.
Nothing more — a customer-facing dashboard is a product of its own and is
explicitly out of scope.

Server-rendered, no JavaScript, no build step, system fonts. It exists for one
job: the owner rings at 9pm asking what the bot told someone, and the answer is
on screen in ten seconds. That job is why it is fast and scannable rather than
clever.
"""
from __future__ import annotations

import asyncio
import html
import re
import secrets
import time
import urllib.parse
from datetime import timedelta

import hmac

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from . import commands, onboard, whatsapp
from . import report as report_mod
from . import slots, wording
from .config import settings
from .db import Booking, Conversation, Handoff, Lead, Message, Owner, SessionLocal, utcnow
from .garages import GarageNotFound, all_ids, load, routable_ids

router = APIRouter(prefix="/admin", tags=["admin"])

PAGE_SIZE = 50

STYLE = """
*{box-sizing:border-box}
:root{
  --page:#f5f7f6; --card:#fff; --ink:#10201a; --ink2:#4a5c53; --ink3:#7d8c84;
  --line:#e4e9e6; --green:#0b6b4f; --green2:#0e8862; --mint:#e8f4ee;
  --amber:#9a6410; --amber-bg:#fdf3e3; --red:#b23b2e; --red-bg:#fdeeec;
  --sans:'Segoe UI',-apple-system,BlinkMacSystemFont,Roboto,Helvetica,Arial,sans-serif;
  --mono:'Cascadia Mono',ui-monospace,Consolas,monospace;
}
html{background:var(--page)}
body{margin:0;background:var(--page);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}

nav{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.nav-in{max-width:1060px;margin:0 auto;padding:0 22px;display:flex;align-items:center;gap:28px;height:58px}
.brand{font-weight:700;font-size:17px;letter-spacing:-.02em;color:var(--green);margin-right:4px}
nav a{color:var(--ink2);text-decoration:none;font-size:14.5px;font-weight:500;
  padding:19px 0;border-bottom:2px solid transparent;margin-bottom:-1px}
nav a:hover{color:var(--ink)}
nav a.on{color:var(--green);border-bottom-color:var(--green)}
nav a:focus-visible{outline:2px solid var(--green2);outline-offset:3px;border-radius:3px}

main{max-width:1060px;margin:0 auto;padding:28px 22px 72px}
h1{font-size:25px;font-weight:700;letter-spacing:-.025em;margin:0 0 3px}
.sub{color:var(--ink3);font-size:14.5px;margin:0 0 22px}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 22px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 17px}
.tile .n{font-size:26px;font-weight:700;letter-spacing:-.02em;line-height:1.15;
  font-variant-numeric:tabular-nums}
.tile .l{font-size:13px;color:var(--ink3);font-weight:500}
.tile.alert .n{color:var(--red)}

.card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.card + .card{margin-top:16px}
.scroll{overflow-x:auto}

table{width:100%;border-collapse:collapse;font-size:14.5px;min-width:560px}
th{font-size:11.5px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);text-align:left;padding:14px 16px;border-bottom:1px solid var(--line);
  background:#fafcfb}
td{padding:13px 16px;border-bottom:1px solid var(--line);vertical-align:middle}
tr:last-child td{border-bottom:0}
tbody tr:hover td{background:#fafcfb}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--ink2)}
td a{color:var(--ink);font-weight:600;text-decoration:none}
td a:hover{color:var(--green)}

.pill{display:inline-block;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;white-space:nowrap}
.pill.wait{background:var(--red-bg);color:var(--red)}
.pill.owner{background:var(--amber-bg);color:var(--amber)}
.pill.ok{background:var(--mint);color:var(--green)}
.pill.grey{background:#eef1ef;color:var(--ink3)}

.empty{padding:44px 20px;text-align:center;color:var(--ink3)}

/* transcript */
.head{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 16px;margin:0 0 20px}
.head .who{font-size:25px;font-weight:700;letter-spacing:-.025em}
.chat{padding:20px;display:flex;flex-direction:column;gap:11px;background:#fbfcfb}
.turn{max-width:74%;padding:11px 15px;border-radius:14px;font-size:14.8px;line-height:1.5;
  border:1px solid var(--line);background:var(--card)}
.turn.customer{align-self:flex-start;border-top-left-radius:4px}
.turn.bot{align-self:flex-end;border-top-right-radius:4px;background:var(--mint);border-color:#d3e8dc}
.turn.owner{align-self:flex-end;border-top-right-radius:4px;background:var(--amber-bg);border-color:#f0e0c4}
.turn .meta{font-size:11.5px;color:var(--ink3);font-weight:600;margin-bottom:4px;
  letter-spacing:.02em;display:flex;gap:8px}
.turn .body{white-space:pre-wrap;word-wrap:break-word}
.flag{align-self:center;background:var(--red-bg);color:var(--red);font-size:13px;font-weight:600;
  padding:7px 15px;border-radius:999px;max-width:88%;text-align:center}
@media(max-width:640px){.turn{max-width:88%}}

.rows{padding:4px 20px}
.row{display:flex;align-items:baseline;gap:14px;padding:13px 0;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:0}
.row .k{flex:1;color:var(--ink2)}
.row .k small{display:block;color:var(--ink3);font-size:12.8px}
.row .v{font-size:20px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums;
  min-width:74px;text-align:right}
.row .v span{font-size:13px;font-weight:500;color:var(--ink3);margin-left:5px}
.row.warn .v{color:var(--red)}

.bars{padding:16px 20px 20px;display:grid;gap:13px}
.bar{display:grid;grid-template-columns:78px 1fr 42px;align-items:center;gap:13px}
.bar .name{font-size:14.5px;color:var(--ink2)}
.bar .track{background:#eef2f0;border-radius:999px;height:9px;overflow:hidden}
.bar .fill{background:var(--green2);height:100%;border-radius:999px;min-width:3px}
.bar .val{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;font-size:14.5px}

.headline{background:var(--green);color:#fff;border-radius:14px;padding:22px 24px;margin:0 0 16px}
.headline .big{font-size:24px;font-weight:700;letter-spacing:-.025em;line-height:1.3}
.headline .small{color:#bfe0d0;font-size:14.5px;margin-top:5px}

.sec-title{font-size:12px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);padding:16px 20px 0}
code{font-family:var(--mono);font-size:.9em;background:var(--mint);color:var(--green);
  padding:2px 6px;border-radius:5px}
.pager{display:flex;gap:10px;margin-top:16px}
.pager a{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:8px 15px;
  color:var(--ink2);text-decoration:none;font-size:14px;font-weight:500}
.pager a:hover{border-color:var(--green);color:var(--green)}
"""


DEFAULT_PASSWORD = "change-me"


SESSION_COOKIE = "mistri_admin"


def _session_value() -> str:
    """A signed marker that says 'this browser logged in with the real password'."""
    key = (settings.admin_password or "x").encode()
    return hmac.new(key, b"mistri-admin-session", "sha256").hexdigest()


def _password_ok(user: str, pw: str) -> bool:
    return (secrets.compare_digest(user or "", settings.admin_user)
            and secrets.compare_digest(pw or "", settings.admin_password))


def _authed(request: Request) -> bool:
    # Cookie only. We deliberately do NOT accept HTTP Basic here: browsers cache
    # Basic credentials and re-send them silently, which would let a stale cached
    # password defeat "Log out". The only way in is the session cookie the login
    # form sets, and logout clears.
    return hmac.compare_digest(request.cookies.get(SESSION_COOKIE, ""), _session_value())


def _gate(request: Request) -> HTMLResponse | RedirectResponse | None:
    """Return a response to send INSTEAD of the page when the caller may not see
    it; None means let them through. The dashboard lists customers' numbers and
    everything they wrote, so it never serves on the shipped default password."""
    if settings.admin_password == DEFAULT_PASSWORD:
        return HTMLResponse(
            "<p style='font:16px system-ui;max-width:34em;margin:60px auto;padding:0 20px'>"
            "Set <b>ADMIN_PASSWORD</b> in the server .env — the admin page will not serve on the "
            "default password.</p>", status_code=503)
    if not _authed(request):
        return RedirectResponse(url="/admin/login", status_code=307)
    return None


def _page(title: str, body: str, tab: str = "") -> HTMLResponse:
    def link(href: str, label: str, key: str) -> str:
        return "<a href='%s'%s>%s</a>" % (href, " class='on'" if tab == key else "", label)

    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>%s · Mistri</title><style>%s</style></head><body>"
        "<nav><div class='nav-in'><span class='brand'>Mistri</span>%s%s%s%s%s</div></nav>"
        "<main>%s</main></body></html>"
        % (
            html.escape(title), STYLE,
            link("/admin/", "Conversations", "chats"),
            link("/admin/bookings", "Bookings", "bookings"),
            link("/admin/messages", "Messages", "messages"),
            link("/admin/setup", "Prices & setup", "setup"),
            link("/admin/report", "Report", "report")
            + "<a href='/admin/logout' style='margin-left:auto'>Log out</a>",
            body,
        )
    )


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


_token_cache: dict = {"at": 0.0, "ok": None, "detail": ""}


def _whatsapp_status() -> tuple[bool, str]:
    """Cached (60s) token health, so a red banner tells the operator outbound is
    down without a Graph call on every page load."""
    now = time.time()
    if _token_cache["ok"] is not None and now - _token_cache["at"] < 60:
        return _token_cache["ok"], _token_cache["detail"]
    try:
        ok, detail = asyncio.run(whatsapp.check_token())
    except Exception:
        ok, detail = False, "check failed"
    _token_cache.update(at=now, ok=ok, detail=detail)
    return ok, detail


def _whatsapp_banner() -> str:
    ok, detail = _whatsapp_status()
    if ok:
        return ("<div style='background:var(--mint);color:var(--green);border:1px solid #cfe6d8;"
                "border-radius:10px;padding:10px 14px;margin:0 0 18px;font-size:14px;font-weight:600'>"
                "&#9679; WhatsApp sending: connected</div>")
    return ("<div style='background:var(--red-bg);color:var(--red);border:1px solid #f0c9c4;"
            "border-radius:10px;padding:12px 15px;margin:0 0 18px;font-size:14px'>"
            "<b>&#9679; WhatsApp sending is DOWN — %s.</b><br>Replies, reminders and alerts are "
            "failing. Update <code>META_ACCESS_TOKEN</code> in the server <code>.env</code> and "
            "restart Mistri.</div>" % _esc(detail))


def _info(garage_id: str) -> dict:
    try:
        return load(garage_id).get("info") or {}
    except GarageNotFound:
        return {}


def _local(dt, garage_id: str) -> str:
    if dt is None:
        return ""
    return slots.to_local(dt, _info(garage_id)).strftime("%d %b, %H:%M")


def _ago(dt) -> str:
    if dt is None:
        return ""
    seconds = (utcnow() - dt).total_seconds()
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return "%d min ago" % (seconds // 60)
    if seconds < 86400:
        return "%d hr ago" % (seconds // 3600)
    return "%d days ago" % (seconds // 86400)


@router.get("/", response_class=HTMLResponse)
def conversation_list(request: Request, page: int = Query(0, ge=0)) -> HTMLResponse:
    gate = _gate(request)
    if gate:
        return gate
    with SessionLocal() as db:
        rows = (
            db.query(Conversation)
            .order_by(Conversation.last_message_at.desc())
            .offset(page * PAGE_SIZE)
            .limit(PAGE_SIZE)
            .all()
        )
        open_handoffs = {
            h.conversation_id
            for h in db.query(Handoff).filter(Handoff.released_at.is_(None)).all()
        }
        total = db.query(Conversation).count()
        since = utcnow() - timedelta(hours=24)
        today = (
            db.query(Conversation).filter(Conversation.started_at >= since).count()
        )
        booked = (
            db.query(Booking)
            .filter(Booking.created_at >= since, Booking.status != "cancelled")
            .count()
        )

    body = [
        "<h1>Conversations</h1>",
        "<p class='sub'>Newest first. Anyone waiting for a call is flagged.</p>",
        _whatsapp_banner(),
        "<div class='tiles'>",
        "<div class='tile'><div class='n'>%d</div><div class='l'>All time</div></div>" % total,
        "<div class='tile'><div class='n'>%d</div><div class='l'>Last 24 hours</div></div>" % today,
        "<div class='tile'><div class='n'>%d</div><div class='l'>Booked today</div></div>" % booked,
        "<div class='tile%s'><div class='n'>%d</div><div class='l'>Waiting for a call</div></div>"
        % (" alert" if open_handoffs else "", len(open_handoffs)),
        "</div>",
    ]

    if not rows:
        body.append("<div class='card'><div class='empty'>No conversations yet.</div></div>")
        return _page("Conversations", "".join(body), "chats")

    body.append("<div class='card'><div class='scroll'><table>"
                "<thead><tr><th>Customer</th><th>Garage</th><th>Last message</th>"
                "<th>Language</th><th>Status</th></tr></thead><tbody>")

    languages = {"en": "English", "ar": "Arabic", "hi": "Hindi", "ur": "Urdu"}
    for c in rows:
        if c.id in open_handoffs:
            state = "<span class='pill wait'>Waiting for a call</span>"
        elif c.paused_until and c.paused_until > utcnow():
            state = "<span class='pill owner'>You are replying</span>"
        else:
            state = "<span class='pill ok'>Bot is handling it</span>"
        body.append(
            "<tr><td><a href='/admin/conversation/%d'>+%s</a></td>"
            "<td><span class='pill grey'>%s</span></td>"
            "<td class='num'>%s<br><span style='color:var(--ink3);font-size:12.5px'>%s</span></td>"
            "<td>%s</td><td>%s</td></tr>"
            % (c.id, _esc(c.customer_number), _esc(c.garage_id),
               _local(c.last_message_at, c.garage_id), _esc(_ago(c.last_message_at)),
               _esc(languages.get(c.language, c.language or "—")), state)
        )
    body.append("</tbody></table></div></div>")

    pager = []
    if page:
        pager.append("<a href='/admin/?page=%d'>&larr; Newer</a>" % (page - 1))
    if (page + 1) * PAGE_SIZE < total:
        pager.append("<a href='/admin/?page=%d'>Older &rarr;</a>" % (page + 1))
    if pager:
        body.append("<div class='pager'>%s</div>" % "".join(pager))

    return _page("Conversations", "".join(body), "chats")


@router.get("/conversation/{conversation_id}", response_class=HTMLResponse)
def transcript(request: Request, conversation_id: int) -> HTMLResponse:
    gate = _gate(request)
    if gate:
        return gate
    with SessionLocal() as db:
        conv = db.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="no such conversation")
        messages = (
            db.query(Message)
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.id)
            .all()
        )
        handoffs = (
            db.query(Handoff)
            .filter_by(conversation_id=conversation_id)
            .order_by(Handoff.id)
            .all()
        )

    by_id = {h.created_at: h for h in handoffs}

    body = [
        "<div class='head'><span class='who'>+%s</span>" % _esc(conv.customer_number),
        "<span class='pill grey'>%s</span>" % _esc(conv.garage_id),
    ]
    if conv.customer_name:
        body.append("<span class='pill grey'>%s</span>" % _esc(conv.customer_name))
    body.append("<span class='sub' style='margin:0'>Started %s</span></div>"
                % _local(conv.started_at, conv.garage_id))

    if any(h.released_at is None for h in handoffs):
        body.append(
            "<div class='card' style='margin-bottom:16px'>"
            "<div class='empty' style='padding:18px;color:var(--red)'>"
            "<strong>Waiting for a call.</strong> The bot is quiet here until it is released. "
            "<form method='post' action='/admin/conversation/%d/release' style='margin-top:12px'>"
            "<button type='submit' class='save' style='background:var(--green2)'>"
            "Give this chat back to the bot</button></form>"
            "</div></div>" % conversation_id)

    body.append("<div class='card'><div class='chat'>")

    labels = {"customer": "Customer", "bot": "Mistri", "owner": "Owner"}
    for m in messages:
        for created, h in list(by_id.items()):
            if created <= m.created_at:
                body.append("<div class='flag' title='%s'>Handed over &mdash; %s</div>"
                            % (_esc(h.reason), _esc(wording.plain_reason(h.reason))))
                del by_id[created]
        timing = " · %.1fs" % m.reply_seconds if m.reply_seconds is not None else ""
        body.append(
            "<div class='turn %s'><div class='meta'><span>%s</span>"
            "<span>%s%s</span></div><div class='body'>%s</div></div>"
            % (_esc(m.sender), _esc(labels.get(m.sender, m.sender)),
               _local(m.created_at, conv.garage_id), _esc(timing), _esc(m.body))
        )
    for h in by_id.values():
        body.append("<div class='flag' title='%s'>Handed over &mdash; %s</div>"
                    % (_esc(h.reason), _esc(wording.plain_reason(h.reason))))

    body.append("</div></div>")
    return _page("Conversation", "".join(body), "chats")


@router.get("/bookings", response_class=HTMLResponse)
def booking_list(request: Request) -> HTMLResponse:
    gate = _gate(request)
    if gate:
        return gate
    with SessionLocal() as db:
        rows = (
            db.query(Booking)
            .filter(Booking.slot_start >= utcnow() - timedelta(days=7))
            .order_by(Booking.slot_start)
            .all()
        )

    upcoming = sum(1 for b in rows if b.slot_start >= utcnow() and b.status != "cancelled")
    body = [
        "<h1>Bookings</h1>",
        "<p class='sub'>The last week and everything ahead.</p>",
        "<div class='tiles'>",
        "<div class='tile'><div class='n'>%d</div><div class='l'>Still to come</div></div>" % upcoming,
        "<div class='tile'><div class='n'>%d</div><div class='l'>Shown here</div></div>" % len(rows),
        "</div>",
    ]

    if not rows:
        body.append("<div class='card'><div class='empty'>Nothing booked in the last week "
                    "or ahead.</div></div>")
        return _page("Bookings", "".join(body), "bookings")

    body.append("<div class='card'><div class='scroll'><table>"
                "<thead><tr><th>When</th><th>Name</th><th>Car</th><th>Service</th>"
                "<th>Number</th><th>Status</th></tr></thead><tbody>")
    for b in rows:
        pill = {"confirmed": "ok", "cancelled": "wait", "done": "grey"}.get(b.status, "grey")
        body.append(
            "<tr><td class='num'>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td><a href='/admin/conversation/%d'>+%s</a></td>"
            "<td><span class='pill %s'>%s</span></td></tr>"
            % (_local(b.slot_start, b.garage_id), _esc(b.customer_name), _esc(b.car),
               _esc(b.service), b.conversation_id, _esc(b.customer_number),
               pill, _esc(b.status))
        )
    body.append("</tbody></table></div></div>")
    return _page("Bookings", "".join(body), "bookings")


@router.get("/report", response_class=HTMLResponse)
def report_page(
    request: Request,
    garage: str = Query("care"),
    days: int = Query(30, ge=1, le=365),
) -> HTMLResponse:
    gate = _gate(request)
    if gate:
        return gate
    end = utcnow() + timedelta(days=1)
    built = report_mod.build(garage, end - timedelta(days=days + 1), end)

    start = (end - timedelta(days=days + 1)).date()
    finish = (end - timedelta(days=1)).date()

    body = [
        "<h1>Report</h1>",
        "<p class='sub'>%s &mdash; %s to %s</p>"
        % (_esc(garage), start.strftime("%d %b %Y"), finish.strftime("%d %b %Y")),
    ]

    # The sentence the next garage owner is actually shown. Lead with it.
    if built.conversations:
        body.append(
            "<div class='headline'><div class='big'>%d of %d conversations became a booking.</div>"
            "<div class='small'>%d of them started after the garage had closed.</div></div>"
            % (built.bookings, built.conversations, built.conversations_outside_hours)
        )

    body += [
        "<div class='tiles'>",
        "<div class='tile'><div class='n'>%d</div><div class='l'>Conversations</div></div>"
        % built.conversations,
        "<div class='tile'><div class='n'>%d%%</div><div class='l'>After hours</div></div>"
        % round(built.outside_hours_share * 100),
        "<div class='tile'><div class='n'>%d</div><div class='l'>Bookings</div></div>"
        % built.bookings,
        "<div class='tile'><div class='n'>%s</div><div class='l'>Median reply</div></div>"
        % ("%.1fs" % built.median_reply_seconds if built.median_reply_seconds is not None else "—"),
        "</div>",
    ]

    def row(label: str, value: str, note: str = "", flag: bool = False) -> str:
        return ("<div class='row%s'><div class='k'>%s%s</div><div class='v'>%s</div></div>"
                % (" warn" if flag else "", _esc(label),
                   "<small>%s</small>" % _esc(note) if note else "", value))

    detail = [
        row("Conversations", str(built.conversations), "over %d days" % built.days),
        row("Started after hours", str(built.conversations_outside_hours),
            "when nobody was at the phone"),
        row("Price questions answered", str(built.price_questions), "straight off the sheet"),
        row("Bookings", str(built.bookings),
            "%d cancelled" % built.bookings_cancelled if built.bookings_cancelled else ""),
        row("Handed to a human", str(built.handoffs),
            "the bot was not sure, so a person took it"),
    ]
    if built.handoffs_open:
        detail.append(row("Still waiting for a call", str(built.handoffs_open),
                          "somebody was promised a call", flag=True))
    detail.append(row("Replies sent", str(built.replies_sent)))
    if built.replies_blocked:
        detail.append(row("Replies stopped by the guard", str(built.replies_blocked),
                          "wrong figures that never reached anyone"))
    detail.append(row(
        "Median reply time",
        "%.1f<span>sec</span>" % built.median_reply_seconds
        if built.median_reply_seconds is not None else "—",
    ))

    body.append("<div class='card'><div class='sec-title'>What happened</div>"
                "<div class='rows'>%s</div></div>" % "".join(detail))

    if built.languages:
        top = max(built.languages.values())
        bars = []
        for code, count in sorted(built.languages.items(), key=lambda kv: -kv[1]):
            bars.append(
                "<div class='bar'><div class='name'>%s</div>"
                "<div class='track'><div class='fill' style='width:%d%%'></div></div>"
                "<div class='val'>%d</div></div>"
                % (_esc(report_mod.LANGUAGE_NAMES.get(code, code)),
                   round(count / top * 100), count)
            )
        body.append("<div class='card'><div class='sec-title'>Languages customers wrote in</div>"
                    "<div class='bars'>%s</div></div>" % "".join(bars))

    if not built.conversations:
        body.append("<div class='card'><div class='empty'>Nothing in this period yet.</div></div>")

    body.append(
        "<p class='sub' style='margin:18px 0 0'>Same numbers on the command line: "
        "<code>python -m app.cli report --garage %s --from YYYY-MM-DD --to YYYY-MM-DD</code></p>"
        % _esc(garage)
    )
    return _page("Report", "".join(body), "report")


# The first line the operator sends a lead, ready to go so he doesn't retype it.
# Matched to the script the lead wrote in — a courtesy, and it reads as a real
# person, not a blast. WhatsApp still needs him to press send; it never sends
# on its own.
_OPENER = {
    "en": "Hey 👋 thanks for messaging! Keen to give you a free 30 days on your garage's own "
          "WhatsApp. When's good for a quick demo?",
    "ar": "أهلاً 👋 شكراً لرسالتك! يسعدنا نجربها معك 30 يوماً مجاناً على واتساب الجراج. متى يناسبك "
          "عرض سريع؟",
    "ur": "السلام علیکم 👋 پیغام کا شکریہ! آپ کے گیراج کے اپنے واٹس ایپ پر 30 دن مفت آزمائیں۔ ڈیمو کے "
          "لیے کب وقت ٹھیک رہے گا؟",
    "hi": "नमस्ते 👋 मैसेज के लिए शुक्रिया! आपके गैराज के अपने WhatsApp पर 30 दिन मुफ़्त ट्राय करें। "
          "डेमो के लिए कब सही रहेगा?",
}

_URDU_LETTERS = re.compile(r"[ٹڈڑںھہیےگچپژ]")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _opener(message: str) -> str:
    """Pick the opener language from the script the lead actually typed in."""
    m = message or ""
    if _DEVANAGARI.search(m):
        return _OPENER["hi"]
    if _ARABIC.search(m):
        return _OPENER["ur"] if _URDU_LETTERS.search(m) else _OPENER["ar"]
    return _OPENER["en"]


@router.get("/messages", response_class=HTMLResponse)
def message_list(request: Request) -> HTMLResponse:
    """Demo requests left on the public landing page. The operator replies from
    here — a tap opens WhatsApp to their number — now or whenever he next looks."""
    gate = _gate(request)
    if gate:
        return gate
    with SessionLocal() as db:
        rows = db.query(Lead).order_by(Lead.created_at.desc()).limit(200).all()
        new_count = db.query(Lead).filter(Lead.handled.is_(False)).count()

    body = [
        "<h1>Messages</h1>",
        "<p class='sub'>People who asked for a demo on the website. Reply on WhatsApp, "
        "then mark it done.</p>",
        "<div class='tiles'>",
        "<div class='tile%s'><div class='n'>%d</div><div class='l'>New</div></div>"
        % (" alert" if new_count else "", new_count),
        "<div class='tile'><div class='n'>%d</div><div class='l'>Shown here</div></div>" % len(rows),
        "</div>",
    ]

    if not rows:
        body.append("<div class='card'><div class='empty'>No messages yet. They arrive here "
                    "when someone fills the form on the website.</div></div>")
        return _page("Messages", "".join(body), "messages")

    body.append("<div class='card'><div class='scroll'><table>"
                "<thead><tr><th>When</th><th>Name</th><th>Number</th><th>Message</th>"
                "<th>Status</th><th></th></tr></thead><tbody>")
    for m in rows:
        # Normalise to full international so the tap actually opens WhatsApp:
        # a locally-typed 05x... becomes 9715x..., which is what wa.me needs.
        wa = commands.normalise(m.number) or "".join(ch for ch in (m.number or "") if ch.isdigit())
        href = "https://wa.me/%s?text=%s" % (wa, urllib.parse.quote(_opener(m.message)))
        num_cell = ("<a href='%s' target='_blank' rel='noopener'>+%s</a>"
                    % (_esc(href), _esc(m.number)) if wa else _esc(m.number) or "—")
        status = ("<span class='pill grey'>Done</span>" if m.handled
                  else "<span class='pill wait'>New</span>")
        action = ("" if m.handled else
                  "<form method='post' action='/admin/messages/%d/done' style='margin:0'>"
                  "<button type='submit' style='background:var(--mint);color:var(--green);"
                  "border:0;border-radius:8px;padding:6px 12px;font-weight:600;cursor:pointer;"
                  "font-size:13px'>Mark done</button></form>" % m.id)
        body.append(
            "<tr><td class='num'>%s<br><span style='color:var(--ink3);font-size:12.5px'>%s</span></td>"
            "<td>%s</td><td class='num'>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (_local(m.created_at, "care"), _esc(_ago(m.created_at)),
               _esc(m.name) or "—", num_cell,
               _esc(m.message) or "<span style='color:var(--ink3)'>(no message)</span>",
               status, action)
        )
    body.append("</tbody></table></div></div>")
    return _page("Messages", "".join(body), "messages")


@router.post("/messages/{lead_id}/done")
def message_done(request: Request, lead_id: int) -> Response:
    gate = _gate(request)
    if gate:
        return gate
    with SessionLocal() as db:
        row = db.get(Lead, lead_id)
        if row is not None:
            row.handled = True
            db.commit()
    return RedirectResponse(url="/admin/messages", status_code=303)


def _missing(value) -> bool:
    s = str(value or "").strip()
    return (not s) or s.upper().startswith("TODO") or "X" in s.upper()


def _price_readiness(prices: dict) -> tuple[int, int]:
    services = (prices or {}).get("services") or []
    total = filled = 0
    for s in services:
        for v in ((s or {}).get("prices") or {}).values():
            total += 1
            if not _missing(v):
                filled += 1
    return filled, total


@router.get("/setup", response_class=HTMLResponse)
def setup(request: Request) -> HTMLResponse:
    """The owner's own price-and-details page — and how ready each garage is.

    The link here is the garage owner's private profile: he opens it, edits his
    prices, hours, and details, and it goes live in his WhatsApp replies on the
    very next message. No password for him, no restart, no developer."""
    gate = _gate(request)
    if gate:
        return gate

    base = str(request.base_url).rstrip("/")
    body = ["<h1>Prices &amp; setup</h1>",
            "<p class='sub'>Each garage owner gets a private link to update their own prices and "
            "details. Changes show up in WhatsApp instantly — no restart.</p>"]

    # Every real garage — signups included. A pending garage (signed up on the
    # website, number not connected yet) is exactly what the operator needs to
    # see here so it can be activated. The invented demo garage is hidden.
    ids = [gid for gid in all_ids() if not _info(gid).get("demo")]
    live = set(routable_ids())
    pending_count = sum(1 for gid in ids if gid not in live)
    if pending_count:
        body.append("<p class='sub' style='margin:-14px 0 20px'><b>%d garage(s) waiting to go "
                    "live</b> — connect their WhatsApp number, then set <code>pending: false</code>."
                    "</p>" % pending_count)

    if not ids:
        body.append("<div class='card'><div class='empty'>No garages yet. They appear here when "
                    "someone signs up on the website.</div></div>")
        return _page("Prices & setup", "".join(body), "setup")

    for gid in ids:
        try:
            g = load(gid)
        except GarageNotFound:
            continue
        info = g.get("info") or {}
        prices = g.get("prices") or {}
        filled, total = _price_readiness(prices)
        is_live = gid in live
        status_pill = ("<span class='pill ok' style='margin-left:8px'>Live</span>" if is_live
                       else "<span class='pill owner' style='margin-left:8px'>Setting up</span>")
        link = "%s/onboard/%s?t=%s" % (base, gid, onboard.token_for(gid))

        def check(ok: bool, label: str, hint: str = "") -> str:
            mark = ("<span class='pill ok'>&#10003;</span>" if ok
                    else "<span class='pill wait'>needs setup</span>")
            return ("<div class='row'><div class='k'>%s%s</div><div class='v' "
                    "style='min-width:120px;font-size:14px;font-weight:600'>%s</div></div>"
                    % (_esc(label), "<small>%s</small>" % _esc(hint) if hint else "", mark))

        def status_row(label: str, value_html: str, hint: str = "") -> str:
            return ("<div class='row'><div class='k'>%s%s</div><div class='v' "
                    "style='min-width:150px;font-size:13px;font-weight:600'>%s</div></div>"
                    % (_esc(label), "<small>%s</small>" % _esc(hint) if hint else "", value_html))

        with SessionLocal() as db:
            owner = db.query(Owner).filter_by(garage_id=gid).first()
        if owner is None:
            owner_html = "<span class='pill grey'>no login yet</span>"
        else:
            bits = ["<span class='pill ok'>&#10003; account</span>"]
            if owner.setup_nudged:
                bits.append("<span class='pill grey'>reminded</span>")
            if owner.welcomed:
                bits.append("<span class='pill ok'>welcomed</span>")
            owner_html = " ".join(bits)

        prices_ok = total > 0 and filled == total
        body.append(
            "<div class='card' style='padding:0;margin-bottom:16px'>"
            "<div class='sec-title'>%s</div>"
            "<div class='rows'>%s%s%s%s%s</div>"
            "<div style='padding:0 20px 20px'>"
            "<div class='sec-title' style='padding:6px 0 8px'>Owner's private edit link</div>"
            "<input readonly value='%s' onclick='this.select()' "
            "style='width:100%%;padding:11px 13px;border:1.4px solid var(--line);border-radius:9px;"
            "font-size:13.5px;font-family:var(--mono);background:#fafcfb;color:var(--ink)'>"
            "<div style='display:flex;gap:10px;margin-top:10px;flex-wrap:wrap;align-items:center'>"
            "<a href='%s' target='_blank' rel='noopener' style='text-decoration:none'>"
            "<span style='background:var(--green);color:#fff;border-radius:9px;"
            "padding:9px 16px;font-weight:600;font-size:14px'>Open / edit prices</span></a>"
            "<form method='post' action='/admin/garage/%s/delete' style='margin:0' "
            "onsubmit=\"return confirm('Delete %s permanently? This removes its prices, "
            "details and owner login. This cannot be undone.')\">"
            "<button type='submit' style='background:var(--red-bg);color:var(--red);border:1px "
            "solid #f0c9c4;border-radius:9px;padding:9px 16px;font-weight:600;font-size:14px;"
            "cursor:pointer'>Delete garage</button></form>"
            "</div>"
            "<p class='sub' style='margin:12px 0 0'>The owner also logs in at "
            "<code>/login</code> with their number and password. Whatever they (or you) save is "
            "quoted on WhatsApp from the next message.</p>"
            "</div></div>"
            % (
                _esc(info.get("name") or gid) + status_pill,
                check(prices_ok, "Prices filled in", "%d of %d filled" % (filled, total) if total else "no services listed"),
                check(not _missing(info.get("owner_alert_number")), "Owner alert number", "where booking alerts go"),
                check(not _missing(info.get("review_link")), "Google review link", "for the review request"),
                check(not _missing(info.get("maps_link")), "Maps location", "sent with the booking"),
                status_row("Owner onboarding", owner_html, "account · reminders · welcome"),
                _esc(link), _esc(link),
                _esc(gid), _esc((info.get("name") or gid).replace("'", "")),
            )
        )

    return _page("Prices & setup", "".join(body), "setup")


@router.post("/conversation/{conversation_id}/release")
def release_conversation(request: Request, conversation_id: int) -> Response:
    """Give a handed-over chat back to the bot right now, instead of waiting for
    the 24-hour auto-release. Clears the open handoff and any owner pause."""
    gate = _gate(request)
    if gate:
        return gate
    from . import conversations
    with SessionLocal() as db:
        conv = db.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="no such conversation")
        number, garage_id = conv.customer_number, conv.garage_id
    conversations.release(garage_id, number)
    return RedirectResponse(url="/admin/conversation/%d" % conversation_id, status_code=303)


@router.post("/garage/{garage_id}/delete")
def delete_garage(request: Request, garage_id: str) -> Response:
    """Operator removes a garage entirely: its knowledge files and owner login.

    Deliberately operator-only and behind the admin gate. The demo garage and
    anything with a bad id are refused rather than touched."""
    gate = _gate(request)
    if gate:
        return gate

    import shutil

    from .garages import GARAGES_DIR, _SAFE_ID, _cache

    if not _SAFE_ID.match(garage_id or ""):
        raise HTTPException(status_code=400, detail="bad garage id")

    folder = GARAGES_DIR / garage_id
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    _cache.pop(garage_id, None)

    # Remove the owner login too, so the number can sign up fresh later.
    with SessionLocal() as db:
        for row in db.query(Owner).filter_by(garage_id=garage_id).all():
            db.delete(row)
        db.commit()

    return RedirectResponse(url="/admin/setup", status_code=303)


# --------------------------------------------------------------------------- auth pages

def _login_page(error: str = "") -> HTMLResponse:
    msg = ("<p style='color:var(--red);font-size:14px;margin:0 0 14px'>%s</p>" % html.escape(error)) if error else ""
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Log in · Mistri</title><style>%s"
        "body{display:grid;place-items:center;min-height:100vh}"
        ".box{background:var(--card);border:1px solid var(--line);border-radius:16px;"
        "padding:30px;width:min(360px,92vw)}"
        ".box h1{font-size:22px;margin:0 0 4px}.box p.s{color:var(--ink3);font-size:14px;margin:0 0 20px}"
        "label{display:block;font-size:13px;font-weight:600;margin:12px 0 4px}"
        "input{width:100%%;padding:10px 12px;border:1.4px solid var(--line);border-radius:9px;"
        "font-size:15px;font-family:inherit}input:focus{outline:2px solid var(--green2);border-color:var(--green2)}"
        "button{width:100%%;margin-top:20px;background:var(--green);color:#fff;border:0;border-radius:10px;"
        "padding:12px;font-size:15px;font-weight:600;cursor:pointer}button:hover{background:var(--green2)}"
        "</style></head><body><form class='box' method='post' action='/admin/login'>"
        "<h1>Mistri</h1><p class='s'>Owner sign in</p>%s"
        "<label>Username</label><input name='username' autofocus autocomplete='username'>"
        "<label>Password</label><input name='password' type='password' autocomplete='current-password'>"
        "<button type='submit'>Log in</button></form></body></html>"
        % (STYLE, msg)
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    if settings.admin_password == DEFAULT_PASSWORD:
        return _gate(request)  # the 503 notice
    if _authed(request):
        return RedirectResponse(url="/admin/", status_code=307)
    return _login_page()


@router.post("/login")
def login_submit(username: str = Form(""), password: str = Form("")) -> Response:
    if settings.admin_password == DEFAULT_PASSWORD:
        return HTMLResponse("Set ADMIN_PASSWORD first.", status_code=503)
    if not _password_ok(username, password):
        return _login_page("Wrong username or password.")
    resp = RedirectResponse(url="/admin/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, _session_value(), httponly=True, samesite="lax",
                    secure=True, max_age=60 * 60 * 24 * 14)
    return resp


@router.get("/logout")
def logout() -> Response:
    resp = RedirectResponse(url="/admin/login", status_code=303)
    # Delete with the SAME attributes the cookie was set with. Chrome will not
    # replace a Secure; HttpOnly; SameSite cookie with a bare deletion header,
    # so without these the browser keeps the old cookie and logout looks broken.
    resp.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    # Belt and braces: also overwrite it with an already-expired empty value.
    resp.set_cookie(SESSION_COOKIE, "", max_age=0, expires=0, path="/",
                    secure=True, httponly=True, samesite="lax")
    return resp
