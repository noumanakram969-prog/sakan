"""Turning internal reasons into something a garage owner can read.

Handoff reasons are written for whoever is debugging: "off sheet: no price on
the sheet for brake_repair / suv" is exactly what you want in a log. It is not
what the owner should get on his phone at nine at night, where it reads as
something being broken.

The internal string is kept as it is in the database, because that is what the
log and the report need. This is only what gets shown to a person.
"""
from __future__ import annotations

# Longest, most specific prefixes first — "booking off sheet" before "off sheet".
_PLAIN = (
    ("booking off sheet", "Wants to book something that is not on your price list"),
    ("off sheet", "Asked the price of something not on your price list"),
    ("low confidence", "I could not tell which service or which car they meant"),
    ("blocked", "My reply did not look right, so I stopped it and called you instead"),
    ("cannot read a photo", "Sent a photo"),
    ("cannot read a voice note", "Sent a voice note"),
    ("cannot read a video", "Sent a video"),
    ("cannot read a document", "Sent a document"),
    ("cannot read a location", "Sent a location"),
    ("cannot read", "Sent something I cannot read"),
    ("info topic not in the garage files", "Asked something that is not in your details"),
    ("no slots available", "Wanted to book, but nothing is free in the next two weeks"),
    ("reply cap reached", "Too many messages in one day from this number"),
    ("owner asked", "You took this chat yourself"),
    ("classifier unavailable", "Something went wrong on my side"),
    ("composer unavailable", "Something went wrong on my side"),
    ("engine error", "Something went wrong on my side"),
    ("no conversation context", "Something went wrong on my side"),
    ("intent not handled", "Asked something I do not handle yet"),
)

FALLBACK = "I was not sure how to answer"


def plain_reason(reason: str | None) -> str:
    """What a person should read. Never the raw internal string."""
    text = (reason or "").strip().lower()
    for prefix, plain in _PLAIN:
        if text.startswith(prefix):
            return plain
    return FALLBACK
