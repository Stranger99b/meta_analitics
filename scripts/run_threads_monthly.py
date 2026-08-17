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
    "3) ОЦЕНКА SMM-СПЕЦИАЛИСТА — балл от 1 до 10 с обоснованием: учитывай регулярность "
    "постинга, рост показателей, наличие залетевших постов, работу с вовлечённостью. Будь "
    "честным, но конструктивным.\n"
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
        data = fetch_and_save(target)
        report = build_digest(data)

        ai_text = qwen_review(build_ai_summary(data))
        if ai_text:
            report += "\n\n━━━ 🤖 ОЦЕНКА И РЕКОМЕНДАЦИИ (AI) ━━━\n" + ai_text

        tag = f"{data['month']['year']}-{data['month']['month']:02d}"
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir, f"threads_monthly_{tag}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(report)

        chat_id = os.environ.get("THREADS_TG_CHAT_ID")
        thread_id = os.environ.get("THREADS_TG_THREAD_ID")
        send_kwargs = {}
        if chat_id:
            send_kwargs["chat_id"] = chat_id
        if thread_id:
            send_kwargs["message_thread_id"] = thread_id
        send_message(report, **send_kwargs)
        print(f"[run_threads_monthly] Готово → reports/threads_monthly_{tag}.txt")
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
