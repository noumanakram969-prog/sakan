# Submitting the templates — paste-ready

Twelve submissions: four templates × three languages. About twenty minutes.

## When

**Straight after Care's number is connected — not before.**

Templates belong to a WhatsApp Business Account, and Care's account does not exist until his number
is onboarded. A template approved against a test number does not carry across. So this is the first
thing you do once the connection is confirmed, sitting in the car outside if need be.

Approval takes about a day. Until it comes through, reminders and follow-ups stay silent and
everything else — prices, bookings, handoffs, owner alerts, the evening summary — works normally.
The pilot does not wait for this; it just starts without reminders for a day or two.

## Where

**Meta Business Manager → WhatsApp Manager → Message templates → Create template.**

Pick Care's WhatsApp Business Account first — templates belong to an account, not to you, so
submitting against the wrong one puts them somewhere they will never be used.

## Fields the form asks for

| Field | What to put |
|---|---|
| Name | exactly as written below — lowercase, underscores, no spaces |
| Category | **UTILITY** or **MARKETING** as marked. Getting this wrong is the usual rejection |
| Language | English / Arabic / Hindi — submit the same name three times, once per language |
| Header | leave empty for all four |
| Body | the block below, `{{1}}` placeholders included |
| Footer | leave empty |
| Buttons | none |
| Samples | the form will ask for an example value per variable — use the samples given |

## What gets them rejected

- A **UTILITY** template that reads like an advert. "Reminder of your appointment" is utility;
  "Book now and save" is not.
- A variable at the very **start or end** of the body, or two variables side by side.
- Sample values left blank, or samples that do not match the variable's meaning.
- Promotional wording, prices, or a URL in a utility template.

If one is rejected, the reason is shown in WhatsApp Manager. Fix and resubmit — it does not affect
the others.

## After approval

Nothing to change in the code. The names below already match
`garages/care/info.yaml`. If Meta makes you rename one, update it there and nowhere else.

---

# 1. booking_reminder_day_before

**Category: UTILITY** — sent the evening before an appointment.

### English
```
Hi {{1}}, reminder of your appointment at {{2}} tomorrow at {{3}} for {{4}}.
Reply here if you need to change the time.
```
Samples: `{{1}}` Ahmed · `{{2}}` Care Auto Repair · `{{3}}` 10:30 AM · `{{4}}` oil change

### Arabic
```
مرحباً {{1}}، تذكير بموعدك في {{2}} غداً الساعة {{3}} لخدمة {{4}}.
يمكنك الرد هنا لتغيير الموعد.
```
Samples: `{{1}}` أحمد · `{{2}}` Care Auto Repair · `{{3}}` 10:30 · `{{4}}` تغيير الزيت

### Hindi
```
नमस्ते {{1}}, आपका अपॉइंटमेंट {{2}} में कल {{3}} बजे {{4}} के लिए है।
समय बदलना हो तो यहीं जवाब दें।
```
Samples: `{{1}}` अहमद · `{{2}}` Care Auto Repair · `{{3}}` 10:30 · `{{4}}` ऑयल चेंज

---

# 2. booking_reminder_morning

**Category: UTILITY** — sent on the morning of the appointment.

### English
```
Good morning {{1}}, we are expecting you at {{2}} today at {{3}}.
Location: {{4}}
```
Samples: `{{1}}` Ahmed · `{{2}}` Care Auto Repair · `{{3}}` 10:30 AM · `{{4}}` https://maps.app.goo.gl/example

### Arabic
```
صباح الخير {{1}}، ننتظرك في {{2}} اليوم الساعة {{3}}.
الموقع: {{4}}
```
Samples: `{{1}}` أحمد · `{{2}}` Care Auto Repair · `{{3}}` 10:30 · `{{4}}` https://maps.app.goo.gl/example

### Hindi
```
सुप्रभात {{1}}, आज {{3}} बजे {{2}} में आपका इंतज़ार है।
लोकेशन: {{4}}
```
Samples: `{{1}}` अहमद · `{{2}}` Care Auto Repair · `{{3}}` 10:30 · `{{4}}` https://maps.app.goo.gl/example

---

# 3. post_service_followup

**Category: UTILITY** — sent two days after the work was done.

### English
```
Hi {{1}}, how is the car after the {{2}} at {{3}}?
Reply here if anything does not feel right.
```
Samples: `{{1}}` Ahmed · `{{2}}` oil change · `{{3}}` Care Auto Repair

### Arabic
```
مرحباً {{1}}، كيف حال السيارة بعد {{2}} في {{3}}؟
رد هنا إذا لاحظت أي شيء غير طبيعي.
```
Samples: `{{1}}` أحمد · `{{2}}` تغيير الزيت · `{{3}}` Care Auto Repair

### Hindi
```
नमस्ते {{1}}, {{3}} में {{2}} के बाद गाड़ी कैसी है?
कुछ ठीक न लगे तो यहीं बताएं।
```
Samples: `{{1}}` अहमद · `{{2}}` ऑयल चेंज · `{{3}}` Care Auto Repair

---

# 4. service_due_nudge

**Category: MARKETING** — sent months after the customer's last visit.

> Submit it as MARKETING. It is an invitation to come back, not a service notice, and filing it as
> utility is both a rejection risk and dishonest. Show the owner the wording before you submit —
> it goes out in his name, and he can switch it off in `info.yaml` if he would rather not send it.

### English
```
Hi {{1}}, it has been {{2}} months since your last {{3}} at {{4}}.
Reply here and we will check availability for you.
```
Samples: `{{1}}` Ahmed · `{{2}}` 6 · `{{3}}` service · `{{4}}` Care Auto Repair

### Arabic
```
مرحباً {{1}}، مضى {{2}} أشهر على آخر {{3}} في {{4}}.
رد هنا وسنتحقق من المواعيد المتاحة.
```
Samples: `{{1}}` أحمد · `{{2}}` 6 · `{{3}}` صيانة · `{{4}}` Care Auto Repair

### Hindi
```
नमस्ते {{1}}, {{4}} में आपकी पिछली {{3}} को {{2}} महीने हो गए हैं।
यहाँ जवाब दें, हम उपलब्धता देख लेते हैं।
```
Samples: `{{1}}` अहमद · `{{2}}` 6 · `{{3}}` सर्विस · `{{4}}` Care Auto Repair

---

## Tick them off

- [ ] booking_reminder_day_before — English / Arabic / Hindi
- [ ] booking_reminder_morning — English / Arabic / Hindi
- [ ] post_service_followup — English / Arabic / Hindi
- [ ] service_due_nudge — English / Arabic / Hindi
- [ ] All twelve showing **Approved** in WhatsApp Manager

Until that last box is ticked, everything else works and reminders stay silent. The log names the
exact template that failed, so a missed one is obvious rather than mysterious.
