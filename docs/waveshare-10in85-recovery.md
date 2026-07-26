# Waveshare 10.85-inch Recovery Runbook

This runbook covers the black/white `1360x480` Waveshare 10.85-inch e-Paper HAT+ used by this project. It contains no hostnames, addresses, credentials, or device-specific secrets.

## Known-good baseline

- Panel: black/white 10.85-inch HAT+, not the four-color `(G)` model.
- Display switch: `B / 0.47R`.
- Interface switch: `0 / 4-line SPI`, with both CE0 and CE1 exposed as `/dev/spidev0.0` and `/dev/spidev0.1`.
- Driver: Waveshare `waveshare_epd.epd10in85` behind the local `waveshare_10in85_bw` row-splitting adapter.
- SPI rate: `2MHz`.
- Runtime: coordinated row-streamed partial updates, with startup and five-minute full normalization refreshes.
- Frame: exactly `1360x480`, 1-bit conversion performed by the Pi client.

The adapter loads old and new RAM for the master and slave halves independently and issues one shared refresh only after both new buffers are loaded.

## Incident finding

The panel rendered both halves successfully before a controlled Pi shutdown. After reboot, the display client initialized the vendor driver before checking whether `current.png` was stale. With no fresh publisher output, the panel remained initialized and powered while the stale image was rejected. Later recovery experiments changed chip-select handling, initialization registers, SPI-line modes, and speeds; none restored stable full-screen output.

Those experimental paths are not part of production. The runtime has been returned to the last-known-working adapter and hardened so that:

1. frame existence, age, digest, and dimensions are checked before vendor import/init;
2. the first fresh frame after restart is a full refresh followed immediately by a same-frame coordinated partial normalization pass;
3. stale frames never power the HAT;
4. failed initialization or writes close/sleep the driver;
5. idle hardware is put to sleep;
6. SIGTERM performs a clean panel sleep before service exit;
7. an OS lock permits only one production writer.

## Controlled recovery gate

Keep normal publishing and `ad-eink-display.service` disabled until each gate passes. Never move HAT switches or reseat FPC/ribbon cables while powered.

1. Confirm the physical panel model and both HAT switch positions against the official manual.
2. Confirm both SPI devices exist, GPIO pins are in hardware-SPI mode, and the switches remain fixed at `B / 0.47R` and `0 / 4-line SPI`.
3. Confirm no display service, diagnostic, or vendor demo process is running.
4. Deploy the last-known-working adapter and lifecycle-safe display client without enabling the service.
5. Use `verify-waveshare-10in85.py`; it refuses to run while the service is active and acquires the production display lock.
6. Display full white once and photograph both halves: `sudo /opt/abu-dhabi-eink/verify-waveshare-10in85.py full-white --apply`.
7. Display full black once and photograph both halves: `sudo /opt/abu-dhabi-eink/verify-waveshare-10in85.py full-black --apply`.
8. Display both split patterns individually using `left-black --apply` and `right-black --apply`, with a photo check between commands.
9. Display one fresh live ribbon frame using `live --apply`.
10. Only after all five images are clean, enable the Pi service and then the A6 publisher.

If either half fails with the restored software baseline, stop repeated refresh attempts. Because the panel and HAT may share a separate Pi/header/ribbon path, the next isolation test is continuity or substitution of that common path, not further template, refresh-speed, or register changes.

## Runtime acceptance

- A stale frame after reboot does not initialize the display.
- A fresh frame performs one full refresh and is visible during its own minute.
- Stopping the service calls panel sleep.
- A second display writer is rejected.
- Both halves remain clean for at least two aligned minute updates.
- The publisher watchdog replaces a hung A6 render process instead of leaving an apparently running but stale task.

## References

- [Waveshare 10.85-inch B/W manual](https://www.waveshare.com/wiki/10.85inch_e-Paper_HAT%2B_Manual)
- [Waveshare official e-Paper repository](https://github.com/waveshareteam/e-Paper)
- [Reference dashboard using the same panel](https://github.com/czuryk/Waveshare-ePaper-10.85-dashboard)
