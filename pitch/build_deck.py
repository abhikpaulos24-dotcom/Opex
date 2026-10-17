"""Builds pitch/OpEx_AI_Builder_Cup_2026.pptx from the official AI Builder Cup template.

The template's header banner, footer strip and section titles are kept exactly; our content
is added underneath. Numbers come from pitch/numbers.json (a default 5-year simulation run)
and the model score files in models/, so the deck can never disagree with the product.

    python pitch/build_deck.py      (needs python-pptx)
"""
import copy
import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
PITCH = ROOT / "pitch"
ICONS = PITCH / "assets" / "icons"
SHOTS = PITCH / "screenshots"
N = json.loads((PITCH / "numbers.json").read_text())
FM = json.loads((ROOT / "models" / "failure_mode_metrics.json").read_text())
RUL = json.loads((ROOT / "models" / "rul_metrics.json").read_text())
PRE = json.loads((ROOT / "models" / "precursor_metrics.json").read_text())

INK, MUTED, BORDER, CARD = "1E2433", "5B6475", "DDE1EA", "F4F5FA"
INDIGO, TEAL, PEACH, RED, WHITE = "4F5BD5", "217A5F", "C2410C", "B3261E", "FFFFFF"
BODY_FONT = "Arial"
D, K = N["delta"], N["kpis"]


def rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


def lakh(v: float) -> str:
    return f"₹{v / 1e5:,.1f} L" if abs(v) < 1e7 else f"₹{v / 1e7:,.2f} Cr"


# ------------------------------------------------------------------ drawing helpers
def text(slide, x, y, w, h, paragraphs, size=11, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, font=BODY_FONT, spacing=2, name=None):
    """paragraphs: str, or list of str / list of (text, {bold,color,size}) runs."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        box.name = name
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(spacing)
        runs = para if isinstance(para, list) else [(para, {})]
        for content, style in runs:
            r = p.add_run()
            r.text = content
            r.font.name = style.get("font", font)
            r.font.size = Pt(style.get("size", size))
            r.font.bold = style.get("bold", bold)
            r.font.color.rgb = rgb(style.get("color", color))
    return box


def bullets(slide, x, y, w, h, items, size=10.5, color=INK, gap=3):
    box = text(slide, x, y, w, h, [""], size=size, color=color)
    tf = box.text_frame
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        runs = item if isinstance(item, list) else [(item, {})]
        r0 = p.add_run()
        r0.text = "•  "
        r0.font.size, r0.font.color.rgb, r0.font.name = Pt(size), rgb(INDIGO), BODY_FONT
        for content, style in runs:
            r = p.add_run()
            r.text = content
            r.font.name = BODY_FONT
            r.font.size = Pt(style.get("size", size))
            r.font.bold = style.get("bold", False)
            r.font.color.rgb = rgb(style.get("color", color))
    return box


def card(slide, x, y, w, h, fill=CARD, line=BORDER, radius=0.08, name=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.adjustments[0] = radius
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    if line:
        shape.line.color.rgb = rgb(line)
        shape.line.width = Pt(0.75)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    if name:
        shape.name = name
    return shape


def icon(slide, name, color, x, y, size=0.42):
    return slide.shapes.add_picture(str(ICONS / f"{name}_{color}.png"), Inches(x), Inches(y), Inches(size), Inches(size))


def headline(slide, message, y=1.08):
    text(slide, 0.38, y, 9.25, 0.42, message, size=17, bold=True, color=INK, name="Headline")


def stat(slide, x, y, w, value, label, color=INDIGO, size=24):
    text(slide, x, y, w, 0.42, value, size=size, bold=True, color=color)
    text(slide, x, y + 0.44, w, 0.42, label, size=9, color=MUTED)


def arrow(slide, x1, y1, x2, y2, color=MUTED, width=1.5):
    line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    line.line.color.rgb = rgb(color)
    line.line.width = Pt(width)
    tail = line.line._get_or_add_ln()
    end = tail.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd", {"type": "triangle"})
    tail.append(end)
    return line


def box_label(slide, x, y, w, h, title, sub=None, fill=WHITE, line=BORDER, title_color=INK, size=10):
    card(slide, x, y, w, h, fill=fill, line=line, radius=0.12)
    paras = [[(title, {"bold": True, "color": title_color, "size": size})]]
    if sub:
        paras.append([(sub, {"color": MUTED, "size": size - 2})])
    text(slide, x + 0.08, y + 0.04, w - 0.16, h - 0.08, paras, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def picture_fit(slide, path, x, y, w, h, border=True):
    from PIL import Image
    with Image.open(path) as im:
        ratio = im.width / im.height
    if w / h > ratio:
        pw, ph = h * ratio, h
    else:
        pw, ph = w, w / ratio
    px, py = x + (w - pw) / 2, y + (h - ph) / 2
    pic = slide.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(pw), Inches(ph))
    if border:
        pic.line.color.rgb = rgb(BORDER)
        pic.line.width = Pt(0.75)
    return pic


def table(slide, x, y, w, h, rows, col_widths, size=9, header_fill=INK, zebra=True, bold_first_col=False):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(h))
    tbl = shape.table
    for i, cw in enumerate(col_widths):
        tbl.columns[i].width = Inches(cw)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.025)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(header_fill if r == 0 else (CARD if zebra and r % 2 == 0 else WHITE))
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = str(value)
            run.font.name = BODY_FONT
            run.font.size = Pt(size)
            run.font.bold = r == 0 or (bold_first_col and c == 0)
            run.font.color.rgb = rgb(WHITE if r == 0 else INK)
    return shape


def set_title(shape, title):
    """Keep the template's title box and font, replace its paragraphs with one title."""
    tf = shape.text_frame
    first = tf.paragraphs[0]
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    runs = first.runs
    runs[0].text = title
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def notes(slide, words):
    slide.notes_slide.notes_text_frame.text = words


