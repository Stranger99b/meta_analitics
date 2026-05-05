"""Detects creative burnout by comparing per-ad CTR: yesterday vs 7-day average."""


def _f(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _i(val):
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _get_action(actions, *atypes):
    if not actions:
        return 0
    return sum(_i(a.get("value", 0)) for a in actions if a.get("action_type") in atypes)


# Burnout thresholds
CTR_DROP_CRITICAL = 0.70   # CTR fell to <70% of 7d avg → critical
CTR_DROP_WARNING  = 0.85   # CTR fell to <85% of 7d avg → warning
FREQ_WARNING      = 3.0    # frequency ≥ 3.0 → risk zone
FREQ_CRITICAL     = 4.0    # frequency ≥ 4.0 → critical
MIN_IMPRESSIONS   = 500    # skip ads with too few impressions


def detect_burnout(ad_rows_yesterday, ad_rows_7d):
    """
    Compares per-ad CTR for yesterday vs 7-day average.
    Returns list of dicts sorted by severity.
    """
    # Build 7d map: ad_id → avg CTR, total impressions, frequency
    map_7d = {}
    for r in ad_rows_7d:
        aid = r.get("ad_id") or r.get("ad_name")
        name = r.get("ad_name", aid)
        camp = r.get("campaign_name", "")
        ctr  = _f(r.get("ctr"))
        impr = _i(r.get("impressions"))
        freq = _f(r.get("frequency", 0))
        if aid not in map_7d:
            map_7d[aid] = {"name": name, "camp": camp,
                           "impr_sum": 0, "clicks_sum": 0, "freq": freq}
        map_7d[aid]["impr_sum"]  += impr
        map_7d[aid]["clicks_sum"] += int(_f(r.get("clicks", 0)))
        map_7d[aid]["freq"] = max(map_7d[aid]["freq"], freq)

    # Compute 7d avg CTR
    for aid, v in map_7d.items():
        v["ctr_7d"] = v["clicks_sum"] / v["impr_sum"] * 100 if v["impr_sum"] else 0

    results = []
    for r in ad_rows_yesterday:
        aid   = r.get("ad_id") or r.get("ad_name")
        name  = r.get("ad_name", aid)
        camp  = r.get("campaign_name", "")
        adset = r.get("adset_name", "")
        ctr_now  = _f(r.get("ctr"))
        impr_now = _i(r.get("impressions"))
        freq_now = _f(r.get("frequency", 0))
        spend    = _f(r.get("spend"))
        dialogs  = _get_action(r.get("actions"), "onsite_conversion.total_messaging_connection")

        if impr_now < MIN_IMPRESSIONS:
            continue

        v7 = map_7d.get(aid, {})
        ctr_7d = v7.get("ctr_7d", 0)
        freq_7d = v7.get("freq", freq_now)

        # Score severity
        severity = 0
        flags = []

        if ctr_7d > 0:
            ratio = ctr_now / ctr_7d
            if ratio < CTR_DROP_CRITICAL:
                severity += 3
                flags.append(f"CTR упал до {ctr_now:.2f}% (7д avg {ctr_7d:.2f}%, -{(1-ratio)*100:.0f}%)")
            elif ratio < CTR_DROP_WARNING:
                severity += 1
                flags.append(f"CTR снижается {ctr_now:.2f}% vs 7д {ctr_7d:.2f}%")

        if freq_7d >= FREQ_CRITICAL or freq_now >= FREQ_CRITICAL:
            severity += 2
            flags.append(f"Критичная частота {max(freq_now, freq_7d):.1f}")
        elif freq_7d >= FREQ_WARNING or freq_now >= FREQ_WARNING:
            severity += 1
            flags.append(f"Частота {max(freq_now, freq_7d):.1f} (зона риска ≥3.0)")

        if severity == 0:
            continue

        level = "🔴 КРИТИЧНО" if severity >= 3 else "🟡 ВНИМАНИЕ"

        results.append({
            "level": level,
            "severity": severity,
            "name": name,
            "adset": adset,
            "camp": camp,
            "ctr_now": ctr_now,
            "ctr_7d": ctr_7d,
            "freq": max(freq_now, freq_7d),
            "spend": spend,
            "dialogs": dialogs,
            "flags": flags,
        })

    return sorted(results, key=lambda x: x["severity"], reverse=True)


def format_burnout_block(burnout_results):
    """Returns Telegram-formatted burnout section or empty string."""
    if not burnout_results:
        return "━━━━ ВЫГОРАНИЕ КРЕАТИВОВ ━━━━\n  ✅ Признаков выгорания нет"

    lines = ["━━━━ ВЫГОРАНИЕ КРЕАТИВОВ ━━━━"]
    for b in burnout_results[:6]:  # max 6 entries to keep message size
        lines.append(f"\n{b['level']}")
        if b["adset"]:
            lines.append(f"  📂 Адсет: *{b['adset'][:55]}*")
        lines.append(f"  🎨 Крео: {b['name'][:55]}")
        lines.append(f"  🏷 {b['camp'][:45]}")
        for flag in b["flags"]:
            lines.append(f"  ⚠️ {flag}")
        lines.append(
            f"  💰 Расход: {b['spend']:.2f}"
            + (f"  |  💬 {b['dialogs']} диалогов" if b["dialogs"] else "")
        )

    critical = sum(1 for b in burnout_results if b["severity"] >= 3)
    warning  = sum(1 for b in burnout_results if b["severity"] < 3)
    summary  = []
    if critical: summary.append(f"🔴 {critical} критичных")
    if warning:  summary.append(f"🟡 {warning} под наблюдением")
    lines.append("\n  " + "  |  ".join(summary))

    return "\n".join(lines)


def burnout_ai_summary(burnout_results):
    """Returns text summary for Claude AI prompt."""
    if not burnout_results:
        return "Выгорания креативов не обнаружено."
    lines = [
        "=== ВЫГОРАНИЕ КРЕАТИВОВ ===",
        "ВАЖНО: при рекомендациях всегда указывай пару Адсет + Крео",
    ]
    for b in burnout_results:
        adset_part = f"Адсет: {b['adset']} → " if b["adset"] else ""
        lines.append(
            f"• [{b['level']}] {adset_part}Крео: {b['name']} | "
            f"CTR вчера {b['ctr_now']:.2f}% vs 7д {b['ctr_7d']:.2f}% | "
            f"частота {b['freq']:.1f} | расход {b['spend']:.2f} | диалогов {b['dialogs']}"
        )
    return "\n".join(lines)
