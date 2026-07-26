# Device Deployment

This guide moves the Phase 1 PNG renderer onto the Geekom A6 Mini and uses the Raspberry Pi Zero 2 W as a lightweight SPI e-ink display client.

The locked templates do not change. The A6 renders a finished `1360x480` PNG every minute; the Pi receives that PNG and displays it on the native `1360x480` panel.

## Topology

- Renderer: Geekom A6 Mini, Windows, reachable over SSH by its LAN/Tailscale hostname or IP
- Display client: Raspberry Pi Zero 2 W, Raspberry Pi OS Lite, hostname chosen during Raspberry Pi Imager setup
- Transport: SSH/SCP over Tailscale
- Frame path on A6: `C:\AbuDhabiEInk\frames\current.png`
- Frame path on Pi: `/var/lib/abu-dhabi-eink/current.png`
- Refresh cadence: render on minute boundaries; use coordinated dual-controller partial refreshes between five-minute full refreshes

## 1. Prepare the microSD

Install Raspberry Pi Imager on this PC:

```powershell
winget install --id RaspberryPiFoundation.RaspberryPiImager --exact --accept-source-agreements --accept-package-agreements
```

Flash the card with **Raspberry Pi OS Lite 32-bit**.

Use Imager customization:

- hostname: `ad-eink-pi`
- username: `display`
- SSH: enabled
- Wi-Fi: configured locally in Imager
- timezone: `Asia/Dubai`

Confirm the removable microSD drive letter immediately before flashing:

```powershell
Get-Volume -DriveLetter <BOOT_DRIVE_LETTER>
Get-Disk | Where-Object BusType -eq USB
```

## 2. Enable Pi Zero USB gadget setup access

After Raspberry Pi Imager finishes, Windows should remount the Pi boot partition. Use its actual drive letter:

```powershell
.\deploy\pi\enable-pi-zero-usb-gadget.ps1 -BootDriveLetter <BOOT_DRIVE_LETTER>
```

This adds:

- `dtoverlay=dwc2` to `config.txt`
- `modules-load=dwc2,g_ether` to `cmdline.txt`

The script backs up both files before editing. If Imager remounts the boot partition with a different letter, use that drive letter instead.

## 3. First Pi boot over USB

Insert the flashed microSD into the Pi Zero 2 W. Connect the **data USB** port on the Pi to this PC, not the power-only port, and wait a few minutes.

From this PC, try:

```powershell
ssh display@ad-eink-pi.local hostname
```

If `.local` resolution is slow on Windows, inspect USB Ethernet adapters and ARP entries:

```powershell
Get-NetAdapter | Where-Object { $_.InterfaceDescription -match "RNDIS|USB|Ethernet Gadget" }
arp -a
```

Then SSH to the discovered USB network IP.

## 4. Bootstrap the Pi

Copy the Pi deployment folder to the Pi:

```powershell
scp -r deploy/pi display@ad-eink-pi:/tmp/abu-dhabi-eink-pi
```

Run the bootstrap:

```powershell
ssh display@ad-eink-pi "cd /tmp/abu-dhabi-eink-pi && bash bootstrap-pi.sh --hostname ad-eink-pi"
```

Then join Tailscale on the Pi:

```powershell
ssh display@ad-eink-pi "sudo tailscale up --hostname ad-eink-pi --ssh"
```

The display client starts immediately in checksum/dry-run mode until the vendor e-ink driver module is configured.

## 5. Bind the SPI panel driver

The selected panel is the Waveshare `10.85inch e-Paper HAT+` black/white SPI display, SKU `29790`. It is a native `1360x480` panel and uses Waveshare's Python module:

```text
waveshare_epd.epd10in85
```

Install the vendor library on the Pi while keeping the display service in safe checksum mode:

```powershell
ssh display@ad-eink-pi "sudo /opt/abu-dhabi-eink/install-waveshare-10in85.sh"
```

After the HAT and panel are physically connected, enable real hardware output:

```powershell
ssh display@ad-eink-pi "sudo /opt/abu-dhabi-eink/install-waveshare-10in85.sh --enable-service"
```

