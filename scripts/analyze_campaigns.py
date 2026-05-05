"""Analyzes Meta Ads data and builds structured summary + Telegram report."""

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


def _trend_arrow(now, prev):
    if prev == 0:
        return ""
    delta = (now - prev) / prev * 100
    if delta > 5:
        return f"↑{delta:.0f}%"
    if delta < -5:
        return f"↓{abs(delta):.0f}%"
    return "→"


def _get_action(actions, *atypes):
    """Sum values for any of the given action types."""
    if not actions:
        return 0
    total = 0
    for a in actions:
        if a.get("action_type") in atypes:
            total += _i(a.get("value", 0))
    return total


def _sum_insights(rows):
    spend       = sum(_f(r.get("spend")) for r in rows)
    impressions = sum(_i(r.get("impressions")) for r in rows)
    clicks      = sum(_i(r.get("clicks")) for r in rows)
    reach       = max((_i(r.get("reach")) for r in rows), default=0)
    ctr  = clicks / impressions * 100 if impressions else 0
    cpc  = spend / clicks if clicks else 0
    cpm  = spend / impressions * 1000 if impressions else 0

    # Key business metrics
    dialogs    = sum(_get_action(r.get("actions"), "onsite_conversion.total_messaging_connection") for r in rows)
    video_views= sum(_get_action(r.get("actions"), "video_view") for r in rows)
    saves      = sum(_get_action(r.get("actions"), "onsite_conversion.post_net_save") for r in rows)
    likes      = sum(_get_action(r.get("actions"), "onsite_conversion.post_net_like") for r in rows)
    comments   = sum(_get_action(r.get("actions"), "comment") for r in rows)

    # Cost per dialog
    cpd = spend / dialogs if dialogs else 0

    return dict(
        spend=spend, impressions=impressions, clicks=clicks, reach=reach,
        ctr=ctr, cpc=cpc, cpm=cpm,
        dialogs=dialogs, cpd=cpd,
        video_views=video_views, saves=saves, likes=likes, comments=comments,
    )


def _campaign_map(rows):
    m = {}
    for r in rows:
        cid = r.get("campaign_id") or r.get("campaign_name")
        if cid not in m:
            m[cid] = {"name": r.get("campaign_name", cid), "rows": []}
        m[cid]["rows"].append(r)
    return {cid: {"name": v["name"], **_sum_insights(v["rows"])} for cid, v in m.items()}


def _health_icon(ctr_now, ctr_7d, freq, dialogs, spend):
    issues = 0
    if ctr_7d > 0 and (ctr_now / ctr_7d) < 0.8:
        issues += 2
    if freq > 4:
        issues += 2
    elif freq > 3:
        issues += 1
    if ctr_now < 0.5:
        issues += 1
    # For dialog campaigns: alert if no dialogs with significant spend
    if dialogs == 0 and spend > 30 and "диалог" in "dialog":
        issues += 1
    if issues >= 3:
        return "🔴"
    if issues >= 1:
        return "🟡"
    return "🟢"


