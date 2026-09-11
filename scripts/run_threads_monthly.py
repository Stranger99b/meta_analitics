"""МЕСЯЧНЫЙ отчёт Threads → Telegram (группа Go_контент, тема «Отчет»).

Cron: 1-е число месяца (отчёт за предыдущий месяц). Можно передать месяц
аргументом 'YYYY-MM' для перегенерации за конкретный период.

Сбор → текст → AI-блок (рекомендации + ОЦЕНКА SMM-специалиста) через Qwen
(--role reason, фолбэк при лимите) → Telegram + архив reports/.
"""
import os
import sys
import traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(__file__))

import ai_review
from fetch_threads_monthly import fetch_and_save
from analyze_threads_monthly import build_digest, build_ai_summary
from send_telegram import send_message

AI_INSTRUCTION = (
    "Ты — руководитель отдела маркетинга, оцениваешь работу SMM-специалиста в Threads "
    "туристической компании (@gotrips_by) за месяц. На входе — месячные метрики и топ "
    "постов (с MoM-сравнением). Ответ строго на русском, БЕЗ markdown-заголовков, по "
    "структуре:\n"
    "1) ИТОГ МЕСЯЦА — 2-3 предложения: динамика охвата/вовлечённости и подписчиков к "
    "прошлому месяцу.\n"
    "2) ЧТО СРАБОТАЛО / ЧТО НЕТ — какие темы и форматы зашли, что провалилось (с цифрами).\n"
    "3) ОЦЕНКА SMM — поясни УЖЕ РАССЧИТАННЫЙ балл (дан на входе): за счёт каких критериев "
    "он такой, что вытянуло, что просело. НЕ меняй сам балл, только объясни.\n"
    "4) РЕКОМЕНДАЦИИ НА СЛЕДУЮЩИЙ МЕСЯЦ — 3-4 конкретных действия.\n"
    "Опирайся на реальные цифры и примеры постов, без общих фраз."
)


def qwen_review(summary: str) -> str:
    """AI-оценка месяца Threads: Qwen (--role long), при недоступности — фолбэк на Claude."""
    return ai_review.generate(AI_INSTRUCTION, summary,
                              tag="run_threads_monthly", max_tokens=3000)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"[run_threads_monthly] Старт месячного отчёта Threads (месяц={target or 'предыдущий'})…")
    try:
        import report_pdf as rpdf
        import smm_score
        from send_telegram import send_bytes

        data = fetch_and_save(target)
        score = smm_score.compute_threads(data)
        pf = smm_score.plan_vs_fact(data)
        ai_text = qwen_review(smm_score.as_text(score, pf) + "\n\n" + build_ai_summary(data))

        pdf = rpdf.threads_monthly_pdf(data, ai_text, score=score, planfact=pf)
        mon = data["month"]
        tag = f"{mon['year']}-{mon['month']:02d}"
        fname = f"№{mon['month']:02d}_{mon['year']}_{mon['name'].capitalize()}_Threads_месячный.pdf"
        cap = f"📄 Threads · месячный отчёт №{mon['month']:02d} · {mon['name'].capitalize()} {mon['year']}"

        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir, f"threads_monthly_{tag}.pdf"), "wb") as f:
            f.write(pdf)

        chat_id = os.environ.get("THREADS_TG_CHAT_ID")
        thread_id = os.environ.get("THREADS_TG_THREAD_ID")
        if chat_id:
            send_bytes(pdf, fname, chat_id=chat_id, message_thread_id=thread_id, caption=cap)
        print(f"[run_threads_monthly] Готово → {fname}")
    except Exception:
        err = traceback.format_exc()
        print(f"[run_threads_monthly] ОШИБКА:\n{err}")
        try:
            send_message(f"❌ Threads месячный отчёт — ошибка\n\n{err[-1000:]}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
