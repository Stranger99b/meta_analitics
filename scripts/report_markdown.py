"""IG-отчёт в виде Markdown-документа (.md), компактно под МОБИЛУ.

Встроенный вьювер Telegram рендерит файл моноширинным шрифтом «по ширине
экрана», поэтому строки держим КОРОТКИМИ (без длинных URL — вместо ссылки
короткий код поста). Тогда шрифт остаётся крупным. Ссылки/детали — в CSV.
Под блоком сторис — легенда эмодзи.
"""
import sys
import os
import textwrap
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import report_format as rf  # noqa: E402
import ig_content_compare as icc  # noqa: E402

_f = rf.fmt
_d = rf.delta


def _period(w):
    a = dt.date.fromisoformat(w["since"])
    b = dt.date.fromisoformat(w["until"])
    return f"{a.strftime('%d.%m')}–{b.strftime('%d.%m')}"


def _label(c):
    t = c.get("media_product_type")
    return {"REELS": "Reels", "FEED": "Пост",
            "CAROUSEL_CONTAINER": "Карусель"}.get(t, t or "медиа")


def _short_link(permalink):
    """.../p/CODE/ → 'p/CODE'; .../reel/CODE/ → 'reel/CODE'. Коротко для мобилы."""
    if not permalink:
        return ""
    parts = [p for p in permalink.split("/") if p]
    for kind in ("reel", "p", "stories"):
        if kind in parts:
            i = parts.index(kind)
            if i + 1 < len(parts):
                return f"{kind}/{parts[i+1]}"
    return ""


def _cap(s, n=30):
    return (s or "").replace("\n", " ").strip()[:n]


def _metrics(title, pairs, tw, tp):
    M = [f"## {title}"]
    for lbl, k in pairs:
        M.append(f"{lbl}: **{_f(tw.get(k))}**{_d(tw.get(k), tp.get(k))}")
    return M


def _story_md(s, i):
    ins = s.get("insights", {})
    r = s.get("retention_pct")
    rt = f"🔒 {r}%" if r is not None else "🔒 —"
    typ = "🎬" if s.get("media_type") == "VIDEO" else "🖼"
    lines = [f"{i}. {typ} {s['local_date']} #{s['num']} · {s['local_time']}",
             f"   👁 {_f(ins.get('views') or 0)} · {rt}",
             f"   👤 {_f(ins.get('profile_visits') or 0)} · ➕ {_f(ins.get('follows') or 0)}"]
    cap = _cap(s.get("caption"), 28)
    if cap:
        lines.append(f"   «{cap}»")
    return "\n".join(lines)


def _stories_md(stories, earliest):
    if not stories:
        return "## 📸 Сторис\nДанных нет (база копится)."

    def _s(k):
        return sum((x.get("insights", {}).get(k) or 0) for x in stories)
    n = len(stories)
    views = _s("views")
    M = [f"## 📸 Сторис · {n} шт"]
    if earliest:
        M.append(f"_данные с {earliest}_")
    M.append(f"👁 просмотры: **{_f(views)}**")
    M.append(f"    (ср. {_f(round(views/n))})")
    M.append(f"🎯 охват: {_f(_s('reach'))}")
    M.append(f"👤 профиль: {_f(_s('profile_visits'))}")
    M.append(f"➕ подписки: {_f(_s('follows'))}")
    M.append(f"💬 ответы: {_f(_s('replies'))} · ↗️ {_f(_s('shares'))}")
    nav = icc.stories_nav_agg(stories)
    if nav.get("retention_pct") is not None:
        M.append(f"🔒 удержание: **{nav['retention_pct']}%**")
        M.append(f"🧭 ⏭ {_f(nav['tap_forward'])} · ⏮ {_f(nav['tap_back'])}")
        M.append(f"    ✖️ {_f(nav['tap_exit'])} · ➡️ {_f(nav['swipe_forward'])}")
    enr = icc.enrich_stories(stories)
    top = sorted(enr, key=lambda s: (s.get("insights", {}).get("views") or 0),
                 reverse=True)[:5]
    M.append("")
    M.append("### 🏆 Топ сторис")
    M += [_story_md(s, i) for i, s in enumerate(top, 1)]
    with_ret = [s for s in enr if s.get("retention_pct") is not None
                and (s.get("insights", {}).get("views") or 0) >= 300]
    weak = sorted(with_ret, key=lambda s: s["retention_pct"])[:3]
    if weak and len(with_ret) > 3:
        M.append("")
        M.append("### ⚠️ Слабое удержание")
        M += [_story_md(s, i) for i, s in enumerate(weak, 1)]
    M.append("")
    M.append("_ID = дата #номер (время)._")
    M.append("_Найти: IG → Архив → тот день._")
    M.append("")
    M.append("### Обозначения")
    M.append("👁 просмотры · 🎯 охват")
    M.append("👤 визиты профиля")
    M.append("➕ подписки со сторис")
    M.append("💬 ответы · ↗️ репосты")
    M.append("🔒 удержание аудитории")
    M.append("🧭 навигация:")
    M.append("⏭ пролистнул вперёд")
    M.append("⏮ вернулся назад")
    M.append("✖️ закрыл истории")
    M.append("➡️ ушёл к др. аккаунту")
    return "\n".join(M)


