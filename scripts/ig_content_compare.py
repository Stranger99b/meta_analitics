"""Сравнение типов IG-контента (сторис / рилс / посты) за период + агрегаты сторис.

Сторис берутся из накопленной базы data/ig_stories/store.json (см.
fetch_ig_stories_daily). Рилс/посты — из списка медиа (media_product_type).
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import fetch_ig_weekly as fiw  # noqa: E402

STORE = os.path.join(fiw.DATA_DIR, "ig_stories", "store.json")


def stories_in_range(start: dt.date, end: dt.date):
    """Сторис с timestamp в [start, end) из накопленной базы."""
    if not os.path.exists(STORE):
        return []
    with open(STORE, encoding="utf-8") as f:
        store = json.load(f)
    out = []
    for s in store.values():
        ts = (s.get("timestamp") or "")[:10]
        try:
            d = dt.date.fromisoformat(ts)
        except ValueError:
            continue
        if start <= d < end:
            out.append(s)
    return out


def stories_since_earliest():
    """Дата самой ранней сторис в базе — чтобы честно писать 'данные с ...'."""
    if not os.path.exists(STORE):
        return None
    with open(STORE, encoding="utf-8") as f:
        store = json.load(f)
    dates = []
    for s in store.values():
        ts = (s.get("timestamp") or "")[:10]
        try:
            dates.append(dt.date.fromisoformat(ts))
        except ValueError:
            continue
    return min(dates) if dates else None


def stories_nav_agg(stories):
    """Агрегат навигации сторис + удержание (для AI-сводок)."""
    def _n(k):
        return sum((s.get("nav", {}).get(k) or 0) for s in stories)
    views = sum((s.get("insights", {}).get("views") or 0) for s in stories)
    tf, tb = _n("tap_forward"), _n("tap_back")
    te, sf = _n("tap_exit"), _n("swipe_forward")
    exits = te + sf
    retention = round((1 - exits / views) * 100) if views else None
    return {"tap_forward": tf, "tap_back": tb, "tap_exit": te,
            "swipe_forward": sf, "exits": exits, "views": views,
            "retention_pct": retention}


def _agg(items):
    views = [(i.get("insights", {}).get("views") or 0) for i in items]
    reach = [(i.get("insights", {}).get("reach") or 0) for i in items]
    n = len(items)
    return {
        "count": n,
        "views_sum": sum(views),
        "views_avg": round(sum(views) / n) if n else 0,
        "reach_sum": sum(reach),
        "reach_avg": round(sum(reach) / n) if n else 0,
    }


def compare(content, stories):
    """content — список медиа (REELS/FEED/CAROUSEL) с insights; stories — из базы."""
    reels = [m for m in content if m.get("media_product_type") == "REELS"]
    posts = [m for m in content
             if m.get("media_product_type") in ("FEED", "CAROUSEL_CONTAINER")]
    return {
        "REELS": _agg(reels),
        "POSTS": _agg(posts),
        "STORIES": _agg(stories),
    }


LABELS = {"REELS": "🎬 Reels", "POSTS": "🖼 Посты", "STORIES": "📸 Сторис"}


def render_compare(cmp: dict, stories_note: str = "") -> str:
    """Текстовый блок сравнения типов контента."""
    L = ["━━━ СРАВНЕНИЕ ТИПОВ КОНТЕНТА ━━━"]
    if stories_note:
        L.append(stories_note)

    def _f(n):
        return f"{n:,}".replace(",", " ")

    for t in ("REELS", "POSTS", "STORIES"):
        a = cmp.get(t, {})
        if a.get("count"):
            L.append(f"{LABELS[t]}: {a['count']} шт | ср.просмотры {_f(a['views_avg'])} | "
                     f"сумма {_f(a['views_sum'])}")
        else:
            L.append(f"{LABELS[t]}: нет данных")

    # вывод: какой тип даёт больше просмотров на единицу
    ranked = sorted(("REELS", "POSTS", "STORIES"),
                    key=lambda t: cmp.get(t, {}).get("views_avg", 0), reverse=True)
    best = ranked[0]
    if cmp.get(best, {}).get("views_avg"):
        L.append(f"👉 Лучший по ср.просмотрам: {LABELS[best]} "
                 f"({_f(cmp[best]['views_avg'])}/ед)")
    return "\n".join(L)


def render_stories(stories, note: str = "") -> str:
    """Текстовый блок аналитики сторис за период."""
    def _f(n):
        return f"{n:,}".replace(",", " ")

    L = ["━━━ 📸 СТОРИС ━━━"]
    if note:
        L.append(note)
    if not stories:
        L.append("Данных по сторис за период нет (база копится ежедневно).")
        return "\n".join(L)

    n = len(stories)
    def _s(metric):
        return sum((s.get("insights", {}).get(metric) or 0) for s in stories)
    views, reach = _s("views"), _s("reach")
    replies, nav = _s("replies"), _s("navigation")
    profile_visits, follows = _s("profile_visits"), _s("follows")
    shares, inter = _s("shares"), _s("total_interactions")
    # удержание: доля навигаций tap_forward/exit не отдаётся отдельно без breakdown,
    # показываем базовые агрегаты
    L.append(f"Сторис: {n} шт | 👁 просмотры {_f(views)} (ср. {_f(round(views/n))}) | "
             f"🎯 охват {_f(reach)}")
    L.append(f"💬 ответы {_f(replies)} | ↗️ репосты {_f(shares)} | "
             f"👤 визиты в профиль {_f(profile_visits)} | "
             f"➕ подписки {_f(follows)} | Σ взаимодействий {_f(inter)}")

    # Навигация + удержание
    def _nav(k):
        return sum((s.get("nav", {}).get(k) or 0) for s in stories)
    tf, tb = _nav("tap_forward"), _nav("tap_back")
    te, sf = _nav("tap_exit"), _nav("swipe_forward")
    nav_total = tf + tb + te + sf
    if nav_total:
        exits = te + sf
        # удержание = доля НЕ ушедших от просмотров (уходы = закрытия + свайпы к др. аккаунтам)
        retention = (1 - exits / views) * 100 if views else 0
        L.append(f"🧭 Навигация: ⏭ вперёд {_f(tf)} | ⏮ назад {_f(tb)} | "
                 f"✖️ закрыли {_f(te)} | ➡️ ушли к др. {_f(sf)}")
        L.append(f"🔒 Удержание: {retention:.0f}% "
                 f"(ушло {_f(exits)} из {_f(views)} просмотров)")
    # топ-3 сторис по просмотрам
    top = sorted(stories, key=lambda s: (s.get("insights", {}).get("views") or 0),
                 reverse=True)[:3]
    if top:
        L.append("Топ сторис:")
        for s in top:
            ins = s.get("insights", {})
            cap = (s.get("caption") or "").replace("\n", " ").strip()[:40]
            when = (s.get("timestamp") or "")[:10]
            L.append(f"  👁{_f(ins.get('views') or 0)} 👤{_f(ins.get('profile_visits') or 0)} "
                     f"➕{_f(ins.get('follows') or 0)} · {when} {cap}")
    return "\n".join(L)
