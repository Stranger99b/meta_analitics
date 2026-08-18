"""Ресерч-плейбук роста для SMM: контент-стратегия GoTrips (Instagram + Threads,
автобусные/групповые туры). Фирменный PDF на стилях report_pdf.

Материал: реальные данные аккаунта (наша аналитика) + тренды travel-SMM 2026 +
специфика групповых туров. Запуск: python3 scripts/research_pdf.py — соберёт PDF
и (если задан PERSONAL_TG_CHAT_ID) отправит в личный чат на проверку.
"""
import io
import os
import sys

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

sys.path.insert(0, os.path.dirname(__file__))
import report_pdf as R  # noqa: E402  (переиспользуем стили/цвета/emoji)


def _h2(t):
    return Paragraph(t, R.ST_H2)


def _p(t):
    return Paragraph(t, R.ST_BODY)


def _cap(t):
    return Paragraph(t, R.ST_CAP)


def _b(items):
    """Список буллетов."""
    return [Paragraph(f"•  {t}", R.ST_BODY) for t in items]


def _diagnosis_dynamic(data):
    """Диагноз месяца из реальных данных (формат-лидер, динамика, сторис, темы)."""
    import ig_content_compare as icc
    cmp = icc.compare(data.get("content", []), data.get("stories", []))
    lab = {"REELS": "Reels", "POSTS": "Посты", "STORIES": "Сторис"}
    best = max(("REELS", "POSTS", "STORIES"),
               key=lambda t: cmp.get(t, {}).get("views_avg", 0))
    tm, tp = data.get("totals_month", {}), data.get("totals_prev", {})
    inter = tm.get("total_interactions") or sum((tm.get(k) or 0)
            for k in ("likes", "comments", "saves", "shares"))
    inter_p = tp.get("total_interactions") or sum((tp.get(k) or 0)
              for k in ("likes", "comments", "saves", "shares"))
    bl = [
        f"<b>Формат-лидер:</b> {lab[best]} — ср. {R._f(cmp[best]['views_avg'])} просмотров "
        f"(Reels {R._f(cmp['REELS']['views_avg'])}, Посты {R._f(cmp['POSTS']['views_avg'])}"
        + (f", Сторис {R._f(cmp['STORIES']['views_avg'])}" if cmp['STORIES']['count'] else "")
        + "). Делайте упор на то, что заходит.",
        f"<b>Динамика к прошлому месяцу:</b> охват {R._f(tm.get('reach'))}"
        f"{R._trend(tm.get('reach'), tp.get('reach'))}, просмотры"
        f"{R._trend(tm.get('views'), tp.get('views'))}, вовлечённость"
        f"{R._trend(inter, inter_p)}.",
    ]
    stories = data.get("stories", [])
    if stories:
        nav = icc.stories_nav_agg(stories)
        bl.append(f"<b>Сторис:</b> удержание {nav.get('retention_pct')}%, "
                  f"подписки со сторис {nav.get('tap_forward') is not None and '' or ''}"
                  f"{sum((s.get('insights',{}).get('follows') or 0) for s in stories)}.")
    fg, fgp = data.get("follower_growth_month"), data.get("follower_growth_prev")
    if fg is not None:
        bl.append(f"<b>Подписчики:</b> +{R._f(fg)} за месяц{R._trend(fg, fgp)}.")
    content = [c for c in data.get("content", []) if c.get("insights", {}).get("views")]
    content.sort(key=lambda c: c["insights"]["views"], reverse=True)
    if content:
        themes = "; ".join(f"«{R._clean((c.get('caption') or '')[:38])}»"
                           for c in content[:3])
        bl.append(f"<b>Что зашло (топ-темы):</b> {themes}.")
    return [_h2(R.E("chart") + "Диагноз месяца (по вашим данным)")] + _b(bl)


