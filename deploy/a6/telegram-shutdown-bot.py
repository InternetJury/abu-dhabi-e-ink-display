#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import random
import re
import secrets
import subprocess
import sys
import time
from typing import Any, Callable, Protocol
from urllib import error, request


TELEGRAM_API_BASE = "https://api.telegram.org"
DEFAULT_REMOTE_FRAME = "/var/lib/abu-dhabi-eink/current.png"
PI_SHUTDOWN_COMMAND = "sudo -n /opt/abu-dhabi-eink/shutdown-display.sh"
PI_STATUS_COMMAND = (
    "printf 'host='; hostname; "
    "printf 'display_service='; systemctl is-active ad-eink-display.service || true; "
    f"stat -c 'frame_size=%s frame_mtime=%y' {DEFAULT_REMOTE_FRAME} 2>/dev/null || echo 'frame=missing'"
)
SAFE_SSH_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


class TelegramSender(Protocol):
    def send_message(self, chat_id: int, text: str) -> None:
        ...


class PiExecutor(Protocol):
    def status(self) -> str:
        ...

    def shutdown(self) -> str:
        ...


@dataclass
class BotConfig:
    token: str
    allowed_user_ids: set[int]
    pi_host: str = "ad-eink-pi.local"
    pi_user: str = "display"
    ssh_path: str = "ssh"
    ssh_identity_file: str = ""
    ssh_known_hosts_file: str = ""
    confirm_ttl_seconds: int = 60
    shutdown_cooldown_seconds: int = 300
    poll_timeout_seconds: int = 30
    dry_run: bool = False


@dataclass
class BotState:
    offset: int = 0
    last_shutdown_epoch: float = 0.0


@dataclass
class PendingConfirmation:
    code: str
    expires_at: float


@dataclass
class RejectionCounters:
    unauthorized: int = 0
    non_private: int = 0
    last_log_epoch: float = 0.0


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> BotState:
        if not self.path.exists():
            return BotState()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return BotState(
            offset=int(payload.get("offset", 0)),
            last_shutdown_epoch=float(payload.get("last_shutdown_epoch", 0.0)),
        )

    def save(self, state: BotState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "offset": state.offset,
                    "last_shutdown_epoch": state.last_shutdown_epoch,
                },
                handle,
                indent=2,
                sort_keys=True,
            )
        tmp_path.replace(self.path)


class TelegramClient:
    def __init__(self, token: str, api_base: str = TELEGRAM_API_BASE) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.api_base}/bot{self.token}/{method}"
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=max(10, int(payload.get("timeout", 10)) + 10)) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram API {method} failed with HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Telegram API {method} failed: {exc.reason}") from exc

        if not decoded.get("ok"):
            raise RuntimeError(f"Telegram API {method} returned not-ok response: {decoded.get('description', decoded)}")
        return decoded

    def get_updates(self, offset: int, timeout_seconds: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout_seconds,
            "allowed_updates": ["message"],
        }
        if offset > 0:
            payload["offset"] = offset
        return list(self._call("getUpdates", payload).get("result", []))

    def send_message(self, chat_id: int, text: str) -> None:
        self._call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )


class ShellPiExecutor:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self._validate_ssh_target(config.pi_user, config.pi_host)

    @staticmethod
    def _validate_ssh_target(pi_user: str, pi_host: str) -> None:
        if not SAFE_SSH_COMPONENT.fullmatch(pi_user):
            raise ValueError("Pi user contains unsupported characters.")
        if not SAFE_SSH_COMPONENT.fullmatch(pi_host):
            raise ValueError("Pi host contains unsupported characters.")

    def _run_fixed_remote_command(self, remote_command: str) -> str:
        target = f"{self.config.pi_user}@{self.config.pi_host}"
        command = [
            self.config.ssh_path,
        ]
        if self.config.ssh_identity_file:
            command.extend(["-i", self.config.ssh_identity_file])
        command.extend([
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ])
        if self.config.ssh_known_hosts_file:
            command.extend(["-o", f"UserKnownHostsFile={self.config.ssh_known_hosts_file}"])
        command.extend(["-o", "ConnectTimeout=10", target, remote_command])

        logging.info("Running fixed Pi command: %s", remote_command.split()[0])
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            raise RuntimeError(output or f"SSH command failed with exit code {result.returncode}")
        return output or "ok"

    def status(self) -> str:
        if self.config.dry_run:
            return "dry-run: Pi status command would be executed"
        return self._run_fixed_remote_command(PI_STATUS_COMMAND)

    def shutdown(self) -> str:
        if self.config.dry_run:
            return "dry-run: Pi shutdown command would be executed"
        return self._run_fixed_remote_command(PI_SHUTDOWN_COMMAND)


