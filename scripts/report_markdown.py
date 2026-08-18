"""Генерация отчётов в виде Markdown-документа (.md) для чтения на мобиле.

Полноценный Markdown (# заголовки, списки, ссылки) — читалка/просмотрщик
разворачивает во всю ширину экрана. Ссылки оформлены как [открыть](url),
под блоком сторис — легенда эмодзи.
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
import report_format as rf  # noqa: E402
import ig_content_compare as icc  # noqa: E402

_f = rf.fmt
_d = rf.delta

STORY_LEGEND = (
    "**Обозначения:** 👁 просмотры · 🎯 охват · 👤 визиты в профиль · ➕ подписки · "
    "💬 ответы · ↗️ репосты · 🔒 удержание.  \n"
    "🧭 Навигация: ⏭ пролистнул вперёд · ⏮ вернулся назад · ✖️ закрыл истории · "
    "➡️ ушёл к другому аккаунту.  \n"
    "Удержание = 100% − (закрыли + ушли к др.) ÷ просмотры. 90%+ отлично, "
    "80–90% норма, <80% слабо."
)


def _period(w):
    a = dt.date.fromisoformat(w["since"])
    b = dt.date.fromisoformat(w["until"])
    return f"{a.strftime('%d.%m')}–{b.strftime('%d.%m')}"


def _label(c):
    t = c.get("media_product_type")
    return {"REELS": "Reels", "FEED": "Пост",
            "CAROUSEL_CONTAINER": "Карусель"}.get(t, t or "медиа")


def _metrics(section_title, pairs, tw, tp):
    M = [f"## {section_title}"]
    for lbl, k in pairs:
        M.append(f"- {lbl}: **{_f(tw.get(k))}**{_d(tw.get(k), tp.get(k))}")
    return M


def _story_md(s, i):
    ins = s.get("insights", {})
    r = s.get("retention_pct")
    rt = f"🔒 {r}%" if r is not None else "🔒 —"
    typ = "🎬" if s.get("media_type") == "VIDEO" else "🖼"
    cap = (s.get("caption") or "").replace("\n", " ").strip()[:44]
    line = (f"{i}. {typ} **{s['local_date']} #{s['num']}** · {s['local_time']} — "
            f"👁 {_f(ins.get('views') or 0)} · {rt} · "
            f"👤 {_f(ins.get('profile_visits') or 0)} · ➕ {_f(ins.get('follows') or 0)}")
    if cap:
        line += f" — «{cap}»"
    return line


def _stories_md(stories, earliest):
    if not stories:
        return "## 📸 Сторис\nДанных за период нет (база копится ежедневно)."

    def _s(k):
        return sum((x.get("insights", {}).get(k) or 0) for x in stories)
    n = len(stories)
    views = _s("views")
    head = f"## 📸 Сторис · {n} шт" + (f" · данные с {earliest}" if earliest else "")
    M = [head]
    M.append(f"- 👁 просмотры: **{_f(views)}** (ср. {_f(round(views/n))}) · "
             f"🎯 охват: {_f(_s('reach'))}")
    M.append(f"- 👤 профиль: {_f(_s('profile_visits'))} · ➕ подписки: {_f(_s('follows'))} · "
             f"💬 ответы: {_f(_s('replies'))} · ↗️ репосты: {_f(_s('shares'))}")
    nav = icc.stories_nav_agg(stories)
    if nav.get("retention_pct") is not None:
        M.append(f"- 🧭 навигация: ⏭ {_f(nav['tap_forward'])} · ⏮ {_f(nav['tap_back'])} · "
                 f"✖️ {_f(nav['tap_exit'])} · ➡️ {_f(nav['swipe_forward'])}")
        M.append(f"- 🔒 удержание: **{nav['retention_pct']}%** "
                 f"(ушло {_f(nav['exits'])} из {_f(nav['views'])})")
    enr = icc.enrich_stories(stories)
    top = sorted(enr, key=lambda s: (s.get("insights", {}).get("views") or 0),
                 reverse=True)[:5]
    M.append("")
    M.append("### 🏆 Топ сторис — по просмотрам")
    M += [_story_md(s, i) for i, s in enumerate(top, 1)]
    with_ret = [s for s in enr if s.get("retention_pct") is not None
                and (s.get("insights", {}).get("views") or 0) >= 300]
    weak = sorted(with_ret, key=lambda s: s["retention_pct"])[:3]
    if weak and len(with_ret) > 3:
        M.append("")
        M.append("### ⚠️ Слабое удержание — что улучшить")
        M += [_story_md(s, i) for i, s in enumerate(weak, 1)]
    M.append("")
    M.append("_ID сторис = дата #номер (время). Найти: Instagram → Архив → тот день._")
    M.append("")
    M.append(STORY_LEGEND)
    return "\n".join(M)


def _compare_md(cmp):
    lab = {"REELS": "🎬 Reels", "POSTS": "🖼 Посты", "STORIES": "📸 Сторис"}
    M = ["## Сравнение типов контента"]
    for t in ("REELS", "POSTS", "STORIES"):
        a = cmp.get(t, {})
        if a.get("count"):
            M.append(f"- {lab[t]}: {a['count']} шт · ср. {_f(a['views_avg'])} · "
                     f"всего {_f(a['views_sum'])}")
        else:
            M.append(f"- {lab[t]}: нет данных")
    best = max(("REELS", "POSTS", "STORIES"),
               key=lambda t: cmp.get(t, {}).get("views_avg", 0))
    if cmp.get(best, {}).get("views_avg"):
        M.append("")
        M.append(f"**Лучший по ср. просмотрам:** {lab[best]}")
    return "\n".join(M)


def ig_weekly_md(data, ai_text: str = "") -> str:
    prof = data.get("profile", {})
    tw, tp = data.get("totals_week", {}), data.get("totals_prev", {})
    M = ["# 📸 Instagram — недельный дайджест",
         f"**@{prof.get('username', 'gotrips_by')}** · {_period(data['week'])} · "
         f"vs пред. неделя", ""]

    M.append("## Аудитория")
    M.append(f"- Подписчики: **{_f(prof.get('followers_count'))}**")
    fg, fgp = data.get("follower_growth_week"), data.get("follower_growth_prev")
    if fg is not None:
        M.append(f"- Прирост за неделю: **+{_f(fg)}**{_d(fg, fgp)}")
    M.append("")

    M += _metrics("Охват и просмотры",
                  [("Просмотры", "views"), ("Охват", "reach"),
                   ("Просмотры профиля", "profile_views"),
                   ("Вовлечено аккаунтов", "accounts_engaged")], tw, tp)
    M.append("")
    M += _metrics("Вовлечённость",
                  [("Лайки", "likes"), ("Комментарии", "comments"),
                   ("Сохранения", "saves"), ("Репосты", "shares"),
                   ("Всего", "total_interactions")], tw, tp)
    M.append("")

    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    if content:
        content.sort(key=lambda c: c["insights"]["views"], reverse=True)
        avg = sum(c["insights"]["views"] for c in content) / len(content)
        M.append(f"## Контент недели · {len(content)} · ср. {_f(round(avg))}")
        for i, c in enumerate(content[:8], 1):
            ins = c["insights"]
            v = ins.get("views", 0)
            flag = " 🔥" if v >= avg * 2 else ""
            cap = (c.get("caption") or "").replace("\n", " ").strip()[:90]
            link = f" · [открыть]({c['permalink']})" if c.get("permalink") else ""
            M.append(f"{i}. **{_label(c)}** — 👁 {_f(v)} · ❤ {_f(ins.get('likes'))} · "
                     f"🔖 {_f(ins.get('saved'))}{flag}{link}")
            if cap:
                M.append(f"   «{cap}»")
        M.append("")

    stories = data.get("stories", [])
    M.append(_stories_md(stories, data.get("stories_earliest")))
    M.append("")
    M.append(_compare_md(icc.compare(data.get("content", []), stories)))

    if ai_text:
        M.append("")
        M.append("## 🤖 Вывод недели (AI)")
        M.append(ai_text)

    return "\n".join(M)
