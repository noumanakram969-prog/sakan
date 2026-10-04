"""The ONLY module that talks to WhatsApp.

Nothing else in this repo may import httpx for WhatsApp traffic. Swapping Meta direct
for a BSP (360dialog) is a base-URL + auth-header change, and it lives here.

Both providers speak the Cloud API message format, so the payload builders are shared.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import settings

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- inbound

IGNORED_TYPES = {"system", "reaction", "unsupported", "ephemeral", "order"}


@dataclass
class InboundMessage:
    """One message lifted out of a webhook payload.

    `sender` is "customer" for messages to the business, and "owner" for messages the
    owner sent from his own phone — coexistence echoes those back to us, and they are
    what pauses the bot in a conversation.
    """
    phone_number_id: str
    wa_message_id: str
    from_number: str          # the customer's number, either direction
    sender: str               # customer | owner
    body: str
    msg_type: str = "text"
    timestamp: int | None = None
    profile_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def parse_webhook(payload: dict[str, Any]) -> list[InboundMessage]:
    """Flatten a Cloud API webhook into messages we care about.

    Ignores: statuses (delivered/read), groups, and anything without a body we can read.
    Non-text types come through with msg_type set so the caller can reply
    "please send that as text" rather than guessing.
    """
    out: list[InboundMessage] = []

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            metadata = value.get("metadata", {}) or {}
            phone_number_id = metadata.get("phone_number_id", "")

            names = {
                c.get("wa_id"): (c.get("profile", {}) or {}).get("name")
                for c in (value.get("contacts", []) or [])
            }

            for msg in value.get("messages", []) or []:
                # groups never reach the API in coexistence, but be explicit about it
                if msg.get("group_id") or (msg.get("context", {}) or {}).get("group_id"):
                    continue

                # Not somebody asking a question: number-change notices, thumbs
                # up on an old message, unsupported payloads. Answering these
                # would send the owner an alert about nothing.
                if msg.get("type") in IGNORED_TYPES:
                    continue

                from_number = msg.get("from", "")
                # Coexistence echo: the owner's own outbound messages arrive with
                # from == the business number. Everything else is the customer.
                #
                # Compared on digits only. Meta returns display_phone_number
                # formatted for humans - "+971 4 123 4567" - while `from` is bare
                # digits, so anything less than this silently classifies every one
                # of the owner's replies as a customer message and the bot talks
                # over him. That is the one behaviour the whole handoff design
                # rests on, and the owner notices within the hour.
                business = _digits(metadata.get("display_phone_number"))
                is_owner_echo = bool(business) and _digits(from_number) == business
                recipient = msg.get("to") or from_number

                out.append(
                    InboundMessage(
                        phone_number_id=phone_number_id,
                        wa_message_id=msg.get("id", ""),
                        from_number=(recipient if is_owner_echo else from_number),
                        sender="owner" if is_owner_echo else "customer",
                        body=_extract_body(msg),
                        msg_type=msg.get("type", "text"),
                        timestamp=int(msg["timestamp"]) if msg.get("timestamp") else None,
                        profile_name=names.get(from_number),
                        raw=msg,
                    )
                )

    return out


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _extract_body(msg: dict[str, Any]) -> str:
    t = msg.get("type")
    if t == "text":
        return (msg.get("text", {}) or {}).get("body", "")
    if t == "button":
        return (msg.get("button", {}) or {}).get("text", "")
    if t == "interactive":
        inter = msg.get("interactive", {}) or {}
        for key in ("button_reply", "list_reply"):
            if key in inter:
                return (inter[key] or {}).get("title", "")
        return ""
    # image / audio / document / location — no text to read
    return (msg.get(t, {}) or {}).get("caption", "") if isinstance(msg.get(t), dict) else ""


def verify_signature(raw_body: bytes, header: str | None, token: str | None = None) -> bool:
    """Is this webhook really from our provider?

    Meta signs every request, so that is checked properly. A BSP does not sign
    anything, and an unauthenticated webhook is not a small problem here: anyone
    who finds the URL could post invented customer messages, which cost model
    calls and, worse, cause the garage's own number to send WhatsApp messages to
    whatever number they name. So on a BSP a shared secret is required, and a
    missing secret fails closed rather than open.
    """
    if settings.wa_provider != "meta":
        if not settings.webhook_token:
            log.error("WA_PROVIDER=%s needs WEBHOOK_TOKEN set; refusing every webhook",
                      settings.wa_provider)
            return False
        return bool(token) and hmac.compare_digest(token, settings.webhook_token)

    if not settings.meta_app_secret:
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.meta_app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


# --------------------------------------------------------------------------- outbound

def _endpoint_and_headers() -> tuple[str, dict[str, str]]:
    if settings.wa_provider == "d360":
        return (
            "https://waba-v2.360dialog.io/messages",
            {"D360-API-KEY": settings.d360_api_key, "Content-Type": "application/json"},
        )
    return (
        f"https://graph.facebook.com/{settings.meta_graph_version}"
        f"/{settings.meta_phone_number_id}/messages",
        {
            "Authorization": f"Bearer {settings.meta_access_token}",
            "Content-Type": "application/json",
        },
    )


SEND_ATTEMPTS = 3
RETRY_AFTER_SECONDS = 1.0

# Rate limits and upstream wobbles. A 4xx that is not 429 is our mistake and
# will fail again identically, so it is not retried.
_RETRYABLE = {429, 500, 502, 503, 504}


async def _post(payload: dict[str, Any]) -> dict[str, Any]:
    """Send, retrying the failures that are worth retrying.

    A customer who gets no reply because of one 503 is a customer the garage
    lost to a blip.
    """
    url, headers = _endpoint_and_headers()
    last = ""

    async with httpx.AsyncClient(timeout=20) as client:
        for attempt in range(1, SEND_ATTEMPTS + 1):
            try:
                resp = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last = str(exc)
            else:
                if resp.status_code < 400:
                    return resp.json()
                last = "%s %s" % (resp.status_code, resp.text)
                if resp.status_code not in _RETRYABLE:
                    break

            if attempt < SEND_ATTEMPTS:
                log.warning("send attempt %d failed (%s), retrying", attempt, last[:120])
                await asyncio.sleep(RETRY_AFTER_SECONDS * attempt)

    raise WhatsAppError(last)


class WhatsAppError(RuntimeError):
    pass


async def send_text(to: str, body: str) -> dict[str, Any]:
    return await _post(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": True, "body": body},
        }
    )


async def send_buttons(to: str, body: str, buttons: list[dict[str, str]]) -> dict[str, Any]:
    """Up to 3 tappable reply buttons. Session-window only (a reply to the customer).

    Button titles are built by CODE from real data (slot times, fixed labels),
    never by the model, so the price/time guarantees are unaffected. WhatsApp
    caps titles at 20 chars and ids at 256; we trim rather than let a send fail.
    """
    reply_buttons = [
        {"type": "reply", "reply": {"id": b["id"][:256], "title": b["title"][:20]}}
        for b in buttons[:3]
    ]
    return await _post(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": reply_buttons},
            },
        }
    )


async def send_list(to: str, body: str, button: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    """A tap-to-choose list (up to 10 rows). Session-window only.

    Same rule: rows come from code, not the model. Title <=24, description <=72.
    """
    return await _post(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body[:1024]},
                "action": {
                    "button": button[:20],
                    "sections": [{
                        "rows": [
                            {"id": r["id"][:200], "title": r["title"][:24],
                             "description": r.get("description", "")[:72]}
                            for r in rows[:10]
                        ],
                    }],
                },
            },
        }
    )


async def check_token() -> tuple[bool, str]:
    """A cheap read against Graph to tell if the access token still works.

    Returns (ok, detail). A 401/code-190 is the token having expired, which is
    the failure that silently stops every outbound message. Never raises."""
    if settings.wa_provider != "meta":
        return True, settings.wa_provider
    url = (f"https://graph.facebook.com/{settings.meta_graph_version}"
           f"/{settings.meta_phone_number_id}?fields=verified_name")
    headers = {"Authorization": f"Bearer {settings.meta_access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return False, "can't reach WhatsApp (%s)" % exc.__class__.__name__
    if resp.status_code == 200:
        return True, "connected"
    if resp.status_code in (401, 403):
        return False, "access token expired or invalid"
    return False, "WhatsApp error %d" % resp.status_code


async def send_template(
    to: str, name: str, language: str, variables: list[str] | None = None
) -> dict[str, Any]:
    """Templates are the only way to message outside the 24-hour window (reminders)."""
    components = []
    if variables:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": v} for v in variables],
            }
        )
    return await _post(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": language},
                "components": components,
            },
        }
    )
