"""Daily Meta Ads report orchestrator. Runs at 03:00 via cron."""

import os
import sys
import traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(__file__))

from fetch_meta_ads import fetch_and_save
from analyze_campaigns import analyze
from ai_audit import ai_audit
from send_telegram import send_message
from ig_followers import fetch_and_record, format_followers_block
from creative_burnout import detect_burnout, format_burnout_block, burnout_ai_summary
from crm_attribution import build_attribution


def main():
    print("[run_daily] Starting Meta Ads daily report...")
    try:
        # --- Fetch ---
        raw = fetch_and_save()

        try:
            ig_snap = fetch_and_record()
        except Exception as e:
            print(f"[run_daily] ig_followers fetch failed (non-fatal): {e}")
            ig_snap = None

        # --- Analyze ---
        report, summary = analyze()

        # --- Creative burnout ---
        burnout = detect_burnout(
            raw.get("ad_insights_yesterday", []),
            raw.get("ad_insights_7d", []),
        )
        burnout_block = format_burnout_block(burnout)
        burnout_summary = burnout_ai_summary(burnout)

        # --- CRM attribution ---
        attribution_block, attribution_summary = build_attribution()

        # --- AI audit ---
        print("[run_daily] Requesting AI audit from Claude...")
        ai_text = ai_audit(summary + "\n\n" + burnout_summary + "\n\n" + attribution_summary, mode="daily")

        followers_block = format_followers_block(ig_snap, period="day")
        if followers_block:
            report = report + "\n\n" + followers_block

        report = report + "\n\n" + burnout_block

        full_report = report + "\n\n━━━━ AI АУДИТ ━━━━\n" + ai_text

        # --- Archive ---
        date_str = datetime.now().strftime("%Y-%m-%d")
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        report_path = os.path.join(reports_dir, f"{date_str}.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_report)

        send_message(full_report)

        # CRM attribution — отдельным сообщением (HTML-форматирование)
        if attribution_block:
            send_message(attribution_block, parse_mode="HTML")
            print("[run_daily] CRM attribution sent.")

        print(f"[run_daily] Done. Report saved → reports/{date_str}.txt")

    except Exception:
        err = traceback.format_exc()
        print(f"[run_daily] ERROR:\n{err}")
        try:
            send_message(f"❌ *Meta Ads отчёт — ошибка*\n\n```{err[-1000:]}```")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