def _kpi_suggestions(data):
    import ig_content_compare as icc
    import smm_score
    cmp = icc.compare(data.get("content", []), data.get("stories", []))
    r = cmp.get("REELS", {}).get("views_avg", 0)
    p = cmp.get("POSTS", {}).get("views_avg", 0)
    sug = []
    if p > r * 1.3 and p:
        sug.append("Посты/карусели заходят заметно лучше Reels — рассмотрите +1 карусель/нед; "
                   "Reels пока держите 2, но усильте хуками.")
    elif r > p * 1.3 and r:
        sug.append("Reels обгоняют посты по просмотрам — можно поднять норму Reels до 3/нед.")
    pf = smm_score.plan_vs_fact(data)
    missed = [x["name"] for x in pf if not x["ok"]]
    if missed:
        sug.append("В прошлом месяце недобрано по: " + ", ".join(missed) +
                   " — подтянуть до нормы.")
    tm, tp = data.get("totals_month", {}), data.get("totals_prev", {})
    if (tm.get("saves") or 0) < (tp.get("saves") or 0):
        sug.append("Сохранения снижаются — добавьте сохраняемый контент (гайды, чек-листы, "
                   "маршруты) с призывом «сохрани».")
    if not sug:
        sug.append("Показатели сбалансированы — держите текущий норматив KPI.")
    return [_h2(R.E("memo") + "Предложения по KPI (решение за вами)")] + _b(sug)


