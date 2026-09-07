"""
Лиды из рекламы Meta по данным Salebot.

Зачем: с ~23.08.2026 Meta перестала отдавать в insights метрики переписок
(`onsite_conversion.messaging_conversation_started_7d` и соседние) — остались
только `messaging_block` и редкий `total_messaging_connection`. Расход (spend)
отдаётся по-прежнему. Поэтому знаменатель для CPL берём из Salebot: у клиента,
пришедшего с рекламы, заполнено поле `instagram_ads_data` — JSON с `ad_id`,
`ad_title`, `post_id`. Это и есть «начатая переписка», только с нашей стороны.

Источник — дневные выгрузки `~/salebot_dialog/<YYYY-MM-DD>/dialogs_*.json`,
которые пишет Analytics_salebot/scripts/salebot_daily_export.py в 21:05.

ВАЖНО про окно выгрузки: дамп за день D покрывает 21:00 D-1 → 21:00 D. Значит
клиенты, созданные в D после 21:00, лежат в дампе D+1. Чтобы календарный день D
был посчитан полностью, читаем дампы D..D+1 (на текущих объёмах «хвост» — 3-6
лидов в день, то есть до четверти дня).
"""

import os
import re
import json
import glob
import datetime as dt
from collections import defaultdict

SALEBOT_ROOT = "/home/user/salebot_dialog"

# CRM-воронка «Отдел продаж» (дублируем, чтобы не зависеть от Analytics_salebot)
BRON      = 66848694
TU_PAID   = 66877873
PAID      = 66848718
CANCEL    = 66848695
IGNORE    = 66848739
WORK      = 66848693
COMPLETED = 66848746

_RE_NUM = re.compile(r"№(\d+)")


def campaign_num(ad_title: str) -> str | None:
    """'№366. 22.07.26. Диалог. Дагестан…' → '366'."""
    m = _RE_NUM.search(ad_title or "")
    return m.group(1) if m else None


def short_name(title: str) -> str:
    """'№358. 06.05.26. Диалог. Питер+Карелия с 17.04. Широкая' → 'Питер+Карелия с 17.04'."""
    parts = (title or "").split(". ")
    return parts[3] if len(parts) >= 4 else (title or "")[:50]


def _ads_data(rec: dict) -> dict | None:
    raw = rec.get("instagram_ads_data")
    if not raw or raw in ("-", "None", "null", "{}"):
        return None
    try:
        d = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def _created(rec: dict) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(rec.get("created_at")))
    except Exception:
        return None


def _client_replies(rec: dict) -> int:
    """Реальные сообщения клиента — как в Analytics_salebot/scripts/daily_ad_leads.py."""
    h = rec.get("history_json") or []
    if isinstance(h, str):
        try:
            h = json.loads(h) if h.strip() else []
        except Exception:
            return 0
    n = 0
    for m in h:
        if (m.get("client_replica")
                and m.get("message_from_outside") in (0, None)
                and isinstance(m.get("text"), str) and m["text"].strip()
                and not m["text"].startswith("change_responsible")):
            n += 1
    return n


def dump_days_present(date_from: dt.date, date_to: dt.date,
                      tail_days: int = 1) -> tuple[list[str], list[str]]:
    """Какие дампы в диапазоне [date_from, date_to+tail_days] есть, а каких нет."""
    have, missing = [], []
    d = date_from
    while d <= date_to + dt.timedelta(days=tail_days):
        (have if glob.glob(os.path.join(SALEBOT_ROOT, d.isoformat(), "dialogs_*.json"))
         else missing).append(d.isoformat())
        d += dt.timedelta(days=1)
    return have, missing


def _load_records(date_from: dt.date, date_to: dt.date, tail_days: int,
                  ads_only: bool) -> dict[int, dict]:
    """Дедуплицированные записи из дампов date_from..date_to+tail_days.
    Побеждает самая свежая запись клиента — у неё актуальная стадия сделки."""
    latest: dict[int, dict] = {}
    d = date_from
    while d <= date_to + dt.timedelta(days=tail_days):
        for path in sorted(glob.glob(os.path.join(SALEBOT_ROOT, d.isoformat(), "dialogs_*.json"))):
            try:
                records = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            for rec in records:
                cid = rec.get("client_id")
                if cid is None:
                    continue
                if ads_only and not _ads_data(rec):
                    continue
                latest[cid] = rec  # более поздний файл перезаписывает
        d += dt.timedelta(days=1)
    return latest


