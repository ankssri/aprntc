"""Inspect the BytePlus knowledge base — what docs/chunks the agent can ground on.

Run after adding new .md files to /Users/ankur/mdfiles/ to confirm they're picked
up and retrievable.

  .venv/bin/python scripts/kb_status.py                  # summary + doc list
  .venv/bin/python scripts/kb_status.py "your question"  # + top retrieved chunks
"""

from __future__ import annotations

import sys

from aprntc.demos.byteplus import build_kb


def main() -> int:
    kb = build_kb()
    print(f"KB: {len(kb)} chunks across {len(kb.docs())} doc areas\n")
    for d in kb.docs():
        n = sum(1 for c in kb.chunks if c.doc == d)
        print(f"  {n:4d}  {d}")

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"\nTop retrieval for: {query!r}")
        hits = kb.search(query, k=4)
        if not hits:
            print("  (no matches — likely a coverage gap; add docs for this topic)")
        for h in hits:
            print(f"  [{h.cite()}]\n    {h.text[:140]}")
    else:
        # quick coverage probes for the topics the user is expanding
        print("\nCoverage probes (add docs if any say 'GAP'):")
        for q in ["list of available models", "model pricing per token", "tokenizer api",
                  "embedding api dimensions", "seedance video generation",
                  "seedream image generation", "3d model generation"]:
            hits = kb.search(q, k=1)
            tag = hits[0].doc if hits else "*** GAP ***"
            print(f"  {q:38s} -> {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
