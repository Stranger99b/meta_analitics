"""Формирование текста недельного дайджеста Instagram из данных fetch_ig_weekly."""
import datetime


def _fmt(n):
    if n is None:
        return "—"
    return f"{n:,}".replace(",", " ")


def _delta(cur, prev):
    """WoW-стрелка вида (▲12%)."""
    if cur is None or prev in (None, 0):
        return ""
    p = (cur - prev) / prev * 100
    arrow = "▲" if p >= 0 else "▼"
    return f" ({arrow}{abs(p):.0f}%)"


def _line(label, cur, prev):
    return f"{label}: {_fmt(cur)}{_delta(cur, prev)}"


def _content_label(c):
    t = c.get("media_product_type")
    return {"REELS": "🎬 Reels", "FEED": "🖼 Пост",
            "CAROUSEL_CONTAINER": "🎠 Карусель"}.get(t, t or "медиа")


def build_digest(data) -> str:
    prof = data.get("profile", {})
    tw = data.get("totals_week", {})
    tp = data.get("totals_prev", {})
    L = []

    L.append(f"📸 INSTAGRAM — НЕДЕЛЬНЫЙ ДАЙДЖЕСТ @{prof.get('username', 'gotrips_by')}")
    L.append(f"Неделя {data['week']['since']} → {data['week']['until']} "
             f"(в скобках — к прошлой неделе)")
    L.append("")
    L.append(f"👥 Подписчиков: {_fmt(prof.get('followers_count'))}")
    fg, fgp = data.get("follower_growth_week"), data.get("follower_growth_prev")
    if fg is not None:
        L.append(f"📈 Прирост за неделю: +{_fmt(fg)}{_delta(fg, fgp)}")

    L.append("")
    L.append("━━━ ОХВАТ И ПРОСМОТРЫ ━━━")
    L.append("👁 " + _line("Просмотры", tw.get("views"), tp.get("views")))
    L.append("🎯 " + _line("Охват", tw.get("reach"), tp.get("reach")))
    L.append("👤 " + _line("Просмотры профиля", tw.get("profile_views"),
                           tp.get("profile_views")))
    L.append("🤝 " + _line("Вовлечённые аккаунты", tw.get("accounts_engaged"),
                           tp.get("accounts_engaged")))

    L.append("")
    L.append("━━━ ВЗАИМОДЕЙСТВИЯ ━━━")
    L.append("❤️ " + _line("Лайки", tw.get("likes"), tp.get("likes")))
    L.append("💬 " + _line("Комментарии", tw.get("comments"), tp.get("comments")))
    L.append("🔖 " + _line("Сохранения", tw.get("saves"), tp.get("saves")))
    L.append("↗️ " + _line("Репосты", tw.get("shares"), tp.get("shares")))
    L.append("Σ " + _line("Всего взаимодействий", tw.get("total_interactions"),
                          tp.get("total_interactions")))

    # ── Контент недели ──
    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    L.append("")
    if content:
        views = sorted(c["insights"]["views"] for c in content)
        avg = sum(views) / len(views)
        viral_thr = avg * 2
        content.sort(key=lambda c: c["insights"]["views"], reverse=True)

        L.append(f"━━━ КОНТЕНТ НЕДЕЛИ ({len(content)} публ., ср. просмотры "
                 f"{_fmt(round(avg))}) ━━━")
        for c in content[:8]:
            ins = c["insights"]
            v = ins.get("views", 0)
            flag = " 🔥ЗАЛЁТ" if v >= viral_thr else ""
            cap = (c.get("caption") or "").replace("\n", " ").strip()[:50]
            L.append(f"{_content_label(c)} · 👁{_fmt(v)} ❤️{_fmt(ins.get('likes'))} "
                     f"🔖{_fmt(ins.get('saved'))} ↗️{_fmt(ins.get('shares'))}"
                     f"{flag}")
            L.append(f"   {cap}")
            if c.get("permalink"):
                L.append(f"   {c['permalink']}")
        virals = [c for c in content if c["insights"]["views"] >= viral_thr]
        if virals:
            L.append("")
            L.append(f"🔥 Залетевших (≥2× среднего): {len(virals)}")
    else:
        L.append("━━━ КОНТЕНТ НЕДЕЛИ ━━━")
        L.append("За неделю новых публикаций с инсайтами не найдено.")

    # ── Сторис + сравнение типов ──
    import ig_content_compare as icc
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
    """Компактная сводка для передачи в Qwen (без ссылок и лишнего)."""
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

    # сторис + сравнение типов контента (для советов по миксу)
    import ig_content_compare as icc
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
        parts.append(f"Сторис за период: {len(stories)} шт, просмотры={sv}, "
                     f"визиты профиля={pv}, подписки={sf}.")
    return "\n".join(parts)
