from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_a6_publisher_uses_atomic_remote_frame_rename():
    script = (REPO_ROOT / "deploy" / "a6" / "run-render-publisher.ps1").read_text()

    assert '$remoteTmp = "$RemotePath.tmp"' in script
    assert 'Invoke-ExternalCommand' in script
    assert '"scp"' in script
    assert "mv -f '$remoteTmp' '$RemotePath'" in script


def test_a6_publisher_bounds_render_and_publish_commands():
    script = (REPO_ROOT / "deploy" / "a6" / "run-render-publisher.ps1").read_text()

    assert "[int]$RenderTimeoutSeconds = 35" in script
    assert "[int]$PublishCommandTimeoutSeconds = 12" in script
    assert "ServerAliveInterval=5" in script
    assert "timed out after $TimeoutSeconds seconds" in script
    assert "taskkill.exe /PID $process.Id /T /F" in script
    assert "RedirectStandardOutput = $false" in script


def test_a6_publisher_uses_dedicated_noninteractive_ssh_identity():
    script = (REPO_ROOT / "deploy" / "a6" / "run-render-publisher.ps1").read_text()

    assert 'Join-Path $secretsDir "publisher_ed25519"' in script
    assert 'Join-Path $secretsDir "publisher_known_hosts"' in script
    assert '"IdentitiesOnly=yes"' in script
    assert '"StrictHostKeyChecking=accept-new"' in script
    assert '"UserKnownHostsFile=$KnownHostsFile"' in script


def test_a6_publisher_can_install_a_valid_one_time_maintenance_key():
    script = (REPO_ROOT / "deploy" / "a6" / "run-render-publisher.ps1").read_text()

    assert 'Join-Path $framesDir "maintenance_authorized_key.pub"' in script
    assert "^ssh-ed25519 [A-Za-z0-9+/]+={0,3}( [A-Za-z0-9_.@-]+)?$" in script
    assert '"$($remote):.ssh/maintenance_authorized_key.pub.tmp"' in script
    assert "cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.new" in script
    assert "cat ~/.ssh/maintenance_authorized_key.pub.tmp >> ~/.ssh/authorized_keys.new" in script
    assert "mv ~/.ssh/authorized_keys.new ~/.ssh/authorized_keys" in script
    assert "Remove-Item -LiteralPath $maintenanceKeyHandoff" in script
    assert "Publisher SSH key not found" in script


def test_a6_publisher_has_fixed_read_only_pi_maintenance_status_flow():
    script = (REPO_ROOT / "deploy" / "a6" / "run-render-publisher.ps1").read_text()

    assert 'Join-Path $framesDir "maintenance-status.request"' in script
    assert "function Export-OneTimeMaintenanceStatus" in script
    assert "export-maintenance-status.sh" in script
    assert '.Replace("`r`n", "`n")' in script
    assert "Export-OneTimeMaintenanceStatus" in script
    assert "Pi maintenance status request failed" in script

    exporter = (REPO_ROOT / "deploy" / "pi" / "export-maintenance-status.sh").read_text()
    assert "systemctl show ad-eink-display.service" in exporter
    assert "journalctl -u ad-eink-display.service" in exporter
    assert 'ssh-keygen -lf "$HOME/.ssh/authorized_keys"' in exporter


def test_a6_publisher_preserves_render_time_and_enforces_end_to_end_deadline():
    script = (REPO_ROOT / "deploy" / "a6" / "run-render-publisher.ps1").read_text()

    assert "[int]$EndToEndDeadlineSeconds = 42" in script
    assert "Get-RemainingDeadlineSeconds" in script
    assert "touch -m -d '@$RenderedAtUnixSeconds'" in script
    assert "Publish-Frame -CycleStarted $renderStarted" in script
    assert "last-successful-publish.txt" in script
    assert "Repair-PublisherIdentityAcl" in script
    assert 'S-1-5-18' in script
    assert 'S-1-5-32-544' in script
    assert 'SetAccessRuleProtection($true, $false)' in script
    assert 'Set-Acl -LiteralPath $IdentityFile' in script


def test_a6_installer_registers_publisher_watchdog():
    script = (REPO_ROOT / "deploy" / "a6" / "install-a6.ps1").read_text()

    assert '"-N", \'""\'' in script
    assert "watch-render-publisher.ps1" in script
    assert "Abu Dhabi E-Ink Publisher Watchdog" in script
    assert "/SC MINUTE /MO 1" in script
    assert "Project dependency install" in script
    assert "Playwright Chromium install" in script
    assert "-MultipleInstances IgnoreNew" in script
    assert "-ExecutionTimeLimit (New-TimeSpan -Seconds 0)" in script
    assert "New-ScheduledTaskTrigger -AtStartup" in script
    assert 'New-ScheduledTaskPrincipal -UserId "SYSTEM"' in script
    assert "/RU SYSTEM /RL HIGHEST" in script
    assert "publisher_ed25519" in script
    assert "publisher_known_hosts" in script
    assert "PLAYWRIGHT_BROWSERS_PATH" in script
    assert 'S-1-5-18' in script
    assert 'S-1-5-32-544' in script
    assert 'Set-Acl -LiteralPath $publisherKey' in script


