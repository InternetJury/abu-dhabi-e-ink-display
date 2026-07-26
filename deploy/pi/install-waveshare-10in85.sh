#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="/opt/abu-dhabi-eink/vendor/waveshare-10in85"
DEMO_URL="https://files.waveshare.com/wiki/10.85inch_e-Paper_HAT%2B/10.85inch_e-Paper.zip"
ENABLE_SERVICE="0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable-service)
      ENABLE_SERVICE="1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

echo "Installing Waveshare 10.85inch e-Paper HAT+ Python driver"
sudo apt-get update
sudo apt-get install -y \
  curl \
  unzip \
  python3-pil \
  python3-numpy \
  python3-spidev \
  python3-gpiozero \
  python3-rpi.gpio

curl -fsSL "${DEMO_URL}" -o "${tmp_dir}/10.85inch_e-Paper.zip"
unzip -q "${tmp_dir}/10.85inch_e-Paper.zip" -d "${tmp_dir}/demo"

sudo rm -rf "${INSTALL_ROOT}"
sudo mkdir -p "$(dirname "${INSTALL_ROOT}")"
sudo cp -a "${tmp_dir}/demo" "${INSTALL_ROOT}"
sudo chown -R root:root "${INSTALL_ROOT}"

driver_lib="${INSTALL_ROOT}/RaspberryPi/python/lib"
if [[ ! -f "${driver_lib}/waveshare_epd/epd10in85.py" ]]; then
  echo "Waveshare driver not found at ${driver_lib}/waveshare_epd/epd10in85.py" >&2
  exit 1
fi

PYTHONPATH="${driver_lib}" python3 - <<'PY'
from waveshare_epd import epd10in85
print(f"Detected Waveshare epd10in85: {epd10in85.EPD_WIDTH}x{epd10in85.EPD_HEIGHT}")
PY

echo "Driver library installed at ${driver_lib}"

if [[ "${ENABLE_SERVICE}" == "1" ]]; then
  if [[ ! -f "${SCRIPT_DIR}/ad-eink-display.defaults" ]]; then
    echo "Missing ${SCRIPT_DIR}/ad-eink-display.defaults; rerun Pi bootstrap from a complete deployment folder." >&2
    exit 1
  fi
  sudo install -m 0644 "${SCRIPT_DIR}/ad-eink-display.defaults" /etc/default/ad-eink-display
  sudo systemctl daemon-reload
  sudo systemctl restart ad-eink-display.service
  echo "ad-eink-display.service is now configured for Waveshare epd10in85."
else
  echo "Service left in dry-run/checksum mode."
  echo "After connecting the HAT/display, enable hardware output with:"
  echo "  sudo /opt/abu-dhabi-eink/install-waveshare-10in85.sh --enable-service"
  echo "or set /etc/default/ad-eink-display to:"
  echo "  WAVESHARE_10IN85_VENDOR_LIB=\"${driver_lib}\""
  echo "  WAVESHARE_10IN85_SPI_HZ=\"2000000\""
  echo "  AD_EINK_DRIVER_ARGS=\"--driver-lib /opt/abu-dhabi-eink --driver-module waveshare_10in85_bw --startup-delay-seconds 5 --startup-full-refresh-count 1 --disable-partial --require-current-minute --latest-display-start-second 45\""
fi
