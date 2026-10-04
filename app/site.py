"""The public landing page — what Mistri is and why a garage owner should want
it, in plain terms. Served at the site root so the link is always live and
always matches the running product. No customer data, nothing private: this is
the page you send to a prospect.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from . import commands, garages, onboard

router = APIRouter(tags=["public"])

# The service list a brand-new garage starts with — the jobs a Dubai garage is
# most asked about on WhatsApp. Every price is TODO: the owner types the numbers
# in onboarding, and until then the assistant offers a free inspection instead.
COMMON_SERVICES = [
    ("oil_change", {"en": "Engine oil change", "ar": "تغيير زيت المحرك", "hi": "इंजन ऑयल चेंज"}),
    ("brake_repair", {"en": "Brake repair", "ar": "إصلاح الفرامل", "hi": "ब्रेक रिपेयर"}),
    ("battery_replacement", {"en": "Battery replacement", "ar": "تغيير البطارية", "hi": "बैटरी बदलना"}),
    ("tyre_service", {"en": "Tyre service", "ar": "خدمة الإطارات", "hi": "टायर सर्विस"}),
    ("ac_service", {"en": "AC service", "ar": "صيانة المكيف", "hi": "एसी सर्विस"}),
    ("computer_diagnostics", {"en": "Computer diagnostics", "ar": "فحص كمبيوتر", "hi": "कंप्यूटर डायग्नोस्टिक"}),
    ("general_service", {"en": "General service", "ar": "صيانة عامة", "hi": "जनरल सर्विस"}),
    ("engine_repair", {"en": "Engine repair", "ar": "إصلاح المحرك", "hi": "इंजन रिपेयर"}),
]


def _make_garage_id(name: str) -> str | None:
    """A safe, unique folder id from the garage name. None if nothing usable."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:40]
    if not base or not garages._SAFE_ID.match(base):
        base = ""
    if not base:
        return None
    gid, n = base, 2
    while (onboard.GARAGES_DIR / gid).exists():
        gid, n = "%s-%d" % (base, n), n + 1
    return gid


def _create_garage(name: str, number: str, area: str) -> str | None:
    """Create a pending garage from a website signup and return its id.

    Pending = inert: not routed to, not messaged by the scheduler, until the
    operator connects the WhatsApp number and flips it live. Prices start as a
    TODO template so the owner just types the numbers in onboarding."""
    gid = _make_garage_id(name)
    if gid is None:
        return None

    info = {
        "id": gid,
        "name": name,
        "pending": True,                       # operator activates after Meta connect
        "owner_alert_number": number,          # their WhatsApp, for alerts
        "area": area or "",
        "timezone": "Asia/Dubai",
        "languages": ["en", "ar", "hi", "ur"],
        "hours": {d: ["08:00", "19:00"] for d in ("mon", "tue", "wed", "thu", "fri", "sat")}
                 | {"sun": None},
        "max_cars_per_hour": 2,
        "service_due_months": 6,
        "followups_enabled": True,
        "service_due_enabled": True,
        "maps_link": "TODO",
        "review_link": "TODO",
    }
    prices = {
        "currency": "AED",
        "services": [
            {"id": sid, "name": nm, "prices": {"sedan": "TODO", "suv": "TODO", "luxury": "TODO"}}
            for sid, nm in COMMON_SERVICES
        ],
    }
    onboard._write(gid, "info", info)
    onboard._write(gid, "prices", prices)
    onboard._write(gid, "faq", {"faqs": []})
    garages._cache.pop(gid, None)
    return gid

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mistri</title>
<meta name="description" content="A WhatsApp assistant that answers your garage's customers day and night, on the number you already use, and books the car in.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800;900&family=Assistant:wght@400;500;600;700&display=swap">
<style>
*{box-sizing:border-box}
:root{
 --paper:#ffffff; --wash:#f4f8f5; --card:#ffffff; --ink:#0f1a16; --ink2:#48554f;
 --ink3:#7c8a83; --line:#e3eae5; --line2:#d3ddd7;
 --green:#0b6b4f; --green2:#0e8862; --greenlite:#e7f3ec; --gold:#a9781f; --goldbg:#fbf4e6;
 --red:#b23b3b; --redbg:#fdecec;
 --sans:"Assistant",-apple-system,"Segoe UI",sans-serif; --disp:"Archivo",sans-serif;
 --shadow:0 1px 2px rgba(16,40,30,.04),0 8px 24px rgba(16,40,30,.06);
}
html{background:var(--wash)}
body{margin:0;background:var(--wash);color:var(--ink);font-family:var(--sans);
 font-size:17px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}
.narrow{max-width:820px}
a{color:var(--green2)}
h1,h2,h3{text-wrap:balance}

