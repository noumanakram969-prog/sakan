"""One customer message in, one reply out.

The shape of a turn, and the order matters:

    1. classify   - what is being asked (model, no prices in sight)
    2. resolve    - look the answer up in the garage's own files (plain code)
    3. compose    - write it in the customer's language (model, facts only)
    4. guard      - refuse to send anything the facts do not support
    5. handoff    - when any step above says "not sure", a human takes it

Steps 2 and 4 are why a wrong price cannot reach a customer. Step 1 and 3 make
it read like a person. Never move a price into step 1 or 3 to save a call.

Booking works the same way: the model never picks a time. It is handed the
slots the garage can genuinely take, and the guard blocks any other.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from . import booking, guard, pricing, slots
from .db import Booking, utcnow
from .llm import LLMUnavailable, classify, compose

log = logging.getLogger(__name__)

CONFIDENCE_FLOOR = 0.7
SLOTS_OFFERED = 3

# Types the bot cannot read. It does not need to: in coexistence the photo or
# voice note is already sitting in the owner's own WhatsApp, so handing over
# costs nothing and is what a person would do anyway.
UNREADABLE = {
    "image": "a photo",
    "audio": "a voice note",
    "voice": "a voice note",
    "video": "a video",
    "document": "a document",
    "sticker": "a sticker",
    "location": "a location",
    "contacts": "a contact card",
}

MEDIA_ACK = {
    "en": "Thanks, got it. Our service advisor will look and call you shortly.",
    "ar": "شكراً، وصلتنا. سيطلع عليها مستشار الخدمة ويتصل بك قريباً.",
    "hi": "धन्यवाद, मिल गया। हमारा सर्विस एडवाइज़र देखकर आपको जल्द कॉल करेगा।",
    "ur": "Shukriya, mil gaya. Hamara service advisor dekh kar aap ko jald call karega.",
}

HANDOFF = {
    "en": "Our service advisor will call you shortly.",
    "ar": "سيتصل بك مستشار الخدمة قريباً.",
    "hi": "हमारा सर्विस एडवाइज़र आपको जल्द कॉल करेगा।",
    "ur": "Hamara service advisor aap ko jald call karega.",
}


@dataclass
class Reply:
    text: str
    intent: str
    language: str = "en"
    quote: pricing.Quote | None = None
    booking: Booking | None = None
    handoff_reason: str | None = None
    blocked: guard.Verdict | None = None
    # Interactive extras, built in code (never by the model) so the price/time
    # guarantees are unaffected. respond.py sends buttons/list when present.
    slot_buttons: list[tuple[str, str]] = field(default_factory=list)
    quick_menu: bool = False

    @property
    def is_handoff(self) -> bool:
        return self.handoff_reason is not None


def handoff_line(garage: dict[str, Any], language: str) -> str:
    custom = ((garage.get("info") or {}).get("handoff_line") or {})
    return custom.get(language) or HANDOFF.get(language) or HANDOFF["en"]


# The booking question under a price quote, per language/script. Built in code
# (not the model) so a price reply always has the same tidy shape and the times
# below always have a clear prompt. (with-slots, without-slots).
_BOOK_Q = {
    "ar":            ("هل ترغب بالحجز؟ اختر موعداً بالأسفل 👇", "هل ترغب بالحجز؟"),
    "hi_devanagari": ("क्या बुकिंग करना चाहेंगे? नीचे समय चुनें 👇", "क्या बुकिंग करना चाहेंगे?"),
    "ur_arabic":     ("کیا بکنگ کرنا چاہیں گے؟ نیچے وقت منتخب کریں 👇", "کیا بکنگ کرنا چاہیں گے؟"),
    "hi":            ("Book karna chahenge? Neeche time chunein 👇", "Book karna chahenge?"),
    "ur":            ("Book karana chahenge? Neeche time chunein 👇", "Book karana chahenge?"),
    "en":            ("Would you like to book? Tap a time below 👇", "Would you like to book it in?"),
}


# Two shapes so the bot never repeats itself: a first ask when we know nothing,
# and a follow-up that names what they gave and asks only for the missing part
# ({make} filled in). Keyed by language, with script variants for hi/ur.
# One question, with an example so they answer in full — the make+model is enough
# to price (sedan/SUV/luxury). We never ask for the year to quote; that only comes
# up later at booking.
_ASK_CAR = {
    "ar":            "بالتأكيد! ما هي سيارتك؟ (مثلاً تويوتا كامري أو نيسان باترول)",
    "hi_devanagari": "ज़रूर! कौन सी गाड़ी है? (जैसे Toyota Camry या Nissan Patrol)",
    "ur_arabic":     "ضرور! کون سی گاڑی ہے؟ (مثلاً Toyota Camry یا Nissan Patrol)",
    "hi":            "Zaroor! Kaunsi gaadi hai? (jaise Toyota Camry ya Nissan Patrol)",
    "ur":            "Zaroor! Kaun si gaari hai? (jaise Toyota Camry ya Nissan Patrol)",
    "en":            "Sure! Which car is it? (for example, Toyota Camry or Nissan Patrol)",
}
_ASK_MODEL = {
    "ar":            "أي موديل {make}؟",
    "hi_devanagari": "कौन सा {make} मॉडल है?",
    "ur_arabic":     "کون سا {make} ماڈل ہے؟",
    "hi":            "Kaunsa {make} model hai?",
    "ur":            "Kaun sa {make} model hai?",
    "en":            "Which {make} model is it?",
}


# Urdu-only letters (not in standard Arabic). Any of these means the message is
# Urdu, however the classifier tagged it.
_URDU_LETTERS = set("ٹڈڑںہھےیکگچپژ")


def _looks_urdu(message: str) -> bool:
    return any(ch in _URDU_LETTERS for ch in (message or ""))


# A tapped time button is always "<Weekday> <DD> <Mon>, HH:MM" (see slots.describe).
# When a customer taps one, the classifier sometimes mislabels it (symptom, because
# the car is still in context; or info). It is a BOOKING, full stop — detect it in
# code so a tapped time can never be re-interpreted and loop the picker.
_SLOT_PICK_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_SLOT_PICK_TOKENS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                     "oct", "nov", "dec", "mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _looks_like_slot_pick(message: str) -> bool:
    m = (message or "").lower()
    return bool(_SLOT_PICK_RE.search(m)) and any(t in m for t in _SLOT_PICK_TOKENS)


def _lang_key(language: str, script: str) -> str:
    if language == "ar":
        return "ar"
    if language == "hi":
        return "hi_devanagari" if script == "devanagari" else "hi"
    if language == "ur":
        return "ur_arabic" if script == "arabic" else "ur"
    return "en"


# Off-topic / nonsense ("do you sell pizza?", "lol", weather) — NOT a real
# garage question. A warm nudge back to cars, no handover, so the owner isn't
# pinged and the chat isn't muted over noise. (A genuine out-of-scope service
# question stays intent "other" and still hands over to a human.)
_OFF_SCOPE = {
    "ar":            "أنا هنا للمساعدة في سيارتك فقط — الأسعار والصيانة والحجز. ماذا تحتاج سيارتك؟",
    "hi_devanagari": "मैं सिर्फ़ आपकी गाड़ी में मदद कर सकता हूँ — दाम, सर्विस और बुकिंग। आपकी गाड़ी को क्या चाहिए?",
    "ur_arabic":     "میں صرف آپ کی گاڑی میں مدد کر سکتا ہوں — ریٹ، سروس اور بکنگ۔ آپ کی گاڑی کو کیا چاہیے؟",
    "hi":            "Main sirf aapki gaadi mein madad kar sakta hoon — daam, service aur booking. Aapki gaadi ko kya chahiye?",
    "ur":            "Main sirf aapki gaari mein madad kar sakta hoon — rates, service aur booking. Aapki gaari ko kya chahiye?",
    "en":            "I'm just here to help with your car — prices, service, and bookings. What does your car need?",
}


def _off_scope(language: str, script: str) -> str:
    return _OFF_SCOPE[_lang_key(language, script)]


_ASK_SERVICE = {
    "ar": "أي خدمة تريد معرفة سعرها؟ (مثلاً تغيير زيت، فرامل، بطارية)",
    "hi_devanagari": "किस सर्विस का दाम चाहिए? (जैसे ऑयल चेंज, ब्रेक, बैटरी)",
    "ur_arabic": "کس سروس کا ریٹ چاہیے؟ (مثلاً آئل چینج، بریک، بیٹری)",
    "hi": "Kaunsi service ka daam chahiye? (jaise oil change, brake, battery)",
    "ur": "Kaunsi service ka rate chahiye? (jaise oil change, brake, battery)",
    "en": "Which service would you like a price for? (e.g. oil change, brakes, battery)",
}


def _ask_service(language: str, script: str) -> str:
    return _ASK_SERVICE[_lang_key(language, script)]


# "Full service?", "what packages do you have?", "service is due" — the garage may
# not have a named package on its sheet. Rather than a dead handover, we let the
# ASSISTANT answer naturally (that is what the model is for): explain in general
# terms, list the jobs we CAN price, offer a free inspection. It may not say a
# price — the guard enforces that — but the words are the model's, not a script.
_MENU_WORDS = (
    "full service", "package", "maintenance", "service due", "service is due",
    "what do you offer", "what services", "which services", "your services",
    "فل سروس", "پیکیج", "مینٹیننس", "سروس کا وقت", "کیا خدمات", "کون سی خدمات",
    "کون سے پیکیج", "الصيانة", "الخدمات", "خدماتكم", "باقات",
)


def _wants_service_menu(message: str) -> bool:
    m = (message or "").lower()
    return any(w in m for w in _MENU_WORDS)


def _priced_service_list(sheet: dict[str, Any], language: str) -> str:
    """The names of the jobs the garage actually has prices for — for the model
    to weave into a natural reply."""
    names = []
    for s in (sheet.get("services") or []):
        prices = [v for v in (s.get("prices") or {}).values() if v and str(v).strip()]
        nm = s.get("name") or {}
        label = nm.get(language) or nm.get("en")
        if label and prices:
            names.append(label)
    return ", ".join(names)


def _ask_car(read: dict[str, Any], language: str, script: str) -> str:
    key = _lang_key(language, script)
    make = _as_text(read.get("car_make"), "").strip()
    if make:
        # They gave a make (or more) but we still can't pick a class — ask for the
        # missing part by name instead of repeating the same question.
        return _ASK_MODEL[key].format(make=make.title())
    return _ASK_CAR[key]


_LANG_NAMES = {"en": "English", "ar": "Arabic", "hi": "Hindi", "ur": "Urdu"}


def _language_directive(language: str, script: str) -> str:
    name = _LANG_NAMES.get(language, "English")
    if language in ("hi", "ur") and script != "devanagari" and script != "arabic":
        return ("Write the ENTIRE reply in %s using Latin/Roman letters (the way the "
                "customer wrote). Do not use any other language or script." % name)
    return "Write the ENTIRE reply in %s. Do not use any other language." % name


# The booking-time picker. Times are always shown as tappable buttons, never
# listed as text — a customer choosing should tap, not read a sentence.
_SLOT_ASK = {
    "ar": "أي وقت يناسبك؟ اختر من الأسفل، أو اكتب وقتاً آخر 👇",
    "hi_devanagari": "कौन सा समय ठीक है? नीचे चुनें, या कोई और समय लिख दें 👇",
    "ur_arabic": "کون سا وقت ٹھیک ہے؟ نیچے منتخب کریں، یا کوئی اور وقت لکھ دیں 👇",
    "hi": "Kaunsa time theek hai? Neeche tap karein, ya koi aur time likh dein 👇",
    "ur": "Kaun sa time theek hai? Neeche tap karein, ya koi aur time likh dein 👇",
    "en": "Which time suits you? Tap one below, or just type another time 👇",
}
_SLOT_TAKEN = {
    "ar": "هذا الوقت غير متاح.", "hi_devanagari": "वह समय उपलब्ध नहीं है।",
    "ur_arabic": "یہ وقت دستیاب نہیں۔", "hi": "Wo time available nahi hai.",
    "ur": "Wo time available nahi hai.", "en": "That time isn't free.",
}
# When the times are ALREADY on screen and the customer sends more (e.g. re-states
# the car), we don't repeat the whole "let's book an inspection" pitch — just a
# short nudge to the buttons already shown, so it never reads as if it ignored them.
_SLOT_NUDGE = {
    "ar": "اختر أحد الأوقات بالأعلى 👆 أو اكتب وقتاً آخر.",
    "hi_devanagari": "ऊपर दिए समय में से चुनें 👆 या कोई और समय लिख दें।",
    "ur_arabic": "اوپر دیے گئے اوقات میں سے کوئی منتخب کریں 👆 یا کوئی اور وقت لکھ دیں۔",
    "hi": "Upar diye gaye times mein se koi choose karein 👆 ya koi aur time likh dein.",
    "ur": "Upar diye gaye times mein se koi choose karein 👆 ya koi aur time likh dein.",
    "en": "Pick one of the times above 👆, or type another time.",
}
_SLOT_DAYFULL = {
    "ar": "لا يوجد موعد متاح في ذلك اليوم.", "hi_devanagari": "उस दिन कोई समय खाली नहीं है।",
    "ur_arabic": "اس دن کوئی وقت خالی نہیں۔", "hi": "Us din koi time free nahi hai.",
    "ur": "Us din koi time free nahi hai.", "en": "Nothing free on that day.",
}


# "What we don't service." A garage that only touches GCC-spec cars, or won't do
# bodywork, should say so UP FRONT — a customer's top complaint is being walked
# all the way to the end only to be turned away (a real Care review). The owner
# writes this line themselves; we surface it, we never invent a scope.
_RESTRICTION_NOTE = {
    "ar": "ملاحظة", "hi_devanagari": "ध्यान दें", "ur_arabic": "نوٹ",
    "hi": "Note", "ur": "Note", "en": "Please note",
}


def _restriction_text(info: dict[str, Any]) -> str | None:
    """The owner's own 'what we don't service' line, if set and not a TODO stub."""
    raw = _as_text(info.get("restrictions"), "").strip()
    if not raw or raw.lower() in _NULLISH or raw.upper().startswith("TODO"):
        return None
    return raw


def _already_stated(history: list[dict[str, str]] | None, text: str) -> bool:
    """Have we already sent this restriction earlier in the chat? Don't repeat it."""
    if not history or not text:
        return False
    needle = text.strip().lower()
    for turn in history:
        if turn.get("role") == "assistant" and needle in (turn.get("content") or "").lower():
            return True
    return False