class BotController:
    def __init__(
        self,
        config: BotConfig,
        state: BotState,
        state_store: JsonStateStore | None,
        telegram: TelegramSender,
        executor: PiExecutor,
        clock: Callable[[], float] = time.time,
        code_factory: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.state_store = state_store
        self.telegram = telegram
        self.executor = executor
        self.clock = clock
        self.code_factory = code_factory or make_confirmation_code
        self.pending: dict[int, PendingConfirmation] = {}
        self.rejections = RejectionCounters(last_log_epoch=self.clock())

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return

        command, args = parse_command(message.get("text"))
        if command is None:
            return

        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        user_id = sender.get("id")
        chat_id = chat.get("id")
        chat_type = chat.get("type")
        if not isinstance(user_id, int) or not isinstance(chat_id, int):
            return

        # Bootstrap discovery is available only while no allowlist exists. Once
        # configured, unknown users receive no response from any command.
        if command == "/whoami" and not self.config.allowed_user_ids:
            self.telegram.send_message(
                chat_id,
                f"Your Telegram user ID is {user_id}.\nAdd this numeric ID to TELEGRAM_ALLOWED_USER_IDS on the A6.",
            )
            return

        if chat_type != "private" or chat_id != user_id:
            self._record_rejection(non_private=True)
            return

        if user_id not in self.config.allowed_user_ids:
            self._record_rejection(unauthorized=True)
            return

        if command == "/whoami":
            self.telegram.send_message(
                chat_id,
                f"Your Telegram user ID is {user_id}.\nThis account is authorized for e-ink control.",
            )
        elif command == "/status":
            self._send_status(chat_id)
        elif command == "/shutdown_pi":
            self._request_shutdown(chat_id, user_id)
        elif command == "/confirm":
            self._confirm_shutdown(chat_id, user_id, args)
        elif command == "/cancel":
            self.pending.pop(user_id, None)
            self.telegram.send_message(chat_id, "Pending shutdown cancelled.")

    def _record_rejection(self, unauthorized: bool = False, non_private: bool = False) -> None:
        if unauthorized:
            self.rejections.unauthorized += 1
        if non_private:
            self.rejections.non_private += 1

        now = self.clock()
        if now - self.rejections.last_log_epoch < 300:
            return

        if self.rejections.unauthorized or self.rejections.non_private:
            logging.warning(
                "Ignored Telegram commands in last window: unauthorized=%s non_private=%s",
                self.rejections.unauthorized,
                self.rejections.non_private,
            )
            self.rejections.unauthorized = 0
            self.rejections.non_private = 0
            self.rejections.last_log_epoch = now

    def _send_status(self, chat_id: int) -> None:
        try:
            status = self.executor.status()
            self.telegram.send_message(chat_id, f"Pi status:\n{trim_for_telegram(status)}")
        except Exception as exc:
            logging.exception("Pi status check failed")
            self.telegram.send_message(chat_id, f"Pi status check failed: {exc}")

    def _request_shutdown(self, chat_id: int, user_id: int) -> None:
        now = self.clock()
        remaining = self.config.shutdown_cooldown_seconds - (now - self.state.last_shutdown_epoch)
        if remaining > 0:
            self.telegram.send_message(chat_id, f"Shutdown is cooling down. Try again in {int(remaining)}s.")
            return

        code = self.code_factory()
        self.pending[user_id] = PendingConfirmation(code=code, expires_at=now + self.config.confirm_ttl_seconds)
        self.telegram.send_message(
            chat_id,
            (
                "Confirm Raspberry Pi shutdown with:\n"
                f"/confirm {code}\n\n"
                f"This code expires in {self.config.confirm_ttl_seconds}s."
            ),
        )

    def _confirm_shutdown(self, chat_id: int, user_id: int, args: list[str]) -> None:
        pending = self.pending.get(user_id)
        if pending is None:
            self.telegram.send_message(chat_id, "No pending shutdown request.")
            return
        if self.clock() > pending.expires_at:
            self.pending.pop(user_id, None)
            self.telegram.send_message(chat_id, "Shutdown confirmation expired.")
            return
        if not args or not secrets.compare_digest(args[0].strip().upper(), pending.code):
            self.telegram.send_message(chat_id, "Confirmation code did not match.")
            return

        self.pending.pop(user_id, None)
        try:
            result = self.executor.shutdown()
            self.state.last_shutdown_epoch = self.clock()
            if self.state_store:
                self.state_store.save(self.state)
            self.telegram.send_message(chat_id, f"Raspberry Pi shutdown requested.\n{trim_for_telegram(result)}")
        except Exception as exc:
            logging.exception("Pi shutdown failed")
            self.telegram.send_message(chat_id, f"Pi shutdown failed: {exc}")


def parse_command(text: Any) -> tuple[str | None, list[str]]:
    if not isinstance(text, str):
        return None, []
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None, []
    parts = stripped.split()
    if not parts:
        return None, []
    command = parts[0].split("@", 1)[0].lower()
    return command, parts[1:]


def make_confirmation_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(6))