def title_box(slide):
    return next(s for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip() and s.top < Inches(1))


# ------------------------------------------------------------------ slides
def slide_team(s):
    box = next(sh for sh in s.shapes if sh.has_text_frame and "Team Details" in sh.text_frame.text)
    box.width = Inches(6.1)
    values = {"Team name: ": "OpEx", "Team leader name: ": "Srihitha Pulapa",
              "Problem Statement: ": "Manufacturing · Intelligent Operations & Industrial Efficiency"}
    for p in box.text_frame.paragraphs:
        label = "".join(r.text for r in p.runs)
        if label in values:
            r = copy.deepcopy(p.runs[0]._r)
            p._p.append(r)
            p.runs[-1].text = values[label]
            p.runs[-1].font.bold = True
    logo = s.shapes.add_picture(str(PITCH / "assets" / "opex-logo.png"), Inches(6.7), Inches(3.2), Inches(2.85))
    logo.name = "OpEx logo"
    text(s, 6.7, 4.35, 2.85, 0.4, "From machine signals to money-backed decisions", size=10, color=MUTED,
         align=PP_ALIGN.CENTER)
    notes(s, "Team OpEx. OpEx is an AI operations copilot for CNC and automotive-component plants in India.")


def slide_brief(s):
    headline(s, "Spot trouble early, price every fix in rupees, let a person decide")
    text(s, 0.38, 1.55, 9.2, 0.55, [[
        ("India's ₹7.6 lakh-crore auto-component industry (ACMA FY26) still runs most CNC shops reactively: ", {}),
        ("plants sit at 60–75% OEE against a world-class 85%", {"bold": True}),
        (", alarms flood screens, and a surprise spindle failure can cost a 24-machine plant ₹3–4 lakh in one go.", {})]],
        size=10.5, color=INK)
    steps = [("activity", "Detect", "Anomalies in plain words: how far off, for how long"),
             ("search", "Diagnose", "One root cause from many signals + 'have we seen this before?'"),
             ("rupee", "Decide", "7 options priced in ₹; Gemini agents review; a human approves"),
             ("refresh", "Learn", "Every outcome is checked; what works rises to the top"),
             ("chart", "Prove", "5-year with-vs-without simulation of the whole plant")]
    x = 0.38
    for i, (ic, title, sub) in enumerate(steps):
        card(s, x, 2.25, 1.72, 1.5, fill=CARD)
        icon(s, ic, "indigo" if i < 4 else "teal", x + 0.65, 2.36, 0.42)
        text(s, x + 0.1, 2.85, 1.52, 0.25, title, size=11.5, bold=True, align=PP_ALIGN.CENTER)
        text(s, x + 0.1, 3.12, 1.52, 0.6, sub, size=8.5, color=MUTED, align=PP_ALIGN.CENTER)
        if i < 4:
            arrow(s, x + 1.74, 3.0, x + 1.86, 3.0, color=INDIGO)
        x += 1.86
    stat(s, 0.45, 3.98, 2.2, f"−{D['breakdowns_reduction'] * 100:.1f}%", "breakdowns over 5 simulated years", RED)
    stat(s, 2.75, 3.98, 2.2, lakh(D["net_benefit_inr"]), "net benefit after paying for OpEx", TEAL)
    stat(s, 5.05, 3.98, 2.2, f"{D['roi_multiple']:.1f}×", f"return · pays back in month {D['payback_months']}", INDIGO)
    stat(s, 7.35, 3.98, 2.3, f"{D['downtime_avoided_h']:,.0f} h", "machine-hours of breakdown avoided", INK)
    text(s, 0.38, 4.88, 9.2, 0.3, "Simulated results for a 24-machine plant, calibrated on 4 real industrial datasets "
         "(AI4I 2020, NASA C-MAPSS, Azure PdM, Zenodo line OEE). Calculation on slide 'How we calculated the 5-year numbers'.",
         size=7.5, color=MUTED)
    notes(s, "The problem, the five-step loop, and the headline result. Stress that the AI never acts on its own.")


