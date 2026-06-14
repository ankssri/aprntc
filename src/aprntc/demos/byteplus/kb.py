"""Knowledge base — chunk BytePlus docs into retrievable passages + lexical search.

Local, in-memory, dependency-light (stdlib only). Docs are markdown files; we split
on headings into passages, strip navigation/link cruft, and retrieve by TF-style
keyword overlap (good enough for a demo; swappable for VikingDB in production).

Each chunk keeps its source doc + section so answers can cite where the fact came
from — citation discipline is part of what the apprentice improves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Default doc roots (the real BytePlus docs the user provided on disk).
DEFAULT_DOC_DIRS = (
    "/Users/ankur/mdfiles",
    "/Users/ankur/mdfiles/byteplus-vikingdb-docs",
)

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")          # [text](url) -> text
_SPAN = re.compile(r"<[^>]+>")                         # html spans/tags
_WS = re.compile(r"[ \t]+")
_HEADING = re.compile(r"^#{1,4}\s+(.*)$")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are", "on",
    "with", "you", "can", "this", "that", "it", "as", "be", "by", "your", "how",
    "what", "which", "does", "do", "i", "my", "use", "using", "from",
}


def _clean(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = _SPAN.sub("", text)
    text = _WS.sub(" ", text)
    return text.strip()


def _tokens(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9_]+", text.lower())
        if len(w) > 2 and w not in _STOP
    }


@dataclass
class Chunk:
    chunk_id: str
    doc: str           # source doc name (human-readable product area)
    section: str       # heading this passage sits under
    text: str
    _tokens: set[str]

    def cite(self) -> str:
        return f"{self.doc} › {self.section}"


def _doc_label(path: Path) -> str:
    """Human-readable product area from a filename."""
    name = path.stem.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", name).strip()


def _chunk_markdown(path: Path, *, min_chars: int = 120, max_chars: int = 900) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    doc = _doc_label(path)
    chunks: list[Chunk] = []
    section = "Overview"
    buf: list[str] = []
    idx = 0

    def flush() -> None:
        nonlocal buf, idx
        body = _clean(" ".join(buf))
        buf = []
        if len(body) < min_chars:
            return
        # split overly long passages on sentence boundaries
        for piece in _split(body, max_chars):
            toks = _tokens(section + " " + piece)
            if len(toks) < 4:
                continue
            chunks.append(Chunk(f"{path.stem}#{idx}", doc, section, piece, toks))
            idx += 1

    for line in raw.splitlines():
        m = _HEADING.match(line.strip())
        if m:
            flush()
            section = _clean(m.group(1)) or section
        elif line.strip():
            buf.append(line)
    flush()
    return chunks


def _split(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if len(cur) + len(sent) > max_chars and cur:
            out.append(cur.strip())
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur.strip())
    return out


class KnowledgeBase:
    """In-memory chunk store with keyword retrieval."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    def __len__(self) -> int:
        return len(self.chunks)

    def docs(self) -> list[str]:
        return sorted({c.doc for c in self.chunks})

    def search(self, query: str, *, k: int = 4) -> list[Chunk]:
        q = _tokens(query)
        if not q:
            return []
        scored = []
        for c in self.chunks:
            overlap = len(q & c._tokens)
            if overlap:
                # light length-normalization so short precise chunks aren't buried
                scored.append((overlap / (1 + len(c._tokens) ** 0.5), overlap, c))
        scored.sort(key=lambda t: (t[1], t[0]), reverse=True)
        return [c for _, _, c in scored[:k]]


def build_kb(doc_dirs: tuple[str, ...] = DEFAULT_DOC_DIRS,
             *, patterns: tuple[str, ...] = ("*.md",)) -> KnowledgeBase:
    """Build a KnowledgeBase from markdown docs under ``doc_dirs``."""
    chunks: list[Chunk] = []
    for d in doc_dirs:
        root = Path(d)
        if not root.exists():
            continue
        for pat in patterns:
            for path in sorted(root.glob(pat)):
                chunks.extend(_chunk_markdown(path))
    return KnowledgeBase(chunks)