def test_a6_ssh_repair_persists_for_tailscale_and_local_networks():
    script = (REPO_ROOT / "deploy" / "a6" / "repair-ssh.ps1").read_text()

    assert "-Verb RunAs" in script
    assert "$PSCommandPath" in script
    assert "Set-Service -Name sshd -StartupType Automatic" in script
    assert "-Profile Any" in script
    assert '"100.64.0.0/10", "LocalSubnet"' in script


def test_a6_watchdog_uses_locale_independent_task_state_and_bounds_logs():
    script = (REPO_ROOT / "deploy" / "a6" / "watch-render-publisher.ps1").read_text()

    assert "Get-ScheduledTask -TaskName $TaskName" in script
    assert "Get-ScheduledTaskInfo -TaskName $TaskName" in script
    assert '$task.State -eq "Running"' in script
    assert "[int]$MaxFrameAgeSeconds = 90" in script
    assert "[int]$MaxLogAgeSeconds = 90" in script
    assert "[int]$LogRetentionDays = 14" in script
    assert 'publisher-watchdog-*.log' in script
    assert 'last-successful-publish.txt' in script
    assert "successful publish age" in script
    assert "withinStartupGrace" in script
    assert "awaiting first publish within startup grace" in script
    assert 'TelegramTaskName = "Abu Dhabi E-Ink Telegram Control Bot"' in script
    assert "Start-TelegramTaskIfNeeded" in script
    assert 'schtasks /Run /TN $TelegramTaskName' in script


def test_telegram_bot_runs_at_startup_as_system_with_publisher_identity():
    installer = (REPO_ROOT / "deploy" / "a6" / "install-telegram-bot.ps1").read_text()
    bot = (REPO_ROOT / "deploy" / "a6" / "telegram-shutdown-bot.py").read_text()

    assert "New-ScheduledTaskTrigger -AtStartup" in installer
    assert 'New-ScheduledTaskPrincipal -UserId "SYSTEM"' in installer
    assert "SSH_IDENTITY_FILE=" in installer
    assert "SSH_KNOWN_HOSTS_FILE=" in installer
    assert 'ssh_identity_file=env.get("SSH_IDENTITY_FILE"' in bot
    assert 'ssh_known_hosts_file=env.get("SSH_KNOWN_HOSTS_FILE"' in bot


def test_waveshare_install_uses_local_dual_controller_adapter():
    script = (REPO_ROOT / "deploy" / "pi" / "install-waveshare-10in85.sh").read_text()
    bootstrap = (REPO_ROOT / "deploy" / "pi" / "bootstrap-pi.sh").read_text()
    environment = (REPO_ROOT / "deploy" / "pi" / "ad-eink-display.defaults").read_text()

    assert "ad-eink-display.defaults" in script
    assert 'sudo cp "${SCRIPT_DIR}/ad-eink-display.defaults" "${INSTALL_DIR}/ad-eink-display.defaults"' in bootstrap
    assert "Missing ${SCRIPT_DIR}/ad-eink-display.defaults" in script
    assert "WAVESHARE_10IN85_SPI_HZ=\"2000000\"" in environment
    assert "--driver-module waveshare_10in85_bw" in environment
    assert "--driver-lib /opt/abu-dhabi-eink" in environment
    assert "waveshare_10in85_c_bridge" not in script
    assert "waveshare-10in85-display-raw" not in script
    assert "SPI_line 0" not in script
    assert "--clear-on-start" not in environment
    assert "--startup-full-refresh-count 1" in environment
    assert "--disable-partial" in environment
    assert "--require-current-minute" in environment
    assert "--latest-display-start-second 45" in environment


def test_display_client_forces_startup_full_refresh_and_clear_path():
    script = (REPO_ROOT / "deploy" / "pi" / "display-current.py").read_text()

    assert "--clear-on-start" in script
    assert "--startup-full-refresh-count" in script
    assert "hardware_full_refresh = full_refresh or args.disable_partial" in script
    assert "force_startup_full" in script
    assert "full_refresh=%s" in script


def test_waveshare_adapter_preserves_last_known_working_vendor_control_path():
    script = (REPO_ROOT / "deploy" / "pi" / "waveshare_10in85_bw.py").read_text()

    assert "no_cs = True" not in script
    assert "GPIO_CS_M_PIN" not in script
    assert "GPIO_CS_S_PIN" not in script
    assert "_patch_shared_controller_commands" not in script
    assert "_init_registers" not in script
    assert "result = self._epd.init()" in script
    assert "self._set_full_half_windows()" in script


def test_display_service_uses_safe_single_writer_shutdown_lifecycle():
    service = (REPO_ROOT / "deploy" / "pi" / "ad-eink-display.service").read_text()
    runner = (REPO_ROOT / "deploy" / "pi" / "run-display-current.sh").read_text()

    assert "RuntimeDirectory=abu-dhabi-eink" in service
    assert "KillSignal=SIGTERM" in service
    assert "TimeoutStopSec=45" in service
    assert "Restart=on-failure" in service
    assert "--lock-file /run/abu-dhabi-eink/display.lock" in runner
    assert "--hardware-idle-seconds 90" in runner
