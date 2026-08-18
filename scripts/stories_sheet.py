"""Заливка ВСЕЙ статистики сторис в Google Sheets (для анализа в будущем).

Таблица «Stories_Gotrips_by_Статистика» (расшарена сервисному аккаунту
gotrips-analytics@…). Перезаписывает лист полной историей из store.json.
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import ig_content_compare as icc  # noqa: E402

SHEET_ID = "1JlI2oP3ylDTryAoI0_4ujRdvY2JmOnSS4iCfrZZyDQw"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
CREDS_DEFAULT = "/home/user/Analytics_salebot/data/gsheets_credentials.json"

HEADERS = ["Дата", "№", "Время", "Тип", "Просмотры", "Охват", "Удержание_%",
           "ВизитыПрофиля", "Подписки", "Ответы", "Репосты",
           "Вперёд", "Назад", "Закрыли", "УшлиКДругим", "Подпись", "Ссылка", "ID"]


def _client():
    import gspread
    from google.oauth2.service_account import Credentials
    path = os.environ.get("GSHEETS_CREDENTIALS", "").strip() or CREDS_DEFAULT
    creds = Credentials.from_service_account_file(path, scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds)


def _all_rows():
    if not os.path.exists(icc.STORE):
        return []
    with open(icc.STORE, encoding="utf-8") as f:
        store = json.load(f)
    enr = icc.enrich_stories(list(store.values()))
    enr.sort(key=lambda s: (s.get("_local_dt") or dt.datetime.min.replace(
        tzinfo=icc.MINSK)))
    rows = []
    for s in enr:
        ins = s.get("insights", {})
        nav = s.get("nav", {})
        rows.append([
            s["local_date"], s["num"], s["local_time"],
            "видео" if s.get("media_type") == "VIDEO" else "фото",
            ins.get("views") or 0, ins.get("reach") or 0,
            s.get("retention_pct") if s.get("retention_pct") is not None else "",
            ins.get("profile_visits") or 0, ins.get("follows") or 0,
            ins.get("replies") or 0, ins.get("shares") or 0,
            nav.get("tap_forward") or 0, nav.get("tap_back") or 0,
            nav.get("tap_exit") or 0, nav.get("swipe_forward") or 0,
            (s.get("caption") or "").replace("\n", " ").strip(),
            s.get("permalink") or "", s.get("id") or "",
        ])
    return rows


def upload():
    """Заливает полную историю сторис в таблицу. Возвращает URL или '' при ошибке."""
    try:
        rows = _all_rows()
        gc = _client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.sheet1
        ws.clear()
        ws.update([HEADERS] + rows, value_input_option="RAW")
        # заголовок жирным
        try:
            ws.format("A1:R1", {"textFormat": {"bold": True}})
            ws.freeze(rows=1)
        except Exception:  # noqa: BLE001
            pass
        print(f"[stories_sheet] Залито строк: {len(rows)} → {SHEET_URL}")
        return SHEET_URL
    except Exception as e:  # noqa: BLE001
        print(f"[stories_sheet] Ошибка заливки: {type(e).__name__}: {str(e)[:150]}")
        return ""


if __name__ == "__main__":
    upload()
