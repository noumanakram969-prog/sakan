"""The public privacy policy.

Meta requires a reachable privacy policy URL before an app can be cleared to
send, and the garage's customers are entitled to one regardless. Serving it from
the service means the URL exists the moment the service is deployed, and it
cannot drift out of date with what the code actually does.

It is written to be true rather than to be thorough: it says what is really
stored, for how long, and who else sees it. Have it read by someone who knows UAE
data rules before the first real customer message arrives.
"""
from __future__ import annotations

import html
from datetime import date

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .config import settings

router = APIRouter(tags=["public"])

STYLE = """
*{box-sizing:border-box}
body{margin:0;padding:0 22px 80px;background:#f5f7f6;color:#10201a;
  font:16px/1.65 'Segoe UI',-apple-system,BlinkMacSystemFont,Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:680px;margin:0 auto}
header{padding:54px 0 26px;border-bottom:1px solid #e4e9e6;margin-bottom:30px}
.brand{font-weight:700;color:#0b6b4f;letter-spacing:-.02em;font-size:17px;margin:0 0 14px}
h1{font-size:31px;font-weight:700;letter-spacing:-.03em;margin:0 0 6px;line-height:1.15}
.date{color:#7d8c84;font-size:14.5px;margin:0}
h2{font-size:18.5px;font-weight:700;letter-spacing:-.02em;margin:34px 0 8px}
p,li{color:#2f3d36}
p{margin:0 0 14px}
ul{margin:0 0 14px;padding-left:22px}
li{margin-bottom:7px}
strong{font-weight:600;color:#10201a}
.note{background:#fff;border:1px solid #e4e9e6;border-radius:12px;padding:18px 20px;margin:0 0 14px}
a{color:#0b6b4f}
footer{margin-top:44px;padding-top:22px;border-top:1px solid #e4e9e6;color:#7d8c84;font-size:14.5px}
"""


@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy() -> HTMLResponse:
    operator = html.escape(settings.operator_name)
    email = html.escape(settings.operator_email)
    updated = date.today().strftime("%d %B %Y")

    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy Policy · Mistri</title><style>{STYLE}</style></head><body><div class="wrap">

<header>
  <p class="brand">Mistri</p>
  <h1>Privacy Policy</h1>
  <p class="date">Last updated {updated}</p>
</header>

<p>Mistri is software that lets a car garage answer its own customers on WhatsApp.
It is operated by <strong>{operator}</strong>. Each garage using it remains
responsible for its own customers' information; we process that information on
the garage's behalf and on its instructions.</p>

<h2>What is collected</h2>
<p>When you message a garage that uses Mistri, the following is stored:</p>
<ul>
  <li>Your <strong>WhatsApp phone number</strong>, and the name shown on your WhatsApp profile.</li>
  <li>The <strong>messages you send</strong> to the garage, and the replies sent back.</li>
  <li>If you make a booking: your <strong>name, your car</strong> (make, model, year),
      the service you asked for, and the appointment time.</li>
  <li>The <strong>language</strong> you wrote in, and how quickly you were answered.</li>
</ul>
<p>Nothing else. No location, no contacts, no payment details, and no tracking of
you anywhere outside that conversation.</p>

<h2>Why it is collected</h2>
<ul>
  <li>To answer your question and to book your car in.</li>
  <li>To send you a reminder before an appointment you asked for.</li>
  <li>To let the garage owner see the conversation and call you back when the
      software cannot help.</li>
  <li>To count how many enquiries the garage received. These counts are numbers
      only and contain nothing that identifies you.</li>
</ul>

<h2>Who else sees it</h2>
<div class="note">
  <p style="margin:0"><strong>WhatsApp (Meta)</strong> carries the messages, as it does for any
  WhatsApp conversation.</p>
</div>
<div class="note">
  <p style="margin:0"><strong>Anthropic</strong> processes message text so the reply can be written.
  Messages are sent for that purpose only and are not used to train models.</p>
</div>
<div class="note">
  <p style="margin:0"><strong>The garage you messaged</strong> sees the conversation, as it would if a
  person had answered you.</p>
</div>
<p>Your information is not sold, not shared with advertisers, and not passed to
any other garage or business.</p>

<h2>How long it is kept</h2>
<p>Conversations and bookings are kept while the garage uses Mistri, so that the
garage has a record of what was said and what was booked. If a garage stops using
Mistri, its data is deleted within 90 days.</p>

<h2>What you can ask for</h2>
<p>You can ask for a copy of what is held about you, or ask for it to be deleted.
Message the garage and say so, or write to <a href="mailto:{email}">{email}</a>.
Deleting a booking record may mean the garage no longer has a record of work done
on your car.</p>

<h2>Stopping messages</h2>
<p>Reply <strong>STOP</strong> to the garage at any time and no further automated
messages will be sent to you. You can still message the garage normally.</p>

<h2>Children</h2>
<p>Mistri is not intended for anyone under 18 and is not directed at children.</p>

<h2>Changes</h2>
<p>If this policy changes, the date at the top changes with it.</p>

<h2>Contact</h2>
<p>{operator} &mdash; <a href="mailto:{email}">{email}</a></p>

<footer>
  This page is served by the Mistri service itself, so it always describes the
  version of the software that is running.
</footer>

</div></body></html>""")
