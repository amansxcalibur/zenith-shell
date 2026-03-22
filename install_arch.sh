#!/usr/bin/env bash
set -euo pipefail

# ================================
#  Zenith Shell – Install Script
# ================================

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}${BOLD}::${NC} $1"; }
log_success() { echo -e "${GREEN}${BOLD}[✔]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}${BOLD}⚠${NC} $1"; }
log_error()   { echo -e "${RED}${BOLD}✖${NC} $1"; }

log_info "Initializing Zenith Shell installer..."

REPO_URL="https://github.com/amansxcalibur/zenith-shell.git"
SHELL_NAME="zenith-shell"
INSTALL_DIR="$HOME/.config/$SHELL_NAME"
VENV_DIR="$INSTALL_DIR/.venv"

# -------- Pre-flight Checks --------

# 1. Check Distro
if ! command -v pacman >/dev/null; then
    log_error "This script supports Arch Linux (pacman) only."
    exit 1
fi

# 2. Check Virtual Env
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    log_error "Active Python virtual environment detected: $VIRTUAL_ENV"
    echo "   Please deactivate it before running this installer."
    exit 1
fi

# -------- Helpers --------
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# -------- AUR Helper --------
log_info "Checking for AUR helper..."

aur_helper=""
if command_exists paru; then
    aur_helper="paru"
    log_success "Using paru"
elif command_exists yay; then
    aur_helper="yay"
    log_success "Using yay"
else
    log_info "No AUR helper found. Installing yay-bin..."
    tmpdir=$(mktemp -d)
    git clone --depth=1 https://aur.archlinux.org/yay-bin.git "$tmpdir/yay-bin"
    (cd "$tmpdir/yay-bin" && makepkg -si --noconfirm)
    rm -rf "$tmpdir"
    aur_helper="yay"
    log_success "yay installed"
fi

# -------- Essential Bootstrap Tools --------
log_info "Checking for essential bootstrap tools..."

ESSENTIAL_DEPS=()
if ! command_exists git;  then ESSENTIAL_DEPS+=("git");  fi
if ! command_exists curl; then ESSENTIAL_DEPS+=("curl"); fi

