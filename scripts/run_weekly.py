"""Weekly Meta Ads report. Runs every Monday at 04:00 via cron."""

import os
import sys
import traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(__file__))

from fetch_meta_weekly import fetch_and_save
from analyze_weekly import analyze_weekly
from ai_audit import ai_audit
from send_telegram import send_message
from ig_followers import fetch_and_record, format_followers_block

WEEKLY_SYSTEM_PROMPT = """Ты — эксперт по платной рекламе в Meta Ads (Facebook/Instagram).
Тебе передаются данные туристической компании за две недели для сравнительного анализа.
Это еженедельный стратегический отчёт — давай более глубокий анализ, чем ежедневный.

Ответ строго на русском языке. Структура:

**ОБЩАЯ ОЦЕНКА НЕДЕЛИ** (2-3 предложения — лучше или хуже, почему)

**КЛЮЧЕВЫЕ ТЕНДЕНЦИИ**
- Эффективность: [CTR, CPC тренды и их причины]
- Креативы: [что работает, что выгорает]
- Аудитория: [охват, частота, насыщение]
- Бюджет: [распределение, эффективность]

**ГЛАВНЫЕ ОТКРЫТИЯ НЕДЕЛИ** (3 конкретных инсайта с цифрами)

**СТРАТЕГИЧЕСКИЕ РЕКОМЕНДАЦИИ НА СЛЕДУЮЩУЮ НЕДЕЛЮ** (3-5 конкретных действий)

Будь конкретен. Ссылайся на названия кампаний и реальные цифры."""


def main():
    print("[run_weekly] Starting weekly Meta Ads report...")
    try:
        fetch_and_save()
        ig_snap = fetch_and_record()

        report, summary = analyze_weekly()

        print("[run_weekly] Requesting AI weekly audit from Claude...")

        # Override the prompt in ai_audit by passing a custom one
        import subprocess, shutil
        claude_bin = shutil.which("claude") or "/home/user/.local/bin/claude"
        from ai_audit import WEEKLY_PROMPT
        prompt = f"{WEEKLY_PROMPT}\n\n=== ДАННЫЕ ===\n{summary}"
        result = subprocess.run(
            [claude_bin, "--print", "--dangerously-skip-permissions", "-p", prompt],
            capture_output=True, text=True, timeout=600,
        )
        ai_text = result.stdout.strip() if result.returncode == 0 and result.stdout.strip() \
            else f"[AI аудит недоступен: {result.stderr[:200]}]"

        followers_block = format_followers_block(ig_snap, period="week")
        if followers_block:
            report = report + "\n\n" + followers_block

        full_report = report + "\n\n━━━━ AI СТРАТЕГИЧЕСКИЙ АУДИТ ━━━━\n" + ai_text

        # Archive
        date_str = datetime.now().strftime("%Y-%m-%d")
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        report_path = os.path.join(reports_dir, f"weekly_{date_str}.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_report)

        send_message(full_report)
        print(f"[run_weekly] Done. Report saved → reports/weekly_{date_str}.txt")

    except Exception:
        err = traceback.format_exc()
        print(f"[run_weekly] ERROR:\n{err}")
        try:
            send_message(f"❌ *Meta Ads недельный отчёт — ошибка*\n\n```{err[-1000:]}```")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
