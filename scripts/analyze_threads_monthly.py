"""Текст МЕСЯЧНОГО отчёта Threads (чистая вёрстка) + сводка для AI."""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import report_format as rf  # noqa: E402


def _cadence(data):
    n = data.get("posts_count", 0)
    ms = dt.date.fromisoformat(data["month"]["since"])
    me = dt.date.fromisoformat(data["month"]["until"])
    days = (me - ms).days
    per_week = n / days * 7 if days else 0
    return n, per_week


def build_digest(data) -> str:
    prof = data.get("profile", {})
    tm = data.get("totals_month", {})
    tp = data.get("totals_prev", {})
    mon = data["month"]
    S = []

    S.append(rf.b("🧵 THREADS · ОТЧЁТ ЗА МЕСЯЦ"))
    S.append(f"@{prof.get('username', 'gotrips_by')} · {mon['name'].capitalize()} "
             f"{mon['year']} · vs {data['prev_month']['name']}")

    S.append("")
    S.append(rf.b("Аудитория"))
    if data.get("followers_count") is not None:
        S.append(rf.line("Подписчики", data.get("followers_count")))
    fg, fgp = data.get("follower_growth_month"), data.get("follower_growth_prev")
    if fg is not None:
        S.append(f"Прирост за месяц — +{rf.fmt(fg)}{rf.delta(fg, fgp)}")
    n, per_week = _cadence(data)
    S.append(f"Постов за месяц — {n}  (~{per_week:.1f}/нед)")

    S.append("")
    S.append(rf.b("Активность"))
    S.append(rf.line("Просмотры", tm.get("views"), tp.get("views")))
    S.append(rf.line("Лайки", tm.get("likes"), tp.get("likes")))
    S.append(rf.line("Ответы", tm.get("replies"), tp.get("replies")))
    S.append(rf.line("Репосты", tm.get("reposts"), tp.get("reposts")))
    S.append(rf.line("Цитирования", tm.get("quotes"), tp.get("quotes")))
    if tm.get("clicks") is not None:
        S.append(rf.line("Клики", tm.get("clicks"), tp.get("clicks")))
    if n and tm.get("views"):
        S.append(rf.line("Ср. просмотров на пост", round(tm["views"] / n)))

    posts = [p for p in data.get("posts", []) if p.get("insights", {}).get("views")]
    S.append("")
    if posts:
        views = [p["insights"]["views"] for p in posts]
        avg = sum(views) / len(views)
        viral_thr = avg * 2
        posts.sort(key=lambda p: p["insights"]["views"], reverse=True)
        S.append(rf.b(f"Топ постов месяца · {len(posts)}"))
        for i, p in enumerate(posts[:10], 1):
            ins = p["insights"]
            v = ins.get("views", 0)
            flag = "  🔥" if v >= viral_thr else ""
            text = (p.get("text") or "").replace("\n", " ").strip()[:55]
            S.append(f"{i}. {rf.fmt(v)} просм · ❤{rf.fmt(ins.get('likes'))} "
                     f"💬{rf.fmt(ins.get('replies'))} 🔁{rf.fmt(ins.get('reposts'))}{flag}")
            if text:
                S.append(f"   «{text}»")
            if p.get("permalink"):
                S.append(f"   {p['permalink']}")
        virals = [p for p in posts if p["insights"]["views"] >= viral_thr]
        if virals:
            S.append(f"🔥 Залетевших (≥2× среднего): {len(virals)}")
    else:
        S.append(rf.b("Посты месяца"))
        S.append("Постов с инсайтами не найдено.")

    return "\n".join(S)


def build_ai_summary(data) -> str:
    tm, tp = data.get("totals_month", {}), data.get("totals_prev", {})
    mon = data["month"]
    n, per_week = _cadence(data)
    parts = [
        f"Threads @{data.get('profile', {}).get('username')}, месяц {mon['name']} {mon['year']}.",
        f"Подписчиков: {data.get('followers_count')}, прирост за месяц: "
        f"{data.get('follower_growth_month')} (прошлый месяц: {data.get('follower_growth_prev')}).",
        f"Постов за месяц: {n} (~{per_week:.1f}/нед).",
    ]
    for k in ("views", "likes", "replies", "reposts", "quotes", "clicks"):
        parts.append(f"{k}: месяц={tm.get(k)}, прошлый месяц={tp.get(k)}.")
    if n and tm.get("views"):
        parts.append(f"Средние просмотры на пост: {round(tm['views'] / n)}.")
    posts = [p for p in data.get("posts", []) if p.get("insights", {}).get("views")]
    posts.sort(key=lambda p: p["insights"]["views"], reverse=True)
    parts.append("Топ постов месяца:")
    for p in posts[:8]:
        ins = p["insights"]
        text = (p.get("text") or "").replace("\n", " ").strip()[:70]
        parts.append(f"- просмотры={ins['views']} лайки={ins.get('likes')} "
                     f"ответы={ins.get('replies')} репосты={ins.get('reposts')} «{text}»")
    return "\n".join(parts)
