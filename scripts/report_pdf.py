"""IG-отчёт в PDF (reportlab) — красивая вёрстка для чтения на телефоне.

Без emoji (в системе нет цветного emoji-шрифта, reportlab их не рендерит) —
вместо них чистая типографика: цветные заголовки-плашки, таблицы для сторис и
контента, цветные тренды ▲/▼. Кириллица через DejaVuSans. Открывается нативно
на iOS, масштабируется. Возвращает bytes PDF.
"""
import io
import os
import sys
import datetime as dt

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, KeepTogether)

sys.path.insert(0, os.path.dirname(__file__))
import report_format as rf  # noqa: E402
import ig_content_compare as icc  # noqa: E402

_FD = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DV", f"{_FD}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", f"{_FD}/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV",
                              boldItalic="DV-B")

# палитра
PINK = colors.HexColor("#E1306C")
INK = colors.HexColor("#1a1a1a")
MUTE = colors.HexColor("#6b7280")
GREEN = colors.HexColor("#16a34a")
RED = colors.HexColor("#dc2626")
AMBER = colors.HexColor("#d97706")
BAND = colors.HexColor("#f4f4f5")
LINE = colors.HexColor("#e5e7eb")

_f = rf.fmt


def _clean(text: str) -> str:
    """Убирает emoji/пиктограммы, которых нет в DejaVu (иначе квадратики □).

    Оставляет кириллицу, латиницу, цифры, пунктуацию, ▲▼≈«»· и т.п.
    """
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

_ss = ParagraphStyle
ST_SUB = _ss("sub", fontName="DV", fontSize=9.5, textColor=MUTE, leading=13)
ST_H2 = _ss("h2", fontName="DV-B", fontSize=13, textColor=PINK, leading=16,
            spaceBefore=10, spaceAfter=4)
ST_LBL = _ss("lbl", fontName="DV", fontSize=10.5, textColor=INK, leading=14)
ST_VAL = _ss("val", fontName="DV-B", fontSize=10.5, textColor=INK, leading=14,
             alignment=2)
ST_BODY = _ss("body", fontName="DV", fontSize=10.5, textColor=INK, leading=15)
ST_CAP = _ss("cap", fontName="DV", fontSize=9, textColor=MUTE, leading=12)
ST_TH = _ss("th", fontName="DV-B", fontSize=9, textColor=colors.white, leading=11)
ST_TD = _ss("td", fontName="DV", fontSize=9, textColor=INK, leading=11)
ST_TDR = _ss("tdr", fontName="DV", fontSize=9, textColor=INK, leading=11, alignment=2)
ST_AI = _ss("ai", fontName="DV", fontSize=10, textColor=INK, leading=15,
            alignment=TA_LEFT, spaceBefore=2)


def _trend(cur, prev):
    if cur is None or prev in (None, 0):
        return ""
    p = (cur - prev) / prev * 100
    if round(abs(p)) == 0:
        return ' <font color="#6b7280">≈</font>'
    col = "#16a34a" if p >= 0 else "#dc2626"
    ar = "▲" if p >= 0 else "▼"
    return f' <font color="{col}">{ar}{abs(p):.0f}%</font>'


def _metric_table(pairs, tw, tp, width):
    rows = []
    for lbl, k in pairs:
        val = f"<b>{_f(tw.get(k))}</b>{_trend(tw.get(k), tp.get(k))}"
        rows.append([Paragraph(lbl, ST_LBL), Paragraph(val, ST_VAL)])
    t = Table(rows, colWidths=[width * 0.55, width * 0.45])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "DV", 10.5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _ret_color(r):
    if r is None:
        return MUTE
    return GREEN if r >= 90 else (AMBER if r >= 80 else RED)


def _stories_table(rows_data, width):
    header = [Paragraph(h, ST_TH) for h in
              ("Сторис", "Время", "Просм", "Удерж", "Проф", "+Подп")]
    data = [header]
    for r in rows_data:
        data.append([
            Paragraph(r["id"], ST_TD), Paragraph(r["time"], ST_TD),
            Paragraph(_f(r["views"]), ST_TDR),
            Paragraph(r["ret"], ST_TDR),
            Paragraph(_f(r["prof"]), ST_TDR),
            Paragraph(_f(r["foll"]), ST_TDR),
        ])
    w = width
    t = Table(data, colWidths=[w*0.24, w*0.15, w*0.17, w*0.16, w*0.14, w*0.14])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PINK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))
    t.setStyle(TableStyle(style))
    return t