def slide_opportunities(s):
    set_title(title_box(s), "Opportunities")
    headline(s, "Not another dashboard: a decision engine with proof of value")
    cols = [
        ("How is it different?", "network", [
            "Combines signals into ONE cause instead of 50 separate alarms",
            "Prices every option in ₹ (repair, downtime, lost output, scrap, energy, risk), not just 'risk: high'",
            "Admits doubt: bad sensor data visibly lowers confidence; a faulty sensor is called a sensor fault",
            "Learns from each decision's real outcome in this plant"]),
        ("How does it solve the problem?", "wrench", [
            "Warns hours to weeks ahead, so parts are ready and swaps happen in the Sunday window",
            "Engineers see the trade-off and approve in one screen",
            "Operators ask in their own language, by voice, with gloves on",
            "Managers see ₹ impact, investigations and the 5-year business case"]),
        ("USP", "sparkles", [
            "Gemini incident room: Diagnostician, Planner and Safety-officer agents, grounded on computed facts and SOPs",
            "'Rewind the factory': replays a real breakdown with OpEx watching",
            "Honest numbers: misses, false alarms and people ignoring advice are all in the simulation",
            "Accessible by design: 6 Indian languages, read-aloud, high contrast, dyslexia-friendly font"]),
    ]
    for i, (title, ic, items) in enumerate(cols):
        x = 0.38 + i * 3.1
        card(s, x, 1.6, 2.95, 2.55, fill=CARD)
        icon(s, ic, ["indigo", "teal", "peach"][i], x + 0.15, 1.72, 0.38)
        text(s, x + 0.62, 1.78, 2.25, 0.3, title, size=11, bold=True)
        bullets(s, x + 0.15, 2.22, 2.68, 1.9, items, size=9.2, gap=3)
    rows = [["Capability", "Typical CMMS / PdM dashboard", "OpEx"],
            ["Root cause across machine, quality and energy", "Single-signal thresholds", "Signature matching + past incidents + chain of impact"],
            ["What to do and what it costs", "Work order only", "7 priced options, multi-objective ranking, safety rule"],
            ["Proof of value before buying", "Vendor case studies", "5-year calibrated with-vs-without simulation of your plant"]]
    table(s, 0.38, 4.25, 9.25, 0.95, rows, [2.75, 2.75, 3.75], size=8)
    notes(s, "Three columns answer the template's three questions; the table shows the gap versus typical tools.")


def slide_features(s):
    headline(s, "Eight capabilities, one flow: detect, diagnose, decide, learn, prove")
    features = [
        ("factory", "Live factory health", "OEE (A×P×Q), 5 health scores, ranked 'worry about first' list, floor map"),
        ("activity", "Anomaly → root cause", "'Vibration 148% above normal for 52 min', chain of impact, sensor-fault detection"),
        ("clock", "Failure & quality prediction", "8-h failure probability, 10–90% window, remaining life per component, defect forecast"),
        ("rupee", "Priced options", "Stop, slow 10%, continue, shift load, partial fix, replace, monitor: each in ₹"),
        ("bot", "AI incident room + approval", "3 Gemini agents review; approve / reject / modify by role; full audit log"),
        ("mic", "Ask OpEx copilot", "Function-calling Gemini, voice in/out, 6 Indian languages, part-photo check"),
        ("refresh", "Closed-loop learning", "Outcome checked after 2 plant hours; '9 of 11 times' feeds ranking; AI investigations"),
        ("rewind", "5-year simulation + rewind", "Choose replay length; live with/without counters; ROI; CSV downloads"),
    ]
    for i, (ic, title, sub) in enumerate(features):
        col, row = i % 4, i // 4
        x, y = 0.38 + col * 2.33, 1.62 + row * 1.62
        card(s, x, y, 2.2, 1.5, fill=CARD)
        icon(s, ic, ["indigo", "teal", "peach", "ink"][col], x + 0.14, y + 0.14, 0.4)
        text(s, x + 0.14, y + 0.62, 1.95, 0.28, title, size=10.5, bold=True)
        text(s, x + 0.14, y + 0.9, 1.95, 0.58, sub, size=8, color=MUTED)
    text(s, 0.38, 4.92, 9.25, 0.3, [[("Also: ", {"bold": True}), (
        "data-health checks (missing, drift, calibration), maintenance plan + spare parts, Pub/Sub alerts, energy standby advice, "
        "CO₂ tracking, sensor CSV upload checker, factory-memory search, 4 roles with server-side permissions.", {})]],
        size=8.5, color=INK)
    notes(s, "Walk through the eight cards left to right; all are working in the prototype.")


