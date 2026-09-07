#!/usr/bin/env python3
"""
Ежедневный отчёт по рекламе Meta за предыдущий день.

Зачем отдельный скрипт, а не старый run_daily.py: тот тянул AI-аудит, выгорание
креативов и подписчиков IG — тяжёлый и был отключён. Здесь только то, что нужно,
чтобы каждое утро видеть состояние рекламы и ловить проблемы Meta:

  • расход и лиды за вчера, CPL, сравнение с нормой (7 дней до вчера);
  • разбивка по кампаниям + тревоги (расход без лидов, скачок CPL);
  • органика рядом с рекламой — чтобы отличить проблему Meta от проблемы
    канала Instagram→Salebot (в конце августа падало и то и другое);
  • блок «что отдаёт Meta»: показы/клики (значит, показы идут) и какие метрики
    переписок вернулись — с ~23.08.2026 Meta их не отдаёт, и по этому блоку
    будет видно, когда выдача восстановится.

Лиды берём из Salebot (метка instagram_ads_data), см. salebot_leads.py.

ВРЕМЯ ЗАПУСКА. Дамп Salebot за день D покрывает 21:00 D-1 → 21:00 D, поэтому
клиенты, пришедшие вечером, лежат в дампе D+1. Чтобы вчерашний день был полным,
запускать ПОСЛЕ вечерней выгрузки текущего дня (она стартует в 21:05 и идёт
10-15 мин) — крон стоит на 21:45. Часовой пояс рекламного кабинета —
Europe/Moscow, тот же UTC+3, что и у выгрузок, так что даты совпадают.

Запуск:
  python3 scripts/run_ads_daily.py               # за вчера, отправить в Telegram
  python3 scripts/run_ads_daily.py --date 2026-09-05
  python3 scripts/run_ads_daily.py --dry-run     # только напечатать
"""

import os
import sys
import json
import html
import argparse
import traceback
import datetime as dt
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import salebot_leads as sl
from crm_attribution import MESSAGING_ACTIONS, _actions, spend_by_campaign
from fetch_meta_ads import BASE_URL, AD_ACCOUNT_ID, _get_all_pages, \
    CAMPAIGN_INSIGHT_FIELDS, AD_INSIGHT_FIELDS
from send_telegram import send_message

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ARCHIVE_DIR = os.path.join(DATA_DIR, "ads_daily")

# «Дорогие» действия: их Meta считает честно и не режет (в отличие от метрик
# переписок, отключённых 20.08.2026), а низкоинтентная аудитория их не делает.
# На обвале 24.08 они просели вдвое-вчетверо ещё до того, как это стало видно
# по лидам, — поэтому годятся как ранний индикатор качества открутки.
QUALITY_ACTIONS = (
    "onsite_conversion.post_save",
    "post_reaction",
    "comment",
)

# Кампания сожгла столько и не дала ни одного лида → тревога.
NO_LEAD_SPEND_ALERT = 30.0
# Во сколько раз CPL должен превысить норму, чтобы это считалось скачком.
CPL_SPIKE_RATIO = 2.0

_WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def _insights(level: str, fields: str, since: dt.date, until: dt.date) -> list[dict]:
    """Инсайты за явный диапазон дат (не date_preset — чтобы дата была точной)."""
    return _get_all_pages(
        f"{BASE_URL}/{AD_ACCOUNT_ID}/insights",
        {
            "fields": fields,
            "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
            "level": level,
            "limit": 200,
        },
    )


def _money(v: float) -> str:
    return f"${v:,.0f}".replace(",", " ") if abs(v) >= 10 else f"${v:.1f}"


def _quality_per_1000(rows: list[dict]) -> float:
    """Сохранения + реакции + комментарии на 1000 показов."""
    imp = _sum(rows, "impressions")
    if not imp:
        return 0.0
    total = 0
    for r in rows:
        acts = _actions(r)
        total += sum(acts.get(a, 0) for a in QUALITY_ACTIONS)
    return 1000 * total / imp


def _sum(rows: list[dict], field: str) -> float:
    total = 0.0
    for r in rows:
        try:
            total += float(r.get(field) or 0)
        except Exception:
            pass
    return total