def _compare_md(cmp):
    lab = {"REELS": "🎬 Reels", "POSTS": "🖼 Посты", "STORIES": "📸 Сторис"}
    M = ["## Типы контента"]
    for t in ("REELS", "POSTS", "STORIES"):
        a = cmp.get(t, {})
        if a.get("count"):
            M.append(f"{lab[t]}: {a['count']} шт")
            M.append(f"    ср. {_f(a['views_avg'])} просм")
        else:
            M.append(f"{lab[t]}: нет данных")
    best = max(("REELS", "POSTS", "STORIES"),
               key=lambda t: cmp.get(t, {}).get("views_avg", 0))
    if cmp.get(best, {}).get("views_avg"):
        M.append(f"**Лучший: {lab[best]}**")
    return "\n".join(M)


def ig_weekly_md(data, ai_text: str = "") -> str:
    prof = data.get("profile", {})
    tw, tp = data.get("totals_week", {}), data.get("totals_prev", {})
    M = ["# 📸 IG — недельный",
         f"**@{prof.get('username', 'gotrips_by')}**",
         f"{_period(data['week'])} · vs пред.", ""]

    M.append("## Аудитория")
    M.append(f"Подписчики: **{_f(prof.get('followers_count'))}**")
    fg, fgp = data.get("follower_growth_week"), data.get("follower_growth_prev")
    if fg is not None:
        M.append(f"Прирост: **+{_f(fg)}**{_d(fg, fgp)}")
    M.append("")

    M += _metrics("Охват", [("Просмотры", "views"), ("Охват", "reach"),
                            ("Профиль", "profile_views"),
                            ("Вовлечено", "accounts_engaged")], tw, tp)
    M.append("")
    M += _metrics("Вовлечённость",
                  [("Лайки", "likes"), ("Комменты", "comments"),
                   ("Сохранения", "saves"), ("Репосты", "shares"),
                   ("Всего", "total_interactions")], tw, tp)
    M.append("")

    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    if content:
        content.sort(key=lambda c: c["insights"]["views"], reverse=True)
        avg = sum(c["insights"]["views"] for c in content) / len(content)
        M.append(f"## Контент · {len(content)} шт")
        for i, c in enumerate(content[:8], 1):
            ins = c["insights"]
            v = ins.get("views", 0)
            flag = " 🔥" if v >= avg * 2 else ""
            M.append(f"{i}. {_label(c)} · 👁 {_f(v)}{flag}")
            M.append(f"   ❤ {_f(ins.get('likes'))} · 🔖 {_f(ins.get('saved'))}")
            cap = _cap(c.get("caption"), 30)
            if cap:
                M.append(f"   «{cap}»")
            sl = _short_link(c.get("permalink"))
            if sl:
                M.append(f"   → {sl}")
        M.append("")

    stories = data.get("stories", [])
    M.append(_stories_md(stories, data.get("stories_earliest")))
    M.append("")
    M.append(_compare_md(icc.compare(data.get("content", []), stories)))

    if ai_text:
        M.append("")
        M.append("## 🤖 Вывод недели")
        M.append(_wrap(ai_text))

    return "\n".join(M)


def _wrap(text, width=34):
    """Переносит длинные абзацы AI под узкий экран (по словам)."""
    out = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            out.append("")
            continue
        out.append("\n".join(textwrap.wrap(para, width=width)) or para)
    return "\n".join(out)
