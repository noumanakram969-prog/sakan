"""SEO guide pages — one page per real, high-demand search query.

Every article here targets something people ACTUALLY type into Google (car
problems + costs in the UAE), not something clever nobody searches. The page's
<title> IS the query. Each ends with a funnel back to Mistri. All live on our own
domain so the traffic and ranking build THIS site.

Audience is mostly car owners (that is where the search volume is); the job now is
traffic + topical authority, converted later. A small "run a garage?" call-out
catches the buyer and builds the brand.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse

from .config import settings

router = APIRouter(tags=["guides"])

BASE = (settings.public_base_url or "https://mistri.offpageos.com").rstrip("/")

_CSS = """
*{box-sizing:border-box}
:root{--paper:#fff;--wash:#f4f8f5;--ink:#0f1a16;--ink2:#48554f;--ink3:#7c8a83;
 --line:#e3eae5;--green:#0b6b4f;--green2:#0e8862;--greenlite:#e7f3ec;--gold:#a9781f;--goldbg:#fbf4e6;
 --sans:"Assistant",-apple-system,"Segoe UI",sans-serif;--disp:"Archivo",sans-serif;}
html{background:var(--wash)}
body{margin:0;background:var(--wash);color:var(--ink);font-family:var(--sans);font-size:17px;
 line-height:1.7;-webkit-font-smoothing:antialiased;overflow-x:hidden}
a{color:var(--green2)}
img{max-width:100%}
/* top bar (always visible → the way back to the site) */
.top{position:sticky;top:0;z-index:6;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);
 border-bottom:1px solid var(--line)}
.top .in{max-width:1120px;margin:0 auto;padding:12px 18px;display:flex;align-items:center;
 justify-content:space-between;gap:12px}
.logo{font-family:var(--disp);font-weight:900;font-size:20px;color:var(--ink);text-decoration:none}
.logo .ar{color:var(--green2);font-weight:700;margin-left:4px}
.forgar{font-family:var(--sans);font-weight:700;font-size:14.5px;background:var(--green);color:#fff;
 text-decoration:none;padding:9px 15px;border-radius:10px;white-space:nowrap}
/* two-column layout: sidebar + article */
.wrap{max-width:1120px;margin:0 auto;padding:0 18px;display:flex;gap:38px;align-items:flex-start}
.side{width:248px;flex:none;position:sticky;top:60px;padding:26px 0}
.side .navlabel{font-family:var(--disp);font-weight:800;font-size:12.5px;text-transform:uppercase;
 letter-spacing:.06em;color:var(--ink3);margin:0 0 10px}
.side nav{display:flex;flex-direction:column;gap:2px}
.side nav a{text-decoration:none;color:var(--ink2);font-weight:600;font-size:15px;padding:9px 12px;
 border-radius:9px;line-height:1.3}
