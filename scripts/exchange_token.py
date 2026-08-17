#!/usr/bin/env python3
"""Меняет короткоживущий токен Meta на долгоживущий (~60 дней) через
fb_exchange_token и сохраняет его в .env. При желании запоминает APP_ID/APP_SECRET
в .env, чтобы следующее обновление можно было делать проще.

Использование:
  python3 exchange_token.py APP_ID APP_SECRET КОРОТКИЙ_ТОКЕН

APP_ID / APP_SECRET — из developers.facebook.com/apps → ваше приложение →
Настройки → Основное. КОРОТКИЙ_ТОКЕН — свежий токен из Graph API Explorer
(права ads_read), живёт ~1-2 часа, поэтому обменивать надо сразу.
"""
import sys
import os
import datetime
import requests

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def _set_env(key: str, value: str):
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.readlines()
    out, done = [], False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}\n"); done = True
        else:
            out.append(line)
    if not done:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key}={value}\n")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(out)


def exchange(app_id: str, app_secret: str, short_token: str):
    print("[exchange] Запрашиваю долгоживущий токен…")
    r = requests.get(
        "https://graph.facebook.com/v19.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=20,
    )
    data = r.json()
    if r.status_code != 200 or "access_token" not in data:
        print(f"[exchange] ❌ Ошибка обмена: {data}")
        sys.exit(1)

    long_token = data["access_token"]
    expires_in = data.get("expires_in")
    print(f"[exchange] ✅ Получен токен ({len(long_token)} символов)"
          + (f", живёт ~{expires_in // 86400} дн." if expires_in else ""))

    # Сохраняем токен и (для удобства будущих обновлений) app_id/app_secret
    _set_env("META_ACCESS_TOKEN", long_token)
    _set_env("META_APP_ID", app_id)
    _set_env("META_APP_SECRET", app_secret)
    print("[exchange] Токен и APP_ID/APP_SECRET записаны в .env")

    # Проверяем через debug_token
    r2 = requests.get(
        "https://graph.facebook.com/debug_token",
        params={"input_token": long_token,
                "access_token": f"{app_id}|{app_secret}"},
        timeout=20,
    )
    if r2.status_code == 200:
        d = r2.json().get("data", {})
        exp = d.get("expires_at", 0)
        valid = d.get("is_valid")
        if exp:
            exp_dt = datetime.datetime.fromtimestamp(exp)
            days = (exp_dt - datetime.datetime.now()).days
            print(f"[exchange] Валиден: {valid}. Истекает: "
                  f"{exp_dt.strftime('%Y-%m-%d')} (через {days} дней)")
        else:
            print(f"[exchange] Валиден: {valid}. Токен без даты истечения.")
    else:
        print(f"[exchange] (проверка debug_token не удалась: {r2.json()})")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Использование: python3 exchange_token.py APP_ID APP_SECRET КОРОТКИЙ_ТОКЕН")
        sys.exit(1)
    exchange(sys.argv[1].strip(), sys.argv[2].strip(), sys.argv[3].strip())
