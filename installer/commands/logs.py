import collections
import sys

from installer.paths import LOG_FILE
from installer.ui import info


def cmd_logs(args) -> int:
    if not LOG_FILE.exists():
        info(f"No installer log yet ({LOG_FILE}).")
        return 0
    with open(LOG_FILE, encoding="utf-8", errors="replace") as log:
        sys.stdout.writelines(collections.deque(log, maxlen=max(args.lines, 0)))
    info(f"Full log: {LOG_FILE}")
    return 0
