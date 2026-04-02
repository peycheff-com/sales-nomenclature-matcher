#!/usr/bin/env python3
"""Health check poller with Telegram alerting."""

import os
import time

import requests

HEALTH_URL = os.environ.get("HEALTH_URL", "http://api:8000/api/v1/health")
HEALTH_TARGETS = os.environ.get("HEALTH_TARGETS", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
ALERT_COOLDOWN = int(os.environ.get("ALERT_COOLDOWN", "600"))  # 10 min between alerts

SLOW_RESPONSE_THRESHOLD = 5.0  # seconds
SLOW_RESPONSE_COUNT_TRIGGER = 3  # consecutive slow responses before alerting

last_alert_time = 0
consecutive_slow_responses = 0


def _parse_targets() -> list[tuple[str, str]]:
    if not HEALTH_TARGETS.strip():
        return [("default", HEALTH_URL)]
    targets = []
    for item in HEALTH_TARGETS.split(","):
        raw = item.strip()
        if not raw:
            continue
        if "=" in raw:
            name, url = raw.split("=", 1)
            targets.append((name.strip() or "target", url.strip()))
        else:
            targets.append((f"target-{len(targets) + 1}", raw))
    return targets or [("default", HEALTH_URL)]


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


def _format_checks(checks: dict | None) -> str:
    """Format individual check statuses for the alert message."""
    if not checks:
        return "n/a"
    parts = []
    for name, status in checks.items():
        icon = "\u2705" if status == "ok" else "\u274c"
        parts.append(f"  {icon} {name}: {status}")
    return "\n".join(parts)


def _check_single_target(name: str, url: str) -> None:
    global consecutive_slow_responses
    try:
        start = time.monotonic()
        resp = requests.get(url, timeout=10)
        elapsed = time.monotonic() - start
        data = resp.json()

        version = data.get("version", "unknown")
        status = data.get("status")
        checks = data.get("checks")  # only present in DEBUG mode

        # Track slow responses
        if elapsed > SLOW_RESPONSE_THRESHOLD:
            consecutive_slow_responses += 1
        else:
            consecutive_slow_responses = 0

        if resp.status_code != 200 or status != "ok":
            msg = (
                f"\u26a0\ufe0f <b>Matcher degraded</b>\n"
                f"Target: {name}\n"
                f"Status: {status}\n"
                f"Version: {version}\n"
                f"Checks:\n{_format_checks(checks)}"
            )
            if consecutive_slow_responses >= SLOW_RESPONSE_COUNT_TRIGGER:
                msg += (
                    f"\n\u23f1 Response time: {elapsed:.1f}s (slow x{consecutive_slow_responses})"
                )
            send_telegram(msg)
        elif consecutive_slow_responses >= SLOW_RESPONSE_COUNT_TRIGGER:
            send_telegram(
                f"\u23f1 <b>Matcher slow</b>\n"
                f"Target: {name}\n"
                f"Response time: {elapsed:.1f}s"
                f" (>{SLOW_RESPONSE_THRESHOLD}s"
                f" x{consecutive_slow_responses})\n"
                f"Version: {version}"
            )
    except Exception as e:
        consecutive_slow_responses = 0
        send_telegram(f"\U0001f534 <b>Matcher DOWN</b>\nTarget: {name}\nURL: {url}\nError: {e}")


def check_health() -> None:
    for name, url in _parse_targets():
        _check_single_target(name, url)


if __name__ == "__main__":
    targets = ", ".join(f"{name}={url}" for name, url in _parse_targets())
    print(f"Alerter started. Checking {targets} every {CHECK_INTERVAL}s")
    while True:
        check_health()
        time.sleep(CHECK_INTERVAL)
