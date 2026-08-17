"""Сбор данных для МЕСЯЧНОГО отчёта Instagram (@gotrips_by).

MoM-сравнение (целевой месяц vs предыдущий): account totals, прирост подписчиков,
контент месяца (рилс+посты с per-media инсайтами), сторис месяца (из базы),
сравнение типов. По умолчанию — предыдущий календарный месяц; можно 'YYYY-MM'.
→ data/latest_ig_monthly.json + data/archive/ig_monthly_YYYY-MM.json
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import fetch_ig_weekly as fiw  # noqa: E402
import ig_content_compare as icc  # noqa: E402

DATA_DIR = fiw.DATA_DIR
RU_MONTHS = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль",
             "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def _month_bounds(year, month):
    start = dt.date(year, month, 1)
    end = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return start, end


def _chunks(start, end, max_days=30):
    """Разбивает [start, end) на окна ≤ max_days (лимит IG insights)."""
    cur = start
    while cur < end:
        nxt = min(cur + dt.timedelta(days=max_days), end)
        yield cur, nxt
        cur = nxt


def _totals_ranged(start, end):
    """Account totals за произвольный период (сумма по 30-дневным окнам).

    Аддитивные метрики (views/likes/…) суммируются точно; reach (уникальные)
    складывается по окнам — небольшое завышение, но метод одинаков для обоих
    месяцев, поэтому MoM-сравнение остаётся корректным.
    """
    agg = {}
    for a, b in _chunks(start, end):
        t = fiw._totals(a, b)
        for k, v in t.items():
            agg[k] = (agg.get(k) or 0) + (v or 0)
    return agg


def _follower_growth_ranged(start, end):
    total = 0
    got = False
    for a, b in _chunks(start, end):
        g = fiw._follower_growth(a, b)
        if g is not None:
            total += g
            got = True
    return total if got else None


def _content_in_range(start, end):
    d = fiw._get(f"{fiw.IG_ID}/media", {
        "fields": "id,media_type,media_product_type,caption,permalink,timestamp,"
                  "like_count,comments_count",
        "since": fiw._ts(start), "until": fiw._ts(end), "limit": 100})
    items = []
    for m in d.get("data", []):
        ts = (m.get("timestamp") or "")[:10]
        try:
            pd = dt.date.fromisoformat(ts)
        except ValueError:
            continue
        if start <= pd < end:
            m["insights"] = fiw._media_insights(m["id"])
            items.append(m)
    return items


def fetch_and_save(target=None):
    today = dt.date.today()
    if target:
        y, m = map(int, target.split("-"))
    else:
        prev = today.replace(day=1) - dt.timedelta(days=1)
        y, m = prev.year, prev.month

    m_start, m_end = _month_bounds(y, m)
    pv = m_start - dt.timedelta(days=1)
    p_start, p_end = _month_bounds(pv.year, pv.month)

    content = _content_in_range(m_start, m_end)
    stories = icc.stories_in_range(m_start, m_end)
    earliest = icc.stories_since_earliest()

    data = {
        "generated": dt.datetime.now().isoformat(),
        "month": {"year": y, "month": m, "name": RU_MONTHS[m],
                  "since": str(m_start), "until": str(m_end)},
        "prev_month": {"name": RU_MONTHS[p_start.month],
                       "since": str(p_start), "until": str(p_end)},
        "profile": fiw._get(fiw.IG_ID, {"fields": "username,followers_count,media_count"}),
        "totals_month": _totals_ranged(m_start, m_end),
        "totals_prev": _totals_ranged(p_start, p_end),
        "follower_growth_month": _follower_growth_ranged(m_start, m_end),
        "follower_growth_prev": _follower_growth_ranged(p_start, p_end),
        "content": content,
        "posts_count": len(content),
        "stories": stories,
        "stories_earliest": str(earliest) if earliest else None,
    }

    os.makedirs(os.path.join(DATA_DIR, "archive"), exist_ok=True)
    with open(os.path.join(DATA_DIR, "latest_ig_monthly.json"), "w",
              encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tag = f"{y}-{m:02d}"
    with open(os.path.join(DATA_DIR, "archive", f"ig_monthly_{tag}.json"), "w",
              encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_ig_monthly] {RU_MONTHS[m]} {y}: контент {len(content)}, "
          f"сторис {len(stories)}")
    return data


if __name__ == "__main__":
    fetch_and_save(sys.argv[1] if len(sys.argv) > 1 else None)