.side nav a:hover{background:var(--greenlite);color:var(--green)}
.side nav a.on{background:var(--greenlite);color:var(--green)}
.side .back{display:block;margin-top:16px;font-weight:700;color:var(--green2);text-decoration:none;font-size:14.5px}
.side-cta{margin-top:20px;background:var(--green);color:#fff;border-radius:14px;padding:16px 16px 18px}
.side-cta .sct{font-family:var(--disp);font-weight:800;font-size:16px;margin-bottom:6px}
.side-cta p{color:#dff1e8;font-size:13.5px;line-height:1.5;margin:0 0 12px}
.side-cta a{display:inline-block;background:#fff;color:var(--green);font-weight:800;text-decoration:none;
 font-size:14px;padding:9px 14px;border-radius:10px}
main{flex:1;min-width:0;padding:26px 0 60px}
.crumb{font-size:13.5px;color:var(--ink3);margin:8px 0 16px}
.crumb a{color:var(--ink3);text-decoration:none}
h1{font-family:var(--disp);font-weight:800;font-size:clamp(26px,5.4vw,38px);line-height:1.12;
 letter-spacing:-.02em;margin:4px 0 8px;overflow-wrap:break-word}
.meta{color:var(--ink3);font-size:14px;margin:0 0 22px}
h2{font-family:var(--disp);font-weight:700;font-size:clamp(20px,3.6vw,23px);margin:30px 0 8px;
 letter-spacing:-.01em;overflow-wrap:break-word}
p{margin:0 0 15px;color:#1c2a24;overflow-wrap:break-word}
ul,ol{margin:0 0 16px;padding-left:20px} li{margin:7px 0}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:20px 0}
.card a{display:block;text-decoration:none}
.cost{background:var(--goldbg);border:1px solid #efdcb4;border-radius:14px;padding:15px 18px;margin:22px 0}
.cost b{color:var(--gold)}
.disc{font-size:13.5px;color:var(--ink3)}
.cta-box{background:var(--green);color:#fff;border-radius:16px;padding:22px;margin:32px 0}
.cta-box h3{font-family:var(--disp);font-size:20px;margin:0 0 8px}
.cta-box p{color:#dff1e8;margin:0 0 14px}
.cta-box a{display:inline-block;background:#fff;color:var(--green);font-weight:800;text-decoration:none;
 padding:11px 18px;border-radius:11px}
.cta-box .cta-note{color:#bfe3d1;font-size:13px;margin-top:12px}
.side-cta .cta-note{color:#bfe3d1;font-size:12px;margin-top:10px}
.related{border-top:1px solid var(--line);margin-top:34px;padding-top:16px}
.related h3{font-family:var(--disp);font-size:16px;color:var(--ink2);margin:0 0 8px}
.related a{display:block;padding:8px 0;text-decoration:none;color:var(--green2);font-weight:600}
footer{max-width:1120px;margin:0 auto;padding:22px 18px 50px;color:var(--ink3);font-size:13.5px;border-top:1px solid var(--line)}
/* share bar */
.share{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:26px 0 6px;
 padding-top:16px;border-top:1px solid var(--line)}
.share .sl{font-weight:700;color:var(--ink2);font-size:14px;margin-right:2px}
.share .sh{font-family:var(--sans);font-weight:700;font-size:13.5px;text-decoration:none;cursor:pointer;
 border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:9px;padding:8px 13px;line-height:1}
.share .sh:hover{border-color:var(--green2);color:var(--green)}
.share .wa{background:#25D366;border-color:#25D366;color:#fff}
.share .fb{background:#1877F2;border-color:#1877F2;color:#fff}
.share .x{background:#111;border-color:#111;color:#fff}
/* MOBILE: sidebar becomes a horizontal scroll of chips under the top bar */
@media(max-width:860px){
 .wrap{flex-direction:column;gap:0;padding:0 16px}
 .side{width:auto;position:static;padding:14px 0 6px;border-bottom:1px solid var(--line)}
 .side .navlabel{margin-bottom:9px}
 .side nav{flex-direction:row;gap:8px;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:4px}
 .side nav a{flex:none;white-space:nowrap;background:#fff;border:1px solid var(--line);font-size:14px;padding:8px 13px}
 .side .back{margin-top:12px}
 .side-cta{display:none}
 main{padding:18px 0 50px}
 body{font-size:16px}
 .forgar{font-size:13.5px;padding:8px 12px}
}
"""

# Per-article CTA copy — a CONTEXTUAL pitch (tied to the page's problem) beats a
# generic "Run a garage?" on click-through. (title, description) keyed by slug.
# Three hook CTAs (title, description) — each connects the question to what Mistri
# does. They ROTATE across the pages so every article shows a fresh angle.
_CTAS = [
    ("Do you know why customers leave a bad review — even after a good repair?",
     "It's usually a slow reply, not the work. Mistri answers every customer in seconds "
     "— quotes your price and books the car in — so no one is left waiting."),
    ("Did you know one AI can answer your customers in every language?",
     "Mistri replies in Arabic, English, Hindi and Urdu, quotes your price and books the "
     "car in — so every customer understands you."),
    ("Do you know you can auto-book customers straight from WhatsApp?",
     "Mistri answers their questions, quotes your price and books the appointment for you "
     "— no calls, no back-and-forth."),
]
_OFFER = "Test it for 30 days. Cancel anytime."

# Separate CTAs for the PRICE pages — "AI customer service for garage owners",
# tied to the price/quote theme those pages attract.
_CTAS_PRICE = [
    ("Are you a garage owner? This is AI customer service for you.",
     "Mistri answers your customers' price questions on WhatsApp in seconds — from your own "
     "price list — and books the car in. 24/7, in any language."),
    ("Own a garage? Let AI quote your customers for you.",
     "When a customer asks “how much?”, Mistri replies instantly with your price and books "
     "them in — day and night, in any language, on your own number."),
    ("Tired of typing prices to customers all day?",
     "Mistri handles every “how much for…” on WhatsApp for you — quotes from your "
     "price list and books the car in automatically."),
]


def _cta_for(slug: str | None):
    # _CTA_BY_SLUG is built after ARTICLES is complete (below); resolved at call time.
    return _CTA_BY_SLUG.get(slug, _CTAS[0])


def _cta_box(slug: str | None) -> str:
    title, desc = _cta_for(slug)
    return ('<div class="cta-box"><h3>%s</h3><p>%s</p>'
            '<a href="/">See how it works &rarr;</a>'
            '<div class="cta-note">%s</div></div>' % (title, desc, _OFFER))


# --- the articles: title == the real search query --------------------------
ARTICLES = [
    {
        "slug": "car-ac-not-cooling",
        "title": "Car AC Not Cooling in Dubai? Causes & What to Do",
        "h1": "Car AC not cooling? Here's why — and what to do",
        "meta": "Car AC not cooling in Dubai? The common causes (low gas, weak compressor, "
                "cooling fan, clogged filter), quick checks, and typical repair costs.",
        "body": """
<p>In the UAE heat a car air conditioner that blows warm air is more than annoying — it's
one of the most common reasons drivers head to a garage. Here are the usual causes, from
cheapest to most serious, and how to tell them apart.</p>

<h2>Common reasons a car AC stops cooling</h2>
<ul>
<li><b>Low refrigerant / a gas leak</b> — the number-one cause. The gas that cools the air
slowly leaks out, so the AC runs but the air isn't cold. Needs a re-gas and a leak check.</li>
<li><b>Weak or failing compressor</b> — the pump that drives the system. If it's worn, cooling
is weak or comes and goes.</li>
<li><b>Faulty condenser cooling fan</b> — a classic UAE symptom: <b>cold while driving, warm when
you stop</b>. At a standstill the fan should pull air through the condenser; if it isn't working,
cooling drops the moment you're idle.</li>
<li><b>Clogged cabin air filter or condenser</b> — dust and sand block airflow, so even a healthy
system can't push cold air through.</li>
<li><b>Electrical or sensor fault</b> — a relay, pressure switch or wiring issue can stop the
system cycling correctly.</li>
</ul>

<h2>Quick things you can check first</h2>
<ul>
<li>Is the air <b>weak</b> (airflow problem — filter/blower) or <b>not cold</b> (gas/compressor)?</li>
<li>Cold moving but warm at idle? Point a mechanic at the <b>condenser fan</b>.</li>
<li>A bad smell when the AC starts is usually the cabin filter or mould in the system — different fix.</li>
</ul>

<div class="cost"><b>Typical Dubai cost:</b> an AC gas re-gas usually runs a few hundred dirhams;
a leak repair, compressor or fan is more and depends entirely on the car.
<div class="disc">These are general ranges that vary by car and garage — always get an exact quote first.</div></div>

<h2>When to get it inspected</h2>
<p>If a simple re-gas doesn't hold for more than a few weeks, there's a leak — keep re-gassing and
you're pouring money out. Ask any garage for a <b>free AC inspection</b> so they can pressure-test
the system and quote the real fix before doing any work.</p>
""",
    },
    {
        "slug": "why-is-my-car-overheating",
        "title": "Why Is My Car Overheating? Common Causes (UAE)",
        "h1": "Why is my car overheating? Common causes",
        "meta": "Why your car overheats — low coolant, a stuck thermostat, a failing cooling fan "
                "or water pump — what to do right away, and when it's serious.",
        "body": """
<p>An overheating engine is one problem you should never drive through — in UAE temperatures it can
turn a small fix into a blown engine fast. Here's what usually causes it and what to do the moment
the needle climbs.</p>

<h2>Do this first — right away</h2>
<ul>
<li>Turn the AC <b>off</b> and the heater <b>on</b> (it pulls heat off the engine), and pull over safely.</li>
<li><b>Never open the radiator or coolant cap while hot</b> — it can spray boiling coolant.</li>
<li>Let it cool before checking anything, or call recovery.</li>
</ul>

<h2>Common causes of overheating</h2>
<ul>
<li><b>Low coolant or a coolant leak</b> — the most common cause. Look for pink/green fluid under the car.</li>
<li><b>Stuck thermostat</b> — if it doesn't open, coolant can't circulate and heat builds quickly.</li>
<li><b>Cooling-fan failure</b> — the tell-tale UAE symptom is <b>overheating in traffic</b> but fine on the
open road, because the fan (not airflow) has to do the cooling when you're crawling.</li>
<li><b>Water pump</b> — if it fails, coolant stops moving.</li>
<li><b>Blocked or damaged radiator</b> — sand, debris or an internal blockage.</li>
<li><b>Head gasket</b> — the serious one; often shows white exhaust smoke and needs urgent attention.</li>
</ul>

<div class="cost"><b>Typical Dubai cost:</b> a coolant top-up or thermostat is usually modest; a water
pump, radiator or head-gasket job is much more.
<div class="disc">Ranges vary a lot by car — get it inspected and quoted before any work.</div></div>

<h2>When to get it inspected</h2>
<p>Overheating even once means something is wrong — get it checked before you drive it again. A garage
can pressure-test the cooling system and find the leak or the failed part. Ask for a
<b>free inspection</b> so you know the real cost before committing.</p>
""",
    },
    {
        "slug": "car-wont-start",
        "title": "Car Won't Start? The Most Common Reasons",
        "h1": "Car won't start? The most common reasons",
        "meta": "Car won't start? The usual reasons — a weak battery, starter, alternator or fuel "
                "issue — how to tell them apart from the sound it makes, and what a fix costs.",
        "body": """
<p>A car that won't start almost always comes down to a handful of causes. The <b>sound it makes</b>
when you turn the key tells you most of the story.</p>

<h2>Match the symptom to the cause</h2>
<ul>
<li><b>Nothing / a single click, lights dim</b> — almost always a <b>flat or weak battery</b>. UAE heat is
brutal on batteries and shortens their life, so this is the most common cause here.</li>
<li><b>Rapid clicking</b> — battery too weak to spin the starter, or a failing <b>starter motor</b>.</li>
<li><b>It cranks but won't fire</b> — usually <b>fuel or spark</b>: fuel pump, spark plugs, or an
ignition/immobiliser issue.</li>
<li><b>Starts then dies</b> — could be fuel delivery, a sensor, or an anti-theft/immobiliser fault.</li>
<li><b>Was fine, now slow to start over days</b> — a <b>dying battery or alternator</b> not charging it.</li>
</ul>

<h2>Quick things to check</h2>
<ul>
<li>Are the dashboard lights bright or dim/dead? Dim points straight at the battery.</li>
<li>Any corrosion on the battery terminals? A loose or dirty terminal alone can stop a start.</li>
<li>Does it need two or three tries each morning? That's a battery on its way out — replace it before
it strands you.</li>
</ul>

<div class="cost"><b>Typical Dubai cost:</b> a new battery is the most common fix and depends on the car's
size; a starter or alternator is more.
<div class="disc">Prices vary by car and garage — get an exact quote before any work.</div></div>

<h2>When to get it checked</h2>
<p>If it's the battery, a garage can test it in minutes and tell you if it just needs charging or
replacing. If it cranks but won't fire, get it inspected — guessing at fuel and ignition parts gets
expensive. Ask for a <b>free inspection</b> first.</p>
""",
    },
    {
        "slug": "car-making-noise-when-starting",
        "title": "Car Making a Noise When Starting? What It Means",
        "h1": "Car making a noise when you start it? What it means",
        "meta": "A clicking, grinding or squealing noise when you start the car — what each sound "
                "means, how urgent it is, and when to get it inspected.",
        "body": """
<p>A new noise when you start the car is worth listening to closely — the <b>type</b> of sound points
to very different problems, some cheap and some not.</p>

<h2>What each starting noise usually means</h2>
<ul>
<li><b>A single or rapid clicking</b> — most often a <b>weak battery</b> or a failing starter motor. If the
lights dim at the same time, it's the battery.</li>
<li><b>A grinding sound</b> — often the <b>starter</b> not engaging the flywheel properly. Don't keep cranking;
it can cause more damage.</li>
<li><b>A loud squeal that fades</b> — usually a worn or loose <b>drive belt</b> slipping when it's cold.
Cheap to fix, but don't ignore it.</li>
<li><b>A knocking or rattling as it fires up</b> — can be worn engine parts or low oil; get it checked.</li>
<li><b>A whirring after it's started</b> — could be a pulley, tensioner or the AC compressor.</li>
</ul>

<h2>How urgent is it?</h2>
<ul>
<li>Clicking / no start → sort the battery before it leaves you stranded.</li>
<li>Grinding on the starter → get it seen soon.</li>
<li>Belt squeal → not an emergency, but a snapped belt is, so fix it early.</li>
<li>Knocking → treat as urgent; keep driving and you risk the engine.</li>
</ul>

<div class="cost"><b>Typical Dubai cost:</b> a belt is inexpensive; a battery or starter is more; internal
engine noise is the one you want diagnosed quickly.
<div class="disc">Costs vary by car — get it inspected and quoted first.</div></div>

<h2>When to get it inspected</h2>
<p>Because the same "noise on start" can be a cheap belt or a serious engine issue, the safe move is a
quick <b>free inspection</b> — a mechanic can tell in minutes which one it is before you spend anything.</p>
""",
    },
    {
        "slug": "steering-wheel-shakes-when-braking",
        "title": "Steering Wheel Shakes When Braking — Causes & Fix",
        "h1": "Steering wheel shakes when braking? Here's why",
        "meta": "Steering wheel shakes or vibrates when braking — the usual cause is warped brake "
                "discs, but here are all the reasons and when it's a safety issue.",
        "body": """
<p>If the steering wheel shakes or vibrates when you press the brakes, it's telling you something in
the braking or wheel setup isn't true. It's common, usually fixable — and worth sorting quickly
because it's your brakes.</p>

<h2>Common causes</h2>
<ul>
<li><b>Warped brake discs (rotors)</b> — by far the most common cause. Heat makes the discs slightly
uneven, so the brake pads grab-release many times a second and you feel it in the wheel.</li>
<li><b>Worn brake pads</b> — uneven or worn-out pads cause the same shudder.</li>
<li><b>Stuck brake caliper</b> — makes one wheel drag and heat up, warping that disc.</li>
<li><b>Wheel balancing or a bent rim</b> — if the shake is there at speed too (not only braking), suspect
balancing or a rim from a pothole/kerb.</li>
<li><b>Worn suspension or steering parts</b> — tie rods, ball joints or bushings can add a shimmy.</li>
</ul>

<h2>How to narrow it down</h2>
<ul>
<li>Shakes <b>only when braking</b> → discs or pads.</li>
<li>Shakes at <b>high speed even without braking</b> → wheel balancing or a bent rim.</li>
<li>Shake plus a <b>pull to one side</b> → possibly a sticking caliper or alignment.</li>
</ul>

<div class="cost"><b>Typical Dubai cost:</b> pads and discs depend on the car; wheel balancing is cheap.
<div class="disc">Ranges vary by car and garage — always get an exact quote before work.</div></div>

<h2>When to get it inspected</h2>
<p>This is a brakes issue, so don't leave it. A garage can measure the discs and check the pads and
calipers quickly. Ask for a <b>free inspection</b> so you get an exact price before anything is replaced.</p>
""",
    },
]

ARTICLES += [
    {
        "slug": "car-using-too-much-fuel",
        "title": "Car Using Too Much Fuel? Common Reasons (UAE)",
        "h1": "Car using too much fuel? Here's why",
        "meta": "Why your car suddenly drinks more fuel — a dirty air filter, worn spark plugs, low "
                "tyre pressure, a faulty sensor or heavy AC load — and what to check first.",
        "body": """
<p>If your car has started drinking fuel faster than usual, something has changed — and most causes
are cheap to fix once you find them.</p>
<h2>Common reasons for high fuel use</h2>
<ul>
<li><b>Dirty air filter</b> — a clogged filter starves the engine of air, so it burns more fuel. Cheap and common.</li>
<li><b>Worn spark plugs</b> — weak or misfiring plugs waste fuel on every cycle.</li>
<li><b>Low tyre pressure</b> — soft tyres drag; check them first, it's free.</li>
<li><b>Faulty oxygen or air-flow sensor</b> — feeds the engine wrong readings, so it over-fuels.</li>
<li><b>Dragging brakes</b> — a sticking caliper makes the engine fight the brakes the whole time.</li>
<li><b>Heavy AC use</b> — in UAE heat the AC adds real load; some extra use is normal in summer.</li>
<li><b>Service overdue</b> — old oil and filters make the whole engine work harder.</li>
</ul>
<h2>Check these first</h2>
<ul>
<li>Tyre pressure (free, do it today).</li>
<li>Is the service overdue? That alone can raise consumption.</li>
<li>Any warning light on? A sensor fault often shows up as the check-engine light.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> an air filter or spark plugs are inexpensive; a sensor or brake fix costs more.
<div class="disc">Prices vary by car and garage — always get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>If tyre pressure and a service don't fix it, a garage can scan the sensors and check the plugs and
brakes in one go. Ask for a <b>free inspection</b> so you get the real cause before spending.</p>
""",
    },
    {
        "slug": "exhaust-smoke",
        "title": "White, Black or Blue Smoke From Exhaust — What It Means",
        "h1": "Smoke from your exhaust? What the colour means",
        "meta": "White, black or blue smoke from your car exhaust each mean a different problem — "
                "coolant, too much fuel, or burning oil. Here's how to tell them apart.",
        "body": """
<p>The <b>colour</b> of the smoke from your exhaust tells you a lot about what's wrong. Here's what
each one usually means.</p>
<h2>White smoke</h2>
<p>A little white vapour on a cold start that clears quickly is just condensation — normal. Thick white
smoke that <b>doesn't clear</b> usually means <b>coolant is getting into the engine</b> — often a head
gasket. That's serious; get it checked before driving far.</p>
<h2>Black smoke</h2>
<p>Black smoke means the engine is <b>burning too much fuel</b>. Common causes are a clogged air filter,
dirty fuel injectors, or a faulty sensor telling the engine to over-fuel. It wastes fuel and should be
sorted, but it's usually less serious than white or blue.</p>
<h2>Blue or grey smoke</h2>
<p>Blue-ish smoke means the engine is <b>burning oil</b> — usually worn piston rings or valve seals
letting oil into the cylinders. You'll often top up oil more often too. Get it inspected; ignoring it
gets expensive.</p>
<div class="cost"><b>Typical Dubai cost:</b> a filter or injector clean is modest; head-gasket or
internal-engine work is much more.
<div class="disc">Ranges vary a lot by car — get it inspected and quoted first.</div></div>
<h2>When to get it checked</h2>
<p>White or blue smoke that doesn't clear should be inspected quickly. A garage can confirm the cause
and quote the fix — ask for a <b>free inspection</b> first.</p>
""",
    },
    {
        "slug": "car-pulling-to-one-side",
        "title": "Car Pulling to One Side? Causes & Fix",
        "h1": "Car pulling to one side? Here's why",
        "meta": "A car that pulls left or right usually needs wheel alignment — but it can also be "
                "tyre pressure, uneven tyres, brakes or suspension. How to tell the difference.",
        "body": """
<p>A car that drifts to one side when you let the wheel go is telling you something is uneven. Most
causes are straightforward.</p>
<h2>Common causes</h2>
<ul>
<li><b>Wheel alignment out</b> — the most common cause, often after hitting a pothole or kerb. A quick
alignment usually fixes it.</li>
<li><b>Uneven tyre pressure</b> — one soft tyre pulls the car. Check pressures first, it's free.</li>
<li><b>Uneven tyre wear</b> — worn unevenly, tyres grip differently side to side.</li>
<li><b>Sticking brake caliper</b> — if it pulls <b>only when braking</b>, suspect a brake on one side.</li>
<li><b>Worn suspension or steering parts</b> — bushings, ball joints or tie rods.</li>
</ul>
<h2>How to narrow it down</h2>
<ul>
<li>Pulls all the time → alignment, tyre pressure or tyre wear.</li>
<li>Pulls <b>only when braking</b> → a brake caliper or pads on one side.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> a wheel alignment is cheap; a brake or suspension fix costs more.
<div class="disc">Prices vary by car and garage — get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>Start with tyre pressures. If it still pulls, a garage can check alignment, brakes and suspension
together — ask for a <b>free inspection</b> so you only pay for what it actually needs.</p>
""",
    },
    {
        "slug": "car-jerks-when-accelerating",
        "title": "Car Jerks When Accelerating? Common Causes",
        "h1": "Car jerks when accelerating? Here's why",
        "meta": "A car that jerks or hesitates when you accelerate — worn spark plugs, dirty fuel "
                "injectors, a clogged air filter or a transmission issue. What to check.",
        "body": """
<p>A jerk or hesitation when you press the accelerator usually comes down to fuel, spark or the
transmission not delivering power smoothly.</p>
<h2>Common causes</h2>
<ul>
<li><b>Worn spark plugs or coils</b> — a misfire feels like a stumble or jerk under acceleration.</li>
<li><b>Dirty fuel injectors or filter</b> — restricts fuel when you ask for more power.</li>
<li><b>Clogged air filter</b> — the engine can't breathe when you accelerate.</li>
<li><b>Dirty air-flow (MAF) sensor</b> — wrong air reading upsets the fuel mix.</li>
<li><b>Transmission issue</b> — if it jerks between gears, the gearbox or its fluid may be the cause.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> plugs, filters or an injector clean are modest; transmission
work is more.
<div class="disc">Prices vary by car — get it inspected and quoted first.</div></div>
<h2>When to get it checked</h2>
<p>A garage can scan for misfires and check the fuel and air side quickly. If it turns out to be the
transmission, catch it early. Ask for a <b>free inspection</b> before any parts are replaced.</p>
""",
    },
    {
        "slug": "check-engine-light-on",
        "title": "Check Engine Light On? What It Means & What to Do",
        "h1": "Check engine light on? What it means",
        "meta": "The check engine light can mean anything from a loose fuel cap to a serious fault. "
                "What it means, whether it's safe to drive, and what to do about it.",
        "body": """
<p>The check engine light is the one warning drivers worry about most — but it covers everything from
something trivial to something serious. Here's how to read it.</p>
<h2>Steady light vs flashing light</h2>
<ul>
<li><b>Steady light</b> — a fault the car wants looked at, but usually not an emergency. You can drive
gently and get it scanned soon.</li>
<li><b>Flashing light</b> — a serious misfire that can damage the catalytic converter. <b>Stop driving
hard and get it checked right away.</b></li>
</ul>
<h2>Common causes</h2>
<ul>
<li><b>Loose or faulty fuel cap</b> — surprisingly common; tighten it and the light may clear.</li>
<li><b>Oxygen sensor</b> — affects fuel mix and economy.</li>
<li><b>Spark plugs or ignition coils</b> — a misfire.</li>
<li><b>Catalytic converter</b> — often follows a long-ignored misfire.</li>
<li><b>Air-flow (MAF) sensor</b> — upsets the air/fuel reading.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> a diagnostic scan is inexpensive and tells you the exact
fault code before you spend on parts.
<div class="disc">The repair cost depends entirely on the code — get it scanned first.</div></div>
<h2>What to do</h2>
<p>Get the car <b>scanned</b> — it reads the exact fault code so nobody has to guess. Any garage can do
it in minutes. Ask for a <b>free inspection or diagnostic</b> so you know what you're dealing with.</p>
""",
    },
    {
        "slug": "car-ac-smells-bad",
        "title": "Car AC Smells Bad? Causes & How to Fix It",
        "h1": "Car AC smells bad? Here's why",
        "meta": "A musty or bad smell from your car AC is usually mould in the system or a dirty cabin "
                "filter. The causes, what each smell means, and how it's fixed.",
        "body": """
<p>A bad smell when you turn the AC on is common in the UAE — the mix of heat, humidity and dust is
hard on the system. The smell often points to the cause.</p>
<h2>What the smell means</h2>
<ul>
<li><b>Musty / mouldy</b> — the most common. Damp on the evaporator grows mould and bacteria. Needs an
AC clean and disinfect.</li>
<li><b>Dusty / stale</b> — usually a <b>dirty cabin air filter</b>. Cheap and quick to replace.</li>
<li><b>Sweet smell</b> — can be a coolant leak into the cabin; get it checked.</li>
<li><b>Burning smell</b> — could be electrical or a belt; don't ignore it.</li>
</ul>
<h2>How it's fixed</h2>
<ul>
<li>A new <b>cabin air filter</b> clears most dusty smells.</li>
<li>An <b>AC clean / disinfect</b> treats the mould behind a musty smell.</li>
<li>A blocked AC drain (water pooling) can also cause it and is easy to clear.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> a cabin filter is cheap; an AC clean is a bit more.
<div class="disc">Prices vary by car — get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>If a new filter doesn't fix it, ask a garage for an <b>AC inspection</b> — they can clean the system
and check the drain. Get it inspected free before any bigger AC work.</p>
""",
    },
    {
        "slug": "brakes-squeaking-grinding",
        "title": "Brakes Squeaking or Grinding? What It Means",
        "h1": "Brakes squeaking or grinding? Here's why",
        "meta": "A squeak or grind from your brakes usually means the pads are worn. What each noise "
                "means, how urgent it is, and what a brake job costs.",
        "body": """
<p>Brake noise is your car asking for attention. The <b>type</b> of noise tells you how urgent it is.</p>
<h2>What the noise means</h2>
<ul>
<li><b>Squealing</b> — often the wear indicator on the pads telling you they're getting low. Sometimes
just brake dust or cheap pads. Get the pads checked.</li>
<li><b>Grinding (metal on metal)</b> — the pads are worn out and metal is cutting into the discs.
<b>This is urgent</b> — it's unsafe and it damages the discs, making the repair more expensive every day.</li>
<li><b>A light squeak only in the morning</b> — usually surface rust on the discs overnight that clears
after the first few stops. Normal.</li>
</ul>
<h2>How urgent?</h2>
<ul>
<li>Squeal → book it in soon, before the pads run out.</li>
<li>Grind → get it seen now; you're risking the discs and your safety.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> new pads are moderate; if the discs are damaged too, it costs more.
<div class="disc">Prices vary by car and garage — get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>Brakes aren't something to leave. A garage can measure the pads and discs in minutes. Ask for a
<b>free brake inspection</b> so you get the exact price before anything is replaced.</p>
""",
    },
    {
        "slug": "car-vibrating-at-high-speed",
        "title": "Car Vibrating at High Speed? Causes",
        "h1": "Car vibrating at high speed? Here's why",
        "meta": "A car that vibrates at high speed usually needs wheel balancing — but it can be worn "
                "tyres, a bent rim from a pothole, or suspension. How to tell.",
        "body": """
<p>A vibration that appears at higher speeds and smooths out again usually comes from the wheels.</p>
<h2>Common causes</h2>
<ul>
<li><b>Wheel balancing out</b> — the most common cause, especially after new tyres or a pothole. Quick
and cheap to fix.</li>
<li><b>Worn or damaged tyre</b> — uneven wear or a bulge causes a vibration at speed.</li>
<li><b>Bent rim</b> — UAE potholes and kerbs bend rims, which throws off the balance.</li>
<li><b>Worn suspension</b> — bushings or ball joints let the wheel move.</li>
<li><b>Driveshaft / CV joint</b> — if the vibration is under acceleration.</li>
</ul>
<h2>How to narrow it down</h2>
<ul>
<li>Vibration in the <b>steering wheel</b> → usually the front wheels/balancing.</li>
<li>Vibration in the <b>seat/floor</b> → often the rear wheels.</li>
<li>Only when braking → that's brakes/discs, not balancing.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> wheel balancing is cheap; a rim or suspension fix costs more.
<div class="disc">Prices vary by car — get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>Start with a balance and a tyre check — it fixes most cases. If it doesn't, a garage can check the
rims and suspension. Ask for a <b>free inspection</b> first.</p>
""",
    },
    {
        "slug": "car-battery-keeps-dying",
        "title": "Car Battery Keeps Dying? Reasons Why",
        "h1": "Car battery keeps dying? Here's why",
        "meta": "If your car battery keeps going flat — a worn-out battery, a bad alternator, "
                "something draining it, or corroded terminals. How to find the cause.",
        "body": """
<p>A battery that keeps going flat has a reason — and in the UAE, heat is often part of it. Here are
the usual causes.</p>
<h2>Common causes</h2>
<ul>
<li><b>The battery is worn out</b> — UAE heat shortens battery life to around 2–3 years. If yours is
that old, it's likely just done.</li>
<li><b>Alternator not charging</b> — if the alternator is failing, the battery never fully recharges
while you drive.</li>
<li><b>Something draining it</b> — an interior light, boot light or an accessory left on pulls power
overnight (a "parasitic drain").</li>
<li><b>Corroded or loose terminals</b> — dirty connections stop it charging properly.</li>
<li><b>Lots of short trips</b> — the battery never gets time to recharge fully.</li>
</ul>
<h2>Quick checks</h2>
<ul>
<li>How old is the battery? Over ~3 years in this heat, suspect the battery itself.</li>
<li>Any corrosion (white/green powder) on the terminals?</li>
<li>Does it need a jump most mornings? That points to the battery or alternator.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> a new battery is the most common fix and depends on the
car's size; an alternator is more.
<div class="disc">Prices vary by car — get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>A garage can test the battery and alternator and check for a drain in minutes — that tells you
whether you need a battery, an alternator, or just a clean terminal. Ask for a <b>free check</b> first.</p>
""",
    },
    {
        "slug": "burning-smell-from-car",
        "title": "Burning Smell From Your Car? What It Could Be",
        "h1": "Burning smell from your car? Here's what it could be",
        "meta": "A burning smell from your car — burning oil, hot brakes, a slipping belt or "
                "electrical. What each smell means and how urgent it is.",
        "body": """
<p>A burning smell should never be ignored. The <b>type</b> of smell points to the cause and how
serious it is.</p>
<h2>What the smell means</h2>
<ul>
<li><b>Burning oil</b> — usually an oil leak dripping onto the hot engine. Check for leaks and get it seen.</li>
<li><b>Hot, sharp brake smell</b> — a dragging brake or riding the brakes downhill. If a wheel is hot,
get it checked soon.</li>
<li><b>Burning rubber</b> — often a slipping or worn drive belt.</li>
<li><b>Electrical / burning plastic</b> — the serious one. It can mean overheating wiring. <b>Stop and
get it checked before driving further.</b></li>
<li><b>Sweet smell</b> — a coolant leak; watch the temperature gauge.</li>
</ul>
<h2>How urgent?</h2>
<ul>
<li>Electrical/plastic smell → treat as urgent, don't keep driving.</li>
<li>Oil, brake or belt smell → get it inspected soon before it turns into a bigger problem.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> a belt or an oil-leak seal is modest; electrical faults
depend on the cause.
<div class="disc">Prices vary by car — get it inspected and quoted first.</div></div>
<h2>When to get it checked</h2>
<p>Because a burning smell can be minor or serious, the safe move is a quick <b>free inspection</b> —
a mechanic can trace the smell and tell you how urgent it really is.</p>
""",
    },
    {
        "slug": "car-shaking-when-idle",
        "title": "Car Shaking When Idle? Common Causes",
        "h1": "Car shaking when idle? Here's why",
        "meta": "A car that shakes or vibrates when idling or stopped at lights — worn spark plugs, "
                "dirty injectors, engine mounts or a vacuum leak. What to check.",
        "body": """
<p>A car that shudders while it's just sitting at idle usually has a rough-running engine or worn
mounts. Here's what causes it.</p>
<h2>Common causes</h2>
<ul>
<li><b>Worn spark plugs</b> — a slight misfire shows up most at idle.</li>
<li><b>Dirty fuel injectors</b> — uneven fuel delivery makes idle rough.</li>
<li><b>Worn engine mounts</b> — the mounts that hold the engine wear out and let the vibration reach the
cabin. Often <b>worse when in gear</b> at a stop.</li>
<li><b>Vacuum leak</b> — upsets the air/fuel mix and roughens the idle.</li>
<li><b>Dirty throttle body or idle control</b> — the engine can't hold a smooth idle.</li>
</ul>
<h2>How to narrow it down</h2>
<ul>
<li>Shakes more when you put it in <b>Drive</b> at a stop → suspect engine mounts.</li>
<li>Check-engine light on with the shake → likely a misfire (plugs/injectors).</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> plugs or a throttle clean are modest; engine mounts cost more.
<div class="disc">Prices vary by car — get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>A garage can scan for a misfire and check the mounts quickly. Ask for a <b>free inspection</b> so you
get the real cause before replacing anything.</p>
""",
    },
    {
        "slug": "gearbox-jerks-changing-gears",
        "title": "Gearbox Jerks When Changing Gears? Causes",
        "h1": "Gearbox jerks when changing gears? Here's why",
        "meta": "An automatic that jerks, slips or thumps when changing gears — usually low or old "
                "transmission fluid, but sometimes worn parts or a sensor. What to do.",
        "body": """
<p>A jerk or thump when an automatic changes gear shouldn't be ignored — transmissions are one of the
most expensive parts to repair, so catching it early matters.</p>
<h2>Common causes</h2>
<ul>
<li><b>Low, old or burnt transmission fluid</b> — by far the most common cause, and the cheapest to fix
if caught early. In UAE heat, fluid degrades faster.</li>
<li><b>Worn clutches or bands inside the gearbox</b> — from age and wear.</li>
<li><b>Faulty solenoid or sensor</b> — controls the shifts; a fault causes hard or jerky changes.</li>
<li><b>Software / adaptation</b> — some cars just need a reset or relearn.</li>
</ul>
<h2>What to do</h2>
<ul>
<li>Get the <b>transmission fluid checked</b> first — level, colour and smell tell a mechanic a lot.</li>
<li>Don't keep driving hard through the jerking; it can wear the gearbox faster.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> a fluid service is modest; internal transmission work is
much more — which is exactly why you want to catch it early.
<div class="disc">Prices vary a lot by car — get it inspected and quoted first.</div></div>
<h2>When to get it checked</h2>
<p>Have it inspected sooner rather than later — a simple fluid service now can save a big bill later.
Ask a garage for a <b>free inspection</b> before any transmission work.</p>
""",
    },
    {
        "slug": "steering-hard-to-turn",
        "title": "Steering Hard to Turn? Common Causes",
        "h1": "Steering hard to turn? Here's why",
        "meta": "A steering wheel that's stiff or hard to turn — low power steering fluid, a failing "
                "pump, a worn belt or low tyre pressure. What to check.",
        "body": """
<p>If the steering has become heavy or stiff, the power steering system usually isn't doing its job.</p>
<h2>Common causes</h2>
<ul>
<li><b>Low power steering fluid</b> — often from a leak. Check the level first; it's the most common cause
on hydraulic systems.</li>
<li><b>Failing power steering pump</b> — heavy steering plus a whine when you turn.</li>
<li><b>Worn or loose drive belt</b> — the belt that drives the pump is slipping.</li>
<li><b>Low tyre pressure</b> — soft front tyres make the wheel feel heavy, especially when parking.</li>
<li><b>Electric power steering fault</b> — on newer cars, an electrical fault (often with a warning light).</li>
</ul>
<h2>How to narrow it down</h2>
<ul>
<li>Heavy only when parking/slow → could be tyre pressure or fluid.</li>
<li>Heavy all the time with a whine → pump or belt.</li>
<li>Warning light on → electric steering fault; get it scanned.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> fluid or a belt is modest; a pump is more.
<div class="disc">Prices vary by car — get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>Heavy steering is a safety issue — get it looked at soon. A garage can check the fluid, belt and pump
quickly. Ask for a <b>free inspection</b> first.</p>
""",
    },
    {
        "slug": "leaking-under-car",
        "title": "Fluid Leaking Under Your Car? What Each Colour Means",
        "h1": "Something leaking under your car? Here's what it is",
        "meta": "A puddle under your car — the colour tells you what's leaking: water from the AC "
                "(usually normal), engine oil, coolant, transmission or brake fluid.",
        "body": """
<p>A puddle under the car looks alarming, but the <b>colour and where it is</b> usually tells you what's
leaking — and whether it matters.</p>
<h2>What the colour means</h2>
<ul>
<li><b>Clear water</b> — almost always <b>AC condensation</b> dripping under the car. In UAE heat this is
normal and nothing to worry about.</li>
<li><b>Brown or black, oily</b> — <b>engine oil</b>. Check your oil level and get the leak seen.</li>
<li><b>Pink, green or orange</b> — <b>coolant</b>. Watch the temperature gauge and get it checked before
it overheats.</li>
<li><b>Reddish, oily</b> — <b>transmission or power steering fluid</b>.</li>
<li><b>Clear and oily/slippery near a wheel</b> — could be <b>brake fluid</b>. This is a safety issue —
get it checked right away.</li>
</ul>
<h2>How to tell</h2>
<ul>
<li>Slide a piece of cardboard under overnight to catch the colour and see where it's dripping from.</li>
<li>Clear water after the AC has been running → normal.</li>
<li>Any oily fluid, or a coolant colour → get it inspected.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> a small seal or hose is modest; bigger leaks depend on the source.
<div class="disc">Prices vary by car — get it inspected and quoted first.</div></div>
<h2>When to get it checked</h2>
<p>If it's not clear AC water, have it looked at — a garage can find the source quickly. Ask for a
<b>free inspection</b> so you know what's leaking before it becomes a bigger problem.</p>
""",
    },
    {
        "slug": "clutch-slipping-signs",
        "title": "Clutch Slipping? Signs Your Clutch Is Worn",
        "h1": "Clutch slipping? Signs it's worn out",
        "meta": "Signs your manual car's clutch is slipping or worn — revs rise without speed, a "
                "burning smell, a high biting point. What it means and what a fix costs.",
        "body": """
<p>On a manual car, a worn clutch shows clear warning signs. Catching them early can save you being
stranded when the clutch finally gives up.</p>
<h2>Signs your clutch is slipping</h2>
<ul>
<li><b>Revs rise but the car doesn't speed up</b> — especially going uphill or accelerating hard. The
clearest sign the clutch is slipping.</li>
<li><b>A burning smell</b> — like hot friction, after pulling away or climbing a hill.</li>
<li><b>High or hard biting point</b> — the clutch grabs right at the top of the pedal.</li>
<li><b>Trouble getting into gear</b> — or the gears crunch.</li>
<li><b>Juddering when you pull away.</b></li>
</ul>
<h2>What to do</h2>
<ul>
<li>Ease off hard acceleration and hill starts until it's checked — that's when a worn clutch slips most.</li>
<li>Get it inspected before it fails completely and leaves you stuck.</li>
</ul>
<div class="cost"><b>Typical Dubai cost:</b> a clutch replacement is a bigger job and varies a lot by car.
<div class="disc">Prices vary by car and garage — get an exact quote first.</div></div>
<h2>When to get it checked</h2>
<p>A garage can confirm whether the clutch is slipping and how much life is left. Ask for a
<b>free inspection</b> so you get an exact quote before booking the work.</p>
""",
    },
]

# ---- Phase 2: "how much does X cost in Dubai" (commercial intent) ----------
_EXACT = ("<h2>Getting an exact price</h2><p>Prices vary by car and garage, so treat the range above as "
          "a guide. The fastest way to a real number is to message a garage on WhatsApp with your car's "
          "make, model and year. Garages running <b>Mistri</b> reply with a quote in seconds, day or night.</p>")

ARTICLES += [
    {
        "slug": "oil-change-price-dubai", "group": "prices",
        "title": "Oil Change Price in Dubai — What It Costs",
        "h1": "How much is an oil change in Dubai?",
        "meta": "Oil change prices in Dubai — what you pay for mineral, semi-synthetic and full-synthetic "
                "oil, what changes the cost, and how to get a fair price.",
        "body": """
<p>An oil change is the most common car service — and the price in Dubai swings a lot depending mainly
on the type of oil your engine needs.</p>
<h2>What changes the price</h2>
<ul>
<li><b>Oil type</b> — mineral is cheapest, semi-synthetic mid, and full-synthetic the most (but it lasts longer).</li>
<li><b>Engine size</b> — a big V6 or V8 needs more oil than a small sedan.</li>
<li><b>Oil filter</b> — usually included; some cars use pricier filters.</li>
<li><b>Car make</b> — luxury and European cars cost more to service.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> mineral oil change ~AED 100–180 · semi-synthetic ~AED 180–300 ·
full-synthetic ~AED 300–600+ (large or luxury engines higher).
<div class="disc">General market ranges, not a fixed price — they vary by car and garage.</div></div>
<h2>What's usually included</h2>
<ul>
<li>Fresh oil + a new oil filter.</li>
<li>Top-up of basic fluids and a quick visual check at most garages.</li>
</ul>
<p>Tip: full-synthetic costs more per change but lasts longer between changes, so ask what interval it buys you.</p>
""" + _EXACT,
    },
    {
        "slug": "car-service-cost-dubai", "group": "prices",
        "title": "Car Service Cost in Dubai — Minor vs Major Service",
        "h1": "How much does a car service cost in Dubai?",
        "meta": "Car service cost in Dubai — the difference between a minor and major service, what each "
                "includes, and typical prices.",
        "body": """
<p>"Car service" covers two different jobs, and the price gap between them is big — so it helps to know
which one your car is due.</p>
<h2>Minor vs major service</h2>
<ul>
<li><b>Minor service</b> — oil and filter change plus basic checks (fluids, lights, tyres, brakes visual). Done more often.</li>
<li><b>Major service</b> — everything in a minor service plus items like spark plugs, air and cabin filters,
fuel filter, a fuller brake and suspension check, and fluid changes. Done at longer intervals.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> minor service ~AED 150–400 · major service ~AED 500–1,500+
(luxury and European cars higher).
<div class="disc">Ranges vary a lot by car and what the garage includes — always confirm the list.</div></div>
<h2>Before you book</h2>
<ul>
<li>Ask exactly <b>what's included</b> — services vary garage to garage.</li>
<li>Check your car's service schedule so you're not paying for a major when a minor is due (or vice-versa).</li>
</ul>
""" + _EXACT,
    },
    {
        "slug": "car-ac-gas-refill-price-dubai", "group": "prices",
        "title": "Car AC Gas Refill Price in Dubai (Recharge Cost)",
        "h1": "How much is a car AC gas refill in Dubai?",
        "meta": "Car AC gas refill / recharge price in Dubai — what a top-up costs, why a leak check "
                "matters, and what changes the price.",
        "body": """
<p>In the UAE heat, an AC re-gas is one of the most common jobs — but the price depends on whether it's
a simple top-up or there's a leak behind it.</p>
<h2>What changes the price</h2>
<ul>
<li><b>Top-up vs leak repair</b> — just adding gas is cheap; finding and fixing a leak costs more.</li>
<li><b>Gas type</b> — newer cars use R1234yf gas, which is more expensive than the older R134a.</li>
<li><b>The real fault</b> — if the compressor or condenser is the problem, that's a separate, bigger cost.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> a basic AC re-gas ~AED 100–250 · with a leak repair, more,
depending on where the leak is.
<div class="disc">Ranges vary by car and gas type — get it checked for the exact price.</div></div>
<h2>Important</h2>
<p>If a re-gas only lasts a few weeks, you have a <b>leak</b> — re-gassing again and again just wastes money.
Ask for a pressure test so the leak is found, not just topped up.</p>
""" + _EXACT,
    },
    {
        "slug": "car-battery-price-dubai", "group": "prices",
        "title": "Car Battery Price in Dubai (With Installation)",
        "h1": "How much is a car battery in Dubai?",
        "meta": "Car battery prices in Dubai including installation — what you pay by size and car type, "
                "why UAE heat matters, and how to choose.",
        "body": """
<p>UAE heat is hard on batteries — most last only 2–3 years here — so this is a price a lot of drivers
end up looking up. Cost depends mainly on the battery size your car needs.</p>
<h2>What changes the price</h2>
<ul>
<li><b>Battery size / capacity</b> — bigger engines and SUVs need bigger, pricier batteries.</li>
<li><b>Type</b> — cars with stop-start need an AGM battery, which costs more.</li>
<li><b>Brand</b> — well-known brands cost more but usually last longer in the heat.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> small sedan ~AED 200–350 · mid-size / SUV ~AED 350–600 ·
large / premium / AGM ~AED 600–1,000+.
<div class="disc">Ranges vary by car and brand — confirm the exact fit for your model.</div></div>
<h2>Usually included</h2>
<ul>
<li>Most garages include <b>free fitting</b> and take the old battery away.</li>
<li>Many will come to you and change it on the spot if you're stranded.</li>
</ul>
""" + _EXACT,
    },
    {
        "slug": "brake-pads-replacement-cost-dubai", "group": "prices",
        "title": "Brake Pads Replacement Cost in Dubai",
        "h1": "How much to replace brake pads in Dubai?",
        "meta": "Brake pad replacement cost in Dubai — front vs rear, pads only vs pads and discs, and "
                "what changes the price.",
        "body": """
<p>Brake pad prices in Dubai depend on your car and on whether the discs need doing too — here's how
it breaks down.</p>
<h2>What changes the price</h2>
<ul>
<li><b>Front or rear</b> — fronts wear faster and are done more often.</li>
<li><b>Pads only vs pads + discs</b> — if the discs are worn or warped, they're replaced together, which
costs more.</li>
<li><b>Car make</b> — luxury and performance cars have pricier brakes.</li>
<li><b>Pad quality</b> — OEM vs aftermarket.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> front pads only ~AED 150–500 · pads + discs ~AED 500–1,500 ·
luxury and performance cars higher.
<div class="disc">Ranges vary by car and garage — get an exact quote.</div></div>
<h2>Worth knowing</h2>
<p>Don't cheap out on brakes — they're a safety part. If the garage says the discs are worn, doing pads and
discs together is usually cheaper than coming back for the discs later.</p>
""" + _EXACT,
    },
    {
        "slug": "new-tyres-price-dubai", "group": "prices",
        "title": "New Tyres Price in Dubai (Per Tyre & Set)",
        "h1": "How much are new tyres in Dubai?",
        "meta": "New tyre prices in Dubai — budget vs premium brands, per tyre and per set, plus fitting "
                "and balancing costs, and how to choose.",
        "body": """
<p>Tyre prices in Dubai range widely by size and brand. In UAE heat, buying good, fresh tyres matters more
than usual.</p>
<h2>What changes the price</h2>
<ul>
<li><b>Size</b> — bigger wheels (common on SUVs) cost more.</li>
<li><b>Brand tier</b> — budget, mid-range or premium.</li>
<li><b>Run-flat tyres</b> — fitted to some cars and pricier.</li>
</ul>
<div class="cost"><b>Typical Dubai range (per tyre):</b> budget ~AED 200–350 · mid-range ~AED 350–600 ·
premium / large ~AED 600–1,200+. Fitting + balancing usually ~AED 30–60 per tyre.
<div class="disc">Ranges vary by size and brand — get a quote for your exact tyre size.</div></div>
<h2>Buying tips</h2>
<ul>
<li>Check the <b>manufacture date</b> (DOT code) — tyres that sat in the heat for years age faster.</li>
<li>Replace in pairs at least, ideally all four, for even grip.</li>
</ul>
""" + _EXACT,
    },
    {
        "slug": "car-diagnostic-cost-dubai", "group": "prices",
        "title": "Car Computer Diagnostic Cost in Dubai",
        "h1": "How much is a car diagnostic check in Dubai?",
        "meta": "Car computer diagnostic (scan) cost in Dubai — what a scan does, why it's worth it "
                "before any repair, and typical prices.",
        "body": """
<p>If your check-engine light is on or something feels off, a computer diagnostic reads the car's fault
codes so nobody has to guess. It's usually inexpensive and can save you money.</p>
<h2>What a diagnostic does</h2>
<ul>
<li>Plugs into the car and <b>reads the fault codes</b> the computer has stored.</li>
<li>Points the mechanic to the actual problem instead of replacing parts by trial and error.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> a basic scan ~AED 100–250. Some garages <b>waive the fee</b>
if you get the repair done with them.
<div class="disc">A deeper diagnosis that takes longer can cost more — confirm first.</div></div>
<h2>Why it's worth it</h2>
<p>Paying a small scan fee first stops you spending on the wrong parts. Always get the fault read before
approving any repair.</p>
""" + _EXACT,
    },
    {
        "slug": "wheel-alignment-cost-dubai", "group": "prices",
        "title": "Wheel Alignment Cost in Dubai",
        "h1": "How much is wheel alignment in Dubai?",
        "meta": "Wheel alignment cost in Dubai — two-wheel vs four-wheel alignment, when you need it, "
                "and typical prices.",
        "body": """
<p>Wheel alignment is one of the cheaper jobs, and getting it done at the right time saves you money on
tyres.</p>
<h2>When you need it</h2>
<ul>
<li>The car pulls to one side, or the steering wheel sits off-centre.</li>
<li>Your tyres are wearing unevenly.</li>
<li>After hitting a pothole or kerb, or fitting new tyres.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> ~AED 50–150, depending on two-wheel or four-wheel alignment
and the car. Often bundled cheaply with wheel balancing.
<div class="disc">Ranges vary by garage — confirm what's included.</div></div>
<h2>Worth knowing</h2>
<p>Getting an alignment after new tyres and after big potholes protects your tyres — bad alignment can wear
an expensive set of tyres out in months.</p>
""" + _EXACT,
    },
    {
        "slug": "car-painting-dent-repair-cost-dubai", "group": "prices",
        "title": "Car Painting & Dent Repair Cost in Dubai",
        "h1": "How much does car painting or dent repair cost in Dubai?",
        "meta": "Car painting and dent repair cost in Dubai — a single panel vs a full respray, paintless "
                "dent removal, and what changes the price.",
        "body": """
<p>Bodywork prices in Dubai depend on how much of the car is involved and how the damage is fixed.</p>
<h2>What changes the price</h2>
<ul>
<li><b>One panel vs the whole car</b> — a single door is far cheaper than a full respray.</li>
<li><b>Colour</b> — metallic and pearl colours are harder to match, so they cost more.</li>
<li><b>Paintless dent removal vs filler + paint</b> — small dents with good paint can often be popped out
cheaply without repainting.</li>
<li><b>Car make</b> — luxury finishes cost more.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> single panel respray ~AED 250–700 · full car respray
~AED 2,000–6,000+ · paintless dent removal ~AED 100–400 per dent.
<div class="disc">Bodywork varies a lot — send photos for an accurate quote.</div></div>
<h2>Worth knowing</h2>
<p>If the damage was from an accident, your <b>insurance</b> may cover it. For quotes, clear photos of the
damage get you a much closer price.</p>
""" + _EXACT,
    },
    {
        "slug": "clutch-replacement-cost-dubai", "group": "prices",
        "title": "Clutch Replacement Cost in Dubai",
        "h1": "How much to replace a clutch in Dubai?",
        "meta": "Clutch replacement cost in Dubai — what the job involves, what changes the price, and "
                "typical ranges for manual cars.",
        "body": """
<p>A clutch replacement (on a manual car) is a bigger job because the gearbox has to come out — so labour
is a big part of the price.</p>
<h2>What changes the price</h2>
<ul>
<li><b>Car make and model</b> — access and parts vary a lot.</li>
<li><b>Parts</b> — OEM vs aftermarket clutch kit, and whether the <b>flywheel</b> needs replacing too.</li>
<li><b>Labour</b> — removing the gearbox takes hours.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> ~AED 800–2,500+, higher for luxury or complex cars.
<div class="disc">Ranges vary a lot by car — get an exact quote after an inspection.</div></div>
<h2>Worth knowing</h2>
<p>Catch a slipping clutch early — it's cheaper than being stranded when it fails completely. If the flywheel
is worn, doing it at the same time saves a second labour bill later.</p>
""" + _EXACT,
    },
    {
        "slug": "ac-compressor-replacement-cost-dubai", "group": "prices",
        "title": "Car AC Compressor Replacement Cost in Dubai",
        "h1": "How much is a car AC compressor in Dubai?",
        "meta": "Car AC compressor replacement cost in Dubai — new vs reconditioned, what changes the "
                "price, and typical ranges.",
        "body": """
<p>When an AC stops cooling and a re-gas doesn't help, the compressor — the pump that drives the whole
system — is sometimes the cause. It's one of the pricier AC repairs.</p>
<h2>What changes the price</h2>
<ul>
<li><b>New vs reconditioned</b> — a reconditioned compressor is cheaper but check the warranty.</li>
<li><b>Car make</b> — parts and labour vary widely.</li>
<li><b>Extra work</b> — the system usually needs a re-gas and sometimes a new drier after the job.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> ~AED 800–2,500+ depending on the car and whether the part is
new or reconditioned.
<div class="disc">Ranges vary a lot by car — get it confirmed and quoted first.</div></div>
<h2>Before you commit</h2>
<p>Make sure it's really the compressor and not a cheaper fault (low gas, a fan, a sensor). Ask for an
inspection that confirms the compressor before paying for one.</p>
""" + _EXACT,
    },
    {
        "slug": "timing-belt-replacement-cost-dubai", "group": "prices",
        "title": "Timing Belt Replacement Cost in Dubai",
        "h1": "How much to replace a timing belt in Dubai?",
        "meta": "Timing belt replacement cost in Dubai — why it matters, when to change it, and what "
                "changes the price.",
        "body": """
<p>The timing belt is one of the most important services to keep on schedule — if it snaps, it can wreck
the engine, which is far more expensive than the belt.</p>
<h2>What changes the price</h2>
<ul>
<li><b>Car make and model</b> — access and part cost vary a lot.</li>
<li><b>Water pump</b> — often driven by the same belt, so many garages replace it at the same time (worth it).</li>
<li><b>Belt vs chain</b> — some engines have a timing chain that lasts much longer; confirm which you have.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> ~AED 400–1,500+ depending on the car (and whether the water
pump is done too).
<div class="disc">Ranges vary a lot by car — get an exact quote.</div></div>
<h2>Worth knowing</h2>
<p>Follow the mileage/age interval in your car's manual — don't wait for it to fail. Doing the water pump at
the same time saves a second big labour bill.</p>
""" + _EXACT,
    },
    {
        "slug": "windshield-replacement-cost-dubai", "group": "prices",
        "title": "Windshield Replacement Cost in Dubai",
        "h1": "How much to replace a windshield in Dubai?",
        "meta": "Windshield / windscreen replacement cost in Dubai — OEM vs aftermarket glass, cars with "
                "sensors and cameras, and typical prices.",
        "body": """
<p>A cracked windshield is common on UAE roads. The price depends on your car and, increasingly, on the
cameras and sensors built into modern windshields.</p>
<h2>What changes the price</h2>
<ul>
<li><b>Car make and model</b> — glass size and shape vary.</li>
<li><b>OEM vs aftermarket glass</b> — original glass costs more.</li>
<li><b>Sensors / cameras (ADAS)</b> — newer cars need the camera <b>recalibrated</b> after fitting, which adds cost.</li>
<li><b>Extras</b> — rain sensors, heating elements or tint.</li>
</ul>
<div class="cost"><b>Typical Dubai range:</b> ~AED 400–1,500+, higher for luxury cars or ones needing ADAS
camera recalibration.
<div class="disc">Ranges vary a lot by car — get a quote for your exact model.</div></div>
<h2>Worth knowing</h2>
<p>A small chip can sometimes be <b>repaired</b> cheaply before it spreads into a full crack. Your insurance
may also cover glass — worth checking first.</p>
""" + _EXACT,
    },
]

_BY_SLUG = {a["slug"]: a for a in ARTICLES}
# rotate CTAs per group: price pages get the "AI customer service" CTAs,
# problem pages get the problem-angle hooks. Separate counters keep each even.
_CTA_BY_SLUG = {}
_pi = _ci = 0
for _a in ARTICLES:
    if _a.get("group") == "prices":
        _CTA_BY_SLUG[_a["slug"]] = _CTAS_PRICE[_pi % len(_CTAS_PRICE)]; _pi += 1
    else:
        _CTA_BY_SLUG[_a["slug"]] = _CTAS[_ci % len(_CTAS)]; _ci += 1


def _related(slug: str) -> str:
    others = [a for a in ARTICLES if a["slug"] != slug][:4]
    links = "".join('<a href="/guides/%s">%s</a>' % (a["slug"], a["title"]) for a in others)
    return '<div class="related"><h3>More car help</h3>%s</div>' % links


def _ld_json(a: dict) -> str:
    url = "%s/guides/%s" % (BASE, a["slug"])
    return (
        '<script type="application/ld+json">{"@context":"https://schema.org",'
        '"@type":"Article","headline":%s,"description":%s,"inLanguage":"en",'
        '"mainEntityOfPage":%s,"author":{"@type":"Organization","name":"Mistri"},'
        '"publisher":{"@type":"Organization","name":"Mistri"}}</script>'
        % (_q(a["h1"]), _q(a["meta"]), _q(url))
    )


def _q(s: str) -> str:
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


# short sidebar labels (the full titles are too long for a nav)
_NAV = {
    "car-ac-not-cooling": "AC not cooling",
    "why-is-my-car-overheating": "Overheating",
    "car-wont-start": "Won't start",
    "car-making-noise-when-starting": "Noise on start",
    "steering-wheel-shakes-when-braking": "Shakes when braking",
    "car-using-too-much-fuel": "High fuel use",
    "exhaust-smoke": "Exhaust smoke",
    "car-pulling-to-one-side": "Pulling to a side",
    "car-jerks-when-accelerating": "Jerks on accel",
    "check-engine-light-on": "Engine light on",
    "car-ac-smells-bad": "AC smells bad",
    "brakes-squeaking-grinding": "Brake noise",
    "car-vibrating-at-high-speed": "Vibrates at speed",
    "car-battery-keeps-dying": "Battery keeps dying",
    "burning-smell-from-car": "Burning smell",
    "car-shaking-when-idle": "Shakes at idle",
    "gearbox-jerks-changing-gears": "Gears jerk",
    "steering-hard-to-turn": "Hard steering",
    "leaking-under-car": "Leaking under car",
    "clutch-slipping-signs": "Clutch slipping",
    "oil-change-price-dubai": "Oil change price",
    "car-service-cost-dubai": "Service cost",
    "car-ac-gas-refill-price-dubai": "AC gas refill price",
    "car-battery-price-dubai": "Battery price",
    "brake-pads-replacement-cost-dubai": "Brake pads cost",
    "new-tyres-price-dubai": "Tyres price",
    "car-diagnostic-cost-dubai": "Diagnostic cost",
    "wheel-alignment-cost-dubai": "Alignment cost",
    "car-painting-dent-repair-cost-dubai": "Painting / dent cost",
    "clutch-replacement-cost-dubai": "Clutch cost",
    "ac-compressor-replacement-cost-dubai": "AC compressor cost",
    "timing-belt-replacement-cost-dubai": "Timing belt cost",
    "windshield-replacement-cost-dubai": "Windshield cost",
}


def _nav_group(articles, current):
    return "".join(
        '<a class="%s" href="/guides/%s">%s</a>'
        % ("on" if a["slug"] == current else "", a["slug"], _NAV.get(a["slug"], a["title"]))
        for a in articles
    )


def _sidebar(current: str | None) -> str:
    problems = [a for a in ARTICLES if a.get("group") != "prices"]
    prices = [a for a in ARTICLES if a.get("group") == "prices"]
    # nav sits BELOW the promo box now
    nav = ('<div class="navlabel" style="margin-top:22px">Common problems</div><nav>%s</nav>'
           '<div class="navlabel" style="margin-top:18px">Prices in Dubai</div><nav>%s</nav>'
           % (_nav_group(problems, current), _nav_group(prices, current)))
    title, desc = _cta_for(current)
    cta = ('<div class="side-cta"><div class="sct">%s</div><p>%s</p>'
           '<a href="/">See how it works &rarr;</a>'
           '<div class="cta-note">%s</div></div>' % (title, desc, _OFFER))
    # promo box first (top), then the article nav
    return ('<aside class="side">'
            '<a class="back" href="/">&larr; Mistri for garages</a>'
            '%s%s</aside>' % (cta, nav))


def _share(url: str, title: str) -> str:
    import urllib.parse
    u = urllib.parse.quote(url, safe="")
    t = urllib.parse.quote(title, safe="")
    wa = "https://wa.me/?text=%s%%20%s" % (t, u)
    fb = "https://www.facebook.com/sharer/sharer.php?u=%s" % u
    x = "https://twitter.com/intent/tweet?text=%s&url=%s" % (t, u)
    return (
        '<div class="share"><span class="sl">Share this:</span>'
        '<a class="sh wa" href="%s" target="_blank" rel="noopener">WhatsApp</a>'
        '<a class="sh fb" href="%s" target="_blank" rel="noopener">Facebook</a>'
        '<a class="sh x" href="%s" target="_blank" rel="noopener">X</a>'
        '<button class="sh" type="button" '
        'onclick="if(navigator.clipboard){navigator.clipboard.writeText(location.href);'
        "this.textContent='Copied \\u2713'}\">Copy link</button>"
        '</div>' % (wa, fb, x)
    )


def _shell(title: str, meta: str, canon: str, head_extra: str, main_html: str,
           current: str | None = None) -> str:
    m = meta.replace('"', "&quot;")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>%s</title>'
        '<meta name="description" content="%s">'
        '<link rel="canonical" href="%s">'
        '<meta property="og:type" content="article"><meta property="og:title" content="%s">'
        '<meta property="og:description" content="%s"><meta property="og:url" content="%s">'
        '<meta property="og:site_name" content="Mistri"><meta property="og:locale" content="en_AE">'
        '<meta name="twitter:card" content="summary">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=Assistant:wght@400;500;600;700&display=swap">'
        '%s<style>%s</style></head><body>'
        '<div class="top"><div class="in">'
        '<a class="logo" href="/">Mistri <span class="ar">مستري</span></a>'
        '<a class="forgar" href="/">🔧 For garages &rarr;</a></div></div>'
        '<div class="wrap">%s%s</div>'
        '<footer>Mistri — a WhatsApp assistant for UAE car garages. '
        'This guide is general information, not a diagnosis; always have a qualified garage inspect your car.</footer>'
        '</body></html>'
        % (title, m, canon, title, m, canon, head_extra, _CSS, _sidebar(current), main_html)
    )


@router.get("/guides", response_class=HTMLResponse)
def guides_index() -> HTMLResponse:
    def cards(group):
        return "".join(
            '<a href="/guides/%s"><h2 style="margin:14px 0 4px">%s</h2>'
            '<p style="color:var(--ink3);margin:0">%s</p></a>'
            % (a["slug"], a["title"], a["meta"]) for a in group)
    problems = [a for a in ARTICLES if a.get("group") != "prices"]
    prices = [a for a in ARTICLES if a.get("group") == "prices"]
    main = (
        '<main><div class="crumb"><a href="/">Home</a> › Car help</div>'
        '<h1>Car help &amp; common problems</h1>'
        '<p class="meta">Straight answers to the car problems and prices drivers in the UAE ask about most.</p>'
        '<div class="group">Common problems</div><div class="card">%s</div>'
        '<div class="group">Prices in Dubai</div><div class="card">%s</div>%s</main>'
        % (cards(problems), cards(prices), _cta_box(None))
    )
    canon = "%s/guides" % BASE
    return HTMLResponse(_shell("Car Help & Common Car Problems | Mistri",
                               "Straight answers to common car problems in the UAE — AC not cooling, "
                               "overheating, won't start, noises and more.", canon, "", main))


@router.get("/guides/{slug}", response_class=HTMLResponse)
def guide(slug: str) -> HTMLResponse:
    a = _BY_SLUG.get(slug)
    if a is None:
        return HTMLResponse("<h1>Not found</h1><p><a href='/guides'>See all car help</a></p>",
                            status_code=404)
    canon = "%s/guides/%s" % (BASE, a["slug"])
    main = (
        '<main><div class="crumb"><a href="/">Home</a> › <a href="/guides">Car help</a></div>'
        '<h1>%s</h1><p class="meta">Car help · Mistri</p>%s%s%s%s</main>'
        % (a["h1"], a["body"], _share(canon, a["title"]), _cta_box(a["slug"]), _related(a["slug"]))
    )
    return HTMLResponse(_shell(a["title"], a["meta"], canon, _ld_json(a), main, current=a["slug"]))


@router.get("/google2e94c7f871e54250.html", response_class=HTMLResponse)
def google_site_verification() -> HTMLResponse:
    # Google Search Console HTML-file verification for mistri.offpageos.com
    return HTMLResponse("google-site-verification: google2e94c7f871e54250.html")


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % BASE)


@router.get("/sitemap.xml")
def sitemap() -> PlainTextResponse:
    urls = ["%s/" % BASE, "%s/guides" % BASE] + ["%s/guides/%s" % (BASE, a["slug"]) for a in ARTICLES]
    body = "".join("<url><loc>%s</loc></url>" % u for u in urls)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>' % body)
    return PlainTextResponse(xml, media_type="application/xml")