def slide_flow(s):
    headline(s, "Every recommendation passes a person and is checked afterwards")
    y = 1.75
    steps = [("Sensors / MES", "vibration, temp, rpm,\ntorque, current, coolant"),
             ("Data health", "missing, drift,\nconsistency → confidence"),
             ("Detect", "anomalies with\nsize + duration"),
             ("Diagnose", "root cause, chain,\npast incidents"),
             ("Predict", "failure window,\nquality, energy")]
    x = 0.38
    for i, (t, sub) in enumerate(steps):
        box_label(s, x, y, 1.65, 0.78, t, sub, fill=WHITE)
        if i < 4:
            arrow(s, x + 1.67, y + 0.39, x + 1.86, y + 0.39, INDIGO)
        x += 1.89
    arrow(s, 8.68, y + 0.8, 8.68, 2.95, INDIGO)
    lower = [("Act & check", "machine changed; outcome\nchecked after 2 plant h"),
             ("Human decides", "approve / reject / modify\n(role-based)"),
             ("AI incident room", "Diagnostician · Planner ·\nSafety officer (Gemini)"),
             ("Price options", "7 options in ₹ +\nmulti-objective ranking")]
    positions = [0.38 + 1.89 * k for k in (1, 2, 3, 4)]
    fills = [WHITE, "EEF0FD", "EEF0FD", WHITE]
    for (t, sub), px, f in zip(lower, positions, fills):
        box_label(s, px, 2.97, 1.65, 0.78, t, sub, fill=f)
    for k in range(3, 0, -1):
        arrow(s, positions[k] - 0.02, 3.36, positions[k - 1] + 1.67, 3.36, INDIGO)
    box_label(s, 0.38, 2.97, 1.65, 0.78, "Learn", "success counts per\nproblem × action", fill="E5F4EC", title_color=TEAL)
    arrow(s, positions[0] - 0.02, 3.36, 0.38 + 1.67, 3.36, TEAL)
    text(s, 0.38, 3.8, 6.0, 0.25, "↺  Learn feeds real success rates back into 'Price options' for the next decision",
         size=8, color=TEAL, bold=True)
    # Actors
    actors = [("user", "indigo", "Operator", "asks by voice, acknowledges alerts, approves small fixes"),
              ("wrench", "teal", "Maintenance engineer", "approves stops and part swaps, writes investigations"),
              ("users", "peach", "Plant manager", "sets priorities and ₹ assumptions, runs the 5-year case")]
    for i, (ic, color, who, what) in enumerate(actors):
        x = 0.38 + i * 3.1
        icon(s, ic, color, x, 4.32, 0.36)
        text(s, x + 0.45, 4.3, 2.55, 0.6, [[(who, {"bold": True, "size": 9.5})], [(what, {"size": 8, "color": MUTED})]])
    notes(s, "Top row is automatic; bottom row always includes a human decision; the learn step closes the loop.")


def slide_wireframes(s):
    headline(s, "Designed for the shop floor: phone at the machine, desktop in the office")
    picture_fit(s, SHOTS / "16_mobile.png", 0.38, 1.6, 1.75, 3.55)
    picture_fit(s, SHOTS / "17_mobile_machine.png", 2.25, 1.6, 1.75, 3.55)
    picture_fit(s, SHOTS / "04_machine_top.png", 4.2, 1.6, 5.4, 3.0)
    bullets(s, 4.2, 4.7, 5.4, 0.55, [
        "Numbered steps on every machine: 1 What we detected · 2 Why · 3 What next · 4 What should we do",
        "Status = icon + word + colour (ISA-101 style: grey when normal, colour only for trouble)"], size=8.5, gap=1)
    notes(s, "Real screenshots of the working prototype, not mock-ups.")


def slide_architecture(s):
    headline(s, "One Cloud Run service + Gemini on Vertex AI + Supabase Postgres")
    # shop floor
    box_label(s, 0.38, 1.75, 1.55, 0.9, "Shop floor", "CNC controllers, sensors\n(OPC UA / MTConnect gateway)", fill=CARD)
    box_label(s, 0.38, 3.0, 1.55, 0.75, "Pub/Sub", "sensor push +\ncritical alerts out", fill="FFF4EC", line="F2A57A")
    arrow(s, 1.15, 2.67, 1.15, 2.98, PEACH)
    # cloud run frame
    card(s, 2.25, 1.6, 4.5, 3.1, fill="F7F8FD", line=INDIGO, radius=0.04)
    text(s, 2.4, 1.66, 4.2, 0.25, "Cloud Run · ONE container (asia-south1)", size=10, bold=True, color=INDIGO)
    inner = [("React web app", "accessible UI, voice,\n6 languages"), ("FastAPI", "auth, roles, API,\ningest"),
             ("Live plant twin", "1-min data, analytics,\ncached per minute"), ("Decision engine", "₹ options, ranking,\nlearning loop"),
             ("5-year simulator", "2.1 M machine-hours\nin 4.5 s"), ("AI agents + copilot", "function calling,\nRAG over SOPs")]
    for i, (t, sub) in enumerate(inner):
        col, row = i % 3, i // 3
        box_label(s, 2.4 + col * 1.43, 2.0 + row * 1.3, 1.33, 1.12, t, sub, fill=WHITE, size=9)
    arrow(s, 1.95, 3.37, 2.23, 3.37, PEACH)
    # right side services
    services = [("Gemini on Vertex AI", "gemini-3.8-flash · 3.5-flash-lite\n· gemini-embedding-001", "EEF0FD", INDIGO),
                ("Supabase Postgres", "users, decisions, incidents,\nsimulation runs (RLS on)", "E5F4EC", TEAL),
                ("BigQuery", "daily simulation results\nfor Looker Studio", CARD, BORDER),
                ("Cloud Storage", "uploaded files", CARD, BORDER)]
    for i, (t, sub, fill, line) in enumerate(services):
        y = 1.6 + i * 0.8
        box_label(s, 7.1, y, 2.5, 0.68, t, sub, fill=fill, line=line, size=9.5)
        arrow(s, 6.77, y + 0.34, 7.08, y + 0.34, MUTED)
    # offline pipeline
    card(s, 0.38, 4.85, 9.22, 0.42, fill=CARD)
    text(s, 0.5, 4.89, 9.0, 0.35, [[("Offline pipeline: ", {"bold": True}),
        ("AI4I 2020 · NASA C-MAPSS · Azure PdM · Zenodo line OEE · NIST Nestor  →  clean  →  train 3 models  →  calibrate simulator  "
         "→  build factory memory (793 jobs, 194 incidents)", {})]], size=8.5, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.38, 3.95, 1.6, 0.7, "Browser on phone / tablet / desktop talks only to the one Cloud Run URL",
         size=7.5, color=MUTED)
    notes(s, "Single deployable unit. Gemini only explains and reasons over computed facts; numbers are deterministic.")


