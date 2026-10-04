"""Garage knowledge: one folder per garage, loaded from YAML.

No vector DB. The sheet is small enough to sit in the system prompt.
Files are cached and reloaded when their mtime changes, so the owner's price sheet
can be edited on the server without a restart.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

GARAGES_DIR = Path(__file__).resolve().parent.parent / "garages"

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class GarageNotFound(KeyError):
    pass


def _mtime(folder: Path) -> float:
    return max((p.stat().st_mtime for p in folder.glob("*.yaml")), default=0.0)


_SAFE_ID = re.compile(r"^[a-z0-9_-]+$")


def load(garage_id: str) -> dict[str, Any]:
    # A garage id names a directory. Nothing currently passes user input here,
    # but "nothing currently" is a poor reason to be able to walk the filesystem.
    if not garage_id or not _SAFE_ID.match(str(garage_id)):
        raise GarageNotFound(garage_id)

    folder = GARAGES_DIR / garage_id
    if not folder.is_dir():
        raise GarageNotFound(garage_id)

    stamp = _mtime(folder)
    cached = _cache.get(garage_id)
    if cached and cached[0] == stamp:
        return cached[1]

    data: dict[str, Any] = {"id": garage_id}
    for part in ("info", "prices", "faq"):
        path = folder / f"{part}.yaml"
        data[part] = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}

    _cache[garage_id] = (stamp, data)
    return data


def all_ids() -> list[str]:
    return sorted(p.name for p in GARAGES_DIR.iterdir() if p.is_dir())


def routable_ids() -> list[str]:
    """Garages a real WhatsApp number may be routed to.

    Excludes any folder whose info.yaml says `demo: true`. The demo garage
    exists for `chat`, `grade` and sales demos; a live message must never be
    answered from an invented price sheet.

    Also excludes `pending: true` — a garage that signed up on the website but
    whose WhatsApp number the operator has not connected yet. It is inert until
    activated: no routing, no scheduled messages. This matters because routing
    falls back to the single live garage, so a half-set-up signup must not count.
    """
    out = []
    for gid in all_ids():
        try:
            info = load(gid).get("info") or {}
        except GarageNotFound:
            continue
        if not info.get("demo") and not info.get("pending"):
            out.append(gid)
    return out


def id_for_phone_number_id(phone_number_id: str) -> str | None:
    """Which garage owns this WhatsApp number?

    Matched against wa_phone_number_id in each garage's info.yaml. With exactly
    one real garage configured we fall back to it, so the Meta test number works
    before any number has been connected.
    """
    ids = routable_ids()
    for gid in ids:
        info = load(gid).get("info") or {}
        if phone_number_id and str(info.get("wa_phone_number_id") or "") == str(phone_number_id):
            return gid
    return ids[0] if len(ids) == 1 else None