def analyze(data_path=None):
    if data_path is None:
        data_path = os.path.join(os.path.dirname(__file__), "..", "data", "latest.json")

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    account  = data["account"]
    cur      = account.get("currency", "USD")
    acc_name = account.get("name", "")
    from datetime import datetime, timedelta
    _fetched = data.get("fetched_at", "")[:10]
    date = (datetime.strptime(_fetched, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d") if _fetched else _fetched

    y_rows   = data.get("insights_yesterday", [])
    w_rows   = data.get("insights_7d", [])
    w14_rows = data.get("insights_14d", [])
    adset_rows = data.get("adset_insights_7d", [])
    ad_rows    = data.get("ad_insights_yesterday", [])

    y_total  = _sum_insights(y_rows)
    w_total  = _sum_insights(w_rows)
    w14_total= _sum_insights(w14_rows)

    prev7_spend = w14_total["spend"] - w_total["spend"]
    prev7_ctr   = (w14_total["clicks"] - w_total["clicks"]) / max(w14_total["impressions"] - w_total["impressions"], 1) * 100
    w_avg_spend = w_total["spend"] / 7

    y_camp = _campaign_map(y_rows)
    w_camp = _campaign_map(w_rows)

    # ── Header ──────────────────────────────────────────────
    lines = [
        f"📊 *META ADS АУДИТ — {date}*",
        f"🏢 {acc_name}",
        "",
        "━━━━ ИТОГО ВЧЕРА ━━━━",
        f"💰 Расход: *{_money(y_total['spend'], cur)}*  (7д avg: {_money(w_avg_spend, cur)}/день {_trend_arrow(y_total['spend'], w_avg_spend)})",
        f"👁 Охват: {y_total['reach']:,}  |  Показы: {y_total['impressions']:,}",
        f"🖱 Клики: {y_total['clicks']:,}  |  CTR: {_pct(y_total['ctr'])}  {_trend_arrow(y_total['ctr'], w_total['ctr'])}",
        f"💵 CPC: {_money(y_total['cpc'], cur)}  |  CPM: {_money(y_total['cpm'], cur)}",
    ]

    # Dialog totals (key metric for this business)
    if y_total["dialogs"]:
        lines.append(
            f"💬 Диалогов: *{y_total['dialogs']}*  |  Цена диалога: {_money(y_total['cpd'], cur)}"
            + (f"  {_trend_arrow(-y_total['cpd'], -w_total['cpd'])}" if w_total['cpd'] else "")
        )

    # Engagement totals
    eng_parts = []
    if y_total["video_views"]: eng_parts.append(f"▶ {y_total['video_views']:,} просмотров")
    if y_total["saves"]:       eng_parts.append(f"🔖 {y_total['saves']} сохранений")
    if y_total["likes"]:       eng_parts.append(f"❤ {y_total['likes']} лайков")
    if y_total["comments"]:    eng_parts.append(f"💭 {y_total['comments']} комментариев")
    if eng_parts:
        lines.append("  ".join(eng_parts))

    # ── Campaigns ───────────────────────────────────────────
    lines += ["", "━━━━ КАМПАНИИ (вчера) ━━━━"]
    sorted_campaigns = sorted(y_camp.items(), key=lambda x: x[1]["spend"], reverse=True)
    alerts = []

    for cid, c in sorted_campaigns:
        w_c  = w_camp.get(cid, {})
        w_ctr= w_c.get("ctr", 0)
        freq = _f(next((r.get("frequency") for r in y_rows if r.get("campaign_id") == cid), 0))
        icon = _health_icon(c["ctr"], w_ctr, freq, c["dialogs"], c["spend"])
        ctr_trend = _trend_arrow(c["ctr"], w_ctr) if w_ctr else ""

        line = (
            f"\n{icon} *{c['name']}*\n"
            f"  💰 {_money(c['spend'], cur)}  |  CTR {_pct(c['ctr'])} {ctr_trend}  |  CPC {_money(c['cpc'], cur)}\n"
            f"  👁 {c['impressions']:,} показов  |  🔁 Частота {freq:.1f}"
        )
        if c["dialogs"]:
            line += f"\n  💬 {c['dialogs']} диалогов  |  цена {_money(c['cpd'], cur)}/диалог"
        if c["video_views"]:
            line += f"\n  ▶ {c['video_views']:,} просм."
        if c["saves"]:
            line += f"  🔖 {c['saves']} сохр."
        lines.append(line)

        # Alerts
        if w_ctr > 0 and (c["ctr"] / w_ctr) < 0.8 and c["impressions"] > 500:
            alerts.append(f"⚡ Усталость CTR ({_pct(c['ctr'])} vs 7д {_pct(w_ctr)}): {c['name'][:50]}")
        if freq > 4:
            alerts.append(f"🔄 Высокая частота {freq:.1f}: {c['name'][:50]}")
        if c["ctr"] < 0.5 and c["impressions"] > 2000:
            alerts.append(f"📉 Низкий CTR {_pct(c['ctr'])}: {c['name'][:50]}")

    # ── Adsets ──────────────────────────────────────────────
    if adset_rows:
        lines += ["", "━━━━ АДСЕТЫ (7д, топ-5) ━━━━"]
        adset_map = {}
        for r in adset_rows:
            aid = r.get("adset_id", r.get("adset_name"))
            adset_map.setdefault(aid, {"name": r.get("adset_name", aid), "rows": []})["rows"].append(r)
        adset_totals = {aid: {"name": v["name"], **_sum_insights(v["rows"])} for aid, v in adset_map.items()}
        for _, a in sorted(adset_totals.items(), key=lambda x: x[1]["spend"], reverse=True)[:5]:
            dial_str = f"  💬{a['dialogs']}" if a["dialogs"] else ""
            lines.append(f"  • {a['name'][:48]}  {_money(a['spend'], cur)}  CTR {_pct(a['ctr'])}{dial_str}")

    # ── Ad creatives ────────────────────────────────────────
    if ad_rows:
        top_ads = sorted(ad_rows, key=lambda r: _f(r.get("ctr")), reverse=True)[:3]
        bottom_ads = [r for r in sorted(ad_rows, key=lambda r: _f(r.get("ctr"))) if _i(r.get("impressions", 0)) > 200][:3]
        lines += ["", "━━━━ ЛУЧШИЕ ОБЪЯВЛЕНИЯ (CTR) ━━━━"]
        for r in top_ads:
            lines.append(f"  🟢 {r.get('ad_name','')[:45]}  CTR {_pct(_f(r.get('ctr')))}")
        if bottom_ads:
            lines += ["", "━━━━ АУТСАЙДЕРЫ ━━━━"]
            for r in bottom_ads:
                lines.append(f"  🔴 {r.get('ad_name','')[:45]}  CTR {_pct(_f(r.get('ctr')))}")

    # ── Alerts ──────────────────────────────────────────────
    if alerts:
        lines += ["", "━━━━ АЛЕРТЫ ━━━━"] + [f"  {a}" for a in alerts]

    report = "\n".join(lines)

    # ── AI summary ──────────────────────────────────────────
    summary = _build_ai_summary(
        acc_name, cur, date,
        y_total, w_total, prev7_spend, prev7_ctr,
        sorted_campaigns, y_camp, w_camp, y_rows, adset_rows, ad_rows, alerts,
    )

    return report, summary


def _build_ai_summary(
    acc_name, cur, date,
    y, w, prev7_spend, prev7_ctr,
    sorted_campaigns, y_camp, w_camp, y_rows, adset_rows, ad_rows, alerts,
):
    lines = [
        f"Аккаунт: {acc_name} | Валюта: {cur} | Дата: {date}",
        "Бизнес: туристическая компания, реклама в Instagram/Facebook",
        "Главная конверсия: диалог в Direct (onsite_conversion.total_messaging_connection)",
        "",
        "=== МЕТРИКИ АККАУНТА ВЧЕРА ===",
        f"Расход: {y['spend']:.2f}, показы: {y['impressions']}, клики: {y['clicks']}, CTR: {y['ctr']:.2f}%, CPC: {y['cpc']:.2f}",
        f"Диалогов: {y['dialogs']}, цена диалога: {y['cpd']:.2f}",
        f"Видеопросмотры: {y['video_views']:,}, сохранения: {y['saves']}, лайки: {y['likes']}",
        f"7д avg/день: расход {w['spend']/7:.2f}, CTR {w['ctr']:.2f}%, диалогов {w['dialogs']/7:.1f}",
        f"Пред. 7 дней: расход {prev7_spend:.2f}, CTR {prev7_ctr:.2f}%",
        "",
        "=== КАМПАНИИ (вчера vs 7д avg) ===",
    ]

    for cid, c in sorted_campaigns:
        w_c = w_camp.get(cid, {})
        freq = _f(next((r.get("frequency") for r in y_rows if r.get("campaign_id") == cid), 0))
        lines.append(
            f"• {c['name']}: расход {c['spend']:.2f}, CTR {c['ctr']:.2f}% (7д {w_c.get('ctr',0):.2f}%), "
            f"CPC {c['cpc']:.2f}, диалогов {c['dialogs']} (цена {c['cpd']:.2f}), "
            f"частота {freq:.1f}, просмотров {c['video_views']:,}, сохр. {c['saves']}"
        )

    if adset_rows:
        lines += ["", "=== АДСЕТЫ (7 дней) ==="]
        adset_map = {}
        for r in adset_rows:
            n = r.get("adset_name", "")
            adset_map[n] = adset_map.get(n, 0) + _f(r.get("spend"))
        for name, sp in sorted(adset_map.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"• {name}: расход {sp:.2f}")

    if ad_rows:
        lines += ["", "=== ОБЪЯВЛЕНИЯ ВЧЕРА (по CTR) ==="]
        for r in sorted(ad_rows, key=lambda x: _f(x.get("ctr")), reverse=True)[:10]:
            lines.append(
                f"• {r.get('ad_name','')} | CTR {_f(r.get('ctr')):.2f}% | "
                f"расход {_f(r.get('spend')):.2f} | {_i(r.get('impressions'))} показов"
            )

    if alerts:
        lines += ["", "=== АЛЕРТЫ ==="] + [f"• {a}" for a in alerts]

    return "\n".join(lines)


if __name__ == "__main__":
    report, summary = analyze()
    print(report)
    print("\n\n--- AI SUMMARY ---")
    print(summary)
