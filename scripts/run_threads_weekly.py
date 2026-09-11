"""Недельный дайджест Threads → Telegram. Cron: понедельник утром.

Сбор (fetch_threads_weekly) → текст (analyze_threads_weekly) → краткий AI-вывод
через Qwen (--role reason, фолбэк при лимите) → Telegram + архив reports/.
"""
import os
import sys
import traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(__file__))

import ai_review
from fetch_threads_weekly import fetch_and_save
from analyze_threads_weekly import build_digest, build_ai_summary
from send_telegram import send_message

AI_INSTRUCTION = (
    "Ты — руководитель маркетинга, оцениваешь SMM в Threads (@gotrips_by) за неделю. "
    "На входе — УЖЕ РАССЧИТАННЫЙ балл SMM по рубрике с разбором + недельные метрики и "
    "топ постов. Ответ на русском, БЕЗ markdown-заголовков, 4-6 предложений: 1) поясни "
    "оценку (что вытянуло, что просело); 2) какие темы/форматы зашли; 3) 1-2 совета. "
    "НЕ меняй балл — только объясняй. Без воды."
)


def qwen_commentary(summary: str) -> str:
    """Вывод недели Threads: Qwen (--role long), при недоступности — фолбэк на Claude."""
    return ai_review.generate(AI_INSTRUCTION, summary,
                              tag="run_threads_weekly", max_tokens=1500)


def main():
    print("[run_threads_weekly] Старт недельного дайджеста Threads…")
    try:
        import datetime as _dt
        import report_pdf as rpdf
        import smm_score
        from send_telegram import send_bytes

        data = fetch_and_save()
        score = smm_score.compute_threads(data)
        pf = smm_score.plan_vs_fact(data)
        ai_text = qwen_commentary(smm_score.as_text(score, pf) + "\n\n" + build_ai_summary(data))

        pdf = rpdf.threads_weekly_pdf(data, ai_text, score=score, planfact=pf)
        b = _dt.date.fromisoformat(data["week"]["until"])
        y, w, _ = b.isocalendar()
        fname = f"№{w}_{y}_Threads_недельный_дайджест.pdf"
        cap = f"📄 Threads · недельный дайджест №{w} · {y}"

        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir, f"threads_weekly_{y}-W{w:02d}.pdf"), "wb") as f:
            f.write(pdf)

        chat_id = os.environ.get("THREADS_TG_CHAT_ID")
        thread_id = os.environ.get("THREADS_TG_THREAD_ID")
        if chat_id:
            send_bytes(pdf, fname, chat_id=chat_id, message_thread_id=thread_id, caption=cap)
        print(f"[run_threads_weekly] Готово → {fname}")
    except Exception:
        err = traceback.format_exc()
        print(f"[run_threads_weekly] ОШИБКА:\n{err}")
        try:
            send_message(f"❌ Threads недельный дайджест — ошибка\n\n{err[-1000:]}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
