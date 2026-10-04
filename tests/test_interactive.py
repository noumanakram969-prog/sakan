"""WhatsApp buttons/list — built in code from real data, never by the model."""
import pytest

from app import engine, respond, whatsapp


@pytest.fixture
def calls(monkeypatch):
    rec = {"text": [], "buttons": [], "list": []}

    async def _text(to, body): rec["text"].append((to, body)); return {"messages": [{"id": "t"}]}
    async def _buttons(to, body, buttons): rec["buttons"].append((to, body, buttons)); return {"messages": [{"id": "b"}]}
    async def _list(to, body, button, rows): rec["list"].append((to, body, rows)); return {"messages": [{"id": "l"}]}

    monkeypatch.setattr(respond.whatsapp, "send_text", _text)
    monkeypatch.setattr(respond.whatsapp, "send_buttons", _buttons)
    monkeypatch.setattr(respond.whatsapp, "send_list", _list)
    return rec


@pytest.mark.asyncio
async def test_slots_go_out_as_buttons(calls):
    r = engine.Reply(text="Oil change — AED 180. Pick a time:", intent="price",
                     slot_buttons=[("Wed 10 Sep, 10:00", "Wed 10 Sep, 10:00"),
                                   ("Wed 10 Sep, 11:00", "Wed 10 Sep, 11:00")])
    await respond._send_reply("971500000000", r)
    assert len(calls["buttons"]) == 1 and not calls["text"]
    _, body, buttons = calls["buttons"][0]
    assert "180" in body
    assert [b["title"] for b in buttons] == ["Wed 10 Sep, 10:00", "Wed 10 Sep, 11:00"]


@pytest.mark.asyncio
async def test_greeting_shows_the_quick_menu(calls):
    r = engine.Reply(text="Hello! How can we help?", intent="greeting", quick_menu=True)
    await respond._send_reply("971500000000", r)
    assert len(calls["buttons"]) == 1
    titles = [b["title"] for b in calls["buttons"][0][2]]
    assert titles == ["Book a car in", "Opening hours", "Our location"]


@pytest.mark.asyncio
async def test_a_plain_reply_stays_plain(calls):
    r = engine.Reply(text="Our service advisor will call you shortly.", intent="other",
                     handoff_reason="x")
    await respond._send_reply("971500000000", r)
    assert len(calls["text"]) == 1 and not calls["buttons"]


@pytest.mark.asyncio
async def test_button_titles_are_trimmed_to_twenty_chars(monkeypatch):
    sent = {}
    async def _post(payload): sent["p"] = payload; return {"messages": [{"id": "x"}]}
    monkeypatch.setattr(whatsapp, "_post", _post)
    await whatsapp.send_buttons("971500000000", "body",
                                [{"id": "x", "title": "A title far longer than twenty characters"}])
    title = sent["p"]["interactive"]["action"]["buttons"][0]["reply"]["title"]
    assert len(title) == 20
