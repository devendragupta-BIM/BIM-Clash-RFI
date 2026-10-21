"""
BIM Clash-to-RFI Automation Engine
====================================
Author  : Devendra Gupta
Project : Greenfield Tower — Block A
Stack   : Python · lxml · Groq AI · ReportLab
Purpose : Parse Navisworks clash XML → Generate professional RFI PDFs using AI
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()
import json
import re
from datetime import datetime, date
from lxml import etree
from groq import Groq
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT as AlignLeft, TA_CENTER as AlignCenter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY is empty! Check your .env file.")
    sys.exit(1)
print(f"🔑 Groq key loaded: {GROQ_API_KEY[:8]}...{GROQ_API_KEY[-4:]}")
XML_FILE       = "clash_report.xml"
OUTPUT_FOLDER  = "rfi_output"

DISCIPLINE_ROUTING = {
    "MEP"             : {"name": "Rajesh Kumar",     "email": "devendragupta56789@gmail.com",    "role": "Lead MEP Engineer"},
    "Structural"      : {"name": "Priya Sharma",     "email": "devendragupta56789@gmail.com",     "role": "Senior Structural Engineer"},
    "Electrical"      : {"name": "Amit Verma",       "email": "devendragupta56789@gmail.com",      "role": "Electrical Engineer"},
    "Fire Protection" : {"name": "Sunita Patel",     "email": "devendragupta56789@gmail.com",     "role": "Fire Protection Specialist"},
    "Fire Alarm"      : {"name": "Sunita Patel",     "email": "devendragupta56789@gmail.com",     "role": "Fire Protection Specialist"},
    "Plumbing"        : {"name": "Deepak Singh",     "email": "devendragupta56789@gmail.com",      "role": "Plumbing Engineer"},
    "Architectural"   : {"name": "Meera Nair",       "email": "devendragupta56789@gmail.com",          "role": "Project Architect"},
}

SEVERITY_COLORS = {
    "Critical" : colors.HexColor("#C0392B"),
    "High"     : colors.HexColor("#E67E22"),
    "Medium"   : colors.HexColor("#F1C40F"),
    "Low"      : colors.HexColor("#27AE60"),
}

SEVERITY_BADGE_TEXT = {
    "Critical" : colors.white,
    "High"     : colors.white,
    "Medium"   : colors.HexColor("#1a1a1a"),
    "Low"      : colors.white,
}

# Brand colors
BRAND_BLUE      = colors.HexColor("#1A3C6E")
BRAND_LIGHT     = colors.HexColor("#EBF2FA")
BRAND_ACCENT    = colors.HexColor("#2980B9")
BORDER_GREY     = colors.HexColor("#BDC3C7")
TEXT_DARK       = colors.HexColor("#2C3E50")
TEXT_MUTED      = colors.HexColor("#7F8C8D")


# ─────────────────────────────────────────────
#  STEP 1 — PARSE NAVISWORKS CLASH XML
# ─────────────────────────────────────────────

def parse_clash_xml(xml_path: str) -> tuple[dict, list[dict]]:
    """Parse Navisworks clash XML and return project info + list of clashes."""
    tree = etree.parse(xml_path)
    root = tree.getroot()

    # Project metadata
    proj = root.find("project")
    project_info = {
        "name"           : proj.findtext("name"),
        "number"         : proj.findtext("number"),
        "client"         : proj.findtext("client"),
        "location"       : proj.findtext("location"),
        "report_date"    : proj.findtext("report_date"),
        "total_clashes"  : proj.findtext("total_clashes"),
    }

    clashes = []
    for clash in root.findall(".//clash"):
        ea = clash.find("element_a")
        eb = clash.find("element_b")
        cp = clash.find("clash_point")

        clashes.append({
            "id"           : clash.get("id"),
            "status"       : clash.get("status"),
            "type"         : clash.get("type"),
            "name"         : clash.findtext("name"),
            "discipline_a" : clash.findtext("discipline_a"),
            "discipline_b" : clash.findtext("discipline_b"),
            "severity"     : clash.findtext("severity"),
            "description"  : clash.findtext("description"),
            "element_a": {
                "id"       : ea.findtext("id"),
                "category" : ea.findtext("category"),
                "family"   : ea.findtext("family"),
                "size"     : ea.findtext("size"),
                "system"   : ea.findtext("system"),
                "level"    : ea.findtext("level"),
                "grid"     : ea.findtext("grid_location"),
            },
            "element_b": {
                "id"       : eb.findtext("id"),
                "category" : eb.findtext("category"),
                "family"   : eb.findtext("family"),
                "size"     : eb.findtext("size"),
                "level"    : eb.findtext("level"),
                "grid"     : eb.findtext("grid_location"),
            },
            "clash_point": {
                "x" : cp.findtext("x"),
                "y" : cp.findtext("y"),
                "z" : cp.findtext("z"),
            },
            "distance"     : clash.findtext("distance"),
        })

    print(f"✅ Parsed {len(clashes)} clashes from XML")
    return project_info, clashes


# ─────────────────────────────────────────────
#  STEP 2 — ROUTE TO CORRECT ENGINEER
# ─────────────────────────────────────────────

def route_engineer(clash: dict) -> dict:
    """Determine responsible engineer based on discipline priority."""
    disc_a = clash["discipline_a"]
    disc_b = clash["discipline_b"]

    # Priority: MEP > Structural > Electrical > Fire > Plumbing > Architectural
    priority = ["MEP", "Structural", "Electrical", "Fire Protection", "Fire Alarm", "Plumbing", "Architectural"]

    for disc in priority:
        if disc in [disc_a, disc_b] and disc in DISCIPLINE_ROUTING:
            return DISCIPLINE_ROUTING[disc]

    return {"name": "BIM Coordinator", "email": "bim@project.com", "role": "BIM Coordinator"}


# ─────────────────────────────────────────────
#  STEP 3 — GROQ AI RFI CONTENT GENERATOR
# ─────────────────────────────────────────────

def generate_rfi_content(clash: dict, project: dict, engineer: dict) -> dict:
    """Use Groq AI to generate professional RFI content for a clash."""

    client = Groq(api_key=GROQ_API_KEY)

    system_prompt = """You are a senior BIM Coordination Engineer with 15 years of experience 
