"""Build docs/PDFLibraryPro-Guide-FA.pdf (RTL, Vazirmatn) from README.md + docs/*.md using Qt only."""
import html, os, re, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QMarginsF, QSizeF, Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QPageLayout, QPageSize, QPdfWriter, QTextDocument, QTextOption
from PySide6.QtWidgets import QApplication

app = QApplication([])
fam = "Vazirmatn"
for f in ("Vazirmatn-Regular.ttf", "Vazirmatn-Bold.ttf"):
    fid = QFontDatabase.addApplicationFont(str(ROOT / "app/resources/fonts" / f))
    fam = QFontDatabase.applicationFontFamilies(fid)[0]


IMGW = 520


def md_to_html(md: str) -> str:
    out, in_ul, in_code, table = [], False, False, []
    def close_ul():
        nonlocal in_ul
        if in_ul: out.append("</ul>"); in_ul = False
    def flush_table():
        nonlocal table
        if table:
            global IMGW
            IMGW = 300
            rows = [r for r in table if not re.match(r"^\|[\s\-|]+\|$", r)]
            out.append("<table border='1' cellspacing='0' cellpadding='5' width='100%'>")
            for i, r in enumerate(rows):
                cells = [c.strip() for c in r.strip("|").split("|")]
                tag = "th" if i == 0 else "td"
                out.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
            out.append("</table>"); table = []; IMGW = 520
    def inline(t):
        t = html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        t = re.sub(r"!\[.*?\]\((.+?)\)", lambda m: f"<img src='{ROOT / m.group(1)}' width='{IMGW}'>", t)
        t = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", t)
        return t
    for line in md.splitlines():
        if line.startswith("```"):
            in_code = not in_code; out.append("<pre dir='ltr'>" if in_code else "</pre>"); continue
        if in_code: out.append(html.escape(line)); continue
        if line.startswith("|"):
            table.append(line); continue
        flush_table()
        if line.startswith("!["):
            close_ul(); out.append(f"<p align='center'>{inline(line)}</p>"); continue
        m = re.match(r"^(#{1,3}) (.*)", line)
        if m: close_ul(); n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); continue
        if line.startswith("- "):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{inline(line[2:])}</li>"); continue
        close_ul()
        if line.startswith(">"): out.append(f"<p><i>{inline(line[1:].strip())}</i></p>"); continue
        if line.strip(): out.append(f"<p>{inline(line)}</p>")
    flush_table(); close_ul()
    return "\n".join(out)


md = "\n\n".join((ROOT / p).read_text(encoding="utf-8") for p in ("README.md", "docs/OCR.md", "docs/OLLAMA.md"))
md = re.sub(r"\| همه کتاب‌ها \| قفسه \|\n\|---\|---\|\n", "", md)
doc = QTextDocument()
doc.setDefaultFont(QFont(fam, 10))
opt = QTextOption(); opt.setTextDirection(Qt.RightToLeft); doc.setDefaultTextOption(opt)
doc.setHtml(f"<html><body dir='rtl' style='font-family:{fam}'>{md_to_html(md)}</body></html>")
w = QPdfWriter(str(ROOT / "docs/PDFLibraryPro-Guide-FA.pdf"))
w.setResolution(96)
w.setPageSize(QPageSize(QPageSize.A4)); w.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
w.setTitle("راهنمای کتابخانه PDF حرفه‌ای")
doc.setPageSize(QSizeF(w.width(), w.height()))
doc.print_(w)
print("guide pdf ok")
