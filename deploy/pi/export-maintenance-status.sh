#!/bin/sh
set -u

output_path="${1:-/var/lib/abu-dhabi-eink/maintenance-status.txt}"
temporary_path="${output_path}.tmp"

{
    echo "=== identity ==="
    id
    hostname
    date --iso-8601=seconds
    echo "=== ssh authorized-key configuration ==="
    grep -RhsE '^[[:space:]]*AuthorizedKeysFile|^[[:space:]]*PubkeyAuthentication|^[[:space:]]*Match' \
        /etc/ssh/sshd_config /etc/ssh/sshd_config.d 2>/dev/null || true
    echo "=== home ssh permissions ==="
    stat -c '%U:%G %a %n' "$HOME" "$HOME/.ssh" "$HOME/.ssh/authorized_keys" 2>/dev/null || true
    ssh-keygen -lf "$HOME/.ssh/authorized_keys" 2>/dev/null || true
    echo "=== display defaults ==="
    cat /etc/default/ad-eink-display 2>/dev/null || true
    echo "=== display unit ==="
    systemctl cat ad-eink-display.service 2>/dev/null || true
    echo "=== display process ==="
    ps -eo pid,lstart,args | grep -E '[d]isplay-current|[w]aveshare' || true
    echo "=== display service state ==="
    systemctl show ad-eink-display.service \
        -p ActiveState -p SubState -p UnitFileState -p ExecMainStartTimestamp -p ExecMainPID \
        2>/dev/null || true
    echo "=== recent display journal ==="
    journalctl -u ad-eink-display.service -n 100 --no-pager 2>/dev/null || true
} > "$temporary_path"

mv -f "$temporary_path" "$output_path"
