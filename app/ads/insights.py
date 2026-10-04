"""Performance reporting.

Meta returns actions as a list of {action_type, value} rather than columns, and
spend as a string. Both are easy to misread, and a misread number here is worse
than no report: it looks authoritative and it decides budgets. So everything is
flattened and typed in one place, and cost-per-lead is computed rather than
trusted from whatever Meta happened to attribute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

from .client import GraphClient

log = logging.getLogger("mistri.ads")

# The action types that count as a lead for this stack. A WhatsApp click is a
# lead here because the agent picks it up from there - which is exactly why the
# ads side and the agent side belong in one system.
LEAD_ACTIONS = {
    "lead",
    "onsite_conversion.lead_grouped",
    "offsite_conversion.fb_pixel_lead",
    "onsite_conversion.messaging_conversation_started_7d",
    "onsite_conversion.total_messaging_connection",
}

FIELDS = [
    "campaign_id", "campaign_name",
    "adset_id", "adset_name",
    "ad_id", "ad_name",
    "impressions", "clicks", "spend", "reach", "frequency",
    "ctr", "cpc", "cpm", "actions", "date_start", "date_stop",
]


@dataclass
class Row:
    level: str
    object_id: str
    name: str
    impressions: int
    clicks: int
    spend: float
    leads: int
    date_start: str
    date_stop: str

    @property
    def ctr(self) -> float:
        return (self.clicks / self.impressions * 100) if self.impressions else 0.0

    @property
    def cost_per_lead(self) -> float | None:
        """None, not zero, when there are no leads.

        Zero would mean "free", and a budget rule reading zero as cheapest would
        pour money into the ad that converts nobody.
        """
        return (self.spend / self.leads) if self.leads else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "id": self.object_id,
            "name": self.name,
            "impressions": self.impressions,
            "clicks": self.clicks,
            "spend": round(self.spend, 2),
            "leads": self.leads,
            "ctr": round(self.ctr, 2),
            "cost_per_lead": round(self.cost_per_lead, 2) if self.cost_per_lead is not None else None,
            "from": self.date_start,
            "to": self.date_stop,
        }


def count_leads(actions: Iterable[dict[str, Any]] | None) -> int:
    if not actions:
        return 0
    total = 0
    for a in actions:
        if a.get("action_type") in LEAD_ACTIONS:
            try:
                total += int(float(a.get("value", 0)))
            except (TypeError, ValueError):
                continue
    return total


def _row(raw: dict[str, Any], level: str) -> Row:
    id_key, name_key = {
        "campaign": ("campaign_id", "campaign_name"),
        "adset": ("adset_id", "adset_name"),
        "ad": ("ad_id", "ad_name"),
    }[level]
    return Row(
        level=level,
        object_id=raw.get(id_key, ""),
        name=raw.get(name_key, ""),
        impressions=int(raw.get("impressions") or 0),
        clicks=int(raw.get("clicks") or 0),
        spend=float(raw.get("spend") or 0.0),
        leads=count_leads(raw.get("actions")),
        date_start=raw.get("date_start", ""),
        date_stop=raw.get("date_stop", ""),
    )


def fetch(
    client: GraphClient,
    ad_account_id: str,
    *,
    level: str = "campaign",
    date_preset: str = "last_7d",
    time_range: dict[str, str] | None = None,
    filtering: list[dict[str, Any]] | None = None,
) -> list[Row]:
    if not ad_account_id.startswith("act_"):
        ad_account_id = f"act_{ad_account_id}"

    params: dict[str, Any] = {"level": level, "fields": ",".join(FIELDS)}
    if time_range:
        import json as _json
        params["time_range"] = _json.dumps(time_range)
    else:
        params["date_preset"] = date_preset
    if filtering:
        import json as _json
        params["filtering"] = _json.dumps(filtering)

    rows = [_row(r, level) for r in client.paged(f"{ad_account_id}/insights", **params)]
    log.info("insights %s level=%s rows=%d", ad_account_id, level, len(rows))
    return rows


def summarise(rows: list[Row]) -> dict[str, Any]:
    spend = sum(r.spend for r in rows)
    leads = sum(r.leads for r in rows)
    impressions = sum(r.impressions for r in rows)
    clicks = sum(r.clicks for r in rows)
    return {
        "objects": len(rows),
        "impressions": impressions,
        "clicks": clicks,
        "spend": round(spend, 2),
        "leads": leads,
        "ctr": round(clicks / impressions * 100, 2) if impressions else 0.0,
        "cost_per_lead": round(spend / leads, 2) if leads else None,
    }


def render(rows: list[Row]) -> str:
    """A report somebody will actually read, in a WhatsApp message or a terminal."""
    if not rows:
        return "No delivery in this period."

    # Cheapest lead first; anything with no leads sorts to the bottom rather
    # than the top, which is where a None would otherwise land.
    ranked = sorted(rows, key=lambda r: (r.cost_per_lead is None, r.cost_per_lead or 0))

    def money(v: float | None) -> str:
        return f"{v:>9.2f}" if v is not None else f"{'-':>9}"

    lines = [f"{'name':<28} {'spend':>9} {'leads':>6} {'CPL':>9} {'CTR':>6}", "-" * 62]
    for r in ranked:
        lines.append(
            f"{r.name[:28]:<28} {r.spend:>9.2f} {r.leads:>6} {money(r.cost_per_lead)} {r.ctr:>5.2f}%"
        )

    t = summarise(rows)
    lines.append("-" * 62)
    lines.append(
        f"{'TOTAL':<28} {t['spend']:>9.2f} {t['leads']:>6} "
        f"{money(t['cost_per_lead'])} {t['ctr']:>5.2f}%"
    )
    return "\n".join(lines)
