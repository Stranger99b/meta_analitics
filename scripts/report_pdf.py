"""IG-отчёт в PDF (reportlab) в фирменном стиле GoTrips (салатовый #73D700).

Цветные emoji — картинками Twemoji (scripts/assets/emoji), кириллица DejaVuSans.
Кликабельные ссылки на посты/рилс, таблицы для сторис и сравнения типов,
номер недели/месяца, ссылка на Google-таблицу сторис. Возвращает bytes PDF.
"""
import io
import os
import sys
import datetime as dt

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, KeepTogether)

sys.path.insert(0, os.path.dirname(__file__))
import report_format as rf  # noqa: E402
import ig_content_compare as icc  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_EMODIR = os.path.join(_HERE, "assets", "emoji")
_FD = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DV", f"{_FD}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", f"{_FD}/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV",
                              boldItalic="DV-B")

# фирменная палитра GoTrips
LIME = colors.HexColor("#73D700")     # салатовый (бренд)
LIME_DK = colors.HexColor("#4A8B00")  # тёмно-зелёный для текста на белом
BANDTX = colors.HexColor("#173a00")   # текст на салатовой плашке
INK = colors.HexColor("#1a1a1a")
MUTE = colors.HexColor("#6b7280")
GREEN = colors.HexColor("#2e9e00")
RED = colors.HexColor("#dc2626")
AMBER = colors.HexColor("#d97706")
BAND = colors.HexColor("#f2fbe8")     # бледно-салатовая заливка строк
LINE = colors.HexColor("#e5e7eb")

_f = rf.fmt

_ss = ParagraphStyle
ST_SUB = _ss("sub", fontName="DV", fontSize=9.5, textColor=MUTE, leading=13)
ST_H2 = _ss("h2", fontName="DV-B", fontSize=13, textColor=LIME_DK, leading=17,
            spaceBefore=11, spaceAfter=4)
ST_LBL = _ss("lbl", fontName="DV", fontSize=10.5, textColor=INK, leading=14)
ST_VAL = _ss("val", fontName="DV-B", fontSize=10.5, textColor=INK, leading=14,
             alignment=2)
ST_BODY = _ss("body", fontName="DV", fontSize=10.5, textColor=INK, leading=15)
ST_CAP = _ss("cap", fontName="DV", fontSize=9, textColor=MUTE, leading=12)
ST_TH = _ss("th", fontName="DV-B", fontSize=9, textColor=BANDTX, leading=11)
ST_TD = _ss("td", fontName="DV", fontSize=9, textColor=INK, leading=11)
ST_TDR = _ss("tdr", fontName="DV", fontSize=9, textColor=INK, leading=11, alignment=2)
ST_AI = _ss("ai", fontName="DV", fontSize=10, textColor=INK, leading=15,
            alignment=TA_LEFT, spaceBefore=2)
ST_TITLE = _ss("title", fontName="DV-B", fontSize=15, textColor=BANDTX, leading=18)


def E(name, size=12, dy=-2):
    """Инлайн цветной emoji-картинкой в Paragraph."""
    p = os.path.join(_EMODIR, f"{name}.png")
    if not os.path.exists(p):
        return ""
    return f'<img src="{p}" width="{size}" height="{size}" valign="{dy}"/> '


def _clean(text: str) -> str:
    out = []
    for ch in text:
        o = ord(ch)
        if (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
                or 0x1F1E6 <= o <= 0x1F1FF or o in (0xFE0F, 0x20E3)
                or 0x2300 <= o <= 0x23FF or 0x2B00 <= o <= 0x2BFF
                or 0x2190 <= o <= 0x21FF):
            continue
        out.append(ch)
    return "".join(out).replace("  ", " ").strip()


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;")


def _trend(cur, prev):
    if cur is None or prev in (None, 0):
        return ""
    p = (cur - prev) / prev * 100
    if round(abs(p)) == 0:
        return ' <font color="#6b7280">≈</font>'
    col = "#2e9e00" if p >= 0 else "#dc2626"
    return f' <font color="{col}">{"▲" if p >= 0 else "▼"}{abs(p):.0f}%</font>'


