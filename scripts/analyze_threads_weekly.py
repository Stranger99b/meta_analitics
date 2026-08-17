"""Формирование текста недельного дайджеста Threads из данных fetch_threads_weekly."""


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


def build_digest(data) -> str:
    prof = data.get("profile", {})
    tw = data.get("totals_week", {})
    tp = data.get("totals_prev", {})
    L = []

    L.append(f"🧵 THREADS — НЕДЕЛЬНЫЙ ДАЙДЖЕСТ @{prof.get('username', 'gotrips_by')}")
    L.append(f"Неделя {data['week']['since']} → {data['week']['until']} "
             f"(в скобках — к прошлой неделе)")
    L.append("")
    if data.get("followers_count") is not None:
        L.append(f"👥 Подписчиков: {_fmt(data.get('followers_count'))}")
    fg, fgp = data.get("follower_growth_week"), data.get("follower_growth_prev")
    if fg is not None:
        L.append(f"📈 Прирост за неделю: +{_fmt(fg)}{_delta(fg, fgp)}")

    L.append("")
    L.append("━━━ АКТИВНОСТЬ ━━━")
    L.append("👁 " + _line("Просмотры", tw.get("views"), tp.get("views")))
    L.append("❤️ " + _line("Лайки", tw.get("likes"), tp.get("likes")))
    L.append("💬 " + _line("Ответы", tw.get("replies"), tp.get("replies")))
    L.append("🔁 " + _line("Репосты", tw.get("reposts"), tp.get("reposts")))
    L.append("🗨 " + _line("Цитирования", tw.get("quotes"), tp.get("quotes")))
    if tw.get("clicks") is not None:
        L.append("🔗 " + _line("Клики", tw.get("clicks"), tp.get("clicks")))

    posts = [p for p in data.get("posts", []) if p.get("insights", {}).get("views")]
    L.append("")
    if posts:
        views = [p["insights"]["views"] for p in posts]
        avg = sum(views) / len(views)
        viral_thr = avg * 2
        posts.sort(key=lambda p: p["insights"]["views"], reverse=True)
        L.append(f"━━━ ПОСТЫ НЕДЕЛИ ({len(posts)} шт., ср. просмотры "
                 f"{_fmt(round(avg))}) ━━━")
        for p in posts[:8]:
            ins = p["insights"]
            v = ins.get("views", 0)
            flag = " 🔥ЗАЛЁТ" if v >= viral_thr else ""
            text = (p.get("text") or "").replace("\n", " ").strip()[:55]
            L.append(f"👁{_fmt(v)} ❤️{_fmt(ins.get('likes'))} "
                     f"💬{_fmt(ins.get('replies'))} 🔁{_fmt(ins.get('reposts'))}{flag}")
            L.append(f"   {text}")
            if p.get("permalink"):
                L.append(f"   {p['permalink']}")
        virals = [p for p in posts if p["insights"]["views"] >= viral_thr]
        if virals:
            L.append("")
            L.append(f"🔥 Залетевших (≥2× среднего): {len(virals)}")
    else:
        L.append("━━━ ПОСТЫ НЕДЕЛИ ━━━")
        L.append("За неделю новых постов с инсайтами не найдено.")

    return "\n".join(L)


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
