#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/abu-dhabi-eink"
STATE_DIR="/var/lib/abu-dhabi-eink"
LOG_DIR="/var/log/abu-dhabi-eink"
SERVICE_NAME="ad-eink-display.service"
HOSTNAME_VALUE="ad-eink-pi"
TAILSCALE_AUTH_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostname)
      HOSTNAME_VALUE="$2"
      shift 2
      ;;
    --tailscale-auth-key)
      TAILSCALE_AUTH_KEY="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting hostname to ${HOSTNAME_VALUE}"
sudo hostnamectl set-hostname "${HOSTNAME_VALUE}"

echo "Installing Pi display dependencies"
sudo apt-get update
sudo apt-get install -y \
  curl \
  python3 \
  python3-pil \
  python3-numpy \
  python3-spidev \
  python3-gpiozero \
  python3-rpi.gpio \
  rsync

echo "Enabling SPI"
if command -v raspi-config >/dev/null 2>&1; then
  sudo raspi-config nonint do_spi 0
fi

echo "Creating runtime directories"
sudo mkdir -p "${INSTALL_DIR}" "${STATE_DIR}" "${LOG_DIR}"
sudo cp "${SCRIPT_DIR}/display-current.py" "${INSTALL_DIR}/display-current.py"
sudo cp "${SCRIPT_DIR}/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
sudo chown -R display:display "${STATE_DIR}" "${LOG_DIR}" || true
sudo chmod +x "${INSTALL_DIR}/display-current.py"

if id display >/dev/null 2>&1; then
  sudo usermod -aG spi,gpio display || true
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Installing Tailscale"
  curl -fsSL https://tailscale.com/install.sh | sh
fi

if [[ -n "${TAILSCALE_AUTH_KEY}" ]]; then
  echo "Joining Tailscale as ${HOSTNAME_VALUE}"
  sudo tailscale up --auth-key "${TAILSCALE_AUTH_KEY}" --hostname "${HOSTNAME_VALUE}" --ssh
else
  echo "Tailscale installed. Join the tailnet with:"
  echo "  sudo tailscale up --hostname ${HOSTNAME_VALUE} --ssh"
fi

echo "Enabling display service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "Pi bootstrap complete."
echo "Copy frames to: ${STATE_DIR}/current.png"
echo "Service logs: journalctl -u ${SERVICE_NAME} -f"