def _metric_table(pairs, tw, tp, width):
    rows = [[Paragraph(lbl, ST_LBL),
             Paragraph(f"<b>{_f(tw.get(k))}</b>{_trend(tw.get(k), tp.get(k))}", ST_VAL)]
            for lbl, k in pairs]
    t = Table(rows, colWidths=[width * 0.56, width * 0.44])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _story_rows(enr):
    out = []
    for s in enr:
        ins = s.get("insights", {})
        r = s.get("retention_pct")
        if r is None:
            ret = "—"
        else:
            rc = "#2e9e00" if r >= 90 else ("#d97706" if r >= 80 else "#dc2626")
            ret = f'<font color="{rc}">{r}%</font>'
        typ = "видео" if s.get("media_type") == "VIDEO" else "фото"
        out.append({"id": f"{s['local_date']} #{s['num']}",
                    "time": f"{s['local_time']} · {typ}",
                    "views": ins.get("views") or 0, "ret": ret,
                    "prof": ins.get("profile_visits") or 0,
                    "foll": ins.get("follows") or 0})
    return out


def _stories_table(rows_data, width):
    header = [Paragraph(h, ST_TH) for h in
              ("Сторис", "Время", "Просм", "Удерж", "Проф", "+Подп")]
    data = [header]
    for r in rows_data:
        data.append([Paragraph(r["id"], ST_TD), Paragraph(r["time"], ST_TD),
                     Paragraph(_f(r["views"]), ST_TDR), Paragraph(r["ret"], ST_TDR),
                     Paragraph(_f(r["prof"]), ST_TDR), Paragraph(_f(r["foll"]), ST_TDR)])
    w = width
    t = Table(data, colWidths=[w*0.24, w*0.15, w*0.17, w*0.16, w*0.14, w*0.14])
    style = [("BACKGROUND", (0, 0), (-1, 0), LIME),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE)]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))
    t.setStyle(TableStyle(style))
    return t


def _title_band(text_html, width):
    tt = Table([[Paragraph(text_html, ST_TITLE)]], colWidths=[width])
    tt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIME),
                            ("TOPPADDING", (0, 0), (-1, -1), 10),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                            ("LEFTPADDING", (0, 0), (-1, -1), 12)]))
    return tt


