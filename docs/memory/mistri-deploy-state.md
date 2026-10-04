---
name: mistri-deploy-state
description: "Mistri is deployed live on the VPS at mistri.offpageos.com; how it is wired, how to reach it, and what is left."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0d3397bf-0fa7-47fe-bb19-5c6e9e13b26e
  modified: 2026-09-19T09:47:11.269Z
---

[[mistri-project]] is **deployed and public** as of 2026-09-10. Not on a clean VPS —
on the user's existing **cPanel/WHM box** (AlmaLinux 8, `server2.dulcebonito.com`, IP
`192.64.115.127`), which also hosts offpageos.com and other cPanel accounts.

**How it runs**
- Code at `/opt/mistri`, venv `/opt/mistri/.venv` (Python 3.11), service user `mistri`.
- systemd unit `mistri.service` runs uvicorn on `127.0.0.1:8123`. `systemctl restart mistri`.
- Public URL `https://mistri.offpageos.com` — valid Let's Encrypt cert via cPanel AutoSSL.
- Reached through cPanel's ea-nginx -> Apache -> our localhost port, via a **scoped,
  rebuild-safe reverse-proxy** at `/etc/apache2/conf.d/userdata/{std,ssl}/2_4/dulcfokx/mistri.offpageos.com/mistri-proxy.conf`.
  Never touched the global web stack — the other sites were never at risk.
- DNS: `mistri` A record at Cloudflare -> the IP, **grey cloud (DNS only)** so AutoSSL works.

**SSH in from this machine:** `ssh -i ~/.ssh/mistri_srv root@192.64.115.127` (key added to
root's authorized_keys on 2026-09-10).

**Meta side (test number, app "Mistri" ID `1317358583652870`, portfolio Digital Media Studio
Canada):** free test number +1 (555) 675-7750, phone_number_id `1315616068301161`, recipient
+971 58 812 9679. Webhook verified and pointing at `/webhook` (verify token in server `.env`).
The earlier app on portfolio Monafa.co was **restricted** — abandoned; this is the second app.

**WORKING END TO END as of 2026-09-10.** A real WhatsApp message to the test number
(+1 555 675-7750, from the allow-listed +971 58 812 9679) gets a real reply: price looked
up from the demo sheet, slot buttons, bold price. App is Live/published; OpenAI provider
(gpt-4o-mini, key in server .env); LLM_PROVIDER=openai. Interactive replies (send_buttons /
send_list) shipped. What made inbound finally work: publish the app + subscribe the app to the
WABA (`/{waba}/subscribed_apps`) + subscribe the app's `messages` webhook field
(`/{app}/subscriptions`). Verifying the callback URL alone was not enough.

**Booking flow hardened for messy customer input (2026-09-12).** Time-pick is ALWAYS deterministic
tappable buttons via `engine._slot_reply` (never the composer) — killed the "model invents 17:00 →
guard blocks → handover" bug on vague times ("tomorrow evening", "3pm", "asap", "morning" all return
buttons). Price quotes no longer dump the calendar; they ask "would you like to book?" and, if the
customer goes quiet ~30s (`respond.BOOK_NUDGE_SECONDS`, `_book_nudge_later`), auto-send the times
once. `_customer_booked_at` stops a 2nd service silently reusing the 1st booking's slot (double-book).
Dead `_offer_slots` removed. Slot wording: future full day → "nothing free that day"; a named time
that's gone → "that time isn't free"; a defaulted today → no scary prefix. All these live in engine
code → apply to every garage.

**Car→class is deterministic in code (2026-09-12).** `pricing.builtin_category(make, model)` maps
common UAE models to sedan/suv/luxury from a built-in table with English + Arabic + Roman aliases
(Patrol/باترول→suv, Mercedes/مرسيدس→luxury, Camry/كامري→sedan, etc.); `pricing.quote` uses garage
model_categories → classifier car_category → builtin table, and only raises NeedCar if all fail. This
killed the intermittent Arabic SUV/luxury handovers (gpt-4o read the car fine but was flaky at setting
the class; now code decides). Prices still never invented — code only reads the sheet. Also: `_car`
de-dupes words (was "Patrol Patrol"). KEY LESSON for the user's repeated "why does GPT fail": the
model does understanding+language; CODE does anything that must be reliable (price class, price
lookup, info keywords). When something's flaky, move it from the model into code.
Note: garage price sheets entered via the onboard form during testing were patchy (Care had only
sedan oil_change filled, an inspection "Free99" typo) — those handovers were MISSING DATA, correct
behaviour, not bugs. Real owners fill prices once via their form; no per-customer manual work.

