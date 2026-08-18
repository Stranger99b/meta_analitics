"""Ежедневный снапшот сторис Instagram (@gotrips_by).

Instagram Graph API отдаёт ТОЛЬКО активные сторис (последние 24ч) — историю
получить нельзя. Поэтому копим их в data/ig_stories/store.json (ключ = id сторис,
dedup + обновление на более полные инсайты). Запускать раз в сутки по cron.

Метрики сторис: reach, views, replies, total_interactions, navigation,
profile_visits, follows, shares.
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import fetch_ig_weekly as fiw  # noqa: E402  (переиспуем _get, IG_ID, DATA_DIR)

STORY_METRICS = ("reach,views,replies,total_interactions,navigation,"
                 "profile_visits,follows,shares")
STORE_DIR = os.path.join(fiw.DATA_DIR, "ig_stories")
STORE = os.path.join(STORE_DIR, "store.json")


def _story_insights(sid):
    try:
        d = fiw._get(f"{sid}/insights", {"metric": STORY_METRICS})
        out = {}
        for r in d.get("data", []):
            v = r.get("values", [{}])
            out[r["name"]] = (v[0].get("value") if v
                              else r.get("total_value", {}).get("value"))
        return out
    except Exception:  # noqa: BLE001
        return {}


def _nav_breakdown(sid):
    """Разбивка навигации: tap_forward/tap_back/tap_exit/swipe_forward.

    Отдаётся только при достаточном числе зрителей — иначе пустой dict.
    """
    try:
        d = fiw._get(f"{sid}/insights", {
            "metric": "navigation",
            "breakdown": "story_navigation_action_type"})
        res = d["data"][0]["total_value"]["breakdowns"][0]["results"]
        return {r["dimension_values"][0]: r["value"] for r in res}
    except Exception:  # noqa: BLE001
        return {}


def _load_store():
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def snapshot():
    d = fiw._get(f"{fiw.IG_ID}/stories", {
        "fields": "id,media_type,media_product_type,timestamp,permalink,caption"})
    stories = d.get("data", [])
    os.makedirs(STORE_DIR, exist_ok=True)
    store = _load_store()
    added = 0
    for s in stories:
        sid = s["id"]
        ins = _story_insights(sid)
        # при повторном захвате берём более полные инсайты (views растут за 24ч)
        prev = store.get(sid)
        if prev and (prev.get("insights", {}).get("views") or 0) >= (ins.get("views") or 0):
            continue
        if sid not in store:
            added += 1
        store[sid] = {
            "id": sid, "media_type": s.get("media_type"),
            "timestamp": s.get("timestamp"), "permalink": s.get("permalink"),
            "caption": (s.get("caption") or "")[:80],
            "insights": ins, "nav": _nav_breakdown(sid),
            "captured": dt.datetime.now().isoformat(),
        }
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    print(f"[ig_stories] активных сейчас: {len(stories)}, новых: {added}, "
          f"всего в базе: {len(store)}")
    # заливаем полную историю в Google-таблицу (не критично, если недоступна)
    try:
        import stories_sheet
        stories_sheet.upload()
    except Exception as e:  # noqa: BLE001
        print(f"[ig_stories] заливка в Sheets пропущена: {e}")
    return store


if __name__ == "__main__":
    snapshot()
