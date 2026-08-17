#!/usr/bin/env python3
"""ПРОТОТИП-разведчик Instagram Insights для @gotrips_by.

Дёргает всё, что отдаёт Instagram Graph API (путь Facebook Login) текущим
токеном, складывает сырой ответ в data/ig_insights_YYYY-MM-DD.json и печатает
человекочитаемое саммари. Цель — увидеть, какие метрики реально доступны,
прежде чем строить регулярный отчёт.

Запуск:  python3 scripts/fetch_ig_insights.py [дней_назад=30]
"""
import os
import sys
import json
import datetime
import requests

BASE = "https://graph.facebook.com/v21.0"
IG_ID = "17841422507211860"          # @gotrips_by (из памяти проекта)
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load_env():
    env = {}
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


def get(token, path, params=None):
    """GET к Graph API. Возвращает (ok, data|error_dict)."""
    p = {"access_token": token}
    if params:
        p.update(params)
    try:
        r = requests.get(f"{BASE}/{path}", params=p, timeout=30)
        data = r.json()
        if "error" in data:
            return False, data["error"]
        return True, data
    except Exception as e:  # noqa: BLE001
        return False, {"message": str(e), "type": "exception"}


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    env = load_env()
    token = env.get("META_ACCESS_TOKEN", "").strip()
    if not token:
        print("Нет META_ACCESS_TOKEN в .env"); sys.exit(1)

    today = datetime.date.today()
    since = today - datetime.timedelta(days=days)
    since_ts = int(datetime.datetime.combine(since, datetime.time()).timestamp())
    until_ts = int(datetime.datetime.combine(today, datetime.time()).timestamp())

    out = {"generated": datetime.datetime.now().isoformat(),
           "ig_id": IG_ID, "period_days": days, "sections": {}}

    def record(name, ok, data):
        out["sections"][name] = {"ok": ok, "data": data}
        mark = "✅" if ok else "❌"
        print(f"{mark} {name}", "" if ok else f"→ {data.get('message','')[:90]}")
        return ok, data

    print(f"\n=== Instagram Insights разведка @gotrips_by, за {days} дн. ===\n")

    # 1. Профиль
    record("profile", *get(token, IG_ID, {
        "fields": "username,followers_count,follows_count,media_count"}))

    # 2. Аккаунт-инсайты: временные ряды (по дням)
    for metric in ["reach", "follower_count"]:
        record(f"account_timeseries_{metric}", *get(token, f"{IG_ID}/insights", {
            "metric": metric, "period": "day",
            "since": since_ts, "until": until_ts}))

    # 3. Аккаунт-инсайты: суммарные значения за период (новый API)
    total_metrics = ("views,profile_views,accounts_engaged,total_interactions,"
                     "likes,comments,saves,shares,replies,reach")
    record("account_totals", *get(token, f"{IG_ID}/insights", {
        "metric": total_metrics, "period": "day",
        "metric_type": "total_value",
        "since": since_ts, "until": until_ts}))

    # 4. Демография подписчиков (разные разбивки)
    for bd in ["age", "gender", "city", "country"]:
        record(f"follower_demographics_{bd}", *get(token, f"{IG_ID}/insights", {
            "metric": "follower_demographics", "period": "lifetime",
            "metric_type": "total_value", "timeframe": "this_month",
            "breakdown": bd}))

    # 5. Последние медиа + их инсайты
    ok, media = get(token, f"{IG_ID}/media", {
        "fields": "id,media_type,media_product_type,caption,permalink,timestamp,"
                  "like_count,comments_count",
        "limit": 25})
    record("media_list", ok, media)

    media_metrics = "reach,views,likes,comments,saved,shares,total_interactions"
    media_insights = []
    if ok:
        for m in media.get("data", []):
            mi_ok, mi = get(token, f"{m['id']}/insights",
                            {"metric": media_metrics})
            vals = {}
            if mi_ok:
                for row in mi.get("data", []):
                    v = row.get("values", [{}])
                    vals[row["name"]] = (v[0].get("value") if v else
                                         row.get("total_value", {}).get("value"))
            media_insights.append({
                "id": m["id"], "type": m.get("media_product_type"),
                "timestamp": m.get("timestamp"),
                "caption": (m.get("caption") or "")[:80],
                "permalink": m.get("permalink"),
                "insights": vals, "error": None if mi_ok else mi.get("message")})
        out["sections"]["media_insights"] = {"ok": True, "data": media_insights}
        print(f"✅ media_insights → {len(media_insights)} медиа обработано")

    # Сохранить
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"ig_insights_{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Сырой ответ: {path}")

    # Саммари по реелс (детектор «залетевших»)
    reels = [m for m in media_insights
             if m["type"] == "REELS" and m["insights"].get("views")]
    if reels:
        views = [r["insights"]["views"] for r in reels]
        avg = sum(views) / len(views)
        print(f"\n=== РЕЕЛС: {len(reels)} шт., средние просмотры {avg:,.0f} ===")
        for r in sorted(reels, key=lambda x: x["insights"]["views"], reverse=True):
            v = r["insights"]["views"]
            flag = "🔥 ЗАЛЁТ" if v >= avg * 2 else ""
            print(f"  {v:>8,} просм | ❤️{r['insights'].get('likes',0):>5} | "
                  f"{r['timestamp'][:10]} {flag}  {r['caption'][:45]}")


if __name__ == "__main__":
    main()
