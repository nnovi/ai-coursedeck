"""Text normalization and boilerplate rules shared by all parsers."""

import re
import unicodedata
from collections import Counter

LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st",
                           "ﬆ": "st"})
# Zero-width characters and the soft hyphen carry no text; odd spaces become a plain space.
INVISIBLE_RE = re.compile(r"[\u00ad\u200b-\u200d\u2060\ufeff]")
SPACES_RE = re.compile(r"[\u00a0\u2000-\u200a\u202f\u205f\u3000\t]+")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# UTF-8 bytes decoded as Latin-1/CP1252 ("ÐŸÑ€Ð¸" instead of "При")
MOJIBAKE_RE = re.compile(r"(?:[ÐÑ][\x80-\xbf\u0080-\u017f\u2010-\u203a]){3,}")

BULLET_RE = re.compile(r"^\s*(?:[•◦▪▫●○■□►▶➢➤✓✔·]|[-–—*](?=\s))\s*")
NUMBERED_RE = re.compile(r"^\s*(?:\d{1,2}|[a-zа-я])[.)]\s+(?=\S)", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:[-–—]?\s*\d{1,4}\s*[-–—]?|(?:page|стор\.?|с\.)\s*\d+(?:\s*(?:of|з|із)\s*\d+)?"
    r"|\d+\s*/\s*\d+)\s*$", re.IGNORECASE)

# Publisher boilerplate that carries no lecture content.
BOILERPLATE_RES = [re.compile(p, re.IGNORECASE) for p in (
    r"^MIT OpenCourseWare\s*$",
    r"^https?://ocw\.mit\.edu/?\S*\s*$",
    r"For information about citing these materials or our Terms of Use",
    r"^This content is excluded from our Creative Commons license",
    r"^Image courtesy of\b",
    r"^©\s*(?:source unknown|\w)",
)]


def normalize(text: str) -> str:
    """Unicode NFC, ligatures, invisible characters, odd spaces, mojibake."""
    if MOJIBAKE_RE.search(text):
        try:
            text = text.encode("cp1252", errors="strict").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    text = unicodedata.normalize("NFC", text).translate(LIGATURES)
    text = INVISIBLE_RE.sub("", text)
    text = CONTROL_RE.sub("", text)
    text = SPACES_RE.sub(" ", text)
    return text


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def join_lines(lines: list[str]) -> str:
    """Join wrapped lines into one paragraph, undoing end-of-line hyphenation ("transfor-" +
    "mation"); a hyphen before a capital letter or a digit is kept ("Navier-" + "Stokes")."""
    out = ""
    for line in (squash(x) for x in lines):
        if not line:
            continue
        hyphen = out.endswith(("-", "‐", "¬")) and len(out) > 1 and out[-2].isalpha()
        if hyphen and line[0].islower():
            out = out[:-1] + line
        elif hyphen:
            out += line
        else:
            out = f"{out} {line}" if out else line
    return out


def is_boilerplate(text: str) -> bool:
    return any(r.search(text) for r in BOILERPLATE_RES)


# OCW PDFs end with a license page: "MIT OpenCourseWare / https://ocw.mit.edu / <course> /
# <term> / For information about citing these materials ..."; the whole page is dropped.
LICENSE_PAGE_RE = re.compile(r"For information about citing these materials", re.IGNORECASE)
LICENSE_PAGE_MAX_CHARS = 500


def margin_key(text: str) -> str:
    """Key for detecting running headers/footers: case- and number-insensitive."""
    return re.sub(r"\d+", "#", squash(text).casefold())


def repeated(keys_per_page: list[set[str]], min_share: float = 0.5, min_pages: int = 3) -> set[str]:
    """Keys that occur on at least `min_share` of the pages (and on `min_pages` of them)."""
    n = len(keys_per_page)
    if n < min_pages:
        return set()
    counts = Counter(k for keys in keys_per_page for k in keys)
    return {k for k, c in counts.items() if c >= max(min_pages, min_share * n)}
