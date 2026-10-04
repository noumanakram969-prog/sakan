"""The owner-facing setup page: a private link where a garage fills its own
prices, details and common questions, and it lands straight in the price sheet
the bot reads.

This is how a garage goes live, and how garage #2..#N onboard without anyone
typing YAML. It writes the same `garages/<id>/*.yaml` files the engine already
loads, so a save takes effect on the next message (the loader reloads on mtime).

Guarded by a per-garage token in the URL — the price sheet is the one thing the
whole product trusts, so it is not editable by anyone who merely finds the path.
The owner's numbers are still the owner's numbers; nothing here invents a price.
"""
from __future__ import annotations

import hashlib
import hmac
import html
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import garages
from .config import settings

router = APIRouter(prefix="/onboard", tags=["onboard"])

GARAGES_DIR = Path(__file__).resolve().parent.parent / "garages"
DAYS = [("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"), ("thu", "Thursday"),
        ("fri", "Friday"), ("sat", "Saturday"), ("sun", "Sunday")]
CATS = ("sedan", "suv", "luxury")


def token_for(garage_id: str) -> str:
    """Stable per-garage link secret. Whoever has the link may edit that garage."""
    key = (settings.admin_password or "mistri").encode()
    return hmac.new(key, ("onboard:" + garage_id).encode(), hashlib.sha256).hexdigest()[:24]


def _check(garage_id: str, t: str) -> None:
    if not hmac.compare_digest(t or "", token_for(garage_id)):
        raise HTTPException(status_code=403, detail="This setup link is not valid.")


def _authorize(garage_id: str, request: Request, t: str) -> None:
    """Allow in with EITHER the private token OR a matching owner login cookie."""
    if t and hmac.compare_digest(t, token_for(garage_id)):
        return
    from . import owners  # local import avoids a circular import with owners.py
    if owners.session_garage(request) == garage_id:
        return
    raise HTTPException(status_code=403, detail="Please log in to edit this garage.")


def _load(garage_id: str, part: str) -> dict[str, Any]:
    path = GARAGES_DIR / garage_id / ("%s.yaml" % part)
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def _write(garage_id: str, part: str, data: dict[str, Any]) -> None:
    folder = GARAGES_DIR / garage_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("%s.yaml" % part)).write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