def ig_weekly_pdf(data, ai_text: str = "", sheet_url: str = "", score=None,
                  planfact=None) -> bytes:
    prof = data.get("profile", {})
    tw, tp = data.get("totals_week", {}), data.get("totals_prev", {})
    a = dt.date.fromisoformat(data["week"]["since"])
    b = dt.date.fromisoformat(data["week"]["until"])
    iso_y, iso_w, _ = b.isocalendar()
    period = f"{a.strftime('%d.%m')}–{b.strftime('%d.%m')}"

    buf = io.BytesIO()
    PW, PH = 430, 880
    doc = SimpleDocTemplate(buf, pagesize=(PW, PH), leftMargin=26, rightMargin=26,
                            topMargin=24, bottomMargin=26,
                            title=f"IG недельный №{iso_w} · {iso_y}")
    W = PW - 52
    D = []

    D.append(_title_band(
        f'{E("camera",15,-3)}<b>INSTAGRAM</b>  ·  Неделя №{iso_w} · {iso_y}', W))
    D.append(Spacer(1, 4))
    D.append(Paragraph(f"@{prof.get('username','gotrips_by')} · {period} · "
                       f"в сравнении с прошлой неделей", ST_SUB))
    if score:
        D += _score_block(score, W)
    if planfact:
        D += _planfact_block(planfact, W)

    D.append(Paragraph(E("people") + "Аудитория", ST_H2))
    arows = [[Paragraph("Подписчики", ST_LBL),
              Paragraph(f"<b>{_f(prof.get('followers_count'))}</b>", ST_VAL)]]
    fg, fgp = data.get("follower_growth_week"), data.get("follower_growth_prev")
    if fg is not None:
        arows.append([Paragraph("Прирост за неделю", ST_LBL),
                      Paragraph(f"<b>+{_f(fg)}</b>{_trend(fg, fgp)}", ST_VAL)])
    at = Table(arows, colWidths=[W*0.56, W*0.44])
    at.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    D.append(at)

    D.append(Paragraph(E("chart") + "Охват и просмотры", ST_H2))
    D.append(_metric_table([("Просмотры", "views"), ("Охват", "reach"),
                            ("Просмотры профиля", "profile_views"),
                            ("Вовлечено аккаунтов", "accounts_engaged")], tw, tp, W))

    D.append(Paragraph(E("heart") + "Вовлечённость", ST_H2))
    D.append(_metric_table([("Лайки", "likes"), ("Комментарии", "comments"),
                            ("Сохранения", "saves"), ("Репосты", "shares"),
                            ("Всего взаимодействий", "total_interactions")], tw, tp, W))

    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    if content:
        content.sort(key=lambda c: c["insights"]["views"], reverse=True)
        avg = sum(c["insights"]["views"] for c in content) / len(content)
        D.append(Paragraph(E("memo") + f"Контент недели · {len(content)} публ.", ST_H2))
        for i, c in enumerate(content[:8], 1):
            ins = c["insights"]
            v = ins.get("views", 0)
            fire = " " + E("fire", 11) if v >= avg*2 else ""
            typ = {"REELS": "Reels", "FEED": "Пост"}.get(c.get("media_product_type"), "Пост")
            link = ""
            if c.get("permalink"):
                link = (f'  <a href="{c["permalink"]}">'
                        f'<font color="#4A8B00"><b>Открыть →</b></font></a>')
            head = (f'<b>{i}. {typ}</b>  {_f(v)} просм · '
                    f'{_f(ins.get("likes"))} лайк · {_f(ins.get("saved"))} сохр{fire}{link}')
            cap = _clean((c.get("caption") or "").replace("\n", " "))[:72]
            block = [Paragraph(head, ST_BODY)]
            if cap:
                block.append(Paragraph(f"«{_esc(cap)}»", ST_CAP))
            D.append(KeepTogether(block))
            D.append(Spacer(1, 3))

    stories = data.get("stories", [])
    D.append(Paragraph(E("camera") + "Сторис", ST_H2))
    if not stories:
        D.append(Paragraph("Данных за период нет (база копится ежедневно).", ST_BODY))
    else:
        def _s(k):
            return sum((x.get("insights", {}).get(k) or 0) for x in stories)
        n = len(stories)
        views = _s("views")
        D.append(Paragraph(f'{E("memo")}Сторис за период: <b>{n}</b>', ST_BODY))
        D.append(Paragraph(
            f'{E("eye")}Просмотры <b>{_f(views)}</b> (ср. {_f(round(views/n))}) · '
            f'{E("target")}охват {_f(_s("reach"))}', ST_BODY))
        D.append(Paragraph(
            f'{E("person")}Визиты профиля <b>{_f(_s("profile_visits"))}</b> · '
            f'{E("plus")}подписки <b>{_f(_s("follows"))}</b> · ответы {_f(_s("replies"))} · '
            f'репосты {_f(_s("shares"))}', ST_BODY))
        nav = icc.stories_nav_agg(stories)
        if nav.get("retention_pct") is not None:
            rc = "#2e9e00" if nav['retention_pct'] >= 90 else (
                "#d97706" if nav['retention_pct'] >= 80 else "#dc2626")
            D.append(Paragraph(
                f'{E("lock")}Удержание <font color="{rc}"><b>{nav["retention_pct"]}%</b></font>'
                f' · навигация: вперёд {_f(nav["tap_forward"])}, назад {_f(nav["tap_back"])}, '
                f'закрыли {_f(nav["tap_exit"])}, ушли к др. {_f(nav["swipe_forward"])}',
                ST_BODY))
        enr = icc.enrich_stories(stories)
        top = sorted(enr, key=lambda s: (s.get("insights", {}).get("views") or 0),
                     reverse=True)[:6]
        D.append(Spacer(1, 4))
        D.append(Paragraph(E("trophy", 11) + "Топ сторис — по просмотрам", ST_CAP))
        D.append(_stories_table(_story_rows(top), W))
        weak = sorted([s for s in enr if s.get("retention_pct") is not None
                       and s["retention_pct"] < 80
                       and (s.get("insights", {}).get("views") or 0) >= 300],
                      key=lambda s: s["retention_pct"])[:3]
        if weak:
            D.append(Spacer(1, 4))
            D.append(Paragraph(E("warn", 11) + "Слабое удержание (ниже 80%)", ST_CAP))
            D.append(_stories_table(_story_rows(weak), W))
        D.append(Spacer(1, 3))
        if sheet_url:
            D.append(Paragraph(
                f'{E("chart",11)}Вся статистика сторис: '
                f'<a href="{sheet_url}"><font color="#4A8B00"><b>Google-таблица →</b>'
                f'</font></a>', ST_CAP))
        D.append(Paragraph(
            "ID сторис = дата #номер за день. Найти: Instagram → Архив → тот день. "
            "Удержание: 90%+ отлично, 80–90 норма, ниже 80 слабо.", ST_CAP))

    cmp = icc.compare(data.get("content", []), stories)
    D.append(Paragraph(E("chart") + "Сравнение типов контента", ST_H2))
    lab = {"REELS": "Reels", "POSTS": "Посты", "STORIES": "Сторис"}
    crows = [[Paragraph(x, ST_TH) for x in ("Тип", "Кол-во", "Ср. просмотры", "Всего")]]
    for t in ("REELS", "POSTS", "STORIES"):
        aobj = cmp.get(t, {})
        crows.append([Paragraph(lab[t], ST_TD), Paragraph(str(aobj.get("count", 0)), ST_TDR),
                      Paragraph(_f(aobj.get("views_avg", 0)), ST_TDR),
                      Paragraph(_f(aobj.get("views_sum", 0)), ST_TDR)])
    ct = Table(crows, colWidths=[W*0.28, W*0.18, W*0.30, W*0.24])
    cstyle = [("BACKGROUND", (0, 0), (-1, 0), LIME),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
              ("LEFTPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE)]
    for i in range(1, len(crows)):
        if i % 2 == 0:
            cstyle.append(("BACKGROUND", (0, i), (-1, i), BAND))
    ct.setStyle(TableStyle(cstyle))
    D.append(ct)

    if ai_text:
        D.append(Paragraph(E("robot") + "Вывод недели (AI)", ST_H2))
        for para in ai_text.split("\n"):
            para = para.strip()
            if para:
                D.append(Paragraph(_esc(para), ST_AI))

    doc.build(D)
    return buf.getvalue()


# ────────── общие блоки (для месячных и Threads) ──────────

def _new_doc(title, band_html):
    buf = io.BytesIO()
    PW, PH = 430, 880
    doc = SimpleDocTemplate(buf, pagesize=(PW, PH), leftMargin=26, rightMargin=26,
                            topMargin=24, bottomMargin=26, title=title)
    W = PW - 52
    D = [_title_band(band_html, W)]
    return buf, doc, W, D


def _content_block(content, title, limit, W):
    out = []
    content = [c for c in content if c.get("insights", {}).get("views")]
    if not content:
        return out
    content.sort(key=lambda c: c["insights"]["views"], reverse=True)
    avg = sum(c["insights"]["views"] for c in content) / len(content)
    out.append(Paragraph(E("memo") + f"{title} · {len(content)} публ.", ST_H2))
    for i, c in enumerate(content[:limit], 1):
        ins = c["insights"]
        v = ins.get("views", 0)
        fire = " " + E("fire", 11) if v >= avg*2 else ""
        typ = {"REELS": "Reels", "FEED": "Пост"}.get(c.get("media_product_type"), "Пост")
        link = (f'  <a href="{c["permalink"]}"><font color="#4A8B00"><b>Открыть →</b>'
                f'</font></a>') if c.get("permalink") else ""
        head = (f'<b>{i}. {typ}</b>  {_f(v)} просм · {_f(ins.get("likes"))} лайк · '
                f'{_f(ins.get("saved"))} сохр{fire}{link}')
        cap = _clean((c.get("caption") or "").replace("\n", " "))[:72]
        block = [Paragraph(head, ST_BODY)]
        if cap:
            block.append(Paragraph(f"«{_esc(cap)}»", ST_CAP))
        out.append(KeepTogether(block))
        out.append(Spacer(1, 3))
    return out


def _stories_block(stories, W, sheet_url=""):
    out = [Paragraph(E("camera") + "Сторис", ST_H2)]
    if not stories:
        out.append(Paragraph("Данных за период нет (база копится ежедневно).", ST_BODY))
        return out

    def _s(k):
        return sum((x.get("insights", {}).get(k) or 0) for x in stories)
    n = len(stories)
    views = _s("views")
    out.append(Paragraph(f'{E("memo")}Сторис за период: <b>{n}</b>', ST_BODY))
    out.append(Paragraph(
        f'{E("eye")}Просмотры <b>{_f(views)}</b> (ср. {_f(round(views/n))}) · '
        f'{E("target")}охват {_f(_s("reach"))}', ST_BODY))
    out.append(Paragraph(
        f'{E("person")}Визиты профиля <b>{_f(_s("profile_visits"))}</b> · '
        f'{E("plus")}подписки <b>{_f(_s("follows"))}</b> · '
        f'ответы {_f(_s("replies"))} · репосты {_f(_s("shares"))}', ST_BODY))
    nav = icc.stories_nav_agg(stories)
    if nav.get("retention_pct") is not None:
        rc = "#2e9e00" if nav['retention_pct'] >= 90 else (
            "#d97706" if nav['retention_pct'] >= 80 else "#dc2626")
        out.append(Paragraph(
            f'{E("lock")}Удержание <font color="{rc}"><b>{nav["retention_pct"]}%</b></font>'
            f' · {E("compass")}навигация: вперёд {_f(nav["tap_forward"])}, '
            f'назад {_f(nav["tap_back"])}, закрыли {_f(nav["tap_exit"])}, '
            f'ушли к др. {_f(nav["swipe_forward"])}', ST_BODY))
    enr = icc.enrich_stories(stories)
    top = sorted(enr, key=lambda s: (s.get("insights", {}).get("views") or 0),
                 reverse=True)[:6]
    out.append(Spacer(1, 4))
    out.append(Paragraph(E("trophy", 11) + "Топ сторис — по просмотрам", ST_CAP))
    out.append(_stories_table(_story_rows(top), W))
    weak = sorted([s for s in enr if s.get("retention_pct") is not None
                   and s["retention_pct"] < 80
                   and (s.get("insights", {}).get("views") or 0) >= 300],
                  key=lambda s: s["retention_pct"])[:3]
    if weak:
        out.append(Spacer(1, 4))
        out.append(Paragraph(E("warn", 11) + "Слабое удержание (ниже 80%)", ST_CAP))
        out.append(_stories_table(_story_rows(weak), W))
    out.append(Spacer(1, 3))
    if sheet_url:
        out.append(Paragraph(
            f'{E("chart",11)}Вся статистика сторис: '
            f'<a href="{sheet_url}"><font color="#4A8B00"><b>Google-таблица →</b></font></a>',
            ST_CAP))
    out.append(Paragraph(
        "ID сторис = дата #номер за день. Найти: Instagram → Архив → тот день. "
        "Удержание: 90%+ отлично, 80–90 норма, ниже 80 слабо.", ST_CAP))
    return out


def _compare_block(content, stories, W):
    cmp = icc.compare(content, stories)
    out = [Paragraph(E("chart") + "Сравнение типов контента", ST_H2)]
    lab = {"REELS": "Reels", "POSTS": "Посты", "STORIES": "Сторис"}
    crows = [[Paragraph(x, ST_TH) for x in ("Тип", "Кол-во", "Ср. просмотры", "Всего")]]
    for t in ("REELS", "POSTS", "STORIES"):
        a = cmp.get(t, {})
        crows.append([Paragraph(lab[t], ST_TD), Paragraph(str(a.get("count", 0)), ST_TDR),
                      Paragraph(_f(a.get("views_avg", 0)), ST_TDR),
                      Paragraph(_f(a.get("views_sum", 0)), ST_TDR)])
    ct = Table(crows, colWidths=[W*0.28, W*0.18, W*0.30, W*0.24])
    cstyle = [("BACKGROUND", (0, 0), (-1, 0), LIME),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
              ("LEFTPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE)]
    for i in range(1, len(crows)):
        if i % 2 == 0:
            cstyle.append(("BACKGROUND", (0, i), (-1, i), BAND))
    ct.setStyle(TableStyle(cstyle))
    out.append(ct)
    return out


def _ai_block(ai_text, heading):
    out = [Paragraph(E("robot") + heading, ST_H2)]
    for para in ai_text.split("\n"):
        para = para.strip()
        if para:
            out.append(Paragraph(_esc(para), ST_AI))
    return out


def _threads_posts_block(posts, W, title):
    posts = [p for p in posts if p.get("insights", {}).get("views")]
    out = [Paragraph(E("memo") + title, ST_H2)]
    if not posts:
        out.append(Paragraph("Постов с инсайтами не найдено.", ST_BODY))
        return out
    posts.sort(key=lambda p: p["insights"]["views"], reverse=True)
    avg = sum(p["insights"]["views"] for p in posts) / len(posts)
    for i, p in enumerate(posts[:10], 1):
        ins = p["insights"]
        v = ins.get("views", 0)
        fire = " " + E("fire", 11) if v >= avg*2 else ""
        link = (f'  <a href="{p["permalink"]}"><font color="#4A8B00"><b>Открыть →</b>'
                f'</font></a>') if p.get("permalink") else ""
        head = (f'<b>{i}.</b> {_f(v)} просм · {_f(ins.get("likes"))} лайк · '
                f'{_f(ins.get("replies"))} отв · {_f(ins.get("reposts"))} реп{fire}{link}')
        cap = _clean((p.get("text") or "").replace("\n", " "))[:72]
        block = [Paragraph(head, ST_BODY)]
        if cap:
            block.append(Paragraph(f"«{_esc(cap)}»", ST_CAP))
        out.append(KeepTogether(block))
        out.append(Spacer(1, 3))
    return out


def _grade_color(g):
    return "#2e9e00" if g >= 8 else ("#d97706" if g >= 6 else "#dc2626")


def _score_block(score, W):
    out = [Paragraph(E("trophy") + "Оценка работы SMM", ST_H2)]
    g = score["grade"]
    gc = _grade_color(g)
    box = Table([[Paragraph(f'<font color="{gc}" size="22"><b>{g}</b></font>'
                            f'<font size="12"> / 10</font>', ST_BODY),
                  Paragraph(f'{score["total"]} из 100 баллов по рубрике', ST_SUB)]],
                colWidths=[W*0.34, W*0.66])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BAND),
                             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("TOPPADDING", (0, 0), (-1, -1), 8),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                             ("LEFTPADDING", (0, 0), (-1, -1), 12)]))
    out.append(box)
    out.append(Spacer(1, 4))
    rows = [[Paragraph(x, ST_TH) for x in ("Критерий", "Балл", "Комментарий")]]
    for it in score["items"]:
        got = "н/д" if it["got"] is None else f'{it["got"]}/{it["max"]}'
        rows.append([Paragraph(it["name"], ST_TD), Paragraph(got, ST_TDR),
                     Paragraph(it["note"], ST_TD)])
    t = Table(rows, colWidths=[W*0.33, W*0.15, W*0.52])
    style = [("BACKGROUND", (0, 0), (-1, 0), LIME),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
             ("VALIGN", (0, 0), (-1, -1), "TOP")]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))
    t.setStyle(TableStyle(style))
    out.append(t)
    return out