# Words that mark a free-inspection offer, across the languages we reply in. If a
# recent assistant turn carried one, a service-less booking is that inspection.
_INSPECT_MARKERS = ("inspection", "فحص", "معاينة", "انسپیکشن", "इंस्पेक्शन")


def _is_inspection_context(history: list[dict[str, str]] | None) -> bool:
    """Did we just offer a free inspection? Then a booking with no named service
    is that inspection, not a prompt to ask which service."""
    if not history:
        return False
    for turn in history[-4:]:
        if turn.get("role") == "assistant":
            low = (turn.get("content") or "").lower()
            if any(m in low for m in _INSPECT_MARKERS):
                return True
    return False


def _recently_offered_slots(history: list[dict[str, str]] | None) -> bool:
    """Was the LAST thing we said a time picker (buttons already on screen)? If so,
    a follow-up shouldn't repeat the whole pitch — just nudge to those buttons.
    Every slot-ask ends with the 👇 marker, so that's the reliable tell."""
    if not history:
        return False
    for turn in reversed(history):
        if turn.get("role") == "assistant":
            return "👇" in (turn.get("content") or "")
    return False


def _restriction_note(info, language: str, script: str) -> str | None:
    """A tidy 'Please note: <what we don't service>' line in the customer's language.

    The lead-in is translated; the owner's scope text is shown verbatim (we must
    not paraphrase what a garage will or won't touch).
    """
    text = _restriction_text(info)
    if not text:
        return None
    return "%s: %s" % (_RESTRICTION_NOTE[_lang_key(language, script)], text)


