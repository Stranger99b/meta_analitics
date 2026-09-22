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
    """
    {ключ: {spend, impressions, clicks, name, acct}} по строкам инсайтов.

    Ключ — кабинет + название кампании, а не номер «№XXX»: номера в кабинетах
    повторяются (в двух новых есть №002), и группировка по номеру склеивала бы
    разные кампании в одну строку.
    """
    out = defaultdict(lambda: {"spend": 0.0, "impressions": 0, "clicks": 0,
                               "name": "", "acct": "", "dialog": True})
    for r in rows:
        name = r.get("campaign_name") or "—"
        acct = r.get("_acct", "")
        o = out[f"{acct}|{name}"]
        o["spend"] += float(r.get("spend") or 0)
        o["impressions"] += int(r.get("impressions") or 0)
        o["clicks"] += int(r.get("clicks") or 0)
        o["name"] = o["name"] or name
        o["acct"] = o["acct"] or acct
        o["dialog"] = is_dialog_objective(r.get("objective"))
    return dict(out)


# Цели кампаний, которые ВЕДУТ В ДИРЕКТ и потому дают лид с меткой объявления.
# Всё остальное (трафик в профиль, охват, клики по ссылке) метку в Salebot не
# создаёт: человек приходит в профиль и пишет оттуда — для нас это органика.
# Поэтому ноль лидов у такой кампании — не провал, и в CPL её расход не идёт.
DIALOG_OBJECTIVES = {"OUTCOME_ENGAGEMENT", "MESSAGES", "CONVERSATIONS"}


def is_dialog_objective(objective: str | None) -> bool:
    """Белый список: считаем диалоговой только явно диалоговую цель."""
    return (objective or "").upper() in DIALOG_OBJECTIVES


def resolve_campaign(ad_id: str, ad_map: dict, prefixes: dict | None = None,
                     index: dict | None = None, min_prefix: int = 10) -> str | None:
    """
    Кампания лида по его `ad_id`.

    1) точное совпадение с объявлением из инсайтов;
    2) иначе — по самому длинному совпадению начала id. Salebot для части лидов
       присылает id варианта плейсмента («…_Group_1»), которого у Meta нет как
       объекта, но он рождается рядом с родительским объявлением: у лидов Дагестана
       совпадало 10 цифр с его объявлениями (1202519140…), тогда как у Мурманска
       префикс другой (1202520428…). Требуем не меньше `min_prefix` цифр И чтобы
       все лучшие совпадения вели в ОДНУ кампанию — иначе не гадаем;
    3) иначе — по кабинету (первые 9 цифр) и номеру «№XXX» из названия объявления.

    Без этого 45 лидов за неделю 14–20.09.2026 висели в строке «без кампании»,
    а Дагестан при расходе $236 показывал ноль лидов.
    """
    key = ad_map.get(ad_id)
    if key:
        return key
    best_len, best_keys = 0, set()
    for known, k in ad_map.items():
        n = len(os.path.commonprefix([known, ad_id]))
        if n > best_len:
            best_len, best_keys = n, {k}
        elif n == best_len:
            best_keys.add(k)
    if best_len >= min_prefix and len(best_keys) == 1:
        return next(iter(best_keys))
    if prefixes is not None and index is not None:
        return index.get((prefixes.get(ad_id[:9], ""), sl.campaign_num(ad_id)))
    return None


def _campaign_index(rows: list[dict]) -> dict[tuple, str]:
    """{(кабинет, номер кампании): ключ} — для лидов, привязанных по номеру."""
    idx = {}
    for r in rows:
        name = r.get("campaign_name") or ""
        num = sl.campaign_num(name)
        if num:
            idx[(r.get("_acct", ""), num)] = f"{r.get('_acct','')}|{name}"
    return idx


def leads_by_campaign(leads: list[dict], ad_map: dict, prefixes: dict,
                      index: dict) -> dict[str, dict]:
    """
    Раскладывает лиды Salebot по кампаниям.

    Сначала по `ad_id` (точно), затем — для вариантов плейсмента «…_Group_1»,
    которых у Meta нет как объектов, — по кабинету (первые 9 цифр id) и номеру
    «№XXX» из названия объявления.
    """
    out = defaultdict(sl._blank_funnel)
    for l in leads:
        key = resolve_campaign(l["ad_id"], ad_map)
        if not key:
            acct = prefixes.get(l["ad_id"][:9], "")
            key = index.get((acct, l.get("campaign_num")))
        if not key:
            key = f"{prefixes.get(l['ad_id'][:9], '')}|без кампании"
        sl._fold(out[key], l)
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
    from fetch_meta_ads import account_prefixes
    prefixes = account_prefixes()
    ad_map = {str(r["ad_id"]): f"{r.get('_acct','')}|{r.get('campaign_name') or '—'}"
              for r in (meta.get("w1_ads") or []) if r.get("ad_id")}

    sp1 = spend_by_campaign(meta.get("w1_campaigns") or [])
    idx1 = _campaign_index(meta.get("w1_campaigns") or [])
    leads1 = sl.load_leads(d1_from, d1_to)
    f1 = leads_by_campaign(leads1, ad_map, prefixes, idx1)

    have_prev = bool(w2.get("since"))
    if have_prev:
        d2_from, d2_to = dt.date.fromisoformat(w2["since"]), dt.date.fromisoformat(w2["until"])
        sp2 = spend_by_campaign(meta.get("w2_campaigns") or [])
        idx2 = _campaign_index(meta.get("w2_campaigns") or [])
        f2 = leads_by_campaign(sl.load_leads(d2_from, d2_to), ad_map, prefixes, idx2)
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
    tot_profile = 0.0  # расход кампаний, ведущих в профиль — считаем отдельно
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
        if sp1.get(num, {}).get("dialog", True):
            tot_s1 += s1
        else:
            tot_profile += s1
        tot_l1 += l1; tot_c1 += sl.conversions(fu1)

        name = sp1.get(num, {}).get("name") or num.replace("|", " · ")
        cpl1 = s1 / l1 if l1 else None
        cpl2 = s2 / l2 if l2 else None

        L.append(f"<b>{_html.escape(name)}</b>")
        if not sp1.get(num, {}).get("dialog", True):
            L.append(f"  💸 {_fmt_money(s1)}  |  ведёт в профиль — лидов с меткой "
                     f"не бывает, в CPL не входит")
            L.append("")
            continue

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
    if tot_profile:
        L.append(f"<i>Трафик в профиль: {_fmt_money(tot_profile)} — вне CPL, "
                 f"эти визиты приходят без метки и попадают в органику.</i>")
    L.append(f"<b>Итого:</b> {_fmt_money(tot_s1)}  |  лидов {tot_l1}"
             + (f" (было {tot_l2})" if have_prev else "")
             + f"  |  бронь/оплата {tot_c1}{tail}")

    if stopped:
        names = [(sp2.get(k, {}).get("name") or k.replace("|", " · ")) for k in stopped]
        if len(names) > 3:
            names = names[:3] + [f"и ещё {len(names) - 3}"]
        L.append(f"⏹ Не крутились на этой неделе: {', '.join(names)} "
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
        A.append(f"{sp1.get(num, {}).get('name') or num.replace('|', ' · ')}: "
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
