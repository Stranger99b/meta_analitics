"""МЕСЯЧНЫЙ отчёт Instagram → Telegram (группа Go_контент, тема «Отчет»).

Cron: 1-е число месяца (за предыдущий месяц). Аргумент 'YYYY-MM' — перегенерация.
Сбор → текст (MoM, топ, сторис, сравнение типов) → AI-блок Qwen (оценка SMM +
рекомендации по контент-миксу) с ретраем/проверкой полноты → Telegram + reports/.
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
from analyze_ig_monthly import build_digest, build_ai_summary
from send_telegram import send_message

AI_INSTRUCTION = (
    "Ты — руководитель маркетинга, оцениваешь работу SMM-специалиста в Instagram "
    "туристической компании (@gotrips_by) за месяц. На входе — месячные метрики, топ "
    "публикаций, аналитика сторис и сравнение типов контента (рилс/посты/сторис) с "
    "MoM-сравнением. Ответ строго на русском, БЕЗ markdown-заголовков, по структуре:\n"
    "1) ИТОГ МЕСЯЦА — 2-3 предложения: динамика охвата/просмотров/подписчиков к прошлому "
    "месяцу.\n"
    "2) ЧТО СРАБОТАЛО / ЧТО НЕТ — какие темы и ФОРМАТЫ (рилс/посты/сторис) зашли, что "
    "провалилось, с цифрами.\n"
    "3) КОНТЕНТ-МИКС — на основе сравнения типов: какого контента и сколько нужно "
    "публиковать (рилс vs посты vs сторис), в какие дни/как часто, чтобы расти эффективнее. "
    "Опирайся на ср.просмотры и вклад сторис в визиты профиля/подписки.\n"
    "4) ОЦЕНКА SMM-СПЕЦИАЛИСТА — балл 1-10 с обоснованием (регулярность, рост, залёты, "
    "работа с вовлечённостью и сторис).\n"
    "5) РЕКОМЕНДАЦИИ НА СЛЕДУЮЩИЙ МЕСЯЦ — 3-5 конкретных действий.\n"
    "Опирайся на реальные цифры, без общих фраз."
)


def _looks_complete(text: str) -> bool:
    if not text:
        return False
    has_recs = "РЕКОМЕНДАЦ" in text.upper() or "5)" in text
    ends_ok = text.rstrip()[-1:] in ".!?»)0123456789"
    return has_recs and ends_ok


def qwen_review(summary: str, attempts: int = 4) -> str:
    qwen = shutil.which("qwen-ask") or "/home/user/.local/bin/qwen-ask"
    if not os.path.exists(qwen):
        print("[run_ig_monthly] qwen-ask не найден — без AI-блока")
        return ""
    best = ""
    for i in range(1, attempts + 1):
        try:
            r = subprocess.run(
                [qwen, "--role", "long", "--max-tokens", "3500", AI_INSTRUCTION],
                input=summary, capture_output=True, text=True, timeout=240)
            if r.returncode == 3 or "QWEN_QUOTA_EXCEEDED" in r.stderr:
                print("[run_ig_monthly] Qwen упёрся в лимит — без AI-блока")
                return best
            out = r.stdout.strip()
            if len(out) > len(best):
                best = out
            if _looks_complete(out):
                print(f"[run_ig_monthly] AI-оценка получена от Qwen (попытка {i})")
                return out
            print(f"[run_ig_monthly] Ответ Qwen оборван/пуст (попытка {i}/{attempts}), ретрай…")
        except Exception as e:  # noqa: BLE001
            print(f"[run_ig_monthly] Qwen ошибка (попытка {i}): {e}")
        if i < attempts:
            time.sleep(4)
    if best:
        print("[run_ig_monthly] Полного ответа не вышло — беру самый длинный")
    return best


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"[run_ig_monthly] Старт месячного отчёта IG (месяц={target or 'предыдущий'})…")
    try:
        data = fetch_and_save(target)
        import report_format as rf
        report = build_digest(data)

        ai_text = qwen_review(build_ai_summary(data))
        if ai_text:
            report += "\n\n" + rf.b("🤖 Оценка и рекомендации (AI)") + "\n" + ai_text

        tag = f"{data['month']['year']}-{data['month']['month']:02d}"
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir, f"ig_monthly_{tag}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(rf.plain(report))

        chat_id = os.environ.get("IG_TG_CHAT_ID")
        thread_id = os.environ.get("IG_TG_THREAD_ID")
        send_kwargs = {}
        if chat_id:
            send_kwargs["chat_id"] = chat_id
        if thread_id:
            send_kwargs["message_thread_id"] = thread_id
        send_message(rf.to_html(report), parse_mode="HTML", **send_kwargs)

        import ig_content_compare as icc
        from send_telegram import send_document
        stories = data.get("stories", [])
        if stories:
            csv = icc.stories_csv(stories)
            send_document(csv, f"stories_{tag}.csv",
                          caption="📎 Все сторис месяца (для сортировки/разбора)",
                          **send_kwargs)
        print(f"[run_ig_monthly] Готово → reports/ig_monthly_{tag}.txt")
    except Exception:
        err = traceback.format_exc()
        print(f"[run_ig_monthly] ОШИБКА:\n{err}")
        try:
            send_message(f"❌ Instagram месячный отчёт — ошибка\n\n{err[-1000:]}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
