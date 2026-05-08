"""
Сквозная атрибуция: Meta Ads spend → CRM-воронка Salebot.

Логика:
  - Из Salebot-выгрузок берём ВСЕ диалоги с instagram_ads_data
  - Группируем по номеру кампании (№XXX из ad_title)
  - Джойним с расходами из latest.json (7д окно)
  - Показываем: расход Meta, диалогов Meta vs CRM, воронку до оплаты, реальный CPD
"""

import json
import glob
import os
import re
from collections import defaultdict

SALEBOT_ROOT = "/home/user/salebot_dialog"
META_LATEST  = os.path.join(os.path.dirname(__file__), "..", "data", "latest.json")

# CRM state IDs (дублируем здесь чтобы не зависеть от другого проекта)
_BRON      = 66848694
_TU_PAID   = 66877873
_PAID      = 66848718
_CANCEL    = 66848695
_IGNORE    = 66848739
_WORK      = 66848693
_COMPLETED = 66848746

_RE_NUM = re.compile(r'№(\d+)')


def _extract_num(title: str) -> str | None:
    m = _RE_NUM.search(title or "")
    return m.group(1) if m else None


def _load_meta_spend() -> dict[str, dict]:
    """Возвращает {campaign_num: {spend, dialogs_meta, name}} из latest.json (7д)."""
    try:
        d = json.load(open(META_LATEST, encoding="utf-8"))
    except Exception:
        return {}

    result = {}
    for c in d.get("insights_7d", []):
        num = _extract_num(c.get("campaign_name", ""))
        if not num:
            continue
        dialogs_meta = next(
            (int(a["value"]) for a in (c.get("actions") or [])
             if a["action_type"] == "onsite_conversion.total_messaging_connection"),
            0,
        )
        result[num] = {
            "spend":        float(c.get("spend", 0)),
            "dialogs_meta": dialogs_meta,
            "name":         c.get("campaign_name", ""),
            "objective":    c.get("objective", ""),
        }
    return result


def _load_crm_stats() -> dict[str, dict]:
    """
    Читает ВСЕ Salebot-выгрузки, дедуплицирует клиентов (последняя запись),
    возвращает {campaign_num: {dialogs, bron, tu_paid, paid, cancel, ignore, work, other, title}}.
    """
    all_files = sorted(glob.glob(os.path.join(SALEBOT_ROOT, "*/dialogs_*.json")))
    latest_by_client = {}  # client_id → последняя запись
    for fpath in all_files:
        try:
            records = json.load(open(fpath, encoding="utf-8"))
        except Exception:
            continue
        for d in records:
            cid = d.get("client_id")
            if cid is None:
                continue
            ads_raw = d.get("instagram_ads_data") or ""
            if not ads_raw or ads_raw in ("-", "None", "null", "{}"):
                continue
            # Сохраняем — более поздний файл перезапишет
            latest_by_client[cid] = d

    stats = defaultdict(lambda: {
        "dialogs": 0, "bron": 0, "tu_paid": 0, "paid": 0,
        "cancel": 0, "ignore": 0, "work": 0, "other": 0, "title": "",
    })

    for d in latest_by_client.values():
        ads_raw = d.get("instagram_ads_data") or ""
        try:
            ads = json.loads(ads_raw) if isinstance(ads_raw, str) else ads_raw
            title = ads.get("ad_title", "")
        except Exception:
            continue

        num = _extract_num(title)
        if not num:
            continue

        sid = d.get("deal_state_id")
        s = stats[num]
        s["dialogs"] += 1
        if not s["title"]:
            s["title"] = title

        if sid == _WORK:      s["work"]    += 1
        elif sid == _BRON:    s["bron"]    += 1
        elif sid == _TU_PAID: s["tu_paid"] += 1
        elif sid == _PAID:    s["paid"]    += 1
        elif sid == _CANCEL:  s["cancel"]  += 1
        elif sid == _IGNORE:  s["ignore"]  += 1
        else:                 s["other"]   += 1

    return dict(stats)


def _short_name(title: str) -> str:
    """'№358. 06.05.26. Диалог. Питер+Карелия из Минска с 17.04. Широкая. Рилс'
    → 'Питер+Карелия из Минска с 17.04'"""
    parts = title.split(". ")
    # parts[0]=№XXX, parts[1]=дата, parts[2]=тип, parts[3]=описание...
    if len(parts) >= 4:
        return parts[3]
    return title[:50]


