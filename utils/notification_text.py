import re
import html

_TAG = re.compile(r"</?(?:b|i|u|a|img|br)\b[^<>]*>", re.IGNORECASE)
_BREAK = re.compile(r"<br\b[^<>]*>", re.IGNORECASE)
_NEWLINE = re.compile(r"\r\n|[\r\n\u2029]")

# pango counts line limits per paragraph, so real newlines dodge them
LINE_SEPARATOR = "\u2028"


def get_body_text(body: str, single_line: bool = False) -> str:
    text = _TAG.sub("", _BREAK.sub("\n", body or ""))
    text = html.unescape(text).replace("\0", "").strip()
    if single_line:
        return " ".join(text.split())
    return _NEWLINE.sub(LINE_SEPARATOR, text)
