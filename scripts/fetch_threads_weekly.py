"""Сбор данных для недельного дайджеста Threads (@gotrips_by).

Threads API — отдельный от Instagram (base graph.threads.net, свой токен
THREADS_ACCESS_TOKEN). Тянет аккаунт-инсайты за текущую и прошлую неделю (WoW),
прирост подписчиков и посты недели с per-post инсайтами.
→ data/latest_threads_weekly.json + data/archive/threads_weekly_YYYY-MM-DD.json
"""
import os
import json
import datetime
import requests
from dotenv import load_dotenv
from secrets_scrub import scrub

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = "https://graph.threads.net/v1.0"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID = os.environ.get("THREADS_USER_ID", "").strip() or "me"

# Метрики уровня аккаунта (threads_insights) с суммой за период
ACCOUNT_METRICS = ["views", "likes", "replies", "reposts", "quotes", "clicks"]
MEDIA_METRICS = "views,likes,replies,reposts,quotes,shares"
# Threads API запрещает since раньше этого времени
MIN_TS = 1712991600


def _get(path, params=None):
    p = {"access_token": TOKEN}
    if params:
        p.update(params)
    r = requests.get(f"{BASE}/{path}", params=p, timeout=30)
    d = r.json()
    if "error" in d:
        raise RuntimeError(f"{path}: {d['error'].get('message')}")
    return d


def _ts(d):
    return max(int(datetime.datetime.combine(d, datetime.time()).timestamp()), MIN_TS)


def _metric_value(row):
    """Достаёт значение метрики из total_value либо суммы values."""
    if "total_value" in row:
        return row["total_value"].get("value")
    vals = row.get("values", [])
    return sum(v.get("value", 0) for v in vals) if vals else None


def _sum_in_range(vals, since, until):
    """Сумма дневного ряда СТРОГО в пределах [since, until).

    Threads insights возвращает лишний пограничный день (обычно since-1) — если его
    не отсечь, он раздувает сумму (напр. июньский всплеск попадал в июль). None, если
    в диапазоне нет ни одного дня."""
    tot, has = 0, False
    for v in vals:
        et = (v.get("end_time") or "")[:10]
        try:
            d0 = datetime.date.fromisoformat(et)
        except ValueError:
            continue
        if since <= d0 < until:
            tot += v.get("value", 0)
            has = True
    return tot if has else None


def _account_totals(since, until):
    d = _get(f"{USER_ID}/threads_insights", {
        "metric": ",".join(ACCOUNT_METRICS),
        "since": _ts(since), "until": _ts(until)})
    out = {}
    for row in d.get("data", []):
        # total_value — уже сумма за период (likes/replies/reposts/quotes);
        # дневной ряд (views) суммируем сами, отсекая пограничные дни вне периода.
        if "total_value" in row:
            out[row["name"]] = row["total_value"].get("value")
        else:
            out[row["name"]] = _sum_in_range(row.get("values", []), since, until)
    return out


def _followers_series(since, until):
    """followers_count — временной ряд; вернём (первое, последнее) для дельты."""
    try:
        d = _get(f"{USER_ID}/threads_insights", {
            "metric": "followers_count",
            "since": _ts(since), "until": _ts(until)})
        row = d["data"][0]
        if "total_value" in row:
            return None, row["total_value"].get("value")
        vals = row.get("values", [])
        if vals:
            return vals[0].get("value"), vals[-1].get("value")
    except Exception:  # noqa: BLE001
        pass
    return None, None


# --- Прирост подписчиков по СОБСТВЕННОЙ истории снимков ------------------------
# Threads API отдаёт followers_count только как текущее total_value (не дневной
# ряд), поэтому дельту за период считаем по своим ежедневным снимкам.
FOLL_HISTORY = os.path.join(DATA_DIR, "threads_followers_history.json")


