"""``slug()`` and ``headline()``, as Laravel's ``Str`` computes them.

A catalog entity is stored under ``slug(input)`` and named ``headline(input)``
when no name is given. A twin that slugs differently stores a second entity for
the same name, so these are pinned by the ``fun-lab/strings`` table rather than
reimplemented "sensibly". Three results that surprise people and are correct:

- ``slug("team@home") == "team-at-home"``: Laravel spells ``@`` as ``at``.
- ``slug("日本語") == ""``: with the default ``en`` language, non-Latin scripts
  are dropped, not transliterated.
- ``headline("Combat XP") == "Combat Xp"``: every word is title-cased, which
  lowercases the rest of an acronym.

Laravel folds to ASCII with ``voku/portable-ascii``, whose tables this package
does not carry (zero dependencies). Latin letters, their diacritics and the
common ligatures fold the same way; for other scripts give an explicit ASCII
slug if it must be portable.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["headline", "slug"]

# Letters NFKD does not decompose to ASCII, folded as portable-ascii does for `en`.
_FOLD = {
    "ß": "ss",
    "ẞ": "SS",
    "æ": "ae",
    "Æ": "AE",
    "ø": "o",
    "Ø": "O",
    "œ": "oe",
    "Œ": "OE",
    "þ": "th",
    "Þ": "TH",
    "ð": "d",
    "Ð": "D",
    "đ": "d",
    "Đ": "D",
    "ł": "l",
    "Ł": "L",
    "ı": "i",  # noqa: RUF001 -- the dotless i is the point of this entry
    "ħ": "h",
    "Ħ": "H",
    "ŧ": "t",
    "Ŧ": "T",
    "ŋ": "n",
    "Ŋ": "N",
    "€": "EUR",
}

# Characters NFKD WOULD turn into ASCII but portable-ascii drops (measured
# against PHP: "½" -> "", "Ⅳ" -> "", "①" -> "", "ǆ" -> "").
_DROP = re.compile("[\u01c4-\u01c6\u01f1-\u01f3\u00bc-\u00be\u2150-\u218f\u2460-\u24ff]")


def _ascii(value: str) -> str:
    value = _DROP.sub("", value)
    value = "".join(_FOLD.get(ch, ch) for ch in value)
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        ch for ch in decomposed if ord(ch) < 128 and not unicodedata.category(ch).startswith("M")
    )


def slug(value: str, separator: str = "-") -> str:
    """``Str::slug($value, $separator)`` with Laravel's default ``['@' => 'at']``."""
    title = _ascii(value)
    flip = "_" if separator == "-" else "-"
    title = re.sub("[" + re.escape(flip) + "]+", separator, title)
    title = title.replace("@", separator + "at" + separator)
    sep = re.escape(separator)
    title = re.sub("[^" + sep + r"a-z0-9\s]+", "", title.lower(), flags=re.ASCII)
    title = re.sub("[" + sep + r"\s]+", separator, title, flags=re.ASCII)
    return title.strip(separator)


# Word_Break MidLetter / MidNumLet / Single_Quote: case-ignorable punctuation.
_IGNORABLE_PUNCT = set(
    "'.:\u00b7\u0387\u055f\u05f4\u2018\u2019\u2024\u2027\ufe13\ufe52\ufe55\uff07\uff0e\uff1a"
)


def _case_ignorable(ch: str) -> bool:
    return ch in _IGNORABLE_PUNCT or unicodedata.category(ch) in ("Mn", "Me", "Cf", "Lm", "Sk")


def _cased(ch: str) -> bool:
    return unicodedata.category(ch) in ("Lu", "Ll", "Lt") or ch.lower() != ch or ch.upper() != ch


def _title(value: str) -> str:
    """``mb_convert_case($value, MB_CASE_TITLE)``: a cased letter after an
    uncased, non-ignorable character (a space, a digit, ``-`` or ``_``) is
    title-cased; every other cased letter is lowercased."""
    out = []
    title_mode = False
    for ch in value:
        out.append(ch.lower() if title_mode else ch.title())
        if not _case_ignorable(ch):
            title_mode = _cased(ch)
    return "".join(out)


def _ucsplit(value: str) -> list[str]:
    """``preg_split('/(?=\\p{Lu})/u', ...)`` with empty pieces dropped."""
    pieces: list[str] = []
    current = ""
    for ch in value:
        if unicodedata.category(ch) == "Lu" and current:
            pieces.append(current)
            current = ""
        current += ch
    if current:
        pieces.append(current)
    return pieces


def headline(value: str) -> str:
    """``Str::headline($value)``."""
    parts = [p for p in re.split(r"\s+", value) if p]
    if len(parts) > 1:
        parts = [_title(p) for p in parts]
    else:
        parts = [_title(p) for p in _ucsplit("_".join(parts))]
    collapsed = re.sub("[-_ ]", "_", "_".join(parts))
    # PHP's array_filter drops "" AND "0".
    return " ".join(w for w in collapsed.split("_") if w not in ("", "0"))
