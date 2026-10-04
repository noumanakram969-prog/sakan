# -*- coding: utf-8 -*-
"""Builds docs/Mistri-Documentation.pdf"""
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, ListFlowable, ListItem, NextPageTemplate,
)

INK = colors.HexColor("#12212E")
BLUE = colors.HexColor("#1F5F8B")
ACC = colors.HexColor("#C8552B")
GREY = colors.HexColor("#5C6B77")
LINE = colors.HexColor("#D6DEE4")
SOFT = colors.HexColor("#F2F6F8")
GREEN = colors.HexColor("#2E7D5B")

OUT = r"C:\Users\user\Projects\OneDrive\FRESH DATA\mistri\docs\Mistri-Documentation.pdf"

ss = getSampleStyleSheet()


def S(name, **kw):
    kw.setdefault("parent", ss["Normal"])
    return ParagraphStyle(name, **kw)


body = S("body", fontName="Helvetica", fontSize=10, leading=15.5, textColor=INK, spaceAfter=7)
lead = S("lead", parent=body, fontSize=11.5, leading=17, textColor=colors.HexColor("#25404F"), spaceAfter=10)
h1 = S("h1", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK, spaceBefore=4, spaceAfter=3)
h1n = S("h1n", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=ACC, spaceAfter=2)
h2 = S("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=BLUE, spaceBefore=13, spaceAfter=4)
h3 = S("h3", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK, spaceBefore=9, spaceAfter=2)
cell = S("cell", fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK)
cellh = S("cellh", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white)
quote = S("quote", fontName="Helvetica-Oblique", fontSize=10, leading=15, textColor=colors.HexColor("#25404F"))
ttitle = S("ttitle", fontName="Helvetica-Bold", fontSize=36, leading=41, textColor=colors.white, alignment=TA_LEFT)
tsub = S("tsub", fontName="Helvetica", fontSize=13.5, leading=19.5, textColor=colors.HexColor("#9DBACE"))

COURIER_OPEN = '<font face="Courier">'
COURIER_CLOSE = "</font>"


def mono(text):
    return COURIER_OPEN + text + COURIER_CLOSE


def bullets(items, style=body):
    return ListFlowable(
        [ListItem(Paragraph(t, style), leftIndent=12) for t in items],
        bulletType="bullet", start="\u2022", bulletFontSize=8,
        bulletColor=ACC, leftIndent=13, bulletOffsetY=1, spaceAfter=6,
    )


def table(rows, widths, header=True, zebra=True):
    data = []
    for i, row in enumerate(rows):
        st = cellh if (header and i == 0) else cell
        data.append([Paragraph(c, st) if isinstance(c, str) else c for c in row])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
    ]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), BLUE),
                 ("LINEBELOW", (0, 0), (-1, 0), 0, colors.white)]
    if zebra:
        for r in range(1 if header else 0, len(data)):
            if (r % 2) == (0 if header else 1):
                cmds.append(("BACKGROUND", (0, r), (-1, r), SOFT))
    t.setStyle(TableStyle(cmds))
    return t


def callout(title, text, color=ACC, bg=colors.HexColor("#FDF3EE")):
    hexcode = "#" + color.hexval()[2:]
    inner = [
        Paragraph('<font color="%s"><b>%s</b></font>' % (hexcode, title),
                  S("ct", fontName="Helvetica-Bold", fontSize=9.5, leading=13, spaceAfter=3)),
        Paragraph(text, S("cb", parent=body, fontSize=9.5, leading=14, spaceAfter=0)),
    ]
    t = Table([[inner]], colWidths=[165 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, color),
    ]))
    return t


def rule(space_before=2, space_after=8):
    t = Table([[""]], colWidths=[165 * mm], rowHeights=[0.8])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LINE)]))
    return KeepTogether([Spacer(1, space_before), t, Spacer(1, space_after)])


def section(num, title):
    return KeepTogether([Spacer(1, 6), Paragraph(num, h1n), Paragraph(title, h1), rule(3, 9)])


