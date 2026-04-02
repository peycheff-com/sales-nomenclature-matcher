#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

if ! command -v ufw >/dev/null 2>&1; then
  echo "ufw is required on the host." >&2
  exit 1
fi

ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw deny 6379/tcp >/dev/null
ufw deny 2375/tcp >/dev/null
ufw deny 2376/tcp >/dev/null
ufw --force enable >/dev/null

echo "Firewall rules applied:"
ufw status

echo
echo "Listening sockets of interest:"
ss -tulpn | grep -E ':(22|80|443|6379|2375|2376)\b' || true