def slide_tech(s):
    headline(s, "Google Cloud where it adds value, and nothing used just for show")
    rows = [["Technology", "What OpEx uses it for"],
            ["Gemini on Vertex AI (gemini-3.8-flash, 3.5-flash-lite)", "3-agent incident room, function-calling copilot (6 tools), investigations, part-photo check, 6 Indian languages"],
            ["gemini-embedding-001 (768-d)", "Semantic search in factory memory (SOPs, manuals, 194 past incidents) + keyword hybrid"],
            ["Cloud Run", "Single service: web app + API + live twin + simulator + agents"],
            ["BigQuery", "Daily with/without simulation results for long-term analysis and Looker Studio"],
            ["Pub/Sub", "Critical alerts out to SMS / WhatsApp / CMMS; sensor readings in (push to /api/ingest)"],
            ["Cloud Storage", "Uploaded sensor files and documents"],
            ["Supabase Postgres", "Users, roles, decisions, outcomes, incidents, runs; Row Level Security on"],
            ["Python · FastAPI · scikit-learn", "Analytics, 3 ML models, 5-year simulator (numpy, shared random draws)"],
            ["React · TypeScript · Recharts", "Accessible web app: WCAG 2.2 AA, Atkinson Hyperlegible, voice, read-aloud"]]
    table(s, 0.38, 1.6, 9.25, 3.05, rows, [3.0, 6.25], size=8.5, bold_first_col=True)
    card(s, 0.38, 4.78, 9.25, 0.45, fill="FFF4EC", line="F2A57A")
    text(s, 0.5, 4.83, 9.0, 0.38, [[("Deliberately not used: ", {"bold": True, "color": PEACH}),
        ("Dataflow and Vertex AI Training. At 24 machines and 1-minute data, training takes 30 s in the container. "
         "Dataflow (Pub/Sub → BigQuery) is the path past ~10k readings/second.", {})]], size=8.5, anchor=MSO_ANCHOR.MIDDLE)
    notes(s, "Every Google service has a concrete job; the two we skipped are explained.")


def slide_cost(s):
    headline(s, f"₹{N['costs']['one_time_inr'] / 1e5:.1f} L to start, ₹{N['costs']['yearly_inr'] / 1e5:.1f} L a year, "
                f"for a 24-machine plant")
    c = N["costs"]
    rows = [["Item", "How it is calculated", "Amount"],
            ["Sensor retrofit", "₹45,000 vibration + current + temperature kit × 24 machines", lakh(c["sensor_kits_inr"])],
            ["Setup and training", "Integration, commissioning, operator training (one time)", lakh(c["implementation_inr"])],
            ["Cloud (per year)", "Cloud Run + Gemini + Supabase Pro + BigQuery/GCS (below)", lakh(c["cloud_per_year_inr"])],
            ["Support (per year)", "Model upkeep, help desk, updates", lakh(c["support_per_year_inr"])],
            ["5-year total", "₹16.8 L once + ₹8.4 L × 5 years", lakh(D["opex_cost_inr"])]]
    table(s, 0.38, 1.6, 5.6, 2.2, rows, [1.35, 3.25, 1.0], size=8.5, bold_first_col=True)
    card(s, 6.2, 1.6, 3.4, 2.2, fill=CARD)
    text(s, 6.35, 1.7, 3.1, 0.25, "Cloud cost per month (estimate)", size=10, bold=True)
    bullets(s, 6.35, 2.02, 3.15, 1.75, [
        "Gemini: ~300 agent/copilot calls a day × 6k tokens = 54 M tokens/month → 40 M in × $0.75 + 14 M out × $3.75 ≈ $82 ≈ ₹7k",
        "Cloud Run 2 vCPU / 2 GiB, mostly idle: ≈ ₹4–6k",
        "Supabase Pro $25 ≈ ₹2.1k · BigQuery + Storage: free tier",
        [("Total ≈ ₹15–20k/month ≈ ₹2.4 L/year", {"bold": True})]], size=8, gap=2)
    stat(s, 0.45, 4.05, 2.3, lakh(D["total_benefit_inr"]), "5-year benefit (simulated)", TEAL, 22)
    stat(s, 2.85, 4.05, 2.3, lakh(D["opex_cost_inr"]), "5-year cost of OpEx", INK, 22)
    stat(s, 5.25, 4.05, 2.1, f"{D['roi_multiple']:.1f}×", "net return on cost", INDIGO, 22)
    stat(s, 7.45, 4.05, 2.2, f"month {D['payback_months']}", "payback", INDIGO, 22)
    text(s, 0.38, 4.98, 9.2, 0.25, "Gemini prices: Google AI pricing page, Oct 2026 (gemini-3.8-flash $0.75 / $3.75 per M tokens until 31 Dec 2026). "
         "USD at ₹84.", size=7.5, color=MUTED)
    notes(s, "Costs are deliberately on the high side; benefit still covers them about 13 times.")


