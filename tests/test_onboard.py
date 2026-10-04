"""The owner setup page writes the same YAML the engine reads, and it is gated."""
import base64
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import garages, onboard
from app.main import app

client = TestClient(app)
GID = "onbtest"
DIR = onboard.GARAGES_DIR / GID


@pytest.fixture(autouse=True)
def clean():
    if DIR.exists():
        shutil.rmtree(DIR)
    yield
    if DIR.exists():
        shutil.rmtree(DIR)
    garages._cache.pop(GID, None)


def tok():
    return onboard.token_for(GID)


def test_the_link_is_gated_by_token():
    assert client.get(f"/onboard/{GID}").status_code == 403
    assert client.get(f"/onboard/{GID}?t=wrong").status_code == 403
    # a valid token renders the form (garage need not exist yet)
    assert client.get(f"/onboard/{GID}?t={tok()}").status_code == 200


def test_token_differs_per_garage():
    assert onboard.token_for("care") != onboard.token_for("demo")


def test_saving_writes_the_price_sheet_the_engine_reads():
    r = client.post(
        f"/onboard/{GID}?t={tok()}",
        data={
            "svc_name": ["Oil change", "Brake pads"],
            "svc_id": ["", ""],
            "price_sedan": ["180", "350-450"],
            "price_suv": ["260", ""],
            "price_luxury": ["450", ""],
            "svc_note": ["includes filter", "per axle"],
            "owner_alert_number": "971500000000",
            "maps_link": "https://maps.app.goo.gl/x",
            "address": "Al Quoz",
            "max_cars_per_hour": "3",
            "warranty": "6 months",
            "payment_methods": "cash, card",
            "pickup_notes": "Free within 15 km",
            "open_mon": "08:00", "close_mon": "19:00",
            "closed_fri": "on",
            "faq_q": ["towing, recovery"],
            "faq_a": ["Yes, we recover from anywhere in Dubai for AED 150."],
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    g = garages.load(GID)
    services = g["prices"]["services"]
    assert {s["id"] for s in services} == {"oil_change", "brake_pads"}
    oil = next(s for s in services if s["id"] == "oil_change")
    assert oil["prices"] == {"sedan": "180", "suv": "260", "luxury": "450"}
    assert oil["notes"] == "includes filter"
    # a blank price is simply omitted, never invented
    brake = next(s for s in services if s["id"] == "brake_pads")
    assert brake["prices"] == {"sedan": "350-450"}

    assert g["info"]["owner_alert_number"] == "971500000000"
    assert g["info"]["max_cars_per_hour"] == 3
    assert g["info"]["payment_methods"] == ["cash", "card"]
    assert g["info"]["hours"]["mon"] == ["08:00", "19:00"]
    assert g["info"]["hours"]["fri"] is None
    assert g["faq"]["faqs"][0]["a"]["en"].startswith("Yes, we recover")


def test_a_saved_faq_answers_a_question(monkeypatch):
    from app import engine
    client.post(
        f"/onboard/{GID}?t={tok()}",
        data={"svc_name": ["Oil change"], "svc_id": [""], "price_sedan": ["180"],
              "price_suv": [""], "price_luxury": [""], "svc_note": [""],
              "faq_q": ["towing, recovery"], "faq_a": ["Yes, AED 150 anywhere in Dubai."]},
        follow_redirects=False,
    )
    garages._cache.pop(GID, None)
    g = garages.load(GID)
    monkeypatch.setattr(engine, "classify",
                        lambda *a, **k: {"intent": "info", "language": "en", "info_topic": None, "confidence": 0.9})
    monkeypatch.setattr(engine, "compose",
                        lambda name, facts, msg, history=None, **k: "ANSWER:" + facts)
    r = engine.build_reply(g, "do you do recovery?")
    assert "AED 150 anywhere in Dubai" in r.text
    assert not r.is_handoff