on large commercial construction projects in India. You write professional Request for Information (RFI) 
documents that are clear, technically precise, and action-oriented.

Your RFIs always follow this exact structure and you MUST respond ONLY with valid JSON — 
no preamble, no markdown fences, just raw JSON:

{
  "subject": "Brief subject line for this RFI",
  "technical_description": "2-3 sentences describing the clash technically and precisely",
  "impact_assessment": "1-2 sentences on project impact if unresolved (schedule, safety, cost)",
  "applicable_codes": ["List of relevant Indian/International codes that apply"],
  "proposed_resolution": "Your recommended resolution as the BIM coordinator",
  "alternative_solutions": ["Option 1 description", "Option 2 description"],
  "information_required": "Exactly what information/approval you need from the engineer",
  "priority_justification": "Why this severity level is assigned",
  "response_deadline": "Recommended deadline based on severity (e.g. 24 hours / 3 days / 1 week)"
}"""

    user_prompt = f"""Generate a professional RFI for this BIM clash:

PROJECT: {project['name']} ({project['number']})
CLIENT: {project['client']}

CLASH ID: {clash['id']}
CLASH TYPE: {clash['type']}
SEVERITY: {clash['severity']}
LOCATION: Level {clash['element_a']['level']}, Grid {clash['element_a']['grid']}

ELEMENT A: {clash['element_a']['category']} — {clash['element_a']['family']} ({clash['element_a']['size']})
System: {clash['element_a'].get('system', 'N/A')}
Revit ID: {clash['element_a']['id']}

