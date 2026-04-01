#!/usr/bin/env python3
"""Health check poller with Telegram alerting."""

import os
import time

import requests

HEALTH_URL = os.environ.get("HEALTH_URL", "http://nginx/api/v1/health")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
ALERT_COOLDOWN = int(os.environ.get("ALERT_COOLDOWN", "600"))  # 10 min between alerts

last_alert_time = 0


def send_telegram(message: str) -> None:
    global last_alert_time
    now = time.time()
    if now - last_alert_time < ALERT_COOLDOWN:
        return
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"ALERT (no Telegram): {message}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        last_alert_time = now
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")


def check_health() -> None:
    try:
        resp = requests.get(HEALTH_URL, timeout=10)
        data = resp.json()
        if resp.status_code != 200 or data.get("status") != "ok":
            status = data.get('status')
            checks = data.get('checks')
            send_telegram(
                f"\u26a0\ufe0f <b>Matcher degraded</b>\n"
                f"Status: {status}\nChecks: {checks}"
            )
    except Exception as e:
        send_telegram(f"\U0001f534 <b>Matcher DOWN</b>\nError: {e}")


if __name__ == "__main__":
    print(f"Alerter started. Checking {HEALTH_URL} every {CHECK_INTERVAL}s")
    while True:
        check_health()
        time.sleep(CHECK_INTERVAL)
