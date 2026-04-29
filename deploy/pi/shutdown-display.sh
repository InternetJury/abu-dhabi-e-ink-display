#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/var/log/abu-dhabi-eink/shutdown-display.log"
SERVICE_NAME="ad-eink-display.service"

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "dry-run: would stop ${SERVICE_NAME}, sync filesystems, and power off the Pi"
  exit 0
fi

mkdir -p "$(dirname "${LOG_FILE}")"
{
  printf '[%s] Telegram shutdown requested\n' "$(date --iso-8601=seconds)"
  systemctl stop "${SERVICE_NAME}" || true
  sync
  printf '[%s] Display service stopped; invoking shutdown\n' "$(date --iso-8601=seconds)"
} >>"${LOG_FILE}" 2>&1

shutdown -h now "Abu Dhabi E-Ink Telegram shutdown"
