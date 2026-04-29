# Telegram Shutdown Bot

The Telegram control bot is an optional device-management helper for the deployed e-ink system. It runs on the A6 Mini and can gracefully shut down the Raspberry Pi display client over SSH.

Telegram's bot platform is free for normal bot usage. This project does not use paid broadcasts, a cloud server, webhooks, or Telegram Stars. The only runtime requirements are the A6 Mini, internet access, and a Telegram bot token created through BotFather.

Official references:

- [Telegram Bots](https://core.telegram.org/bots)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Telegram Bots FAQ](https://core.telegram.org/bots/faq)

## Security Model

- The bot authenticates by numeric Telegram user ID, not by phone number.
- Phone numbers are not stored in this repo and should not be used as bot authorization data.
- Secrets stay local on the A6 in `C:\AbuDhabiEInk\secrets\telegram-bot.env`.
- The bot accepts only fixed commands: `/whoami`, `/status`, `/shutdown_pi`, `/confirm <code>`, and `/cancel`.
- Shutdown requires a short-lived confirmation code.
- All unknown messages are ignored.
- Unauthorized users receive no operational status and cannot trigger SSH commands.
- The A6 runs one fixed SSH command for shutdown; Telegram message text is never interpolated into a shell command.
- The Pi sudoers rule permits only `/opt/abu-dhabi-eink/shutdown-display.sh`, not unrestricted root access.

## Install On The A6

Run after the normal A6 renderer install has completed:

```powershell
C:\AbuDhabiEInk\app\deploy\a6\install-telegram-bot.ps1 -RegisterTask -PiHost ad-eink-pi.local -PiUser display
```

This creates:

```text
C:\AbuDhabiEInk\secrets\telegram-bot.env
C:\AbuDhabiEInk\state\
C:\AbuDhabiEInk\logs\
```

The config file is intentionally local-only and ignored by Git.

## Create The Bot

1. In Telegram, open `@BotFather`.
2. Create a new bot with `/newbot`.
3. Copy the bot token into:

```text
TELEGRAM_BOT_TOKEN=...
```

Do not paste the token into chat, GitHub, or public docs.

## Discover Allowed Telegram User IDs

Start the bot manually:

```powershell
C:\AbuDhabiEInk\app\deploy\a6\run-telegram-bot.ps1 -InstallRoot C:\AbuDhabiEInk
```

From each approved Telegram account, send:

```text
/whoami
```

The bot replies with that account's numeric Telegram user ID. Add those IDs to:

```text
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
```

Then restart the scheduled task:

```powershell
Stop-ScheduledTask -TaskName "Abu Dhabi E-Ink Telegram Control Bot"
Start-ScheduledTask -TaskName "Abu Dhabi E-Ink Telegram Control Bot"
```

## Pi Shutdown Wrapper

The Pi bootstrap installs:

```text
/opt/abu-dhabi-eink/shutdown-display.sh
/etc/sudoers.d/abu-dhabi-eink-shutdown
```

Verify the wrapper without shutting down:

```powershell
ssh display@ad-eink-pi.local "sudo -n /opt/abu-dhabi-eink/shutdown-display.sh --dry-run"
```

## Commands

- `/whoami`: returns the sender's numeric Telegram user ID.
- `/status`: checks Pi hostname, display service state, and current frame file status.
- `/shutdown_pi`: starts a shutdown confirmation challenge.
- `/confirm <code>`: shuts down the Pi if the code is valid and not expired.
- `/cancel`: cancels a pending shutdown.

## Important Power Note

The Pi will boot automatically when power is applied. After a software shutdown, it normally remains halted until power is cycled or the hardware reset path is triggered. This bot provides safe remote shutdown, not remote power-on.
