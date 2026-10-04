# -*- coding: utf-8 -*-
"""END-TO-END GATE: run full conversations to completion in every language, tapping
the ACTUAL buttons the bot offers, and ASSERT the end state. Real classifier, Care,
throwaway DB. Prints a PASS/FAIL matrix; any FAIL is a real bug to fix."""
import itertools
from app import engine, garages
from app.db import init_db, utcnow
init_db(); g = garages.load("care")
cid = itertools.count(5000)
fails = []

def step(msg, hist, num, hint, tap=None):
    m = tap or msg
    r = engine.build_reply(g, m, hist, conversation_id=num, customer_number="g%d" % num,
                           now_utc=utcnow(), msg_type="text", language_hint=hint)
    hist += [{"role": "user", "content": m}, {"role": "assistant", "content": r.text}]
    return r

def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  <<< " + detail))
    if not cond:
        fails.append(name + " :: " + detail)

def inspection_flow(lang, symptom, car):
    n = next(cid); hist = []; hint = None
    print("\n[%s] symptom -> car -> tap -> CONFIRM FREE INSPECTION" % lang)
    r = step(symptom, hist, n, hint); hint = r.language or hint
    check("%s symptom not handover" % lang, not r.is_handoff, r.text[:60])
    r = step(car, hist, n, hint); hint = r.language or hint
    check("%s car -> inspection buttons" % lang, bool(r.slot_buttons), "(%s) %s" % (r.intent, r.text[:60]))
    if not r.slot_buttons:
        return
    r = step(None, hist, n, hint, tap=r.slot_buttons[0][0]); hint = r.language or hint
    ok = (r.booking is not None) and (not r.is_handoff)
    svc = (r.booking.service if r.booking else "") or ""
    check("%s tap -> CONFIRMED" % lang, ok, "(%s) %s" % (r.intent, r.text[:70]))
    is_insp = ("inspection" in svc.lower()) or ("فحص" in svc) or ("معائنہ" in svc) or ("इंस्पेक्शन" in svc)
    check("%s booked = free inspection" % lang, is_insp, "service=%r" % svc)

def price_flow(lang, price_msg, yes_msg):
    n = next(cid); hist = []; hint = None
    print("\n[%s] price -> yes -> tap -> CONFIRM SERVICE" % lang)
    r = step(price_msg, hist, n, hint); hint = r.language or hint
    check("%s price quoted" % lang, (r.quote is not None) and not r.is_handoff, "(%s) %s" % (r.intent, r.text[:60]))
    r = step(yes_msg, hist, n, hint); hint = r.language or hint
    check("%s yes -> time buttons" % lang, bool(r.slot_buttons), "(%s) %s" % (r.intent, r.text[:60]))
    if not r.slot_buttons:
        return
    r = step(None, hist, n, hint, tap=r.slot_buttons[0][0]); hint = r.language or hint
    check("%s tap -> CONFIRMED (not blocked)" % lang, (r.booking is not None) and not r.is_handoff,
          "(%s) %s" % (r.intent, r.text[:70]))

LANGS = [
 ("EN", "My engine is overheating badly", "Toyota Corolla 2019",
        "How much for tyre service on a Corolla?", "Yes please book it"),
 ("AR", "سيارتي ترتفع حرارتها بشدة", "تويوتا كورولا 2019",
        "كم سعر خدمة الإطارات لكورولا؟", "نعم احجز لي"),
 ("UR-roman", "meri gaari bohat overheat ho rahi hai", "Toyota Corolla 2019",
        "corolla ki tyre service kitni hai?", "haan book kar do"),
 ("UR-script", "میری گاڑی بہت زیادہ گرم ہو رہی ہے", "ٹویوٹا کرولا 2019",
        "کرولا کی ٹائر سروس کتنی ہے؟", "جی ہاں بک کر دیں"),
 ("HI", "मेरी गाड़ी बहुत ओवरहीट हो रही है", "टोयोटा कोरोला 2019",
        "कोरोला की टायर सर्विस कितने की है?", "हाँ बुक कर दो"),
]
for lang, sym, car, price, yes in LANGS:
    inspection_flow(lang, sym, car)
    price_flow(lang, price, yes)

print("\n==================== RESULT ====================")
print("ALL GREEN" if not fails else "FAILURES (%d):" % len(fails))
for f in fails:
    print("  - " + f)
