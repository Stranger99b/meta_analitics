"""Builds weekly Meta Ads report with week-over-week comparison."""

import json
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def _f(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _i(val):
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _pct(val):
    return f"{val:.2f}%"


def _money(val, cur=""):
    s = f"{val:,.2f}"
    return f"{s} {cur}".strip() if cur else s


def _delta(now, prev, invert=False):
    if prev == 0:
        return ""
    d = (now - prev) / prev * 100
    if invert:
        d = -d
    if d > 3:
        return f"↑{d:.1f}%"
    if d < -3:
        return f"↓{abs(d):.1f}%"
    return "→"


def _get_action(actions, *atypes):
    if not actions:
        return 0
    return sum(_i(a.get("value", 0)) for a in actions if a.get("action_type") in atypes)


def _is_dialog(name):
    n = (name or "").lower()
    return "диалог" in n or "dialog" in n


def _sum_rows(rows):
    spend       = sum(_f(r.get("spend")) for r in rows)
    impressions = sum(_i(r.get("impressions")) for r in rows)
    clicks      = sum(_i(r.get("clicks")) for r in rows)
    reach       = max((_i(r.get("reach", 0)) for r in rows), default=0)
    ctr = clicks / impressions * 100 if impressions else 0
    cpc = spend / clicks if clicks else 0
    cpm = spend / impressions * 1000 if impressions else 0

    dialogs     = sum(_get_action(r.get("actions"), "onsite_conversion.total_messaging_connection") for r in rows)
    video_views = sum(_get_action(r.get("actions"), "video_view") for r in rows)
    saves       = sum(_get_action(r.get("actions"), "onsite_conversion.post_net_save") for r in rows)
    likes       = sum(_get_action(r.get("actions"), "onsite_conversion.post_net_like") for r in rows)
    cpd = spend / dialogs if dialogs else 0

    return dict(
        spend=spend, impressions=impressions, clicks=clicks, reach=reach,
        ctr=ctr, cpc=cpc, cpm=cpm,
        dialogs=dialogs, cpd=cpd, video_views=video_views, saves=saves, likes=likes,
    )


def _campaign_totals(rows):
    camps = {}
    for r in rows:
        cid = r.get("campaign_id") or r.get("campaign_name")
        name = r.get("campaign_name", cid)
        camps.setdefault(cid, {"name": name, "rows": []})["rows"].append(r)
    return {cid: {"name": v["name"], **_sum_rows(v["rows"])} for cid, v in camps.items()}


def _fmt_date(d):
    y, m, day = d.split("-")
    return f"{day}.{m}"


def _health_icon_dialog(cpd_now, cpd_prev, dialogs_now, dialogs_prev):
    issues = 0
    if cpd_now >= 3.0:
        issues += 3
    elif cpd_now >= 2.0:
        issues += 1
    if cpd_prev > 0 and cpd_now / cpd_prev > 1.2:
        issues += 2
    if dialogs_prev > 0 and dialogs_now > 0 and dialogs_now / dialogs_prev < 0.7:
        issues += 2
    if issues >= 3:
        return "🔴"
    if issues >= 1:
        return "🟡"
    return "🟢"


def _health_icon_traffic(ctr_now, ctr_prev):
    issues = 0
    if ctr_prev > 0 and ctr_now / ctr_prev < 0.85:
        issues += 2
    if ctr_now < 0.5:
        issues += 1
    if issues >= 3:
        return "🔴"
    if issues >= 1:
        return "🟡"
    return "🟢"


def analyze_weekly(data_path=None):
    if data_path is None:
        data_path = os.path.join(os.path.dirname(__file__), "..", "data", "latest_weekly.json")

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    account = data["account"]
    cur     = account.get("currency", "USD")
    acc     = account.get("name", "")

    w1 = data["week1"]
    w2 = data["week2"]
    w1_label = f"{_fmt_date(w1['since'])}–{_fmt_date(w1['until'])}"
    w2_label = f"{_fmt_date(w2['since'])}–{_fmt_date(w2['until'])}"

    w1c    = data.get("w1_campaigns", [])
    w2c    = data.get("w2_campaigns", [])
    adsets = data.get("w1_adsets", [])
    ads    = data.get("w1_ads", [])

    T1 = _sum_rows(w1c)
    T2 = _sum_rows(w2c)

    w1_camps = _campaign_totals(w1c)
    w2_camps = _campaign_totals(w2c)

    # ── Header ──────────────────────────────────────────────
    lines = [
        f"📊 *НЕДЕЛЬНЫЙ ОТЧЁТ META ADS*",
        f"🗓 {w1_label}.2026  vs  {w2_label}.2026",
        f"🏢 {acc}",
        "",
        "━━━━ ИТОГО ЗА НЕДЕЛЮ ━━━━",
        f"💰 Расход: *{_money(T1['spend'], cur)}*  (пред: {_money(T2['spend'], cur)}  {_delta(T1['spend'], T2['spend'])})",
        f"👁 Охват: {T1['reach']:,}  (пред: {T2['reach']:,}  {_delta(T1['reach'], T2['reach'])})",
    ]
    if T1["dialogs"] or T2["dialogs"]:
        cpd_delta = _delta(T1['cpd'], T2['cpd'], invert=True) if T1['cpd'] and T2['cpd'] else ""
        lines.append(
            f"💬 Диалогов: *{T1['dialogs']}*  (пред: {T2['dialogs']}  {_delta(T1['dialogs'], T2['dialogs'])})"
            + (f"  |  CPD *{_money(T1['cpd'], cur)}*  (пред: {_money(T2['cpd'], cur)}  {cpd_delta})" if T1['cpd'] else "")
        )
    lines += [
        f"📈 CTR: {_pct(T1['ctr'])}  (пред: {_pct(T2['ctr'])}  {_delta(T1['ctr'], T2['ctr'])})",
        f"💵 CPC: {_money(T1['cpc'], cur)}  (пред: {_money(T2['cpc'], cur)}  {_delta(T1['cpc'], T2['cpc'], invert=True)})",
        f"📣 CPM: {_money(T1['cpm'], cur)}  (пред: {_money(T2['cpm'], cur)}  {_delta(T1['cpm'], T2['cpm'], invert=True)})",
    ]
    eng_parts = []
    if T1["video_views"]: eng_parts.append(f"▶ {T1['video_views']:,} просмотров (пред: {T2['video_views']:,}  {_delta(T1['video_views'], T2['video_views'])})")
    if T1["saves"]:       eng_parts.append(f"🔖 {T1['saves']} сохр. (пред: {T2['saves']}  {_delta(T1['saves'], T2['saves'])})")
    if T1["likes"]:       eng_parts.append(f"❤ {T1['likes']} лайков")
    for p in eng_parts:
        lines.append("  " + p)

    # ── Campaigns ───────────────────────────────────────────
    lines += ["", "━━━━ КАМПАНИИ (неделя к неделе) ━━━━"]
    sorted_camps = sorted(w1_camps.items(), key=lambda x: x[1]["spend"], reverse=True)
    alerts = []

    for cid, c in sorted_camps:
        c2         = w2_camps.get(cid, {})
        prev_spend = c2.get("spend", 0)
        is_dialog  = _is_dialog(c["name"])

        if is_dialog:
            prev_cpd     = c2.get("cpd", 0)
            prev_dialogs = c2.get("dialogs", 0)
            icon = _health_icon_dialog(c["cpd"], prev_cpd, c["dialogs"], prev_dialogs)

            cpd_delta = _delta(c["cpd"], prev_cpd, invert=True) if prev_cpd and c["dialogs"] else ""
            line = (
                f"\n{icon} 💬 *{c['name']}*\n"
                f"  💰 {_money(c['spend'], cur)} {_delta(c['spend'], prev_spend)}"
                f"  |  💬 {c['dialogs']} диалогов {_delta(c['dialogs'], prev_dialogs)}"
            )
            if c["dialogs"]:
                line += f"  |  CPD *{_money(c['cpd'], cur)}* {cpd_delta}"
            else:
                line += "  |  ⚠️ 0 диалогов"
            line += f"\n  👁 {c['impressions']:,} показов  |  📈 CTR {_pct(c['ctr'])}"
            if c2:
                prev_cpd_str = f", CPD {_money(prev_cpd, cur)}" if prev_cpd else ""
                line += f"\n  ↔ Пред. нед.: расход {_money(prev_spend, cur)}, {prev_dialogs} диалогов{prev_cpd_str}"

            # Alerts for dialog campaigns
            if c["dialogs"] == 0 and c["spend"] > 50:
                alerts.append(f"🚨 0 диалогов при расходе {_money(c['spend'], cur)}: {c['name'][:50]}")
            if c["dialogs"] > 0 and c["cpd"] >= 3.0:
                alerts.append(f"💸 CPD {_money(c['cpd'], cur)} выше нормы $3: {c['name'][:50]}")
            elif c["dialogs"] > 0 and prev_cpd > 0 and c["cpd"] / prev_cpd > 1.3:
                alerts.append(f"📈 CPD вырос {_delta(c['cpd'], prev_cpd)}: {c['name'][:50]}")
            if prev_dialogs > 0 and c["dialogs"] > 0 and c["dialogs"] / prev_dialogs < 0.7:
                alerts.append(f"💬 Диалогов стало меньше {_delta(c['dialogs'], prev_dialogs)}: {c['name'][:50]}")

        else:
            prev_ctr = c2.get("ctr", 0)
            icon = _health_icon_traffic(c["ctr"], prev_ctr)

            line = (
                f"\n{icon} 👁 *{c['name']}*\n"
                f"  💰 {_money(c['spend'], cur)} {_delta(c['spend'], prev_spend)}"
                f"  |  CTR {_pct(c['ctr'])} {_delta(c['ctr'], prev_ctr)}"
                f"  |  CPC {_money(c['cpc'], cur)}\n"
                f"  👁 {c['impressions']:,} показов  |  Клики: {c['clicks']:,}"
            )
            if c2:
                line += f"\n  ↔ Пред. нед.: расход {_money(prev_spend, cur)}, CTR {_pct(prev_ctr)}"
            if c["video_views"]:
                line += f"\n  ▶ {c['video_views']:,} просм."
            if c["saves"]:
                line += f"  🔖 {c['saves']} сохр."

            # Alerts for traffic campaigns
            if prev_ctr > 0 and c["ctr"] / prev_ctr < 0.85:
                alerts.append(f"⚡ CTR упал {_delta(c['ctr'], prev_ctr)}: {c['name'][:50]}")
            if c["ctr"] < 0.5 and c["impressions"] > 3000:
                alerts.append(f"📉 Низкий CTR {_pct(c['ctr'])}: {c['name'][:50]}")

        lines.append(line)

    # ── Adsets ───────────────────────────────────────────────
    if adsets:
        lines += ["", "━━━━ АДСЕТЫ НЕДЕЛИ (топ-6 по расходу) ━━━━"]
        adset_map = {}
        for r in adsets:
            aid = r.get("adset_id", r.get("adset_name"))
            camp = r.get("campaign_name", "")
            adset_map.setdefault(aid, {"name": r.get("adset_name", aid), "camp": camp, "rows": []})["rows"].append(r)
        adset_totals = {
            aid: {"name": v["name"], "camp": v["camp"], **_sum_rows(v["rows"])}
            for aid, v in adset_map.items()
        }
        for _, a in sorted(adset_totals.items(), key=lambda x: x[1]["spend"], reverse=True)[:6]:
            is_d = _is_dialog(a["camp"])
            if is_d and a["dialogs"]:
                metric = f"CPD {_money(a['cpd'])}  💬{a['dialogs']}"
            elif is_d:
                metric = "💬 0 диал."
            else:
                metric = f"CTR {_pct(a['ctr'])}"
                if a["saves"]:
                    metric += f"  🔖{a['saves']}"
            lines.append(f"  • {a['name'][:52]}  {_money(a['spend'], cur)}  {metric}")

    # ── Ads split by campaign type ───────────────────────────
    if ads:
        dialog_ads  = [r for r in ads if _is_dialog(r.get("campaign_name", ""))]
        traffic_ads = [r for r in ads if not _is_dialog(r.get("campaign_name", ""))]

        # Dialog ads: rank by CPD
        if dialog_ads:
            with_dialogs = [
                r for r in dialog_ads
                if _get_action(r.get("actions", []), "onsite_conversion.total_messaging_connection") >= 2
                and _f(r.get("spend")) >= 5
            ]
            if with_dialogs:
                def _cpd(r):
                    d = _get_action(r.get("actions", []), "onsite_conversion.total_messaging_connection")
                    s = _f(r.get("spend"))
                    return s / d if d else float("inf")

                best  = sorted(with_dialogs, key=_cpd)[:3]
                worst = sorted(with_dialogs, key=_cpd, reverse=True)[:3]

                lines += ["", "━━━━ 💬 ДИАЛОГОВЫЕ ОБЪЯВЛЕНИЯ (CPD) ━━━━"]
                lines.append("  Лучшие (дешевле диалог):")
                for r in best:
                    d = _get_action(r.get("actions", []), "onsite_conversion.total_messaging_connection")
                    s = _f(r.get("spend"))
                    lines.append(f"  🟢 {r.get('ad_name','')[:45]}  CPD {_money(s/d)}  💬{d}")

                if worst and worst[0].get("ad_name") != best[0].get("ad_name"):
                    lines.append("  Дорогие:")
                    for r in worst:
                        d = _get_action(r.get("actions", []), "onsite_conversion.total_messaging_connection")
                        s = _f(r.get("spend"))
                        lines.append(f"  🔴 {r.get('ad_name','')[:45]}  CPD {_money(s/d)}  💬{d}")

        # Traffic ads: rank by CTR
        if traffic_ads:
            filtered = [r for r in traffic_ads if _i(r.get("impressions", 0)) > 500]
            if filtered:
                top = sorted(filtered, key=lambda r: _f(r.get("ctr")), reverse=True)[:4]
                bot = sorted(filtered, key=lambda r: _f(r.get("ctr")))[:3]
                lines += ["", "━━━━ 👁 ТРАФИКОВЫЕ ОБЪЯВЛЕНИЯ (CTR) ━━━━"]
                lines.append("  Лучшие:")
                for r in top:
                    lines.append(f"  🟢 {r.get('ad_name','')[:45]}  CTR {_pct(_f(r.get('ctr')))}  расход {_money(_f(r.get('spend')), cur)}")
                if bot:
                    lines.append("  Слабые:")
                    for r in bot:
                        lines.append(f"  🔴 {r.get('ad_name','')[:45]}  CTR {_pct(_f(r.get('ctr')))}  расход {_money(_f(r.get('spend')), cur)}")

    # ── Trend summary ────────────────────────────────────────
    lines += ["", "━━━━ ТЕНДЕНЦИЯ НЕДЕЛИ ━━━━"]

    def _label(arrow, good_dir="up"):
        if arrow.startswith("↑"):
            return arrow + (" ✅" if good_dir == "up" else " ⚠️")
        if arrow.startswith("↓"):
            return arrow + (" ⚠️" if good_dir == "up" else " ✅")
        return (arrow or "—") + " —"

    trend_lines = [
        f"  Расход:    {_label(_delta(T1['spend'],   T2['spend']),             'neutral')}",
        f"  Диалоги:   {_label(_delta(T1['dialogs'], T2['dialogs']),           'up')}",
    ]
    if T1['cpd'] and T2['cpd']:
        trend_lines.append(f"  CPD:       {_label(_delta(T1['cpd'], T2['cpd'], True),   'up')}")
    trend_lines += [
        f"  CTR:       {_label(_delta(T1['ctr'],     T2['ctr']),               'up')}",
        f"  CPC:       {_label(_delta(T1['cpc'],     T2['cpc'], True),         'up')}",
        f"  Сохранения:{_label(_delta(T1['saves'],   T2['saves']),             'up')}",
    ]
    lines += trend_lines

    # ── Alerts ───────────────────────────────────────────────
    if alerts:
        lines += ["", "━━━━ АЛЕРТЫ ━━━━"] + [f"  {a}" for a in alerts]

    report = "\n".join(lines)

    summary = _build_weekly_ai_summary(
        acc, cur, w1_label, w2_label, T1, T2,
        sorted_camps, w1_camps, w2_camps, adsets, ads, alerts,
    )

    return report, summary


def _build_weekly_ai_summary(
    acc, cur, w1_label, w2_label, T1, T2,
    sorted_camps, w1_camps, w2_camps, adsets, ads, alerts,
):
    lines = [
        f"Аккаунт: {acc} | Валюта: {cur}",
        f"Период: неделя {w1_label} vs предыдущая {w2_label}",
        "Бизнес: туристическая компания, реклама в Instagram/Facebook",
        "Главная конверсия: диалог в Direct (onsite_conversion.total_messaging_connection)",
        "Стратегия: 60% бюджета — диалоговые кампании (ключевая метрика CPD, норма ≤$3), "
        "40% — трафик в профиль (ключевая метрика CTR/охват)",
        "",
        "=== ИТОГО АККАУНТА ===",
        f"Нед.1: расход {T1['spend']:.2f}, показы {T1['impressions']}, CTR {T1['ctr']:.2f}%, CPM {T1['cpm']:.2f}, охват {T1['reach']}",
        f"Нед.2: расход {T2['spend']:.2f}, показы {T2['impressions']}, CTR {T2['ctr']:.2f}%, CPM {T2['cpm']:.2f}, охват {T2['reach']}",
    ]
    if T1["dialogs"] or T2["dialogs"]:
        lines.append(
            f"Диалоги: нед.1={T1['dialogs']} (CPD {T1['cpd']:.2f})  |  нед.2={T2['dialogs']} (CPD {T2['cpd']:.2f})"
        )

    lines += ["", "=== КАМПАНИИ (нед.1 vs нед.2) ==="]
    for cid, c in sorted_camps:
        c2 = w2_camps.get(cid, {})
        is_dialog = _is_dialog(c["name"])
        if is_dialog:
            lines.append(
                f"• [💬 ДИАЛОГ] {c['name']}: расход {c['spend']:.2f} (пред {c2.get('spend',0):.2f}), "
                f"диалогов {c['dialogs']} (пред {c2.get('dialogs',0)}), "
                f"CPD {c['cpd']:.2f} (пред {c2.get('cpd',0):.2f}), "
                f"CTR {c['ctr']:.2f}%, показы {c['impressions']}"
            )
        else:
            lines.append(
                f"• [👁 ТРАФИК] {c['name']}: расход {c['spend']:.2f} (пред {c2.get('spend',0):.2f}), "
                f"CTR {c['ctr']:.2f}% (пред {c2.get('ctr',0):.2f}%), "
                f"CPC {c['cpc']:.2f}, клики {c['clicks']}, "
                f"просм. {c['video_views']:,}, сохр. {c['saves']}"
            )

    if adsets:
        lines += ["", "=== ТОП АДСЕТЫ (нед.1) ==="]
        adset_map = {}
        for r in adsets:
            n    = r.get("adset_name", "")
            camp = r.get("campaign_name", "")
            adset_map.setdefault(n, {"spend": 0, "camp": camp, "rows": []})
            adset_map[n]["spend"] += _f(r.get("spend"))
            adset_map[n]["rows"].append(r)
        for name, v in sorted(adset_map.items(), key=lambda x: -x[1]["spend"])[:8]:
            t = _sum_rows(v["rows"])
            is_d = _is_dialog(v["camp"])
            if is_d:
                lines.append(f"• {name} | расход {v['spend']:.2f} | диалогов {t['dialogs']} | CPD {t['cpd']:.2f}")
            else:
                lines.append(f"• {name} | расход {v['spend']:.2f} | CTR {t['ctr']:.2f}% | сохр. {t['saves']}")

    if ads:
        lines += ["", "=== ОБЪЯВЛЕНИЯ (нед.1) ==="]
        for r in sorted(ads, key=lambda x: _f(x.get("spend")), reverse=True)[:10]:
            is_d    = _is_dialog(r.get("campaign_name", ""))
            dialogs = _get_action(r.get("actions", []), "onsite_conversion.total_messaging_connection")
            spend   = _f(r.get("spend"))
            cpd     = spend / dialogs if dialogs else None
            if is_d:
                metric = f"диалогов {dialogs}, CPD {cpd:.2f}" if cpd else f"диалогов {dialogs}"
            else:
                metric = f"CTR {_f(r.get('ctr')):.2f}%"
            lines.append(
                f"• {'💬' if is_d else '👁'} {r.get('ad_name','')} | "
                f"расход {spend:.2f} | {metric} | {_i(r.get('impressions'))} показов"
            )

    if alerts:
        lines += ["", "=== АЛЕРТЫ ==="] + [f"• {a}" for a in alerts]

    return "\n".join(lines)


if __name__ == "__main__":
    report, summary = analyze_weekly()
    print(report)
    print("\n\n--- AI SUMMARY ---\n")
    print(summary)
