# -*- coding: utf-8 -*-
"""Full OBJECTIVE audit: run every question through the REAL engine/classifier
against Care, each a FRESH chat, plus the two booking flows (tapping the real
button). Verdict per item is computed IN CODE against the rules — not opinion."""
import re, itertools
from app import engine, garages
from app.db import init_db, utcnow
init_db(); g = garages.load("care")
cid = itertools.count(30000)

INSP = ("معائنہ", "انسپیکشن", "inspection", "فحص", "جانچ", "معاينة")
CARASK = ("ماڈل", "میک", "make", "model", "برانڈ", "سال", "year", "گاڑی کا", "کار کا")
PRICE_RE = re.compile(r"\bAED\b|\*\s*\d{2,4}\s*\*|درہم|dirham", re.I)

def run(seq):
    n = next(cid); hist = []; hint = None; trail = []
    for msg in seq:
        if msg == "__TAP__":
            btns = trail[-1]["buttons"] if trail else []
            if not btns:
                trail.append({"you": "__TAP__", "bot": "(NO BUTTON TO TAP)", "intent": "none",
                              "lang": hint, "buttons": [], "booked": False}); continue
            msg = btns[0]
        r = engine.build_reply(g, msg, hist, conversation_id=n, customer_number="a%d" % n,
                               now_utc=utcnow(), msg_type="text", language_hint=hint)
        hint = r.language or hint
        trail.append({"you": msg, "bot": r.text, "intent": ("handover" if r.is_handoff else r.intent),
                      "lang": r.language, "buttons": [t for t, _ in r.slot_buttons], "booked": bool(r.booking)})
        hist += [{"role": "user", "content": msg}, {"role": "assistant", "content": r.text}]
    return trail

def has_price(text):
    return bool(PRICE_RE.search(text or ""))

def verdict(item):
    cat, trail = item["cat"], item["trail"]
    last = trail[-1]; allbot = " ".join(t["bot"] for t in trail)
    # language: every input here is Urdu -> expect ur
    if last["lang"] != "ur":
        return "FAIL", "replied in '%s', expected Urdu" % last["lang"]
    if cat == "price-exact":
        exp = item["expect"]
        return ("PASS", "quoted %s" % exp) if exp in allbot else ("FAIL", "expected price %s not found" % exp)
    if cat == "symptom":
        if last["intent"] == "handover": return "FAIL", "symptom handed over instead of inspection"
        if has_price(allbot): return "FAIL", "a symptom must not carry a price"
        if any(w in allbot for w in INSP) or any(w in allbot for w in CARASK): return "PASS", "asks car / free inspection"
        return "WARN", "no inspection/car ask detected"
    if cat in ("policy", "pickup", "media"):
        if last["intent"] == "handover": return "WARN", "handed over (could be answered)"
        if has_price(allbot): return "FAIL", "policy answer leaked a price"
        return "PASS", "answered, no price"
    if cat in ("price", "scope", "advice", "complaint"):
        if has_price(allbot): return "FAIL", "invented/leaked a price"
        return ("WARN", "handover (ok, but check if natural)") if last["intent"] == "handover" else ("PASS", "answered, no invented price")
    if cat == "flow-inspection":
        if not last["booked"]: return "FAIL", "did not confirm the inspection"
        return ("PASS", "confirmed inspection") if not has_price(allbot) else ("FAIL", "price leaked in flow")
    if cat == "flow-service":
        return ("PASS", "confirmed booking") if last["booked"] else ("FAIL", "did not confirm the booking")
    return "WARN", "uncategorised"

