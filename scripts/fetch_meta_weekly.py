"""Fetches two weeks of Meta Ads data for weekly comparison report."""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API_VERSION = "v19.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
ACCESS_TOKEN = os.environ["META_ACCESS_TOKEN"]
AD_ACCOUNT_ID = os.environ["META_AD_ACCOUNT_ID"]

CAMPAIGN_FIELDS = (
    "campaign_id,campaign_name,spend,impressions,clicks,ctr,cpc,cpm,"
    "reach,frequency,actions,action_values,objective"
)
ADSET_FIELDS = (
    "adset_id,adset_name,campaign_name,campaign_id,"
    "spend,impressions,clicks,ctr,cpc,frequency,optimization_goal,actions"
)
AD_FIELDS = (
    "ad_id,ad_name,adset_name,campaign_name,"
    "spend,impressions,clicks,ctr,cpc"
)


TIMEOUT = 60
MAX_RETRIES = 3


def _get(url, params, _retry=0):
    params = dict(params, access_token=ACCESS_TOKEN)
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        if _retry < MAX_RETRIES:
            wait = 2 ** _retry * 5
            print(f"[weekly] Timeout, retry {_retry + 1}/{MAX_RETRIES} in {wait}s... ({e})")
            time.sleep(wait)
            return _get(url, params, _retry + 1)
        raise


def _get_page(url, _retry=0):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        if _retry < MAX_RETRIES:
            wait = 2 ** _retry * 5
            print(f"[weekly] Timeout on pagination, retry {_retry + 1}/{MAX_RETRIES} in {wait}s...")
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


def _week_range(weeks_ago=1):
    """Returns (since, until) strings for a Mon–Sun week, weeks_ago weeks back."""
    today = datetime.now().date()
    # Last Monday = today minus days since Monday (weekday 0)
    last_monday = today - timedelta(days=today.weekday() + 7 * weeks_ago)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday.strftime("%Y-%m-%d"), last_sunday.strftime("%Y-%m-%d")


def _fetch_insights(fields, level, since, until):
    return _get_all_pages(
        f"{BASE_URL}/{AD_ACCOUNT_ID}/insights",
        {
            "fields": fields,
            "time_range": json.dumps({"since": since, "until": until}),
            "level": level,
            "limit": 200,
        },
    )


def fetch_and_save():
    account = _get(
        f"{BASE_URL}/{AD_ACCOUNT_ID}",
        {"fields": "name,currency,timezone_name"},
    )

    w1_since, w1_until = _week_range(1)  # last full week (Mon–Sun)
    w2_since, w2_until = _week_range(2)  # week before that

    print(f"[weekly] Week 1: {w1_since} → {w1_until}")
    print(f"[weekly] Week 2: {w2_since} → {w2_until}")

    w1_campaigns = _fetch_insights(CAMPAIGN_FIELDS, "campaign", w1_since, w1_until)
    w2_campaigns = _fetch_insights(CAMPAIGN_FIELDS, "campaign", w2_since, w2_until)
    w1_adsets   = _fetch_insights(ADSET_FIELDS,    "adset",    w1_since, w1_until)
    w1_ads      = _fetch_insights(AD_FIELDS,       "ad",       w1_since, w1_until)

    result = {
        "fetched_at": datetime.now().isoformat(),
        "week1": {"since": w1_since, "until": w1_until},
        "week2": {"since": w2_since, "until": w2_until},
        "account": account,
        "w1_campaigns": w1_campaigns,
        "w2_campaigns": w2_campaigns,
        "w1_adsets": w1_adsets,
        "w1_ads": w1_ads,
    }

    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    archive_dir = os.path.join(data_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    out_path = os.path.join(data_dir, "latest_weekly.json")
    archive_path = os.path.join(archive_dir, f"weekly_{w1_since}.json")

    for path in (out_path, archive_path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        f"[weekly] Saved: W1 {len(w1_campaigns)} campaigns, "
        f"W2 {len(w2_campaigns)} campaigns, {len(w1_adsets)} adsets, {len(w1_ads)} ads"
    )
    return result


if __name__ == "__main__":
    fetch_and_save()