def crop(file: str, top: int, aspect: float, left: int = 480) -> Path:
    """Cut the useful band out of a 2x screenshot (skip the sidebar) so it reads at slide size."""
    from PIL import Image
    out = PITCH / "assets" / "crops" / file
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(SHOTS / file) as im:
        width = im.width - left
        im.crop((left, top, im.width, min(im.height, top + int(width / aspect)))).save(out)
    return out


def slide_snapshots(s):
    headline(s, "Working prototype: four real screens from the running app")
    shots = [("02_overview.png", 190, "Factory health and 'worry about first'"),
             ("05_decide.png", 190, "Options priced in ₹ + human approval"),
             ("07_sensor_drift.png", 190, "Faulty sensor caught: recalibrate, not a false breakdown alarm"),
             ("10_simulation_results.png", 190, "5-year results vs published benchmarks")]
    for i, (file, top, caption) in enumerate(shots):
        col, row = i % 2, i // 2
        x, y = 0.38 + col * 4.68, 1.55 + row * 1.86
        picture_fit(s, crop(file, top, 4.55 / 1.56, left=760 if "incident" in file else 480), x, y, 4.55, 1.56)
        text(s, x, y + 1.58, 4.55, 0.22, caption, size=8.5, color=MUTED, align=PP_ALIGN.CENTER)
    notes(s, "All four are live screens from the running app.")


def slide_performance(s):
    headline(s, "Scored on unseen data; results land inside published benchmarks")
    rows = [["Model (held-out test)", "Data", "Score"],
            ["Failure-mode classifier", "AI4I 2020 · 2,000 test rows", f"ROC AUC {FM['roc_auc_any_failure']:.3f} · P {FM['precision_at_threshold']:.0%} / R {FM['recall_at_threshold']:.0%}"],
            ["Remaining-life model", "NASA C-MAPSS FD001 · 100 test engines", f"RMSE {RUL['test_rmse_cycles']:.1f} cycles · NASA score {RUL['nasa_score']:.0f}"],
            ["Remaining-life 10–90% band", "same", f"covers {RUL['p10_p90_coverage']:.0%} of engines"],
            ["Component precursor model", "Azure PdM · Sep–Dec held out", "caught 94–100% of failures 24–32 h ahead"],
            ["Live overview (24 machines)", "app benchmark", "0.18 s warm · 5-yr simulation 4.5 s"]]
    table(s, 0.38, 1.6, 5.15, 2.25, rows, [1.7, 1.65, 1.8], size=8, bold_first_col=True)
    data = CategoryChartData()
    data.categories = ["Fewer breakdowns", "Lower maintenance cost"]
    data.add_series("OpEx (simulated)", (round(D["breakdowns_reduction"] * 100, 1), round(D["maintenance_cost_reduction"] * 100, 1)))
    data.add_series("US DOE low", (70, 25))
    data.add_series("US DOE high", (75, 30))
    frame = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(5.7), Inches(1.55), Inches(3.95), Inches(2.4), data)
    chart = frame.chart
    chart.has_title = True
    chart.chart_title.text_frame.text = "% improvement vs reactive maintenance"
    chart.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(9)
    chart.chart_title.text_frame.paragraphs[0].runs[0].font.bold = True
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(8)
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.font.size = Pt(8)
    plot.data_labels.number_format = '0.0"%"'
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for series, color in zip(plot.series, (INDIGO, "AAB2C5", "6B7489")):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = rgb(color)
    chart.value_axis.visible = False
    chart.value_axis.has_major_gridlines = False
    chart.category_axis.tick_labels.font.size = Pt(8)
    bullets(s, 0.38, 4.0, 9.25, 1.2, [
        [("Honest by design: ", {"bold": True}), ("the simulation counts model misses (sensor coverage 90%), people ignoring advice (15%), "
          f"{K['with']['false_alarms']:,.0f} false alarms over 5 years (each a 1 h inspection stop) and parts stock-outs.", {})],
        [("Equipment downtime ", {"bold": True}), (f"−{D['downtime_reduction'] * 100:.0f}% (DOE 35–45% counts all stops; our material and set-up stops, "
          "17.5% of planned time, stay identical in both worlds).", {})],
        [("Tested: ", {"bold": True}), ("7 automated tests (simulator determinism and benefit, live scenario, roles and decision flow); "
          "SQL verified on Postgres 18 with Supabase-style roles.", {})]], size=8.5, gap=2)
    notes(s, "Benchmarks from the US DOE O&M Best Practices Guide R3.0, section 5.4.")


