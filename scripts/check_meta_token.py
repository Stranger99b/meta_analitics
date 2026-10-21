#!/usr/bin/env python3
"""Сторож срока Meta-токена: предупреждает в Telegram ЗАРАНЕЕ, пока токен ещё живой.

Meta USER-токен живёт ~60 дней, и `fb_exchange_token` его НЕ продлевает (новый токен
с той же датой истечения). Поэтому авто-рефреш невозможен — нужен ручной перевыпуск
до истечения (или бессрочный System User токен). Этот сторож не даёт токену протухнуть
молча: за ALERT_DAYS до конца шлёт напоминание, при протухшем/битом — тревогу.

Cron: раз в неделю. При ≤ ALERT_DAYS днях (или ошибке) — сообщение в Telegram.
"""
import os
import sys
import datetime
import requests
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(ENV_PATH)
ALERT_DAYS = 14


def _alert(text):
    try:
        from send_telegram import send_message
        send_message(text)
    except Exception as e:  # noqa: BLE001
        print(f"[check_meta_token] не смог отправить алерт: {e}")


def main():
    tok = os.environ.get("META_ACCESS_TOKEN", "")
    appid = os.environ.get("META_APP_ID", "")
    sec = os.environ.get("META_APP_SECRET", "")
    if not (tok and appid and sec):
        print("[check_meta_token] нет META_ACCESS_TOKEN/APP_ID/APP_SECRET")
        sys.exit(1)
    try:
        d = requests.get("https://graph.facebook.com/debug_token",
                         params={"input_token": tok, "access_token": f"{appid}|{sec}"},
                         timeout=30).json().get("data", {})
    except Exception as e:  # noqa: BLE001
        print(f"[check_meta_token] сеть недоступна: {e}")
        sys.exit(1)

    if not d.get("is_valid"):
        msg = d.get("error", {}).get("message", "токен невалиден")
        print(f"[check_meta_token] ❌ токен невалиден: {msg}")
        _alert(f"🔴 Meta/Instagram-токен НЕВАЛИДЕН: {msg}\n\nПеревыпусти токен и запусти "
               "update_token.py — иначе отчёты IG/Meta Ads падают.")
        sys.exit(1)

    exp = d.get("expires_at")
    if not exp:  # 0 = бессрочный (System User)
        print("[check_meta_token] ✅ токен бессрочный (System User) — ок")
        return
    exp_dt = datetime.datetime.fromtimestamp(exp)
    days = (exp_dt - datetime.datetime.now()).days
    print(f"[check_meta_token] токен истекает {exp_dt:%Y-%m-%d} (через {days} дн.)")
    if days <= ALERT_DAYS:
        _alert(f"🟡 Meta/Instagram-токен истекает через {days} дн. "
               f"({exp_dt:%d.%m.%Y}). Перевыпусти его в developers.facebook.com → "
               "GoTrips Analytics (Graph API Explorer, права IG+Ads), обмени на "
               "долгоживущий и запусти update_token.py. Либо сделай бессрочный "
               "System User токен в Business Manager.")


if __name__ == "__main__":
    main()
