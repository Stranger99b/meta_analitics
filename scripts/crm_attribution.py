"""
Сквозная атрибуция: расход Meta Ads → лиды и воронка в Salebot/CRM.

Переписано 07.09.2026. Что изменилось и почему:
  - Источник расхода: `data/latest_weekly.json` (обновляется недельным cron)
    вместо `data/latest.json` — тот заморожен с 15.06, потому что дневной cron
    Meta отключён.
  - «Начатые переписки» больше НЕ берутся из Meta: с ~23.08.2026 API перестал
    отдавать `onsite_conversion.messaging_conversation_started_7d` и соседние
    метрики переписок (ограничения на выдачу данных). Знаменатель для CPL —
    лиды из Salebot по метке `instagram_ads_data` (модуль salebot_leads).
  - Лиды считаются строго за окно недели, а не «за всю историю выгрузок»
    (старая версия читала все 147 дампов, ~1.7 ГБ, и сравнивала их с расходом
    за 7 дней — цифры были несопоставимы).
"""

import os
import json
import datetime as dt
import html as _html
from collections import defaultdict

import salebot_leads as sl

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
META_WEEKLY = os.path.join(DATA_DIR, "latest_weekly.json")

# Метрики переписок, которые Meta отдавала до ~23.08.2026.
MESSAGING_ACTIONS = (
    "onsite_conversion.messaging_conversation_started_7d",
    "onsite_conversion.messaging_conversation_replied_7d",
    "onsite_conversion.messaging_first_reply",
    "onsite_conversion.total_messaging_connection",
)


def _actions(row: dict) -> dict[str, int]:
    out = {}
    for a in row.get("actions") or []:
        try:
            out[a["action_type"]] = int(float(a["value"]))
        except Exception:
            continue
    return out


def meta_messaging_status(rows: list[dict]) -> dict:
    """Сколько переписок Meta ещё отдаёт. Нужен, чтобы заметить возврат метрики."""
    totals = {a: 0 for a in MESSAGING_ACTIONS}
    for r in rows:
        acts = _actions(r)
        for a in MESSAGING_ACTIONS:
            totals[a] += acts.get(a, 0)
    started = totals["onsite_conversion.messaging_conversation_started_7d"]
    return {
        "totals": totals,
        "started": started,
        "alive": started > 0,
    }


def load_meta_weekly() -> dict | None:
    try:
        return json.load(open(META_WEEKLY, encoding="utf-8"))
    except Exception:
        return None


def spend_by_campaign(rows: list[dict]) -> dict[str, dict]:
    """{campaign_num: {spend, impressions, clicks, name}} — суммируем по номеру №XXX."""
    out = defaultdict(lambda: {"spend": 0.0, "impressions": 0, "clicks": 0, "name": ""})
    for r in rows:
        num = sl.campaign_num(r.get("campaign_name") or "")
        if not num:
            continue
        o = out[num]
        o["spend"] += float(r.get("spend") or 0)
        o["impressions"] += int(r.get("impressions") or 0)
        o["clicks"] += int(r.get("clicks") or 0)
        if not o["name"]:
            o["name"] = r.get("campaign_name") or ""
    return dict(out)


def _fmt_money(v: float) -> str:
    return f"${v:,.0f}".replace(",", " ")


