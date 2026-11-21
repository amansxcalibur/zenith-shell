import os
import re
import shutil
import sys
from types import SimpleNamespace


OPTS = SimpleNamespace(yes=False, dry_run=False, verbose=False)


TTY = sys.stdout.isatty()
COLOR = TTY and "NO_COLOR" not in os.environ
UTF = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()


def _c(code: str) -> str:
    return f"\033[{code}m" if COLOR else ""


RED, GREEN, YELLOW = _c("0;31"), _c("0;32"), _c("1;33")
BLUE, CYAN, DIM, BOLD, NC = _c("0;34"), _c("0;36"), _c("2"), _c("1"), _c("0")


SYM = {
    "ok": "✔" if UTF else "OK",
    "err": "✖" if UTF else "X",
    "warn": "⚠" if UTF else "!",
    "dot": "•" if UTF else "*",
}
BOX = ("╭", "╮", "╰", "╯", "─", "│") if UTF else ("+", "+", "+", "+", "-", "|")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if UTF else "|/-\\"
_ANSI = re.compile(r"\033\[[0-9;]*m")
_LEADING_ANSI = re.compile(r"^(?:\033\[[0-9;]*m)*")


_step = {"n": 0, "total": 0}


def vlen(text: str) -> int:
    """Visible length (ANSI colour codes don't count)."""
    return len(_ANSI.sub("", text))


def mark(good: bool) -> str:
    return f"{GREEN}{SYM['ok']}{NC}" if good else f"{RED}{SYM['err']}{NC}"


def info(msg: str) -> None:
    print(f"{BLUE}{BOLD}::{NC} {msg}")


def ok(msg: str) -> None:
    print(f"{GREEN}{BOLD}[{SYM['ok']}]{NC} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}{BOLD}{SYM['warn']}{NC} {msg}")


def err(msg: str) -> None:
    print(f"{RED}{BOLD}{SYM['err']}{NC} {msg}")


def set_total(n: int) -> None:
    _step["n"], _step["total"] = 0, n


def step(title: str) -> None:
    _step["n"] += 1
    print(f"\n{CYAN}{BOLD}[{_step['n']}/{_step['total']}]{NC} {BOLD}{title}{NC}")


def fmt_time(sec: float) -> str:
    minutes, seconds = divmod(int(sec), 60)
    return f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"


def wrap_line(line: str, width: int) -> list[str]:
    """Word-wrap one (possibly coloured) line to `width` visible columns.

    Continuation lines keep the original indentation (+2 after a bullet/status mark),
    and the line's colour is re-applied to every wrapped piece.
    """
    if vlen(line) <= width:
        return [line]
    lead = _LEADING_ANSI.match(line).group(0)
    body = line[len(lead) :]
    indent = len(body) - len(body.lstrip(" "))
    tokens = _ANSI.sub("", body).split()
    hang = indent + (
        2 if tokens and len(tokens[0]) == 1 and not tokens[0].isalnum() else 0
    )

    limit = max(10, width - hang)
    words: list[str] = []
    for word in body.split():
        if "\033" not in word and len(word) > limit:  # absurdly long token (e.g. URL)
            words += [word[i : i + limit] for i in range(0, len(word), limit)]
        else:
            words.append(word)

    rows: list[str] = []
    cur, cur_len, cur_indent = "", 0, indent
    for word in words:
        gap = 1 if cur else 0
        if cur and cur_indent + cur_len + gap + vlen(word) > width:
            rows.append(" " * cur_indent + cur)
            cur, cur_len, cur_indent = word, vlen(word), hang
        else:
            cur = f"{cur} {word}" if cur else word
            cur_len += gap + vlen(word)
    rows.append(" " * cur_indent + cur)

    if lead:
        rows = [
            f"{lead}{row}" if row.endswith(NC) else f"{lead}{row}{NC}" for row in rows
        ]
    return rows


def panel(title: str, lines: list[str], color: str = "") -> None:
    color = color or BLUE
    tl, tr, bl, br, h, v = BOX
    limit = max(shutil.get_terminal_size((80, 20)).columns - 4, 40)
    rows = [piece for line in lines for piece in wrap_line(line, limit)]
    width = max([vlen(row) for row in rows] + [vlen(title) + 1, 38])
    inner = width + 2
    dashes = h * (inner - vlen(title) - 3)
    print(f"{color}{tl}{h} {BOLD}{title}{NC}{color} {dashes}{tr}{NC}")
    for row in rows:
        pad = " " * (width - vlen(row))
        print(f"{color}{v}{NC} {row}{pad} {color}{v}{NC}")
    print(f"{color}{bl}{h * inner}{br}{NC}")


def confirm(question: str, default: bool = True) -> bool:
    if OPTS.yes:
        return True
    if not sys.stdin.isatty():
        return False
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = (
                input(f"{BLUE}{BOLD}?{NC} {question} {DIM}{suffix}{NC} ")
                .strip()
                .lower()
            )
        except EOFError:
            return False
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        # a typo must not count as "no": some of these questions decide what gets deleted
        print("   Please answer y or n.")


def choose(question: str, options: list[str]) -> str | None:
    if not sys.stdin.isatty():
        return None
    print(f"{BLUE}{BOLD}?{NC} {question}")
    for i, option in enumerate(options, 1):
        print(f"   {i}) {option}")
    try:
        raw = input("   > ").strip()
    except EOFError:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return raw if raw in options else None
