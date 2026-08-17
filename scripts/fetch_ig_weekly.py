"""Сбор данных для недельного дайджеста Instagram (@gotrips_by).

Тянет агрегаты за текущую неделю (7 дней) и предыдущую (7 дней до неё) для
WoW-сравнения + контент, опубликованный за неделю, с per-media инсайтами.
Сохраняет в data/latest_ig_weekly.json и data/archive/ig_weekly_YYYY-MM-DD.json.
"""
import os
import json
import datetime
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = "https://graph.facebook.com/v21.0"
IG_ID = "17841422507211860"  # @gotrips_by
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()

# Метрики аккаунта, у которых есть суммарное значение за период
TOTAL_METRICS = ["views", "reach", "profile_views", "accounts_engaged",
                 "total_interactions", "likes", "comments", "saves", "shares"]
MEDIA_METRICS = "reach,views,likes,comments,saved,shares,total_interactions"


def _get(path, params=None):
    p = {"access_token": TOKEN}
    if params:
        p.update(params)
    r = requests.get(f"{BASE}/{path}", params=p, timeout=30)
    d = r.json()
    if "error" in d:
        raise RuntimeError(f"{path}: {d['error'].get('message')}")
    return d


def _ts(d: datetime.date) -> int:
    return int(datetime.datetime.combine(d, datetime.time()).timestamp())


def _totals(since, until):
    d = _get(f"{IG_ID}/insights", {
        "metric": ",".join(TOTAL_METRICS), "period": "day",
        "metric_type": "total_value", "since": _ts(since), "until": _ts(until)})
    return {row["name"]: row.get("total_value", {}).get("value")
            for row in d.get("data", [])}


def _follower_growth(since, until):
    try:
        d = _get(f"{IG_ID}/insights", {
            "metric": "follower_count", "period": "day",
            "since": _ts(since), "until": _ts(until)})
        return sum(v.get("value", 0) for v in d["data"][0]["values"])
    except Exception:  # noqa: BLE001
        return None


def _media_insights(mid):
    try:
        d = _get(f"{mid}/insights", {"metric": MEDIA_METRICS})
        out = {}
        for row in d.get("data", []):
            v = row.get("values", [{}])
            out[row["name"]] = (v[0].get("value") if v
                                else row.get("total_value", {}).get("value"))
        return out
    except Exception:  # noqa: BLE001
        return {}


def _content_since(week_start):
    d = _get(f"{IG_ID}/media", {
        "fields": "id,media_type,media_product_type,caption,permalink,timestamp,"
                  "like_count,comments_count", "limit": 50})
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
    today = datetime.date.today()
    w_start = today - datetime.timedelta(days=7)
    prev_start = today - datetime.timedelta(days=14)

    data = {
        "generated": datetime.datetime.now().isoformat(),
        "week": {"since": str(w_start), "until": str(today)},
        "prev_week": {"since": str(prev_start), "until": str(w_start)},
        "profile": _get(IG_ID, {"fields": "username,followers_count,media_count"}),
        "totals_week": _totals(w_start, today),
        "totals_prev": _totals(prev_start, w_start),
        "follower_growth_week": _follower_growth(w_start, today),
        "follower_growth_prev": _follower_growth(prev_start, w_start),
        "content": _content_since(w_start),
    }

    os.makedirs(os.path.join(DATA_DIR, "archive"), exist_ok=True)
    with open(os.path.join(DATA_DIR, "latest_ig_weekly.json"), "w",
              encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "archive", f"ig_weekly_{today}.json"), "w",
              encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_ig_weekly] Сохранено. Контента за неделю: {len(data['content'])}")
    return data


if __name__ == "__main__":
    fetch_and_save()