def cover_page(c, d):
    c.saveState()
    c.setFillColor(INK)
    c.rect(0, A4[1] - 118 * mm, A4[0], 118 * mm, stroke=0, fill=1)
    c.setFillColor(ACC)
    c.rect(0, A4[1] - 121 * mm, A4[0], 3 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(22 * mm, A4[1] - 26 * mm, "MISTRI")
    c.setFillColor(colors.HexColor("#8FA9BC"))
    c.setFont("Helvetica", 9)
    c.drawString(22 * mm, A4[1] - 32 * mm, "Product documentation")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 8)
    c.drawRightString(A4[0] - 22 * mm, 14 * mm, "Internal document \u2014 v1 build, September 2026")
    c.restoreState()


def inner_page(c, d):
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(22 * mm, A4[1] - 17 * mm, A4[0] - 22 * mm, A4[1] - 17 * mm)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 8)
    c.drawString(22 * mm, A4[1] - 14.5 * mm, "Mistri \u2014 product documentation")
    c.drawRightString(A4[0] - 22 * mm, A4[1] - 14.5 * mm, "v1 \u00b7 September 2026")
    c.line(22 * mm, 16 * mm, A4[0] - 22 * mm, 16 * mm)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GREY)
    c.drawRightString(A4[0] - 22 * mm, 11 * mm, str(c.getPageNumber()))
    c.restoreState()


