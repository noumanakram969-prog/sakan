"""Inventory retrieval. Never generation.

The property equivalent of a garage price sheet, and it carries the same
guarantee: a price reaches a customer because it was read out of this file, or
it does not reach them at all.

The stakes are higher here than for an oil change. A model that cheerfully
answers "around 1.2 million" for a JVC two-bedroom has invented a number a buyer
will repeat to their bank, and the brokerage will be the one explaining it. So
the lookup returns facts or it returns nothing, and `NeedMore` is a normal
answer rather than a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

AGENCIES = Path("agencies")

# How people actually type bedroom counts on WhatsApp.
BED_ALIASES = {
    "studio": ["studio", "std", "استوديو", "ستوديو"],
    "1bed": ["1bed", "1 bed", "1bhk", "1 bhk", "1br", "1 br", "one bed", "1-bed",
             "غرفة", "غرفه", "1 bedroom"],
    "2bed": ["2bed", "2 bed", "2bhk", "2 bhk", "2br", "2 br", "two bed", "2-bed",
             "غرفتين", "2 bedroom"],
    "3bed": ["3bed", "3 bed", "3bhk", "3 bhk", "3br", "3 br", "three bed", "3-bed",
             "3 bedroom"],
    "4bed": ["4bed", "4 bed", "4bhk", "4 bhk", "4br", "4 br", "four bed", "4-bed",
             "4 bedroom"],
}

BED_LABEL = {
    "studio": "studio", "1bed": "1 bedroom", "2bed": "2 bedroom",
    "3bed": "3 bedroom", "4bed": "4 bedroom",
}


class NeedMore(Exception):
    """Not enough to answer. Carries what is missing, so the caller can ask for
    exactly one thing rather than a form."""

    def __init__(self, missing: str, *, options: list[str] | None = None) -> None:
        self.missing = missing
        self.options = options or []
        super().__init__(f"need {missing}")


@dataclass(frozen=True)
class Quote:
    project: str
    area: str
    developer: str
    unit: str
    price_from: str
    size_sqft: str
    status: str
    handover: str
    payment_plan: str = ""
    service_charge_psf: str = ""
    dld_project_number: str = ""

    def as_facts(self) -> dict[str, Any]:
        """What the composer is allowed to see. Nothing else exists to it."""
        f = {
            "project": self.project,
            "area": self.area,
            "developer": self.developer,
            "unit_type": BED_LABEL.get(self.unit, self.unit),
            "starting_price_aed": self.price_from,
            "size_sqft": self.size_sqft,
            "status": "off-plan" if self.status == "off_plan" else "ready",
            "handover": self.handover,
        }
        if self.payment_plan:
            f["payment_plan"] = self.payment_plan
        if self.service_charge_psf:
            f["service_charge_per_sqft"] = self.service_charge_psf
        if self.dld_project_number:
            f["dld_project_number"] = self.dld_project_number
        return f


@dataclass
class Agency:
    id: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def currency(self) -> str:
        return self.data.get("currency", "AED")

    @property
    def projects(self) -> list[dict[str, Any]]:
        return self.data.get("projects", [])

    @property
    def areas(self) -> dict[str, str]:
        return self.data.get("areas", {})


def load(agency_id: str, root: Path | None = None) -> Agency:
    path = (root or AGENCIES) / agency_id / "inventory.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no inventory for agency {agency_id!r} at {path}")
    return Agency(agency_id, yaml.safe_load(path.read_text(encoding="utf-8")) or {})


# --- parsing what the customer typed ---------------------------------------

def parse_beds(text: str) -> str | None:
    t = f" {text.lower()} "
    for key, aliases in BED_ALIASES.items():
        for a in aliases:
            if f" {a} " in t or f" {a}," in t or f" {a}?" in t or f" {a}." in t:
                return key
    # "2 bedroom apartment", "3-bedroom"
    m = re.search(r"\b([1-4])\s*-?\s*(?:bedroom|bed|bhk|br)\b", t)
    if m:
        return f"{m.group(1)}bed"
    if re.search(r"\bstudio\b", t):
        return "studio"
    return None


def parse_area(text: str, areas: dict[str, str]) -> str | None:
    t = text.lower()
    for key, label in areas.items():
        if key.replace("_", " ") in t or label.lower() in t:
            return key
        # initials people actually use: JVC, JVT, MBR
        initials = "".join(w[0] for w in label.split() if w[0].isalpha())
        if len(initials) >= 3 and re.search(rf"\b{initials.lower()}\b", t):
            return key
    return None


def parse_budget(text: str) -> int | None:
    """'1.2m', '1,200,000', '800k', 'under 2 million'."""
    t = text.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(m|million|k|thousand)\b", t)
    if m:
        n = float(m.group(1))
        return int(n * (1_000_000 if m.group(2).startswith(("m", "mil")) else 1_000))
    m = re.search(r"\b(\d{6,9})\b", t)
    return int(m.group(1)) if m else None


# --- the lookup -------------------------------------------------------------

def find_project(agency: Agency, text: str) -> dict[str, Any] | None:
    t = text.lower()
    for p in agency.projects:
        if p["name"].lower() in t:
            return p
        # "binghatti", "ellington" - developer or first word of the project
        first = p["name"].split()[0].lower()
        if len(first) > 4 and re.search(rf"\b{re.escape(first)}\b", t):
            return p
    return None


def quote(
    agency: Agency,
    *,
    project_id: str | None = None,
    area: str | None = None,
    beds: str | None = None,
    status: str | None = None,
) -> list[Quote]:
    """Every matching unit, or NeedMore naming the one thing to ask for.

    Returns a list because "2 bed in JVC" legitimately matches several projects,
    and showing three starting prices is a better answer than picking one and
    implying it is the only option.
    """
    if beds is None:
        raise NeedMore("beds", options=["studio", "1 bed", "2 bed", "3 bed"])

    pool = agency.projects
    if project_id:
        pool = [p for p in pool if p["id"] == project_id]
    if area:
        pool = [p for p in pool if p.get("area") == area]
    if status:
        pool = [p for p in pool if p.get("status") == status]

    if project_id is None and area is None:
        # Answering "2 bed in Palm Jumeirah" with JVC prices is worse than
        # asking. The customer named a place; we do not serve it; say so by
        # asking which of ours they mean.
        raise NeedMore("area", options=sorted(agency.areas.values()))

    out: list[Quote] = []
    for p in pool:
        unit = (p.get("units") or {}).get(beds)
        if not unit:
            continue
        out.append(Quote(
            project=p["name"],
            area=agency.areas.get(p.get("area", ""), p.get("area", "")),
            developer=p.get("developer", ""),
            unit=beds,
            price_from=str(unit["from"]),
            size_sqft=str(unit.get("size_sqft", "")),
            status=p.get("status", ""),
            handover=p.get("handover", ""),
            payment_plan=p.get("payment_plan", ""),
            service_charge_psf=str(p.get("service_charge_psf", "")),
            dld_project_number=str(p.get("dld_project_number", "")),
        ))

    # Cheapest first. A buyer asked what it costs; lead with the answer to that.
    out.sort(key=lambda q: int(q.price_from))
    return out


def allowed_numbers(quotes: list[Quote], agency: Agency) -> set[str]:
    """Every number the reply is permitted to contain.

    The guard compares against this. A figure that is not here never leaves,
    whatever the model wrote.
    """
    nums: set[str] = set()
    for q in quotes:
        nums |= {q.price_from, q.size_sqft, q.service_charge_psf, q.dld_project_number}
        nums |= set(re.findall(r"\d+", q.payment_plan))
        nums |= set(re.findall(r"\d+", q.handover))
    for v in (agency.data.get("fees") or {}).values():
        nums |= set(re.findall(r"[\d.]+", str(v)))
    for v in (agency.data.get("mortgage") or {}).values():
        nums |= set(re.findall(r"[\d.]+", str(v)))
    return {n for n in nums if n}