STYLE = """
*{box-sizing:border-box}
:root{--paper:#f4f7f5;--card:#fff;--ink:#16211e;--ink2:#4a5751;--ink3:#7f8b84;
 --line:#dde4df;--line2:#c6cfc9;--fill:#f1f6f2;--green:#0b6b4f;--green2:#0e8862;--mint:#e7f3ec;
 --amber:#8a6414;--amber-bg:#fbf1dc;
 --sans:"Assistant",-apple-system,"Segoe UI",sans-serif;--disp:"Archivo",sans-serif;
 --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
html{background:var(--paper)}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:16px;
 line-height:1.5;-webkit-font-smoothing:antialiased;padding:0 16px 90px}
.wrap{max-width:720px;margin:0 auto}
header{padding:26px 0 16px;border-bottom:2.5px solid var(--ink)}
.brand{font-family:var(--disp);font-weight:800;font-size:12px;letter-spacing:.18em;
 text-transform:uppercase;color:var(--green);margin:0 0 6px}
h1{font-family:var(--disp);font-weight:800;font-size:clamp(26px,5vw,36px);line-height:1.05;margin:0}
.lede{color:var(--ink2);margin:8px 0 0;font-size:15px}
h2{font-family:var(--disp);font-weight:700;font-size:13px;letter-spacing:.12em;text-transform:uppercase;
 color:var(--ink3);margin:30px 0 4px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.hint{color:var(--ink3);font-size:13.5px;margin:0 0 14px}
label{display:block;font-weight:600;font-size:13.5px;margin:0 0 4px}
input[type=text],input[type=tel],textarea,select{width:100%;font-family:var(--sans);font-size:15px;
 color:var(--ink);background:var(--card);border:1.4px solid var(--line2);border-radius:8px;padding:9px 11px}
input:focus,textarea:focus,select:focus{outline:2px solid var(--green2);outline-offset:1px;border-color:var(--green2)}
textarea{min-height:64px;resize:vertical}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:560px){.grid2{grid-template-columns:1fr}}
.field{margin:0 0 14px}
.svc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:0 0 12px}
.svc .top{display:flex;gap:10px;align-items:center;margin:0 0 10px}
.svc .top input{font-weight:600}
.prices{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.prices .p label{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink3)}
.prices input{font-family:var(--mono);text-align:center}
.mono-note{margin-top:10px}
.mono-note input{font-size:13.5px}
.rm{border:0;background:none;color:var(--ink3);font-size:20px;line-height:1;cursor:pointer;padding:4px 6px}
.rm:hover{color:#b23b2e}
.add{background:var(--mint);color:var(--green);border:1px dashed var(--green2);border-radius:9px;
 padding:10px 14px;font-family:var(--sans);font-weight:600;font-size:14px;cursor:pointer;width:100%}
.add:hover{background:#dbeee2}
.note{background:var(--mint);border-left:3px solid var(--green);border-radius:0 6px 6px 0;
 padding:11px 14px;margin:16px 0;font-size:13.5px;color:var(--ink2)}
.note b{color:var(--green)}
.hours{display:grid;grid-template-columns:120px 1fr 1fr auto;gap:8px 10px;align-items:center}
@media(max-width:560px){.hours{grid-template-columns:80px 1fr 1fr auto}}
.hours .d{font-weight:600;font-size:14px}
.hours input{font-family:var(--mono);text-align:center;padding:7px}
.hours .closed{font-size:13px;color:var(--ink3);display:flex;align-items:center;gap:6px}
.bar{position:sticky;bottom:0;background:linear-gradient(transparent,var(--paper) 24%);
 padding:20px 0 8px;margin-top:24px}
.save{width:100%;background:var(--green);color:#fff;border:0;border-radius:11px;padding:15px;
 font-family:var(--disp);font-weight:700;font-size:16px;letter-spacing:.02em;cursor:pointer}
.save:hover{background:var(--green2)}
.done{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:28px;text-align:center;margin-top:40px}
.done h1{color:var(--green);margin-bottom:8px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0}
@media(max-width:560px){.stats{grid-template-columns:1fr}}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.stat .sn{font-family:var(--disp);font-weight:800;font-size:24px;letter-spacing:-.02em;color:var(--ink)}
.stat .sl{color:var(--ink3);font-size:13px;margin-top:3px}
.pill{display:inline-block;font-size:12px;font-weight:700;padding:3px 11px;border-radius:999px;vertical-align:middle}
.pill.amber{background:var(--amber-bg);color:var(--amber)}
.pill.live{background:var(--mint);color:var(--green)}
.backlink{display:inline-block;margin:14px 0 0;color:var(--ink3);text-decoration:none;font-size:14px;font-weight:600}
.backlink:hover{color:var(--green)}
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?"
        "family=Archivo:wght@700;800&family=Assistant:wght@400;600&family=IBM+Plex+Mono&display=swap'>"
        "<title>%s</title><style>%s</style></head><body><div class='wrap'>%s</div></body></html>"
        % (_esc(title), STYLE, body)
    )


def _service_row(sid: str, name: str, prices: dict, note: str) -> str:
    p = lambda c: _esc((prices or {}).get(c, "") if str((prices or {}).get(c, "")).lower() not in
                       ("", "todo", "none", "null") else "")
    return f"""
    <div class="svc">
      <div class="top">
        <input type="text" name="svc_name" value="{_esc(name)}" placeholder="Service name" required>
        <input type="hidden" name="svc_id" value="{_esc(sid)}">
        <button type="button" class="rm" onclick="this.closest('.svc').remove()" title="Remove">×</button>
      </div>
      <div class="prices">
        <div class="p"><label>Sedan</label><input type="text" name="price_sedan" value="{p('sedan')}" placeholder="AED"></div>
        <div class="p"><label>SUV</label><input type="text" name="price_suv" value="{p('suv')}" placeholder="AED"></div>
        <div class="p"><label>Luxury</label><input type="text" name="price_luxury" value="{p('luxury')}" placeholder="AED"></div>
      </div>
      <div class="mono-note"><input type="text" name="svc_note" value="{_esc(note)}" placeholder="Note (optional) — e.g. includes filter, per axle"></div>
    </div>"""


@router.get("/{garage_id}", response_class=HTMLResponse)
def form(garage_id: str, request: Request, t: str = "") -> HTMLResponse:
    _authorize(garage_id, request, t)
    info = _load(garage_id, "info")
    prices = _load(garage_id, "prices")
    faq = _load(garage_id, "faq")

    services = prices.get("services") or []
    rows = "".join(
        _service_row(
            s.get("id", ""),
            (s.get("name") or {}).get("en", "") if isinstance(s.get("name"), dict) else s.get("name", ""),
            s.get("prices") or {},
            s.get("notes") or "",
        )
        for s in services
    ) or _service_row("", "", {}, "")

    hours = info.get("hours") or {}
    hours_rows = ""
    for key, label in DAYS:
        win = hours.get(key)
        opens = win[0] if isinstance(win, list) and len(win) == 2 else ""
        closes = win[1] if isinstance(win, list) and len(win) == 2 else ""
        closed = "checked" if (key in hours and not win) else ""
        hours_rows += f"""
        <div class="d">{label}</div>
        <input type="text" name="open_{key}" value="{_esc(opens)}" placeholder="08:00">
        <input type="text" name="close_{key}" value="{_esc(closes)}" placeholder="19:00">
        <label class="closed"><input type="checkbox" name="closed_{key}" {closed}> closed</label>"""

    faq_rows = ""
    for entry in (faq.get("faqs") or []):
        q = ", ".join(entry.get("q", [])) if isinstance(entry.get("q"), list) else entry.get("q", "")
        a = (entry.get("a") or {}).get("en", "") if isinstance(entry.get("a"), dict) else entry.get("a", "")
        if q and a:
            faq_rows += _faq_row(q, a)
    faq_rows = faq_rows or _faq_row("", "")

    pay = info.get("payment_methods") or []
    body = f"""
    <header>
      <p class="brand">Mistri · setup</p>
      <h1>{_esc(info.get('name') or garage_id.title())}</h1>
      <p class="lede">Fill in your prices and details. This is what the WhatsApp
      assistant will tell your customers — so it only ever says what you enter here.</p>
      <a class="backlink" href="/onboard/{_esc(garage_id)}/home?t={_esc(t)}">&larr; My garage page</a>
    </header>

    <form method="post" action="/onboard/{_esc(garage_id)}?t={_esc(t)}">

      <div class="note"><b>Leave a price blank</b> if it depends on the car — the assistant
      will offer a free inspection instead of guessing. It never makes a price up.</div>

      <h2>Your services & prices (AED)</h2>
      <p class="hint">One row per service. Fill the car types you price differently; a range like
      “400-600” is fine.</p>
      <div id="services">{rows}</div>
      <button type="button" class="add" onclick="addService()">+ Add another service</button>

      <h2>Opening hours</h2>
      <p class="hint">Leave a day's times empty and tick “closed” if you don't open.</p>
      <div class="hours">{hours_rows}</div>

      <h2>Your details</h2>
      <div class="grid2">
        <div class="field"><label>Your personal WhatsApp (for alerts)</label>
          <input type="tel" name="owner_alert_number" value="{_esc(info.get('owner_alert_number') if 'X' not in str(info.get('owner_alert_number','')) else '')}" placeholder="9715XXXXXXXX"></div>
        <div class="field"><label>Google Maps link</label>
          <input type="text" name="maps_link" value="{_esc(info.get('maps_link') if str(info.get('maps_link','')).startswith('http') else '')}" placeholder="https://maps.app.goo.gl/..."></div>
        <div class="field"><label>Address</label>
          <input type="text" name="address" value="{_esc(info.get('address') if 'TODO' not in str(info.get('address','')) else '')}"></div>
        <div class="field"><label>Cars you can start per hour</label>
          <input type="text" name="max_cars_per_hour" value="{_esc(info.get('max_cars_per_hour',''))}" placeholder="2"></div>
        <div class="field"><label>Warranty</label>
          <input type="text" name="warranty" value="{_esc(info.get('warranty') if 'TODO' not in str(info.get('warranty','')) else '')}" placeholder="6 months / 10,000 km"></div>
        <div class="field"><label>Payment accepted</label>
          <input type="text" name="payment_methods" value="{_esc(', '.join(pay))}" placeholder="cash, card, transfer"></div>
      </div>
      <div class="field"><label>Do you collect the car? (leave blank if not)</label>
        <input type="text" name="pickup_notes" value="{_esc(info.get('pickup_notes') if 'TODO' not in str(info.get('pickup_notes','')) else '')}" placeholder="Free within 15 km"></div>

      <div class="field"><label>What you do NOT service (leave blank if none)</label>
        <textarea name="restrictions" placeholder="e.g. GCC-spec vehicles only — we don't service US or import-spec cars. No accident / bodywork.">{_esc(info.get('restrictions') if 'TODO' not in str(info.get('restrictions','')) else '')}</textarea>
        <p class="hint">The assistant tells customers this early, so nobody is turned away after waiting.</p></div>

      <h2>Common questions</h2>
      <p class="hint">Questions customers ask a lot, and your answer. The assistant will use these
      word-for-word.</p>
      <div id="faqs">{faq_rows}</div>
      <button type="button" class="add" onclick="addFaq()">+ Add another question</button>

      <div class="bar"><button type="submit" class="save">Save — this goes live on WhatsApp</button></div>
    </form>

    <template id="svc-tpl">{_service_row("", "", {}, "")}</template>
    <template id="faq-tpl">{_faq_row("", "")}</template>
    <script>
      function addService(){{const t=document.getElementById('svc-tpl').content.cloneNode(true);
        document.getElementById('services').appendChild(t);}}
      function addFaq(){{const t=document.getElementById('faq-tpl').content.cloneNode(true);
        document.getElementById('faqs').appendChild(t);}}
    </script>"""
    return _page("Set up " + (info.get("name") or garage_id), body)


def _faq_row(q: str, a: str) -> str:
    return f"""
    <div class="svc">
      <div class="top">
        <input type="text" name="faq_q" value="{_esc(q)}" placeholder="e.g. do you take card?">
        <button type="button" class="rm" onclick="this.closest('.svc').remove()" title="Remove">×</button>
      </div>
      <textarea name="faq_a" placeholder="Your answer">{_esc(a)}</textarea>
    </div>"""


def _clean(v: str) -> str:
    return (v or "").strip()


@router.post("/{garage_id}")
async def save(garage_id: str, request: Request, background: BackgroundTasks,
               t: str = "") -> RedirectResponse:
    _authorize(garage_id, request, t)
    form = await request.form()

    info = _load(garage_id, "info")
    prices = _load(garage_id, "prices")

    # ---- services: rebuild from the posted rows, preserving multilingual names by id ----
    old_by_id = {s.get("id"): s for s in (prices.get("services") or [])}
    names = form.getlist("svc_name")
    ids = form.getlist("svc_id")
    ps, pu, pl = form.getlist("price_sedan"), form.getlist("price_suv"), form.getlist("price_luxury")
    notes = form.getlist("svc_note")
    services = []
    used = set()
    for i, name in enumerate(names):
        name = _clean(name)
        if not name:
            continue
        sid = _clean(ids[i]) if i < len(ids) and _clean(ids[i]) else _slug(name, used)
        used.add(sid)
        old = old_by_id.get(sid, {})
        name_field = old.get("name") if isinstance(old.get("name"), dict) else {}
        name_field = dict(name_field or {})
        name_field["en"] = name
        svc = {"id": sid, "name": name_field}
        price = {}
        for cat, lst in (("sedan", ps), ("suv", pu), ("luxury", pl)):
            val = _clean(lst[i]) if i < len(lst) else ""
            if val:
                price[cat] = val
        svc["prices"] = price
        note = _clean(notes[i]) if i < len(notes) else ""
        if note:
            svc["notes"] = note
        services.append(svc)

    prices.setdefault("currency", "AED")
    prices["services"] = services
    _write(garage_id, "prices", prices)

    # ---- info fields ----
    info["id"] = garage_id
    for key in ("name",):
        info.setdefault(key, garage_id.title())
    for key in ("owner_alert_number", "maps_link", "address", "warranty", "pickup_notes"):
        v = _clean(form.get(key, ""))
        if v:
            info[key] = v
    mc = _clean(form.get("max_cars_per_hour", ""))
    if mc.isdigit():
        info["max_cars_per_hour"] = int(mc)
    pay = [p.strip() for p in _clean(form.get("payment_methods", "")).split(",") if p.strip()]
    if pay:
        info["payment_methods"] = pay
    info["pickup_available"] = bool(_clean(form.get("pickup_notes", "")))
    # Scope limits: settable AND clearable — blank means "no restriction", so we
    # drop the key rather than leaving a stale line the bot would keep telling people.
    restrictions = _clean(form.get("restrictions", ""))
    if restrictions:
        info["restrictions"] = restrictions
    else:
        info.pop("restrictions", None)

    hours = {}
    for key, _label in DAYS:
        if form.get("closed_" + key):
            hours[key] = None
            continue
        o, c = _clean(form.get("open_" + key, "")), _clean(form.get("close_" + key, ""))
        hours[key] = [o, c] if o and c else None
    info["hours"] = hours
    _write(garage_id, "info", info)

    # ---- FAQ ----
    fq, fa = form.getlist("faq_q"), form.getlist("faq_a")
    faqs = []
    for i, q in enumerate(fq):
        q = _clean(q)
        a = _clean(fa[i]) if i < len(fa) else ""
        if q and a:
            faqs.append({"q": [s.strip() for s in q.split(",") if s.strip()], "a": {"en": a}})
    _write(garage_id, "faq", {"faqs": faqs})

    garages._cache.pop(garage_id, None)  # force a reload on the next message

    # If this save completed their setup, send the one-time "all set" welcome.
    from . import nudges  # local import avoids a circular import
    background.add_task(nudges.maybe_welcome, garage_id)

    return RedirectResponse(url="/onboard/%s/home?t=%s&saved=1" % (garage_id, t), status_code=303)


def _slug(name: str, used: set) -> str:
    base = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")[:40] or "service"
    sid, n = base, 2
    while sid in used:
        sid, n = "%s_%d" % (base, n), n + 1
    return sid


def _price_counts(prices: dict) -> tuple[int, int]:
    filled = total = 0
    for s in (prices.get("services") or []):
        for v in ((s or {}).get("prices") or {}).values():
            total += 1
            if v and str(v).strip().lower() not in ("todo", "none", "null"):
                filled += 1
    return filled, total


@router.get("/{garage_id}/home", response_class=HTMLResponse)
def home(garage_id: str, request: Request, t: str = "", saved: str = "") -> HTMLResponse:
    """The owner's own page: their garage at a glance, and the button back into
    editing. This is where a save lands, and where an owner login lands."""
    _authorize(garage_id, request, t)
    info = _load(garage_id, "info")
    prices = _load(garage_id, "prices")
    services = prices.get("services") or []
    filled, total = _price_counts(prices)
    pending = bool(info.get("pending"))
    edit_url = "/onboard/%s?t=%s" % (_esc(garage_id), _esc(t))

    saved_banner = ('<div class="note" style="background:#e7f3ec;border-color:var(--green)">'
                    '<b>Saved.</b> Your prices are updated — the assistant uses them from the next '
                    'message.</div>') if saved else ""

    status = ('<span class="pill amber">Setting up</span>' if pending
              else '<span class="pill live">Live on WhatsApp</span>')
    status_note = ("We'll connect your WhatsApp number and switch it on — we'll message you. "
                   "Everything you enter is saved and ready." if pending else
                   "Your assistant is answering your customers now.")

    def stat(n, label):
        return ("<div class='stat'><div class='sn'>%s</div><div class='sl'>%s</div></div>" % (n, label))

    body = f"""
    <header>
      <p class="brand">Mistri · your garage</p>
      <h1>{_esc(info.get('name') or garage_id)} &nbsp;{status}</h1>
      <p class="lede">{status_note}</p>
    </header>
    {saved_banner}

    <div class="stats">
      {stat("%d/%d" % (filled, total) if total else "0", "prices filled in")}
      {stat(str(len(services)), "services listed")}
      {stat("+"+_esc(info.get("owner_alert_number")) if info.get("owner_alert_number") and "X" not in str(info.get("owner_alert_number","")) else "—", "your alerts number")}
    </div>

    <div class="bar" style="position:static">
      <a class="save" style="display:block;text-decoration:none;text-align:center" href="{edit_url}">
        Edit my prices &amp; details</a>
    </div>
    <p class="hint" style="text-align:center;margin-top:12px">Come back anytime — log in at
    <b>mistri.offpageos.com/login</b> with your WhatsApp number and password.
    &nbsp;·&nbsp; <a class="backlink" style="margin:0" href="/logout">Log out</a></p>"""
    return _page(info.get("name") or garage_id, body)


@router.get("/{garage_id}/done", response_class=HTMLResponse)
def done(garage_id: str, t: str = "") -> RedirectResponse:
    # Old link → the owner's home page.
    return RedirectResponse(url="/onboard/%s/home?t=%s" % (garage_id, t), status_code=307)
