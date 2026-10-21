"""
BIM Clash-to-RFI Engine — Master Runner
=========================================
Author  : Devendra Gupta
Purpose : Run the full pipeline in one command
          XML → Parse → AI → PDF → Sheets → Telegram

Usage:
    python run_engine.py                         # uses default clash_report.xml
    python run_engine.py my_clash_file.xml       # uses your own XML file
"""

import sys
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Allow passing a custom XML file as argument
XML_FILE = sys.argv[1] if len(sys.argv) > 1 else "clash_report.xml"

def check_env():
    """Check all required config before running."""
    print("🔍 Checking configuration...")

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key or groq_key == "your_groq_api_key_here":
        print("❌ GROQ_API_KEY not set in .env")
        print("   Get your free key at: https://console.groq.com")
        return False

    if not os.path.exists(XML_FILE):
        print(f"❌ XML file not found: {XML_FILE}")
        print(f"   Place your Navisworks clash XML in the same folder")
        return False

    print("✅ Configuration OK")
    print(f"✅ XML file found: {XML_FILE}")
    return True


def main():
    print("\n" + "█"*55)
    print("█  BIM CLASH-TO-RFI AUTOMATION ENGINE          █")
    print("█  by Devendra Gupta                           █")
    print("█  Stack: Python · Groq AI · ReportLab · n8n  █")
    print("█"*55 + "\n")

    # ── Pre-flight check ──────────────────────────────────
    if not check_env():
        print("\n📖 Setup guide:")
        print("   1. Copy .env.example to .env")
        print("   2. Add your GROQ_API_KEY from console.groq.com")
        print("   3. Run again\n")
        sys.exit(1)

    start_time = time.time()

    # ── Step 1: Core engine — parse + AI + PDF ────────────
    print("\n" + "─"*55)
    print("STEP 1/3 — Running core engine (Parse + AI + PDF)")
    print("─"*55)

    # Import and run with the user's XML file
    import clash_to_rfi as engine
    engine.XML_FILE = XML_FILE
    results = engine.main()

    # ── Step 2: Google Sheets dashboard ──────────────────
    print("\n" + "─"*55)
    print("STEP 2/3 — Pushing to Google Sheets dashboard")
    print("─"*55)

    try:
        from dashboard import push_summary_stats, push_to_sheets, SHEET_ID
        push_summary_stats("rfi_output/rfi_summary.json")
        if SHEET_ID and SHEET_ID != "your_google_sheet_id_here":
            push_to_sheets("rfi_output/rfi_summary.json")
        else:
            print("⚠️  Google Sheets skipped — add GOOGLE_SHEET_ID to .env to enable")
    except Exception as e:
        print(f"⚠️  Google Sheets skipped: {e}")

    # ── Step 3: Telegram notifications ───────────────────
    print("\n" + "─"*55)
    print("STEP 3/3 — Sending Telegram notifications")
    print("─"*55)

    try:
        from notifier import notify_critical_rfis
        notify_critical_rfis("rfi_output/rfi_summary.json")
    except Exception as e:
        print(f"⚠️  Telegram skipped: {e}")

    # ── Final summary ─────────────────────────────────────
    elapsed = round(time.time() - start_time, 1)
    total   = len(results) if results else 0
    critical = len([r for r in results if r["severity"] == "Critical"]) if results else 0

    print("\n" + "█"*55)
    print(f"█  ✅ PIPELINE COMPLETE in {elapsed}s")
    print(f"█  📄 {total} RFI PDFs generated")
    print(f"█  🔴 {critical} Critical clashes flagged")
    print(f"█  📁 Output folder: ./rfi_output/")
    print("█"*55 + "\n")


if __name__ == "__main__":
    main()
