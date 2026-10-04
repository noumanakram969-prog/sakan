"""Meta Marketing API + Conversions API.

The ads half of the stack. Same discipline as the WhatsApp half:

* one module owns the HTTP (`client`), so a version bump is one file
* the dangerous thing is impossible rather than discouraged - `campaigns`
  cannot create an object that is already spending, the way `pricing` cannot
  return a price that is not on the sheet
* deciding is separate from doing - `rules.evaluate` is pure, `rules.apply`
  defaults to a dry run
* personal data is hashed before it leaves the process (`capi`)

    from app.ads import settings_from_env, GraphClient, CampaignBuilder

    cfg = settings_from_env()
    with GraphClient(cfg.access_token, version=cfg.graph_version) as c:
        b = CampaignBuilder(c, cfg.ad_account_id, page_id=cfg.page_id)
        campaign = b.create_campaign("JVC buyers - Oct")   # PAUSED
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .campaigns import CampaignBuilder, Targeting
from .capi import ConversionsAPI, Event, hash_user_data
from .client import GraphClient, MetaError
from .insights import Row, fetch, render, summarise
from .rules import Action, RuleSet, apply, evaluate

__all__ = [
    "GraphClient", "MetaError",
    "CampaignBuilder", "Targeting",
    "ConversionsAPI", "Event", "hash_user_data",
    "fetch", "render", "summarise", "Row",
    "evaluate", "apply", "RuleSet", "Action",
    "AdsSettings", "settings_from_env",
]


@dataclass
class AdsSettings:
    access_token: str = ""
    ad_account_id: str = ""
    sandbox_ad_account_id: str = ""
    page_id: str = ""
    business_id: str = ""
    pixel_id: str = ""
    capi_token: str = ""
    capi_test_event_code: str = ""
    graph_version: str = "v21.0"

    @property
    def write_account(self) -> str:
        """Where writes go.

        The sandbox when there is one. A sandbox account is a real ad account
        through the API but cannot spend, so there is no reason to point writes
        at a live account while building or demonstrating.
        """
        return self.sandbox_ad_account_id or self.ad_account_id


def settings_from_env(path: str | Path | None = ".env.ads") -> AdsSettings:
    """Read .env.ads, then the real environment, which wins.

    Kept out of app/config.py deliberately: the bot must start and answer
    customers whether or not anybody has ever configured the ads side.
    """
    values: dict[str, str] = {}
    p = Path(path) if path else None
    if p and p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip('"').strip("'")

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key) or values.get(key, "") or default

    return AdsSettings(
        access_token=get("META_ADS_ACCESS_TOKEN"),
        ad_account_id=get("META_AD_ACCOUNT_ID"),
        sandbox_ad_account_id=get("META_SANDBOX_AD_ACCOUNT_ID"),
        page_id=get("META_PAGE_ID"),
        business_id=get("META_BUSINESS_ID"),
        pixel_id=get("META_PIXEL_ID"),
        capi_token=get("META_CAPI_TOKEN"),
        capi_test_event_code=get("META_CAPI_TEST_EVENT_CODE"),
        graph_version=get("META_GRAPH_VERSION", "v21.0"),
    )
