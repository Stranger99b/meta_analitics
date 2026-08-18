"""Текст недельного дайджеста Threads (чистая вёрстка для Telegram HTML)."""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import report_format as rf  # noqa: E402


def _period(week):
    a = dt.date.fromisoformat(week["since"])
    b = dt.date.fromisoformat(week["until"])
    return f"{a.strftime('%d.%m')} – {b.strftime('%d.%m')}"


def build_digest(data) -> str:
    prof = data.get("profile", {})
    tw = data.get("totals_week", {})
    tp = data.get("totals_prev", {})
    S = []

    S.append(rf.b("🧵 THREADS · НЕДЕЛЬНЫЙ ДАЙДЖЕСТ"))
    S.append(f"@{prof.get('username', 'gotrips_by')} · {_period(data['week'])} "
             f"· vs пред. неделя")

    S.append("")
    S.append(rf.b("Аудитория"))
    if data.get("followers_count") is not None:
        S.append(rf.line("Подписчики", data.get("followers_count")))
    fg, fgp = data.get("follower_growth_week"), data.get("follower_growth_prev")
    if fg is not None:
        S.append(f"Прирост за неделю — +{rf.fmt(fg)}{rf.delta(fg, fgp)}")

    S.append("")
    S.append(rf.b("Активность"))
    S.append(rf.line("Просмотры", tw.get("views"), tp.get("views")))
    S.append(rf.line("Лайки", tw.get("likes"), tp.get("likes")))
    S.append(rf.line("Ответы", tw.get("replies"), tp.get("replies")))
    S.append(rf.line("Репосты", tw.get("reposts"), tp.get("reposts")))
    S.append(rf.line("Цитирования", tw.get("quotes"), tp.get("quotes")))
    if tw.get("clicks") is not None:
        S.append(rf.line("Клики", tw.get("clicks"), tp.get("clicks")))

    posts = [p for p in data.get("posts", []) if p.get("insights", {}).get("views")]
    S.append("")
    if posts:
        views = [p["insights"]["views"] for p in posts]
        avg = sum(views) / len(views)
        viral_thr = avg * 2
        posts.sort(key=lambda p: p["insights"]["views"], reverse=True)
        S.append(rf.b(f"Посты недели · {len(posts)} · ср. {rf.fmt(round(avg))}"))
        for i, p in enumerate(posts[:8], 1):
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
        S.append(rf.b("Посты недели"))
        S.append("Новых постов с инсайтами не найдено.")

    return "\n".join(S)


def build_ai_summary(data) -> str:
    tw, tp = data.get("totals_week", {}), data.get("totals_prev", {})
    parts = [f"Threads @{data.get('profile', {}).get('username')}. "
             f"Подписчики: {data.get('followers_count')}, "
             f"прирост за неделю: {data.get('follower_growth_week')}."]
    for k in ("views", "likes", "replies", "reposts", "quotes"):
        parts.append(f"{k}: неделя={tw.get(k)}, прошлая={tp.get(k)}.")
    posts = [p for p in data.get("posts", []) if p.get("insights", {}).get("views")]
    posts.sort(key=lambda p: p["insights"]["views"], reverse=True)
    parts.append("Топ постов недели:")
    for p in posts[:6]:
        text = (p.get("text") or "").replace("\n", " ").strip()[:60]
        parts.append(f"- просмотры={p['insights']['views']} "
                     f"лайки={p['insights'].get('likes')} «{text}»")
    return "\n".join(parts)
