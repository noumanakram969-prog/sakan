import os

os.environ.setdefault("META_APP_SECRET", "test-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_mistri.db")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("WEBHOOK_TOKEN", "test-webhook-token")

import pytest  # noqa: E402

from app.db import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    """Create the tables once, for every test file.

    Without this, a file that never touches the database still fails when run
    on its own - the price branch checks slot availability, which reads
    `bookings`. Passing only because another file ran first is not passing.
    """
    init_db()


@pytest.fixture
def sheet():
    """A small sheet with the shapes that matter: fixed price, range, free, unfilled."""
    return {
        "currency": "AED",
        "services": [
            {
                "id": "oil_change",
                "name": {"en": "Oil change", "ar": "تغيير الزيت"},
                "prices": {"sedan": "180", "suv": "240", "luxury": "450"},
                "notes": "Includes filter",
            },
            {
                "id": "brake_pads_front",
                "name": {"en": "Front brake pads replacement"},
                "prices": {"sedan": "400-600", "suv": "550-800", "luxury": "TODO"},
            },
            {
                "id": "inspection",
                "name": {"en": "Inspection"},
                "prices": {"sedan": "Free", "suv": "Free", "luxury": "Free"},
            },
        ],
        "model_categories": {"patrol": "suv", "range rover": "luxury"},
    }


@pytest.fixture
def garage(sheet):
    return {
        "id": "test",
        "prices": sheet,
        "faq": {},
        "info": {
            "name": "Test Auto Repair",
            "address": "Al Quoz 3, Dubai",
            "maps_link": "https://maps.example/test",
            "payment_methods": ["cash", "card"],
            "warranty": "6 months on parts and labour",
            "pickup_available": True,
            "pickup_notes": "Free within 10 km",
            "hours": {"sat": ["08:00", "20:00"], "fri": None},
        },
    }
