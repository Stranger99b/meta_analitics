"""On-demand анализ сторис по обращению к боту в чате/теме.

Триггер: сообщение с упоминанием @tor39_bot и словом «сторис». Бот отвечает
«Обрабатываю», затем присылает текстовый разбор вчерашних сторис из накопленной
базы (они уже дозрели по охвату). Запускать по cron каждую минуту.

Использует getUpdates с сохранением offset (data/tg_stories_offset.txt) + файловый
лок, чтобы параллельные запуски не задваивали ответы. Privacy mode бота не мешает —
упоминания доставляются.
"""
import os
import re
import sys
import fcntl
import datetime as dt
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(__file__))

import ig_content_compare as icc  # noqa: E402
import report_format as rf  # noqa: E402
from send_telegram import send_message  # noqa: E402

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{BOT}"
BOT_USERNAME = "tor39_bot"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OFFSET_FILE = os.path.join(DATA_DIR, "tg_stories_offset.txt")
LOCK_FILE = "/tmp/stories_ondemand.lock"


def _read_offset():
    try:
        with open(OFFSET_FILE) as f:
            return int(f.read().strip())
    except Exception:  # noqa: BLE001
        return None


def _save_offset(v):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OFFSET_FILE, "w") as f:
        f.write(str(v))


def _report(day):
    """Текстовый разбор сторис за конкретную дату (из базы)."""
    stories = icc.stories_in_range(day, day + dt.timedelta(days=1))
    head = rf.b(f"📸 Анализ сторис за {day.strftime('%d.%m.%Y')}")
    if not stories:
        return head + "\n\nЗа этот день сторис в базе нет (сбор идёт 3×/день; " \
               "возможно, ещё не попали или день слишком старый)."
    return head + "\n\n" + icc.render_stories(stories, "", full=True)


MAX_AGE = 600  # не отвечать на сообщения старше 10 минут (защита от бэклога)
STORY_KW = ("сторис", "стори", "истори", "stories", "story")   # варианты слова
INTENT_KW = ("анализ", "разбер", "разбор", "отчет", "отчёт", "статист", "провер")

HINT = ("Чтобы разобрать сторис — напишите мне со словом «сторис», например:\n"
        "«@tor39_bot проанализируй сторис» — за вчера (по умолчанию),\n"
        "«@tor39_bot сторис за сегодня» — за сегодня,\n"
        "«@tor39_bot сторис 18.08» или «сторис за 18.08.2026» — за конкретный день.")

_DATE_RE = re.compile(r'(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?')


def _parse_day(text):
    """Дата из текста команды: сегодня / вчера / DD.MM[.YYYY]. По умолчанию — вчера."""
    if "сегодня" in text:
        return dt.date.today()
    m = _DATE_RE.search(text)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        today = dt.date.today()
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100:
            y += 2000
        try:
            day = dt.date(y, mo, d)
        except ValueError:
            return today - dt.timedelta(days=1)
        # без явного года и дата в будущем → значит прошлый год
        if not m.group(3) and day > today:
            try:
                day = day.replace(year=y - 1)
            except ValueError:
                pass
        return day
    return dt.date.today() - dt.timedelta(days=1)


def _addressed(m):
    text = (m.get("text") or "").lower()
    if "@" + BOT_USERNAME in text:
        return True
    r = m.get("reply_to_message") or {}
    return (r.get("from") or {}).get("username", "").lower() == BOT_USERNAME


def _handle(m):
    import time
    if not _addressed(m):
        return
    if m.get("date") and time.time() - m["date"] > MAX_AGE:
        return
    text = (m.get("text") or "").lower()
    chat = m["chat"]["id"]
    kw = {"chat_id": str(chat)}
    if m.get("message_thread_id"):
        kw["message_thread_id"] = m["message_thread_id"]

    if any(k in text for k in STORY_KW):
        send_message("⏳ Обрабатываю…", **kw)
        day = _parse_day(text)
        send_message(rf.to_html(_report(day)), parse_mode="HTML", **kw)
        print(f"[stories_ondemand] ответил в chat {chat} за {day}")
    elif any(k in text for k in INTENT_KW):
        send_message(HINT, **kw)  # обратился, но не про сторис — подсказка
        print(f"[stories_ondemand] отправил подсказку в chat {chat}")


def _stash_media(m):
    """Сохраняет присланные фото/документы в data/incoming (чтобы не потерять их
    из-за того, что поллер «съедает» апдейты — напр. скрины для Claude)."""
    f = None
    if m.get("photo"):
        f = sorted(m["photo"], key=lambda x: x.get("file_size", 0))[-1]
    elif m.get("document"):
        f = m["document"]
    if not f:
        return
    try:
        fi = requests.get(f"{API}/getFile",
                          params={"file_id": f["file_id"]}, timeout=20).json()
        path = fi["result"]["file_path"]
        raw = requests.get(f"https://api.telegram.org/file/bot{BOT}/{path}",
                           timeout=30).content
        os.makedirs(os.path.join(DATA_DIR, "incoming"), exist_ok=True)
        name = f"{m.get('date','')}_{os.path.basename(path)}"
        with open(os.path.join(DATA_DIR, "incoming", name), "wb") as out:
            out.write(raw)
        print(f"[stories_ondemand] сохранил вложение → data/incoming/{name}")
    except Exception as e:  # noqa: BLE001
        print(f"[stories_ondemand] вложение не сохранено: {e}")


def main():
    if not BOT:
        print("[stories_ondemand] нет TELEGRAM_BOT_TOKEN")
        return
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:  # noqa: BLE001
        return  # уже выполняется

    offset = _read_offset()
    params = {"timeout": 3, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset
    try:
        d = requests.get(f"{API}/getUpdates", params=params, timeout=15).json()
    except Exception as e:  # noqa: BLE001
        print(f"[stories_ondemand] getUpdates err: {e}")
        return
    if not d.get("ok"):
        print(f"[stories_ondemand] getUpdates not ok: {d}")
        return
    ups = d.get("result", [])
    if not ups:
        return
    # бэклог отсекается по свежести сообщения (MAX_AGE в _handle), offset — против дублей
    last = offset if offset is not None else 0
    for u in ups:
        last = u["update_id"] + 1
        m = u.get("message") or {}
        try:
            _stash_media(m)
            _handle(m)
        except Exception as e:  # noqa: BLE001
            print(f"[stories_ondemand] обработка упала: {e}")
    _save_offset(last)


if __name__ == "__main__":
    main()
