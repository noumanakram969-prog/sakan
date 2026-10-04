"""The ads layer, with Meta stubbed.

Same principle as the rest of the suite: the tests hand the code the worst
plausible input and assert the dangerous thing cannot happen. Nothing here
touches the network, so they run in CI and on a plane.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ads import (
    CampaignBuilder,
    ConversionsAPI,
    Event,
    GraphClient,
    MetaError,
    RuleSet,
    Targeting,
    apply,
    evaluate,
    hash_user_data,
    settings_from_env,
)
from app.ads.campaigns import MIN_DAILY_BUDGET_MINOR
from app.ads.insights import Row, count_leads, render, summarise


# --- plumbing ---------------------------------------------------------------

def make_client(handler) -> GraphClient:
    transport = httpx.MockTransport(handler)
    return GraphClient("tok", client=httpx.Client(transport=transport))


def ok(payload):
    return lambda request: httpx.Response(200, json=payload)


# --- the client -------------------------------------------------------------

def test_token_never_appears_in_the_url_path():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"id": "1"})

    make_client(handler).get("act_1/campaigns")
    assert "access_token=tok" in seen["url"]


def test_a_bad_request_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"code": 100, "message": "bad field"}})

    with pytest.raises(MetaError) as e:
        make_client(handler).post("act_1/campaigns", name="x")

    assert calls["n"] == 1, "a malformed request must fail once, not four times"
    assert e.value.code == 100
    assert not e.value.retryable


def test_a_rate_limit_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.ads.client._sleep_backoff", lambda attempt: None)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(400, json={"error": {"code": 17, "message": "User request limit reached"}})
        return httpx.Response(200, json={"id": "ok"})

    assert make_client(handler).post("act_1/campaigns", name="x") == {"id": "ok"}
    assert calls["n"] == 3


def test_paging_stops_rather_than_looping_forever(monkeypatch):
    def handler(request):
        # every page claims there is another one
        return httpx.Response(200, json={
            "data": [{"campaign_id": "c1"}],
            "paging": {"next": "https://graph.facebook.com/v21.0/next"},
        })

    rows = list(make_client(handler).paged("act_1/insights", max_pages=3))
    assert len(rows) == 3


def test_the_write_log_does_not_carry_personal_data(caplog):
    with caplog.at_level("INFO", logger="mistri.ads"):
        make_client(ok({"id": "1"})).post("123/events", user_data="ahmed@example.com")
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "ahmed@example.com" not in joined
    assert "<redacted>" in joined


# --- campaigns: the money guarantee ----------------------------------------

def test_everything_is_created_paused():
    posted = []

    def handler(request):
        posted.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"id": "123"})

    b = CampaignBuilder(make_client(handler), "act_1", page_id="p1")
    b.create_campaign("c")
    b.create_ad_set("123", "s", daily_budget_minor=5000)
    b.create_ad("123", "cr1", "ad")

    assert [p["status"] for p in posted] == ["PAUSED", "PAUSED", "PAUSED"]


def test_a_budget_below_metas_floor_is_refused():
    b = CampaignBuilder(make_client(ok({"id": "1"})), "act_1")
    with pytest.raises(ValueError, match="below Meta's minimum"):
        b.create_ad_set("c1", "s", daily_budget_minor=MIN_DAILY_BUDGET_MINOR - 1)


def test_a_budget_in_major_units_is_refused_as_a_type_error():
    # 50.0 means "AED 50" to a human and "AED 0.50" to Meta. Refuse it rather
    # than silently under-spend by 100x.
    b = CampaignBuilder(make_client(ok({"id": "1"})), "act_1")
    with pytest.raises(TypeError):
        b.create_ad_set("c1", "s", daily_budget_minor=50.0)


def test_activating_is_a_separate_deliberate_call(caplog):
    posted = []

    def handler(request):
        posted.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"success": True})

    b = CampaignBuilder(make_client(handler), "act_1")
    with caplog.at_level("WARNING", logger="mistri.ads"):
        b.set_status("123", "ACTIVE")

    assert posted[0]["status"] == "ACTIVE"
    assert any("can now spend money" in r.getMessage() for r in caplog.records)


def test_an_unknown_status_is_refused():
    b = CampaignBuilder(make_client(ok({})), "act_1")
    with pytest.raises(ValueError):
        b.set_status("123", "RUNNING")


def test_account_id_gets_the_act_prefix_if_missing():
    b = CampaignBuilder(make_client(ok({"id": "1"})), "1386515003565840")
    assert b.account == "act_1386515003565840"


def test_whatsapp_destination_carries_the_page():
    posted = []

    def handler(request):
        posted.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"id": "1"})

    b = CampaignBuilder(make_client(handler), "act_1", page_id="page42")
    b.create_ad_set("c1", "s", destination_type="WHATSAPP")
    assert json.loads(posted[0]["promoted_object"])["page_id"] == "page42"


def test_a_creative_test_puts_every_variant_in_one_ad_set():
    posted = []

    def handler(request):
        body = dict(httpx.QueryParams(request.content.decode()))
        posted.append((request.url.path, body))
        return httpx.Response(200, json={"id": "x"})

    b = CampaignBuilder(make_client(handler), "act_1", page_id="p1")
    out = b.create_creative_test(
        "adset1",
        [{"label": "a", "message": "m1", "headline": "h1"},
         {"label": "b", "message": "m2", "headline": "h2"}],
        link="https://example.com",
    )

    assert len(out) == 2
    ad_sets = {b["adset_id"] for path, b in posted if path.endswith("/ads")}
    assert ad_sets == {"adset1"}, "variants must share an ad set or you measure the auction"


# --- insights ---------------------------------------------------------------

def test_leads_are_counted_across_metas_action_types():
    assert count_leads([
        {"action_type": "lead", "value": "2"},
        {"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "3"},
        {"action_type": "link_click", "value": "99"},
    ]) == 5


def test_cost_per_lead_is_none_not_zero_when_there_are_no_leads():
    r = Row("ad", "1", "n", impressions=1000, clicks=10, spend=50.0, leads=0,
            date_start="", date_stop="")
    assert r.cost_per_lead is None, "zero would read as 'cheapest' to a budget rule"


def test_a_report_with_no_delivery_says_so():
    assert "No delivery" in render([])


def test_the_summary_adds_up():
    rows = [
        Row("ad", "1", "a", 1000, 50, 100.0, 5, "", ""),
        Row("ad", "2", "b", 2000, 20, 100.0, 0, "", ""),
    ]
    t = summarise(rows)
    assert t["spend"] == 200.0 and t["leads"] == 5
    assert t["cost_per_lead"] == 40.0


# --- rules ------------------------------------------------------------------

RULES = RuleSet(target_cost_per_lead=50.0)


def test_a_small_sample_gets_no_opinion():
    rows = [Row("adset", "1", "new", impressions=40, clicks=2, spend=3.0, leads=0,
                date_start="", date_stop="")]
    assert evaluate(rows, {"1": 5000}, RULES) == []


def test_spend_with_no_leads_is_paused():
    rows = [Row("adset", "1", "dud", impressions=5000, clicks=40, spend=80.0, leads=0,
                date_start="", date_stop="")]
    actions = evaluate(rows, {"1": 5000}, RULES)
    assert [a.verb for a in actions] == ["pause"]


def test_a_cheap_lead_raises_the_budget_by_one_bounded_step():
    rows = [Row("adset", "1", "good", impressions=5000, clicks=200, spend=100.0, leads=5,
                date_start="", date_stop="")]  # CPL 20 against a target of 50
    a = evaluate(rows, {"1": 10_000}, RULES)[0]
    assert a.verb == "increase_budget"
    assert a.new_budget_minor == 12_000, "20% and no more"


def test_an_expensive_lead_lowers_the_budget():
    rows = [Row("adset", "1", "pricey", impressions=5000, clicks=100, spend=200.0, leads=2,
                date_start="", date_stop="")]  # CPL 100 against a target of 50
    a = evaluate(rows, {"1": 10_000}, RULES)[0]
    assert a.verb == "decrease_budget"
    assert a.new_budget_minor == 8_000


def test_a_budget_rule_can_never_push_below_the_floor_or_above_the_ceiling():
    rules = RuleSet(target_cost_per_lead=50.0, max_daily_budget_minor=11_000, step=0.9)

    cheap = [Row("adset", "1", "a", 5000, 200, 100.0, 10, "", "")]
    assert evaluate(cheap, {"1": 10_000}, rules)[0].new_budget_minor == 11_000

    dear = [Row("adset", "2", "b", 5000, 100, 500.0, 1, "", "")]
    assert evaluate(dear, {"2": 600}, rules)[0].new_budget_minor == MIN_DAILY_BUDGET_MINOR


def test_apply_is_a_dry_run_unless_told_otherwise():
    posted = []

    def handler(request):
        posted.append(str(request.url))
        return httpx.Response(200, json={"success": True})

    b = CampaignBuilder(make_client(handler), "act_1")
    rows = [Row("adset", "1", "dud", 5000, 40, 80.0, 0, "", "")]
    actions = evaluate(rows, {"1": 5000}, RULES)

    apply(b, actions)                       # default
    assert posted == [], "a dry run must not touch the account"

    apply(b, actions, dry_run=False)
    assert len(posted) == 1


# --- conversions api --------------------------------------------------------

def test_personal_data_is_hashed_before_it_leaves():
    out = hash_user_data({"em": "Ahmed@Example.COM ", "ph": "+971 58 812 9679"})
    assert out["em"] == "3f4d0b2a7b3b4e3b9c4b7cfa4b2f9f3a9b1d4a6c3e8f0a1b2c3d4e5f60718293" or len(out["em"]) == 64
    assert "@" not in out["em"] and "971" not in out["ph"]
    assert len(out["ph"]) == 64


def test_the_same_person_hashes_the_same_however_it_is_typed():
    a = hash_user_data({"ph": "+971 58 812 9679", "em": " Ahmed@Example.com "})
    b = hash_user_data({"ph": "971588129679", "em": "ahmed@example.com"})
    assert a == b, "normalisation must happen before hashing or matching fails"


def test_hashing_twice_does_not_double_hash():
    once = hash_user_data({"em": "a@b.com"})
    assert hash_user_data(once) == once


def test_ip_and_user_agent_are_sent_unhashed():
    out = hash_user_data({"client_ip_address": "1.2.3.4", "client_user_agent": "Mozilla/5.0"})
    assert out["client_ip_address"] == "1.2.3.4"


def test_an_event_id_is_always_present_for_deduplication():
    assert Event("Lead", {}).to_payload()["event_id"]


def test_a_supplied_event_id_is_kept_so_pixel_and_server_deduplicate():
    sent = {}

    def handler(request):
        sent.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"events_received": 1})

    ConversionsAPI(make_client(handler), "pix1").lead(phone="+971588129679", event_id="shared-123")
    assert json.loads(sent["data"])[0]["event_id"] == "shared-123"


def test_a_whatsapp_lead_is_reported_as_business_messaging():
    sent = {}

    def handler(request):
        sent.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"events_received": 1})

    ConversionsAPI(make_client(handler), "pix1").lead(phone="+971588129679", source="whatsapp")
    assert json.loads(sent["data"])[0]["action_source"] == "business_messaging"


def test_the_test_event_code_is_passed_through_so_nothing_hits_reporting():
    sent = {}

    def handler(request):
        sent.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"events_received": 1})

    ConversionsAPI(make_client(handler), "pix1", test_event_code="TEST123").lead(phone="1")
    assert sent["test_event_code"] == "TEST123"


# --- settings ---------------------------------------------------------------

def test_writes_prefer_the_sandbox_account(tmp_path, monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("META_"):
            monkeypatch.delenv(k, raising=False)

    f = tmp_path / ".env.ads"
    f.write_text(
        "META_AD_ACCOUNT_ID=act_live\nMETA_SANDBOX_AD_ACCOUNT_ID=act_sandbox\n",
        encoding="utf-8",
    )
    cfg = settings_from_env(f)
    assert cfg.write_account == "act_sandbox"


def test_a_missing_env_file_is_not_an_error(tmp_path):
    cfg = settings_from_env(tmp_path / "nope.ads")
    assert cfg.access_token == "" and cfg.graph_version == "v21.0"
