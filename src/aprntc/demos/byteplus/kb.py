"""Knowledge base — chunk BytePlus docs into retrievable passages + lexical search.

Local, in-memory, dependency-light (stdlib only). Docs are markdown files; we split
on headings into passages, strip navigation/link cruft, and retrieve by TF-style
keyword overlap (good enough for a demo; swappable for VikingDB in production).

Each chunk keeps its source doc + section so answers can cite where the fact came
from — citation discipline is part of what the apprentice improves.
"""

from __future__ import annotations

import math
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
    out = set()
    for w in re.findall(r"[a-z0-9_]+", text.lower()):
        if w in _STOP:
            continue
        # keep words >2 chars, OR short alphanumerics that mix a digit + letter
        # (e.g. "3d", "v2", "m3") — these are meaningful product/version terms
        if len(w) > 2 or (any(ch.isdigit() for ch in w) and any(ch.isalpha() for ch in w)):
            out.add(w)
    return out


@dataclass
class Chunk:
    chunk_id: str
    doc: str           # source doc name (human-readable product area)
    section: str       # heading this passage sits under
    text: str
    _tokens: set[str]
    _title_tokens: set[str] = None  # type: ignore[assignment]  # doc-name + section tokens

    def __post_init__(self) -> None:
        if self._title_tokens is None:
            self._title_tokens = _tokens(f"{self.doc} {self.section}")

    def cite(self) -> str:
        return f"{self.doc} › {self.section}"


def _doc_label(path: Path) -> str:
    """Human-readable product area from a filename.

    Splits separators AND camelCase / letter-digit boundaries so e.g.
    ``3DModelAPI`` → "3 D Model API" and ``SeedanceCreateAPI`` → "Seedance Create
    API" — otherwise the whole filename collapses into one unsearchable token.
    """
    name = path.stem.replace("_", " ").replace("-", " ")
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)  # camelCase / 3DModel -> 3D Model
    name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", name)  # DModel -> D Model (acronym+word)
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
    """In-memory chunk store with TF-IDF keyword retrieval.

    Scoring sums the **IDF** of matched query terms (rare/distinctive terms weigh
    far more than common ones like "api"/"model"), with length normalization so a
    big generic doc can't win on sheer size. This makes precise matches (e.g. the
    small TokenizerAPI doc for "tokenizer") beat large catch-all docs (Pricing/Chat).
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self._idf = self._compute_idf(chunks)
        # distinctiveness threshold for title-boosting (~35th percentile of IDF).
        # Title matches on terms rarer than this (product names like "seedance",
        # "seedream", "embedding", "tokenizer") get boosted; common ones ("api",
        # "model", "search", "request") do not.
        vals = sorted(self._idf.values())
        self._idf_hi = vals[int(len(vals) * 0.35)] if vals else 1.0

    @staticmethod
    def _compute_idf(chunks: list[Chunk]) -> dict[str, float]:
        n = len(chunks) or 1
        df: dict[str, int] = {}
        for c in chunks:
            for t in c._tokens:
                df[t] = df.get(t, 0) + 1
        # smoothed idf; common terms → ~0, rare terms → high
        return {t: math.log((n + 1) / (d + 1)) + 1.0 for t, d in df.items()}

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
            matched = q & c._tokens
            title_match = q & c._title_tokens
            if not matched and not title_match:
                continue
            # sum IDF of matched body terms; normalize by sqrt(chunk size) so big
            # chunks don't dominate purely by having more tokens
            idf_sum = sum(self._idf.get(t, 1.0) for t in matched)
            body_score = idf_sum / (1 + len(c._tokens) ** 0.5)
            # strong boost when a DISTINCTIVE query term hits the doc NAME / section
            # heading — the surest topic signal (e.g. "tokenizer" → TokenizerAPI doc).
            # Gate on IDF so generic title words ("api", "models", "search") don't hijack.
            title_score = 3.0 * sum(
                self._idf.get(t, 1.0) for t in title_match if self._idf.get(t, 1.0) >= self._idf_hi
            )
            scored.append((body_score + title_score, len(matched | title_match), c))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
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
