"""Месячный ПЛАН/СТРАТЕГИЯ для SMM → Telegram (тема «Отчет»).

Cron: 1-го числа (за предыдущий месяц). Динамический слой (диагноз + предложения
по KPI) считается из данных; «Фокус на месяц» пишет Qwen; методичка (тренды, хуки,
воронка) — стабильная. Аргумент YYYY-MM для перегенерации.
"""
import os
import sys
import time
import shutil
import subprocess
import traceback
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(__file__))

from fetch_ig_monthly import fetch_and_save
from analyze_ig_monthly import build_ai_summary
import research_pdf
from send_telegram import send_bytes

AI_INSTRUCTION = (
    "Ты — стратег по SMM туристической компании (Instagram @gotrips_by, автобусные/"
    "групповые туры). На входе — метрики месяца, сравнение типов контента и топ публикаций. "
    "Дай ФОКУС НА СЛЕДУЮЩИЙ МЕСЯЦ: 3-5 конкретных приоритетных действий, что и в каком "
    "объёме усилить (по форматам и темам), опираясь на то, что реально зашло. На русском, "
    "без markdown-заголовков, по пункту на строку, без общих фраз."
)


def _focus(summary):
    qwen = shutil.which("qwen-ask") or "/home/user/.local/bin/qwen-ask"
    if not os.path.exists(qwen):
        return ""
    for i in range(3):
        try:
            r = subprocess.run([qwen, "--role", "long", "--max-tokens", "1200",
                                AI_INSTRUCTION], input=summary,
                               capture_output=True, text=True, timeout=200)
            if r.returncode == 3 or "QWEN_QUOTA_EXCEEDED" in r.stderr:
                return ""
            out = r.stdout.strip()
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
        time.sleep(4)
    return ""


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"[run_strategy_monthly] Старт (месяц={target or 'предыдущий'})…")
    try:
        data = fetch_and_save(target)
        focus = _focus(build_ai_summary(data))
        pdf = research_pdf.build(data=data, ai_focus=focus)

        mon = data["month"]
        fname = (f"№{mon['month']:02d}_{mon['year']}_{mon['name'].capitalize()}_"
                 f"ПЛАН_SMM.pdf")
        cap = (f"🚀 План/стратегия SMM на основе {mon['name']} {mon['year']} — "
               f"диагноз, предложения по KPI, фокус на след. месяц")

        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir,
                  f"strategy_{mon['year']}-{mon['month']:02d}.pdf"), "wb") as f:
            f.write(pdf)

        chat_id = os.environ.get("IG_TG_CHAT_ID")
        thread_id = os.environ.get("IG_TG_THREAD_ID")
        if chat_id:
            send_bytes(pdf, fname, chat_id=chat_id, message_thread_id=thread_id, caption=cap)
        print(f"[run_strategy_monthly] Готово → {fname}")
    except Exception:
        print(f"[run_strategy_monthly] ОШИБКА:\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
