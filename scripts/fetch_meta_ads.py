"""Fetches campaign, adset and ad data from Meta Marketing API."""

import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API_VERSION = "v19.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
ACCESS_TOKEN = os.environ["META_ACCESS_TOKEN"]
AD_ACCOUNT_ID = os.environ["META_AD_ACCOUNT_ID"]

CAMPAIGN_INSIGHT_FIELDS = (
    "campaign_id,campaign_name,spend,impressions,clicks,ctr,cpc,cpm,"
    "reach,frequency,actions,action_values,objective"
)

ADSET_INSIGHT_FIELDS = (
    "adset_id,adset_name,campaign_name,campaign_id,"
    "spend,impressions,clicks,ctr,cpc,frequency,"
    "optimization_goal,actions"
)

AD_INSIGHT_FIELDS = (
    "ad_id,ad_name,adset_name,campaign_name,"
    "spend,impressions,clicks,ctr,cpc,frequency,actions"
)


TIMEOUT = 60
MAX_RETRIES = 3


class MetaAPIError(RuntimeError):
    """Ошибка Meta API с человеческим текстом и БЕЗ токена.

    requests кладёт в текст HTTPError весь URL запроса, а токен едет в query-строке,
    поэтому голый raise_for_status() и утекает секрет, и не показывает причину:
    в теле ответа лежит вменяемое объяснение, а в исключении — только «400 Bad Request».
    """


def _raise_for_status(r):
    if r.status_code < 400:
        return
    try:
        e = r.json().get("error", {}) or {}
    except Exception:
        e = {}
    msg = e.get("message") or (r.text or "")[:200]
    code, sub = e.get("code"), e.get("error_subcode")
    hint = ""
    if code == 190:
        hint = ("  → Токен Meta недействителен. Получить новый и применить: "
                "python3 scripts/update_token.py НОВЫЙ_ТОКЕН")
    raise MetaAPIError(
        f"Meta API {r.status_code}"
        + (f" (code {code}" + (f"/{sub}" if sub else "") + ")" if code else "")
        + f": {msg}{hint}"
    )


def _get(url, params, _retry=0):
    params = dict(params, access_token=ACCESS_TOKEN)
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        _raise_for_status(r)
        return r.json()
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        if _retry < MAX_RETRIES:
            wait = 2 ** _retry * 5  # 5s, 10s, 20s
            print(f"[fetch] Timeout/connection error, retry {_retry + 1}/{MAX_RETRIES} in {wait}s... ({e})")
            time.sleep(wait)
            return _get(url, params, _retry + 1)
        raise


def _get_page(url, _retry=0):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        _raise_for_status(r)
        return r.json()
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        if _retry < MAX_RETRIES:
            wait = 2 ** _retry * 5
            print(f"[fetch] Timeout on pagination, retry {_retry + 1}/{MAX_RETRIES} in {wait}s...")
            time.sleep(wait)
            return _get_page(url, _retry + 1)
        raise


def _get_all_pages(url, params):
    results = []
    data = _get(url, params)
    results.extend(data.get("data", []))
    while "paging" in data and "next" in data.get("paging", {}):
        data = _get_page(data["paging"]["next"])
        results.extend(data.get("data", []))
    return results


def ad_accounts() -> list[tuple[str, str]]:
    """
    Кабинеты для отчётов: [(act_id, метка)].

    Берётся из META_AD_ACCOUNTS вида «act_123:Беларусь,act_456:Личный».
    Если переменной нет — один кабинет из META_AD_ACCOUNT_ID, как было раньше.
    Понадобилось 11.09.2026: старый кабинет остановлен, бюджет ушёл в два новых,
    и отчёт по одному кабинету стал показывать расход 0 при живых лидах.
    """
    raw = os.environ.get("META_AD_ACCOUNTS", "").strip()
    if not raw:
        return [(AD_ACCOUNT_ID, "")]
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        acct, _, label = part.partition(":")
        out.append((acct.strip(), label.strip()))
    return out


def fetch_account_info():
    return _get(f"{BASE_URL}/{AD_ACCOUNT_ID}", {"fields": "name,currency,timezone_name"})


def fetch_campaign_insights(date_preset):
    return _get_all_pages(
        f"{BASE_URL}/{AD_ACCOUNT_ID}/insights",
        {"fields": CAMPAIGN_INSIGHT_FIELDS, "date_preset": date_preset, "level": "campaign", "limit": 100},
    )


def fetch_adset_insights(date_preset="yesterday"):
    return _get_all_pages(
        f"{BASE_URL}/{AD_ACCOUNT_ID}/insights",
        {"fields": ADSET_INSIGHT_FIELDS, "date_preset": date_preset, "level": "adset", "limit": 200},
    )


def fetch_ad_insights(date_preset="yesterday"):
    return _get_all_pages(
        f"{BASE_URL}/{AD_ACCOUNT_ID}/insights",
        {"fields": AD_INSIGHT_FIELDS, "date_preset": date_preset, "level": "ad", "limit": 200},
    )


def fetch_and_save(date_preset="yesterday"):
    print(f"[fetch] Fetching Meta Ads data ({date_preset})...")

    account = fetch_account_info()
    yesterday = fetch_campaign_insights("yesterday")
    week = fetch_campaign_insights("last_7d")
    prev_week = fetch_campaign_insights("last_14d")  # last 14d includes prev 7d
    adsets = fetch_adset_insights("last_7d")
    ads_yesterday = fetch_ad_insights("yesterday")
    ads_7d        = fetch_ad_insights("last_7d")

    result = {
        "fetched_at": datetime.now().isoformat(),
        "date_preset": date_preset,
        "account": account,
        "insights_yesterday": yesterday,
        "insights_7d": week,
        "insights_14d": prev_week,
        "adset_insights_7d": adsets,
        "ad_insights_yesterday": ads_yesterday,
        "ad_insights_7d": ads_7d,
    }

    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    archive_dir = os.path.join(data_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(data_dir, "latest.json")
    archive_path = os.path.join(archive_dir, f"{date_str}.json")

    for path in (out_path, archive_path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        f"[fetch] Saved: {len(yesterday)} campaigns yesterday, "
        f"{len(adsets)} adsets (7d), {len(ads_yesterday)} ads yesterday, {len(ads_7d)} ads (7d)"
    )
    return result


if __name__ == "__main__":
    fetch_and_save()