doc = BaseDocTemplate(
    OUT, pagesize=A4,
    leftMargin=22 * mm, rightMargin=22 * mm, topMargin=24 * mm, bottomMargin=22 * mm,
    title="Mistri \u2014 Product Documentation",
    author="Noman", subject="WhatsApp AI assistant for car garages",
)
frame_cover = Frame(22 * mm, 22 * mm, A4[0] - 44 * mm, A4[1] - 44 * mm, id="cover",
                    leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
frame_body = Frame(22 * mm, 20 * mm, A4[0] - 44 * mm, A4[1] - 44 * mm, id="body",
                   leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([
    PageTemplate(id="cover", frames=[frame_cover], onPage=cover_page),
    PageTemplate(id="inner", frames=[frame_body], onPage=inner_page),
])

W = 165 * mm
st = []

# ---------------------------------------------------------------- COVER
st += [
    Spacer(1, 52 * mm),
    Paragraph("Mistri", ttitle),
    Spacer(1, 5),
    Paragraph("A WhatsApp assistant that answers a garage's customers<br/>on the number they already message.", tsub),
    Spacer(1, 34 * mm),
    table([
        ["Product", "Mistri \u2014 WhatsApp assistant for car garages"],
        ["The name", "What half of Dubai already calls the mechanic"],
        ["First customer", "Care Auto Repair Services, Dubai (careautorepair.ae)"],
        ["Version", "v1 \u2014 in build"],
        ["Document date", "1 September 2026"],
        ["Owner", "Noman"],
    ], [38 * mm, W - 38 * mm], header=False),
    Spacer(1, 12 * mm),
    callout(
        "What this document is",
        "A plain description of what the tool does, what it will never do, and how it fits into a "
        "garage's day. Sections 1\u20134 are written so a garage owner can read them. Sections 5\u20139 "
        "are the build detail.",
        BLUE, colors.HexColor("#EEF4F8"),
    ),
    NextPageTemplate("inner"),
    PageBreak(),
]

# ---------------------------------------------------------------- 1
st += [
    section("01", "What this tool is"),
    Paragraph(
        "Mistri answers a garage's WhatsApp messages automatically. It runs on the garage's "
        "<b>existing WhatsApp Business number</b> \u2014 the same number already on the shop sign, the "
        "Google listing and every old customer's phone. Nothing new to print, nothing for customers "
        "to install, nothing for staff to learn.", lead),
    Paragraph(
        "The owner keeps using WhatsApp Business on his phone exactly as before. The bot sits behind "
        "the same number and picks up the messages he has not answered yet. The moment he types a reply "
        "himself, the bot goes quiet in that chat.", body),

    Paragraph("The problem it solves", h2),
    Paragraph(
        "A busy garage loses work in the gaps. A customer asks \u201chow much for brake pads?\u201d at "
        "9 pm, gets no answer until 10 am, and by then has booked somewhere else. The same six questions "
        "arrive twenty times a day and eat the owner's attention while he is under a car.", body),
    bullets([
        "<b>After-hours messages die.</b> Nobody is at the phone from 8 pm to 8 am, and that is when people sit down and think about their car.",
        "<b>The same questions, endlessly.</b> Price, timing, location, do you take card, do you collect the car.",
        "<b>Price questions go cold.</b> A quote that takes two hours to arrive is a quote the customer has stopped waiting for.",
        "<b>Nothing is measured.</b> No garage owner can tell you how many WhatsApp enquiries he got last month, or how many turned into work.",
    ]),

    Paragraph("What it does about it", h2),
    Paragraph(
        "It answers in seconds, in the customer's own language, at 3 am on a Friday, using nothing "
        "but the garage's own price sheet \u2014 and it books the car in.", body),
    Spacer(1, 4),
    callout(
        "The one-line version",
        "Every enquiry gets an answer within seconds, every answer is a real price off the garage's "
        "own sheet, and anything the bot is not certain about goes straight to a human.",
    ),
    PageBreak(),
]

# ---------------------------------------------------------------- 2
st += [
    section("02", "The four rules"),
    Paragraph(
        "Most \u201cAI for business\u201d tools fail on trust: the bot invents a price, or guesses what is "
        "wrong with a car, and the garage spends a week undoing the damage. These four rules are not "
        "settings. They are the product, and they are enforced in code and in tests.", lead),

    Paragraph("Rule 1 \u2014 Never invent a price", h3),
    Paragraph(
        "The bot quotes only what is written on the garage's own price sheet, word for word, fixed "
        "price or range. It never estimates, never interpolates between two rows, never guesses from a "
        "similar car. If the service or the car is not on the sheet, it offers a free inspection and "
        "alerts the owner.", body),

    Paragraph("Rule 2 \u2014 Never diagnose", h3),
    Paragraph(
        "\u201cThere's a noise\u201d, \u201cthe light is on\u201d, \u201cit smells of burning\u201d, "
        "\u201cit won't start\u201d \u2014 the bot does not guess a cause and does not guess a price. "
        "It collects the make, model and year plus the symptom, and books an inspection. A garage that "
        "diagnoses over WhatsApp is a garage with an argument coming.", body),

    Paragraph("Rule 3 \u2014 Hand over when unsure", h3),
    Paragraph(
        "Anything outside the price sheet and the FAQ gets one honest line \u2014 \u201cour service advisor "
        "will call you shortly\u201d \u2014 and the owner receives a WhatsApp alert with a three-line summary "
        "and the customer's number. The bot then stops replying in that conversation until it is "
        "released. No bluffing.", body),

    Paragraph("Rule 4 \u2014 Speak the customer's language", h3),
    Paragraph(
        "English, Arabic, Hindi and Urdu, in whichever script the customer used \u2014 including Roman "
        "Urdu and Roman Hindi, which is how most of Dubai actually types. The reply comes back in the "
        "same language and the same script.", body),
    Spacer(1, 6),
    callout(
        "How this is proved, not promised",
        "A test set of 100 questions ships with the product \u2014 including 20 trick questions asking "
        "for prices that are deliberately not on the sheet, and 20 symptom messages fishing for a "
        "diagnosis. The build is not finished until that set produces <b>zero invented prices and "
        "zero diagnoses</b>.",
        GREEN, colors.HexColor("#EDF6F1"),
    ),
    PageBreak(),
]

# ---------------------------------------------------------------- 3
st += [
    section("03", "Features"),
    Paragraph("Customer-facing", h2),
    table([
        ["Feature", "What happens"],
        ["<b>Price answers</b>",
         "Identifies the service and the car, asks for make / model / year if missing, and quotes the "
         "garage's sheet price for that car category \u2014 sedan, SUV or luxury."],
        ["<b>Booking</b>",
         "Collects name, car, service and preferred day, checks the garage's real opening hours and "
         "how many cars it can take that hour, confirms the slot and sends a maps link."],
        ["<b>Hours, location, payment, warranty, pickup</b>",
         "Answered instantly from the garage's own FAQ. No more typing the address forty times a week."],
        ["<b>Symptom messages</b>",
         "Collects the car and the symptom, offers a free inspection, books it. Never names a cause, "
         "never names a price."],
        ["<b>Reminders</b>",
         "One the day before the appointment, one on the morning of it. Fewer no-shows, which is where "
         "a garage quietly loses a day."],
        ["<b>Four languages</b>",
         "English, Arabic, Hindi, Urdu \u2014 script or Roman, matched to whatever the customer wrote in."],
        ["<b>Short replies</b>",
         "One to four lines. One question at a time. It reads like a person on WhatsApp, not a brochure."],
    ], [42 * mm, W - 42 * mm]),

    Paragraph("Owner-facing", h2),
    table([
        ["Feature", "What happens"],
        ["<b>Booking alert</b>", "A WhatsApp message to the owner's personal number the moment a car is booked in."],
        ["<b>Handoff alert</b>", "A three-line summary plus the customer's number whenever the bot steps back."],
        ["<b>Daily 6 pm summary</b>", "Conversations, bookings, handoffs, and how many messages arrived after closing."],
        ["<b>Takeover</b>", "He replies from his own phone and the bot goes silent in that chat for two hours."],
        ["<b>Release</b>", mono("/bot on 0501234567") + " from his phone hands the chat back."],
        ["<b>Admin page</b>", "A password-protected page listing conversations, full transcripts and bookings. Deliberately plain."],
    ], [42 * mm, W - 42 * mm]),

    Paragraph("The pilot report", h2),
    Paragraph(
        "One command prints the numbers for any date range: conversations and how many started outside "
        "opening hours, price questions answered, bookings, handoffs, median reply time, language split.", body),
    Paragraph(
        "This is not a vanity dashboard. It is the evidence that sells garage number two: not "
        "\u201cAI will transform your business\u201d, but \u201chere is what happened at Care over thirty days.\u201d", quote),
    PageBreak(),
]

# ---------------------------------------------------------------- 4
st += [
    section("04", "How it works on the owner's phone"),
    Paragraph(
        "This is the part that makes the product sellable. Understand it before promising anything "
        "to a garage.", lead),

    Paragraph("Coexistence \u2014 same number, two places", h2),
    Paragraph(
        "One number can now run on the WhatsApp Business app <b>and</b> the official API at the same "
        "time \u2014 Meta calls it coexistence. The owner keeps his app, his chats and his history.", body),
    bullets([
        "Nothing installs on anyone's phone \u2014 not the owner's, not the customer's.",
        "The garage keeps its number, its chat history and every existing contact.",
        "Setup is one QR scan by the owner, roughly twenty minutes, done once.",
        "It can be disconnected again at any time. The number simply goes back to being app-only.",
    ]),

    Paragraph("The handover, in practice", h2),
    table([
        ["Situation", "What the bot does"],
        ["Customer asks a price that is on the sheet", "Answers it, then offers the next free slots"],
        ["Customer asks something off the sheet", "Offers a free inspection, alerts the owner, stops replying"],
        ["Owner types a reply himself", "Goes silent in that chat for 2 hours"],
        ["Owner sends " + mono("/bot on &lt;number&gt;"), "Starts replying in that chat again"],
        ["Handed-over chat goes quiet for 24 hours", "Releases itself automatically"],
    ], [58 * mm, W - 58 * mm]),
    Spacer(1, 4),
    Paragraph("The bot never talks over the owner. That is the whole design of this section.", quote),

    Paragraph("What the owner must be told before he agrees", h2),
    Paragraph(
        "He should hear this before the QR scan, not after. Full list in "
        + mono("ONBOARDING.md") + ".", body),
    table([
        ["Stops working on that number", "Keeps working normally"],
        ["Broadcast lists \u2014 no new ones, existing ones become read-only", "Voice and video calls in WhatsApp"],
        ["Disappearing messages and view-once", "Normal phone calls \u2014 same SIM, unaffected"],
        ["Live location in one-to-one chats", "Group chats (the bot never sees or replies in them)"],
        ["WhatsApp Web is unlinked once at setup; re-link after", "Status, catalog and orders"],
    ], [W / 2, W / 2]),
    Spacer(1, 4),
    Paragraph(
        "Say the broadcast-list one out loud. It is the only change a garage might genuinely feel, and "
        "some owners send promos that way.", quote),
    PageBreak(),
]

# ---------------------------------------------------------------- 5
st += [
    section("05", "How it is built"),
    Paragraph(
        "A single Python service on a VPS. No queue, no cluster, no Kubernetes \u2014 one garage's "
        "WhatsApp traffic is a few hundred messages a day.", lead),

    table([
        ["Layer", "Choice", "Why"],
        ["Service", "Python 3.11, FastAPI, uvicorn", "WhatsApp pushes webhooks; this handles them and acks fast"],
        ["Hosting", "AlmaLinux VPS, systemd, nginx, Let's Encrypt", "Already owned. Meta requires a public HTTPS endpoint"],
        ["WhatsApp", "Meta Cloud API, via 360dialog for the pilot", "Coexistence needs an approved provider \u2014 see section 7"],
        ["Language model", "Anthropic API \u2014 Sonnet first, Haiku once stable", "Reply quality first, then benchmark for cost"],
        ["Database", "SQLite via SQLAlchemy", "One file, no server. Moving to Postgres is a connection string"],
        ["Knowledge", "YAML files per garage", "The owner's price sheet is small. No vector database, no RAG"],
        ["Scheduling", "APScheduler", "Reminders and the 6 pm summary"],
    ], [26 * mm, 46 * mm, W - 72 * mm]),

    Paragraph("Two decisions worth knowing", h2),
    Paragraph("Multi-garage from day one", h3),
    Paragraph(
        "Every table and every config carries a " + mono("garage_id") + ". Garage number "
        "two is a new folder of YAML files and a number connected \u2014 not a fork of the codebase. "
        "This costs almost nothing now and would cost weeks later.", body),
    Paragraph("One WhatsApp module, nothing else", h3),
    Paragraph(
        "All WhatsApp traffic goes through a single file. Switching from the pilot provider to Meta "
        "direct is two environment variables. No other part of the code knows or cares which one is "
        "in use.", body),

    Paragraph("Knowledge files, per garage", h2),
    table([
        ["File", "Holds"],
        [mono("prices.yaml"), "The price sheet \u2014 every service by car category, or per model where the garage prices that way. <b>The bot may quote nothing that is not in this file.</b>"],
        [mono("faq.yaml"), "The answers that are not prices, built from the garage's own chat history"],
        [mono("info.yaml"), "Hours, address, maps link, payment methods, warranty, pickup, capacity per hour, owner's alert number"],
    ], [34 * mm, W - 34 * mm]),
    Paragraph(
        "The owner's prices live in a plain text file he could read himself. That is deliberate \u2014 "
        "when a garage asks \u201cwhere does it get the price from?\u201d, the honest answer is a file you "
        "can open in front of him.", quote),
    PageBreak(),
]

# ---------------------------------------------------------------- 6
st += [
    section("06", "What it will not do"),
    Paragraph(
        "Written down so it stops being discussed. These are out of scope for v1 by decision, not by "
        "oversight.", lead),
    table([
        ["Not in v1", "Reason"],
        ["Full web dashboard", "v1 reporting is WhatsApp alerts plus a bare admin page. A dashboard is a product of its own"],
        ["Payments and deposits", "Adds a payment provider, refunds and disputes to a two-week build"],
        ["CRM and dealer-software integration", "Every garage uses something different. Wait for a customer who will pay for it"],
        ["Mobile app", "The whole point is that nothing installs"],
        ["Voice or AI phone calls", "Different product, different failure modes"],
        ["Marketing broadcasts", "Coexistence removes broadcast lists anyway. A real v2 feature, not a v1 bolt-on"],
        ["Multi-branch", "One garage, one location, until a customer has two"],
        ["Vector search over the price sheet", "The sheet fits in the prompt. Adding retrieval would add a way to get prices wrong"],
    ], [50 * mm, W - 50 * mm]),
    Spacer(1, 4),
    Paragraph(
        "Ideas that come up mid-build are written to " + mono("LATER.md") + " and dropped. "
        "The v1 that ships beats the v2 that is still being designed.", quote),

    Paragraph("Definition of done", h2),
    Paragraph("v1 is finished when all three of these are true \u2014 not before, and not on any other basis.", body),
    table([
        ["1", "Care's real number answers \u201cbrake pads Camry 2019?\u201d with the sheet price in under five seconds, offers slots, books one, and the owner gets the alert."],
        ["2", "The 100-question test set \u2014 20 of them fishing for off-sheet prices, 20 fishing for a diagnosis \u2014 produces zero invented prices and zero diagnoses."],
        ["3", "The report command prints correct numbers for the pilot period."],
    ], [10 * mm, W - 10 * mm], header=False),
    PageBreak(),
]

# ---------------------------------------------------------------- 7
st += [
    section("07", "Getting a garage connected"),
    Paragraph(
        "Coexistence cannot be switched on by the garage alone. Meta only allows it through an approved "
        "provider's onboarding flow, and the owner must click through it himself \u2014 nobody may do "
        "it on his behalf.", lead),

    Paragraph("The route chosen for the pilot", h2),
    table([
        ["", "Via a provider (360dialog)", "Direct with Meta"],
        ["Meta app review needed", "No", "Yes \u2014 advanced access on two permissions"],
        ["Business verification needed", "No", "Yes"],
        ["Time before the pilot can go live", "Days", "Weeks, in a queue you do not control"],
        ["Monthly cost", "~\u20ac49 plus Meta's per-conversation fees", "Meta's fees only"],
    ], [40 * mm, 52 * mm, W - 92 * mm]),
    Spacer(1, 4),
    callout(
        "Decision",
        "Pilot number one goes through 360dialog. Meta's own approval queue would consume the entire "
        "build window, and switching to direct later is a two-line configuration change \u2014 not a rewrite.",
        BLUE, colors.HexColor("#EEF4F8"),
    ),

    Paragraph("What the owner does, once", h2),
    table([
        ["1", "Updates WhatsApp Business to 2.24.17 or newer (the day before \u2014 an old app is the usual reason this fails)"],
        ["2", "Signs in with his own Meta business account and picks \u201cconnect your existing WhatsApp Business app\u201d"],
        ["3", "Re-enters and verifies his number"],
        ["4", "Opens the message that arrives in his WhatsApp Business app and scans the QR code"],
        ["5", "Chooses to sync chat history \u2014 say yes; it is where the FAQ comes from"],
        ["6", "Re-links WhatsApp Web afterwards if he uses it"],
    ], [10 * mm, W - 10 * mm], header=False),
    Paragraph(
        "About twenty minutes, done once, with someone sitting next to him. The full script, including "
        "what to do when a step fails, is in " + mono("ONBOARDING.md") + ".", body),
    PageBreak(),
]

# ---------------------------------------------------------------- 8
st += [
    section("08", "Build status"),
    Paragraph("Everything that does not need the garage's own data is finished, "
              "with 296 tests behind it.", lead),
    table([
        ["Stage", "Scope", "Status"],
        ["Step 0", "Onboarding route decided; owner checklist written; message templates drafted", '<font color="#2E7D5B"><b>Done</b></font>'],
        ["Days 1\u20132", "Webhook, database, message logging, owner-takeover pause", '<font color="#2E7D5B"><b>Done</b></font>'],
        ["Days 3\u20135", "Reply engine with the four rules, the price guard, language handling", '<font color="#2E7D5B"><b>Done</b></font>'],
        ["Days 6\u20138", "Booking flow, slot capacity, confirmation, owner alerts", '<font color="#2E7D5B"><b>Done</b></font>'],
        ["Days 9\u201310", "Handoff, owner commands, reminders, the 6 pm summary", '<font color="#2E7D5B"><b>Done</b></font>'],
        ["Days 11\u201312", "Admin page, pilot report, systemd and nginx deployment", '<font color="#2E7D5B"><b>Done</b></font>'],
        ["v1.1", "Post-service follow-up and the service-due nudge", '<font color="#2E7D5B"><b>Done</b></font>'],
        ["Review", "Two adversarial passes over the code; nine real defects fixed", '<font color="#2E7D5B"><b>Done</b></font>'],
        ["Days 13\u201314", "The price sheet, their real questions, the number connected",
         '<font color="#C8552B"><b>Needs the garage</b></font>'],
    ], [24 * mm, W - 60 * mm, 36 * mm]),

    Paragraph("What is still needed from the garage", h2),
    bullets([
        "<b>The price sheet.</b> Their own service list is already loaded from their website; every price is deliberately blank. Nothing published, nothing guessed.",
        "<b>The top thirty questions</b> from their real WhatsApp history. These become the FAQ and the test set. Invented questions produce a bot that passes its own exam and fails on day one.",
        "<b>Four message templates approved by Meta.</b> Reminders cannot send until they are, and it is the only step whose speed nobody here controls.",
    ]),

    Paragraph("What the review found", h2),
    Paragraph(
        "Two passes were made over the finished code, reading it rather than running it. Nine real "
        "defects turned up while every test was passing, all of them in the plumbing around the "
        "rules rather than in the rules themselves.", body),
    bullets([
        "The bot would have <b>talked over the owner</b> \u2014 his replies were matched against a phone number formatted for humans, so each was filed as a customer message.",
        "The webhook was <b>open to anyone who found the URL</b> on the pilot's provider, which does not sign requests. A stranger could have sent messages from the garage's number.",
        "Several failures reached the customer as <b>silence</b> rather than as a person.",
    ]),
    Paragraph("The risk that is still open", h3),
    Paragraph(
        "The takeover behaviour can only be fully confirmed on a live number. It is the first thing "
        "checked on connection day, and it is checked first because it was already found broken "
        "once. A bot that talks over the owner is worse than no bot.", body),
    PageBreak(),
]

# ---------------------------------------------------------------- 9
st += [
    section("09", "Beyond the first garage"),
    Paragraph(
        "The pilot exists to produce a number, not a testimonial. Thirty days at Care should yield a "
        "line like: <i>\u201c214 enquiries, 61 of them after closing time, 38 cars booked, average reply "
        "eight seconds.\u201d</i> That sentence is what sells garage number two.", lead),

    Paragraph("What garage two actually costs", h2),
    table([
        ["Step", "Effort"],
        ["New folder with that garage's prices, FAQ and details", "An afternoon, mostly transcription"],
        ["Owner connects his number", "20 minutes, once"],
        ["Code changes", "None \u2014 " + mono("garage_id") + " is already everywhere"],
    ], [72 * mm, W - 72 * mm]),

    Paragraph("Sensible next steps, in order", h2),
    bullets([
        "<b>The service-due nudge is already built.</b> Months after a car's last visit it asks whether they want to come in. This is what a garage renews for: cancelling stops the thing that refills the bay.",
        "Owner-side reporting he can read himself, once there is enough data to be worth reading.",
        "Template-based promotions, which become the honest replacement for the broadcast lists coexistence removes.",
        "Other trades with the same shape \u2014 fixed price list, appointment, one busy owner on WhatsApp.",
    ]),

    Spacer(1, 8),
    rule(0, 8),
    Paragraph(
        "The tool is not interesting because it uses AI. It is interesting because a garage owner "
        "under a car at 8 pm stops losing the customer who messaged at 7:40 \u2014 and because the "
        "bot would rather say \u201csomeone will call you\u201d than make a price up.", quote),
]

doc.build(st)
print("built:", OUT)