def count_new_clients(date_from: dt.date, date_to: dt.date,
                      tail_days: int = 1) -> dict:
    """
    Все новые клиенты за период, с разбивкой реклама/органика.

    Нужно, чтобы отличать проблему рекламы от проблемы канала: если органика
    падает вместе с рекламой — дело не в Meta, а в связке Instagram→Salebot.
    """
    res = {"total": 0, "ads": 0, "organic": 0, "by_messenger": defaultdict(int)}
    for rec in _load_records(date_from, date_to, tail_days, ads_only=False).values():
        created = _created(rec)
        if not created or not (date_from <= created.date() <= date_to):
            continue
        res["total"] += 1
        res["ads" if _ads_data(rec) else "organic"] += 1
        res["by_messenger"][rec.get("messenger") or "—"] += 1
    res["by_messenger"] = dict(res["by_messenger"])
    return res


def load_leads(date_from: dt.date, date_to: dt.date, tail_days: int = 1) -> list[dict]:
    """
    Рекламные лиды, созданные в [date_from, date_to] включительно.

    Читает дампы date_from..date_to+tail_days (см. про «хвост» в докстринге
    модуля), дедуплицирует по client_id, оставляя САМУЮ СВЕЖУЮ запись — чтобы
    стадия сделки (deal_state_id) была актуальной, а не той, что была в день
    прихода.

    tail_days=1 закрывает штатный «хвост» 21:00–24:00. Изредка (<1% случаев)
    клиент не попадает даже в дамп своего дня и всплывает сильно позже — такие
    единицы не ловятся никаким разумным tail_days, это известная погрешность.
    """
    latest = _load_records(date_from, date_to, tail_days, ads_only=True)

    leads = []
    for rec in latest.values():
        created = _created(rec)
        if not created or not (date_from <= created.date() <= date_to):
            continue
        ads = _ads_data(rec) or {}
        title = (ads.get("ad_title") or "").strip()
        leads.append({
            "client_id":     rec.get("client_id"),
            "name":          rec.get("name"),
            "created":       created,
            "date":          created.date().isoformat(),
            "ad_id":         str(ads.get("ad_id") or ""),
            "ad_title":      title,
            "campaign_num":  campaign_num(title),
            "messenger":     rec.get("messenger"),
            "deal_state_id": rec.get("deal_state_id"),
            "replies":       _client_replies(rec),
        })
    return leads


def _blank_funnel() -> dict:
    return {"leads": 0, "replied": 0, "engaged": 0, "work": 0, "bron": 0,
            "tu_paid": 0, "paid": 0, "cancel": 0, "ignore": 0, "other": 0, "title": ""}


def _fold(acc: dict, lead: dict) -> None:
    acc["leads"] += 1
    if lead["replies"] >= 1:
        acc["replied"] += 1
    if lead["replies"] >= 2:
        acc["engaged"] += 1
    if not acc["title"]:
        acc["title"] = lead["ad_title"]
    sid = lead["deal_state_id"]
    key = {WORK: "work", BRON: "bron", TU_PAID: "tu_paid", PAID: "paid",
           CANCEL: "cancel", IGNORE: "ignore"}.get(sid, "other")
    acc[key] += 1


def group_by_campaign(leads: list[dict]) -> dict[str, dict]:
    out = defaultdict(_blank_funnel)
    for l in leads:
        _fold(out[l["campaign_num"] or "—"], l)
    return dict(out)


def group_by_ad(leads: list[dict]) -> dict[str, dict]:
    out = defaultdict(_blank_funnel)
    for l in leads:
        _fold(out[l["ad_id"] or "—"], l)
    return dict(out)


def conversions(f: dict) -> int:
    """Бронь + оплаты — то, ради чего реклама и крутится."""
    return f["bron"] + f["tu_paid"] + f["paid"]


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    to_ = dt.date.fromisoformat(a[1]) if len(a) > 1 else dt.date.today() - dt.timedelta(days=1)
    from_ = dt.date.fromisoformat(a[0]) if a else to_
    ls = load_leads(from_, to_)
    have, missing = dump_days_present(from_, to_)
    print(f"{from_} .. {to_}: лидов с меткой Meta — {len(ls)}"
          + (f"; НЕТ дампов: {missing}" if missing else ""))
    for num, f in sorted(group_by_campaign(ls).items(), key=lambda x: -x[1]["leads"]):
        print(f"  №{num:<6}{f['leads']:>4} лид.  завяз {f['engaged']:>3}  "
              f"конв {conversions(f):>3}  {short_name(f['title'])[:45]}")