def _story_rows(enr):
    out = []
    for s in enr:
        ins = s.get("insights", {})
        r = s.get("retention_pct")
        if r is None:
            ret = "—"
        else:
            rc = "#16a34a" if r >= 90 else ("#d97706" if r >= 80 else "#dc2626")
            ret = f'<font color="{rc}">{r}%</font>'
        typ = "видео" if s.get("media_type") == "VIDEO" else "фото"
        out.append({
            "id": f"{s['local_date']} #{s['num']}",
            "time": f"{s['local_time']} · {typ}",
            "views": ins.get("views") or 0, "ret": ret,
            "prof": ins.get("profile_visits") or 0,
            "foll": ins.get("follows") or 0,
        })
    return out


def ig_weekly_pdf(data, ai_text: str = "") -> bytes:
    prof = data.get("profile", {})
    tw, tp = data.get("totals_week", {}), data.get("totals_prev", {})
    a = dt.date.fromisoformat(data["week"]["since"])
    b = dt.date.fromisoformat(data["week"]["until"])
    period = f"{a.strftime('%d.%m')}–{b.strftime('%d.%m')}"

    buf = io.BytesIO()
    PW, PH = 430, 880
    doc = SimpleDocTemplate(buf, pagesize=(PW, PH), leftMargin=26, rightMargin=26,
                            topMargin=26, bottomMargin=26, title="IG недельный отчёт")
    W = PW - 52
    E = []

    # шапка-плашка
    title_tbl = Table([[Paragraph(
        '<font color="white" size="15"><b>INSTAGRAM</b></font>'
        '<font color="white" size="11">   недельный дайджест</font>', ST_BODY)]],
        colWidths=[W])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PINK),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    E.append(title_tbl)
    E.append(Spacer(1, 4))
    E.append(Paragraph(f"@{prof.get('username','gotrips_by')} · {period} · "
                       f"в сравнении с прошлой неделей", ST_SUB))

    # Аудитория
    E.append(Paragraph("Аудитория", ST_H2))
    aud = [["Подписчики", "followers_count"]]
    audrows = [[Paragraph("Подписчики", ST_LBL),
                Paragraph(f"<b>{_f(prof.get('followers_count'))}</b>", ST_VAL)]]
    fg, fgp = data.get("follower_growth_week"), data.get("follower_growth_prev")
    if fg is not None:
        audrows.append([Paragraph("Прирост за неделю", ST_LBL),
                        Paragraph(f"<b>+{_f(fg)}</b>{_trend(fg, fgp)}", ST_VAL)])
    at = Table(audrows, colWidths=[W*0.55, W*0.45])
    at.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    E.append(at)

    E.append(Paragraph("Охват и просмотры", ST_H2))
    E.append(_metric_table([("Просмотры", "views"), ("Охват", "reach"),
                            ("Просмотры профиля", "profile_views"),
                            ("Вовлечено аккаунтов", "accounts_engaged")], tw, tp, W))

    E.append(Paragraph("Вовлечённость", ST_H2))
    E.append(_metric_table([("Лайки", "likes"), ("Комментарии", "comments"),
                            ("Сохранения", "saves"), ("Репосты", "shares"),
                            ("Всего взаимодействий", "total_interactions")], tw, tp, W))

    # Контент
    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    if content:
        content.sort(key=lambda c: c["insights"]["views"], reverse=True)
        avg = sum(c["insights"]["views"] for c in content) / len(content)
        E.append(Paragraph(f"Контент недели · {len(content)} публ.", ST_H2))
        for i, c in enumerate(content[:8], 1):
            ins = c["insights"]
            v = ins.get("views", 0)
            fire = ' <font color="#dc2626"><b>ЗАЛЁТ</b></font>' if v >= avg*2 else ""
            typ = {"REELS": "Reels", "FEED": "Пост"}.get(
                c.get("media_product_type"), "Пост")
            head = (f'<b>{i}. {typ}</b>  {_f(v)} просмотров · '
                    f'{_f(ins.get("likes"))} лайк · {_f(ins.get("saved"))} сохр{fire}')
            cap = _clean((c.get("caption") or "").replace("\n", " "))[:72]
            block = [Paragraph(head, ST_BODY)]
            if cap:
                block.append(Paragraph(f"«{cap}»", ST_CAP))
            E.append(KeepTogether(block))
            E.append(Spacer(1, 3))

    # Сторис
    stories = data.get("stories", [])
    E.append(Paragraph("Сторис", ST_H2))
    if not stories:
        E.append(Paragraph("Данных за период нет (база копится ежедневно).", ST_BODY))
    else:
        def _s(k):
            return sum((x.get("insights", {}).get(k) or 0) for x in stories)
        n = len(stories)
        views = _s("views")
        E.append(Paragraph(
            f"Всего <b>{n}</b> · просмотры <b>{_f(views)}</b> (ср. {_f(round(views/n))}) "
            f"· охват {_f(_s('reach'))}", ST_BODY))
        E.append(Paragraph(
            f"Визиты профиля <b>{_f(_s('profile_visits'))}</b> · "
            f"подписки <b>{_f(_s('follows'))}</b> · ответы {_f(_s('replies'))} · "
            f"репосты {_f(_s('shares'))}", ST_BODY))
        nav = icc.stories_nav_agg(stories)
        if nav.get("retention_pct") is not None:
            rc = "#16a34a" if nav['retention_pct'] >= 90 else (
                "#d97706" if nav['retention_pct'] >= 80 else "#dc2626")
            E.append(Paragraph(
                f'Удержание <font color="{rc}"><b>{nav["retention_pct"]}%</b></font> · '
                f'навигация: вперёд {_f(nav["tap_forward"])}, назад {_f(nav["tap_back"])}, '
                f'закрыли {_f(nav["tap_exit"])}, ушли к др. {_f(nav["swipe_forward"])}',
                ST_BODY))
        enr = icc.enrich_stories(stories)
        top = sorted(enr, key=lambda s: (s.get("insights", {}).get("views") or 0),
                     reverse=True)[:6]
        E.append(Spacer(1, 4))
        E.append(Paragraph("Топ сторис — по просмотрам", ST_CAP))
        E.append(_stories_table(_story_rows(top), W))
        with_ret = [s for s in enr if s.get("retention_pct") is not None
                    and (s.get("insights", {}).get("views") or 0) >= 300]
        weak = sorted(with_ret, key=lambda s: s["retention_pct"])[:3]
        if weak and len(with_ret) > 3:
            E.append(Spacer(1, 4))
            E.append(Paragraph("Слабое удержание — что улучшить", ST_CAP))
            E.append(_stories_table(_story_rows(weak), W))
        E.append(Spacer(1, 3))
        E.append(Paragraph(
            "ID сторис = дата #номер за день. Найти: Instagram → Архив → тот день. "
            "Удержание = сколько людей не ушло: 90%+ отлично, 80–90 норма, ниже 80 слабо.",
            ST_CAP))

    # Сравнение типов
    cmp = icc.compare(data.get("content", []), stories)
    E.append(Paragraph("Сравнение типов контента", ST_H2))
    lab = {"REELS": "Reels", "POSTS": "Посты", "STORIES": "Сторис"}
    crows = [[Paragraph(x, ST_TH) for x in ("Тип", "Кол-во", "Ср. просмотры", "Всего")]]
    for t in ("REELS", "POSTS", "STORIES"):
        aobj = cmp.get(t, {})
        crows.append([Paragraph(lab[t], ST_TD),
                      Paragraph(str(aobj.get("count", 0)), ST_TDR),
                      Paragraph(_f(aobj.get("views_avg", 0)), ST_TDR),
                      Paragraph(_f(aobj.get("views_sum", 0)), ST_TDR)])
    ct = Table(crows, colWidths=[W*0.28, W*0.18, W*0.30, W*0.24])
    cstyle = [("BACKGROUND", (0, 0), (-1, 0), PINK),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
              ("LEFTPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE)]
    for i in range(1, len(crows)):
        if i % 2 == 0:
            cstyle.append(("BACKGROUND", (0, i), (-1, i), BAND))
    ct.setStyle(TableStyle(cstyle))
    E.append(ct)

    # AI
    if ai_text:
        E.append(Paragraph("Вывод недели (AI)", ST_H2))
        for para in ai_text.split("\n"):
            para = para.strip()
            if para:
                E.append(Paragraph(para.replace("&", "&amp;").replace("<", "&lt;"), ST_AI))

    doc.build(E)
    return buf.getvalue()
