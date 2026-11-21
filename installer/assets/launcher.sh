#!/usr/bin/env bash
cd "@INSTALL_DIR@" || exit 1

PROCESS='@PROCESS@'
COMMANDS=(start stop restart status lock settings setup help)

running() { pgrep -f "$PROCESS" >/dev/null; }

start_shell() {
    if running; then
        echo "zenith-shell is already running (use: zenith-shell restart)"
        return 0
    fi
    "@VENV@/bin/python" main.py &
    disown
}

stop_shell() {
    pkill -f "$PROCESS" || return 1
    for _ in {1..50}; do
        running || return 0
        sleep 0.1
    done
    pkill -KILL -f "$PROCESS"
}

case "${1:-}" in
    ""|start)
        start_shell
        ;;
    stop)
        stop_shell || echo "zenith-shell is not running"
        ;;
    restart)
        stop_shell
        start_shell
        ;;
    status)
        if pids=$(pgrep -f "$PROCESS"); then
            echo "zenith-shell is running (pid ${pids//$'\n'/, })"
        else
            echo "zenith-shell is not running"
            exit 1
        fi
        ;;
    -h|--help|help)
        cat <<'EOF'
Usage:
    zenith-shell [start]          start the shell
    zenith-shell stop             stop the shell
    zenith-shell restart          restart the shell
    zenith-shell status           show whether the shell is running
    zenith-shell lock [-f]        lock the screen (-f: return once locked)
    zenith-shell settings         open the settings window
    zenith-shell setup <cmd>      install | sync | update | doctor | uninstall | logs
                                  (zenith-shell setup --help for details)
    zenith-shell -V, --version    show the installed version
    zenith-shell -h, --help       show this message
EOF
        ;;
    -V|--version)
        version=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' version.json 2>/dev/null)
        name=$(sed -n 's/.*"name": *"\([^"]*\)".*/\1/p' version.json 2>/dev/null)
        commit=$(git rev-parse --short HEAD 2>/dev/null)
        echo "zenith-shell ${version:-unknown}${name:+ $name}${commit:+ ($commit)}"
        ;;
    lock)
        # foreground + exec: xss-lock and swayidle -w watch this process,
        # and xss-lock's sleep fd must reach the locker
        shift
        exec "@VENV@/bin/python" -m lock "$@"
        ;;
    settings)
        exec "@VENV@/bin/python" -m settings
        ;;
    setup)
        shift
        export ZENITH_PROG="zenith-shell setup"
        export ZENITH_DIR="@INSTALL_DIR@"
        py="@VENV@/bin/python"
        "$py" -c '' 2>/dev/null || py=python3
        exec "$py" installer/main.py "$@"
        ;;
    *)
        echo "zenith-shell: unknown command '$1'" >&2
        match=$(python3 -c 'import difflib, sys; print(*difflib.get_close_matches(sys.argv[1], sys.argv[2:], 1))' "$1" "${COMMANDS[@]}" 2>/dev/null)
        [[ -z "$match" ]] || echo "Did you mean: zenith-shell $match" >&2
        echo "See: zenith-shell --help" >&2
        exit 2
        ;;
esac
