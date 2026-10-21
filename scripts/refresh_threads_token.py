#!/usr/bin/env python3
"""Продлевает долгоживущий Threads-токен (th_refresh_token) → +60 дней.

Threads-токен живёт ~60 дней и обновляется, только ПОКА ОН ЖИВОЙ (и старше 24 ч).
Если дать ему протухнуть — refresh уже невозможен, нужна ручная переавторизация
(тестировщик + «Сгенерировать маркер доступа» в дашборде). Поэтому этот скрипт
гоняем по крону раз в неделю — токен фактически вечный.

При неудаче шлёт понятный алерт в Telegram (а не молчит/роняет дайджест).
"""
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(__file__))
import exchange_threads_token as X  # _get_env/_set_env и ENV_PATH

BASE = "https://graph.threads.net"


def _alert(text):
    try:
        from send_telegram import send_message
        send_message(text)
    except Exception as e:  # noqa: BLE001
        print(f"[threads-refresh] не смог отправить алерт: {e}")


def main():
    tok = X._get_env("THREADS_ACCESS_TOKEN")
    if not tok:
        print("[threads-refresh] нет THREADS_ACCESS_TOKEN в .env")
        sys.exit(1)
    try:
        r = requests.get(f"{BASE}/refresh_access_token",
                         params={"grant_type": "th_refresh_token", "access_token": tok},
                         timeout=30)
        d = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[threads-refresh] сеть недоступна: {e}")
        sys.exit(1)

    if "access_token" in d:
        X._set_env("THREADS_ACCESS_TOKEN", d["access_token"])
        days = (d.get("expires_in") or 0) // 86400
        print(f"[threads-refresh] ✅ токен продлён, живёт ещё ~{days} дн.")
        return

    msg = d.get("error", {}).get("message", str(d))[:200]
    print(f"[threads-refresh] ❌ рефреш не удался: {msg}")
    _alert("⚠️ Threads: не удалось продлить токен — "
           f"{msg}\n\nНужна переавторизация: дашборд Meta → Threads API → "
           "«Сгенерировать маркер доступа», затем сохранить новый токен.")
    sys.exit(1)


if __name__ == "__main__":
    main()
