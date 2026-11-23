"""Retrieval-augmented generation over the library's own FTS index (page-aware citations)."""
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..core.textnorm import fts_query, tokens
from ..services.book_service import BookService

STOP = set("و در به از که این را با است برای آن یک هم تا یا the a an of to in and or is are for on with".split())

SYSTEM = ("You are a careful assistant that answers ONLY from the provided PDF excerpts. Each excerpt is labeled "
          "[book title, p.N]. Cite the page numbers you used in the form (p.N). If the excerpts do not contain the "
          "answer, say clearly that the information is not in the PDF. Answer in the language of the question "
          "(Persian questions get Persian answers).")


@dataclass
class Excerpt:
    book_id: int
    title: str
    page: int
    text: str


@dataclass
class Answer:
    text: str
    sources: list = field(default_factory=list)  # [(title, page, book_id)]
    found: bool = True


def retrieve(svcs: dict[int, BookService], book_ids: list[tuple[int, int]], question: str, k: int = 8) -> list[Excerpt]:
    """book_ids: list of (library_id, book_id). Uses BM25 over normalised chunks."""
    toks = [t for t in tokens(question) if t not in STOP and len(t) > 1]
    if not toks:
        return []
    q = " OR ".join('"%s"' % t for t in toks)
    out: list[Excerpt] = []
    for lib_id, bid in book_ids:
        svc = svcs[lib_id]
        title = svc.book(bid)["title"]
        rows = svc.db.q(
            "SELECT c.page_start, c.text FROM chunks_fts f JOIN document_chunks c ON c.id=f.chunk_id "
            "WHERE chunks_fts MATCH ? AND f.book_id=? ORDER BY rank LIMIT ?", (q, bid, k))
        out += [Excerpt(bid, title, r["page_start"], r["text"]) for r in rows]
    return out[: max(k, 1) * max(1, len(book_ids))] if len(book_ids) > 1 else out[:k]


def _fmt(ex: list[Excerpt], limit_chars=9000) -> str:
    parts, total = [], 0
    for e in ex:
        s = f"[{e.title}, p.{e.page}]\n{e.text}"
        if total + len(s) > limit_chars:
            break
        parts.append(s)
        total += len(s)
    return "\n\n".join(parts)


def sample_book(svc: BookService, bid: int, page_range: Optional[tuple[int, int]] = None, n_chunks: int = 14,
                ) -> list[Excerpt]:
    """Evenly spread excerpts across a book (or page range) for summary-style tasks."""
    title = svc.book(bid)["title"]
    lo, hi = page_range or (1, 10 ** 9)
    rows = svc.db.q("SELECT page_start, text FROM document_chunks WHERE book_id=? AND page_start BETWEEN ? AND ? "
                    "ORDER BY id", (bid, lo, hi))
    if not rows:
        return []
    step = max(1, len(rows) // n_chunks)
    return [Excerpt(bid, title, r["page_start"], r["text"]) for r in rows[::step][:n_chunks]]


def chapter_range(doc_toc: list, title_query: str, total_pages: int) -> Optional[tuple[int, int]]:
    """doc_toc: PyMuPDF [[lvl, title, page], ...]."""
    tq = " ".join(tokens(title_query))
    for i, (lvl, t, p) in enumerate(doc_toc):
        if tq and tq in " ".join(tokens(t)):
            end = total_pages
            for lvl2, _t2, p2 in doc_toc[i + 1:]:
                if lvl2 <= lvl:
                    end = max(p, p2 - 1)
                    break
            return p, end
    return None


TASKS = {
    "summary": "Write a structured summary (headings + bullet points) of the following excerpts.",
    "keypoints": "Extract the most important key points as a numbered list.",
    "definitions": "Extract important terms and their definitions as 'term: definition (p.N)'.",
    "flashcards": "Create 10 flashcards. Output JSON only: [{\"q\": \"...\", \"a\": \"...\", \"page\": N}].",
    "quiz": "Create 8 four-option multiple choice questions. Output JSON only: "
            "[{\"q\":\"...\",\"options\":[\"..\",\"..\",\"..\",\"..\"],\"answer\":0,\"page\":N}].",
    "topics": "List the main topics covered, each with a one-line description and page numbers.",
    "handout": "Produce a concise study handout (jozve) with sections, key definitions and bullet points.",
    "compare": "Compare the books/excerpts: similarities, differences, and unique points of each, citing pages.",
}


def parse_json(text: str):
    m = re.search(r"\[.*\]", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def _sources(ex: list[Excerpt]):
    seen, out = set(), []
    for e in ex:
        key = (e.book_id, e.page)
        if key not in seen:
            seen.add(key)
            out.append((e.title, e.page, e.book_id))
    return out


def ask(provider, svcs, book_ids, question: str, k: int = 8) -> Answer:
    ex = retrieve(svcs, book_ids, question, k)
    if not ex:
        return Answer("", [], found=False)
    reply = provider.chat(SYSTEM, f"Excerpts:\n{_fmt(ex)}\n\nQuestion: {question}")
    return Answer(reply, _sources(ex))


def run_task(provider, svcs, book_ids, task: str, page_range=None, topic: str = "",
             progress: Callable[[str], None] = None) -> Answer:
    instr = TASKS[task]
    ex: list[Excerpt] = []
    if topic:
        ex = retrieve(svcs, book_ids, topic, 10)
    else:
        per = 14 if len(book_ids) == 1 else max(5, 14 // len(book_ids))
        for lib_id, bid in book_ids:
            ex += sample_book(svcs[lib_id], bid, page_range, per)
    if not ex:
        return Answer("", [], found=False)
    if task == "summary" and len(ex) > 8 and not topic:  # two-stage summary for long inputs
        half = len(ex) // 2
        if progress:
            progress("1/3")
        a = provider.chat(SYSTEM, f"{instr}\n\nExcerpts:\n{_fmt(ex[:half])}")
        if progress:
            progress("2/3")
        b = provider.chat(SYSTEM, f"{instr}\n\nExcerpts:\n{_fmt(ex[half:])}")
        if progress:
            progress("3/3")
        reply = provider.chat(SYSTEM, "Merge these two partial summaries into one coherent summary, keeping the "
                                      f"(p.N) citations:\n\nPART 1:\n{a}\n\nPART 2:\n{b}")
        return Answer(reply, _sources(ex))
    reply = provider.chat(SYSTEM, f"{instr}\n\nExcerpts:\n{_fmt(ex)}")
    return Answer(reply, _sources(ex))
