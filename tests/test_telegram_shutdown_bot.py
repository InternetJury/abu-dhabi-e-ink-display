from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


BOT_PATH = Path(__file__).resolve().parents[1] / "deploy" / "a6" / "telegram-shutdown-bot.py"
SPEC = importlib.util.spec_from_file_location("telegram_shutdown_bot", BOT_PATH)
bot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = bot
SPEC.loader.exec_module(bot)


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class FakeExecutor:
    def __init__(self) -> None:
        self.status_calls = 0
        self.shutdown_calls = 0

    def status(self) -> str:
        self.status_calls += 1
        return "display_service=active"

    def shutdown(self) -> str:
        self.shutdown_calls += 1
        return "shutdown requested"


class FakeStateStore:
    def __init__(self) -> None:
        self.saved_states = []

    def save(self, state) -> None:
        self.saved_states.append((state.offset, state.last_shutdown_epoch))


def make_update(user_id: int, text: str, chat_type: str = "private", chat_id: int | None = None, update_id: int = 1):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": user_id if chat_id is None else chat_id, "type": chat_type},
            "from": {"id": user_id, "is_bot": False},
            "text": text,
        },
    }


def make_controller(allowed_user_ids={42}, clock_value=1000.0, code="ABC123"):
    telegram = FakeTelegram()
    executor = FakeExecutor()
    state_store = FakeStateStore()
    state = bot.BotState()
    config = bot.BotConfig(
        token="token",
        allowed_user_ids=set(allowed_user_ids),
        confirm_ttl_seconds=60,
        shutdown_cooldown_seconds=300,
    )
    controller = bot.BotController(
        config,
        state,
        state_store,
        telegram,
        executor,
        clock=lambda: clock_value,
        code_factory=lambda: code,
    )
    return controller, telegram, executor, state, state_store


def test_parse_command_strips_bot_username_and_args():
    assert bot.parse_command("/STATUS@MyBot extra") == ("/status", ["extra"])


def test_whoami_is_available_without_authorizing_operational_access():
    controller, telegram, executor, _state, _store = make_controller(allowed_user_ids=set())

    controller.handle_update(make_update(777, "/whoami"))

    assert executor.status_calls == 0
    assert executor.shutdown_calls == 0
    assert telegram.messages == [(777, "Your Telegram user ID is 777.\nAdd this numeric ID to TELEGRAM_ALLOWED_USER_IDS on the A6.")]


def test_unauthorized_whoami_is_silent_after_allowlist_is_configured():
    controller, telegram, executor, _state, _store = make_controller(allowed_user_ids={42})

    controller.handle_update(make_update(777, "/whoami"))

    assert executor.status_calls == 0
    assert executor.shutdown_calls == 0
    assert telegram.messages == []
    assert controller.rejections.unauthorized == 1


def test_authorized_whoami_remains_available_after_allowlist_is_configured():
    controller, telegram, executor, _state, _store = make_controller(allowed_user_ids={42})

    controller.handle_update(make_update(42, "/whoami"))

    assert executor.status_calls == 0
    assert executor.shutdown_calls == 0
    assert telegram.messages == [(42, "Your Telegram user ID is 42.\nThis account is authorized for e-ink control.")]


def test_unauthorized_status_is_ignored_without_operational_response():
    controller, telegram, executor, _state, _store = make_controller(allowed_user_ids={42})

    controller.handle_update(make_update(777, "/status"))

    assert executor.status_calls == 0
    assert executor.shutdown_calls == 0
    assert telegram.messages == []
    assert controller.rejections.unauthorized == 1


def test_authorized_status_runs_status_only():
    controller, telegram, executor, _state, _store = make_controller(allowed_user_ids={42})

    controller.handle_update(make_update(42, "/status"))

    assert executor.status_calls == 1
    assert executor.shutdown_calls == 0
    assert telegram.messages == [(42, "Pi status:\ndisplay_service=active")]


def test_shutdown_requires_confirmation_code_before_executor_runs():
    controller, telegram, executor, _state, _store = make_controller(allowed_user_ids={42})

    controller.handle_update(make_update(42, "/shutdown_pi"))

    assert executor.shutdown_calls == 0
    assert "Confirm Raspberry Pi shutdown" in telegram.messages[-1][1]
    assert "/confirm ABC123" in telegram.messages[-1][1]


