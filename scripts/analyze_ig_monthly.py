"""Текст МЕСЯЧНОГО отчёта Instagram + сводка для AI (оценка SMM + рекомендации)."""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import report_format as rf  # noqa: E402
import ig_content_compare as icc  # noqa: E402


def _label(c):
    t = c.get("media_product_type")
    return {"REELS": "Reels", "FEED": "Пост",
            "CAROUSEL_CONTAINER": "Карусель"}.get(t, t or "медиа")


def build_digest(data) -> str:
    prof = data.get("profile", {})
    tm = data.get("totals_month", {})
    tp = data.get("totals_prev", {})
    mon = data["month"]
    S = []

    S.append(rf.b("📸 INSTAGRAM · ОТЧЁТ ЗА МЕСЯЦ"))
    S.append(f"@{prof.get('username', 'gotrips_by')} · {mon['name'].capitalize()} "
             f"{mon['year']} · vs {data['prev_month']['name']}")

    S.append("")
    S.append(rf.b("Аудитория"))
    S.append(rf.line("Подписчики", prof.get("followers_count")))
    fg, fgp = data.get("follower_growth_month"), data.get("follower_growth_prev")
    if fg is not None:
        S.append(f"Прирост за месяц — +{rf.fmt(fg)}{rf.delta(fg, fgp)}")
    S.append(f"Публикаций (рилс+посты) — {data.get('posts_count', 0)}")

    S.append("")
    S.append(rf.b("Охват и просмотры"))
    S.append(rf.line("Просмотры", tm.get("views"), tp.get("views")))
    S.append(rf.line("Охват", tm.get("reach"), tp.get("reach")))
    S.append(rf.line("Просмотры профиля", tm.get("profile_views"), tp.get("profile_views")))
    S.append(rf.line("Вовлечено аккаунтов", tm.get("accounts_engaged"),
                     tp.get("accounts_engaged")))

    S.append("")
    S.append(rf.b("Вовлечённость"))
    S.append(rf.line("Лайки", tm.get("likes"), tp.get("likes")))
    S.append(rf.line("Комментарии", tm.get("comments"), tp.get("comments")))
    S.append(rf.line("Сохранения", tm.get("saves"), tp.get("saves")))
    S.append(rf.line("Репосты", tm.get("shares"), tp.get("shares")))

    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    S.append("")
    if content:
        views = [c["insights"]["views"] for c in content]
        avg = sum(views) / len(views)
        viral_thr = avg * 2
        content.sort(key=lambda c: c["insights"]["views"], reverse=True)
        S.append(rf.b(f"Топ публикаций месяца · {len(content)}"))
        for i, c in enumerate(content[:10], 1):
            ins = c["insights"]
            v = ins.get("views", 0)
            flag = "  🔥" if v >= viral_thr else ""
            cap = (c.get("caption") or "").replace("\n", " ").strip()[:52]
            S.append(f"{i}. {_label(c)} — {rf.fmt(v)} просм · "
                     f"❤{rf.fmt(ins.get('likes'))} 🔖{rf.fmt(ins.get('saved'))}{flag}")
            if cap:
                S.append(f"   «{cap}»")
            if c.get("permalink"):
                S.append(f"   {c['permalink']}")
        virals = [c for c in content if c["insights"]["views"] >= viral_thr]
        if virals:
            S.append(f"🔥 Залетевших (≥2× среднего): {len(virals)}")

    stories = data.get("stories", [])
    note = f"данные копятся с {data['stories_earliest']}" if data.get("stories_earliest") else ""
    S.append("")
    S.append(icc.render_stories(stories, note))
    S.append("")
    S.append(icc.render_compare(icc.compare(data.get("content", []), stories)))

    return "\n".join(S)


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
