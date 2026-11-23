"""Persian/Arabic text normalisation used for indexing and querying."""
import re

_MAP = {
    "ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "ٱ": "ا",
    "ؤ": "و", "\u200c": " ", "\xa0": " ", "\u202f": " ", "\u2009": " ", "\u200f": "", "\u200e": "", "ـ": "",
}
_TABLE = str.maketrans(_MAP)
_DIG = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIG.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})
_TASHKEEL = re.compile("[\u064b-\u065f\u0670\u06d6-\u06ed]")
_WORD = re.compile(r"\w+", re.UNICODE)


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.translate(_TABLE).translate(_DIG)
    text = _TASHKEEL.sub("", text)
    return text.casefold()


def tokens(text: str) -> list[str]:
    return _WORD.findall(normalize(text))


def fts_query(text: str, prefix: bool = True) -> str:
    """Build a safe FTS5 query: AND of quoted tokens, last token is a prefix."""
    toks = tokens(text)
    if not toks:
        return ""
    parts = ['"%s"' % t.replace('"', "") for t in toks]
    if prefix:
        parts[-1] += "*"
    return " ".join(parts)
