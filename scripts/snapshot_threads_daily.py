#!/usr/bin/env python3
"""Ежедневный снимок числа подписчиков Threads → data/threads_followers_history.json.

Threads API отдаёт followers_count только как ТЕКУЩЕЕ значение (не дневной ряд),
поэтому прирост за период считаем по своей накопленной истории абсолютных снимков
(как в TikTok/IG). Ставится на дневной cron. Идемпотентен: перезапись за сегодня.
"""
import os
import json
import datetime

import fetch_threads_weekly as ftw
from secrets_scrub import scrub

HISTORY = ftw.FOLL_HISTORY


def main():
    n = ftw.current_followers()
    if not n:
        print("[snapshot_threads_daily] followers_count не получен — пропуск")
        return
    hist = {}
    if os.path.exists(HISTORY):
        try:
            with open(HISTORY, encoding="utf-8") as f:
                hist = json.load(f)
        except Exception:  # noqa: BLE001
            hist = {}
    today = datetime.date.today().isoformat()
    hist[today] = n
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(scrub(dict(sorted(hist.items()))), f, ensure_ascii=False, indent=2)
    print(f"[snapshot_threads_daily] {today}: подписчиков {n} (записей всего {len(hist)})")


if __name__ == "__main__":
    main()
