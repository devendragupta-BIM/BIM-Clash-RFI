"""
Google Sheets Live Dashboard
==============================
Author  : Devendra Gupta
Purpose : Push all RFI data to Google Sheets for live clash tracking
"""

import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")

def push_to_sheets(summary_json_path: str):
    """Read rfi_summary.json and push every RFI to Google Sheets."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("⚠️  gspread not installed. Run: pip install gspread google-auth")
        return

    # Load summary
    with open(summary_json_path) as f:
        data = json.load(f)

    project = data["project"]
    rfis    = data["rfis"]

    # Auth
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds  = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    sheet  = client.open_by_key(SHEET_ID)

    # ── Sheet 1: RFI Tracker ──────────────────────────────
    try:
        ws = sheet.worksheet("RFI Tracker")
        ws.clear()
    except:
        ws = sheet.add_worksheet(title="RFI Tracker", rows=200, cols=12)

    headers = [
        "RFI Number", "Clash ID", "Severity", "Clash Type",
        "Discipline A", "Discipline B", "Level", "Grid",
        "Assigned To", "Email", "Response Deadline", "Status",
        "Subject", "Date Issued"
    ]
    ws.append_row(headers)

    severity_colors = {
        "Critical" : {"red": 0.75, "green": 0.18, "blue": 0.18},
        "High"     : {"red": 0.9,  "green": 0.47, "blue": 0.13},
        "Medium"   : {"red": 0.95, "green": 0.76, "blue": 0.05},
        "Low"      : {"red": 0.15, "green": 0.68, "blue": 0.38},
    }

    rows = []
    for rfi in rfis:
        rows.append([
            rfi["rfi_number"],
            rfi["clash_id"],
            rfi["severity"],
            rfi.get("clash_type", "Hard Clash"),
            rfi["discipline"].split(" vs ")[0],
            rfi["discipline"].split(" vs ")[1] if " vs " in rfi["discipline"] else "",
            rfi.get("level", ""),
            rfi.get("grid", ""),
            rfi["assigned_to"],
            rfi["email"],
            rfi["deadline"],
            "Open",
            rfi["subject"],
            datetime.today().strftime("%d-%b-%Y"),
        ])

    if rows:
        ws.append_rows(rows)

    print(f"✅ Google Sheets updated — {len(rows)} RFIs pushed")
    print(f"   → https://docs.google.com/spreadsheets/d/{SHEET_ID}")


# ── Sheet 2: Summary Stats ────────────────────────────
def push_summary_stats(summary_json_path: str):
    """Push a summary stats tab — counts by severity and discipline."""
    with open(summary_json_path) as f:
        data = json.load(f)

    rfis = data["rfis"]

    severity_count = {}
    discipline_count = {}

    for rfi in rfis:
        sev  = rfi["severity"]
        disc = rfi["discipline"]
        severity_count[sev]   = severity_count.get(sev, 0) + 1
        discipline_count[disc] = discipline_count.get(disc, 0) + 1

    print("\n📊 SUMMARY STATS:")
    print("   Severity Breakdown:")
    for k, v in severity_count.items():
        icon = {"Critical":"🔴","High":"🟠","Medium":"🟡","Low":"🟢"}.get(k,"⚪")
        print(f"     {icon} {k}: {v}")

    print("   Discipline Clashes:")
    for k, v in discipline_count.items():
        print(f"     • {k}: {v}")


if __name__ == "__main__":
    summary = "rfi_output/rfi_summary.json"
    if os.path.exists(summary):
        push_summary_stats(summary)
        if SHEET_ID and SHEET_ID != "your_google_sheet_id_here":
            push_to_sheets(summary)
        else:
            print("\n⚠️  Add GOOGLE_SHEET_ID to .env to enable Google Sheets sync")
    else:
        print("❌ rfi_summary.json not found. Run clash_to_rfi.py first.")
