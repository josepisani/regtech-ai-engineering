"""chunking.py — cut regulatory texts along their own structure, not by size.

WHAT IT DOES
    Turns the raw corpus files in data/corpus/raw/ into a list of Chunk
    objects, one per unit a lawyer would cite:

        EU acts (XHTML from the Publications Office):
            numbered paragraph of an article        -> "DORA Article 5(2)"
            article with no numbered paragraphs     -> "DORA Article 1"
            definition or list point                -> "DORA Article 3, point (1)"
                                                       "AI Act Article 5(1), point (a)"
            recital (Official Journal originals)    -> "DORA Recital 12"
            numbered point of an annex              -> "AI Act Annex III, point 4"
            annex without numbered points           -> "AI Act Annex II"
        CSSF circular (PDF, no markup):
            numbered point, with its heading path   -> "CSSF 18/698 point 188"
            annex, whole                            -> "CSSF 18/698 Annex 1"

    `chunk_corpus()` runs the whole MANIFEST and returns every chunk;
    `python -m toolkit.chunking` writes data/corpus/chunks.jsonl and prints
    counts plus a sample so the boundaries can be eyeballed.

WHY IT EXISTS
    Retrieval returns chunks, and the answer cites whatever chunk it got. A
    chunk cut every 500 characters starts in the middle of one obligation and
    ends in the middle of the next; its citation is "somewhere near Article 5".
    A chunk that IS Article 5(2) can be cited as Article 5(2), and a reader
    can open the Act and check. That is the difference between a retrieval
    demo and a tool a compliance officer would use, and it is decided here,
    before any embedding is computed.

    The structure is not guessed from the text. The Publications Office marks
    every article as <div id="art_N"> and every numbered paragraph inside it;
    the two markup dialects it uses (Official Journal originals and
    consolidated texts) are both handled below. The CSSF circular has no
    markup, so its numbered points and headings are recognised by pattern.

HOW TO CALL IT
    from toolkit.chunking import chunk_corpus, Chunk
    chunks = chunk_corpus()                 # uses the MANIFEST below
    chunks[0].ref                           # e.g. "AI Act Article 1(1)"
    chunks[0].text                          # the paragraph, plain text

    Or one file at a time:
    chunk_eu_act(Path("data/corpus/raw/dora.xhtml"), doc="dora", title="DORA")
    chunk_cssf_circular(Path("data/corpus/raw/cssf-18-698.pdf"), doc="cssf-18-698", title="CSSF 18/698")

WHAT IT DOES NOT DO
    It does not embed, rank or interpret anything. It never reads the
    meaning of a paragraph; it only finds where one ends and the next begins.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag

RAW = Path("data/corpus/raw")
OUT = Path("data/corpus/chunks.jsonl")

# One line per source file: (file name, short id used in chunk ids, name used
# in citations). Order is the order chunks come out in.
MANIFEST = [
    ("eu-ai-act.xhtml", "eu-ai-act", "AI Act"),
    ("dora.xhtml", "dora", "DORA"),
    ("dora-rts-ict-risk-management.xhtml", "dora-rts-2024-1774", "DORA RTS 2024/1774"),
    ("dora-rts-incident-classification.xhtml", "dora-rts-2024-1772", "DORA RTS 2024/1772"),
    ("dora-rts-ict-third-party-policy.xhtml", "dora-rts-2024-1773", "DORA RTS 2024/1773"),
    ("aifmd-consolidated.xhtml", "aifmd", "AIFMD"),  # consolidated 2026-04-16, includes AIFMD II
    ("sfdr.xhtml", "sfdr", "SFDR"),
    ("cssf-18-698.pdf", "cssf-18-698", "CSSF 18/698"),
]

# A list is split into point chunks only when it is long enough to be worth
# it: over SPLIT_OVER_CHARS in total, with at least 3 points in a paragraph
# or MIN_POINTS in an article (definitions articles are the typical case).
SPLIT_OVER_CHARS = 2500
MIN_POINTS = 5


@dataclass
class Chunk:
    """One citable unit of text.

    id       stable, unique: "dora:art_5:2"
    doc      which source: "dora"
    ref      what a person would write in a footnote: "DORA Article 5(2)"
    heading  the article or section title the unit sits under
    text     the words, whitespace collapsed
    """

    id: str
    doc: str
    ref: str
    heading: str
    text: str


# ---------------------------------------------------------------------------
# EU acts — XHTML from publications.europa.eu
# ---------------------------------------------------------------------------
# The Publications Office uses two dialects. Where they differ, both class
# names are listed; the code tries each in turn.
ARTICLE_LABEL = ("oj-ti-art", "title-article-norm")        # "Article 5"
ARTICLE_TITLE = ("oj-sti-art", "stitle-article-norm")      # "Governance and organisation"
ANNEX_LABEL = ("title-annex-1",)                            # "ANNEX III"
ANNEX_TITLE = ("title-annex-2",)

# Consolidated texts flag amended passages with ►M1 ... ◄ and ▼B markers.
# They are editorial, not law, and they sit inside <a> tags.
MARKER = re.compile(r"[►▼◄]\s*[A-Z]?\d*")


def _clean(text: str) -> str:
    """Collapse whitespace and drop consolidation markers."""
    return re.sub(r"\s+", " ", MARKER.sub("", text)).strip()


def _first_text(node: Tag, classes: tuple[str, ...]) -> str:
    for cls in classes:
        hit = node.find("p", class_=cls)
        if hit:
            return _clean(hit.get_text(" "))
    return ""


def _strip_editorial(soup: BeautifulSoup) -> None:
    """Remove amendment references so they never land in a chunk."""
    for p in soup.find_all("p", class_="modref"):
        p.extract()
    for a in soup.find_all("a"):
        if MARKER.fullmatch(a.get_text(strip=True) or "-"):
            a.extract()


def _points(node: Tag) -> tuple[str, list[tuple[str, str]]]:
    """(lead-in text, [(marker, text), ...]) for a list of points under `node`.

    OJ dialect:            one <table> per point: <td>(1)</td><td>text</td>
    consolidated dialect:  <div class="grid-container"> with column-1 (marker)
                           and column-2 (text); inside a numbered paragraph it
                           sits one level down, in a div.inline-element.
    The lead-in is the prose before the first point ("For the purposes of
    this Regulation, the following definitions apply:").
    """
    inner = node.find("div", class_="inline-element", recursive=False)
    scope = inner if inner is not None else node
    lead: list[str] = []
    points: list[tuple[str, str]] = []
    for child in scope.find_all(["p", "table", "div"], recursive=False):
        if child.name == "p" and not points:
            lead.append(child.get_text(" "))
        elif child.name == "table":
            cells = child.find_all("td")
            if len(cells) >= 2:
                points.append((_clean(cells[0].get_text()), _clean(cells[1].get_text(" "))))
        elif child.name == "div" and "grid-container" in (child.get("class") or []):
            marker = child.find("div", class_="grid-list-column-1")
            body = child.find("div", class_="grid-list-column-2")
            if marker is not None and body is not None:
                points.append((_clean(marker.get_text()), _clean(body.get_text(" "))))
    return _clean(" ".join(lead)), points


def _paragraphs(article: Tag) -> list[tuple[str, Tag]]:
    """[(number, node)] for an article's numbered paragraphs, [] if none.

    OJ dialect:            <div id="005.002"> ... </div>   (article 5, para 2)
    consolidated dialect:  <div class="norm"><span class="no-parag">2.  </span> ...
    """
    out: list[tuple[str, Tag]] = []
    for div in article.find_all("div", id=re.compile(r"^\d{3}\.\d{3}$"), recursive=False):
        out.append((str(int(div["id"].split(".")[1])), div))  # "005.002" -> "2"
    if out:
        return out
    for div in article.find_all("div", class_="norm", recursive=False):
        marker = div.find("span", class_="no-parag")
        if marker is None:
            continue
        number = _clean(marker.get_text()).rstrip(".")
        marker.extract()  # so the number is not repeated in the text
        out.append((number, div))
    return out


def _unit_chunks(node: Tag, *, doc: str, cid: str, ref: str, heading: str, at_article: bool) -> list[Chunk]:
    """One chunk for `node`, or one per point when it is a long list."""
    lead, points = _points(node)
    enough_points = len(points) >= (MIN_POINTS if at_article else 3)
    markers = [m for m, _ in points]
    unique_markers = len(set(markers)) == len(markers)   # two "(a)" lists in one unit: keep it whole
    split = enough_points and unique_markers and len(_clean(node.get_text(" "))) > SPLIT_OVER_CHARS
    if not split:
        text = re.sub(r"^\d+\.\s+", "", _clean(node.get_text(" ")))  # OJ repeats "2." in the text
        return [Chunk(cid, doc, ref, heading, text)]
    prefix = (lead + " ") if lead and len(lead) <= 300 else ""
    return [
        Chunk(f"{cid}:{m.strip('().')}", doc, f"{ref}, point {m}", heading, f"{prefix}{m} {t}")
        for m, t in points
    ]


def chunk_eu_act(path: Path, *, doc: str, title: str) -> list[Chunk]:
    """Chunk one EU act. See module docstring for the units."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    _strip_editorial(soup)
    chunks: list[Chunk] = []

    # Recitals: only present in Official Journal originals.
    for rct in soup.find_all("div", id=re.compile(r"^rct_\d+$")):
        n = rct["id"].split("_")[1]
        text = re.sub(r"^\(\d+\)\s*", "", _clean(rct.get_text(" ")))  # drop the leading "(12)"
        chunks.append(Chunk(f"{doc}:rct_{n}", doc, f"{title} Recital {n}", "Recitals", text))

    # Articles.
    for art in soup.find_all("div", id=re.compile(r"^art_\d+[a-z]*$")):
        label = _first_text(art, ARTICLE_LABEL)             # "Article 5"
        heading = _first_text(art, ARTICLE_TITLE)           # its title
        n = art["id"].split("_")[1]
        paras = _paragraphs(art)
        if not paras:
            # Drop the label and title lines so only the body remains.
            for p in art.find_all("p", class_=ARTICLE_LABEL + ARTICLE_TITLE):
                p.extract()
            chunks += _unit_chunks(art, doc=doc, cid=f"{doc}:art_{n}", ref=f"{title} {label}",
                                   heading=heading, at_article=True)
            continue
        for num, node in paras:
            chunks += _unit_chunks(node, doc=doc, cid=f"{doc}:art_{n}:{num}", ref=f"{title} {label}({num})",
                                   heading=heading, at_article=False)

    # Annexes: split on top-level numbered points only; a dash list or a
    # lettered list stays whole, as one annex chunk.
    for anx in soup.find_all("div", id=re.compile(r"^anx_[IVXLC]+$")):
        roman = anx["id"].split("_")[1]
        heading = _first_text(anx, ANNEX_TITLE)
        for p in anx.find_all("p", class_=ANNEX_LABEL + ANNEX_TITLE):
            p.extract()
        lead, points = _points(anx)
        numbered = [(m, t) for m, t in points if re.fullmatch(r"\d+\.?", m)]
        # Split only on a single run 1..k. An annex with sections A, B, C that
        # each restart at 1 (AI Act Annex VIII) stays whole.
        consecutive = [int(m.rstrip(".")) for m, _ in numbered] == list(range(1, len(numbered) + 1))
        if points and len(numbered) == len(points) and consecutive:
            for m, t in numbered:
                num = m.rstrip(".")
                chunks.append(Chunk(f"{doc}:anx_{roman}:{num}", doc, f"{title} Annex {roman}, point {num}", heading, t))
        else:
            chunks.append(Chunk(f"{doc}:anx_{roman}", doc, f"{title} Annex {roman}", heading, _clean(anx.get_text(" "))))
    return chunks


# ---------------------------------------------------------------------------
# CSSF circular — PDF, structure recognised by pattern
# ---------------------------------------------------------------------------
PAGE_HEADER = re.compile(r"^\s*Circular CSSF 18/698\s+Page \d+/\d+\s*$")
LEVELS = ("Part", "Chapter", "Sub-chapter", "Section", "Sub-section")
HEADING = re.compile(r"^(Part [IVX]+\.|Chapter \d+\.|Sub-chapter \d+(\.\d+)*\.|Section \d+(\.\d+)*\.|Sub-section \d+(\.\d+)*\.)\s*(.*)$")
POINT = re.compile(r"^(\d{1,3})\.\s+(\S.*)$")            # "188. The permanent risk ..."
ANNEXES_START = re.compile(r"^\s*ANNEXES\s*$")
ANNEX = re.compile(r"^ANNEX (\d+):\s*(.*)$")               # "ANNEX 1: The risk management ..."
TOC_ENTRY = re.compile(r"\.{4,}\s*\d+\s*$")                # "...Chapter 2. Shareholding ........ 12"


def chunk_cssf_circular(path: Path, *, doc: str, title: str) -> list[Chunk]:
    """One chunk per numbered point, then one per annex section.

    Points are numbered 1..N consecutively through the whole circular, so a
    line is a new point only when its number is the next one expected; that
    is what keeps "2013 Law" or a footnote from starting a chunk. The table
    of contents at the front repeats the headings, harmlessly: the heading
    path is overwritten again when the body reaches them.
    """
    from pypdf import PdfReader  # imported here so the EU path needs no pypdf

    lines: list[str] = []
    for page in PdfReader(str(path)).pages:
        for line in page.extract_text().splitlines():
            if not PAGE_HEADER.match(line):
                lines.append(line.strip())

    # The table of contents repeats every heading and numbers its own entries
    # "1.", "2.", "3.", which would be taken for points 1-3. Every TOC entry
    # ends in dotted leaders and a page number; the body starts after the last.
    toc_end = max((i for i, l in enumerate(lines) if TOC_ENTRY.search(l)), default=-1)
    lines = lines[toc_end + 1:]

    chunks: list[Chunk] = []
    path_by_level: dict[str, str] = {}
    current: list[str] | None = None
    current_id, current_ref = "", ""
    expected = 1
    in_annexes = False
    open_heading: str | None = None

    def flush() -> None:
        if current is not None and current_id:
            heading = " > ".join(path_by_level[k] for k in LEVELS if k in path_by_level)
            chunks.append(Chunk(f"{doc}:{current_id}", doc, current_ref, heading, _clean(" ".join(current))))

    for line in lines:
        if not in_annexes and ANNEXES_START.match(line):
            flush(); current = None; in_annexes = True
            path_by_level = {}
            continue

        if in_annexes:
            # One chunk per annex. The three annexes are a template and two
            # tables whose rows restart at "1." in every column, so there is
            # no numbering to split on without inventing one.
            a = ANNEX.match(line)
            if a:
                flush()
                path_by_level = {"Part": f"Annex {a.group(1)}"}
                current_id, current_ref = f"anx_{a.group(1)}", f"{title} Annex {a.group(1)}"
                current = [a.group(2)]
            elif current is not None and line:
                current.append(line)
            continue

        h = HEADING.match(line)
        if h:
            level = h.group(1).split(" ")[0]
            flush(); current = None
            path_by_level[level] = _clean(line)
            open_heading = level                              # may continue on the next line
            for lower in LEVELS[LEVELS.index(level) + 1:]:   # a new heading resets the levels below it
                path_by_level.pop(lower, None)
            continue
        p = POINT.match(line)
        if p and int(p.group(1)) == expected:
            flush()
            current, current_id, current_ref = [p.group(2)], f"pt_{p.group(1)}", f"{title} point {p.group(1)}"
            open_heading = None
            expected += 1
            continue
        if current is not None and line:
            current.append(line)
        elif open_heading and line:                           # a heading wrapped onto a second line
            path_by_level[open_heading] += " " + _clean(line)
    flush()
    return chunks


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------
def chunk_corpus(raw: Path = RAW) -> list[Chunk]:
    """Every chunk of every file in MANIFEST, in manifest order."""
    out: list[Chunk] = []
    for name, doc, title in MANIFEST:
        path = raw / name
        if not path.exists():
            print(f"skip {name}: not downloaded", file=sys.stderr)
            continue
        if path.suffix == ".pdf":
            out += chunk_cssf_circular(path, doc=doc, title=title)
        else:
            out += chunk_eu_act(path, doc=doc, title=title)
    return out


def write_jsonl(chunks: list[Chunk], path: Path = OUT) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # the texts use characters cp1252 cannot print
    chunks = chunk_corpus()
    write_jsonl(chunks)
    by_doc: dict[str, int] = {}
    for c in chunks:
        by_doc[c.doc] = by_doc.get(c.doc, 0) + 1
    print(f"{len(chunks)} chunks -> {OUT}")
    for doc, n in by_doc.items():
        print(f"  {doc:22} {n:5}")
    # A sample to eyeball: a few refs per document, first 160 characters each.
    wanted = {
        "AI Act Article 6(1)", "AI Act Article 3, point (1)", "AI Act Article 5(1), point (a)",
        "AI Act Annex III, point 4", "AI Act Annex II",
        "DORA Recital 1", "DORA Article 3, point (1)", "DORA Article 5(2)",
        "SFDR Article 6(1)", "AIFMD Article 4(1), point (a)", "AIFMD Annex I",
        "CSSF 18/698 point 4", "CSSF 18/698 point 188", "CSSF 18/698 Annex 1",
    }
    for c in chunks:
        if c.ref in wanted:
            print(f"\n[{c.id}]  {c.ref}\n  heading: {c.heading}\n  {c.text[:160]}{'…' if len(c.text) > 160 else ''}")
