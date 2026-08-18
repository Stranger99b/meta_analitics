"""Текст МЕСЯЧНОГО отчёта Instagram + сводка для AI (оценка SMM + рекомендации)."""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import ig_content_compare as icc  # noqa: E402


def _fmt(n):
    if n is None:
        return "—"
    return f"{n:,}".replace(",", " ")


def _delta(cur, prev):
    if cur is None or prev in (None, 0):
        return ""
    p = (cur - prev) / prev * 100
    arrow = "▲" if p >= 0 else "▼"
    return f" ({arrow}{abs(p):.0f}%)"


def _line(label, cur, prev):
    return f"{label}: {_fmt(cur)}{_delta(cur, prev)}"


def _label(c):
    t = c.get("media_product_type")
    return {"REELS": "🎬 Reels", "FEED": "🖼 Пост",
            "CAROUSEL_CONTAINER": "🎠 Карусель"}.get(t, t or "медиа")


def build_digest(data) -> str:
    prof = data.get("profile", {})
    tm = data.get("totals_month", {})
    tp = data.get("totals_prev", {})
    mon = data["month"]
    L = []

    L.append(f"📸 INSTAGRAM — ОТЧЁТ ЗА МЕСЯЦ @{prof.get('username', 'gotrips_by')}")
    L.append(f"{mon['name'].capitalize()} {mon['year']} "
             f"(в скобках — к прошлому месяцу: {data['prev_month']['name']})")
    L.append("")
    L.append(f"👥 Подписчиков: {_fmt(prof.get('followers_count'))}")
    fg, fgp = data.get("follower_growth_month"), data.get("follower_growth_prev")
    if fg is not None:
        L.append(f"📈 Прирост за месяц: +{_fmt(fg)}{_delta(fg, fgp)}")
    L.append(f"📝 Публикаций (рилс+посты): {data.get('posts_count', 0)}")

    L.append("")
    L.append("━━━ ОХВАТ И ПРОСМОТРЫ ━━━")
    L.append("👁 " + _line("Просмотры", tm.get("views"), tp.get("views")))
    L.append("🎯 " + _line("Охват", tm.get("reach"), tp.get("reach")))
    L.append("👤 " + _line("Просмотры профиля", tm.get("profile_views"),
                           tp.get("profile_views")))
    L.append("🤝 " + _line("Вовлечённые аккаунты", tm.get("accounts_engaged"),
                           tp.get("accounts_engaged")))

    L.append("")
    L.append("━━━ ВЗАИМОДЕЙСТВИЯ ━━━")
    L.append("❤️ " + _line("Лайки", tm.get("likes"), tp.get("likes")))
    L.append("💬 " + _line("Комментарии", tm.get("comments"), tp.get("comments")))
    L.append("🔖 " + _line("Сохранения", tm.get("saves"), tp.get("saves")))
    L.append("↗️ " + _line("Репосты", tm.get("shares"), tp.get("shares")))

    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    L.append("")
    if content:
        views = [c["insights"]["views"] for c in content]
        avg = sum(views) / len(views)
        viral_thr = avg * 2
        content.sort(key=lambda c: c["insights"]["views"], reverse=True)
        L.append("━━━ ТОП ПУБЛИКАЦИЙ МЕСЯЦА ━━━")
        for c in content[:10]:
            ins = c["insights"]
            v = ins.get("views", 0)
            flag = " 🔥ЗАЛЁТ" if v >= viral_thr else ""
            cap = (c.get("caption") or "").replace("\n", " ").strip()[:50]
            L.append(f"{_label(c)} · 👁{_fmt(v)} ❤️{_fmt(ins.get('likes'))} "
                     f"🔖{_fmt(ins.get('saved'))} ↗️{_fmt(ins.get('shares'))}{flag}")
            L.append(f"   {cap}")
            if c.get("permalink"):
                L.append(f"   {c['permalink']}")
        virals = [c for c in content if c["insights"]["views"] >= viral_thr]
        if virals:
            L.append("")
            L.append(f"🔥 Залетевших публикаций (≥2× среднего): {len(virals)}")

    # Сторис + сравнение типов
    stories = data.get("stories", [])
    note = ""
    if data.get("stories_earliest"):
        note = f"(данные сторис копятся с {data['stories_earliest']})"
    L.append("")
    L.append(icc.render_stories(stories, note))
    L.append("")
    cmp = icc.compare(data.get("content", []), stories)
    L.append(icc.render_compare(cmp))

    return "\n".join(L)


def build_ai_summary(data) -> str:
    tm, tp = data.get("totals_month", {}), data.get("totals_prev", {})
    mon = data["month"]
    parts = [
        f"Instagram @{data.get('profile', {}).get('username')}, месяц {mon['name']} "
        f"{mon['year']}.",
        f"Подписчиков: {data['profile'].get('followers_count')}, прирост за месяц: "
        f"{data.get('follower_growth_month')} (прошлый месяц: "
        f"{data.get('follower_growth_prev')}).",
        f"Публикаций (рилс+посты): {data.get('posts_count', 0)}.",
    ]
    for k in ("views", "reach", "profile_views", "accounts_engaged",
              "likes", "comments", "saves", "shares"):
        parts.append(f"{k}: месяц={tm.get(k)}, прошлый месяц={tp.get(k)}.")

    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    content.sort(key=lambda c: c["insights"]["views"], reverse=True)
    parts.append("Топ публикаций месяца:")
    for c in content[:8]:
        ins = c["insights"]
        cap = (c.get("caption") or "").replace("\n", " ").strip()[:65]
        parts.append(f"- {_label(c)} просмотры={ins['views']} лайки={ins.get('likes')} "
                     f"сохранения={ins.get('saved')} «{cap}»")

    stories = data.get("stories", [])
    cmp = icc.compare(data.get("content", []), stories)
    parts.append("Сравнение типов контента (кол-во / ср.просмотры / сумма просмотров):")
    for t in ("REELS", "POSTS", "STORIES"):
        a = cmp.get(t, {})
        parts.append(f"- {t}: {a.get('count', 0)} шт, ср.просмотры {a.get('views_avg', 0)}, "
                     f"сумма {a.get('views_sum', 0)}")
    if stories:
        sv = sum((s.get("insights", {}).get("views") or 0) for s in stories)
        sf = sum((s.get("insights", {}).get("follows") or 0) for s in stories)
        pv = sum((s.get("insights", {}).get("profile_visits") or 0) for s in stories)
        nav = icc.stories_nav_agg(stories)
        parts.append(f"Сторис за месяц: {len(stories)} шт, просмотры={sv}, "
                     f"визиты профиля={pv}, подписки со сторис={sf}, "
                     f"удержание={nav.get('retention_pct')}% "
                     f"(закрытий={nav.get('tap_exit')}, свайпов к др.={nav.get('swipe_forward')}).")
    else:
        parts.append("Данных по сторис за этот месяц нет (сбор начат недавно).")
    return "\n".join(parts)
