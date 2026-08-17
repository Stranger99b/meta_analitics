#!/usr/bin/env python3
"""Меняет короткоживущий Threads-токен на долгоживущий (~60 дней) через
th_exchange_token и сохраняет его в .env как THREADS_ACCESS_TOKEN.

Threads API — ОТДЕЛЬНЫЙ от Facebook/Instagram (base graph.threads.net), токен
берётся через Threads use case (OAuth Authorization Window), Facebook-токен тут
НЕ работает. client_secret — тот же META_APP_SECRET (Threads use case в том же
приложении GoTrips Analytics).

Использование:
  python3 exchange_threads_token.py КОРОТКИЙ_THREADS_ТОКЕН [APP_SECRET]
"""
import os
import sys
import datetime
import requests

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
BASE = "https://graph.threads.net"


def _get_env(key):
    if not os.path.exists(ENV_PATH):
        return None
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return None


def _set_env(key, value):
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


def exchange(short_token, app_secret):
    print("[threads-exchange] Запрашиваю долгоживущий токен…")
    r = requests.get(f"{BASE}/access_token", params={
        "grant_type": "th_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token,
    }, timeout=20)
    data = r.json()
    if r.status_code != 200 or "access_token" not in data:
        print(f"[threads-exchange] ❌ Ошибка обмена: {data}")
        sys.exit(1)
    long_token = data["access_token"]
    exp = data.get("expires_in")
    print(f"[threads-exchange] ✅ Токен ({len(long_token)} символов)"
          + (f", живёт ~{exp // 86400} дн." if exp else ""))
    _set_env("THREADS_ACCESS_TOKEN", long_token)
    print("[threads-exchange] Записан в .env как THREADS_ACCESS_TOKEN")

    # Проверка: кто мы в Threads
    r2 = requests.get(f"{BASE}/v1.0/me",
                      params={"fields": "id,username", "access_token": long_token},
                      timeout=20)
    d = r2.json()
    if "error" not in d:
        print(f"[threads-exchange] Аккаунт: @{d.get('username')} (id {d.get('id')})")
        _set_env("THREADS_USER_ID", str(d.get("id")))
    else:
        print(f"[threads-exchange] (проверка /me не удалась: {d['error'].get('message')})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 exchange_threads_token.py КОРОТКИЙ_ТОКЕН [APP_SECRET]")
        sys.exit(1)
    secret = sys.argv[2].strip() if len(sys.argv) > 2 else _get_env("META_APP_SECRET")
    if not secret:
        print("Нет APP_SECRET (передай аргументом или заведи META_APP_SECRET в .env)")
        sys.exit(1)
    exchange(sys.argv[1].strip(), secret)
