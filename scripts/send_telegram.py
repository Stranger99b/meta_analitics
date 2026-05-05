"""Sends text to Telegram via bot."""

import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

MAX_MSG_LEN = 4096


def send_message(text: str, chat_id: str = CHAT_ID, parse_mode: str = "Markdown"):
    """Send text, splitting into chunks if longer than 4096 chars."""
    chunks = [text[i:i + MAX_MSG_LEN] for i in range(0, len(text), MAX_MSG_LEN)]
    for chunk in chunks:
        r = requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode},
            timeout=30,
        )
        r.raise_for_status()
    print(f"[telegram] Sent {len(chunks)} message(s)")


if __name__ == "__main__":
    send_message("✅ Meta Ads бот работает!")
