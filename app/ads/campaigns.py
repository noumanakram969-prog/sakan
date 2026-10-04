"""Building the campaign -> ad set -> ad tree.

One rule runs through this file: **nothing is created active.** Every object is
written PAUSED, and turning it on is a separate, deliberate call. An automation
that can create a live campaign is one bad loop away from spending a client's
month in an afternoon, and no amount of care in the calling code buys back the
money. So the guarantee lives here, where it cannot be forgotten.

Mirrors the guarantee the garage bot already makes about prices: the dangerous
thing is not possible, rather than merely discouraged.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .client import GraphClient

log = logging.getLogger("mistri.ads")

PAUSED = "PAUSED"
ACTIVE = "ACTIVE"

# Meta rejects an ad set below this. Hard-coded rather than discovered at
# runtime because a floor that moves silently is how a "minimum budget" test
# becomes a real spend.
MIN_DAILY_BUDGET_MINOR = 500  # 5.00 in the account currency


@dataclass(frozen=True)
class Targeting:
    """Only the fields a lead campaign actually sets."""

    countries: list[str] = field(default_factory=lambda: ["AE"])
    age_min: int = 25
    age_max: int = 60
    interests: list[dict[str, str]] = field(default_factory=list)
    publisher_platforms: list[str] = field(default_factory=lambda: ["facebook", "instagram"])

    def to_spec(self) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "geo_locations": {"countries": self.countries},
            "age_min": self.age_min,
            "age_max": self.age_max,
            "publisher_platforms": self.publisher_platforms,
        }
        if self.interests:
            spec["flexible_spec"] = [{"interests": self.interests}]
        return spec


class CampaignBuilder:
    def __init__(self, client: GraphClient, ad_account_id: str, *, page_id: str | None = None) -> None:
        if not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"
        self.client = client
        self.account = ad_account_id
        self.page_id = page_id

    # -- campaign ----------------------------------------------------------

    def create_campaign(
        self,
        name: str,
        *,
        objective: str = "OUTCOME_LEADS",
        daily_budget_minor: int | None = None,
        buying_type: str = "AUCTION",
    ) -> str:
        """Create a PAUSED campaign and return its id.

        daily_budget_minor set here means campaign budget optimisation - Meta
        spreads one budget across the ad sets. Left None, each ad set carries
        its own.
        """
        payload: dict[str, Any] = {
            "name": name,
            "objective": objective,
            "status": PAUSED,
            "buying_type": buying_type,
            "special_ad_categories": json.dumps([]),
        }
        if daily_budget_minor is not None:
            payload["daily_budget"] = _checked_budget(daily_budget_minor)

        res = self.client.post(f"{self.account}/campaigns", **payload)
        log.info("campaign created %s (%s) PAUSED", res["id"], name)
        return res["id"]

    # -- ad set ------------------------------------------------------------

    def create_ad_set(
        self,
        campaign_id: str,
        name: str,
        *,
        daily_budget_minor: int | None = None,
        optimization_goal: str = "LEAD_GENERATION",
        billing_event: str = "IMPRESSIONS",
        targeting: Targeting | None = None,
        destination_type: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "name": name,
            "campaign_id": campaign_id,
            "status": PAUSED,
            "optimization_goal": optimization_goal,
            "billing_event": billing_event,
            "targeting": json.dumps((targeting or Targeting()).to_spec()),
        }
        if daily_budget_minor is not None:
            payload["daily_budget"] = _checked_budget(daily_budget_minor)
        if destination_type:
            # WHATSAPP sends the click straight into a chat - the format that
            # feeds a WhatsApp agent instead of a form.
            payload["destination_type"] = destination_type
            if destination_type == "WHATSAPP" and self.page_id:
                payload["promoted_object"] = json.dumps({"page_id": self.page_id})

        res = self.client.post(f"{self.account}/adsets", **payload)
        log.info("ad set created %s (%s) PAUSED", res["id"], name)
        return res["id"]

    # -- creative and ad ---------------------------------------------------

    def create_creative(
        self,
        name: str,
        *,
        message: str,
        headline: str,
        link: str,
        description: str = "",
        call_to_action: str = "LEARN_MORE",
    ) -> str:
        if not self.page_id:
            raise ValueError("page_id is required to create a creative")

        spec = {
            "page_id": self.page_id,
            "link_data": {
                "message": message,
                "link": link,
                "name": headline,
                "description": description,
                "call_to_action": {"type": call_to_action},
            },
        }
        res = self.client.post(
            f"{self.account}/adcreatives",
            name=name,
            object_story_spec=json.dumps(spec),
        )
        log.info("creative created %s (%s)", res["id"], name)
        return res["id"]

    def create_ad(self, ad_set_id: str, creative_id: str, name: str) -> str:
        res = self.client.post(
            f"{self.account}/ads",
            name=name,
            adset_id=ad_set_id,
            creative=json.dumps({"creative_id": creative_id}),
            status=PAUSED,
        )
        log.info("ad created %s (%s) PAUSED", res["id"], name)
        return res["id"]

    # -- creative testing --------------------------------------------------

    def create_creative_test(
        self,
        ad_set_id: str,
        variants: list[dict[str, str]],
        *,
        link: str,
        name_prefix: str = "test",
    ) -> list[dict[str, str]]:
        """One ad per variant in a single ad set.

        Same ad set on purpose: identical budget, audience and optimisation, so
        the only difference between variants is the copy. Split across ad sets
        and you are measuring the auction, not the creative.
        """
        out = []
        for i, v in enumerate(variants, 1):
            label = v.get("label") or f"v{i}"
            creative_id = self.create_creative(
                f"{name_prefix}-{label}-creative",
                message=v["message"],
                headline=v["headline"],
                link=link,
                description=v.get("description", ""),
                call_to_action=v.get("call_to_action", "LEARN_MORE"),
            )
            ad_id = self.create_ad(ad_set_id, creative_id, f"{name_prefix}-{label}")
            out.append({"label": label, "ad_id": ad_id, "creative_id": creative_id})
        return out

    # -- state changes -----------------------------------------------------

    def set_status(self, object_id: str, status: str) -> dict[str, Any]:
        """Activating is deliberate and separate. Nothing above calls this."""
        if status not in {ACTIVE, PAUSED, "ARCHIVED", "DELETED"}:
            raise ValueError(f"refusing unknown status {status!r}")
        if status == ACTIVE:
            log.warning("ACTIVATING %s - this object can now spend money", object_id)
        return self.client.post(object_id, status=status)

    def set_daily_budget(self, ad_set_id: str, daily_budget_minor: int) -> dict[str, Any]:
        return self.client.post(ad_set_id, daily_budget=_checked_budget(daily_budget_minor))


def _checked_budget(minor: int) -> int:
    if not isinstance(minor, int) or isinstance(minor, bool):
        raise TypeError("budget must be an int in minor units (fils, cents)")
    if minor < MIN_DAILY_BUDGET_MINOR:
        raise ValueError(
            f"daily budget {minor} is below Meta's minimum {MIN_DAILY_BUDGET_MINOR} "
            "(minor units - 500 = AED 5.00)"
        )
    return minor