def _planfact_block(pf, W):
    out = [Paragraph(E("memo") + "План vs Факт (норматив недели)", ST_H2)]
    rows = [[Paragraph(x, ST_TH) for x in ("Показатель", "План", "Факт", "")]]
    for r in pf:
        mark = ('<font color="#2e9e00"><b>✓</b></font>' if r["ok"]
                else '<font color="#dc2626"><b>✗</b></font>')
        rows.append([Paragraph(r["name"], ST_TD), Paragraph(str(r["plan"]), ST_TDR),
                     Paragraph(str(r["fact"]), ST_TDR), Paragraph(mark, ST_TDR)])
    t = Table(rows, colWidths=[W*0.54, W*0.16, W*0.16, W*0.14])
    style = [("BACKGROUND", (0, 0), (-1, 0), LIME),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE)]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))
    t.setStyle(TableStyle(style))
    out.append(t)
    return out


def _audience_table(rows, W):
    t = Table(rows, colWidths=[W*0.56, W*0.44])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def ig_monthly_pdf(data, ai_text: str = "", sheet_url: str = "", score=None,
                   planfact=None) -> bytes:
    prof = data.get("profile", {})
    tm, tp = data.get("totals_month", {}), data.get("totals_prev", {})
    mon = data["month"]
    buf, doc, W, D = _new_doc(
        f"IG месячный {mon['name']} {mon['year']}",
        f'{E("camera",15,-3)}<b>INSTAGRAM</b>  ·  Месяц №{mon["month"]:02d} · '
        f'{mon["name"].capitalize()} {mon["year"]}')
    D.append(Spacer(1, 4))
    D.append(Paragraph(f"@{prof.get('username','gotrips_by')} · в сравнении с "
                       f"{data['prev_month']['name']}", ST_SUB))
    if score:
        D += _score_block(score, W)
    if planfact:
        D += _planfact_block(planfact, W)

    D.append(Paragraph(E("people") + "Аудитория", ST_H2))
    arows = [[Paragraph("Подписчики", ST_LBL),
              Paragraph(f"<b>{_f(prof.get('followers_count'))}</b>", ST_VAL)]]
    fg, fgp = data.get("follower_growth_month"), data.get("follower_growth_prev")
    if fg is not None:
        arows.append([Paragraph("Прирост за месяц", ST_LBL),
                      Paragraph(f"<b>+{_f(fg)}</b>{_trend(fg, fgp)}", ST_VAL)])
    arows.append([Paragraph("Публикаций (рилс+посты)", ST_LBL),
                  Paragraph(f"<b>{data.get('posts_count', 0)}</b>", ST_VAL)])
    D.append(_audience_table(arows, W))

    D.append(Paragraph(E("chart") + "Охват и просмотры", ST_H2))
    D.append(_metric_table([("Просмотры", "views"), ("Охват", "reach"),
                            ("Просмотры профиля", "profile_views"),
                            ("Вовлечено аккаунтов", "accounts_engaged")], tm, tp, W))
    D.append(Paragraph(E("heart") + "Вовлечённость", ST_H2))
    D.append(_metric_table([("Лайки", "likes"), ("Комментарии", "comments"),
                            ("Сохранения", "saves"), ("Репосты", "shares")], tm, tp, W))
    D += _content_block(data.get("content", []), "Топ публикаций месяца", 10, W)
    D += _stories_block(data.get("stories", []), W, sheet_url)
    D += _compare_block(data.get("content", []), data.get("stories", []), W)
    if ai_text:
        D += _ai_block(ai_text, "Оценка и рекомендации (AI)")
    doc.build(D)
    return buf.getvalue()