def _restriction_fact(info: dict[str, Any]) -> str | None:
    """Give the composer the scope line, to state ONLY if the customer's request
    falls under it. Weaving it into a reply in the right language is exactly the
    kind of judgement the model is good at; the guard still blocks any price."""
    text = _restriction_text(info)
    if not text:
        return None
    return ("This garage does NOT service the following: \"%s\". If the customer's "
            "car or request clearly falls under this, tell them so clearly and early "
            "so they don't waste time; otherwise do not mention it." % text)


def _customer_booked_at(garage_id: str, customer_number: str, slot_utc) -> bool:
    """Does this customer already have a live booking at exactly this slot?"""
    from .db import Booking, SessionLocal
    with SessionLocal() as db:
        return db.query(Booking).filter(
            Booking.garage_id == garage_id,
            Booking.customer_number == customer_number,
            Booking.slot_start == slot_utc,
            Booking.status != "cancelled",
        ).first() is not None


# The service label written to the booking row / confirmation for a free
# inspection (keyed by language, not script — confirmations use language).
_INSPECT_NAME = {"en": "Free inspection", "ar": "فحص مجاني",
                 "hi": "Free inspection", "ur": "Free inspection"}

# A booking confirmation, built in code (never composed → never guard-blocked,
# and the time is shown exactly as the customer tapped it).
_CONFIRMED = {
    "ar": "تم تأكيد حجزك ✅",
    "hi_devanagari": "आपकी बुकिंग कन्फ़र्म हो गई ✅",
    "ur_arabic": "آپ کی بکنگ کنفرم ہو گئی ✅",
    "hi": "Aapki booking confirm ho gayi ✅",
    "ur": "Aap ki booking confirm ho gayi ✅",
    "en": "Your booking is confirmed ✅",
}