**Classifier model: gpt-4o (decided 2026-09-11).** A full-battery test showed gpt-4o-mini
returning `intent=other, confidence=0.0` for obvious info/price questions (so they handed over) and
the COMPOSER mis-picking language (English → Roman Urdu). Fixes: `settings.openai_classify_model`
(default "gpt-4o") used by `llm.classify` while compose stays on cheap `openai_model` (gpt-4o-mini);
engine inserts a `_language_directive` fact forcing the reply language from the classifier read;
`_guess_info_topic` keyword fallback answers hours/location/payment even when intent is mislabelled
(FAQ still wins over the guess); price flow asks for the car (pricing.NeedCar) BEFORE the confidence
gate; `_as_text`/`_car`/pricing strip "null"/"TODO" junk. Result: info, language, and partial-car
all work now; Arabic price still occasionally hands over (safe). ~+half a cent/msg for gpt-4o classify.

**Token: RESOLVED 2026-09-11.** Replaced the 24h test token with a **permanent System User
token** (Business Settings → System Users → "Mistri" (Admin), app + Test WABA both Full access →
Generate token, expiration Never, scopes whatsapp_business_messaging + whatsapp_business_management).
Lives in `/opt/mistri/.env` `META_ACCESS_TOKEN=` (198 chars). `whatsapp.check_token()` returns
connected; admin dashboard shows a 🟢/🔴 WhatsApp-sending banner. `hello_world` delivered to the
allow-listed +971 58 812 9679, proving token+recipient+delivery end-to-end. Editing .env tripped the
user up badly (they were already root on the box, kept wrapping in ssh-to-self; the line also got
deleted then re-appended) — for future edits just run the `sed`/`echo >>` locally on the server, no ssh.

**Two hard caveats**
- The Meta access token is a **24-hour test token** — it EXPIRES daily and replies then fail
  401. For anything beyond a same-day demo it must be replaced with a permanent **System User**
  token (business.facebook.com -> System Users -> assign app + WABA -> generate, no expiry).
- The test number only messages the one allow-listed recipient. Real customers need Care's
  own number via coexistence, which needs Tech Provider/BSP + business verification = a **trade
  licence** the user does not yet have. That is the real launch blocker, not code.

**What is NOT done / blockers**
- `.env` still needs three secrets before it can answer a live message: `META_APP_SECRET`
  (accept signed inbound, else 401), `META_ACCESS_TOKEN` (send reply; test-number token
  expires 24h), `ANTHROPIC_API_KEY` (or every reply hands over). User edits `/opt/mistri/.env`
  directly and `systemctl restart mistri` — secrets must not go through chat.
- Inbound may need the app **published** (unpublished apps may only get test webhooks).
- Routing: `routable_ids()` excludes the demo garage, and `care` has no prices, so a live
  message currently routes to `care` and hands over. For a price-answering demo, point the
  test number's phone_number_id at the demo garage temporarily, then revert.
- Admin page: `https://mistri.offpageos.com/admin/` — user `admin`, password in server `.env`.
  Auth is **cookie-only** (session cookie from the login form). HTTP Basic is deliberately NOT
  accepted — browsers cache Basic creds and silently re-send them, which defeated Log out (the
  cached password re-authenticated on the post-logout redirect). Tests authenticate with a
  `Cookie: mistri_admin=<_session_value()>` header, not Basic. Logout deletes the cookie with the
  same Secure/HttpOnly/SameSite/Path attributes it was set with.
  Public marketing landing page is at `/` (light theme, full sales page: problem, ROI/money
  section, automation, 30-day free test, "no app/reinstall, just your number, leave anytime").
  Pricing = two packages (word "trial" avoided, use "test"): **Monthly AED 600/mo** and
  **3 Months AED 1,000** (~AED 333/mo, marked best value, save AED 800 vs monthly), both after a
  free 30 days. A public demo form (`POST /contact`) writes a `leads` row; leads show in admin →
  **Messages** with a tap-to-reply wa.me link that pre-fills a short opener in the lead's own
  script (en/ar/ur/hi, `admin._opener`) and a Mark-done button. Mistri never auto-messages a lead.
  Admin has a real cookie-session login/logout (`/admin/login`), no longer a raw Basic prompt.