ELEMENT B: {clash['element_b']['category']} — {clash['element_b']['family']} ({clash['element_b']['size']})
Revit ID: {clash['element_b']['id']}

PENETRATION DEPTH: {clash['distance']}m
DISCIPLINES: {clash['discipline_a']} vs {clash['discipline_b']}

NAVISWORKS DESCRIPTION: {clash['description']}

Assigned Engineer: {engineer['name']} ({engineer['role']})

Write a professional RFI. Be technically precise. Reference Indian codes (IS, NBC 2016, OISD) where relevant."""

    response = client.chat.completions.create(
        model="qwen/qwen3.8-27b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=1000,
    )

    raw = response.choices[0].message.content.strip()

    # Clean potential markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback if JSON parse fails
        return {
            "subject"              : clash["name"],
            "technical_description": clash["description"],
            "impact_assessment"    : "Immediate coordination required to prevent construction delay.",
            "applicable_codes"     : ["NBC 2016", "IS 456", "IE Rules 1956"],
            "proposed_resolution"  : "Refer to assigned engineer for resolution.",
            "alternative_solutions": ["Reroute conflicting element", "Structural penetration with approval"],
            "information_required" : "Revised drawing and written approval required.",
            "priority_justification": f"Classified as {clash['severity']} due to clash type {clash['type']}.",
            "response_deadline"    : "3 working days",
        }


# ─────────────────────────────────────────────
#  STEP 4 — PROFESSIONAL PDF GENERATOR
# ─────────────────────────────────────────────

def build_pdf(clash: dict, project: dict, engineer: dict, rfi: dict,
              rfi_number: str, output_path: str):
    """Generate a professional multi-section RFI PDF."""

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=15*mm,  bottomMargin=15*mm,
    )

    W = A4[0] - 36*mm   # usable width
    story = []
    styles = getSampleStyleSheet()

    # ── Custom styles ──────────────────────────────────────
    def style(name, **kw):
        base = kw.pop("parent", "Normal")
        s = ParagraphStyle(name, parent=styles[base], **kw)
        return s

    S = {
        "h_company"   : style("hc", fontSize=9,  textColor=colors.white,   fontName="Helvetica-Bold",  leading=12),
        "h_title"     : style("ht", fontSize=16, textColor=colors.white,   fontName="Helvetica-Bold",  leading=20),
        "h_sub"       : style("hs", fontSize=9,  textColor=colors.HexColor("#BFD7F0"), fontName="Helvetica", leading=12),
        "label"       : style("lb", fontSize=7.5,textColor=TEXT_MUTED,     fontName="Helvetica-Bold",  leading=10, spaceAfter=1),
        "value"       : style("vl", fontSize=9,  textColor=TEXT_DARK,      fontName="Helvetica",       leading=12),
        "value_bold"  : style("vb", fontSize=9,  textColor=TEXT_DARK,      fontName="Helvetica-Bold",  leading=12),
        "section_hdr" : style("sh", fontSize=10, textColor=colors.white,   fontName="Helvetica-Bold",  leading=13),
        "body"        : style("bd", fontSize=8.5,textColor=TEXT_DARK,      fontName="Helvetica",       leading=13, spaceAfter=3),
        "bullet"      : style("bu", fontSize=8.5,textColor=TEXT_DARK,      fontName="Helvetica",       leading=13, leftIndent=12, spaceAfter=2),
        "footer"      : style("ft", fontSize=7,  textColor=TEXT_MUTED,     fontName="Helvetica",       leading=9,  alignment=AlignCenter),
        "tag"         : style("tg", fontSize=8,  textColor=colors.white,   fontName="Helvetica-Bold",  leading=10),
    }

    sev        = clash["severity"]
    sev_color  = SEVERITY_COLORS.get(sev, BRAND_BLUE)
    sev_text   = SEVERITY_BADGE_TEXT.get(sev, colors.white)
    today      = date.today().strftime("%d %B %Y")
    gen_time   = datetime.now().strftime("%d-%b-%Y %H:%M")

    # ── HEADER BANNER ──────────────────────────────────────
    header_data = [[
        Paragraph("GREENFIELD DEVELOPERS PVT LTD<br/><font size='7'>BIM Coordination — Request for Information</font>", S["h_company"]),
        Paragraph(f"RFI #{rfi_number}", S["h_title"]),
        Paragraph(f"Issued: {today}<br/>Auto-generated by BIM Clash Engine", S["h_sub"]),
    ]]
    header_tbl = Table(header_data, colWidths=[W*0.38, W*0.32, W*0.30])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), BRAND_BLUE),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
        ("TOPPADDING",  (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("ALIGN",       (1,0), (1,0),   "CENTER"),
        ("ALIGN",       (2,0), (2,0),   "RIGHT"),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 4*mm))

    # ── SEVERITY + CLASH TYPE BADGES ───────────────────────
    badge_data = [[
        Paragraph(f"  ● {sev.upper()} SEVERITY  ", S["tag"]),
        Paragraph(f"  {clash['type'].upper()}  ", S["tag"]),
        Paragraph(f"  {clash['discipline_a'].upper()} vs {clash['discipline_b'].upper()}  ", S["tag"]),
        Paragraph(f"  {clash['element_a']['level'].upper()}  ", S["tag"]),
        Paragraph(f"  GRID {clash['element_a']['grid']}  ", S["tag"]),
    ]]
    badge_tbl = Table(badge_data, colWidths=[W*0.18, W*0.17, W*0.28, W*0.18, W*0.19])
    badge_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (0,0), sev_color),
        ("BACKGROUND",   (1,0), (1,0), BRAND_ACCENT),
        ("BACKGROUND",   (2,0), (2,0), colors.HexColor("#8E44AD")),
        ("BACKGROUND",   (3,0), (3,0), colors.HexColor("#16A085")),
        ("BACKGROUND",   (4,0), (4,0), colors.HexColor("#2C3E50")),
        ("ROUNDEDCORNERS", (0,0), (-1,-1), 3),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
    ]))
    story.append(badge_tbl)
    story.append(Spacer(1, 4*mm))

    # ── PROJECT + RFI METADATA ─────────────────────────────
    def section_header(title):
        t = Table([[Paragraph(f"  {title}", S["section_hdr"])]], colWidths=[W])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), BRAND_BLUE),
            ("TOPPADDING",   (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0), (-1,-1), 5),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ]))
        return t

    def info_row(pairs, widths=None):
        """pairs = list of (label, value) tuples displayed as a grid row."""
        n = len(pairs)
        if widths is None:
            w = W / n
            widths = [w] * n
        cells = []
        for lbl, val in pairs:
            cells.append(
                Paragraph(f"<b>{lbl}</b><br/>{val}", S["value"])
            )
        t = Table([cells], colWidths=widths)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), BRAND_LIGHT),
            ("BOX",           (0,0), (-1,-1), 0.5, BORDER_GREY),
            ("INNERGRID",     (0,0), (-1,-1), 0.5, BORDER_GREY),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ]))
        return t

    story.append(section_header("PROJECT INFORMATION"))
    story.append(Spacer(1, 1*mm))
    story.append(info_row([
        ("Project Name", project["name"]),
        ("Project Number", project["number"]),
        ("Client", project["client"]),
    ]))
    story.append(Spacer(1, 1*mm))
    story.append(info_row([
        ("Location", project["location"]),
        ("RFI Number", rfi_number),
        ("Date Issued", today),
    ]))
    story.append(Spacer(1, 4*mm))

    # ── RFI SUBJECT ────────────────────────────────────────
    story.append(section_header("RFI SUBJECT"))
    story.append(Spacer(1, 1*mm))
    subj_tbl = Table(
        [[Paragraph(str(rfi.get("subject") or clash.get("name") or "RFI Subject"), S["value_bold"])]],
        colWidths=[W]
    )
    subj_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), BRAND_LIGHT),
        ("BOX",           (0,0), (-1,-1), 0.5, BORDER_GREY),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story.append(subj_tbl)
    story.append(Spacer(1, 4*mm))

    # ── CLASH ELEMENTS ─────────────────────────────────────
    story.append(section_header("CLASH ELEMENT DETAILS"))
    story.append(Spacer(1, 1*mm))

    ea, eb = clash["element_a"], clash["element_b"]
    clash_data = [
        [
            Paragraph("<b>Field</b>", S["value_bold"]),
            Paragraph(f"<b>Element A — {clash['discipline_a']}</b>", S["value_bold"]),
            Paragraph(f"<b>Element B — {clash['discipline_b']}</b>", S["value_bold"]),
        ],
        [Paragraph("Revit ID",  S["label"]), Paragraph(str(ea.get("id") or "—"),       S["value"]), Paragraph(str(eb.get("id") or "—"),       S["value"])],
        [Paragraph("Category",  S["label"]), Paragraph(str(ea.get("category") or "—"),  S["value"]), Paragraph(str(eb.get("category") or "—"),  S["value"])],
        [Paragraph("Family",    S["label"]), Paragraph(str(ea.get("family") or "—"),    S["value"]), Paragraph(str(eb.get("family") or "—"),    S["value"])],
        [Paragraph("Size",      S["label"]), Paragraph(str(ea.get("size") or "—"),      S["value"]), Paragraph(str(eb.get("size") or "—"), S["value"])],
        [Paragraph("System",    S["label"]), Paragraph(str(ea.get("system") or "—"), S["value"]), Paragraph("—",        S["value"])],
        [Paragraph("Level",     S["label"]), Paragraph(str(ea.get("level") or "—"),     S["value"]), Paragraph(str(eb.get("level") or "—"),     S["value"])],
        [Paragraph("Grid Ref",  S["label"]), Paragraph(str(ea.get("grid") or "—"),      S["value"]), Paragraph(str(eb.get("grid") or "—"), S["value"])],
    ]
    cp = clash["clash_point"]
    clash_data.append([
        Paragraph("Clash Point", S["label"]),
        Paragraph(f"X: {cp['x']}  Y: {cp['y']}  Z: {cp['z']}", S["value"]),
        Paragraph(f"Penetration: {clash['distance']}m", S["value"]),
    ])

    clash_tbl = Table(clash_data, colWidths=[W*0.18, W*0.41, W*0.41])
    clash_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  BRAND_BLUE),
        ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
        ("BACKGROUND",    (0,1), (-1,-1), BRAND_LIGHT),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [BRAND_LIGHT, colors.white]),
        ("BOX",           (0,0), (-1,-1), 0.5, BORDER_GREY),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, BORDER_GREY),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(clash_tbl)
    story.append(Spacer(1, 4*mm))

    # ── TECHNICAL DESCRIPTION ──────────────────────────────
    story.append(section_header("TECHNICAL DESCRIPTION"))
    story.append(Spacer(1, 1*mm))
    desc_tbl = Table(
        [[Paragraph(str(rfi.get("technical_description") or clash.get("description") or "See clash details."), S["body"])]],
        colWidths=[W]
    )
    desc_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.white),
        ("BOX",           (0,0), (-1,-1), 0.5, BORDER_GREY),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story.append(desc_tbl)
    story.append(Spacer(1, 3*mm))

    # ── IMPACT ASSESSMENT ─────────────────────────────────
    story.append(section_header("IMPACT ASSESSMENT"))
    story.append(Spacer(1, 1*mm))
    impact_tbl = Table(
        [[Paragraph(str(rfi.get("impact_assessment") or "Immediate coordination required."), S["body"])]],
        colWidths=[W]
    )
    impact_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#FDF2F2")),
        ("BOX",           (0,0), (-1,-1), 0.8, sev_color),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story.append(impact_tbl)
    story.append(Spacer(1, 3*mm))

    # ── APPLICABLE CODES ──────────────────────────────────
    codes = rfi.get("applicable_codes", [])
    if codes:
        story.append(section_header("APPLICABLE CODES & STANDARDS"))
        story.append(Spacer(1, 1*mm))
        codes_text = "  •  ".join(codes) if codes else "NBC 2016, IS 456"
        codes_tbl = Table(
            [[Paragraph(f"• " + "<br/>• ".join(codes), S["body"])]],
            colWidths=[W]
        )
        codes_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), BRAND_LIGHT),
            ("BOX",           (0,0), (-1,-1), 0.5, BORDER_GREY),
            ("LEFTPADDING",   (0,0), (-1,-1), 14),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        story.append(codes_tbl)
        story.append(Spacer(1, 3*mm))

    # ── PROPOSED RESOLUTION + ALTERNATIVES ────────────────
    story.append(section_header("PROPOSED RESOLUTION"))
    story.append(Spacer(1, 1*mm))

    res_rows = [[Paragraph(str(rfi.get("proposed_resolution") or "Refer to assigned engineer for resolution."), S["body"])]]
    alts = rfi.get("alternative_solutions", [])
    if alts:
        alt_text = "<br/>".join([f"<b>Option {i+1}:</b> {a}" for i, a in enumerate(alts)])
        res_rows.append([Paragraph(alt_text, S["body"])])

    res_tbl = Table(res_rows, colWidths=[W])
    res_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.white),
        ("BOX",           (0,0), (-1,-1), 0.5, BORDER_GREY),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, BORDER_GREY),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(res_tbl)
    story.append(Spacer(1, 3*mm))

    # ── INFORMATION REQUIRED ──────────────────────────────
    story.append(section_header("INFORMATION REQUIRED"))
    story.append(Spacer(1, 1*mm))
    info_tbl = Table(
        [[Paragraph(str(rfi.get("information_required") or "Revised drawing and written approval required."), S["body"])]],
        colWidths=[W]
    )
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#F0FFF4")),
        ("BOX",           (0,0), (-1,-1), 0.8, colors.HexColor("#27AE60")),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 3*mm))

    # ── ROUTING + DEADLINE ────────────────────────────────
    story.append(section_header("ROUTING & RESPONSE DEADLINE"))
    story.append(Spacer(1, 1*mm))
    deadline = rfi.get("response_deadline", "3 working days")
    routing_data = [
        [
            Paragraph("<b>Assigned To</b><br/>" + engineer["name"],       S["value"]),
            Paragraph("<b>Role</b><br/>" + engineer["role"],               S["value"]),
            Paragraph("<b>Email</b><br/>" + engineer["email"],             S["value"]),
            Paragraph(f"<b>Response Required</b><br/>{deadline}", S["value"]),
        ]
    ]
    route_tbl = Table(routing_data, colWidths=[W*0.22, W*0.28, W*0.32, W*0.18])
    route_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), BRAND_LIGHT),
        ("BOX",           (0,0), (-1,-1), 0.5, BORDER_GREY),
        ("INNERGRID",     (0,0), (-1,-1), 0.5, BORDER_GREY),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ]))
    story.append(route_tbl)
    story.append(Spacer(1, 4*mm))

    # ── SIGNATURE / ISSUED BY ─────────────────────────────
    sig_data = [[
        Paragraph(
            "<b>Issued By:</b> Devendra Gupta  |  BIM Automation Engineer<br/>"
            "<b>Company:</b> Greenfield BIM Team  |  "
            f"<b>Date:</b> {today}  |  "
            f"<b>Auto-generated:</b> {gen_time}",
            S["footer"]
        )
    ]]
    sig_tbl = Table(sig_data, colWidths=[W])
    sig_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), BRAND_BLUE),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TEXTCOLOR",     (0,0), (-1,-1), colors.white),
    ]))
    story.append(sig_tbl)

    doc.build(story)
    print(f"  ✅ PDF saved → {output_path}")


# ─────────────────────────────────────────────
#  MAIN RUNNER
# ─────────────────────────────────────────────

def main():
    print("\n" + "="*55)
    print("  BIM CLASH-TO-RFI AUTOMATION ENGINE")
    print("  by Devendra Gupta")
    print("="*55 + "\n")

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # 1. Parse XML
    print("📂 Step 1 — Parsing Navisworks clash XML...")
    project, clashes = parse_clash_xml(XML_FILE)
    print(f"   Project : {project['name']}")
    print(f"   Clashes : {len(clashes)} found\n")

    # 2. Process each clash
    results = []
    for i, clash in enumerate(clashes, 1):
        print(f"🔄 Processing clash {i}/{len(clashes)} → {clash['id']} [{clash['severity']}]")

        # Route engineer
        engineer  = route_engineer(clash)
        rfi_num   = f"RFI-{project['number']}-{clash['id']}"
        out_path  = os.path.join(OUTPUT_FOLDER, f"{rfi_num}.pdf")

        print(f"   → Routed to: {engineer['name']} ({engineer['role']})")
        print(f"   → Calling Groq AI to generate RFI content...")

        # Generate AI content with retry on rate limit
        import time
        for attempt in range(5):
            try:
                rfi_content = generate_rfi_content(clash, project, engineer)
                break
            except Exception as e:
                if "rate_limit_exceeded" in str(e) or "429" in str(e):
                    wait = 15 + (attempt * 5)
                    print(f"   ⏳ Rate limit — waiting {wait}s before retry ({attempt+1}/5)...")
                    time.sleep(wait)
                else:
                    raise e
        time.sleep(12)  # 12s gap between clashes to stay under free tier limit

        # Build PDF
        print(f"   → Building PDF...")
        build_pdf(clash, project, engineer, rfi_content, rfi_num, out_path)

        results.append({
            "clash_id"    : clash["id"],
            "rfi_number"  : rfi_num,
            "severity"    : clash["severity"],
            "discipline"  : f"{clash['discipline_a']} vs {clash['discipline_b']}",
            "assigned_to" : engineer["name"],
            "email"       : engineer["email"],
            "pdf"         : out_path,
            "subject"     : rfi_content.get("subject", clash["name"]),
            "deadline"    : rfi_content.get("response_deadline", "3 days"),
        })

    # 3. Summary
    print("\n" + "="*55)
    print(f"✅ ENGINE COMPLETE — {len(results)} RFIs generated")
    print("="*55)

    critical = [r for r in results if r["severity"] == "Critical"]
    high     = [r for r in results if r["severity"] == "High"]
    medium   = [r for r in results if r["severity"] == "Medium"]
    low      = [r for r in results if r["severity"] == "Low"]

    print(f"\n📊 SEVERITY BREAKDOWN:")
    print(f"   🔴 Critical : {len(critical)}")
    print(f"   🟠 High     : {len(high)}")
    print(f"   🟡 Medium   : {len(medium)}")
    print(f"   🟢 Low      : {len(low)}")

    print(f"\n📁 RFI PDFs saved to: ./{OUTPUT_FOLDER}/")
    print(f"\n📋 ROUTING SUMMARY:")
    for r in results:
        sev_icon = {"Critical":"🔴","High":"🟠","Medium":"🟡","Low":"🟢"}.get(r["severity"],"⚪")
        print(f"   {sev_icon} {r['rfi_number']} → {r['assigned_to']} ({r['email']})")

    # Save summary JSON
    summary_path = os.path.join(OUTPUT_FOLDER, "rfi_summary.json")
    with open(summary_path, "w") as f:
        json.dump({"project": project, "rfis": results}, f, indent=2)
    print(f"\n📄 Summary JSON → {summary_path}")
    print("\n🚀 Ready for n8n automation & Google Sheets dashboard!\n")

    return results


if __name__ == "__main__":
    main()
