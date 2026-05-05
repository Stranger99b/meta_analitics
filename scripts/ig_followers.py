"""Fetches Instagram follower count and tracks daily growth via local history."""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE_URL = "https://graph.facebook.com/v19.0"
ACCESS_TOKEN = os.environ["META_ACCESS_TOKEN"]
AD_ACCOUNT_ID = os.environ["META_AD_ACCOUNT_ID"]

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "followers_history.json")
IG_ID_FILE   = os.path.join(os.path.dirname(__file__), "..", "data", "ig_account_id.txt")


def _get_ig_account_id():
    if os.path.exists(IG_ID_FILE):
        return open(IG_ID_FILE).read().strip()
    r = requests.get(
        f"{BASE_URL}/{AD_ACCOUNT_ID}/instagram_accounts",
        params={"access_token": ACCESS_TOKEN},
        timeout=15,
    )
    r.raise_for_status()
    accounts = r.json().get("data", [])
    if not accounts:
        return None
    ig_id = accounts[0]["id"]
    os.makedirs(os.path.dirname(IG_ID_FILE), exist_ok=True)
    open(IG_ID_FILE, "w").write(ig_id)
    return ig_id


def _load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def fetch_and_record():
    """Fetches current followers, saves to history, returns enriched snapshot."""
    ig_id = _get_ig_account_id()
    if not ig_id:
        return None

    r = requests.get(
        f"{BASE_URL}/{ig_id}",
        params={
            "fields": "name,username,followers_count,media_count",
            "access_token": ACCESS_TOKEN,
        },
        timeout=15,
    )
    r.raise_for_status()
    info = r.json()

    today = datetime.now().strftime("%Y-%m-%d")
    followers = info.get("followers_count", 0)

    history = _load_history()
    history[today] = followers
    _save_history(history)

    # Calculate growth vs yesterday, 7d ago, 30d ago
    dates = sorted(history.keys())

    def _prev(days_ago):
        from datetime import timedelta
        target = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        # Find closest date <= target
        candidates = [d for d in dates if d <= target]
        if candidates:
            return history[candidates[-1]]
        return None

    prev1  = _prev(1)
    prev7  = _prev(7)
    prev30 = _prev(30)

    return {
        "ig_id": ig_id,
        "username": info.get("username", ""),
        "name": info.get("name", ""),
        "followers": followers,
        "media_count": info.get("media_count", 0),
        "date": today,
        "growth_1d":  followers - prev1  if prev1  is not None else None,
        "growth_7d":  followers - prev7  if prev7  is not None else None,
        "growth_30d": followers - prev30 if prev30 is not None else None,
    }


def format_followers_block(snap, period="day"):
    """Returns a Telegram-formatted followers block."""
    if not snap:
        return ""

    followers = snap["followers"]
    username  = snap.get("username", "")
    lines = [f"👥 *Подписчики @{username}: {followers:,}*"]

    def _sign(n):
        return f"+{n}" if n > 0 else str(n)

    if period == "day":
        if snap["growth_1d"] is not None:
            lines.append(f"  вчера: {_sign(snap['growth_1d'])}")
        if snap["growth_7d"] is not None:
            lines.append(f"  за 7 дней: {_sign(snap['growth_7d'])}")
    elif period == "week":
        if snap["growth_7d"] is not None:
            lines.append(f"  за неделю: {_sign(snap['growth_7d'])}")
        if snap["growth_30d"] is not None:
            lines.append(f"  за 30 дней: {_sign(snap['growth_30d'])}")

    return "\n".join(lines)


if __name__ == "__main__":
    snap = fetch_and_record()
    if snap:
        print(f"Подписчики: {snap['followers']:,}")
        print(f"Прирост вчера: {snap['growth_1d']}")
        print(f"Прирост 7д: {snap['growth_7d']}")
