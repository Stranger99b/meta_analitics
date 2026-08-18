"""Недельный дайджест Threads → Telegram. Cron: понедельник утром.

Сбор (fetch_threads_weekly) → текст (analyze_threads_weekly) → краткий AI-вывод
через Qwen (--role reason, фолбэк при лимите) → Telegram + архив reports/.
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

from fetch_threads_weekly import fetch_and_save
from analyze_threads_weekly import build_digest, build_ai_summary
from send_telegram import send_message

AI_INSTRUCTION = (
    "Ты — SMM-аналитик туристической компании в Threads (@gotrips_by). На входе — "
    "недельные метрики Threads и топ постов. Дай КРАТКИЙ вывод на русском (3-5 "
    "предложений, без markdown-заголовков): динамика просмотров/вовлечённости к "
    "прошлой неделе, какие темы/форматы зашли, 1-2 конкретных совета. Без воды."
)


def qwen_commentary(summary: str) -> str:
    qwen = shutil.which("qwen-ask") or "/home/user/.local/bin/qwen-ask"
    if not os.path.exists(qwen):
        print("[run_threads_weekly] qwen-ask не найден — без AI-вывода")
        return ""
    try:
        r = subprocess.run(
            [qwen, "--role", "long", AI_INSTRUCTION],
            input=summary, capture_output=True, text=True, timeout=200)
        if r.returncode == 3 or "QWEN_QUOTA_EXCEEDED" in r.stderr:
            print("[run_threads_weekly] Qwen упёрся в лимит — без AI-вывода")
            return ""
        out = r.stdout.strip()
        if out:
            print("[run_threads_weekly] AI-вывод получен от Qwen")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[run_threads_weekly] Qwen ошибка: {e}")
        return ""


def main():
    print("[run_threads_weekly] Старт недельного дайджеста Threads…")
    try:
        data = fetch_and_save()
        report = build_digest(data)

        import report_format as rf
        ai_text = qwen_commentary(build_ai_summary(data))
        if ai_text:
            report += "\n\n" + rf.b("🤖 Вывод недели (AI)") + "\n" + ai_text

        date_str = datetime.now().strftime("%Y-%m-%d")
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir, f"threads_weekly_{date_str}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(rf.plain(report))

        # Threads-дайджест идёт в группу Go_контент, тему «Отчет» (не в личный чат)
        chat_id = os.environ.get("THREADS_TG_CHAT_ID")
        thread_id = os.environ.get("THREADS_TG_THREAD_ID")
        send_kwargs = {}
        if chat_id:
            send_kwargs["chat_id"] = chat_id
        if thread_id:
            send_kwargs["message_thread_id"] = thread_id
        send_message(rf.to_html(report), parse_mode="HTML", **send_kwargs)
        print(f"[run_threads_weekly] Готово → reports/threads_weekly_{date_str}.txt")
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