def build_attribution() -> tuple[str, str]:
    """
    Возвращает (telegram_block_html, ai_summary_plain) за последнюю полную неделю
    из latest_weekly.json, с сравнением с предыдущей неделей.
    """
    meta = load_meta_weekly()
    if not meta:
        return "", ""

    w1 = meta.get("week1") or {}
    w2 = meta.get("week2") or {}
    if not w1.get("since"):
        return "", ""

    d1_from, d1_to = dt.date.fromisoformat(w1["since"]), dt.date.fromisoformat(w1["until"])
    sp1 = spend_by_campaign(meta.get("w1_campaigns") or [])
    leads1 = sl.load_leads(d1_from, d1_to)
    f1 = sl.group_by_campaign(leads1)

    have_prev = bool(w2.get("since"))
    if have_prev:
        d2_from, d2_to = dt.date.fromisoformat(w2["since"]), dt.date.fromisoformat(w2["until"])
        sp2 = spend_by_campaign(meta.get("w2_campaigns") or [])
        f2 = sl.group_by_campaign(sl.load_leads(d2_from, d2_to))
    else:
        sp2, f2 = {}, {}

    status = meta_messaging_status((meta.get("w1_campaigns") or []))
    _, missing = sl.dump_days_present(d1_from, d1_to)

    # Прошлую неделю тоже включаем в перебор — иначе остановленная кампания
    # нигде не всплывёт и падение лидов будет выглядеть беспричинным.
    nums = sorted(set(sp1) | set(f1) | set(sp2) | set(f2),
                  key=lambda n: -sp1.get(n, {}).get("spend", 0))

    L = [f"📊 <b>Атрибуция: расход Meta → лиды Salebot</b>",
         f"Неделя {d1_from.strftime('%d.%m')}–{d1_to.strftime('%d.%m')}"
         + (f" (пред. {d2_from.strftime('%d.%m')}–{d2_to.strftime('%d.%m')})" if have_prev else ""),
         ""]

    if not status["alive"]:
        L.append("⚠️ Meta не отдаёт «начатые переписки» — лиды считаем по метке "
                 "<code>instagram_ads_data</code> в Salebot.")
        L.append("")

    tot_s1, tot_l1, tot_c1 = 0.0, 0, 0
    # Итоги прошлой недели считаем по ВСЕМ её кампаниям, а не только по тем, что
    # крутятся сейчас: иначе остановленная кампания молча выпадает из сравнения.
    tot_s2 = sum(v["spend"] for v in sp2.values())
    tot_l2 = sum(v["leads"] for v in f2.values())
    stopped = []

    for num in nums:
        s1 = sp1.get(num, {}).get("spend", 0.0)
        fu1 = f1.get(num) or sl._blank_funnel()
        l1 = fu1["leads"]
        if s1 == 0 and l1 == 0:
            if (f2.get(num) or {}).get("leads", 0) or sp2.get(num, {}).get("spend", 0):
                stopped.append(num)
            continue

        s2 = sp2.get(num, {}).get("spend", 0.0)
        l2 = (f2.get(num) or {}).get("leads", 0)
        tot_s1 += s1; tot_l1 += l1; tot_c1 += sl.conversions(fu1)

        title = fu1["title"] or sp1.get(num, {}).get("name", "")
        name = sl.short_name(title) or f"кампания №{num}"
        cpl1 = s1 / l1 if l1 else None
        cpl2 = s2 / l2 if l2 else None

        L.append(f"<b>№{num} — {_html.escape(name)}</b>")
        cpl_str = _fmt_money(cpl1) if cpl1 is not None else "—"
        if cpl1 is not None and cpl2:
            arrow = "🔺" if cpl1 > cpl2 * 1.15 else ("🔻" if cpl1 < cpl2 * 0.85 else "▪️")
            cpl_str += f" {arrow} (было {_fmt_money(cpl2)})"
        elif l1 == 0 and s1 > 0:
            cpl_str = "нет лидов ⛔"
        L.append(f"  💸 {_fmt_money(s1)}  |  лидов <b>{l1}</b>"
                 + (f" (было {l2})" if have_prev else "")
                 + f"  |  CPL {cpl_str}")

        parts = []
        if fu1["engaged"]:
            parts.append(f"💬 завязались: {fu1['engaged']}")
        conv = sl.conversions(fu1)
        if conv:
            parts.append(f"✅ бронь/оплата: {conv}")
        if fu1["cancel"]:
            parts.append(f"❌ отмена: {fu1['cancel']}")
        if fu1["ignore"]:
            parts.append(f"👻 игнор: {fu1['ignore']}")
        if parts:
            L.append("  " + "  |  ".join(parts))
        L.append("")

    cpl_tot1 = tot_s1 / tot_l1 if tot_l1 else None
    cpl_tot2 = tot_s2 / tot_l2 if tot_l2 else None
    tail = f"  |  CPL {_fmt_money(cpl_tot1)}" if cpl_tot1 else ""
    if cpl_tot1 and cpl_tot2:
        tail += f" (было {_fmt_money(cpl_tot2)})"
    L.append(f"<b>Итого:</b> {_fmt_money(tot_s1)}  |  лидов {tot_l1}"
             + (f" (было {tot_l2})" if have_prev else "")
             + f"  |  бронь/оплата {tot_c1}{tail}")

    if stopped:
        L.append(f"⏹ Не крутились на этой неделе: {', '.join('№' + n for n in stopped)} "
                 f"(на прошлой лиды были).")

    tail_day = (d1_to + dt.timedelta(days=1)).isoformat()
    if tail_day in missing:
        L.append(f"\nℹ️ Клиенты, пришедшие {d1_to.strftime('%d.%m')} после 21:00, попадают "
                 f"в выгрузку за {tail_day[8:10]}.{tail_day[5:7]} — её ещё нет, "
                 f"лиды последнего дня неполные.")
    inner = [m for m in missing if m != tail_day]
    if inner:
        L.append(f"⚠️ Нет выгрузок Salebot за: {', '.join(inner)} — лиды занижены.")

    block = "\n".join(L)

    A = [f"=== Атрибуция Meta→Salebot, неделя {d1_from}–{d1_to} ==="]
    if not status["alive"]:
        A.append("ВНИМАНИЕ: Meta не отдаёт метрики переписок с ~23.08.2026; "
                 "лиды посчитаны по метке instagram_ads_data в Salebot.")
    for num in nums:
        s1 = sp1.get(num, {}).get("spend", 0.0)
        fu1 = f1.get(num) or sl._blank_funnel()
        if s1 == 0 and fu1["leads"] == 0:
            continue
        l2 = (f2.get(num) or {}).get("leads", 0)
        cpl = f"${s1 / fu1['leads']:.1f}" if fu1["leads"] else "нет лидов"
        A.append(f"№{num} {sl.short_name(fu1['title'] or sp1.get(num, {}).get('name', ''))}: "
                 f"расход=${s1:.0f}, лидов={fu1['leads']} (пред.нед. {l2}), CPL={cpl}, "
                 f"завязались={fu1['engaged']}, бронь/оплата={sl.conversions(fu1)}, "
                 f"отмен={fu1['cancel']}")
    A.append(f"Итого: расход=${tot_s1:.0f}, лидов={tot_l1} (пред.нед. {tot_l2}), "
             f"бронь/оплата={tot_c1}"
             + (f", CPL=${cpl_tot1:.1f}" if cpl_tot1 else ""))
    return block, "\n".join(A)


if __name__ == "__main__":
    b, s = build_attribution()
    print(s)
    print("\n---- telegram ----\n")
    print(b)