This writes `/etc/default/ad-eink-display` with:

```text
WAVESHARE_10IN85_VENDOR_LIB="/opt/abu-dhabi-eink/vendor/waveshare-10in85/RaspberryPi/python/lib"
WAVESHARE_10IN85_SPI_HZ="2000000"
AD_EINK_DRIVER_ARGS="--driver-lib /opt/abu-dhabi-eink --driver-module waveshare_10in85_bw --startup-delay-seconds 5 --clear-on-start --startup-full-refresh-count 1 --full-refresh-seconds 300 --monochrome-threshold 200 --require-current-minute --latest-display-start-second 45"
```

Then reloads and restarts `ad-eink-display.service`.

The service uses a local `waveshare_10in85_bw` adapter instead of calling the vendored module directly. The 10.85inch display uses two controller halves, so the adapter splits each packed `1360x480` frame row-by-row into master/slave buffers, loads both halves, then performs one shared refresh. The default SPI rate is `2MHz`. Startup performs a row-streamed white clear and a full refresh; every full refresh finishes with an immediate same-frame coordinated partial pass so the master and slave halves settle at equal contrast. Minute updates use coordinated partial refreshes, with another full-plus-normalization cycle every five minutes. Grayscale is converted with a deterministic threshold rather than controller-sensitive dithering.

The client validates file age, render minute, safe refresh-start cutoff, and PNG dimensions before importing or initializing the hardware driver. A stale or previous-minute frame therefore cannot power the panel after reboot. The first valid frame after service start is forced through the full-refresh path, the panel is put to sleep if publishing stops, and an OS lock prevents more than one process from writing GPIO/SPI.

The Waveshare Python GPIO stack is run by the display service with root privileges. The vendor driver needs GPIO edge-detection access for the panel busy pin; running it as the unprivileged `display` user can fail with `RuntimeError: Failed to add edge detection` even when the user belongs to the `gpio` group.

If you need to return to checksum mode before hardware is connected, reset the environment file:

```powershell
ssh display@ad-eink-pi "echo 'AD_EINK_DRIVER_ARGS=\"\"' | sudo tee /etc/default/ad-eink-display && sudo systemctl restart ad-eink-display.service"
```

Check logs:

```powershell
ssh display@ad-eink-pi "journalctl -u ad-eink-display.service -f"
```

Important Waveshare wiring notes:

- Directly mount the HAT onto the Pi 40-pin header, or use the Waveshare 10-pin mapping from the official manual.
- SPI must expose both `/dev/spidev0.0` and `/dev/spidev0.1` because this panel uses separate `CS_M` and `CS_S`.
- Do not enable hardware output until the HAT and panel ribbon are seated; otherwise the service may loop on driver/hardware errors.
- Keep `Display Config` fixed at `B / 0.47R` and `Interface Config` fixed at `0 / 4-line SPI`. Switches must only be changed while the Pi and HAT are unpowered.
- Never run a vendor diagnostic while `ad-eink-display.service` is active. The runtime lock protects the production client, but third-party demos may not honor it.

## 6. Prepare the A6 Mini

First ensure SSH to the A6 works over Tailscale:

```powershell
ssh <A6_TAILSCALE_IP_OR_HOSTNAME> hostname
```

If this times out, run the repair script on the A6. It requests Administrator access through the normal Windows UAC prompt:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Path\To\app\deploy\a6\repair-ssh.ps1
```

Approve the UAC prompt when Windows asks. If the repo is not on the A6 yet, download the public `repair-ssh.ps1` file first; it contains no credentials or device-specific secrets. After it completes, retry `ssh <A6_TAILSCALE_IP_OR_HOSTNAME> hostname` from this PC.

On the A6, run PowerShell as Administrator:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Path\To\app\deploy\a6\install-a6.ps1 -RegisterTask -DisableLockSleep -PiHost ad-eink-pi -PiUser display
```

The script installs or verifies Git, Python 3.11, Playwright Chromium, the project checkout, runtime folders, and the scheduled render loop.