def build(data=None, ai_focus: str = "") -> bytes:
    buf = io.BytesIO()
    PW, PH = 430, 880
    if data:
        mon = data["month"]
        title = f"GoTrips — план на месяц {mon['name']} {mon['year']}"
        band = (f'{R.E("rocket",15,-3)}<b>ПЛАН SMM НА МЕСЯЦ</b>  ·  '
                f'{mon["name"].capitalize()} {mon["year"]}')
        sub = (f"План и KPI для SMM-менеджера · @gotrips_by · обновлён по данным месяца · "
               f"автобусные и групповые туры")
    else:
        title = "GoTrips — стратегия роста SMM"
        band = f'{R.E("rocket",15,-3)}<b>СТРАТЕГИЯ РОСТА</b>  ·  Instagram + Threads'
        sub = ("Плейбук для SMM-менеджера · автобусные и групповые туры · "
               "на основе данных аккаунта @gotrips_by и трендов 2026")
    doc = SimpleDocTemplate(buf, pagesize=(PW, PH), leftMargin=26, rightMargin=26,
                            topMargin=24, bottomMargin=26, title=title)
    W = PW - 52
    D = [R._title_band(band, W)]
    D.append(Spacer(1, 4))
    D.append(_cap(sub))

    # 0. Норматив KPI (что делать каждую неделю)
    D.append(_h2(R.E("trophy") + "Норматив недели (KPI) — за это начисляется балл"))
    kpi = [[Paragraph(x, R.ST_TH) for x in ("Что", "Норма/нед", "Зачем")]]
    for row in [
        ("Reels", "2", "охват, новые подписчики"),
        ("Карусели", "1", "сохранения, планирование"),
        ("Посты", "1", "вовлечённость, бренд"),
        ("Сторис", "ежедневно (6/7 дней)", "воронка, конверсия"),
        ("Threads", "3–4", "доп. охват, обсуждение"),
    ]:
        kpi.append([Paragraph(row[0], R.ST_TD), Paragraph(row[1], R.ST_TDR),
                    Paragraph(row[2], R.ST_TD)])
    kt = Table(kpi, colWidths=[W*0.24, W*0.32, W*0.44])
    ks = [("BACKGROUND", (0, 0), (-1, 0), R.LIME),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.3, R.LINE)]
    for i in range(1, len(kpi)):
        if i % 2 == 0:
            ks.append(("BACKGROUND", (0, i), (-1, i), R.BAND))
    kt.setStyle(TableStyle(ks))
    D.append(kt)
    D.append(_cap("Плюс качество: ER ≥ 1.5%, удержание сторис ≥ 80%, минимум 1 «залёт» "
                  "(≥2× среднего) в месяц. Выполнение норматива ловится в дайджесте "
                  "блоком «План vs Факт» и влияет на балл SMM."))

    # 1. Диагноз — динамический (из данных) или статический-пример
    if data:
        D += _diagnosis_dynamic(data)
        D += _kpi_suggestions(data)
        if ai_focus:
            D.append(_h2(R.E("rocket") + "Фокус на следующий месяц"))
            for para in ai_focus.split("\n"):
                if para.strip():
                    D.append(_p(R._esc(para.strip())))
    else:
        D.append(_h2(R.E("chart") + "1. Диагноз аккаунта (пример по июлю)"))
        D += _b([
            "<b>Сильная сторона — посты и карусели.</b> Посты собирают в среднем "
            "~50 000 просмотров против ~29 000 у Reels. Значит посты/карусели резонируют.",
            "<b>Заходит эмоция и локальный юмор</b> — сезонные посты и ирония про направления.",
            "<b>Сторис — отличное удержание (~92%), но слабая конверсия</b> в профиль/подписки.",
            "<b>Падает вовлечённость</b> — сохранения/репосты снижаются. Репосты (DM) — сигнал №1.",
            "<b>Reels — точка роста</b>: не хватает хука в первые 3 секунды и трендового звука.",
        ])

    # 2. Главный вывод — микс
    D.append(_h2(R.E("trophy") + "2. Главный вывод: правильный микс контента"))
    D.append(_p("Разным форматам — разные задачи. Зрелая стратегия 2026 использует всё, "
                "но осознанно:"))
    mix = [[Paragraph(x, R.ST_TH) for x in ("Формат", "Роль", "В неделю")]]
    for row in [
        ("Reels", "Охват, новые подписчики", "2–3"),
        ("Карусели", "Сохранения, планирование", "1–2"),
        ("Пост/эмоция", "Вовлечённость, бренд", "1–2"),
        ("Сторис", "Воронка, конверсия", "ежедневно"),
        ("Threads", "Доп. охват, обсуждение", "3–4"),
    ]:
        mix.append([Paragraph(row[0], R.ST_TD), Paragraph(row[1], R.ST_TD),
                    Paragraph(row[2], R.ST_TDR)])
    mt = Table(mix, colWidths=[W*0.26, W*0.54, W*0.20])
    st = [("BACKGROUND", (0, 0), (-1, 0), R.LIME),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.3, R.LINE)]
    for i in range(1, len(mix)):
        if i % 2 == 0:
            st.append(("BACKGROUND", (0, i), (-1, i), R.BAND))
    mt.setStyle(TableStyle(st))
    D.append(mt)
    D.append(_cap("Карусели в 2026 — двигатель вовлечённости (до +114% взаимодействий, "
                  "лучшие сохранения в сезон планирования). Reels — двигатель охвата и новых "
                  "подписчиков. Ваши посты/карусели уже сильны — усильте Reels."))

    # 3. Что делать больше
    D.append(_h2(R.E("fire") + "3. Что делать БОЛЬШЕ (по приоритету)"))
    D += _b([
        "<b>Карусели-гайды и маршруты</b> — «Маршрут тура по Дагестану за 7 дней», "
        "«Что взять в автобусный тур», «5 направлений на осень». Их сохраняют и "
        "пересылают тем, с кем планируют поездку. Начинайте с сильного текстового слайда.",
        "<b>Reels с хуком и трендовым звуком</b> — короткие, «живые», не заскриптованные. "
        "Первые 3 секунды — конфликт/удивление/вопрос (примеры в разделе 7).",
        "<b>Отзывы и UGC (контент туристов)</b> — видео и фото реальных клиентов из поездок. "
        "Доверие продаёт групповые туры лучше глянца.",
        "<b>«Неглянцевая» закулиса</b> — сборы группы, дорога, гид, бытовые моменты "
        "(даже 14-часовой переезд). Аутентичность = доверие = аудитория.",
        "<b>Эмоция и сезон</b> — ваша сильная сторона, продолжайте: привязка к датам, "
        "праздникам, настроению, локальный юмор про направления.",
    ])

    # 4. Контент-пиллары
    D.append(_h2(R.E("memo") + "4. Контент-пиллары (рубрики) для авто-туров"))
    D += _b([
        "<b>Направления</b> — атмосферные ролики/карусели по турам (Дагестан, Абхазия, "
        "Грузия, Мурманск, Карелия).",
        "<b>Полезное/планирование</b> — гайды, чек-листы, «что взять», FAQ по автобусным турам.",
        "<b>Люди и эмоции</b> — отзывы, истории туристов, момент встречи группы, юмор.",
        "<b>Закулисье</b> — как готовим тур, гид, дорога, кухня в поездке.",
        "<b>Оффер/сроки</b> — ближайшие даты выездов, места «горят», раннее бронирование "
        "(мягко, не в каждом посте).",
    ])

    # 5. Reels
    D.append(_h2(R.E("film") + "5. Reels: как починить (ваша точка роста)"))
    D += _b([
        "Хук в первые 3 секунды — иначе пролистнут. Не «Дагестан — красивое место», "
        "а «Не едьте в Дагестан, если…» или «3 ошибки в автобусном туре».",
        "Трендовый звук + короткие динамичные склейки. Ролики «живые», не рекламные.",
        "Одна мысль на ролик. Длинные описательные Reels проигрывают коротким «залипательным».",
        "Цель — <b>репосты в директ</b>: делайте контент, которым захочется поделиться с "
        "попутчиком («отправь тому, с кем поедешь»). DM-шеры весят в 3–5× больше лайков.",
    ])

    # 6. Карусели
    D.append(_h2(R.E("bookmark") + "6. Карусели: двигатель сохранений"))
    D += _b([
        "1-й слайд — крупный текст-обещание («Маршрут по Абхазии на 5 дней»).",
        "Дальше — история/маршрут по шагам, 6–10 слайдов, последний — призыв "
        "(«Сохрани, чтобы не потерять» / «Напиши “даты” в директ»).",
        "Гайды и маршруты собирают максимум сохранений в сезон планирования поездок.",
    ])

    # 7. Хуки
    D.append(_h2(R.E("fire") + "7. Хуки под тур-нишу (первые 3 секунды)"))
    D += _b([
        "«Не бронируйте автобусный тур, пока не посмотрите это»",
        "«3 ошибки, из-за которых поездка в горы превращается в кошмар»",
        "«Что реально происходит в 14-часовом переезде (без прикрас)»",
        "«Куда поехать осенью, если бюджет ограничен, а хочется вау»",
        "«Абхазия за 5 дней: маршрут, который сохранят все»",
        "«Признаки, что тебе пора в тур с GoTrips»",
    ])

    # 8. Сторис-воронка
    D.append(_h2(R.E("camera") + "8. Сторис: превратить удержание в клиентов"))
    D += _b([
        "У вас люди досматривают сторис (~92%) — используйте это для действий.",
        "Стикеры: опрос/викторина (вовлечение), обратный отсчёт до старта продаж, "
        "стикер-ссылка на бронь/направление.",
        "Явный призыв: «Свайп — забронировать», «Напиши “Дагестан” в директ».",
        "Серии: «День из тура», отзывы туристов, закулисье сборов группы.",
    ])

    # 9. Threads
    D.append(_h2(R.E("thread") + "9. Threads: что постить"))
    D += _b([
        "Короткие истории и наблюдения из туров, вопросы аудитории («Горы или море?»).",
        "Треды-подборки: «5 недооценённых направлений», «мифы об автобусных турах».",
        "Живой, разговорный тон — Threads любит обсуждение, а не рекламу. 3–4 поста/нед.",
    ])

    # 10. Метрики
    D.append(_h2(R.E("chart") + "10. За чем следить (метрики успеха)"))
    D += _b([
        "<b>Репосты и сохранения</b> — главные сигналы алгоритма и намерения. Ростите их.",
        "<b>Досмотры и удержание Reels</b> — качество хука и монтажа.",
        "<b>Визиты профиля и подписки со сторис</b> — работает ли воронка.",
        "<b>Оценка SMM в дайджестах</b> — интегральный балл по неделям/месяцам (уже в отчётах).",
    ])

    # 11. План на 2 недели
    D.append(_h2(R.E("calendar") + "11. Пример плана на 2 недели"))
    D += _b([
        "<b>Неделя 1:</b> 2 Reels (хук+тренд), 1 карусель-маршрут, 1 пост-эмоция/сезон, "
        "1 отзыв туриста; сторис ежедневно (опрос + ссылка + обратный отсчёт).",
        "<b>Неделя 2:</b> 3 Reels (в т.ч. закулисье/«неглянец»), 1 карусель-гайд, "
        "1 пост-юмор про направление; сторис ежедневно; 3–4 поста в Threads.",
        "После 2 недель — сверьтесь с дайджестом: что подняло охват/сохранения/репосты, "
        "и усиливайте это.",
    ])

    doc.build(D)
    return buf.getvalue()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    pdf = build()
    out = os.path.join(os.path.dirname(__file__), "..", "reports", "research_growth.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(pdf)
    print(f"[research_pdf] Собран: {out} ({len(pdf)} байт)")
    chat = os.environ.get("PERSONAL_TG_CHAT_ID") or "162610900"
    try:
        from send_telegram import send_bytes
        send_bytes(pdf, "GoTrips_Стратегия_роста_SMM.pdf", chat_id=chat,
                   caption="🚀 Ресерч-плейбук: как расти в Instagram+Threads (автобусные туры) — на ваших данных + тренды 2026")
        print("[research_pdf] Отправлен в личный чат")
    except Exception as e:  # noqa: BLE001
        print(f"[research_pdf] Отправка пропущена: {e}")
