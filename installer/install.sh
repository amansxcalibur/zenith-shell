#!/usr/bin/env bash

set -euo pipefail

REPO_URL="${ZENITH_REPO:-https://github.com/amansxcalibur/zenith-shell.git}"
INSTALL_DIR="${ZENITH_DIR:-$HOME/.config/zenith-shell}"
export ZENITH_DIR="$INSTALL_DIR"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; BLUE=$'\033[0;34m'
    YELLOW=$'\033[1;33m'; BOLD=$'\033[1m'; NC=$'\033[0m'
else
    RED=""; GREEN=""; BLUE=""; YELLOW=""; BOLD=""; NC=""
fi
info() { printf '%s::%s %s\n' "$BLUE$BOLD" "$NC" "$*"; }
ok()   { printf '%s[✔]%s %s\n' "$GREEN$BOLD" "$NC" "$*"; }
warn() { printf '%s⚠%s %s\n' "$YELLOW$BOLD" "$NC" "$*"; }
die()  { printf '%s✖%s %s\n' "$RED$BOLD" "$NC" "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Zenith Shell installer

Usage: install.sh [command] [options]

Commands:
  install    Full install (default)
  sync       Install only what is missing for the chosen WM(s)
             (use this after switching between i3 and sway)
  update     Pull the latest version, then sync dependencies and re-apply setup
  doctor     Show which dependencies are present / missing
  uninstall  Remove Zenith Shell (asks whether to keep your config.json)

Options:
  --wm {auto,i3,sway,both}   Window manager(s) to set up (default: auto)
  --dry-run                  Run pre-flight checks and show the plan; change nothing
  --purge                    uninstall: also remove tools that were built from source
  -y, --yes                  Never ask; accept automatic prerequisite installs
  -h, --help                 Show this help

After installing, the same tool is available as:  zenith-shell setup <command> [options]
EOF
}

for arg in "$@"; do
    if [[ "$arg" == "-h" || "$arg" == "--help" ]]; then usage; exit 0; fi
done

# -------- Minimal sanity (everything else is checked in python) --------
[[ "$(uname -s)" == "Linux" ]] || die "Linux only."
[[ $EUID -ne 0 ]] || die "Do not run as root. sudo is requested automatically when needed."

detect_distro() {
    if [[ -n "${ZENITH_DISTRO:-}" ]]; then echo "$ZENITH_DISTRO"; return; fi
    [[ -r /etc/os-release ]] || die "Cannot read /etc/os-release – unsupported system."
    local id like
    id=$(. /etc/os-release; echo "${ID:-}")
    like=$(. /etc/os-release; echo "${ID_LIKE:-}")
    case " $id $like " in
        *" arch "*)                   echo arch ;;
        *" ubuntu "*|*" debian "*)    echo ubuntu ;;
        *) die "Unsupported distro (ID=$id, ID_LIKE=$like). Supported: Arch-based, Ubuntu/Debian-based." ;;
    esac
}
DISTRO="$(detect_distro)"
info "Detected distro family: ${BOLD}${DISTRO}${NC}"

check_python() {
    command -v python3 >/dev/null 2>&1 || die "python3 is required."
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
        || die "Python 3.10+ is required (found $(python3 --version 2>&1))."
}

# -------- commands that work on an existing install: no bootstrap, no git pull here --------
# (`update` does its own fetch/pull so it can re-launch the *new* installer afterwards)
for arg in "$@"; do
    case "$arg" in
        uninstall|update|sync|doctor)
            check_python
            [[ -f "$INSTALL_DIR/installer/main.py" ]] \
                || die "Zenith Shell is not installed ($INSTALL_DIR/installer/main.py not found). Run: install.sh"
            exec python3 "$INSTALL_DIR/installer/main.py" --distro "$DISTRO" "$@"
            ;;
    esac
done

# -------- Bootstrap tools: git, curl, python3 (>=3.10) --------
need=()
command -v git  >/dev/null 2>&1 || need+=(git)
command -v curl >/dev/null 2>&1 || need+=(curl)
if ! command -v python3 >/dev/null 2>&1; then
    if [[ "$DISTRO" == "arch" ]]; then need+=(python); else need+=(python3); fi
fi
if [[ "$DISTRO" == "ubuntu" ]] && command -v python3 >/dev/null 2>&1 \
   && ! python3 -c 'import venv, ensurepip' >/dev/null 2>&1; then
    need+=(python3-venv python3-pip)
fi

if [[ ${#need[@]} -gt 0 ]]; then
    command -v sudo >/dev/null 2>&1 || die "sudo is required to install: ${need[*]}"
    info "Installing bootstrap packages: ${need[*]}"
    if [[ "$DISTRO" == "arch" ]]; then
        sudo pacman -S --needed --noconfirm "${need[@]}"
    else
        sudo apt-get -o DPkg::Lock::Timeout=300 update -qq
        sudo env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y "${need[@]}"
    fi
fi

check_python

# -------- Repository --------
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating Zenith Shell..."
    git -C "$INSTALL_DIR" pull --ff-only --quiet \
        || warn "Could not fast-forward (local changes?). Continuing with the existing checkout."
elif [[ -e "$INSTALL_DIR" ]]; then
    die "$INSTALL_DIR exists but is not a git checkout. Move it away and re-run."
else
    info "Cloning Zenith Shell..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --depth=1 "$REPO_URL" "$INSTALL_DIR" || die "git clone failed – check your connection."
fi

[[ -f "$INSTALL_DIR/installer/main.py" ]] || die "installer/main.py not found in $INSTALL_DIR."

exec python3 "$INSTALL_DIR/installer/main.py" --distro "$DISTRO" "$@"