The installer also creates a dedicated A6-to-Pi Ed25519 key under
`C:\AbuDhabiEInk\secrets`. Authorize the public key printed by the installer
once in the Pi user's `~/.ssh/authorized_keys`. The private key and known-hosts
file remain local to the A6 and must never be committed or copied into the
public repository.

Both scheduled tasks run as `SYSTEM`: the publisher starts at Windows startup,
and the watchdog checks it every minute. No interactive Windows sign-in is
required after an A6 reboot. A publisher frame or heartbeat older than `90`
seconds is treated as stale and the task is restarted, limiting a hung process
to approximately one missed refresh interval before recovery begins.

Default A6 folders:

- app: `C:\AbuDhabiEInk\app`
- frames: `C:\AbuDhabiEInk\frames`
- logs: `C:\AbuDhabiEInk\logs`
- secrets: `C:\AbuDhabiEInk\secrets` (local-only SSH material)
- Playwright browser cache: `C:\AbuDhabiEInk\playwright`

## 7. Manual A6 render/publish test

Run one cycle manually:

```powershell
C:\AbuDhabiEInk\app\deploy\a6\run-render-publisher.ps1 -InstallRoot C:\AbuDhabiEInk -PiHost ad-eink-pi -PiUser display -Once
```

Confirm the Pi received the frame:

```powershell
ssh display@ad-eink-pi "ls -lh /var/lib/abu-dhabi-eink/current.png"
```

## 8. Acceptance checks

- `tailscale status` shows both the renderer Mini PC and the display Pi, if Tailscale is enabled on both devices.
- A6 logs show a new render every minute.
- Pi logs show a new frame checksum whenever the PNG changes.
- The PNG on the Pi is exactly `1360x480`.
- Rebooting the A6 starts the publisher and Telegram control tasks as `SYSTEM`; no user login is required.
- Rebooting the Pi restarts `ad-eink-display.service`.

## 9. Storage retention

The runtime is current-frame only by design:

- A6 keeps `C:\AbuDhabiEInk\frames\current.png` and may briefly create `current.tmp.png` during rendering.
- Pi keeps `/var/lib/abu-dhabi-eink/current.png` and may briefly receive `/var/lib/abu-dhabi-eink/current.png.tmp` during atomic publish.
- A6 removes interrupted `*.tmp.png` files on each publish cycle.
- A6 keeps render publisher logs for `14` days by default.
- Pi display logs rotate at `1 MB` with `3` backups by default.

This means the long-running deployment does not accumulate one PNG per minute.

## 10. Freshness guarantees

The runtime is tuned to avoid showing an old minute on the e-paper panel:

- A6 waits for aligned render slots, so normal renders start at `HH:MM:00` rather than drifting through sleep-after-render timing.
- A6 skips publishing a frame if rendering takes more than `30` seconds and aborts the complete render/publish cycle after `42` seconds.
- Pi polls for changed frames every `1` second.
- Pi skips display updates when the received frame file is older than `50` seconds.
- Pi also rejects a frame whose render mtime is not in the current minute or whose refresh would start after second `45`.
- The publish operation is atomic: A6 copies to `current.png.tmp`, then renames it to `current.png`.

In normal operation this means a frame generated for `10:00` is published and picked up during the `10:00` minute, not displayed as a fresh update at `10:01` or later.

## 11. Optional Telegram shutdown bot

The A6 can also run a private Telegram control bot for graceful Pi shutdown. It is intentionally narrow: it can report status and shut down the Pi after a confirmation code, but it cannot execute arbitrary Telegram messages as shell commands.

Setup guide:

```text
docs/telegram-shutdown-bot.md
```

Secrets are stored only on the A6 at `C:\AbuDhabiEInk\secrets\telegram-bot.env`. Do not commit bot tokens, Telegram user IDs, phone numbers, passwords, IPs, or SSH keys.

## Notes

- Wi-Fi credentials should stay local to Raspberry Pi Imager or the Pi, not in repo scripts.
- The A6 is intentionally the heavy runtime because Darbi browser fallback and RSS/market/weather fetching are much better suited to the Mini PC than the Pi Zero 2 W.
- The Pi client is intentionally driver-pluggable because the final import path depends on the exact `1360x480` SPI panel vendor package.