def trim_for_telegram(text: str, limit: int = 3500) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n...[truncated]"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def parse_allowed_user_ids(value: str) -> set[int]:
    ids: set[int] = set()
    for item in re.split(r"[\s,;]+", value.strip()):
        if not item:
            continue
        ids.add(int(item))
    return ids


def build_config(env: dict[str, str], dry_run_override: bool = False, poll_timeout_override: int | None = None) -> BotConfig:
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "PASTE_BOTFATHER_TOKEN_HERE":
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured.")

    return BotConfig(
        token=token,
        allowed_user_ids=parse_allowed_user_ids(env.get("TELEGRAM_ALLOWED_USER_IDS", "")),
        pi_host=env.get("PI_HOST", "ad-eink-pi.local").strip(),
        pi_user=env.get("PI_USER", "display").strip(),
        ssh_path=env.get("SSH_PATH", "ssh").strip(),
        ssh_identity_file=env.get("SSH_IDENTITY_FILE", "").strip(),
        ssh_known_hosts_file=env.get("SSH_KNOWN_HOSTS_FILE", "").strip(),
        confirm_ttl_seconds=int(env.get("TELEGRAM_CONFIRM_TTL_SECONDS", "60")),
        shutdown_cooldown_seconds=int(env.get("TELEGRAM_SHUTDOWN_COOLDOWN_SECONDS", "300")),
        poll_timeout_seconds=poll_timeout_override or int(env.get("TELEGRAM_POLL_TIMEOUT_SECONDS", "30")),
        dry_run=dry_run_override or env.get("TELEGRAM_DRY_RUN", "").strip().lower() in {"1", "true", "yes"},
    )


def configure_logging(log_file: Path | None, max_bytes: int = 1024 * 1024, backup_count: int = 3) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def run_poll_loop(
    client: TelegramClient,
    controller: BotController,
    state_store: JsonStateStore,
    state: BotState,
    poll_timeout_seconds: int,
    once: bool,
) -> None:
    logging.info("Telegram shutdown bot started. allowed_user_count=%s dry_run=%s", len(controller.config.allowed_user_ids), controller.config.dry_run)
    while True:
        try:
            updates = client.get_updates(offset=state.offset, timeout_seconds=poll_timeout_seconds)
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    state.offset = max(state.offset, update_id + 1)
                    # Confirm the Telegram update before side effects so shutdown commands are not replayed.
                    state_store.save(state)
                controller.handle_update(update)
        except Exception as exc:
            logging.exception("Telegram polling failed: %s", exc)
            if once:
                raise
            time.sleep(5)

        if once:
            break


def default_path(*parts: str) -> Path:
    return Path("C:/AbuDhabiEInk").joinpath(*parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Private Telegram control bot for the Abu Dhabi e-ink Pi.")
    parser.add_argument("--config", default=str(default_path("secrets", "telegram-bot.env")))
    parser.add_argument("--state-file", default=str(default_path("state", "telegram-bot-state.json")))
    parser.add_argument("--log-file", default=str(default_path("logs", "telegram-bot.log")))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-timeout", type=int, default=None)
    args = parser.parse_args()

    configure_logging(Path(args.log_file) if args.log_file else None)
    env = parse_env_file(Path(args.config))
    config = build_config(env, dry_run_override=args.dry_run, poll_timeout_override=args.poll_timeout)
    state_store = JsonStateStore(Path(args.state_file))
    state = state_store.load()
    client = TelegramClient(config.token)
    executor = ShellPiExecutor(config)
    controller = BotController(config, state, state_store, client, executor)
    run_poll_loop(client, controller, state_store, state, config.poll_timeout_seconds, args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
