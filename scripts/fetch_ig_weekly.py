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
from secrets_scrub import scrub

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = "https://graph.facebook.com/v21.0"
IG_ID = "17841422507211860"  # @gotrips_by
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()

# Метрики аккаунта, у которых есть суммарное значение за период
TOTAL_METRICS = ["views", "reach", "profile_views", "accounts_engaged",
                 "total_interactions", "likes", "comments", "saves", "shares"]
MEDIA_METRICS = "reach,views,likes,comments,saved,shares,total_interactions"
# Доступны ТОЛЬКО для постов ленты (FEED). Для REELS Graph API отвечает error 100
# («does not support ... for this media product type»), поэтому тянем отдельно и
# только для FEED, чтобы не потерять базовые метрики на reels.
FEED_EXTRA_METRICS = "follows,profile_visits,profile_activity"


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


# Органические поверхности (без рекламы AD) — охват SMM считаем только по ним
ORGANIC_SURFACES = {"POST", "REEL", "CAROUSEL_CONTAINER", "STORY"}


def _reach_follow_type(since, until):
    """Охват с разбивкой подписчики/не-подписчики, ОТДЕЛЬНО органика и реклама.

    Account-level reach раздут платной рекламой (AD даёт почти весь охват на
    не-подписчиков). Считаем органику (работа SMM) и рекламу (AD) по отдельности,
    чтобы разница была видна. Возвращает {follower, non_follower, ad_follower,
    ad_non_follower} (follower/non_follower — ОРГАНИКА) или None."""
    try:
        d = _get(f"{IG_ID}/insights", {
            "metric": "reach", "period": "day", "metric_type": "total_value",
            "breakdown": "media_product_type,follow_type",
            "since": _ts(since), "until": _ts(until)})
        tv = (d.get("data") or [{}])[0].get("total_value", {})
        fol = non = ad_fol = ad_non = st_fol = st_non = 0
        got = False
        for b in tv.get("breakdowns", []):
            for res in b.get("results", []):
                surf, ft = res.get("dimension_values", ["", ""])
                val = res.get("value", 0)
                is_fol = ft == "FOLLOWER"
                if surf == "AD":
                    got = True
                    ad_fol += val if is_fol else 0
                    ad_non += 0 if is_fol else val
                elif surf in ORGANIC_SURFACES:
                    got = True
                    fol += val if is_fol else 0
                    non += 0 if is_fol else val
                    if surf == "STORY":  # отдельно для блока сторис
                        st_fol += val if is_fol else 0
                        st_non += 0 if is_fol else val
        return {"follower": fol, "non_follower": non,
                "ad_follower": ad_fol, "ad_non_follower": ad_non,
                "story_follower": st_fol, "story_non_follower": st_non} if got else None
    except Exception:  # noqa: BLE001
        return None


def _ad_reach_placements(since, until):
    """Охват Instagram-рекламы по плейсментам за период (сумма по всем ad-кабинетам).

    IG-инсайты дают только общий бакет AD без разбивки по плейсментам — детализация
    (сторис/лента/reels) есть только в Meta Ads (Marketing) API. Возвращает
    {stories, feed, reels, explore, other} или None."""
    try:
        import json as _json
        import fetch_meta_ads as fma
    except Exception:  # noqa: BLE001
        return None
    buckets = {"stories": 0, "feed": 0, "reels": 0, "explore": 0, "other": 0}
    got = False
    try:
        accts = fma.ad_accounts()
    except Exception:  # noqa: BLE001
        accts = [(fma.AD_ACCOUNT_ID, "")]
    for act, _label in accts:
        try:
            d = fma._get(f"{fma.BASE_URL}/{act}/insights", {
                "fields": "reach", "level": "account",
                "breakdowns": "publisher_platform,platform_position",
                "time_range": _json.dumps({"since": str(since), "until": str(until)})})
        except Exception:  # noqa: BLE001
            continue
        for row in d.get("data", []):
            if row.get("publisher_platform") != "instagram":
                continue
            pos = row.get("platform_position", "") or ""
            reach = int(row.get("reach") or 0)
            if reach == 0:
                continue
            got = True
            if "stories" in pos:
                buckets["stories"] += reach
            elif "reels" in pos:
                buckets["reels"] += reach
            elif "explore" in pos:
                buckets["explore"] += reach
            elif "feed" in pos:
                buckets["feed"] += reach
            else:
                buckets["other"] += reach
    return buckets if got else None


def _follower_growth(since, until):
    try:
        d = _get(f"{IG_ID}/insights", {
            "metric": "follower_count", "period": "day",
            "since": _ts(since), "until": _ts(until)})
        return sum(v.get("value", 0) for v in d["data"][0]["values"])
    except Exception:  # noqa: BLE001
        return None


def _insights_call(mid, metrics):
    """Один запрос инсайтов медиа → {metric: value}. При ошибке — {}."""
    try:
        d = _get(f"{mid}/insights", {"metric": metrics})
        out = {}
        for row in d.get("data", []):
            v = row.get("values", [{}])
            out[row["name"]] = (v[0].get("value") if v
                                else row.get("total_value", {}).get("value"))
        return out
    except Exception:  # noqa: BLE001
        return {}


def _media_insights(mid, product_type=None):
    out = _insights_call(mid, MEDIA_METRICS)
    # follows/profile_visits/profile_activity доступны только у постов ленты
    if product_type == "FEED":
        out.update(_insights_call(mid, FEED_EXTRA_METRICS))
    return out


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
            m["insights"] = _media_insights(m["id"], m.get("media_product_type"))
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
        "reach_ft": _reach_follow_type(w_start, today),
        "reach_ft_prev": _reach_follow_type(prev_start, w_start),
        "ad_placements": _ad_reach_placements(w_start, today),
        "content": _content_since(w_start),
    }

    # Сторис за неделю из накопленной базы (ленивый импорт против цикла).
    # Верхняя граница today+1, чтобы включить сегодняшние сторис (как и контент).
    import ig_content_compare as icc
    data["stories"] = icc.stories_in_range(w_start, today + datetime.timedelta(days=1))
    earliest = icc.stories_since_earliest()
    data["stories_earliest"] = str(earliest) if earliest else None

    os.makedirs(os.path.join(DATA_DIR, "archive"), exist_ok=True)
    with open(os.path.join(DATA_DIR, "latest_ig_weekly.json"), "w",
              encoding="utf-8") as f:
        json.dump(scrub(data), f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "archive", f"ig_weekly_{today}.json"), "w",
              encoding="utf-8") as f:
        json.dump(scrub(data), f, ensure_ascii=False, indent=2)
    print(f"[fetch_ig_weekly] Сохранено. Контента за неделю: {len(data['content'])}")
    return data


if __name__ == "__main__":
    fetch_and_save()