def _threads_audience(data, growth_key):
    rows = [[Paragraph("Подписчики", ST_LBL),
             Paragraph(f"<b>{_f(data.get('followers_count'))}</b>", ST_VAL)]]
    fg = data.get(growth_key)
    fgp = data.get("follower_growth_prev")
    if fg is not None:
        rows.append([Paragraph("Прирост за период", ST_LBL),
                     Paragraph(f"<b>+{_f(fg)}</b>{_trend(fg, fgp)}", ST_VAL)])
    return rows


def _threads_activity(tw, tp, W):
    pairs = [("Просмотры", "views"), ("Лайки", "likes"), ("Ответы", "replies"),
             ("Репосты", "reposts"), ("Цитирования", "quotes")]
    if tw.get("clicks") is not None:
        pairs.append(("Клики", "clicks"))
    return _metric_table(pairs, tw, tp, W)


def threads_weekly_pdf(data, ai_text: str = "", score=None, planfact=None) -> bytes:
    prof = data.get("profile", {})
    tw, tp = data.get("totals_week", {}), data.get("totals_prev", {})
    a = dt.date.fromisoformat(data["week"]["since"])
    b = dt.date.fromisoformat(data["week"]["until"])
    iso_y, iso_w, _ = b.isocalendar()
    period = f"{a.strftime('%d.%m')}–{b.strftime('%d.%m')}"
    buf, doc, W, D = _new_doc(
        f"Threads недельный №{iso_w} · {iso_y}",
        f'{E("thread",15,-3)}<b>THREADS</b>  ·  Неделя №{iso_w} · {iso_y}')
    D.append(Spacer(1, 4))
    D.append(Paragraph(f"@{prof.get('username','gotrips_by')} · {period} · "
                       f"в сравнении с прошлой неделей", ST_SUB))
    if score:
        D += _score_block(score, W)
    if planfact:
        D += _planfact_block(planfact, W)
    D.append(Paragraph(E("people") + "Аудитория", ST_H2))
    D.append(_audience_table(_threads_audience(data, "follower_growth_week"), W))
    D.append(Paragraph(E("chart") + "Активность", ST_H2))
    D.append(_threads_activity(tw, tp, W))
    D += _threads_posts_block(data.get("posts", []), W, "Топ постов недели")
    if ai_text:
        D += _ai_block(ai_text, "Вывод недели (AI)")
    doc.build(D)
    return buf.getvalue()