if [ ${#ESSENTIAL_DEPS[@]} -gt 0 ]; then
    log_info "Installing missing bootstrap dependencies: ${ESSENTIAL_DEPS[*]}"
    sudo pacman -S --needed --noconfirm "${ESSENTIAL_DEPS[@]}"
fi

# -------- Repository Setup --------
if [ -d "$INSTALL_DIR" ]; then
    log_info "Updating Zenith-Shell..."
    git -C "$INSTALL_DIR" pull
else
    log_info "Cloning Zenith-Shell..."
    git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
fi

# -------- System Dependencies --------
log_info "Installing runtime dependencies via $aur_helper..."

DEPENDENCIES=(
    python-gobject
    python-cairo
    gtk3
    libdbusmenu-gtk3
    gobject-introspection
    gnome-bluetooth-3.0
    brightnessctl
    feh
    playerctl
    matugen-bin
    fabric-cli-git
    gray-git
    libnotify
)

$aur_helper -S --needed --noconfirm "${DEPENDENCIES[@]}"

# -------- Python Environment --------
log_info "Setting up Python virtual environment..."

# --system-site-packages so the venv can see python-gobject installed via pacman
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

(
    source "$VENV_DIR/bin/activate"
    python -m pip install --upgrade pip

    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        log_info "Installing Python requirements (this may take a moment)..."
        python -m pip install -r "$INSTALL_DIR/requirements.txt"
    else
        log_warn "requirements.txt not found, skipping Python deps."
    fi
)

# -------- Fonts --------
install_fonts() {
    local FONT_DIR="$HOME/.local/share/fonts/$SHELL_NAME"
    mkdir -p "$FONT_DIR"
    local ROBOTO_FILE="$FONT_DIR/RobotoFlex.ttf"
    local SYMBOLS_FILE="$FONT_DIR/MaterialSymbolsRounded.ttf"
    local GOOGLE_SANS_FLEX_FILE="$FONT_DIR/GoogleSansFlex.ttf"

    if [[ -f "$ROBOTO_FILE" && -f "$SYMBOLS_FILE" && -f "$GOOGLE_SANS_FLEX_FILE" ]]; then
        log_success "Fonts present."
        return
    fi

    log_info "Downloading fonts..."
    curl -L --fail --silent --show-error -o "$ROBOTO_FILE" "https://raw.githubusercontent.com/googlefonts/roboto-flex/main/fonts/RobotoFlex%5BGRAD%2CXOPQ%2CXTRA%2CYOPQ%2CYTAS%2CYTDE%2CYTFI%2CYTLC%2CYTUC%2Copsz%2Cslnt%2Cwdth%2Cwght%5D.ttf"
    curl -L --fail --silent --show-error -o "$GOOGLE_SANS_FLEX_FILE" "https://raw.githubusercontent.com/amansxcalibur/zenith-resources/gh-pages/fonts/Google_Sans_Flex/GoogleSansFlex-VariableFont_GRAD%2CROND%2Copsz%2Cslnt%2Cwdth%2Cwght.ttf"
    curl -L --fail --silent --show-error -o "$SYMBOLS_FILE" "https://raw.githubusercontent.com/google/material-design-icons/master/variablefont/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.ttf"

    log_info "Updating font cache..."
    fc-cache -f
}

install_fonts

# -------- Launcher Script --------
mkdir -p "$HOME/.local/bin"
LAUNCHER_PATH="$HOME/.local/bin/$SHELL_NAME"

log_info "Generating launcher at $LAUNCHER_PATH..."

cat << EOF > "$LAUNCHER_PATH"
#!/usr/bin/env bash
cd "$INSTALL_DIR"
exec "$VENV_DIR/bin/python" main.py "\$@" &
disown
EOF

chmod +x "$LAUNCHER_PATH"

# -------- Bootstrap --------
log_info "Running Zenith bootstrap..."
PYTHONPATH="$INSTALL_DIR" "$VENV_DIR/bin/python" -m config.bootstrap

echo
log_success "Successfully installed"
echo
log_info "Summary:"
echo "  • Zenith installed to: $INSTALL_DIR"
echo "  • Launcher created at: $LAUNCHER_PATH"
echo "  • i3 configuration snippets added at ~/.config/i3/"

echo -e "${BLUE}"
cat << "EOF"
 /$$$$$$$$ /$$$$$$$$ /$$   /$$ /$$$$$$ /$$$$$$$$ /$$   /$$
|_____ $$ | $$_____/| $$$ | $$|_  $$_/|__  $$__/| $$  | $$
     /$$/ | $$      | $$$$| $$  | $$     | $$   | $$  | $$
    /$$/  | $$$$$   | $$ $$ $$  | $$     | $$   | $$$$$$$$
   /$$/   | $$__/   | $$  $$$$  | $$     | $$   | $$__  $$
  /$$/    | $$      | $$\  $$$  | $$     | $$   | $$  | $$
 /$$$$$$$$| $$$$$$$$| $$ \  $$ /$$$$$$   | $$   | $$  | $$
|________/|________/|__/  \__/|______/   |__/   |__/  |__/
EOF
echo -e "${NC}"

echo -e "⚠️  ${BOLD}IMPORTANT NOTICE:${NC}"
echo "   $SHELL_NAME has added i3 configuration snippets and keybindings."
echo "   If you already have custom i3 keybindings, you may encounter"
echo "   duplicate keybinding warnings from i3."
echo ""
echo "   Please review and resolve any conflicts in:"
echo "     ~/.config/i3/config  (or your included config files)"
echo ""

echo
echo -e "⚠️  ${BOLD}PICOM CONFIGURATION NOTICE:${NC}"
echo "   $SHELL_NAME ships Picom configuration files for rounded corners"
echo "   and compositor effects."
echo
echo "   Config location:"
echo "     $INSTALL_DIR/config/picom"
echo
echo "   Online reference:"
echo "     https://github.com/amansxcalibur/zenith-shell/tree/main/config/picom"
echo

# -------- Picom presence check --------
if ! command_exists picom; then
    log_warn "Picom is not installed. Compositor effects will be disabled by default."
    log_warn "Install Picom (v12 or newer) to enable rounded corners and effects."
else
    echo "   Picom detected on your system."
fi

echo
echo "   Compatibility notice:"
echo "     • Picom < v12"
echo "     • Distro-patched Picom builds using legacy config syntax"
echo
echo "   These may produce warnings, errors, or missing compositor effects."
echo
echo "   Recommended upstream Picom:"
echo "     https://github.com/yshui/picom  (v12 or newer)"
echo

# Check if the bin dir is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo -e "⚠️  ${BOLD}ACTION REQUIRED:${NC}"
    echo "   $HOME/.local/bin is not in your PATH."
    echo "   Please add the following line to your shell config (~/.bashrc, ~/.zshrc):"
    echo ""
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "   After updating your PATH, you can either:"
    echo "     • restart your i3wm session"
    echo "     • or start it manually with: ${BOLD}zenith-shell${NC}"
else
    echo -e "To start, run: ${BOLD}zenith-shell${NC}, or restart your i3wm session"
fi