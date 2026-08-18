"""Оценка работы SMM-специалиста по прозрачной рубрике (0–100 → балл 1–10).

Гибрид: часть критериев от норм (постинг, ER, удержание), часть — от динамики
к прошлому периоду. Веса — под приоритет пользователя (рост охвата, ER,
подписчики, сторис — выше). Считается кодом, ИИ только поясняет.

compute_ig(data) / compute_threads(data) принимают dict из fetch_* (недельный или
месячный — определяется по ключам). Возвращают:
  {"total": int 0-100, "grade": float 1-10, "items": [{name, got, max, note}]}
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import ig_content_compare as icc  # noqa: E402

# нормы (можно менять)
POSTS_PER_WEEK = 5          # норма постов/рилс в неделю
ER_TARGET = 1.5            # целевой ER, % (взаимодействия/охват)
RETENTION_TARGET = 80     # целевое удержание сторис, %
STORY_COVER_TARGET = 0.8  # доля дней периода со сторис на макс. балл

WEIGHTS_IG = {"reach": 20, "er": 20, "followers": 18, "stories": 17,
              "activity": 15, "viral": 10}
WEIGHTS_TH = {"reach": 26, "er": 26, "followers": 24, "activity": 14, "viral": 10}


def _pct(cur, prev):
    if not prev or cur is None:
        return None
    return (cur - prev) / prev * 100


def _lin(x, lo, hi):
    if x is None:
        return None
    if x <= lo:
        return 0.0
    if x >= hi:
        return 1.0
    return (x - lo) / (hi - lo)


def _finalize(items):
    """items: list of {name, frac(0..1|None), weight, note}. None frac → исключить."""
    out = []
    tot_got = tot_max = 0.0
    for it in items:
        if it["frac"] is None:
            out.append({"name": it["name"], "got": None, "max": it["weight"],
                        "note": it["note"] + " · н/д (исключён)"})
            continue
        got = it["frac"] * it["weight"]
        tot_got += got
        tot_max += it["weight"]
        out.append({"name": it["name"], "got": round(got), "max": it["weight"],
                    "note": it["note"]})
    total = round(tot_got / tot_max * 100) if tot_max else 0
    return {"total": total, "grade": round(total / 10, 1), "items": out}


def _period(data):
    if "totals_week" in data:
        return (data["totals_week"], data["totals_prev"],
                data.get("follower_growth_week"), data.get("follower_growth_prev"), 7)
    m = data["month"]
    days = (dt.date.fromisoformat(m["until"]) - dt.date.fromisoformat(m["since"])).days
    return (data["totals_month"], data["totals_prev"],
            data.get("follower_growth_month"), data.get("follower_growth_prev"), days)


def _reach_item(cur, prev, weight):
    r, v = _pct(cur.get("reach"), prev.get("reach")), _pct(cur.get("views"), prev.get("views"))
    parts = [x for x in (r, v) if x is not None]
    if not parts:
        return {"name": "Рост охвата/просмотров", "frac": None, "weight": weight,
                "note": "нет прошлого периода"}
    g = sum(parts) / len(parts)
    note = (f"reach {r:+.0f}%" if r is not None else "") + \
           (f" · views {v:+.0f}%" if v is not None else "")
    return {"name": "Рост охвата/просмотров", "frac": _lin(g, -10, 10),
            "weight": weight, "note": note.strip(" ·")}


def _er_item(cur, prev, weight, inter_keys):
    reach = cur.get("reach") or 0
    inter = cur.get("total_interactions") or sum((cur.get(k) or 0) for k in inter_keys)
    er = inter / reach * 100 if reach else 0
    preach = prev.get("reach") or 0
    pinter = prev.get("total_interactions") or sum((prev.get(k) or 0) for k in inter_keys)
    er_prev = pinter / preach * 100 if preach else 0
    frac_abs = _lin(er, 0, ER_TARGET)
    frac_dyn = _lin(_pct(er, er_prev), -10, 10) if er_prev else 0.5
    frac = 0.6 * frac_abs + 0.4 * (frac_dyn if frac_dyn is not None else 0.5)
    return {"name": "Вовлечённость (ER)", "frac": frac, "weight": weight,
            "note": f"ER {er:.2f}% (норма {ER_TARGET}%)"}


def _followers_item(fg, fgp, weight):
    if fg is None:
        return {"name": "Прирост подписчиков", "frac": None, "weight": weight,
                "note": "нет данных"}
    if fg <= 0:
        frac = 0.1
    elif fgp and fg >= fgp:
        frac = 1.0
    elif fgp and fg < fgp:
        frac = 0.6 + 0.3 * _lin(fg / fgp, 0, 1)
    else:
        frac = 0.8
    note = f"+{fg}" + (f" (пред. +{fgp})" if fgp is not None else "")
    return {"name": "Прирост подписчиков", "frac": frac, "weight": weight, "note": note}


def _activity_item(n_posts, days, weight):
    norm = POSTS_PER_WEEK * days / 7
    frac = _lin(n_posts, norm * 0.4, norm)
    return {"name": "Активность (постинг)", "frac": frac, "weight": weight,
            "note": f"{n_posts} публ. (норма ~{round(norm)})"}


def _viral_item(items, weight):
    with_v = [c for c in items if c.get("insights", {}).get("views")]
    if not with_v:
        return {"name": "Виральность (залёты)", "frac": None, "weight": weight,
                "note": "нет контента"}
    avg = sum(c["insights"]["views"] for c in with_v) / len(with_v)
    virals = sum(1 for c in with_v if c["insights"]["views"] >= avg * 2)
    frac = 1.0 if virals >= 2 else (0.6 if virals == 1 else 0.0)
    return {"name": "Виральность (залёты)", "frac": frac, "weight": weight,
            "note": f"{virals} залетевших (≥2× ср.)"}


def _stories_item(stories, days, weight):
    if not stories:
        return {"name": "Работа со сторис", "frac": None, "weight": weight,
                "note": "нет данных сторис"}
    enr = icc.enrich_stories(stories)
    cover = len({s["local_date"] for s in enr}) / days if days else 0
    nav = icc.stories_nav_agg(stories)
    ret = nav.get("retention_pct")
    follows = sum((s.get("insights", {}).get("follows") or 0) for s in stories)
    visits = sum((s.get("insights", {}).get("profile_visits") or 0) for s in stories)
    f_cover = _lin(cover, 0.3, STORY_COVER_TARGET)
    f_ret = _lin(ret, 60, 90) if ret is not None else 0.5
    f_conv = 1.0 if follows > 0 else (0.5 if visits > 0 else 0.0)
    frac = 0.4 * f_cover + 0.4 * f_ret + 0.2 * f_conv
    note = (f"покрытие {cover*100:.0f}% дней · удерж "
            f"{ret if ret is not None else '—'}% · подписки {follows}")
    return {"name": "Работа со сторис", "frac": frac, "weight": weight, "note": note}


def compute_ig(data):
    cur, prev, fg, fgp, days = _period(data)
    content = data.get("content", [])
    stories = data.get("stories", [])
    n_posts = len([c for c in content
                   if c.get("media_product_type") in ("REELS", "FEED", "CAROUSEL_CONTAINER")])
    W = WEIGHTS_IG
    items = [
        _reach_item(cur, prev, W["reach"]),
        _er_item(cur, prev, W["er"], ("likes", "comments", "saves", "shares")),
        _followers_item(fg, fgp, W["followers"]),
        _stories_item(stories, days, W["stories"]),
        _activity_item(n_posts, days, W["activity"]),
        _viral_item(content, W["viral"]),
    ]
    return _finalize(items)


def compute_threads(data):
    cur, prev, fg, fgp, days = _period(data)
    posts = data.get("posts", [])
    n_posts = len(posts)
    W = WEIGHTS_TH
    items = [
        _reach_item(cur, prev, W["reach"]),
        _er_item(cur, prev, W["er"], ("likes", "replies", "reposts", "quotes")),
        _followers_item(fg, fgp, W["followers"]),
        _activity_item(n_posts, days, W["activity"]),
        _viral_item(posts, W["viral"]),
    ]
    return _finalize(items)


def as_text(score):
    """Текстовая сводка оценки для передачи в AI-промпт."""
    lines = [f"ИТОГОВАЯ ОЦЕНКА SMM: {score['grade']}/10 ({score['total']}/100). Разбор:"]
    for it in score["items"]:
        got = "н/д" if it["got"] is None else f"{it['got']}/{it['max']}"
        lines.append(f"- {it['name']}: {got} — {it['note']}")
    return "\n".join(lines)
