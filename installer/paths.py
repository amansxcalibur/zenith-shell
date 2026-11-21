import os
from pathlib import Path


SHELL_NAME = "zenith-shell"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

HOME = Path.home()
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share"))
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
INSTALL_DIR = Path(os.environ.get("ZENITH_DIR", DATA_HOME / SHELL_NAME))
VENV_DIR = INSTALL_DIR / ".venv"
VENDOR_DIR = INSTALL_DIR / "vendors"
BIN_DIR = HOME / ".local" / "bin"
CARGO_BIN = HOME / ".cargo" / "bin"
STATE_FILE = (
    Path(os.environ.get("XDG_STATE_HOME", HOME / ".local" / "state"))
    / SHELL_NAME
    / "install.json"
)
LOG_FILE = (
    Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / SHELL_NAME / "install.log"
)
CONFIG_DIR = CONFIG_HOME / SHELL_NAME
FONT_DIR = HOME / ".local" / "share" / "fonts" / SHELL_NAME
ZSH_COMPLETION_DIR = DATA_HOME / "zsh" / "site-functions"


# shell -> (our completion file, where that shell loads it from)
_COMPLETION_SOURCES = ASSETS_DIR / "completions"
COMPLETIONS = {
    "bash": (
        _COMPLETION_SOURCES / "zenith-shell.bash",
        DATA_HOME / "bash-completion" / "completions" / SHELL_NAME,
    ),
    "zsh": (
        _COMPLETION_SOURCES / "_zenith-shell",
        ZSH_COMPLETION_DIR / f"_{SHELL_NAME}",
    ),
    "fish": (
        _COMPLETION_SOURCES / "zenith-shell.fish",
        CONFIG_HOME / "fish" / "completions" / f"{SHELL_NAME}.fish",
    ),
}


# the running shell's process title, main.py sets it to zenith-shell too
SHELL_PROCESS = f"^{SHELL_NAME}( |$)"


# keep the user's PATH for the "add ~/.local/bin" notice, then extend ours so
# freshly installed tools (cargo, matugen) are found
ORIGINAL_PATH = os.environ.get("PATH", "")
for _p in (CARGO_BIN, BIN_DIR):
    if str(_p) not in ORIGINAL_PATH.split(":"):
        os.environ["PATH"] = f"{_p}:{os.environ['PATH']}"
