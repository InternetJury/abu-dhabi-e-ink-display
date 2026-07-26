#!/usr/bin/env bash
set -euo pipefail

AD_EINK_DRIVER_ARGS="${AD_EINK_DRIVER_ARGS:-}"

if [[ -f /etc/default/ad-eink-display ]]; then
  # shellcheck disable=SC1091
  source /etc/default/ad-eink-display
fi

# AD_EINK_DRIVER_ARGS is intentionally shell-split so the service can add
# driver flags without rewriting the systemd unit.
# shellcheck disable=SC2086
exec /usr/bin/python3 /opt/abu-dhabi-eink/display-current.py \
  --image /var/lib/abu-dhabi-eink/current.png \
  --lock-file /run/abu-dhabi-eink/display.lock \
  --hardware-idle-seconds 90 \
  --log-file /var/log/abu-dhabi-eink/display-current.log \
  ${AD_EINK_DRIVER_ARGS}
