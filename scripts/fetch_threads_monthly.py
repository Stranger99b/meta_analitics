"""Сбор данных для МЕСЯЧНОГО отчёта Threads (@gotrips_by).

MoM-сравнение (целевой месяц vs предыдущий): account totals, прирост подписчиков,
все посты месяца с per-post инсайтами, ритм постинга. Переиспользует примитивы
из fetch_threads_weekly. По умолчанию берёт ПРЕДЫДУЩИЙ календарный месяц (для
запуска 1-го числа); можно передать целевой месяц как 'YYYY-MM'.
→ data/latest_threads_monthly.json + data/archive/threads_monthly_YYYY-MM.json
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import fetch_threads_weekly as ftw  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
RU_MONTHS = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль",
             "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def _month_bounds(year, month):
    start = dt.date(year, month, 1)
    end = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return start, end


def _posts_in_range(start, end):
    d = ftw._get(f"{ftw.USER_ID}/threads", {
        "fields": "id,media_type,text,permalink,timestamp",
        "since": ftw._ts(start), "until": ftw._ts(end), "limit": 100})
    items = []
    for m in d.get("data", []):
        ts = m.get("timestamp", "")[:10]
        try:
            pd = dt.datetime.strptime(ts, "%Y-%m-%d").date()
        except ValueError:
            continue
        if start <= pd < end:
            m["insights"] = ftw._media_insights(m["id"])
            items.append(m)
    return items


def fetch_and_save(target=None):
    if not ftw.TOKEN:
        raise RuntimeError("Нет THREADS_ACCESS_TOKEN в .env")
    today = dt.date.today()
    if target:
        y, m = map(int, target.split("-"))
    else:
        prev = today.replace(day=1) - dt.timedelta(days=1)
        y, m = prev.year, prev.month

    m_start, m_end = _month_bounds(y, m)
    pv = m_start - dt.timedelta(days=1)
    p_start, p_end = _month_bounds(pv.year, pv.month)

    fw_first, fw_last = ftw._followers_series(m_start, m_end)
    fp_first, fp_last = ftw._followers_series(p_start, p_end)
    posts = _posts_in_range(m_start, m_end)

    data = {
        "generated": dt.datetime.now().isoformat(),
        "month": {"year": y, "month": m, "name": RU_MONTHS[m],
                  "since": str(m_start), "until": str(m_end)},
        "prev_month": {"name": RU_MONTHS[p_start.month],
                       "since": str(p_start), "until": str(p_end)},
        "profile": ftw._get(ftw.USER_ID, {"fields": "id,username"}),
        "followers_count": fw_last,
        "follower_growth_month": (fw_last - fw_first) if (fw_last and fw_first) else None,
        "follower_growth_prev": (fp_last - fp_first) if (fp_last and fp_first) else None,
        "totals_month": ftw._account_totals(m_start, m_end),
        "totals_prev": ftw._account_totals(p_start, p_end),
        "posts": posts,
        "posts_count": len(posts),
    }

    os.makedirs(os.path.join(DATA_DIR, "archive"), exist_ok=True)
    with open(os.path.join(DATA_DIR, "latest_threads_monthly.json"), "w",
              encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tag = f"{y}-{m:02d}"
    with open(os.path.join(DATA_DIR, "archive", f"threads_monthly_{tag}.json"), "w",
              encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_threads_monthly] {RU_MONTHS[m]} {y}: постов {len(posts)}")
    return data


if __name__ == "__main__":
    fetch_and_save(sys.argv[1] if len(sys.argv) > 1 else None)