def collect(day: dt.date) -> dict:
    """Собирает всё за день `day` плюс норму по 7 дням до него."""
    base_from, base_to = day - dt.timedelta(days=7), day - dt.timedelta(days=1)

    camps_day = _insights("campaign", CAMPAIGN_INSIGHT_FIELDS, day, day)
    ads_day = _insights("ad", AD_INSIGHT_FIELDS, day, day)
    camps_base = _insights("campaign", CAMPAIGN_INSIGHT_FIELDS, base_from, base_to)

    leads_day = sl.load_leads(day, day)
    leads_base = sl.load_leads(base_from, base_to)
    clients_day = sl.count_new_clients(day, day)
    clients_base = sl.count_new_clients(base_from, base_to)

    _, missing = sl.dump_days_present(day, day)

    msg_actions = defaultdict(int)
    for r in camps_day:
        for a, v in _actions(r).items():
            if "messag" in a:
                msg_actions[a] += v

    clicks_base = int(_sum(camps_base, "clicks"))

    return {
        "day": day.isoformat(),
        "spend": _sum(camps_day, "spend"),
        "impressions": int(_sum(camps_day, "impressions")),
        "clicks": int(_sum(camps_day, "clicks")),
        "leads": len(leads_day),
        "by_campaign_spend": spend_by_campaign(camps_day),
        "by_campaign_leads": sl.group_by_campaign(leads_day),
        "clients": clients_day,
        "baseline": {
            "from": base_from.isoformat(), "to": base_to.isoformat(),
            "spend_per_day": _sum(camps_base, "spend") / 7,
            "leads_per_day": len(leads_base) / 7,
            "organic_per_day": clients_base["organic"] / 7,
            "clicks": clicks_base,
            # Клик по «написать в директ» — это уже заявленное намерение. Доля
            # кликов, дошедших до диалога, ловит поломку связки Instagram→Salebot
            # там, где расход и CTR ещё выглядят нормально. Именно этот показатель
            # вскрыл обвал 22-24.08.2026: 4-6 на 100 кликов → 1.1.
            "leads_per_100_clicks": (100 * len(leads_base) / clicks_base) if clicks_base else 0,
            "quality_per_1000": _quality_per_1000(camps_base),
            "by_campaign_spend": spend_by_campaign(camps_base),
            "by_campaign_leads": sl.group_by_campaign(leads_base),
        },
        "quality_per_1000": _quality_per_1000(camps_day),
        "meta_messaging": dict(msg_actions),
        "ads_count": len(ads_day),
        "missing_dumps": missing,
    }


def _alerts(d: dict) -> list[str]:
    out = []
    b = d["baseline"]

    cpl = d["spend"] / d["leads"] if d["leads"] else None
    cpl_base = (b["spend_per_day"] / b["leads_per_day"]) if b["leads_per_day"] else None

    if d["spend"] > 0 and d["leads"] == 0:
        out.append(f"Расход {_money(d['spend'])} и <b>ни одного лида</b> за день.")
    elif cpl and cpl_base and cpl > cpl_base * CPL_SPIKE_RATIO:
        out.append(f"CPL {_money(cpl)} — в {cpl / cpl_base:.1f}× дороже нормы "
                   f"({_money(cpl_base)}).")

    l100 = 100 * d["leads"] / d["clicks"] if d["clicks"] else 0
    l100_base = b["leads_per_100_clicks"]
    if d["clicks"] >= 200 and l100_base >= 1 and l100 < l100_base * 0.5:
        out.append(f"Из 100 кликов доходит до диалога {l100:.1f} против нормы "
                   f"{l100_base:.1f} — клики есть, диалогов нет. Проверить связку "
                   f"Instagram→Salebot, а не креативы.")

    q, q_base = d["quality_per_1000"], b["quality_per_1000"]
    if d["impressions"] >= 20000 and q_base >= 0.5 and q < q_base * 0.6:
        out.append(f"Качество аудитории {q:.2f} против нормы {q_base:.2f} — Meta льёт "
                   f"на низкоинтентных. Проверить, регистрируется ли событие конверсии "
                   f"по переписке.")

    if b["leads_per_day"] >= 3 and d["leads"] < b["leads_per_day"] * 0.5:
        out.append(f"Лидов {d['leads']} против нормы {b['leads_per_day']:.1f}/день "
                   f"— падение больше чем вдвое.")

    # Органика падает вместе с рекламой → проблема не в Meta, а в канале.
    if (b["organic_per_day"] >= 3 and d["clients"]["organic"] < b["organic_per_day"] * 0.5
            and d["leads"] < max(b["leads_per_day"] * 0.5, 1)):
        out.append("Органика упала так же, как реклама — похоже на проблему связки "
                   "Instagram→Salebot, а не на Meta.")

    for num, sp in sorted(d["by_campaign_spend"].items(), key=lambda x: -x[1]["spend"]):
        got = (d["by_campaign_leads"].get(num) or {}).get("leads", 0)
        if sp["spend"] >= NO_LEAD_SPEND_ALERT and got == 0:
            name = sl.short_name(sp["name"]) or f"№{num}"
            out.append(f"№{num} {html.escape(name)}: {_money(sp['spend'])} без лидов.")
        if sp["spend"] > 0 and sp["impressions"] == 0:
            out.append(f"№{num}: расход есть, показов нет — проверить открутку.")

    if d["missing_dumps"]:
        out.append(f"Нет выгрузки Salebot за {', '.join(d['missing_dumps'])} — "
                   f"вечерние лиды не учтены, цифры занижены.")
    return out


