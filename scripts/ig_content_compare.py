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
MINSK = dt.timezone(dt.timedelta(hours=3))  # локальное время GoTrips (UTC+3)


def _local(ts: str):
    """UTC-таймстамп API → локальное время (UTC+3)."""
    try:
        d = dt.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=dt.timezone.utc).astimezone(MINSK)
        return d
    except Exception:  # noqa: BLE001
        return None


def _retention(s):
    nav = s.get("nav", {})
    exits = (nav.get("tap_exit") or 0) + (nav.get("swipe_forward") or 0)
    views = s.get("insights", {}).get("views") or 0
    if not views or not nav:
        return None
    return round((1 - exits / views) * 100)


def enrich_stories(stories):
    """Добавляет к сторис: local_dt, local_date, local_time, num (№ в дне),
    retention_pct. Нумерация — по локальной дате, по времени публикации."""
    items = []
    for s in stories:
        d = _local(s.get("timestamp", ""))
        s = dict(s)
        s["_local_dt"] = d
        s["local_date"] = d.strftime("%d.%m") if d else "??"
        s["local_time"] = d.strftime("%H:%M") if d else "??"
        s["retention_pct"] = _retention(s)
        items.append(s)
    # нумерация внутри дня
    by_day = {}
    for s in sorted(items, key=lambda x: (x["_local_dt"] or dt.datetime.min.replace(
            tzinfo=MINSK))):
        key = s["local_date"]
        by_day.setdefault(key, 0)
        by_day[key] += 1
        s["num"] = by_day[key]
    return items


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
    # Детализация для пост-обработки: сторис с ID (дата #№ время)
    enr = enrich_stories(stories)

    def _story_line(s):
        ins = s.get("insights", {})
        r = s.get("retention_pct")
        rt = f"🔒{r}%" if r is not None else "🔒—"
        cap = (s.get("caption") or "").replace("\n", " ").strip()[:32]
        typ = "🎬" if s.get("media_type") == "VIDEO" else "🖼"
        return (f"  📅{s['local_date']} #{s['num']} ({s['local_time']}) {typ} · "
                f"👁{_f(ins.get('views') or 0)} {rt} 👤{_f(ins.get('profile_visits') or 0)} "
                f"➕{_f(ins.get('follows') or 0)}" + (f" · {cap}" if cap else ""))

    top = sorted(enr, key=lambda s: (s.get("insights", {}).get("views") or 0),
                 reverse=True)[:5]
    if top:
        L.append("🏆 Топ сторис (по просмотрам):")
        L += [_story_line(s) for s in top]

    # слабое удержание (среди сторис с достаточными просмотрами)
    with_ret = [s for s in enr if s.get("retention_pct") is not None
                and (s.get("insights", {}).get("views") or 0) >= 300]
    weak = sorted(with_ret, key=lambda s: s["retention_pct"])[:3]
    if weak and len(with_ret) > 3:
        L.append("⚠️ Слабое удержание (что улучшить):")
        L += [_story_line(s) for s in weak]

    L.append("ℹ️ ID сторис = дата #номер-за-день (время). Ищи в IG → Архив → тот день.")
    return "\n".join(L)


def stories_csv(stories) -> str:
    """CSV со всеми сторис периода для детальной пост-обработки (Excel-friendly)."""
    import io
    import csv
    enr = enrich_stories(stories)
    enr.sort(key=lambda s: (s.get("_local_dt") or dt.datetime.min.replace(tzinfo=MINSK)))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Дата", "№", "Время", "Тип", "Просмотры", "Охват", "Удержание_%",
                "ВизитыПрофиля", "Подписки", "Ответы", "Репосты",
                "Вперёд", "Назад", "Закрыли", "УшлиКДругим", "Подпись", "Ссылка"])
    for s in enr:
        ins = s.get("insights", {})
        nav = s.get("nav", {})
        w.writerow([
            s["local_date"], s["num"], s["local_time"],
            "видео" if s.get("media_type") == "VIDEO" else "фото",
            ins.get("views") or 0, ins.get("reach") or 0,
            s.get("retention_pct") if s.get("retention_pct") is not None else "",
            ins.get("profile_visits") or 0, ins.get("follows") or 0,
            ins.get("replies") or 0, ins.get("shares") or 0,
            nav.get("tap_forward") or 0, nav.get("tap_back") or 0,
            nav.get("tap_exit") or 0, nav.get("swipe_forward") or 0,
            (s.get("caption") or "").replace("\n", " ").strip(),
            s.get("permalink") or "",
        ])
    return buf.getvalue()
