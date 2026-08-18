"""Текст недельного дайджеста Instagram (чистая вёрстка для Telegram HTML)."""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import report_format as rf  # noqa: E402
import ig_content_compare as icc  # noqa: E402


def _period(week):
    a = dt.date.fromisoformat(week["since"])
    b = dt.date.fromisoformat(week["until"])
    return f"{a.strftime('%d.%m')} – {b.strftime('%d.%m')}"


def _content_label(c):
    t = c.get("media_product_type")
    return {"REELS": "Reels", "FEED": "Пост",
            "CAROUSEL_CONTAINER": "Карусель"}.get(t, t or "медиа")


def build_digest(data) -> str:
    prof = data.get("profile", {})
    tw = data.get("totals_week", {})
    tp = data.get("totals_prev", {})
    S = []

    S.append(rf.b("📸 INSTAGRAM · НЕДЕЛЬНЫЙ ДАЙДЖЕСТ"))
    S.append(f"@{prof.get('username', 'gotrips_by')} · {_period(data['week'])} "
             f"· vs пред. неделя")

    # Аудитория
    S.append("")
    S.append(rf.b("Аудитория"))
    S.append(rf.line("Подписчики", prof.get("followers_count")))
    fg, fgp = data.get("follower_growth_week"), data.get("follower_growth_prev")
    if fg is not None:
        S.append(f"Прирост — +{rf.fmt(fg)}{rf.delta(fg, fgp)}")

    # Охват
    S.append("")
    S.append(rf.b("Охват и просмотры"))
    S.append(rf.line("Просмотры", tw.get("views"), tp.get("views")))
    S.append(rf.line("Охват", tw.get("reach"), tp.get("reach")))
    S.append(rf.line("Просмотры профиля", tw.get("profile_views"), tp.get("profile_views")))
    S.append(rf.line("Вовлечено аккаунтов", tw.get("accounts_engaged"),
                     tp.get("accounts_engaged")))

    # Вовлечённость
    S.append("")
    S.append(rf.b("Вовлечённость"))
    S.append(rf.line("Лайки", tw.get("likes"), tp.get("likes")))
    S.append(rf.line("Комментарии", tw.get("comments"), tp.get("comments")))
    S.append(rf.line("Сохранения", tw.get("saves"), tp.get("saves")))
    S.append(rf.line("Репосты", tw.get("shares"), tp.get("shares")))
    S.append(rf.line("Всего", tw.get("total_interactions"), tp.get("total_interactions")))

    # Контент недели
    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    S.append("")
    if content:
        views = [c["insights"]["views"] for c in content]
        avg = sum(views) / len(views)
        viral_thr = avg * 2
        content.sort(key=lambda c: c["insights"]["views"], reverse=True)
        S.append(rf.b(f"Контент недели · {len(content)} публ. · ср. {rf.fmt(round(avg))}"))
        for i, c in enumerate(content[:8], 1):
            ins = c["insights"]
            v = ins.get("views", 0)
            flag = "  🔥" if v >= viral_thr else ""
            cap = (c.get("caption") or "").replace("\n", " ").strip()[:52]
            S.append(f"{i}. {_content_label(c)} — {rf.fmt(v)} просм · "
                     f"❤{rf.fmt(ins.get('likes'))} 🔖{rf.fmt(ins.get('saved'))}{flag}")
            if cap:
                S.append(f"   «{cap}»")
            if c.get("permalink"):
                S.append(f"   {c['permalink']}")
        virals = [c for c in content if c["insights"]["views"] >= viral_thr]
        if virals:
            S.append(f"🔥 Залетевших (≥2× среднего): {len(virals)}")
    else:
        S.append(rf.b("Контент недели"))
        S.append("Новых публикаций с инсайтами не найдено.")

    # Сторис
    stories = data.get("stories", [])
    note = f"данные копятся с {data['stories_earliest']}" if data.get("stories_earliest") else ""
    S.append("")
    S.append(icc.render_stories(stories, note))

    # Сравнение типов
    S.append("")
    S.append(icc.render_compare(icc.compare(data.get("content", []), stories)))

    return "\n".join(S)


def build_ai_summary(data) -> str:
    """Компактная сводка для Qwen (не отображается — вёрстка не важна)."""
    tw, tp = data.get("totals_week", {}), data.get("totals_prev", {})
    parts = [f"Подписчики: {data['profile'].get('followers_count')}, "
             f"прирост за неделю: {data.get('follower_growth_week')}."]
    for k in ("views", "reach", "profile_views", "total_interactions",
              "likes", "saves", "shares"):
        parts.append(f"{k}: неделя={tw.get(k)}, прошлая={tp.get(k)}.")
    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    content.sort(key=lambda c: c["insights"]["views"], reverse=True)
    parts.append("Топ контента недели:")
    for c in content[:6]:
        cap = (c.get("caption") or "").replace("\n", " ").strip()[:60]
        parts.append(f"- {_content_label(c)} просмотры={c['insights']['views']} "
                     f"лайки={c['insights'].get('likes')} «{cap}»")
    stories = data.get("stories", [])
    cmp = icc.compare(data.get("content", []), stories)
    parts.append("Сравнение типов (кол-во / ср.просмотры):")
    for t in ("REELS", "POSTS", "STORIES"):
        a = cmp.get(t, {})
        parts.append(f"- {t}: {a.get('count', 0)} шт, ср.просмотры {a.get('views_avg', 0)}")
    if stories:
        sv = sum((s.get("insights", {}).get("views") or 0) for s in stories)
        sf = sum((s.get("insights", {}).get("follows") or 0) for s in stories)
        pv = sum((s.get("insights", {}).get("profile_visits") or 0) for s in stories)
        nav = icc.stories_nav_agg(stories)
        parts.append(f"Сторис за период: {len(stories)} шт, просмотры={sv}, "
                     f"визиты профиля={pv}, подписки={sf}, "
                     f"удержание={nav.get('retention_pct')}%.")
    return "\n".join(parts)