def _confirm_reply(row, info: dict[str, Any], language: str, script: str) -> "Reply":
    """A fixed-layout confirmation: one translated line, then the plain details
    (service, car, time, address, map). No model, so nothing to reword or block."""
    lines = [_CONFIRMED[_lang_key(language, script)]]
    head = row.service or "Booking"
    if row.car:
        head = "%s — %s" % (head, row.car)
    lines.append(head)
    lines.append(slots.describe(row.slot_start, info))
    if info.get("address") and "TODO" not in str(info.get("address")):
        lines.append(info["address"])
    maps = str(info.get("maps_link") or "")
    if maps.startswith("http"):
        lines.append(maps)
    return Reply(text="\n".join(lines), intent="booking", language=language, booking=row)


# Framing for a free-inspection time pick (symptom path). One warm line, then the
# tappable times follow from _SLOT_ASK.
_INSPECT_LEAD = {
    "ar": "لنحجز لك فحصاً مجانياً.",
    "hi_devanagari": "चलिए एक फ्री इंस्पेक्शन बुक कर लेते हैं।",
    "ur_arabic": "چلیں ایک فری انسپیکشن بک کر لیتے ہیں۔",
    "hi": "Chaliye ek free inspection book kar lete hain.",
    "ur": "Chalein ek free inspection book kar lete hain.",
    "en": "Let's book you a free inspection.",
}


def _slot_reply(garage, garage_id, info, now, language, script, prefer,
                asked_time=False, lead="", customer_number=None, nudge=False):
    """A time picker as tappable buttons (never text). Handoff if truly nothing free.

    Wording rules:
    * requested day has other times, but the one they asked isn't free -> "that time isn't free".
    * requested day is empty (closed/full) AND they genuinely named it -> "nothing free that day".
    * no day named (or a defaulted today the customer never asked for) -> no prefix, just offer.

    We pass `customer_number` so a slot the customer ALREADY holds is never
    offered — otherwise tapping it hits the double-book guard and the picker loops.
    """
    key = _lang_key(language, script)
    today = slots.to_local(now, info).date()
    day_options = (slots.next_available(garage_id, info, now, SLOTS_OFFERED, prefer=prefer,
                                        exclude_customer=customer_number) if prefer else [])

    prefix = ""
    if prefer is not None and day_options:
        options = day_options
        if asked_time:
            prefix = _SLOT_TAKEN[key]
    else:
        options = slots.next_available(garage_id, info, now, SLOTS_OFFERED,
                                       exclude_customer=customer_number)
        if prefer is not None and prefer > today:
            prefix = _SLOT_DAYFULL[key]          # a real future day that's full
        elif asked_time:
            prefix = _SLOT_TAKEN[key]            # they named a time that isn't free

    if not options:
        return _handoff(garage, "no slots available in the next two weeks", language, "booking")
    # If the times are already on screen and there's nothing new to say (no
    # "taken"/"day full" prefix), just nudge to them instead of repeating the pitch.
    if nudge and not prefix:
        text = _SLOT_NUDGE[key]
    else:
        text = " ".join(p for p in (lead, prefix, _SLOT_ASK[key]) if p)
    buttons = [(slots.describe(o, info), slots.describe(o, info)) for o in options[:3]]
    return Reply(text=text, intent="booking", language=language, slot_buttons=buttons)


def _book_question(language: str, script: str, has_slots: bool) -> str:
    if language == "ar":
        pair = _BOOK_Q["ar"]
    elif language == "hi":
        pair = _BOOK_Q["hi_devanagari"] if script == "devanagari" else _BOOK_Q["hi"]
    elif language == "ur":
        pair = _BOOK_Q["ur_arabic"] if script == "arabic" else _BOOK_Q["ur"]
    else:
        pair = _BOOK_Q["en"]
    return pair[0] if has_slots else pair[1]


def _price_reply(quote, car: str | None, language: str, script: str, has_slots: bool) -> str:
    """A price answer with a fixed, tidy layout — no model guesswork:
        <service> — <car>
        *<price>*
        <note, if any>
        <booking question>
    """
    head = quote.service_name
    if car:
        head = "%s — %s" % (head, car)
    lines = [head, "*%s*" % quote.display]
    if quote.notes:
        lines.append(quote.notes)
    lines.append(_book_question(language, script, has_slots))
    return "\n".join(lines)


def _handoff(garage: dict[str, Any], reason: str, language: str = "en",
             intent: str = "other", blocked: guard.Verdict | None = None) -> Reply:
    return Reply(
        text=handoff_line(garage, language),
        intent=intent,
        language=language,
        handoff_reason=reason,
        blocked=blocked,
    )