def test_wrong_confirmation_does_not_shutdown():
    controller, telegram, executor, _state, _store = make_controller(allowed_user_ids={42})

    controller.handle_update(make_update(42, "/shutdown_pi"))
    controller.handle_update(make_update(42, "/confirm WRONG"))

    assert executor.shutdown_calls == 0
    assert telegram.messages[-1] == (42, "Confirmation code did not match.")


def test_valid_confirmation_runs_one_fixed_shutdown_action_and_saves_cooldown():
    controller, telegram, executor, state, state_store = make_controller(allowed_user_ids={42}, clock_value=1000.0)

    controller.handle_update(make_update(42, "/shutdown_pi"))
    controller.handle_update(make_update(42, "/confirm ABC123"))

    assert executor.shutdown_calls == 1
    assert state.last_shutdown_epoch == 1000.0
    assert state_store.saved_states[-1] == (0, 1000.0)
    assert telegram.messages[-1] == (42, "Raspberry Pi shutdown requested.\nshutdown requested")


def test_expired_confirmation_does_not_shutdown():
    times = iter([900.0, 1000.0, 1100.0])
    telegram = FakeTelegram()
    executor = FakeExecutor()
    state = bot.BotState()
    config = bot.BotConfig(token="token", allowed_user_ids={42}, confirm_ttl_seconds=10)
    controller = bot.BotController(
        config,
        state,
        None,
        telegram,
        executor,
        clock=lambda: next(times),
        code_factory=lambda: "ABC123",
    )

    controller.handle_update(make_update(42, "/shutdown_pi"))
    controller.handle_update(make_update(42, "/confirm ABC123"))

    assert executor.shutdown_calls == 0
    assert telegram.messages[-1] == (42, "Shutdown confirmation expired.")


def test_non_private_chat_is_ignored_even_for_allowed_user():
    controller, telegram, executor, _state, _store = make_controller(allowed_user_ids={42})

    controller.handle_update(make_update(42, "/status", chat_type="group", chat_id=-100))

    assert executor.status_calls == 0
    assert executor.shutdown_calls == 0
    assert telegram.messages == []
    assert controller.rejections.non_private == 1


def test_shell_executor_rejects_unsafe_ssh_components():
    config = bot.BotConfig(token="token", allowed_user_ids={42}, pi_host="host;rm", pi_user="display")

    try:
        bot.ShellPiExecutor(config)
    except ValueError as exc:
        assert "Pi host" in str(exc)
    else:
        raise AssertionError("unsafe host should be rejected")


def test_shell_executor_uses_dedicated_identity_and_known_hosts(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        return type("Result", (), {"stdout": "active", "stderr": "", "returncode": 0})()

    monkeypatch.setattr(bot.subprocess, "run", fake_run)
    config = bot.BotConfig(
        token="token",
        allowed_user_ids={42},
        ssh_identity_file="C:/local/secrets/publisher_ed25519",
        ssh_known_hosts_file="C:/local/secrets/publisher_known_hosts",
    )

    assert bot.ShellPiExecutor(config).status() == "active"
    command = captured["command"]
    assert command[:3] == ["ssh", "-i", "C:/local/secrets/publisher_ed25519"]
    assert "IdentitiesOnly=yes" in command
    assert "StrictHostKeyChecking=accept-new" in command
    assert "UserKnownHostsFile=C:/local/secrets/publisher_known_hosts" in command
    assert command[-2] == "display@ad-eink-pi.local"
    assert command[-1] == bot.PI_STATUS_COMMAND


def test_poll_loop_persists_offset_before_handling_update():
    class FakeClient:
        def get_updates(self, offset: int, timeout_seconds: int):
            return [make_update(42, "/status", update_id=15)]

    controller, telegram, executor, state, state_store = make_controller(allowed_user_ids={42})

    bot.run_poll_loop(FakeClient(), controller, state_store, state, poll_timeout_seconds=0, once=True)

    assert state.offset == 16
    assert state_store.saved_states[0] == (16, 0.0)
    assert executor.status_calls == 1
    assert telegram.messages[-1] == (42, "Pi status:\ndisplay_service=active")