URDU = [
 (1,"price","السلام علیکم، ٹویوٹا کرولا کی فل سروس کتنے میں ہوگی؟"),
 (2,"price","میری گاڑی کی سروس کا وقت ہوگیا ہے۔ آپ کے پاس کون سے پیکیجز ہیں؟"),
 (3,"price","اگر میں انجن آئل خود لے آؤں تو صرف لیبر چارجز کتنے ہوں گے؟"),
 (4,"symptom","گاڑی چلتے ہوئے اے سی ٹھنڈا کرتا ہے، لیکن رکنے پر گرم ہوا آنے لگتی ہے۔"),
 (5,"price","اے سی کی گیس کم ہے یا کہیں لیک ہے، یہ چیک کرنے کے کتنے پیسے ہوں گے؟"),
 (6,"symptom","صبح گاڑی اسٹارٹ کرتے وقت عجیب سی آواز آتی ہے۔"),
 (7,"symptom","میری گاڑی دو تین بار کوشش کرنے کے بعد اسٹارٹ ہوتی ہے۔ چیک کر سکتے ہیں؟"),
 (8,"symptom","بیٹری بار بار ڈاؤن ہو جاتی ہے۔ بیٹری خراب ہے یا کوئی اور مسئلہ ہے؟"),
 (9,"symptom","ٹریفک میں پھنسنے پر گاڑی کا ٹمپریچر بڑھنے لگتا ہے۔"),
 (10,"symptom","گاڑی کے نیچے پانی نظر آ رہا ہے۔ کیا یہ نارمل ہے؟"),
 (11,"symptom","سو کی اسپیڈ پر گاڑی کانپنے لگتی ہے۔"),
 (12,"symptom","اسٹیئرنگ موڑتے وقت ٹک ٹک کی آواز آتی ہے۔"),
 (13,"symptom","بریک کا پیڈل نرم لگ رہا ہے۔ چیک کر دیں گے؟"),
 (14,"symptom","ابھی بریک تبدیل کروائے ہیں، لیکن آواز اب بھی آ رہی ہے۔"),
 (15,"symptom","گیئر لگاتے وقت جھٹکا آتا ہے، خاص طور پر ریورس میں۔"),
 (16,"symptom","دوسری گیراج سے انجن کی لائٹ بند کروائی تھی، لیکن دوبارہ آ گئی ہے۔"),
 (17,"symptom","میری گاڑی آج کل پیٹرول بہت زیادہ کھا رہی ہے۔"),
 (18,"symptom","گاڑی میں بہت جھٹکے لگتے ہیں۔ سسپنشن چیک کر سکتے ہیں؟"),
 (19,"symptom","ایک ٹائر کی ہوا بار بار کم ہو جاتی ہے۔ پنکچر چیک کر دیں گے؟"),
 (20,"scope","میں استعمال شدہ گاڑی خرید رہا ہوں۔ کیا آپ چیک کرکے رپورٹ دے سکتے ہیں؟"),
 (21,"scope","میری گاڑی آر ٹی اے ٹیسٹ میں فیل ہوگئی ہے۔ ضروری کام کا خرچہ بتا سکتے ہیں؟"),
 (22,"scope","اوریجنل اور آفٹر مارکیٹ پارٹس، دونوں کی قیمت بتا دیں۔"),
 (23,"scope","دوسری گیراج نے یہ کوٹیشن دیا ہے۔ آپ دیکھ کر اپنا ریٹ بتا سکتے ہیں؟"),
 (24,"policy","پہلے گاڑی چیک کرکے ٹوٹل خرچہ بتا دیں، پھر کام شروع کیجیے گا۔"),
 (25,"advice","کون سا کام فوراً کروانا ضروری ہے اور کون سا بعد میں کروا سکتا ہوں؟"),
 (26,"pickup","کیا آپ میرے آفس سے گاڑی لے کر آج ہی واپس دے سکتے ہیں؟"),
 (27,"scope","کیا آپ کا مکینک میری لوکیشن پر آ کر گاڑی چیک کر سکتا ہے؟"),
 (28,"policy","اگر صبح گاڑی دے دوں تو کب تک واپس مل جائے گی؟"),
 (29,"complaint","پچھلے ہفتے یہی کام کروایا تھا، لیکن مسئلہ دوبارہ آ گیا ہے۔"),
 (30,"media","گاڑی لانے سے پہلے آواز کی ویڈیو بھیج دوں؟"),
]
items = []
for _id, cat, q in URDU:
    items.append({"id": _id, "cat": cat, "trail": run([q])})
items.append({"id": "P-oil", "cat": "price-exact", "expect": "249", "trail": run(["ٹویوٹا کیمری کے آئل چینج کی قیمت؟"])})
items.append({"id": "P-batt", "cat": "price-exact", "expect": "399", "trail": run(["نسان پٹرول کی بیٹری کتنے کی ہے؟"])})
items.append({"id": "F-insp", "cat": "flow-inspection", "trail": run(["میری گاڑی زیادہ گرم ہو رہی ہے", "ٹویوٹا کرولا 2019", "__TAP__"])})
items.append({"id": "F-tyre", "cat": "flow-service", "trail": run(["کرولا کی ٹائر سروس کتنی ہے؟", "جی ہاں بک کر دیں", "__TAP__"])})

npass = nwarn = nfail = 0
lines = []
for it in items:
    v, why = verdict(it)
    npass += v == "PASS"; nwarn += v == "WARN"; nfail += v == "FAIL"
    last = it["trail"][-1]
    lines.append("%-6s %-15s %-4s  %s  | %s" % (str(it["id"]), it["cat"], v, why, last["bot"].replace(chr(10), " ")[:70]))

print("================= AUDIT RESULT =================")
print("PASS=%d  WARN=%d  FAIL=%d   (of %d)" % (npass, nwarn, nfail, len(items)))
print("------------------------------------------------")
for ln in lines:
    print(ln)
print("------------------------------------------------")
if nfail:
    print("FAILURES:")
    for it in items:
        v, why = verdict(it)
        if v == "FAIL":
            print("  [%s] %s -> %s" % (it["id"], why, it["trail"][-1]["bot"].replace(chr(10), " ")[:120]))