def build_reply(
    garage: dict[str, Any],
    message: str,
    history: list[dict[str, str]] | None = None,
    *,
    conversation_id: int | None = None,
    customer_number: str | None = None,
    now_utc: datetime | None = None,
    msg_type: str = "text",
    language_hint: str | None = None,
) -> Reply:
    info = garage.get("info") or {}
    sheet = garage.get("prices") or {}
    garage_id = garage.get("id") or "unknown"
    name = info.get("name") or garage_id
    now = now_utc or utcnow()

    # 0. can we even read it? -------------------------------------------------
    # A garage customer sends a photo of a part or a voice note describing a
    # noise more often than they type. Guessing at either would break rule 2.
    if msg_type in UNREADABLE or not (message or "").strip():
        # No text means no language to read, so answer in whatever they were
        # already being answered in.
        language = language_hint or "en"
        return Reply(
            text=MEDIA_ACK.get(language, MEDIA_ACK["en"]),
            intent=msg_type if msg_type in UNREADABLE else "empty",
            language=language,
            handoff_reason="cannot read %s" % UNREADABLE.get(msg_type, "that message"),
        )

    # 1. classify -------------------------------------------------------------
    try:
        read = _as_dict(classify(
            message,
            pricing.service_ids(sheet),
            history,
            today=slots.to_local(now, info),
            timezone=info.get("timezone") or slots.DEFAULT_TZ,
        ))
    except LLMUnavailable as exc:
        log.warning("classify failed, handing over: %s", exc)
        return _handoff(garage, "classifier unavailable")

    # A model asked for JSON returns JSON-shaped, not JSON-typed. "confidence":
    # "high" is a perfectly plausible thing for it to say, and float() on it
    # used to end the turn with an exception - which reaches the customer as
    # silence, the one outcome worse than handing over.
    language = _as_text(read.get("language"), "en")
    intent = _as_text(read.get("intent"), "other")
    confidence = _as_confidence(read.get("confidence"))

    # Language, corrected in code (the classifier is shaky on the shared script):
    # 1) Urdu is written in the same script as Arabic and gets mislabelled as
    #    Arabic. Urdu-only letters (ٹ ڈ ک گ ہ ے ی …) are a reliable tell.
    if language == "ar" and _looks_urdu(message):
        language = "ur"
        read["script"] = "arabic"
    # 2) A short reply — a one-word answer, a car, a tapped English slot title —
    #    must not flip a conversation's language. Keep the established one.
    if language_hint and language != language_hint and len((message or "").split()) <= 4:
        language = language_hint

    # A tapped time button is a BOOKING, whatever the classifier called it. This
    # stops a tapped slot from being re-read as a symptom and looping the picker.
    if _looks_like_slot_pick(message):
        intent = "booking"

    # A universal policy question ("quote before you start?", "how long?", "can I
    # walk in?", "send photos?") must be ANSWERED, not handed over — but the
    # classifier often mislabels these as price/booking, which short-circuit
    # below. So catch them here, in code, and route to the info answer. We stay
    # out of the way of a genuine service request (a named service being priced
    # or booked) and of a fault description (symptom → inspection covers "how
    # long" already).
    policy_topic = _guess_policy_topic(message)
    if policy_topic:
        named_service = bool(_as_text(read.get("service_id"), "")) and intent in ("price", "booking")
        # "Quote before you start?" and "can I send a photo/video?" are ALWAYS
        # policy questions — answer them even if the model thought it saw a
        # service or a symptom. "How long?" / "walk in?" defer to a genuine
        # service being priced/booked, or to a fault (symptom → inspection).
        force = policy_topic in ("quotation", "media") or (
            intent != "symptom" and not named_service)
        if force:
            intent = "info"
            read["info_topic"] = policy_topic

    # 2. resolve --------------------------------------------------------------
    quote: pricing.Quote | None = None
    made: Booking | None = None
    offered_slots: list = []
    quick_menu = False
    money_ok = False  # owner-authored info/FAQ may state a figure; the model still may not
    facts: list[str] = ["Garage: %s" % name]

    if intent == "symptom":
        # Rule 2: never diagnose. Collect the car, then book a free inspection.
        # The moment we HAVE the car, jump STRAIGHT to the tappable time picker —
        # do NOT let the composer improvise a "would you like a time?" question in
        # plain text (it did, and it left the customer with nothing to tap).
        script = _as_text(read.get("script"), "")
        if _car(read) and conversation_id is not None and customer_number is not None:
            return _slot_reply(garage, garage_id, info, now, language, script,
                               prefer=None, lead=_INSPECT_LEAD[_lang_key(language, script)],
                               customer_number=customer_number,
                               nudge=_recently_offered_slots(history))
        # No car yet (or no booking context): warmly ask for it and offer the
        # free inspection — the composer keeps this human, the guard keeps it safe.
        facts += [
            "The customer is describing a fault, not asking for a listed service.",
            "You may not name a cause and you may not give any price.",
            "Ask for make, model and year if they are missing, then offer a free inspection.",
        ]
        if read.get("symptom"):
            facts.append("What they described: %s" % read["symptom"])

    elif intent == "price":
        # A short, vague price message with no service ("how much?", "price?") —
        # ask which service.
        if not _as_text(read.get("service_id"), "") and len((message or "").split()) <= 3:
            return Reply(text=_ask_service(language, _as_text(read.get("script"), "")),
                         intent="price", language=language)
        quote = None
        try:
            quote = pricing.quote(
                sheet,
                read.get("service_id"),
                read.get("car_category"),
                make=read.get("car_make"),
                model=read.get("car_model"),
                language=language,
            )
        except pricing.NeedCar:
            # We know the service, just not the car. Ask for it — do NOT hand over.
            return Reply(
                text=_ask_car(read, language, _as_text(read.get("script"), "")),
                intent="price", language=language,
            )
        except pricing.NotOnSheet as exc:
            log.info("off-sheet price request: %s", exc)
            # It's car work we can't price off the fixed list (a full service, a
            # pre-purchase check, an RTA-fail repair, "what's urgent"). A cold
            # "advisor will call" is a dumb answer. Let the model answer NATURALLY
            # and offer a FREE INSPECTION so the team can quote it — no price, ever
            # (the guard enforces that). Non-car / genuinely out-of-scope asks
            # arrive as other/info intents, not here, so they still hand over.
            facts += [
                "The customer asked the price of car work that isn't a single fixed "
                "item on our price list (e.g. a full service, a pre-purchase check, "
                "an RTA-fail repair, or which work is urgent).",
                "Answer naturally and warmly in one or two short lines. You MUST NOT "
                "state any price or number.",
                "Offer to book a FREE inspection so the team can look and give an exact quote.",
            ]
            if _wants_service_menu(message):
                facts.append("You may also mention the jobs we can price: %s."
                             % (_priced_service_list(sheet, language) or "our listed services"))
            # quote stays None → falls through to the composer below (money blocked).

        # The quote resolved. Only now does low confidence matter: it means the
        # wrong service may have matched, so don't send a price — hand over. (A
        # missing car never reaches here; it asked for the car above.)
        if quote is not None and confidence < CONFIDENCE_FLOOR:
            return _handoff(garage, "low confidence on service or car", language, intent)

        # The price answer is built in code (exact price, tidy layout, right
        # language). We quote and ASK "would you like to book?" — but we do NOT
        # dump the calendar on every quote; that reads pushy. The times appear
        # only when they say yes (the booking turn), which feels natural.
        if quote is not None:
            script = _as_text(read.get("script"), "")
            text = _price_reply(quote, _car(read), language, script, has_slots=False)
            # If the garage limits what it services, say so with the very first
            # quote (once per chat) — better now than after they've booked.
            note = _restriction_note(info, language, script)
            if note and not _already_stated(history, _restriction_text(info)):
                text = "%s\n\n%s" % (note, text)
            return Reply(text=text, intent="price", language=language, quote=quote)
        # else: a package/"what do you offer" ask — facts are set above; fall
        # through to the composer for a natural, price-free answer.

    elif intent == "booking":
        outcome = _handle_booking(
            garage, garage_id, info, sheet, read, language,
            conversation_id, customer_number, now, history,
        )
        if isinstance(outcome, Reply):
            return outcome
        extra, made = outcome
        facts += extra

    elif intent == "info":
        # Order matters: the classifier's own topic, then the owner's custom FAQ
        # answers (they beat a generic guess), then a keyword guess as last resort.
        resolved = (
            (_info_facts(info, read.get("info_topic")) if read.get("info_topic") else [])
            or _faq_facts(garage, message)
            or _info_facts(info, _guess_info_topic(message))
        )
        if not resolved:
            return _handoff(garage, "info topic not in the garage files", language, intent)
        facts += resolved
        money_ok = True

    elif intent == "greeting":
        facts.append("Greet them in one short line. Do not list options in words; "
                     "buttons will be shown below your message.")
        quick_menu = True

    elif intent == "irrelevant":
        # Off-topic / nonsense, nothing to do with cars or this garage. A warm
        # redirect, not a handover — the owner is not pinged over noise.
        return Reply(text=_off_scope(language, _as_text(read.get("script"), "")),
                     intent="irrelevant", language=language)

    elif intent == "smalltalk":
        # A thanks, an ok, a pleasantry. Answer like a friendly person would - but
        # a price, a time, a promise or a fact is off-limits, so the guard keeps
        # this to warmth only. No handover: this does not need the owner.
        facts.append("The customer made a conversational remark, not a request. "
                     "Reply in ONE short, warm line in their language. Do not state any "
                     "price, time, fact, or promise. If it seems they may still need "
                     "something, end by asking what they need for their car.")

    else:
        # Last chance before a handover: it may be a plain info question the
        # classifier mislabelled as "other" (a very common miss). FAQ first.
        topic = _guess_info_topic(message)
        rescued = _faq_facts(garage, message) or (_info_facts(info, topic) if topic else [])
        if not rescued:
            return _handoff(garage, "intent not handled in v1: %s" % intent, language, intent)
        facts += rescued
        money_ok = True

    # 3. compose --------------------------------------------------------------
    # If the garage limits its scope ("GCC-spec only", "no bodywork"), let the
    # composer raise it — but only when the customer's request actually falls
    # under it. On every other turn it stays quiet.
    restriction = _restriction_fact(info)
    if restriction and intent in ("symptom", "booking", "info", "greeting", "other"):
        facts.append(restriction)

    # Force the reply language from the classifier's read (which is reliable),
    # rather than letting the composer guess it from the message — that guess was
    # turning plain English into Roman Urdu.
    facts.insert(0, _language_directive(language, _as_text(read.get("script"), "")))

    try:
        draft = compose(name, "\n".join("- %s" % f for f in facts), message, history)
    except LLMUnavailable as exc:
        log.warning("compose failed, handing over: %s", exc)
        return _handoff(garage, "composer unavailable", language, intent)

    # 4. guard ----------------------------------------------------------------
    # On a turn that carries a price, the customer's own message stops being a
    # source of allowed numbers. Otherwise "my friend said you did it for 450"
    # would hand the bot a price to repeat, and it would look exactly like a
    # quote off the sheet.
    allowed = (
        guard.allowed_numbers(*facts)
        if quote is not None
        else guard.allowed_numbers(*facts, message)
    )
    text, verdict = guard.enforce(
        draft,
        allowed=allowed,
        money_allowed=quote is not None or money_ok,
        fallback=handoff_line(garage, language),
    )
    if not verdict.ok:
        # Loud on purpose. A blocked reply means the composer tried to send
        # something the facts did not support, and somebody should read it.
        log.error("BLOCKED reply (%s) offending=%s draft=%r",
                  verdict.reason, verdict.offending, draft)
        return _handoff(garage, "blocked: %s" % verdict.reason, language, intent, verdict)

    slot_buttons = [(slots.describe(x, info), slots.describe(x, info)) for x in offered_slots[:3]]
    return Reply(
        text=text, intent=intent, language=language, quote=quote, booking=made,
        slot_buttons=slot_buttons, quick_menu=quick_menu,
    )