def threads_monthly_pdf(data, ai_text: str = "", score=None, planfact=None) -> bytes:
    prof = data.get("profile", {})
    tm, tp = data.get("totals_month", {}), data.get("totals_prev", {})
    mon = data["month"]
    buf, doc, W, D = _new_doc(
        f"Threads месячный {mon['name']} {mon['year']}",
        f'{E("thread",15,-3)}<b>THREADS</b>  ·  Месяц №{mon["month"]:02d} · '
        f'{mon["name"].capitalize()} {mon["year"]}')
    D.append(Spacer(1, 4))
    D.append(Paragraph(f"@{prof.get('username','gotrips_by')} · в сравнении с "
                       f"{data['prev_month']['name']}", ST_SUB))
    if score:
        D += _score_block(score, W)
    if planfact:
        D += _planfact_block(planfact, W)
    D.append(Paragraph(E("people") + "Аудитория", ST_H2))
    arows = _threads_audience(data, "follower_growth_month")
    arows.append([Paragraph("Постов за месяц", ST_LBL),
                  Paragraph(f"<b>{data.get('posts_count', 0)}</b>", ST_VAL)])
    D.append(_audience_table(arows, W))
    D.append(Paragraph(E("chart") + "Активность", ST_H2))
    D.append(_threads_activity(tm, tp, W))
    D += _threads_posts_block(data.get("posts", []), W, "Топ постов месяца")
    if ai_text:
        D += _ai_block(ai_text, "Оценка и рекомендации (AI)")
    doc.build(D)
    return buf.getvalue()