- Follow-up features shipped 2026-09-10 (`app/aftercare.py` + morning `unconfirmed` scheduler
  job): **no-show confirmation** (day-before reminder asks "reply YES", a yes marks the booking
  confirmed, owner gets a 07:30 list of today's unconfirmed cars) and **review request** (a happy
  reply after the post-service follow-up sends the garage's Google review link). Three new
  `bookings` columns auto-migrated live. For these to actually fire, Care's `info.yaml` still
  needs real values (all currently TODO/placeholder): `owner_alert_number` (owner's personal
  WhatsApp — where every alert/summary/no-show list goes), `review_link` (Google review URL),
  plus prices. The public CTA button is driven by the new `operator_whatsapp` (else
  `operator_email`) setting — Mistri's own sales contact, never a garage's number; unset by default.
- Landing page has a "Why garages lose customers" section under the hero: 1★ review-style cards
  (real anonymized UAE-garage complaint quotes, no competitor named — NOT literal screenshots, to
  avoid impersonation/defamation) mapped to Mistri's fix. Backed by docs/RESEARCH-garage-reviews.md
  (finding: bad reviews are driven by communication failure, not bad repairs; review-request feature
  is the growth wedge).
- **Self-service signup** (added 2026-09-11): public `GET/POST /start` — a garage owner enters
  name + WhatsApp number, `site._create_garage` writes `garages/<slug>/` (info+prices template, all
  prices TODO) with **`pending: true`**, records a "NEW GARAGE" lead for the operator, and redirects
  straight into their private onboarding link `/onboard/<id>?t=`. Landing page has a "Set up your
  garage" header button + a "Get started" 3-step section. CRITICAL: `garages.routable_ids()` now
  excludes `pending` (as well as `demo`) — because `id_for_phone_number_id` falls back to the single
  routable garage, a pending signup must stay inert or it breaks the live `care` routing. To take a
  signup live: edit its info.yaml `pending: false` + set `wa_phone_number_id` after the Meta connect.
  Owners now get a REAL account: at `/start` they set a password; `owners` DB table stores
  garage_id + normalised number + pbkdf2 hash. They log in at `/login` (number + password) →
  `/owner` → their garage home. Owner session cookie `mistri_owner` (signed, carries only their
  garage_id) — separate from the operator's `mistri_admin`; an owner reaches ONLY their own garage.
  `onboard.py` form/save/home authorize via EITHER the `t=` token OR a matching owner cookie, so no
  magic link to keep. Signup logs them in immediately. Public header: "Owner login"→/login +
  "Set up your garage"→/start; footer "Operator login"→/admin/. app/owners.py holds it all.
- Admin **Prices & setup** lists ALL garages (not just routable) with a Live/Setting-up pill + a
  "N waiting to go live" banner, so pending signups are visible/activatable. (Demo garage hidden.)
- **Onboarding nudges** (app/nudges.py, added 2026-09-11): a daily `setup_reminders` scheduler job
  WhatsApps an owner who signed up ≥24h ago but entered no prices (once, `Owner.setup_nudged`); and
  `maybe_welcome`, fired as a background task from onboard.save, sends an "all set" message the
  moment prices are complete (once, `Owner.welcomed`). Both are approved WhatsApp templates
  (templates/onboarding_reminder.md, onboarding_welcome.md) — so they only DELIVER once those
  templates are approved in Meta and a live sending number exists; the logic/flags work now.
  `settings.public_base_url` builds the edit link in the reminder.
- Admin has a **Prices & setup** page (`/admin/setup`): per routable garage it shows the owner's
  private tokenised edit link (`/onboard/{id}?t=...`) to hand over, plus a readiness checklist
  (prices filled X/Y, owner_alert_number, review_link, maps_link). The owner form already writes the
  `*.yaml` and `garages.load()` reloads on mtime change, so an owner's price edit is quoted on
  WhatsApp from the very next message — no restart. This IS the "owner profile" (no password, just
  the link).

**Common-query coverage — English policy topics (2026-09-16).** User supplied 38 typical customer
questions and wanted the bot to never mishandle them. Added 4 universal policy topics to
`engine._INFO_KEYWORDS` + constant safe answers in `_info_facts` (no garage data needed, product-true
for all): `quotation` (we always quote before work; free inspection then exact quote incl parts/
labour/VAT — never a number), `appointment` (book here or walk in), `turnaround` (depends; exact time
after inspection; no promise), `media` (yes send a photo/video, don't diagnose from it). Also added
"instalment" to payment keywords. Deliberately did NOT hardcode garage-specific scope (bodywork,
tyres, genuine parts, RTA, pre-purchase, diagnostic price) — those still hand over (correct, rule 1).
Prices→price flow, symptoms→inspection, unchanged. Keyword router is deterministic so it fires even
when the classifier mislabels intent as "other". A LIVE probe on the server (real gpt-4o classifier +
Care's real sheet) first showed 3/5 policy Qs leaking to HANDOVER/"which service" because the model
tagged "quotation before starting?"/"how long?"/"finish today?" as price/booking — those branches
short-circuit before the info/keyword net. FIX: an EARLY in-code policy pre-check in build_reply
(`_guess_policy_topic` with TIGHT process-phrase keywords `_POLICY_KEYWORDS`) runs right after
classify and, unless it's a symptom or a genuinely named service being priced/booked, forces
intent=info + info_topic=<policy>. Re-probed live: all 5 policy Qs now answer, prices still quote,
symptom→inspection buttons, scope still hands over. Suite 396 passing. LESSON (again): for known
phrasings, decide in code BEFORE trusting the model's intent — the price/booking branches run first,
so a keyword net placed only in the info branch never sees them.

**English audit + independent judge workflow (2026-09-16).** Ran the same objective audit for ENGLISH
(scratchpad probe_en.py → report_en.json): 42 items (38 Qs + 2 exact prices + 2 flows), plus 3 full
English conversations. Code verdict: 37 PASS, 5 WARN, 0 FAIL; all 3 convs clean (English throughout,
booked, no stray price). The 5 WARN = handovers: 2 correct (bodywork, parts-type), 3 improvable
(tyres — on sheet!, brand, minor-service). THEN ran a Workflow (ultracode) — 6 independent gpt/judge
agents grading all 42 English Q/A against the 7 rules (scratchpad judge_en.wf.js, run
wf_afd0f646-8ea): result {"total":42,"ok":42,"issues":[]} — ZERO violations. So English has two
agreeing verdicts (code 0-fail + judges 0-issue). English report artifact:
https://claude.ai/artifact/N77ggwUsUhZiVyBEsv7uZk ; Urdu report:
https://claude.ai/artifact/6HHKfBhVxamD3Kcy1iK5nW . WINDOWS GOTCHA for Workflow scriptPath: write the
.js with newline="\n" (CRLF's \r triggers "control characters hidden in approval dialog" rejection);
also strip control chars from any embedded data.

**Repeat-picker fix (2026-09-16).** User (screenshot) caught: after times were shown for a symptom,
re-stating the car made the bot REPEAT the whole "let's book a free inspection, which time? 👇" block
verbatim (still booked correctly on tap, but read as broken). Fix: `_recently_offered_slots(history)`
(last assistant msg contains 👇) + a `nudge` param on `_slot_reply` + `_SLOT_NUDGE` dict — when times
are already on screen and there's no taken/day-full prefix, reply just "Pick one of the times above 👆
or type another" and re-show the buttons, instead of the full pitch. Wired into the symptom branch and
the booking-missing-slot path. Verified live: topic-switch convo now nudges (not repeats) and confirms.
Suite 412 passing; gate ALL GREEN.

**Multi-turn CONVERSATION testing (2026-09-16).** User's sharp point: the audit tested each of the 30
Qs in a FRESH chat (first question only) — but real customers ask several questions in a row, which is
where follow-ups/language-drift/booking-state break. Added a conversation probe (scratchpad
conv_probe.py) running 4 realistic Urdu threads through the real bot: (1) greeting→price→2nd price→
location→book→tap; (2) symptom→car→"how long?"→"card?"→tap; (3) tyre price→switches to a fault
mid-chat→car→tap; (4) short replies "haan"/"shukriya". Result after fixing the test's __TAP__ (a tap
uses the LAST turn that showed buttons, since intervening info answers have none): ALL 4 end BOOKED,
language stays 'ur' throughout, no stray price. So follow-up questions hold. Report artifact
(https://claude.ai/artifact/6HHKfBhVxamD3Kcy1iK5nW) now has a "Full back-and-forth conversations"
section showing the whole chats. USER also keeps asking "why pay for ChatGPT API if we hardcode
things" — settled answer: the AI does the un-hardcodable 90% (understanding messy human language in
4 languages/scripts + writing natural replies); code does only the 10% that must be exact (the price
NUMBER from the sheet, and booking slot/confirmation). Receptionist reading a price list, not a dumb
IVR menu.

**FULL AUDIT — objective, 0 failures (2026-09-16).** Two saved harnesses in repo:
`tests/gate_live.py` (5-language end-to-end flows, run before every deploy, must be ALL GREEN) and
`tests/audit_live.py` (all 30 Urdu Qs + priced quotes + both booking flows, verdict computed IN CODE
per rule). Run on server: `DATABASE_URL=sqlite:////tmp/x.db PYTHONPATH=/opt/mistri
.venv/bin/python tests/audit_live.py` (real gpt-4o, Care, throwaway DB). Latest audit: **28 PASS,
6 WARN, 0 FAIL** of 34. Hard rules all held: no invented prices; exact prices right (oil 249, batt/SUV
399); 19/19 symptoms ask car+free inspection with no price/diagnosis; all Urdu (no Arabic/English
flips); both booking flows confirm on tapped time. The 6 WARN are all "advisor will call" handovers on
off-sheet/scope Qs: 3 are CORRECT (parts-type price, match-competitor-quote, labour-only — owner
pricing calls); 3 are IMPROVABLE — should offer a free inspection instead of a cold handover:
#20 pre-purchase (Care HAS pre_purchase_inspection on sheet — should recognise+quote), #21 RTA-fail
cost, #25 which-work-urgent. Test-plan given to user (7 pass/fail rules; automated gate + manual smoke;
per-garage data readiness; triage bug-vs-datagap-vs-correct-handover; every found issue becomes a
permanent gate case). IMPROVED: off-sheet PRICE asks for car work no longer cold-handover — the price
branch's `pricing.NotOnSheet` (and unfilled/TODO price) now sets natural facts ("can't price off the
list; offer a FREE inspection; NO price") and falls through to the composer (money_ok False → guard
blocks any number). "full service", gearbox rebuild, RTA repair, pre-purchase, unfilled-luxury-brake
all get a warm inspection offer, never "advisor will call", never an invented price. Non-car/
out-of-scope (motorbikes, financing) still hand over (they arrive as other/info intent, not price).
Adversarial off-sheet tests updated to expect inspection-offer + no-price-leak. Re-audit: 31 PASS,
3 WARN, 0 FAIL (was 28/6/0); gate ALL GREEN. The 3 remaining WARN (#2 packages, #20 pre-purchase,
#25 urgent) hand over only because the classifier tags them other/scope not price — safe, not wrong;
pushing further risks the deliberate out-of-scope handover. Suite 411 passing.

**Slot-picker LOOP fixed + slot-tap always books (2026-09-16).** Field bug (screenshot): customer
tapped an offered time -> "Wo time available nahi hai" -> re-offered the SAME times -> infinite loop;
another tap just re-showed the inspection lead. Live-DB diagnosis: the test number already HELD
Wed16 17:00 (from earlier testing); `slots.next_available` still offered it (capacity 1<2), but the
engine's `_customer_booked_at` double-book guard rejected the tap -> re-offer -> loop. FIX 1:
`slots.next_available(..., exclude_customer=NUM)` + `slots.customer_booked_slots()` — never offer a
slot the customer already holds; `engine._slot_reply(customer_number=...)` threads it through all 3
call sites. FIX 2 (caught by the GATE as an AR/UR regression): a tapped time button
("Wed 16 Sep, 14:00") was being re-classified as symptom (car still in context) and looped the picker
— added `_looks_like_slot_pick()` (regex \d{1,2}:\d{2} + weekday/month token) and force intent=
"booking" early, so a tapped time ALWAYS books and can never be re-interpreted. Reproduced the loop on
a seeded throwaway DB: held slot excluded, tap confirms, no loop. Full gate ALL GREEN again (EN/AR/
UR-roman/UR-script/HI, both flows). Cancelled the 4 stale test bookings on 971588129679 so manual
testing is fresh. Suite 411 passing. Minor residual: on an English button tap the reply script can
render Roman Urdu instead of Urdu-script (language is right, script not persisted on the conversation)
— cosmetic; fix later by persisting conv.script.

**REBALANCE — let the AI be natural again (2026-09-16).** User's key push: "this is [supposed to]
give natural answer, that's why I pay for API... this like dumb human." Correct — I'd over-hardcoded,
making it a robotic rule-bot. NEW PRINCIPLE (the balance): ONLY the exact price NUMBER (from sheet)
and the booking mechanics (slot buttons, confirmation) stay deterministic; EVERYTHING conversational
is the model's, guard just blocks invented numbers. Concrete change: an off-sheet "full service /
packages / what do you offer" ask no longer cold-handovers — `_wants_service_menu()` routes it to the
COMPOSER with facts (the real priced-service list via `_priced_service_list()` + "answer naturally,
NO price, offer a free inspection"); `pricing.NotOnSheet` for a menu ask sets facts and falls through
to compose (quote stays None, money_ok False so guard blocks any number). A GENUINE specific off-sheet
job (gearbox rebuild — no menu words) still hands over (intentional, adversarial tests keep passing).
Live proof (Care, real gpt-4o): "full service?" -> "we'd need to inspect to quote exactly, book a free
inspection?"; "what packages?" -> naturally lists oil/brake/battery/tyre/diagnostics/pre-purchase; all
price-free, warm, Urdu+English. Suite 410 passing. KEY LESSON: don't script what the model should say
— lock the money, free the conversation.

**Deterministic booking confirmation + end-to-end GATE (2026-09-16).** Field bug: after tapping a
slot to confirm a free inspection, the owner alert said "my reply did not look right, I stopped it"
— the CONFIRMATION was composed by the model, which reworded the time (15:00 -> "3 بجے") and the
money-guard blocked the unapproved number, turning a good booking into a handover. FIX: confirmations
are now built in code (`engine._confirm_reply` + `_CONFIRMED` dict per lang) and returned directly
from `_handle_booking` — never composed, never guarded, time shown exactly as tapped. This was the
LAST model-written step in the price->inspection->booking->confirmation path; that whole path is now
deterministic (model only reads intent/car/language). NEW STANDARD to stop the whack-a-mole: a live
end-to-end GATE at `tests/gate_live.py` runs FULL multi-turn conversations to completion in EN, AR,
UR-roman, UR-script, HI — symptom->car->tap(actual button)->CONFIRM free inspection, and price->yes->
tap->CONFIRM service — asserting the end state (booking set, not handover, not blocked, right service/
lang). Run it on the server: `DATABASE_URL=sqlite:////tmp/gate.db PYTHONPATH=/opt/mistri
.venv/bin/python tests/gate_live.py` (throwaway DB, real gpt-4o classifier, Care). Result: ALL GREEN
(35 checks). Run this gate after ANY engine/booking change, not slice-by-slice hand tests. Unit suite
405 passing. Care sheet has no "full service"/packages (so #1/#2 handover is correct-but-common).
RESOLVED: one-tap release shipped — admin conversation page (`/admin/conversation/{id}`) now shows a
"Give this chat back to the bot" button POSTing to `/admin/conversation/{id}/release` →
`conversations.release`; clears the open handoff + owner pause instantly (no more 24h-only wait).
Tests added; suite 407 passing. NOTE ON SSH: the cPanel box rate-limits rapid SSH/scp bursts
("Connection closed by ... port 22"); space out or wrap in an until-retry loop.

**Full Urdu run — 3 real bugs found & fixed (2026-09-16).** Built a harness (throwaway
DATABASE_URL sqlite, fresh chat per query) that runs ALL 30 Urdu queries + multi-turn flows through
the REAL gpt-4o classifier against Care on the server — DON'T make the user test one at a time; probe
everything at once. Found & fixed 3 bugs (engine.py + booking.py): (1) LANGUAGE — Urdu misread as
Arabic (shared script) → replies in Arabic. Fix: `_looks_urdu(message)` checks Urdu-only letters
(ٹ ڈ ک گ ہ ے ی گ چ پ …); if classifier says "ar" but text has them → force "ur"+arabic script.
Plus short-reply stickiness: a ≤4-word reply keeps the conversation's `language_hint` so a one-word
answer / a tapped English slot title never flips the language. (2) FREE INSPECTION became a PAID job
— after a symptom offered a free inspection, tapping a time booked e.g. "brake repair" (classifier
re-attached a service from the symptom). Fix: in `_handle_booking`, `_is_inspection_context(history)`
now WINS over any classifier service_id — a free inspection stays free. (3) BOOKING NAME LOOP — asking
the name mid-booking looped (a one-word "roman" wasn't read back as the name). Fix: removed
customer_name from `booking.REQUIRED` entirely (we have the WhatsApp number); confirm() defaults it to
"WhatsApp customer". Booking now gathers only service/inspection + car + slot. Re-probed all 30 +
both flows end-to-end: symptom→car→tap = FREE INSPECTION confirmed (Urdu); price→yes→tap = service
booked (Urdu); #3 now Urdu; no loops. Suite 405 passing. NOTE for testing: a HANDOVER (off-sheet Qs
like "full service", "labour only", "match competitor quote") flips the whole chat to "handed over,
waiting for release" — bot stays SILENT on everything after until released; `conversations.release()`
exists but NOTHING calls it (no admin button / owner cmd) → only 24h auto-release. Need a one-tap
release for testing + launch (offered, not yet built). Care sheet has NO "full service"/packages, so
#1/#2 handover is correct-but-common; owner should add packages. Care pickup_available=true.

**Urdu-script coverage for policy/info questions (2026-09-16).** User gave 30 real Urdu
(Arabic-script) customer queries. The policy/info ANSWERS were already language-independent (composer
writes in the customer's language via `_language_directive`); the gap was the keyword net being
English/Roman/Arabic only. Added Urdu-script triggers to `_POLICY_KEYWORDS` + `_INFO_KEYWORDS`
(quotation "پھر کام شروع"/"کرنے سے پہلے"; turnaround "کب تک واپس"/"کتنی دیر"; media "ویڈیو"/"تصویر";
hours/location/payment/warranty/pickup Urdu words). Live Urdu probe on Care exposed 2 leaks: "check
then start work" (#24, model attached a service → asked which car) and "send a video of the noise"
(#30, model tagged symptom). FIX: the policy override now FORCES `quotation` and `media` through even
when the model saw a service or a symptom (those are always policy questions); `turnaround`/
`appointment` still defer to a genuine named service or a fault. Re-probed: all correct — symptoms→
inspection buttons (Urdu), quote-before-work answer, media yes, turnaround, pickup (Care pickup_
available=true so "yes" is real). Suite 405 passing. Caveat: keyword matching is literal Urdu script —
different yeh/keheh forms (ي vs ی) won't match; acceptable, composer+classifier still catch most.

**Free-inspection booking fixed (2026-09-16).** Field bug (screenshot): after a symptom, once the
customer gave the car ("mercedes 2030"), the bot asked for a time in PLAIN TEXT with NO tappable
buttons — the composer improvised "pick a time?". Root cause: a free inspection has no service_id,
but `booking.Draft.missing()` required service FIRST, so the inspection could never reach the slot
step and fell through to compose. Fixes (engine.py + booking.py, deployed): (1) `Draft.is_inspection`
flag — when set, `missing()` needs only car+slot (no service, no name gate); (2) symptom branch: the
moment `_car(read)` is known, route STRAIGHT to `_slot_reply` deterministic buttons with an
`_INSPECT_LEAD` line ("Let's book you a free inspection.") in all langs — never compose a time
question; (3) `_handle_booking` treats a service-less booking as the inspection ONLY when
`_is_inspection_context(history)` (recent assistant turn mentions inspection/فحص/انسپیکشن) — a bare
"book me in" with no context still asks which service (guarded by test). Inspection rows get
service_name "Free inspection" + fallback customer_name "WhatsApp customer" (bookings.customer_name
is NOT NULL). +4 tests; suite 381 passing. Lesson repeats: the time step must ALWAYS be deterministic
buttons, never the composer.

**Scope limits / "what we don't service" (2026-09-12).** New owner-set free-text field
`info["restrictions"]` (e.g. "GCC-spec only, no import-spec cars") — addresses Care's top real
complaint (Orxan Google review: turned away for a non-GCC car only at the end). Owner sets it via
a textarea on their onboard form (blank clears it). Engine surfaces it UP FRONT: on the FIRST price
quote of a chat it prepends a translated lead-in ("Please note/ملاحظة/Note") + the owner's verbatim
scope text (once per chat, tracked by scanning assistant history — `engine._already_stated`); on
greeting/symptom/booking/info compose turns it passes `engine._restriction_fact` so the composer
raises it in the customer's own language ONLY if their request falls under it. We never invent a
scope; lead-in is translated, owner's text shown verbatim. 5 new engine tests; suite 377 passing.
Deployed (scp engine.py + onboard.py). NOTE: Care's own restriction text is left for the owner to
fill via their form — do NOT write Care's scope for them (user's "prices add by care, not by me").

**SEO content — Tier-1 guide pages (2026-09-17).** Strategy decided WITH user: traffic-first from
Google (leads later); build ONE page per REAL high-demand search query (title == the query), no
attractive-but-unsearched fluff (user was firm on this — killed a "symptom checker tool" idea because
nobody searches that). Audience is mostly car owners (that's where volume is) — job now is traffic +
topical authority, converted later via a small "Run a garage?" CTA on each page. Built `app/guides.py`
(own router, registered in main.py after site.router): 5 articles on the highest-demand car-problem
queries — car-ac-not-cooling, why-is-my-car-overheating, car-wont-start, car-making-noise-when-starting,
steering-wheel-shakes-when-braking. Each: SEO title/meta/canonical/OpenGraph/Article JSON-LD, UAE-
flavored genuinely-useful content, generic Dubai cost RANGES (clearly "varies, get a quote" — NOT a
specific price, respects the no-invented-price rule), related-links, CTA to "/". Also `/guides` hub,
`/sitemap.xml`, `/robots.txt`, and a "Car help" footer link on the landing for crawl discovery. All
live 200 on mistri.offpageos.com. NEXT (user action, not code): submit site + sitemap to Google
Search Console so Google indexes them (free; without it, discovery is slow); ranking takes weeks.
Guide pages now have (added 2026-09-17): a responsive SIDEBAR nav (all guides, current highlighted;
desktop=left column, mobile=horizontal scroll chip row), landing links in 3 spots (sticky top "For
garages" btn, sidebar "← Mistri for garages", CTA "See how it works"), and SOCIAL SHARE buttons
(WhatsApp/Facebook/X/Copy-link) on every article for free distribution. Mobile layout fixed
(overflow-x:hidden, min-width:0 on main, overflow-wrap) — verified at 375px in the browser pane.
Sidebar also has a "Run a garage?" PROMO BOX (green, links to landing "/") under the nav (hidden on
mobile). CTAs are now DYNAMIC PER ARTICLE for CTR (`_CTA_COPY` keyed by slug, `_cta_box(slug)` +
sidebar both use it): each page's CTA headline names that problem's pain ("Drowning in AC messages
every summer?", "Missing the morning won't-start rush?", "Losing brake jobs to slow replies?", etc.)
+ a tailored description. Contextual CTA > generic. Falls back to _DEFAULT_CTA (index/unknown).
Guide CTAs reworked (2026-09-17) to 3 rotating HOOK CTAs (`_CTAS`, rotated by article index via
`_CTA_BY_SLUG`, resolved at call time by `_cta_for`): (1) "Do you know why customers leave a bad
review — even after a good repair?" → slow reply not the work, Mistri answers in seconds; (2) "Did you
know one AI can answer your customers in every language?" → Arabic/English/Hindi/Urdu; (3) "Do you know
you can auto-book customers straight from WhatsApp?". Each description ties the hook question → cause →
Mistri → result. Added offer line `_OFFER="Test it for 30 days. Cancel anytime."` under the button in
BOTH the sidebar promo box and the in-article CTA. Google Search Console HTML-file verification served
at /google2e94c7f871e54250.html (route in guides.py).
PHASE 2 COMPLETE (2026-09-19): 13 "X cost in Dubai" price pages live (oil-change-price-dubai,
car-service-cost-dubai, car-ac-gas-refill-price-dubai, car-battery-price-dubai,
brake-pads-replacement-cost-dubai, new-tyres-price-dubai, car-diagnostic-cost-dubai,
wheel-alignment-cost-dubai, car-painting-dent-repair-cost-dubai, clutch-replacement-cost-dubai,
ac-compressor-replacement-cost-dubai, timing-belt-replacement-cost-dubai,
windshield-replacement-cost-dubai). Each group="prices", realistic Dubai price RANGES (clearly "varies,
get exact quote"), ends with _EXACT funnel. Price pages get OWN rotating CTAs (`_CTAS_PRICE`, "AI
customer service for garage owners" angle) via group-aware _CTA_BY_SLUG; problem pages keep `_CTAS`.
Sidebar + index split into "Common problems"/"Prices in Dubai". Total 33 guide pages, sitemap 35 URLs.
Guide sidebar reordered (2026-09-19): promo CTA box moved to TOP, above the nav lists (was bottom).
Landing money section (app/site.py ~line 449): added an "AED 4,000/mo (a person, 9-6) vs AED 600/mo
(Mistri, 24/7, every language)" comparison box; ALSO fixed a pre-existing price mismatch — ROI
"Mistri subscription" was −AED 400 while pricing section advertises AED 600/mo → aligned to −AED 600
and net gain recomputed +AED 1,190 → +AED 990. (Advertised price is AED 600/mo, AED 1,000/3-mo.)
NEXT: Phase 3 (RTA/registration), 4 (maintenance how-to), 5 (local+buyer); Arabic track. Outreach:
100-garage tracker xlsx built (scratchpad Garage-Outreach-List.xlsx, auto-message col); user getting
free Google Places API key so I can write a fetch script to fill it (can't scrape from here, won't fabricate).
PHASE 1 COMPLETE (2026-09-17): 20 car-problem
pages live (5 original + 15 added in one batch:
car-using-too-much-fuel, exhaust-smoke, car-pulling-to-one-side, car-jerks-when-accelerating,
check-engine-light-on, car-ac-smells-bad, brakes-squeaking-grinding, car-vibrating-at-high-speed,
car-battery-keeps-dying, burning-smell-from-car, car-shaking-when-idle, gearbox-jerks-changing-gears,
steering-hard-to-turn, leaking-under-car, clutch-slipping-signs). Each: SEO title=query, useful UAE
content, generic cost ranges w/ disclaimer, sidebar+share+dynamic simple CTA, mobile. sitemap.xml =
22 URLs. Content roadmap (phases 1-5, ~70 keywords + Arabic parallel track) given to user this
session. NEXT: user submits sitemap to Google Search Console (indexing); then Phase 2 ("X cost Dubai")
+ Phase 3 (RTA/registration). Keyword volumes: can't pull live from here — gave estimates + told user
to use free Google Keyword Planner / Keyword Surfer ext.
Then EXPAND: more Tier-1 symptom pages + Tier-2 "X cost Dubai" + Tier-3 RTA pages. Marketing plan &
keyword tiers are earlier in this session; landing already has demo CTA above the fold.

**Why on cPanel not a $5 VPS:** the user already owns this box and chose to use it. The
scoped-proxy approach keeps blast radius to the one subdomain. A dedicated VPS is still the
cleaner long-term home if this grows.