# --------------------------------------------------------------------- booking

def _handle_booking(
    garage, garage_id, info, sheet, read, language,
    conversation_id, customer_number, now, history=None,
) -> Reply | tuple[list[str], Booking | None]:
    """Gather what a booking needs, then write it. Returns facts, or a handoff."""
    if conversation_id is None or customer_number is None:
        return _handoff(garage, "no conversation context for booking", language, "booking")

    draft = booking.Draft(
        customer_name=read.get("customer_name") or None,
        car=_car(read),
    )

    # If we already offered a FREE INSPECTION (the symptom path), this booking IS
    # that inspection — even if the classifier now guesses a service from the
    # earlier symptom ("brake pedal soft" -> it would say brake_repair). The
    # inspection context WINS, so a free inspection never silently becomes a paid
    # job. Only when there was no inspection offered do we honour a named service.
    service_id = _as_text(read.get("service_id"), "")
    if _is_inspection_context(history):
        draft.is_inspection = True
        draft.service_name = _INSPECT_NAME.get(language, _INSPECT_NAME["en"])
    elif service_id:
        try:
            svc = pricing.find_service(sheet, service_id)
        except pricing.NotOnSheet as exc:
            # They want something the garage has not listed. A human decides.
            return _handoff(garage, "booking off sheet: %s" % exc, language, "booking")
        names = svc.get("name") or {}
        draft.service_id = service_id
        draft.service_name = names.get(language) or names.get("en") or service_id
    # else: a bare "book me in" with no service — missing() asks which service.

    wanted_date = _as_date(read.get("preferred_date"))
    wanted_time = _as_time(read.get("preferred_time"))
    draft.preferred_day = wanted_date

    asked_for_a_slot = wanted_date is not None and wanted_time is not None
    if asked_for_a_slot:
        candidate = slots.to_utc(datetime.combine(wanted_date, wanted_time), info)
        # Guard against the classifier carrying a time from an earlier booking in
        # the same chat: if this customer already has a booking at that exact slot,
        # it's almost certainly stale context, not a fresh choice — so ask for the
        # time instead of silently booking a second service at the same hour.
        if (slots.is_bookable(garage_id, info, candidate, now)
                and not _customer_booked_at(garage_id, customer_number, candidate)):
            draft.slot_utc = candidate

    missing = draft.missing()

    # everything gathered: write it
    if not missing:
        try:
            row = booking.confirm(garage_id, info, conversation_id, customer_number, draft, now)
        except booking.SlotGone:
            log.info("slot went while confirming for %s", customer_number)
            return _slot_reply(garage, garage_id, info, now, language,
                               _as_text(read.get("script"), ""), wanted_date, asked_time=True,
                               customer_number=customer_number)
        # Confirmation is built in code, NOT composed — the composer used to
        # reword the time ("15:00" -> "3 بجے") and the money-guard then blocked
        # the whole reply as an unapproved number, turning a good booking into a
        # handover. A confirmation carries no price, so it never needs the model.
        return _confirm_reply(row, info, language, _as_text(read.get("script"), ""))

    # still gathering: ask for exactly one thing
    field, label = missing[0]

    # The time picker is always buttons — return it directly, skip the composer.
    if field == "slot":
        script = _as_text(read.get("script"), "")
        return _slot_reply(garage, garage_id, info, now, language, script, wanted_date,
                           asked_time=wanted_time is not None, customer_number=customer_number,
                           nudge=_recently_offered_slots(history))

    # everything else (name, car, service) is a short text question via the composer.
    facts = ["The customer is booking. This is what is known so far:"]
    facts += _draft_lines(draft, info)
    facts.append("Ask only for %s. One question, nothing else, no summary." % label)
    return facts, None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


