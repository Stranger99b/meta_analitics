"""МЕСЯЧНЫЙ отчёт Threads → Telegram (группа Go_контент, тема «Отчет»).

Cron: 1-е число месяца (отчёт за предыдущий месяц). Можно передать месяц
аргументом 'YYYY-MM' для перегенерации за конкретный период.

Сбор → текст → AI-блок (рекомендации + ОЦЕНКА SMM-специалиста) через Qwen
(--role reason, фолбэк при лимите) → Telegram + архив reports/.
"""
import os
import sys
import time
import shutil
import subprocess
import traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(__file__))

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


def _looks_complete(text: str) -> bool:
    """Ответ считаем полным, если дошёл до секции рекомендаций и не оборван на слове."""
    if not text:
        return False
    has_recs = "РЕКОМЕНДАЦ" in text.upper() or "4)" in text
    # оборван на полуслове (нет финальной пунктуации в конце) — признак обрезки
    ends_ok = text.rstrip()[-1:] in ".!?»)0123456789"
    return has_recs and ends_ok


def qwen_review(summary: str, attempts: int = 4) -> str:
    """AI-оценка SMM через Qwen. Ретрай при пустом ИЛИ оборванном ответе.

    Возвращает лучший из полученных ответов (полный — приоритетно; если полного
    не вышло за все попытки — самый длинный, чтобы не терять оценку целиком).
    """
    qwen = shutil.which("qwen-ask") or "/home/user/.local/bin/qwen-ask"
    if not os.path.exists(qwen):
        print("[run_threads_monthly] qwen-ask не найден — без AI-блока")
        return ""
    best = ""
    for i in range(1, attempts + 1):
        try:
            r = subprocess.run(
                [qwen, "--role", "long", "--max-tokens", "3000", AI_INSTRUCTION],
                input=summary, capture_output=True, text=True, timeout=240)
            if r.returncode == 3 or "QWEN_QUOTA_EXCEEDED" in r.stderr:
                print("[run_threads_monthly] Qwen упёрся в лимит — без AI-блока")
                return best
            out = r.stdout.strip()
            if len(out) > len(best):
                best = out
            if _looks_complete(out):
                print(f"[run_threads_monthly] AI-оценка получена от Qwen (попытка {i})")
                return out
            print(f"[run_threads_monthly] Ответ Qwen оборван/пуст (попытка {i}/{attempts}), "
                  f"ретрай…")
        except Exception as e:  # noqa: BLE001
            print(f"[run_threads_monthly] Qwen ошибка (попытка {i}): {e}")
        if i < attempts:
            time.sleep(4)
    if best:
        print("[run_threads_monthly] Полного ответа не вышло — беру самый длинный")
    return best


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