def render(d: dict) -> str:
    day = dt.date.fromisoformat(d["day"])
    b = d["baseline"]
    cpl = d["spend"] / d["leads"] if d["leads"] else None
    cpl_base = (b["spend_per_day"] / b["leads_per_day"]) if b["leads_per_day"] else None

    L = [f"📣 <b>Реклама Meta за {day.strftime('%d.%m')} ({_WD[day.weekday()]})</b>", ""]
    L.append(f"💸 Расход <b>{_money(d['spend'])}</b>  ·  "
             f"👥 лидов <b>{d['leads']}</b>  ·  "
             f"CPL <b>{_money(cpl) if cpl else '—'}</b>")
    L.append(f"<i>норма за 7 дней ({b['from'][8:10]}.{b['from'][5:7]}–{b['to'][8:10]}.{b['to'][5:7]}): "
             f"{_money(b['spend_per_day'])}/день · {b['leads_per_day']:.1f} лид./день · "
             f"CPL {_money(cpl_base) if cpl_base else '—'}</i>")
    l100 = 100 * d["leads"] / d["clicks"] if d["clicks"] else 0
    L.append(f"🖱 Из 100 кликов в диалог: <b>{l100:.1f}</b> "
             f"<i>(норма {b['leads_per_100_clicks']:.1f})</i>")
    L.append(f"💎 Качество аудитории: <b>{d['quality_per_1000']:.2f}</b> "
             f"<i>(норма {b['quality_per_1000']:.2f}; сохранения+реакции+комментарии "
             f"на 1000 показов)</i>")
    L.append(f"🌱 Органика: <b>{d['clients']['organic']}</b> "
             f"<i>(норма {b['organic_per_day']:.1f}/день)</i>")

    alerts = _alerts(d)
    if alerts:
        L.append("\n⚠️ <b>Тревоги</b>")
        L += [f"• {a}" for a in alerts]

    rows = sorted(
        set(d["by_campaign_spend"]) | set(d["by_campaign_leads"]),
        key=lambda n: -d["by_campaign_spend"].get(n, {}).get("spend", 0),
    )
    if rows:
        L.append("\n<b>По кампаниям</b>")
        for num in rows:
            sp = d["by_campaign_spend"].get(num, {})
            f = d["by_campaign_leads"].get(num) or sl._blank_funnel()
            spend = sp.get("spend", 0.0)
            name = sl.short_name(f["title"] or sp.get("name", "")) or f"кампания №{num}"
            c = f"{_money(spend / f['leads'])}" if f["leads"] and spend else "—"
            L.append(f"• <b>№{num}</b> {html.escape(name)[:38]} — {_money(spend)} · "
                     f"{f['leads']} лид. · CPL {c}"
                     + (f" · 💬{f['engaged']}" if f["engaged"] else ""))

    L.append("\n🔌 <b>Что отдаёт Meta</b>")
    ctr = 100 * d["clicks"] / d["impressions"] if d["impressions"] else 0
    L.append(f"показы {d['impressions']:,}".replace(",", " ")
             + f" · клики {d['clicks']} · CTR {ctr:.2f}%")
    started = d["meta_messaging"].get("onsite_conversion.messaging_conversation_started_7d", 0)
    if started:
        L.append(f"✅ «Начатые переписки» снова приходят: <b>{started}</b> "
                 f"(Salebot насчитал {d['leads']}).")
    else:
        got = ", ".join(f"{a.split('.')[-1]}={v}" for a, v in sorted(d["meta_messaging"].items())) or "ничего"
        L.append(f"⛔ «Начатые переписки» Meta не отдаёт (с ~23.08). Из переписок пришло: {got}.")
        L.append("<i>Поэтому лиды выше — из Salebot по метке объявления.</i>")

    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Дневной отчёт по рекламе Meta за вчера.")
    ap.add_argument("--date", help="День YYYY-MM-DD (по умолчанию вчера).")
    ap.add_argument("--dry-run", action="store_true", help="Не отправлять в Telegram.")
    args = ap.parse_args()

    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today() - dt.timedelta(days=1)

    try:
        data = collect(day)
        text = render(data)

        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        with open(os.path.join(ARCHIVE_DIR, f"{day.isoformat()}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if args.dry_run:
            print(text)
        else:
            send_message(text, parse_mode="HTML")
            print(f"[run_ads_daily] Отправлено за {day}.")
    except Exception:
        err = traceback.format_exc()
        print(f"[run_ads_daily] ERROR:\n{err}", file=sys.stderr)
        if not args.dry_run:
            try:
                send_message(f"❌ Дневной отчёт по рекламе — ошибка\n\n{err[-800:]}")
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