# The model sometimes fills a field with the literal string "null"/"none"/"N/A"
# instead of a real JSON null. Treat those as empty so they never leak into a
# reply ("Got it, Null!").
_NULLISH = {"null", "none", "n/a", "na", "nil", "-", "undefined", "unknown"}


def _as_text(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        s = value.strip()
        if s and s.lower() not in _NULLISH:
            return s
    return fallback


def _as_confidence(value: Any) -> float:
    """Anything unreadable means "not confident", which means hand over."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        log.info("classifier returned confidence=%r; treating as 0", value)
        return 0.0


def _car(read: dict[str, Any]) -> str | None:
    parts = [_as_text(read.get("car_make"), ""), _as_text(read.get("car_model"), ""),
             _as_text(read.get("car_year"), "")]
    # De-duplicate words so a make==model read ("Patrol"/"Patrol") doesn't print twice.
    words: list[str] = []
    for p in parts:
        for w in p.split():
            if w.lower() not in {x.lower() for x in words}:
                words.append(w)
    return " ".join(words) or None


def _as_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _as_time(value: Any) -> time | None:
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _draft_lines(draft: booking.Draft, info: dict[str, Any]) -> list[str]:
    out = []
    if draft.service_name:
        out.append("Service: %s" % draft.service_name)
    if draft.car:
        out.append("Car: %s" % draft.car)
    if draft.customer_name:
        out.append("Name: %s" % draft.customer_name)
    if draft.slot_utc:
        out.append("When: %s" % slots.describe(draft.slot_utc, info))
    return out or ["Nothing yet."]


# ------------------------------------------------------------------------ info

def _faq_facts(garage: dict[str, Any], message: str) -> list[str]:
    """Answer from the owner's own common-questions list, if one matches.

    The owner wrote both the trigger words and the answer on the setup page, so
    this is his voice, not the model's - served as a fact the composer must use.
    """
    msg = (message or "").lower()
    for entry in ((garage.get("faq") or {}).get("faqs") or []):
        triggers = entry.get("q") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        if any(t and t.lower() in msg for t in triggers):
            answer = entry.get("a")
            answer = answer.get("en") if isinstance(answer, dict) else answer
            if answer:
                return ["Answer this exactly, in the customer's language: %s" % answer]
    return []


# Keyword fallback so common questions answer even when the classifier fails to
# tag the topic (or mislabels the whole message as "other"). Kept broad and
# multilingual-ish; it only ever selects which owner-provided fact to read.
_INFO_KEYWORDS = {
    "hours": ["open", "close", "closing", "timing", "what time", "hours", "working",
              "khula", "khulta", "waqt", "kitne baje", "kab tak", "ساعات", "الدوام", "متى تفتح",
              "کتنے بجے", "کھلتے", "کھلتا", "بند ہوتے", "اوقات", "ٹائمنگ"],
    "location": ["where", "location", "address", "located", "find you", "direction",
                 "map", "kahan", "kahaan", "pata", "وين", "اين", "العنوان", "الموقع",
                 "کہاں", "پتہ", "پتا", "لوکیشن", "ایڈریس"],
    "payment": ["card", "cash", "pay ", "payment", "apple pay", "visa", "mastercard",
                "installment", "instalment", "bank transfer", "الدفع", "كاش", "بطاقة",
                "کارڈ", "کیش", "قسط", "قسطوں", "ادائیگی", "بینک ٹرانسفر"],
    "warranty": ["warranty", "guarantee", "guaranty", "zamanat", "ضمان",
                 "وارنٹی", "گارنٹی", "ضمانت", "زمانت"],
    "pickup": ["pick up", "pickup", "pick-up", "collect", "recovery", "tow", "سحب", "استلام",
               "پک اپ", "گاڑی لے", "لینے آ", "ڈیلیوری", "پہنچا"],
    # Universal policy answers — true for every garage, so they carry a safe
    # built-in reply instead of handing over. Keep the triggers narrow so a price
    # or symptom question is never pulled in here.
    "quotation": ["quotation", "quote before", "before starting", "before you start",
                  "estimate first", "inclusive of", "include vat", "including vat",
                  "with vat", "final price", "price before"],
    "appointment": ["appointment", "book first", "walk in", "walk-in", "come directly",
                    "come straight", "without booking", "do i need to book", "need to book"],
    "turnaround": ["how long", "how many days", "finish", "complete", "done today",
                   "ready today", "same day", "same-day", "take long", "by today"],
    "media": ["photo", "photos", "picture", "pictures", "pics", "video", "videos"],
}


def _guess_info_topic(message: str) -> str | None:
    m = (message or "").lower()
    for topic, words in _INFO_KEYWORDS.items():
        if any(w in m for w in words):
            return topic
    return None


# TIGHT triggers for the universal policy answers, used to catch these BEFORE the
# price/booking dispatch — because the classifier often tags "quotation before
# starting?" or "how long will it take?" as price/booking, which would hand over
# or ask "which service" instead of just answering. Kept to process-phrases (not
# bare "quote"/"appointment") so a real service request is never pulled in here.
_POLICY_KEYWORDS = {
    "quotation": ["before starting", "before you start", "before any work", "before repair",
                  "quotation before", "quote before", "inclusive of", "include vat",
                  "including vat", "with vat", "final price", "is the price final",
                  # Urdu: "check first, tell total, THEN start the work"
                  "پھر کام شروع", "شروع کرنے سے پہلے", "کرنے سے پہلے", "پہلے خرچہ", "ٹوٹل خرچہ بتا",
                  # Arabic
                  "قبل البدء", "قبل أن تبدأ", "السعر النهائي", "شامل"],
    "appointment": ["need an appointment", "need appointment", "do i need to book",
                    "need to book", "walk in", "walk-in", "come directly", "come straight",
                    "without appointment", "without booking", "appointment or",
                    # Urdu
                    "اپائنٹمنٹ", "بغیر اپائنٹمنٹ", "سیدھا آ", "موعد"],
    "turnaround": ["how long", "how many days", "finish", "complete", "done today",
                   "ready today", "ready by", "same day", "same-day", "take long",
                   "by today", "how soon",
                   # Urdu: "how long / by when will it be ready / when do I get it back"
                   "کب تک مل", "کب تک واپس", "کب تیار", "کب ملے گی", "کتنی دیر", "کتنا وقت لگے",
                   # Arabic
                   "كم يستغرق", "كم من الوقت", "جاهزة اليوم"],
    "media": ["photo", "photos", "picture", "pictures", "pics", "video", "videos",
              # Urdu / Arabic
              "ویڈیو", "تصویر", "فوٹو", "فيديو", "صورة"],
}


def _guess_policy_topic(message: str) -> str | None:
    m = (message or "").lower()
    for topic, words in _POLICY_KEYWORDS.items():
        if any(w in m for w in words):
            return topic
    return None


def _info_facts(info: dict[str, Any], topic: str | None) -> list[str]:
    """Answers that are not prices, straight out of info.yaml."""
    if topic == "hours":
        hours = info.get("hours") or {}
        lines = []
        for day, window in hours.items():
            lines.append("%s: %s" % (day, "closed" if not window else "%s to %s" % tuple(window)))
        return ["Opening hours:\n%s" % "\n".join(lines)] if lines else []

    if topic == "location":
        out = []
        if info.get("address"):
            out.append("Address: %s" % info["address"])
        if info.get("maps_link"):
            out.append("Maps link to send: %s" % info["maps_link"])
        return out

    if topic == "payment":
        methods = info.get("payment_methods") or []
        return ["Payment accepted: %s" % ", ".join(methods)] if methods else []

    if topic == "warranty":
        return ["Warranty: %s" % info["warranty"]] if info.get("warranty") else []

    if topic == "pickup":
        if not info.get("pickup_available"):
            return ["Pickup is not offered."] if "pickup_available" in info else []
        out = ["Pickup is available."]
        if info.get("pickup_notes"):
            out.append("Pickup details: %s" % info["pickup_notes"])
        return out

    # --- universal policy answers (true for any garage; never a price) --------
    if topic == "quotation":
        return ["Reassure them: they always get a price before any work begins. "
                "If the job is on our list you give the price now; for anything else "
                "we do a free inspection first and then give an exact quote covering "
                "parts, labour and VAT. Never invent a number — just this promise."]

    if topic == "appointment":
        return ["Tell them they can book a time right here in the chat, or simply "
                "come in during opening hours — both are fine. Offer to book them in."]

    if topic == "turnaround":
        return ["Explain it depends on the job, and that once the car is inspected "
                "we'll tell them exactly how long it takes and whether it's same-day. "
                "Do not promise a specific time. Offer to book a free inspection."]

    if topic == "media":
        return ["Yes — invite them to send a photo or a short video here so the team "
                "can take a look. Do not diagnose from it; use it to book them in."]

    return []
