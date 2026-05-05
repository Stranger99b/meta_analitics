"""Hybrid creative burnout detector.

Dialog campaigns  → primary signal: CPD (cost per dialog) growth
Traffic campaigns → primary signal: CTR drop vs 7-day average
Both              → secondary signal: frequency
"""


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


def _is_dialog(campaign_name):
    n = (campaign_name or "").lower()
    return "диалог" in n or "dialog" in n


# Thresholds — traffic campaigns (CTR-based)
CTR_DROP_CRITICAL = 0.70   # CTR < 70% of 7d avg → critical
CTR_DROP_WARNING  = 0.85   # CTR < 85% of 7d avg → warning
MIN_IMPRESSIONS   = 500    # minimum impressions to analyze traffic ad

# Thresholds — dialog campaigns (CPD-based)
CPD_CRITICAL      = 2.0    # CPD grew to 2x of 7d avg → critical
CPD_WARNING       = 1.5    # CPD grew to 1.5x of 7d avg → warning
MIN_DIALOGS_7D    = 5      # minimum 7d dialogs to establish CPD baseline
MIN_SPEND_DIALOG  = 3.0    # minimum $ spend yesterday to analyze dialog ad

# Thresholds — both types
FREQ_WARNING      = 3.0
FREQ_CRITICAL     = 4.0


def detect_burnout(ad_rows_yesterday, ad_rows_7d):
    """
    Hybrid burnout detection:
    - Dialog campaigns: CPD growth vs 7d baseline (fallback to CTR if no dialog history)
    - Traffic campaigns: CTR drop vs 7d average
    Returns list of dicts sorted by severity (highest first).
    """
    # Build 7d map: ad_id → aggregated metrics
    map_7d = {}
    for r in ad_rows_7d:
        aid  = r.get("ad_id") or r.get("ad_name")
        name = r.get("ad_name", aid)
        camp = r.get("campaign_name", "")
        impr = _i(r.get("impressions"))
        freq = _f(r.get("frequency", 0))
        dialogs = _get_action(r.get("actions"), "onsite_conversion.total_messaging_connection")
        if aid not in map_7d:
            map_7d[aid] = {
                "name": name, "camp": camp,
                "impr_sum": 0, "clicks_sum": 0,
                "spend_sum": 0.0, "dialogs_sum": 0, "freq": 0.0,
            }
        map_7d[aid]["impr_sum"]    += impr
        map_7d[aid]["clicks_sum"]  += _i(r.get("clicks", 0))
        map_7d[aid]["spend_sum"]   += _f(r.get("spend", 0))
        map_7d[aid]["dialogs_sum"] += dialogs
        map_7d[aid]["freq"]         = max(map_7d[aid]["freq"], freq)

    for v in map_7d.values():
        v["ctr_7d"] = v["clicks_sum"] / v["impr_sum"] * 100 if v["impr_sum"] else 0
        d7 = v["dialogs_sum"]
        v["cpd_7d"] = v["spend_sum"] / d7 if d7 >= MIN_DIALOGS_7D else None

    results = []
    for r in ad_rows_yesterday:
        aid      = r.get("ad_id") or r.get("ad_name")
        name     = r.get("ad_name", aid)
        camp     = r.get("campaign_name", "")
        adset    = r.get("adset_name", "")
        ctr_now  = _f(r.get("ctr"))
        impr_now = _i(r.get("impressions"))
        freq_now = _f(r.get("frequency", 0))
        spend    = _f(r.get("spend"))
        dialogs  = _get_action(r.get("actions"), "onsite_conversion.total_messaging_connection")
        is_dialog_camp = _is_dialog(camp)

        # Minimum data filter
        if is_dialog_camp:
            if spend < MIN_SPEND_DIALOG:
                continue
        else:
            if impr_now < MIN_IMPRESSIONS:
                continue

        v7       = map_7d.get(aid, {})
        ctr_7d   = v7.get("ctr_7d", 0)
        cpd_7d   = v7.get("cpd_7d")       # None = not enough dialog history
        freq_7d  = v7.get("freq", freq_now)
        dialogs_7d = v7.get("dialogs_sum", 0)

        severity = 0
        flags    = []
        cpd_now  = None

        if is_dialog_camp:
            # ── Dialog campaign: CPD-based ──────────────────────
            if cpd_7d is not None:
                # Have reliable 7d baseline
                if dialogs == 0:
                    # Spent money, got zero dialogs — historically worked
                    severity += 3
                    flags.append(
                        f"0 диалогов при расходе ${spend:.2f}"
                        f" (7д avg CPD ${cpd_7d:.2f}, всего диалогов за 7д: {dialogs_7d})"
                    )
                else:
                    cpd_now = spend / dialogs
                    ratio = cpd_now / cpd_7d
                    if ratio >= CPD_CRITICAL:
                        severity += 3
                        flags.append(
                            f"CPD вырос до ${cpd_now:.2f}"
                            f" (7д avg ${cpd_7d:.2f}, +{(ratio-1)*100:.0f}%)"
                        )
                    elif ratio >= CPD_WARNING:
                        severity += 1
                        flags.append(
                            f"CPD растёт ${cpd_now:.2f} vs 7д ${cpd_7d:.2f}"
                            f" (+{(ratio-1)*100:.0f}%)"
                        )
            else:
                # No dialog baseline — fall back to CTR
                if ctr_7d > 0:
                    ratio = ctr_now / ctr_7d
                    if ratio < CTR_DROP_CRITICAL:
                        severity += 2
                        flags.append(
                            f"CTR упал до {ctr_now:.2f}%"
                            f" (7д avg {ctr_7d:.2f}%, мало диалогов для CPD-анализа)"
                        )
                    elif ratio < CTR_DROP_WARNING:
                        severity += 1
                        flags.append(f"CTR снижается {ctr_now:.2f}% vs 7д {ctr_7d:.2f}%")
        else:
            # ── Traffic campaign: CTR-based ─────────────────────
            if ctr_7d > 0:
                ratio = ctr_now / ctr_7d
                if ratio < CTR_DROP_CRITICAL:
                    severity += 3
                    flags.append(
                        f"CTR упал до {ctr_now:.2f}%"
                        f" (7д avg {ctr_7d:.2f}%, -{(1-ratio)*100:.0f}%)"
                    )
                elif ratio < CTR_DROP_WARNING:
                    severity += 1
                    flags.append(f"CTR снижается {ctr_now:.2f}% vs 7д {ctr_7d:.2f}%")

        # ── Frequency — both types ───────────────────────────
        freq_max = max(freq_now, freq_7d)
        if freq_max >= FREQ_CRITICAL:
            severity += 2
            flags.append(f"Критичная частота {freq_max:.1f}")
        elif freq_max >= FREQ_WARNING:
            severity += 1
            flags.append(f"Частота {freq_max:.1f} (зона риска ≥3.0)")

        if severity == 0 or not flags:
            continue

        level     = "🔴 КРИТИЧНО" if severity >= 3 else "🟡 ВНИМАНИЕ"
        camp_type = "💬 Диалог"   if is_dialog_camp else "👁 Трафик"

        results.append({
            "level":      level,
            "severity":   severity,
            "camp_type":  camp_type,
            "name":       name,
            "adset":      adset,
            "camp":       camp,
            "ctr_now":    ctr_now,
            "ctr_7d":     ctr_7d,
            "cpd_now":    cpd_now,
            "cpd_7d":     cpd_7d,
            "dialogs":    dialogs,
            "dialogs_7d": dialogs_7d,
            "freq":       freq_max,
            "spend":      spend,
            "flags":      flags,
        })

    return sorted(results, key=lambda x: x["severity"], reverse=True)


