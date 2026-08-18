"""Sends text to Telegram via bot."""

import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

MAX_MSG_LEN = 4000  # under Telegram's 4096 hard limit, leaves headroom


def _split_message(text: str, limit: int = MAX_MSG_LEN) -> list[str]:
    """Split on line boundaries so chunks stay under the limit.

    Splitting by raw text[i:i+4096] can cut a Markdown entity in half and make
    Telegram reject the whole message with 400 "can't parse entities". Cutting on
    line boundaries keeps each chunk self-contained.
    """
    chunks: list[str] = []
    cur = ""
    for line in text.split("\n"):
        # A single line longer than the limit is hard-split as a fallback.
        while len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            if cur:
                chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def send_message(text: str, chat_id: str = CHAT_ID, parse_mode: str | None = None,
                 message_thread_id: int | str | None = None):
    """Send text, splitting into chunks on line boundaries if it exceeds the limit.

    parse_mode defaults to None (plain text) so report markup can never trigger a
    400 "can't parse entities" error. message_thread_id targets a forum topic in a
    supergroup (None = обычный чат / General).
    """
    chunks = _split_message(text)
    for chunk in chunks:
        payload = {"chat_id": chat_id, "text": chunk}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        r = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=30)
        r.raise_for_status()
    print(f"[telegram] Sent {len(chunks)} message(s)")


def send_document(content: str, filename: str, chat_id: str = CHAT_ID,
                  caption: str | None = None,
                  message_thread_id: int | str | None = None,
                  mime: str = "text/csv", bom: bool = True,
                  parse_mode: str | None = None):
    """Отправляет текстовый файл (CSV/Markdown/…) как документ в чат/тему."""
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    if parse_mode:
        data["parse_mode"] = parse_mode
    if message_thread_id:
        data["message_thread_id"] = message_thread_id
    enc = content.encode("utf-8-sig" if bom else "utf-8")
    files = {"document": (filename, enc, mime)}
    r = requests.post(f"{API_URL}/sendDocument", data=data, files=files, timeout=60)
    r.raise_for_status()
    print(f"[telegram] Sent document {filename}")


if __name__ == "__main__":
    send_message("✅ Meta Ads бот работает!")