def slide_calc(s):
    text(s, 0.38, 0.72, 9.0, 0.35, "How we calculated the 5-year numbers", size=16, color=INK,
         font="Google Sans Flex Medium")
    headline(s, "Same plant, same luck, two policies: where the ₹7.1 Cr comes from")
    rows = [["Benefit line", "Formula", "Result"],
            ["Production protected", f"{D['good_parts_gained']:,.0f} extra good parts × contribution ₹175–760 per part", lakh(D["production_protected_inr"])],
            ["Maintenance saved", "parts + labour (×1.5 overtime after breakdowns) + secondary damage + inspections", lakh(D["maintenance_savings_inr"])],
            ["Scrap avoided", f"{D['defects_avoided']:,.0f} fewer bad parts × scrap cost ₹380–1,450", lakh(D["scrap_savings_inr"])],
            ["Energy saved", f"{D['energy_saved_mwh']:,.0f} MWh × ₹9.25/kWh (MSEDCL HT FY27) · {D['co2_avoided_t']:,.0f} t CO₂ at 0.675 t/MWh (CEA v22)", lakh(D["energy_savings_inr"])],
            ["Total benefit", "sum of the four lines above", lakh(D["total_benefit_inr"])],
            ["Net benefit / ROI", f"{lakh(D['total_benefit_inr'])} − {lakh(D['opex_cost_inr'])} cost = {lakh(D['net_benefit_inr'])} · ÷ cost", f"{D['roi_multiple']:.1f}×"]]
    table(s, 0.38, 1.55, 5.75, 2.75, rows, [1.35, 3.45, 0.95], size=7.8, bold_first_col=True)
    card(s, 6.3, 1.55, 3.3, 2.75, fill=CARD)
    text(s, 6.42, 1.62, 3.1, 0.25, "Calibrated inputs", size=9.5, bold=True)
    bullets(s, 6.42, 1.9, 3.1, 2.4, [
        "Failures/machine-yr: bearing 1.79 · drive 2.59 · electrical 1.92 · coolant 1.31 (Azure PdM)",
        "Wear curve damage(u) = (e^3.75u − 1)/(e^3.75 − 1); life spread Weibull k 4.41 (NASA C-MAPSS)",
        "Prevented = recall 0.94–1.00 × sensor coverage 0.90 × follow-advice 0.85 ≈ 72–76%",
        "Warning timing error N(0.04, 0.20) of remaining life (C-MAPSS out-of-fold)",
        "Minor stops 8.9% + set-ups 8.6%, repair-time σ 0.82 (Zenodo real line)",
        "6,750 planned h/yr (3 shifts × 7.5 h × 300 days)"], size=8.3, gap=3)
    data = CategoryChartData()
    data.categories = [f"Year {y['year']}" for y in N["yearly"]]
    data.add_series("Without AI", [y["without"]["failures"] for y in N["yearly"]])
    data.add_series("With OpEx", [y["with"]["failures"] for y in N["yearly"]])
    frame = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.38), Inches(4.35), Inches(5.75), Inches(0.95), data)
    chart = frame.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.RIGHT
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(7)
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.font.size = Pt(7)
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for series, color in zip(plot.series, (PEACH, INDIGO)):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = rgb(color)
    chart.value_axis.visible = False
    chart.value_axis.has_major_gridlines = False
    chart.category_axis.tick_labels.font.size = Pt(7)
    text(s, 6.3, 4.4, 3.3, 0.9, [[("Breakdowns per year ", {"bold": True}), (f"{K['without']['failures']:.0f} → {K['with']['failures']:.0f} over 5 years. "
         f"OEE {K['without']['oee']:.1%} → {K['with']['oee']:.1%}: modest by design, because material and set-up losses are untouched.", {})]],
         size=7.8, color=INK)
    notes(s, "Walk the formula top to bottom; every input has a dataset or a cited source.")