/* reassurance ribbon */
.ribbon{background:var(--ink);color:#eaf3ee;font-size:14px;text-align:center;padding:9px 16px}
.ribbon b{color:#6fd6a8;font-weight:700}
.ribbon .dot{color:#5a6b63;margin:0 8px}
@media(max-width:560px){.ribbon .dot{display:none}.ribbon span.line{display:block}}

/* top bar */
.top{display:flex;align-items:center;justify-content:space-between;padding:20px 0}
.logo{font-family:var(--disp);font-weight:900;font-size:23px;letter-spacing:-.01em;color:var(--green)}
.logo .ar{font-family:var(--sans);font-weight:600;color:var(--ink3);font-size:15px;margin-left:8px;letter-spacing:.12em}
.top .actions{display:flex;align-items:center;gap:20px}
.top .actions a.login{font-size:14.5px;color:var(--ink2);text-decoration:none;font-weight:600}
.btn{display:inline-block;background:var(--green);color:#fff;text-decoration:none;font-weight:700;
 font-size:15px;padding:11px 20px;border-radius:11px;box-shadow:var(--shadow)}
.btn:hover{background:var(--green2)}
.btn.big{font-size:16.5px;padding:15px 28px}

/* hero */
.hero{display:grid;grid-template-columns:1.15fr .85fr;gap:48px;align-items:center;padding:34px 0 56px}
@media(max-width:840px){.hero{grid-template-columns:1fr;gap:36px;padding:20px 0 40px}}
.eyebrow{font-family:var(--disp);font-weight:700;font-size:12px;letter-spacing:.16em;
 text-transform:uppercase;color:var(--green);margin:0 0 16px}
h1{font-family:var(--disp);font-weight:800;font-size:clamp(34px,5.4vw,54px);line-height:1.04;
 letter-spacing:-.025em;margin:0}
.hero .lede{font-size:clamp(18px,2.4vw,20px);color:var(--ink2);margin:20px 0 0;line-height:1.5}
.hero .cta-row{display:flex;align-items:center;gap:18px;margin-top:30px;flex-wrap:wrap}
.hero .note{font-size:14px;color:var(--ink3)}

/* phone chat card */
.phone{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:18px 16px 20px;
 box-shadow:var(--shadow)}
.phone .bar{display:flex;align-items:center;gap:10px;padding:2px 6px 14px;border-bottom:1px solid var(--line);margin-bottom:14px}
.phone .av{width:34px;height:34px;border-radius:50%;background:var(--green);color:#fff;font-family:var(--disp);
 font-weight:800;display:grid;place-items:center;font-size:15px}
.phone .who{font-weight:700;font-size:15px}
.phone .who small{display:block;color:var(--green2);font-weight:600;font-size:12px}
.chat{display:flex;flex-direction:column;gap:9px}
.b{max-width:85%;padding:9px 13px;border-radius:14px;font-size:15px;line-height:1.45}
.b.them{align-self:flex-start;background:var(--wash);border:1px solid var(--line);border-top-left-radius:4px}
.b.us{align-self:flex-end;background:var(--greenlite);border-top-right-radius:4px}
.b.us b{color:var(--green)}
.b .t{display:block;font-size:11px;color:var(--ink3);margin-top:3px;text-align:right}

/* generic section */
section{padding:52px 0;border-top:1px solid var(--line)}
.kicker{font-family:var(--disp);font-weight:700;font-size:12px;letter-spacing:.15em;
 text-transform:uppercase;color:var(--green);margin:0 0 12px}
h2{font-family:var(--disp);font-weight:800;font-size:clamp(26px,3.8vw,36px);letter-spacing:-.02em;margin:0}
.sub{color:var(--ink2);margin:12px 0 0;font-size:17px;max-width:60ch}
.mt{margin-top:34px}

/* problem: before / after */
.ba{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:34px}
@media(max-width:720px){.ba{grid-template-columns:1fr}}
.col{border:1px solid var(--line);border-radius:16px;padding:22px 22px 8px;background:var(--card)}
.col.bad{background:var(--redbg);border-color:#f3d6d6}
.col.good{background:var(--greenlite);border-color:#cfe6d8}
.col .tag{font-family:var(--disp);font-weight:800;font-size:13px;letter-spacing:.04em;text-transform:uppercase}
.col.bad .tag{color:var(--red)}
.col.good .tag{color:var(--green)}
.col ul{list-style:none;padding:0;margin:14px 0 14px}
.col li{position:relative;padding:8px 0 8px 26px;font-size:15.5px;color:var(--ink);border-top:1px solid rgba(0,0,0,.05)}
.col li:first-child{border-top:0}
.col li::before{position:absolute;left:0;top:8px;font-weight:800}
.col.bad li::before{content:"\\2715";color:var(--red)}
.col.good li::before{content:"\\2713";color:var(--green)}

/* money / ROI */
.money{background:var(--ink);color:#eaf3ee;border-radius:22px;padding:40px 36px;margin-top:20px}
@media(max-width:720px){.money{padding:30px 22px}}
.money .kicker{color:#6fd6a8}
.money h2{color:#fff}
.money .sub{color:#b7c8bf}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin-top:34px}
@media(max-width:640px){.stats{grid-template-columns:1fr;gap:16px}}
.stat .n{font-family:var(--disp);font-weight:800;font-size:38px;line-height:1;color:#fff;letter-spacing:-.02em}
.stat .n span{font-size:20px;color:#6fd6a8}
.stat .l{color:#a9bcb2;font-size:14.5px;margin-top:8px;line-height:1.4}
.roi{margin-top:34px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:16px;overflow:hidden}
.roi .rh{padding:16px 22px;font-family:var(--disp);font-weight:700;font-size:14px;letter-spacing:.05em;
 text-transform:uppercase;color:#6fd6a8;border-bottom:1px solid rgba(255,255,255,.12)}
.roi table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.roi td{padding:13px 22px;border-top:1px solid rgba(255,255,255,.08);font-size:15.5px}
.roi tr:first-child td{border-top:0}
.roi td:last-child{text-align:right;font-weight:700;color:#fff}
.roi .total td{background:rgba(111,214,168,.12);font-weight:800;color:#fff}
.roi .total td:first-child{color:#6fd6a8}
.money .fine{color:#8ca298;font-size:13px;margin-top:14px}

/* automation grid */
.auto{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:34px}
@media(max-width:820px){.auto{grid-template-columns:1fr 1fr}}
@media(max-width:520px){.auto{grid-template-columns:1fr}}
.a{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}
.a .i{width:36px;height:36px;border-radius:10px;background:var(--greenlite);color:var(--green);
 display:grid;place-items:center;font-size:19px;margin-bottom:12px}
.a h3{font-size:16px;font-weight:700;margin:0 0 5px}
.a p{margin:0;color:var(--ink2);font-size:14.5px}

/* steps */
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:34px}
@media(max-width:720px){.steps{grid-template-columns:1fr;gap:18px}}
.step .n{font-family:var(--disp);font-weight:800;color:#fff;background:var(--green);width:34px;height:34px;
 border-radius:9px;display:grid;place-items:center;font-size:17px;margin-bottom:12px}
.step h3{font-size:17px;font-weight:700;margin:0 0 4px}
.step p{margin:0;color:var(--ink2);font-size:15px}

/* rules */
.rules{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:34px}
@media(max-width:560px){.rules{grid-template-columns:1fr}}
.rule{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;border-left:3px solid var(--green)}
.rule h3{font-family:var(--disp);font-weight:700;font-size:16px;margin:0 0 5px}
.rule p{margin:0;color:var(--ink2);font-size:14.5px}

/* real-review cards */
.reviews{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:30px}
@media(max-width:760px){.reviews{grid-template-columns:1fr}}
.rev{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;
 box-shadow:var(--shadow);border-top:3px solid var(--red);display:flex;flex-direction:column}
.rev .stars{font-size:15px;letter-spacing:2px;margin-bottom:9px;color:#e0a400}
.rev .stars .off{color:var(--line2)}
.rev p{margin:0 0 14px;font-size:14.5px;color:var(--ink);line-height:1.5;flex:1}
.rev .src{display:flex;align-items:center;gap:9px;font-size:12.5px;color:var(--ink3)}
.rev .src .g{width:22px;height:22px;border-radius:50%;background:var(--wash);border:1px solid var(--line);
 display:grid;place-items:center;font-weight:800;color:var(--ink2);font-size:11px}
.revnote{font-size:12.5px;color:var(--ink3);margin-top:14px;font-style:italic;text-align:center}
.fixmap{display:grid;gap:10px;margin-top:26px}
.fixrow{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:640px){.fixrow{grid-template-columns:1fr}}
.fixrow>div{border-radius:12px;padding:14px 16px;font-size:14.5px;line-height:1.45}
.fixrow .pain{background:var(--redbg);border:1px solid #f3d6d6}
.fixrow .fix{background:var(--greenlite);border:1px solid #cfe6d8}
.fixrow .pain b{color:var(--red)}
.fixrow .fix b{color:var(--green)}
.fixlabel{font-family:var(--disp);font-weight:700;font-size:12px;letter-spacing:.05em;
 text-transform:uppercase;margin-bottom:4px;display:block}
.fixrow .pain .fixlabel{color:var(--red)}
.fixrow .fix .fixlabel{color:var(--green)}

/* pricing */
.price{background:var(--card);border:1px solid var(--line2);border-radius:20px;padding:34px;margin-top:34px;
 box-shadow:var(--shadow);display:grid;grid-template-columns:1fr auto;gap:30px;align-items:center}
@media(max-width:720px){.price{grid-template-columns:1fr;gap:22px;text-align:center}}
.price .amt{font-family:var(--disp);font-weight:800;font-size:46px;line-height:1;letter-spacing:-.02em}
.price .amt small{font-size:18px;color:var(--ink3);font-weight:600}
.price .free{display:inline-block;background:var(--goldbg);color:var(--gold);font-weight:700;font-size:13px;
 padding:5px 12px;border-radius:999px;margin-bottom:14px}
.price ul{list-style:none;padding:0;margin:16px 0 0;columns:2;column-gap:26px}
@media(max-width:720px){.price ul{columns:1;text-align:left;max-width:300px;margin:16px auto 0}}
.price li{padding:5px 0 5px 24px;position:relative;font-size:15px;color:var(--ink)}
.price li::before{content:"\\2713";position:absolute;left:0;color:var(--green);font-weight:800}

/* plans */
.plans{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:34px;align-items:stretch}
@media(max-width:640px){.plans{grid-template-columns:1fr}}
.plan{background:var(--card);border:1px solid var(--line2);border-radius:18px;padding:26px 24px;
 box-shadow:var(--shadow);display:flex;flex-direction:column;position:relative}
.plan.best{border:2px solid var(--green);box-shadow:0 10px 30px rgba(11,107,79,.14)}
.pbadge{position:absolute;top:-12px;left:50%;transform:translateX(-50%);white-space:nowrap;
 background:var(--green);color:#fff;font-family:var(--disp);font-weight:700;font-size:12px;
 letter-spacing:.03em;padding:5px 14px;border-radius:999px}
.pname{font-family:var(--disp);font-weight:700;font-size:15px;letter-spacing:.04em;text-transform:uppercase;
 color:var(--green);margin-bottom:10px}
.pamt{font-family:var(--disp);font-weight:800;font-size:42px;line-height:1;letter-spacing:-.02em}
.pamt small{font-size:16px;color:var(--ink3);font-weight:600;letter-spacing:0}
.pnote{color:var(--ink2);font-size:14.5px;margin-top:8px}
.psave{display:inline-block;background:var(--goldbg);color:var(--gold);font-weight:700;font-size:12.5px;
 padding:4px 11px;border-radius:999px;margin-top:12px;align-self:flex-start}
.plan .btn{margin-top:20px;text-align:center}
.plan.best .btn{background:var(--green)}
.plan .btn.ghost{background:transparent;color:var(--green);border:1.5px solid var(--line2)}
.plan .btn.ghost:hover{border-color:var(--green);background:var(--greenlite)}
.incl{margin-top:24px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 24px}
.incl h4{font-family:var(--disp);font-weight:700;font-size:13px;letter-spacing:.05em;text-transform:uppercase;
 color:var(--ink3);margin:0 0 14px}
.incl ul{list-style:none;padding:0;margin:0;columns:2;column-gap:26px}
@media(max-width:560px){.incl ul{columns:1}}
.incl li{padding:5px 0 5px 24px;position:relative;font-size:15px;color:var(--ink)}
.incl li::before{content:"\\2713";position:absolute;left:0;color:var(--green);font-weight:800}

/* languages */
.langgrid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:34px}
@media(max-width:640px){.langgrid{grid-template-columns:1fr}}
.langex{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:var(--shadow)}
.langex .lh{font-family:var(--disp);font-weight:700;font-size:13px;letter-spacing:.05em;text-transform:uppercase;
 color:var(--green);margin-bottom:14px}
.langex .chat{gap:8px}
.langex .b{max-width:88%;font-size:14.5px}

/* tags */
.tags{display:flex;flex-wrap:wrap;gap:10px;margin-top:24px}
.tag{background:var(--greenlite);color:var(--green);border-radius:999px;padding:7px 15px;font-weight:600;font-size:14px}

/* final cta */
.final{background:var(--green);color:#fff;border-radius:22px;padding:46px 36px;text-align:center;margin:52px 0}
.final h2{color:#fff}
.final p{color:rgba(255,255,255,.9);max-width:44ch;margin:12px auto 26px;font-size:17px}
.final .btn{background:#fff;color:var(--green)}
.final .btn:hover{background:#eef7f1}

footer{padding:20px 0 60px;color:var(--ink3);font-size:14px;text-align:center;border-top:1px solid var(--line)}

/* contact form on the green panel */
.final form{max-width:440px;margin:22px auto 0;text-align:left;display:grid;gap:12px}
.final .frow{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:520px){.final .frow{grid-template-columns:1fr}}
.final label{display:block;font-size:13px;font-weight:600;color:rgba(255,255,255,.9);margin:0 0 5px}
.final input,.final textarea{width:100%;padding:11px 13px;border:0;border-radius:10px;
 font-size:15px;font-family:inherit;background:#fff;color:var(--ink)}
.final textarea{resize:vertical;min-height:76px}
.final input:focus,.final textarea:focus{outline:3px solid rgba(255,255,255,.5)}
.final .btn{background:#fff;color:var(--green);width:100%;border:0;cursor:pointer;margin-top:4px}
.final .btn:hover{background:#eef7f1}
.final .tiny{color:rgba(255,255,255,.8);font-size:12.5px;text-align:center;margin:2px 0 0}
</style></head><body>

<div class="ribbon">
  <span class="line"><b>No app to install.</b> No reinstalling WhatsApp.</span>
  <span class="dot">·</span>
  <span class="line"><b>No new number.</b> We only need the number you already use.</span>
  <span class="dot">·</span>
  <span class="line"><b>Leave anytime.</b></span>
</div>

<div class="wrap">

  <div class="top">
    <div class="logo">Mistri <span class="ar">مستري</span></div>
    <div class="actions">
      <a class="login" href="/login">Owner login</a>
      <a class="btn" href="/start">Set up your garage</a>
    </div>
  </div>

  <!-- HERO -->
  <div class="hero">
    <div>
      <p class="eyebrow">WhatsApp assistant for car garages</p>
      <h1>Stop losing customers to the messages you never answered.</h1>
      <p class="lede">Mistri replies to your customers on the WhatsApp number you already use —
      quotes your prices, answers hours and location, and books the car in — instantly, day and night,
      in their own language. You keep your phone exactly as it is.</p>
      <div class="cta-row">
        <a class="btn big" href="#demo">See it on your phone</a>
        <span class="note">No new number · No app · Live in a day</span>
      </div>
    </div>

    <div class="phone">
      <div class="bar">
        <div class="av">M</div>
        <div class="who">Your garage <small>● online · replies in seconds</small></div>
      </div>
      <div class="chat">
        <div class="b them">how much for oil change on my camry 2019?<span class="t">11:42 pm</span></div>
        <div class="b us">Oil change, Toyota Camry 2019 — <b>AED 180</b>.<br>Tomorrow 10:00 is free. Shall I book you in?<span class="t">11:42 pm</span></div>
        <div class="b them">yes please<span class="t">11:43 pm</span></div>
        <div class="b us">Booked ✅ Camry 2019, oil change, 10:00.<br>See you tomorrow!<span class="t">11:43 pm</span></div>
        <div class="b them">شكراً</div>
        <div class="b us">You're welcome! Drive safe. 🚗</div>
      </div>
    </div>
  </div>

  <!-- WHY GARAGES LOSE CUSTOMERS -->
  <section>
    <div class="narrow">
      <p class="kicker">Why garages lose customers</p>
      <h2>Read any garage's 1-star reviews. It's almost never the repair.</h2>
      <p class="sub">We went through hundreds of reviews of car garages in the UAE. The bad ones
      nearly all say the same thing — nobody replied, nobody kept them updated, and the price was a
      surprise. The work wasn't the problem. The silence was.</p>
    </div>

    <div class="reviews">
      <div class="rev">
        <div class="stars">&#9733;<span class="off">&#9733;&#9733;&#9733;&#9733;</span></div>
        <p>"They didn't answer my calls or WhatsApp for days. I had to keep chasing just to find out
        what was happening with my car."</p>
        <div class="src"><span class="g">G</span> 1-star review · UAE garage</div>
      </div>
      <div class="rev">
        <div class="stars">&#9733;<span class="off">&#9733;&#9733;&#9733;&#9733;</span></div>
        <p>"Promised the car on Tuesday, I got it Friday — and nobody ever called to tell me it was
        delayed. Started as a 5-star, ended like this."</p>
        <div class="src"><span class="g">G</span> 1-star review · UAE garage</div>
      </div>
      <div class="rev">
        <div class="stars">&#9733;<span class="off">&#9733;&#9733;&#9733;&#9733;</span></div>
        <p>"The bill was three times what I expected. No estimate up front, and the invoice only came
        when I insisted on it."</p>
        <div class="src"><span class="g">G</span> 1-star review · UAE garage</div>
      </div>
    </div>
    <p class="revnote">Representative of real public reviews of UAE garages. Names and businesses omitted.</p>

    <div class="narrow" style="margin-top:38px">
      <h2 style="font-size:clamp(22px,3.4vw,28px)">Mistri fixes the exact thing that sinks their scores.</h2>
    </div>
    <div class="fixmap">
      <div class="fixrow">
        <div class="pain"><span class="fixlabel">The complaint</span>"No reply to my calls or WhatsApp for days."</div>
        <div class="fix"><span class="fixlabel">Mistri</span>Answers <b>every</b> message in seconds, 24/7, in the customer's language.</div>
      </div>
      <div class="fixrow">
        <div class="pain"><span class="fixlabel">The complaint</span>"Nobody told me it was delayed. I had to keep chasing."</div>
        <div class="fix"><span class="fixlabel">Mistri</span>Sends the booking, the reminder and the confirmation <b>automatically</b> — they're never left guessing.</div>
      </div>
      <div class="fixrow">
        <div class="pain"><span class="fixlabel">The complaint</span>"The bill was 3× what I expected. No estimate up front."</div>
        <div class="fix"><span class="fixlabel">Mistri</span>Quotes <b>only your sheet price</b> — the number they're told is the number. Never invented.</div>
      </div>
      <div class="fixrow">
        <div class="pain"><span class="fixlabel">The complaint</span>"They went cold after I paid. Never asked how it went."</div>
        <div class="fix"><span class="fixlabel">Mistri</span>Follows up after the job and asks happy customers for a <b>Google review</b> — turning good work into 5-stars.</div>
      </div>
    </div>
  </section>

  <!-- THE MONEY -->
  <section>
    <div class="money">
      <p class="kicker">The money</p>
      <h2>It pays for itself with one recovered job a month.</h2>
      <p class="sub">Mistri isn't a cost — it's the jobs you're already losing, brought back.</p>

      <div class="stats">
        <div class="stat">
          <div class="n">40<span>%</span></div>
          <div class="l">of garage enquiries arrive outside working hours — exactly when no one replies</div>
        </div>
        <div class="stat">
          <div class="n">&lt;60<span>s</span></div>
          <div class="l">Mistri's reply time, day or night — before the customer messages the next garage</div>
        </div>
        <div class="stat">
          <div class="n">AED&nbsp;150<span>–2,000</span></div>
          <div class="l">the value of a single job you save from going cold — from an oil change to a repair</div>
        </div>
      </div>

      <div style="margin-top:30px;display:flex;flex-wrap:wrap;align-items:center;gap:14px 26px;
        background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:20px 24px">
        <div style="flex:1;min-width:190px">
          <div style="font-family:var(--disp);font-weight:800;font-size:26px;color:#fff">AED&nbsp;4,000<span style="font-size:15px;color:#b7c8bf">/mo</span></div>
          <div style="color:#b7c8bf;font-size:14px;margin-top:4px">a person to answer your WhatsApp all day — and only 9 to 6</div>
        </div>
        <div style="color:#6fd6a8;font-family:var(--disp);font-weight:800;font-size:16px">vs</div>
        <div style="flex:1;min-width:190px">
          <div style="font-family:var(--disp);font-weight:800;font-size:26px;color:#6fd6a8">AED&nbsp;600<span style="font-size:15px;color:#b7c8bf">/mo</span></div>
          <div style="color:#b7c8bf;font-size:14px;margin-top:4px">Mistri — 24/7, every language, never off sick or on leave</div>
        </div>
      </div>

      <div class="roi">
        <div class="rh">A typical month</div>
        <table>
          <tr><td>Mistri subscription</td><td>− AED 600</td></tr>
          <tr><td>3 oil changes you'd have missed at night</td><td>+ AED 540</td></tr>
          <tr><td>1 brake job recovered from a weekend message</td><td>+ AED 650</td></tr>
          <tr><td>2 inspections booked that would've gone cold</td><td>+ AED 400</td></tr>
          <tr class="total"><td>Net gain in one month</td><td>+ AED 990</td></tr>
        </table>
      </div>
      <p class="fine">Illustrative example — real numbers depend on your prices and message volume. The point holds:
      a handful of recovered jobs covers the fee many times over.</p>
    </div>
  </section>

  <!-- AUTOMATION -->
  <section>
    <div class="narrow">
      <p class="kicker">The automation</p>
      <h2>It runs the front desk while you run the workshop.</h2>
      <p class="sub">Set your prices once. From then on, it works on its own — no screen to watch, nothing to switch on.</p>
    </div>
    <div class="auto">
      <div class="a"><div class="i">⚡</div><h3>Answers instantly</h3><p>Prices, hours, location, services — replied in seconds, around the clock.</p></div>
      <div class="a"><div class="i">📅</div><h3>Books the car in</h3><p>Offers a time, confirms the slot, and holds the booking — no back-and-forth from you.</p></div>
      <div class="a"><div class="i">🔔</div><h3>Alerts you</h3><p>A WhatsApp ping the moment a car is booked, with the customer's number.</p></div>
      <div class="a"><div class="i">✅</div><h3>Confirms the day before</h3><p>Reminds every customer and asks them to confirm — so cars don't just not show up.</p></div>
      <div class="a"><div class="i">📞</div><h3>Flags the no-shows</h3><p>Each morning it tells you which of today's cars never confirmed, so you can call.</p></div>
      <div class="a"><div class="i">⭐</div><h3>Asks for reviews</h3><p>After a happy job, it asks the customer for a Google review — more reviews, more customers.</p></div>
      <div class="a"><div class="i">🔄</div><h3>Brings cars back</h3><p>Months later it reminds them the car is due again — the jobs most garages forget to chase.</p></div>
      <div class="a"><div class="i">🌍</div><h3>Speaks their language</h3><p>English, Arabic, Hindi, Urdu — in script or Roman letters, automatically.</p></div>
      <div class="a"><div class="i">📊</div><h3>Sums up your day</h3><p>An evening summary of every chat, quote and booking — so nothing slips.</p></div>
      <div class="a"><div class="i">📵</div><h3>Steps aside for you</h3><p>Reply to any chat yourself and it goes quiet there. You're always in control.</p></div>
    </div>
  </section>

  <!-- HOW IT WORKS -->
  <section>
    <div class="narrow">
      <p class="kicker">How it works</p>
      <h2>Nothing changes on your phone.</h2>
      <p class="sub">It sits on your existing WhatsApp Business number — the same one on your sign and your Google listing.</p>
    </div>
    <div class="steps">
      <div class="step"><div class="n">1</div><h3>A customer messages your normal number</h3><p>No new number to advertise. No app for them or you to install.</p></div>
      <div class="step"><div class="n">2</div><h3>Mistri answers in seconds</h3><p>From your own price list, in the customer's language, day or night.</p></div>
      <div class="step"><div class="n">3</div><h3>It books the car and tells you</h3><p>You get an alert for every booking and a summary each evening.</p></div>
    </div>
  </section>

  <!-- SAFETY RULES -->
  <section>
    <div class="narrow">
      <p class="kicker">The safety</p>
      <h2>It only ever says what you tell it.</h2>
      <p class="sub">The part that protects your name: it never guesses a price and never pretends to diagnose.</p>
    </div>
    <div class="rules">
      <div class="rule"><h3>Never invents a price</h3><p>It quotes only what's on your sheet. Not listed? It offers a free inspection and calls you.</p></div>
      <div class="rule"><h3>Never diagnoses</h3><p>A noise or a warning light books an inspection — it never guesses what's wrong.</p></div>
      <div class="rule"><h3>Hands over when unsure</h3><p>Anything it can't answer goes straight to you, with the customer's number.</p></div>
      <div class="rule"><h3>You're always in charge</h3><p>Jump into any chat and it steps back. Switch it off whenever you like.</p></div>
    </div>
  </section>

  <!-- LANGUAGES -->
  <section>
    <div class="narrow">
      <p class="kicker">The languages</p>
      <h2>It answers Arabic and Urdu the way your customers actually type.</h2>
      <p class="sub">Mistri reads each message and replies in the <em>same</em> language and the
      <em>same</em> script — Arabic script back to Arabic script, and Roman Urdu back to Roman Urdu.
      Nobody gets forced into formal writing they don't use.</p>
    </div>
    <div class="langgrid">
      <div class="langex">
        <div class="lh">Roman Urdu</div>
        <div class="chat">
          <div class="b them">bhai oil change kitne ka hai?</div>
          <div class="b us">Oil change, aap ki gari ka — <b>AED 180</b>.<br>Kal 10:00 khali hai. Book kar dun?</div>
        </div>
      </div>
      <div class="langex">
        <div class="lh">العربية</div>
        <div class="chat" dir="rtl">
          <div class="b them">السلام عليكم، بكم تغيير الزيت؟</div>
          <div class="b us">تغيير الزيت لسيارتك — <b>AED 180</b>.<br>بكرة الساعة 10:00 متوفر. أحجز لك؟</div>
        </div>
      </div>
    </div>
    <p class="sub mt">The chosen language sticks to the whole conversation — even the evening reminder
    goes out in it. And the safety rules hold in every language: the price and the time are still
    looked up from your sheet, never invented, whatever language it's writing in.</p>
    <div class="tags">
      <span class="tag">English</span><span class="tag">العربية</span>
      <span class="tag">हिन्दी</span><span class="tag">اردو</span>
      <span class="tag">Roman Urdu</span><span class="tag">Roman Hindi</span>
    </div>
  </section>

  <!-- GET STARTED -->
  <section>
    <div class="narrow">
      <p class="kicker">Get started</p>
      <h2>Set up your garage yourself, in minutes.</h2>
      <p class="sub">No sales call, no paperwork. Create your garage, add your prices, and your
      WhatsApp assistant is ready. It only goes live on your number when you're happy — free for
      30 days.</p>
    </div>
    <div class="steps">
      <div class="step"><div class="n">1</div><h3>Create your garage</h3><p>Your garage name and WhatsApp number — that's all it takes to start.</p></div>
      <div class="step"><div class="n">2</div><h3>Add your prices</h3><p>Type your prices for the common jobs. Leave any that depend on the car blank.</p></div>
      <div class="step"><div class="n">3</div><h3>Go live</h3><p>We connect it to your number and it starts answering your customers.</p></div>
    </div>
    <div style="text-align:center;margin-top:32px">
      <a class="btn big" href="/start">Set up your garage &rarr;</a>
    </div>
  </section>

  <!-- PRICING -->
  <section>
    <div class="narrow">
      <p class="kicker">Simple pricing</p>
      <h2>Test it free for 30 days. If you're happy, pick a plan.</h2>
      <p class="sub">Run it on your own number for a full month with everything switched on.
      See the bookings it brings in, the messages it catches at night. Only pay if it's earning
      its place — no card to start, no lock-in, nothing to uninstall.</p>
    </div>

    <div class="plans">
      <div class="plan">
        <div class="pname">Monthly</div>
        <div class="pamt">AED 600<small> /month</small></div>
        <div class="pnote">Pay month to month. Leave anytime.</div>
        <a class="btn ghost" href="#demo">Start free, then AED 600/mo</a>
      </div>
      <div class="plan best">
        <div class="pbadge">Best value · save AED 800</div>
        <div class="pname">3 Months</div>
        <div class="pamt">AED 1,000<small> /3 months</small></div>
        <div class="pnote">Just AED 333 a month.</div>
        <span class="psave">vs AED 1,800 monthly</span>
        <a class="btn" href="#demo">Start free, then AED 1,000</a>
      </div>
    </div>

    <div class="incl">
      <h4>Every plan includes</h4>
      <ul>
        <li>Your existing number</li>
        <li>Unlimited messages</li>
        <li>All four languages</li>
        <li>Bookings &amp; reminders</li>
        <li>No-show &amp; review chasing</li>
        <li>Evening summaries</li>
        <li>Bring-cars-back nudges</li>
        <li>First 30 days free</li>
      </ul>
    </div>
  </section>

  <!-- FINAL CTA -->
  <div class="final" id="demo">
    <h2>See it answer with your own prices.</h2>
    <p>Leave your number and a message. We'll set it up with your price list and let you
    try it yourself — free for 30 days, on your own number, nothing to install.</p>
    <form method="post" action="/contact">
      <div class="frow">
        <div><label>Your name</label><input name="name" maxlength="120" placeholder="Name"></div>
        <div><label>WhatsApp number</label><input name="number" maxlength="32" required placeholder="05X XXX XXXX"></div>
      </div>
      <div><label>Message (optional)</label><textarea name="message" maxlength="1000" placeholder="Tell us about your garage, or just say hi"></textarea></div>
      <button class="btn big" type="submit">Send message</button>
      <p class="tiny">We reply on WhatsApp — usually the same day.</p>
    </form>
  </div>

</div>
<footer>Mistri · WhatsApp assistant for garages · Dubai
  &nbsp;·&nbsp; <a href="/guides" style="color:var(--ink3)">Car help</a>
  &nbsp;·&nbsp; <a href="/admin/" style="color:var(--ink3)">Operator login</a></footer>
</body></html>"""


_THANKS = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thank you · Mistri</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f8f5;
 font-family:"Assistant",-apple-system,"Segoe UI",sans-serif;color:#0f1a16;padding:24px}
.box{max-width:440px;text-align:center;background:#fff;border:1px solid #e3eae5;border-radius:20px;
 padding:40px 32px;box-shadow:0 8px 24px rgba(16,40,30,.06)}
.tick{width:56px;height:56px;border-radius:50%;background:#e7f3ec;color:#0b6b4f;display:grid;
 place-items:center;font-size:30px;margin:0 auto 18px}
h1{font-family:"Archivo",sans-serif;font-size:26px;margin:0 0 8px;letter-spacing:-.02em}
p{color:#48554f;font-size:16px;margin:0 0 22px}
a{display:inline-block;background:#0b6b4f;color:#fff;text-decoration:none;font-weight:700;
 padding:12px 22px;border-radius:11px}
</style></head><body>
<div class="box">
  <div class="tick">&#10003;</div>
  <h1>Message received</h1>
  <p>Thanks for reaching out. We'll get back to you on WhatsApp, usually the same day.</p>
  <a href="/">Back to the page</a>
</div></body></html>"""


@router.get("/", response_class=HTMLResponse)
def landing() -> HTMLResponse:
    return HTMLResponse(PAGE)


@router.post("/contact", response_class=HTMLResponse)
def contact(
    name: str = Form(""),
    number: str = Form(""),
    message: str = Form(""),
) -> HTMLResponse:
    """A demo request from the landing page. Lands in the admin inbox — no email,
    nothing sent anywhere; the operator replies from there whenever he looks."""
    name = (name or "").strip()[:200]
    number = (number or "").strip()[:32]
    message = (message or "").strip()[:1000]

    # A number or a message — otherwise it's an empty submit, not a lead.
    if not number and not message:
        return HTMLResponse(_THANKS)

    from .db import Lead, SessionLocal

    with SessionLocal() as db:
        db.add(Lead(name=name, number=number, message=message))
        db.commit()
    return HTMLResponse(_THANKS)


_START_STYLE = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;
 background:#f4f8f5;font-family:"Assistant",-apple-system,"Segoe UI",sans-serif;color:#0f1a16;padding:24px}
.box{width:min(460px,94vw);background:#fff;border:1px solid #e3eae5;border-radius:20px;padding:34px;
 box-shadow:0 8px 24px rgba(16,40,30,.06)}
.ey{font-family:"Archivo",sans-serif;font-weight:700;font-size:12px;letter-spacing:.14em;
 text-transform:uppercase;color:#0b6b4f;margin:0 0 8px}
h1{font-family:"Archivo",sans-serif;font-size:27px;margin:0 0 6px;letter-spacing:-.02em}
p.s{color:#48554f;font-size:15px;margin:0 0 22px}
label{display:block;font-size:13px;font-weight:600;margin:14px 0 5px}
input{width:100%;padding:11px 13px;border:1.4px solid #d3ddd7;border-radius:10px;font-size:15px;font-family:inherit}
input:focus{outline:2px solid #0e8862;border-color:#0e8862}
button{width:100%;margin-top:22px;background:#0b6b4f;color:#fff;border:0;border-radius:11px;padding:14px;
 font-size:16px;font-weight:700;font-family:"Archivo",sans-serif;cursor:pointer}
button:hover{background:#0e8862}
.err{color:#b23b3b;font-size:14px;margin:0 0 12px}
.foot{color:#7d8a83;font-size:13px;margin-top:16px;text-align:center}
.foot a{color:#0b6b4f;font-weight:600}
"""


def _start_page(error: str = "", name: str = "", number: str = "") -> HTMLResponse:
    err = ("<p class='err'>%s</p>" % error) if error else ""
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?"
        "family=Archivo:wght@700;800&family=Assistant:wght@400;600;700&display=swap'>"
        "<title>Set up your garage · Mistri</title><style>%s</style></head><body>"
        "<form class='box' method='post' action='/start'>"
        "<p class='ey'>Mistri · get started</p>"
        "<h1>Set up your garage</h1>"
        "<p class='s'>Create your account, then add your prices — and your WhatsApp "
        "assistant is ready. Free for 30 days.</p>%s"
        "<label>Garage name</label>"
        "<input name='name' value='%s' maxlength='120' required placeholder='e.g. Al Noor Auto Garage'>"
        "<label>Your WhatsApp number</label>"
        "<input name='number' value='%s' maxlength='32' required placeholder='05X XXX XXXX'>"
        "<label>Choose a password</label>"
        "<input name='password' type='password' minlength='6' required placeholder='At least 6 characters'>"
        "<label>Area (optional)</label>"
        "<input name='area' maxlength='80' placeholder='e.g. Al Quoz, Dubai'>"
        "<button type='submit'>Create account &amp; add prices &rarr;</button>"
        "<p class='foot'>Already set up? <a href='/login'>Log in</a> &nbsp;·&nbsp; "
        "No app to install · leave anytime</p>"
        "</form></body></html>"
        % (_START_STYLE, err, _esc(name), _esc(number))
    )


def _esc(v) -> str:
    import html as _html
    return _html.escape("" if v is None else str(v))


@router.get("/start", response_class=HTMLResponse)
def start_form() -> HTMLResponse:
    return _start_page()


@router.post("/start")
def start_submit(background: BackgroundTasks, name: str = Form(""), number: str = Form(""),
                 password: str = Form(""), area: str = Form("")):
    from . import owners

    name = (name or "").strip()[:120]
    raw_number = number
    number = commands.normalise(number) or ""
    password = (password or "").strip()
    area = (area or "").strip()[:80]

    if not name:
        return _start_page("Please enter your garage name.", name, raw_number)
    if not number:
        return _start_page("Please enter a valid WhatsApp number.", name, raw_number)
    if len(password) < 6:
        return _start_page("Please choose a password of at least 6 characters.", name, raw_number)
    if owners.number_taken(number):
        return _start_page("That number is already set up — please log in instead.", name, raw_number)

    gid = _create_garage(name, number, area)
    if gid is None:
        return _start_page("Sorry, we couldn't use that name — try letters and numbers.", name, raw_number)

    owners.create_account(gid, number, password)

    # Tell the operator a new garage signed up, so the number gets connected.
    from .db import Lead, SessionLocal
    with SessionLocal() as db:
        db.add(Lead(name="NEW GARAGE: %s" % name, number=number,
                    message="Signed up on the website (%s). Connect their WhatsApp number to go live."
                            % (area or "no area given")))
        db.commit()

    # WhatsApp them a welcome + their setup link (delivers once the template is
    # approved in Meta). Best-effort, never blocks signup.
    from . import nudges
    background.add_task(nudges.send_signup_confirmation, gid)

    # Log them in and drop them straight into onboarding — their private prices page.
    resp = RedirectResponse(url="/onboard/%s?t=%s" % (gid, onboard.token_for(gid)), status_code=303)
    owners.log_in(resp, gid)
    return resp
