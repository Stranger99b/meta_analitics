"""Updates META_ACCESS_TOKEN in .env and verifies it works."""

import sys
import os
import requests
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def update_token(new_token: str):
    # Read current .env
    with open(ENV_PATH, encoding="utf-8") as f:
        lines = f.readlines()

    # Replace token line
    new_lines = []
    replaced = False
    for line in lines:
        if line.startswith("META_ACCESS_TOKEN="):
            new_lines.append(f"META_ACCESS_TOKEN={new_token}\n")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"META_ACCESS_TOKEN={new_token}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"[update_token] Токен обновлён ({len(new_token)} символов)")

    # Verify
    r = requests.get(
        "https://graph.facebook.com/v19.0/me",
        params={"access_token": new_token},
        timeout=10,
    )
    if r.status_code == 200:
        data = r.json()
        print(f"[update_token] ✅ Токен валиден. Пользователь: {data.get('name', data.get('id'))}")

        # Check expiry
        r2 = requests.get(
            "https://graph.facebook.com/debug_token",
            params={"input_token": new_token, "access_token": new_token},
            timeout=10,
        )
        if r2.status_code == 200:
            d = r2.json().get("data", {})
            import datetime
            exp = d.get("expires_at", 0)
            if exp:
                exp_dt = datetime.datetime.fromtimestamp(exp)
                days = (exp_dt - datetime.datetime.now()).days
                print(f"[update_token] Истекает: {exp_dt.strftime('%Y-%m-%d')} (через {days} дней)")
            elif not d.get("expires_at"):
                print("[update_token] Токен бессрочный")
    else:
        print(f"[update_token] ❌ Токен не валиден: {r.json()}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 update_token.py НОВЫЙ_ТОКЕН")
        sys.exit(1)
    update_token(sys.argv[1].strip())