def build_attribution() -> tuple[str, str]:
    """
    Возвращает (telegram_block, ai_summary).
    """
    meta  = _load_meta_spend()
    crm   = _load_crm_stats()

    # Объединяем все номера кампаний из обоих источников
    all_nums = sorted(set(meta.keys()) | set(crm.keys()),
                      key=lambda n: -(crm.get(n, {}).get("dialogs", 0)))

    # Фильтруем: только те, что есть в CRM (иначе нет смысла — нет данных)
    # Для трафиковых кампаний (нет диалогов) тоже не показываем
    rows = []
    for num in all_nums:
        c = crm.get(num, {})
        m = meta.get(num, {})
        if c.get("dialogs", 0) == 0:
            continue
        # Пропускаем явно трафиковые (нет dialogs_meta И нет бронь/оплат)
        conv = c.get("bron", 0) + c.get("tu_paid", 0) + c.get("paid", 0)
        if not m and conv == 0 and c.get("dialogs", 0) < 3:
            continue
        rows.append((num, c, m))

    if not rows:
        return "", ""

    # Находим диапазон дат Salebot
    all_files = sorted(glob.glob(os.path.join(SALEBOT_ROOT, "*/dialogs_*.json")))
    date_from = all_files[0].split("/")[-2] if all_files else "?"
    date_to   = all_files[-1].split("/")[-2] if all_files else "?"

    lines = [f"📊 <b>Атрибуция: Meta → CRM</b>  ({date_from} — {date_to})\n"]
    lines.append("Диалоги из рекламы, их статус в CRM и стоимость:\n")

    total_spend = 0.0
    total_crm_dialogs = 0
    total_conv = 0

    for num, c, m in rows:
        spend        = m.get("spend", 0.0)
        dialogs_meta = m.get("dialogs_meta", 0)
        dialogs_crm  = c["dialogs"]
        conv         = c["bron"] + c["tu_paid"] + c["paid"]
        conv_pct     = round(conv / dialogs_crm * 100, 1) if dialogs_crm else 0
        cpd_real     = round(spend / dialogs_crm, 1) if dialogs_crm and spend else None
        cpd_meta     = round(spend / dialogs_meta, 1) if dialogs_meta and spend else None

        # Название
        title_src = c.get("title") or m.get("name", "")
        name = _short_name(title_src) if title_src else f"кампания №{num}"

        total_spend        += spend
        total_crm_dialogs  += dialogs_crm
        total_conv         += conv

        lines.append(f"<b>№{num} — {name}</b>")

        # Строка расхода и CPD
        if spend:
            cpd_str = f"CPD реальный: <b>${cpd_real}</b>"
            if cpd_meta and cpd_meta != cpd_real:
                cpd_str += f" (Meta считает: ${cpd_meta})"
            lines.append(f"  💸 Расход 7д: ${spend:.0f}  |  {cpd_str}")

        # Строка диалогов
        dial_str = f"  💬 Диалогов в CRM: <b>{dialogs_crm}</b>"
        if dialogs_meta:
            dial_str += f"  (Meta API: {dialogs_meta})"
        lines.append(dial_str)

        # Воронка
        funnel_parts = []
        if c["work"]:    funnel_parts.append(f"🔄 работаем: {c['work']}")
        if conv:         funnel_parts.append(f"✅ бронь/оплата: {conv} ({conv_pct}%)")
        if c["cancel"]:  funnel_parts.append(f"❌ отмена: {c['cancel']}")
        if c["ignore"]:  funnel_parts.append(f"👻 игнор: {c['ignore']}")
        if funnel_parts:
            lines.append("  " + "  |  ".join(funnel_parts))

        lines.append("")

    # Итого
    total_cpd = round(total_spend / total_crm_dialogs, 1) if total_crm_dialogs and total_spend else None
    total_conv_pct = round(total_conv / total_crm_dialogs * 100, 1) if total_crm_dialogs else 0
    lines.append(f"<b>Итого:</b> расход 7д ${total_spend:.0f}  |  диалогов в CRM {total_crm_dialogs}  |  "
                 f"конверсий {total_conv} ({total_conv_pct}%)"
                 + (f"  |  CPD реальный ${total_cpd}" if total_cpd else ""))

    block = "\n".join(lines)

    # AI summary (компактный текст без HTML)
    summary_lines = [f"=== CRM-атрибуция рекламы ({date_from}–{date_to}) ==="]
    for num, c, m in rows:
        spend = m.get("spend", 0.0)
        conv  = c["bron"] + c["tu_paid"] + c["paid"]
        cpd   = round(spend / c["dialogs"], 1) if c["dialogs"] and spend else "н/д"
        title_src = c.get("title") or m.get("name", "")
        name = _short_name(title_src) if title_src else f"кампания №{num}"
        summary_lines.append(
            f"№{num} {name}: диалогов={c['dialogs']}, конв.={conv}, "
            f"отмен={c['cancel']}, CPD=${cpd}, расход7д=${spend:.0f}"
        )
    summary_lines.append(
        f"Всего: диалогов={total_crm_dialogs}, конв.={total_conv} ({total_conv_pct}%), расход=${total_spend:.0f}"
    )
    ai_summary = "\n".join(summary_lines)

    return block, ai_summary