def slide_future(s):
    headline(s, "Built to scale from one plant to India's 1,100+ ACMA members")
    phases = [("rocket", "Next 3 months", ["Pilot on 6 machines with OPC UA / MTConnect gateway",
                                           "Re-fit health estimators per machine", "Shift-handover summaries by Gemini"]),
              ("layers", "6–12 months", ["Multi-plant view and benchmarking", "Dataflow streaming into BigQuery",
                                          "Per-machine fine-tuning on Vertex AI with 6 months of data"]),
              ("eye", "Later", ["Line-camera visual inspection with Gemini", "Spare-parts auto-ordering",
                                "Energy tariff-aware scheduling (peak hours +25%)"])]
    for i, (ic, title, items) in enumerate(phases):
        x = 0.38 + i * 3.1
        card(s, x, 1.6, 2.95, 1.75, fill=CARD)
        icon(s, ic, ["indigo", "teal", "peach"][i], x + 0.15, 1.7, 0.36)
        text(s, x + 0.6, 1.76, 2.2, 0.3, title, size=11, bold=True)
        bullets(s, x + 0.15, 2.18, 2.7, 1.15, items, size=9.6, gap=4)
    card(s, 0.38, 3.5, 4.55, 1.72, fill="E5F4EC", line="9ED3B8")
    icon(s, "users", "teal", 0.5, 3.6, 0.34)
    text(s, 0.95, 3.63, 3.9, 0.28, "Community benefit", size=10.5, bold=True, color=TEAL)
    bullets(s, 0.5, 4.0, 4.35, 1.2, [
        "1.5 M people work directly in Indian auto components (ACMA): fewer emergency night repairs, safer work with LOTO steps built in",
        "Works in Hindi, Telugu, Tamil, Kannada, Marathi; read-aloud and voice for low-literacy and low-vision workers",
        f"{D['co2_avoided_t']:,.0f} t CO₂ avoided per 24-machine plant over 5 years (simulated)"], size=9.2, gap=4)
    card(s, 5.08, 3.5, 4.55, 1.72, fill="EEF0FD", line="B9BFF2")
    icon(s, "network", "indigo", 5.2, 3.6, 0.34)
    text(s, 5.65, 3.63, 3.9, 0.28, "Feasibility and scalability", size=10.5, bold=True, color=INDIGO)
    bullets(s, 5.2, 4.0, 4.35, 1.2, [
        "Runs today: one container, zero keys needed to try, one script to deploy",
        "Sensor-agnostic models (health-index features) transfer to any machine type",
        "Scale-out path: real ingest replaces the twin → Cloud Run instances → pgvector at 100k documents"], size=9.2, gap=4)
    notes(s, "Roadmap, then who benefits and why this is feasible now.")


def slide_links(s):
    box = title_box(s)
    links = {"GitHub Public Repository": "github.com/<your-team>/opex  (add after pushing)",
             "Demo Video Link (3 Minutes)": "<add YouTube / Drive link> (script in HOW_TO_RUN.md)",
             "Final Product Link": "<add Cloud Run URL> (./deploy/deploy_cloud_run.sh prints it)"}
    for p in box.text_frame.paragraphs:
        label = "".join(r.text for r in p.runs).strip()
        if label in links and p.runs:
            r = copy.deepcopy(p.runs[0]._r)
            p._p.append(r)
            p.runs[-1].text = ":  " + links[label]
            p.runs[-1].font.color.rgb = rgb(INDIGO)
    card(s, 0.38, 2.4, 9.25, 2.75, fill=CARD)
    text(s, 0.55, 2.52, 9.0, 0.3, "Try it in 60 seconds", size=12, bold=True)
    bullets(s, 0.55, 2.9, 4.4, 2.2, [
        "Click 'Explore as a guest' on the sign-in page, or sign in as engineer@opex.demo (password OpEx-demo-2026)",
        "Open M-17 → see the diagnosis → compare priced options → AI incident room → Approve",
        "5-year simulation → choose replay length → Simulate → Skip to results → Rewind the factory",
        "Settings → Display: try high contrast, extra-large text and Lexend"], size=9, gap=3)
    picture_fit(s, SHOTS / "09_simulation_live.png", 5.1, 2.55, 4.4, 2.5)
    notes(s, "Replace the three placeholders with the real links before exporting to PDF.")


def build() -> Path:
    prs = Presentation(PITCH / "template.pptx")
    slides = list(prs.slides)
    slide_team(slides[0])
    slide_brief(slides[2])
    slide_opportunities(slides[3])
    slide_features(slides[4])
    slide_flow(slides[5])
    slide_wireframes(slides[6])
    slide_architecture(slides[7])
    slide_tech(slides[8])
    slide_cost(slides[9])
    slide_snapshots(slides[10])
    slide_performance(slides[11])
    slide_future(slides[12])
    slide_links(slides[13])
    slide_calc(slides[14])
    notes(slides[15], "Thank you. Questions?")

    # Drop the template's instruction slide (#2) and move the calculation slide after the benchmarks.
    id_list = prs.slides._sldIdLst
    entries = list(id_list)
    instruction = entries[1]
    prs.part.drop_rel(instruction.rId)
    id_list.remove(instruction)
    entries = list(id_list)
    calc = entries[13]            # template slide 15, now 14th
    id_list.remove(calc)
    id_list.insert(11, calc)      # after performance (11th)

    out = PITCH / "OpEx_AI_Builder_Cup_2026.pptx"
    prs.save(out)
    return out


if __name__ == "__main__":
    print(build())