def current_followers():
    """Текущее абсолютное число подписчиков (total_value) или None."""
    try:
        d = _get(f"{USER_ID}/threads_insights", {"metric": "followers_count"})
        return int(d["data"][0]["total_value"]["value"])
    except Exception:  # noqa: BLE001
        return None


def load_follower_history():
    try:
        with open(FOLL_HISTORY, encoding="utf-8") as f:
            return {datetime.date.fromisoformat(k): int(v)
                    for k, v in json.load(f).items()}
    except Exception:  # noqa: BLE001
        return {}


def _interp(hist, target):
    if not hist:
        return None
    if target in hist:
        return hist[target]
    before = [d for d in hist if d <= target]
    after = [d for d in hist if d >= target]
    if not before or not after:
        return None
    a, b = max(before), min(after)
    if a == b:
        return hist[a]
    return hist[a] + (hist[b] - hist[a]) * ((target - a).days / ((b - a).days))


def follower_growth_history(start, end, hist=None):
    """Прирост подписчиков за [start, end) по истории снимков. None — если не покрыто."""
    if hist is None:
        hist = load_follower_history()
    vs = _interp(hist, start)
    ve = _interp(hist, end)
    if vs is None or ve is None:
        return None
    return round(ve - vs)


def _media_insights(mid):
    try:
        d = _get(f"{mid}/insights", {"metric": MEDIA_METRICS})
        return {row["name"]: _metric_value(row) for row in d.get("data", [])}
    except Exception:  # noqa: BLE001
        return {}


def _posts_since(week_start):
    d = _get(f"{USER_ID}/threads", {
        "fields": "id,media_type,text,permalink,timestamp",
        "since": _ts(week_start), "limit": 50})
    items = []
    for m in d.get("data", []):
        ts = m.get("timestamp", "")[:10]
        try:
            dt = datetime.datetime.strptime(ts, "%Y-%m-%d").date()
        except ValueError:
            continue
        if dt >= week_start:
            m["insights"] = _media_insights(m["id"])
            items.append(m)
    return items


def fetch_and_save():
    if not TOKEN:
        raise RuntimeError("Нет THREADS_ACCESS_TOKEN в .env — сначала получи Threads-токен")
    today = datetime.date.today()
    w_start = today - datetime.timedelta(days=7)
    prev_start = today - datetime.timedelta(days=14)

    prof = _get(USER_ID, {"fields": "id,username"})
    now_foll = current_followers()

    # Прирост — по истории снимков (+ сегодняшняя живая точка), фолбэк на API-ряд
    hist = load_follower_history()
    if now_foll:
        hist[today] = now_foll
    fg_week = follower_growth_history(w_start, today, hist)
    fg_prev = follower_growth_history(prev_start, w_start, hist)
    if fg_week is None:
        f0, f1 = _followers_series(w_start, today)
        fg_week = (f1 - f0) if (f0 and f1) else None

    data = {
        "generated": datetime.datetime.now().isoformat(),
        "week": {"since": str(w_start), "until": str(today)},
        "prev_week": {"since": str(prev_start), "until": str(w_start)},
        "profile": prof,
        "followers_count": now_foll,
        "follower_growth_week": fg_week,
        "follower_growth_prev": fg_prev,
        "totals_week": _account_totals(w_start, today),
        "totals_prev": _account_totals(prev_start, w_start),
        "posts": _posts_since(w_start),
    }

    os.makedirs(os.path.join(DATA_DIR, "archive"), exist_ok=True)
    with open(os.path.join(DATA_DIR, "latest_threads_weekly.json"), "w",
              encoding="utf-8") as f:
        json.dump(scrub(data), f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "archive", f"threads_weekly_{today}.json"), "w",
              encoding="utf-8") as f:
        json.dump(scrub(data), f, ensure_ascii=False, indent=2)
    print(f"[fetch_threads_weekly] Сохранено. Постов за неделю: {len(data['posts'])}")
    return data


if __name__ == "__main__":
    fetch_and_save()
