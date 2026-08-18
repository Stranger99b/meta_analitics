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
    "Ты — руководитель маркетинга, оцениваешь SMM в Instagram (@gotrips_by) за неделю. "
    "На входе — УЖЕ РАССЧИТАННЫЙ балл SMM по рубрике с разбором по критериям + недельные "
    "метрики и топ контента. Ответ на русском, БЕЗ markdown-заголовков, 4-6 предложений: "
    "1) поясни оценку — за счёт каких критериев балл такой (что вытянуло, что просело); "
    "2) какой формат/тема зашли лучше; 3) 1-2 конкретных совета на следующую неделю. "
    "НЕ меняй балл — только объясняй. Без воды."
)


def qwen_commentary(summary: str) -> str:
    """Краткий вывод недели через Qwen. Пустая строка, если недоступен/лимит."""
    qwen = shutil.which("qwen-ask") or "/home/user/.local/bin/qwen-ask"
    if not os.path.exists(qwen):
        print("[run_ig_weekly] qwen-ask не найден — без AI-вывода")
        return ""
    try:
        r = subprocess.run(
            [qwen, "--role", "long", AI_INSTRUCTION],
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
        import datetime as _dt
        import report_pdf as rpdf
        import stories_sheet
        import smm_score
        from send_telegram import send_bytes

        data = fetch_and_save()
        score = smm_score.compute_ig(data)
        pf = smm_score.plan_vs_fact(data)
        ai_text = qwen_commentary(smm_score.as_text(score, pf) + "\n\n" + build_ai_summary(data))

        # вся статистика сторис → Google-таблица (ссылка попадёт в PDF)
        sheet_url = stories_sheet.upload()

        pdf = rpdf.ig_weekly_pdf(data, ai_text, sheet_url=sheet_url, score=score, planfact=pf)
        b = _dt.date.fromisoformat(data["week"]["until"])
        y, w, _ = b.isocalendar()
        fname = f"№{w}_{y}_IG_недельный_дайджест.pdf"
        cap = f"📄 Instagram · недельный дайджест №{w} · {y}"

        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir, f"ig_weekly_{y}-W{w:02d}.pdf"), "wb") as f:
            f.write(pdf)

        # прод: только в тему Go_контент/«Отчет»
        chat_id = os.environ.get("IG_TG_CHAT_ID")
        thread_id = os.environ.get("IG_TG_THREAD_ID")
        if chat_id:
            send_bytes(pdf, fname, chat_id=chat_id, message_thread_id=thread_id, caption=cap)
        print(f"[run_ig_weekly] Готово → {fname}")
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
