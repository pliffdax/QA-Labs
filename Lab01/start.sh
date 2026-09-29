#!/usr/bin/env bash
set -euo pipefail
LAB=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$LAB/results" "$LAB/sandbox"
run=$(date +%Y%m%d-%H%M%S)
# Preserve only variables needed for a graphical session, not arbitrary inherited secrets.
exec env -i HOME="$HOME" USER="$USER" LOGNAME="$USER" PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin TERM="${TERM:-xterm}" DISPLAY="${DISPLAY:-}" XAUTHORITY="${XAUTHORITY:-}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" LAB="$LAB" HISTFILE="$LAB/results/history-$run.txt" HISTSIZE=10000 HISTFILESIZE=20000 PS1='QA01 \u@\h:\w\$ ' PROMPT_COMMAND='history -a' script -q -f "$LAB/results/session-$run.log" -c 'bash --noprofile --rcfile "$LAB/shell.bashrc" -i'