def format_burnout_block(burnout_results):
    """Returns Telegram-formatted burnout section."""
    if not burnout_results:
        return "━━━━ ВЫГОРАНИЕ КРЕАТИВОВ ━━━━\n  ✅ Признаков выгорания нет"

    lines = ["━━━━ ВЫГОРАНИЕ КРЕАТИВОВ ━━━━"]
    for b in burnout_results[:6]:
        lines.append(f"\n{b['level']} {b['camp_type']}")
        if b["adset"]:
            lines.append(f"  📂 Адсет: *{b['adset'][:55]}*")
        lines.append(f"  🎨 Крео: {b['name'][:55]}")
        for flag in b["flags"]:
            lines.append(f"  ⚠️ {flag}")
        spend_line = f"  💰 Расход: ${b['spend']:.2f}"
        if b["camp_type"] == "💬 Диалог":
            if b["cpd_now"]:
                spend_line += f"  |  💬 {b['dialogs']} диал. (CPD ${b['cpd_now']:.2f})"
            elif b["dialogs"] == 0:
                spend_line += f"  |  💬 0 диалогов"
        else:
            if b["dialogs"]:
                spend_line += f"  |  💬 {b['dialogs']} диал."
        lines.append(spend_line)

    critical = sum(1 for b in burnout_results if b["severity"] >= 3)
    warning  = sum(1 for b in burnout_results if b["severity"] < 3)
    parts = []
    if critical: parts.append(f"🔴 {critical} критичных")
    if warning:  parts.append(f"🟡 {warning} под наблюдением")
    lines.append("\n  " + "  |  ".join(parts))

    return "\n".join(lines)


def burnout_ai_summary(burnout_results):
    """Returns text summary for Claude AI prompt."""
    if not burnout_results:
        return "Выгорания креативов не обнаружено."
    lines = [
        "=== ВЫГОРАНИЕ КРЕАТИВОВ (гибридный анализ) ===",
        "Диалоговые кампании: сигнал = рост CPD (стоимости диалога)",
        "Трафиковые кампании: сигнал = падение CTR",
        "ВАЖНО: при рекомендациях всегда указывай пару Адсет + Крео",
    ]
    for b in burnout_results:
        adset_part = f"Адсет: {b['adset']} → " if b["adset"] else ""
        if b["camp_type"] == "💬 Диалог" and b["cpd_7d"] is not None:
            metric = (
                f"CPD вчера ${b['cpd_now']:.2f} vs 7д avg ${b['cpd_7d']:.2f}"
                if b["cpd_now"] else
                f"0 диалогов при расходе ${b['spend']:.2f} (7д avg CPD ${b['cpd_7d']:.2f})"
            )
        else:
            metric = f"CTR вчера {b['ctr_now']:.2f}% vs 7д avg {b['ctr_7d']:.2f}%"
        lines.append(
            f"• [{b['level']}] [{b['camp_type']}] {adset_part}Крео: {b['name']} | "
            f"{metric} | частота {b['freq']:.1f} | расход ${b['spend']:.2f} | диалогов {b['dialogs']}"
        )
    return "\n".join(lines)
