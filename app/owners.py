"""Garage-owner accounts and login.

Separate from the operator admin: an owner logs in with their WhatsApp number
and a password they set at signup, and reaches only their own garage's page.
The session cookie carries just the garage id (signed), so an owner can never
see another garage or the operator console.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from . import commands, onboard
from .config import settings
from .db import Owner, SessionLocal

router = APIRouter(tags=["owner"])

OWNER_COOKIE = "mistri_owner"
_PBKDF_ROUNDS = 100_000


# --- passwords --------------------------------------------------------------

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", (pw or "").encode(), salt, _PBKDF_ROUNDS)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_b64, dk_b64 = (stored or "").split("$", 1)
        salt, dk = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        test = hashlib.pbkdf2_hmac("sha256", (pw or "").encode(), salt, _PBKDF_ROUNDS)
        return hmac.compare_digest(test, dk)
    except Exception:
        return False


# --- session cookie ---------------------------------------------------------

def _sign(garage_id: str) -> str:
    key = (settings.admin_password or "mistri").encode()
    sig = hmac.new(key, ("owner:" + garage_id).encode(), hashlib.sha256).hexdigest()[:24]
    return "%s.%s" % (garage_id, sig)


def session_garage(request: Request) -> str | None:
    """The garage id this browser is logged in as, or None."""
    raw = request.cookies.get(OWNER_COOKIE, "")
    gid, _, _sig = raw.rpartition(".")
    if gid and hmac.compare_digest(raw, _sign(gid)):
        return gid
    return None


def _set_cookie(resp: Response, garage_id: str) -> None:
    resp.set_cookie(OWNER_COOKIE, _sign(garage_id), httponly=True, samesite="lax",
                    secure=True, max_age=60 * 60 * 24 * 30, path="/")


def log_in(resp: Response, garage_id: str) -> None:
    """Used by signup too, so a new owner is logged in straight away."""
    _set_cookie(resp, garage_id)


# --- accounts ---------------------------------------------------------------

def create_account(garage_id: str, number: str, password: str) -> None:
    with SessionLocal() as db:
        db.add(Owner(garage_id=garage_id, number=number, password_hash=hash_password(password)))
        db.commit()


def number_taken(number: str) -> bool:
    with SessionLocal() as db:
        return db.query(Owner).filter_by(number=number).first() is not None


def authenticate(number: str, password: str) -> str | None:
    """Return the garage id if the number+password match, else None."""
    with SessionLocal() as db:
        row = db.query(Owner).filter_by(number=number).first()
    if row and verify_password(password, row.password_hash):
        return row.garage_id
    return None


# --- pages ------------------------------------------------------------------

_STYLE = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;
 background:#f4f8f5;font-family:"Assistant",-apple-system,"Segoe UI",sans-serif;color:#0f1a16;padding:24px}
.box{width:min(420px,94vw);background:#fff;border:1px solid #e3eae5;border-radius:20px;padding:34px;
 box-shadow:0 8px 24px rgba(16,40,30,.06)}
.ey{font-family:"Archivo",sans-serif;font-weight:700;font-size:12px;letter-spacing:.14em;
 text-transform:uppercase;color:#0b6b4f;margin:0 0 8px}
h1{font-family:"Archivo",sans-serif;font-size:26px;margin:0 0 6px;letter-spacing:-.02em}
p.s{color:#48554f;font-size:15px;margin:0 0 20px}
label{display:block;font-size:13px;font-weight:600;margin:14px 0 5px}
input{width:100%;padding:11px 13px;border:1.4px solid #d3ddd7;border-radius:10px;font-size:15px;font-family:inherit}
input:focus{outline:2px solid #0e8862;border-color:#0e8862}
button{width:100%;margin-top:22px;background:#0b6b4f;color:#fff;border:0;border-radius:11px;padding:14px;
 font-size:16px;font-weight:700;font-family:"Archivo",sans-serif;cursor:pointer}
button:hover{background:#0e8862}
.err{color:#b23b3b;font-size:14px;margin:0 0 12px}
.foot{color:#7d8a83;font-size:13.5px;margin-top:18px;text-align:center}
.foot a{color:#0b6b4f;font-weight:600}
"""


def _login_page(error: str = "", number: str = "") -> HTMLResponse:
    err = ("<p class='err'>%s</p>" % html.escape(error)) if error else ""
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?"
        "family=Archivo:wght@700;800&family=Assistant:wght@400;600;700&display=swap'>"
        "<title>Owner login · Mistri</title><style>%s</style></head><body>"
        "<form class='box' method='post' action='/login'>"
        "<p class='ey'>Mistri</p><h1>Owner login</h1>"
        "<p class='s'>Sign in to update your garage's prices and details.</p>%s"
        "<label>Your WhatsApp number</label>"
        "<input name='number' value='%s' inputmode='tel' autofocus placeholder='05X XXX XXXX'>"
        "<label>Password</label>"
        "<input name='password' type='password' placeholder='Your password'>"
        "<button type='submit'>Log in</button>"
        "<p class='foot'>New here? <a href='/start'>Set up your garage</a></p>"
        "</form></body></html>"
        % (_STYLE, err, html.escape(number))
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    gid = session_garage(request)
    if gid:
        return RedirectResponse(url="/owner", status_code=307)
    return _login_page()


@router.post("/login")
def login_submit(number: str = Form(""), password: str = Form("")) -> Response:
    num = commands.normalise(number) or ""
    gid = authenticate(num, password) if num else None
    if not gid:
        return _login_page("Wrong number or password.", number)
    resp = RedirectResponse(url="/owner", status_code=303)
    _set_cookie(resp, gid)
    return resp


@router.get("/owner")
def owner_home(request: Request) -> Response:
    """Send a logged-in owner to their garage page; otherwise to login."""
    gid = session_garage(request)
    if not gid:
        return RedirectResponse(url="/login", status_code=307)
    return RedirectResponse(url="/onboard/%s/home?t=%s" % (gid, onboard.token_for(gid)),
                            status_code=307)


@router.get("/logout")
def logout() -> Response:
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(OWNER_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    resp.set_cookie(OWNER_COOKIE, "", max_age=0, expires=0, path="/",
                    secure=True, httponly=True, samesite="lax")
    return resp
