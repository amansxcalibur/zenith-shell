import sys
from pathlib import Path

# install.sh, the launcher and older installers mid-update all run this file by
# path, so it stays here. The repo root goes first: config/ lives there too
sys.path[0] = str(Path(__file__).resolve().parents[1])

from installer.cli import main

sys.exit(main())
