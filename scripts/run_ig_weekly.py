"""Недельный дайджест Instagram → Telegram. Cron: понедельник утром.

Сбор данных (fetch_ig_weekly) → текст дайджеста (analyze_ig_weekly) →
краткий AI-вывод недели через Qwen (--role reason, с фолбэком при лимите) →
отправка в Telegram + архив в reports/.
"""
import os
import sys
import shutil
import subprocess
import traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(__file__))

from fetch_ig_weekly import fetch_and_save
from analyze_ig_weekly import build_digest, build_ai_summary
from send_telegram import send_message

AI_INSTRUCTION = (
    "Ты — SMM-аналитик туристической компании (Instagram @gotrips_by). "
    "На входе — недельные метрики инстаграма и топ контента. Дай КРАТКИЙ вывод "
    "на русском (3-5 предложений, без markdown-заголовков): что с охватом и "
    "вовлечённостью относительно прошлой недели, какой формат/тема зашли лучше, "
    "1-2 конкретных совета на следующую неделю. Без воды и общих фраз."
)


def qwen_commentary(summary: str) -> str:
    """Краткий вывод недели через Qwen. Пустая строка, если недоступен/лимит."""
    qwen = shutil.which("qwen-ask") or "/home/user/.local/bin/qwen-ask"
    if not os.path.exists(qwen):
        print("[run_ig_weekly] qwen-ask не найден — без AI-вывода")
        return ""
    try:
        r = subprocess.run(
            [qwen, "--role", "reason", AI_INSTRUCTION],
            input=summary, capture_output=True, text=True, timeout=200)
        if r.returncode == 3 or "QWEN_QUOTA_EXCEEDED" in r.stderr:
            print("[run_ig_weekly] Qwen упёрся в лимит — без AI-вывода")
            return ""
        out = r.stdout.strip()
        if out:
            print("[run_ig_weekly] AI-вывод получен от Qwen")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[run_ig_weekly] Qwen ошибка: {e}")
        return ""


def main():
    print("[run_ig_weekly] Старт недельного дайджеста Instagram…")
    try:
        data = fetch_and_save()
        report = build_digest(data)

        ai_text = qwen_commentary(build_ai_summary(data))
        if ai_text:
            report += "\n\n━━━ 🤖 ВЫВОД НЕДЕЛИ (AI) ━━━\n" + ai_text

        date_str = datetime.now().strftime("%Y-%m-%d")
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir, f"ig_weekly_{date_str}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(report)

        send_message(report)
        print(f"[run_ig_weekly] Готово → reports/ig_weekly_{date_str}.txt")
    except Exception:
        err = traceback.format_exc()
        print(f"[run_ig_weekly] ОШИБКА:\n{err}")
        try:
            send_message(f"❌ Instagram недельный дайджест — ошибка\n\n{err[-1000:]}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
