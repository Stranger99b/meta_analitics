"""Текст МЕСЯЧНОГО отчёта Threads + сводка для AI (рекомендации + оценка SMM)."""
import datetime as dt


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


def _cadence(data):
    """Постов за месяц и в среднем в неделю."""
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
    L = []

    L.append(f"🧵 THREADS — ОТЧЁТ ЗА МЕСЯЦ @{prof.get('username', 'gotrips_by')}")
    L.append(f"{mon['name'].capitalize()} {mon['year']} "
             f"(в скобках — к прошлому месяцу: {data['prev_month']['name']})")
    L.append("")
    if data.get("followers_count") is not None:
        L.append(f"👥 Подписчиков: {_fmt(data.get('followers_count'))}")
    fg, fgp = data.get("follower_growth_month"), data.get("follower_growth_prev")
    if fg is not None:
        L.append(f"📈 Прирост за месяц: +{_fmt(fg)}{_delta(fg, fgp)}")
    n, per_week = _cadence(data)
    L.append(f"📝 Постов за месяц: {n} (~{per_week:.1f}/нед)")

    L.append("")
    L.append("━━━ АКТИВНОСТЬ ━━━")
    L.append("👁 " + _line("Просмотры", tm.get("views"), tp.get("views")))
    L.append("❤️ " + _line("Лайки", tm.get("likes"), tp.get("likes")))
    L.append("💬 " + _line("Ответы", tm.get("replies"), tp.get("replies")))
    L.append("🔁 " + _line("Репосты", tm.get("reposts"), tp.get("reposts")))
    L.append("🗨 " + _line("Цитирования", tm.get("quotes"), tp.get("quotes")))
    if tm.get("clicks") is not None:
        L.append("🔗 " + _line("Клики", tm.get("clicks"), tp.get("clicks")))

    # средний охват на пост
    if n and tm.get("views"):
        L.append(f"📊 Ср. просмотров на пост: {_fmt(round(tm['views'] / n))}")

    posts = [p for p in data.get("posts", []) if p.get("insights", {}).get("views")]
    L.append("")
    if posts:
        views = [p["insights"]["views"] for p in posts]
        avg = sum(views) / len(views)
        viral_thr = avg * 2
        posts.sort(key=lambda p: p["insights"]["views"], reverse=True)
        L.append(f"━━━ ТОП ПОСТОВ МЕСЯЦА ━━━")
        for p in posts[:10]:
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
            L.append(f"🔥 Залетевших постов (≥2× среднего): {len(virals)}")
    else:
        L.append("━━━ ПОСТЫ МЕСЯЦА ━━━")
        L.append("За месяц постов с инсайтами не найдено.")

    return "\n".join(L)


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
