"""BytePlus product-support agent — a REAL demo parent grounded in BytePlus docs.

Unlike the toy support/RAG demos, this agent answers questions about the BytePlus
AI stack (ModelArk LLM, VikingDB, image/video/speech generation, RAG Cloud) from
the actual documentation. It has genuine *headroom* for the apprentice to improve:
a deliberately thin "parent" config makes real mistakes (incomplete / uncited /
shallow answers) that a distilled child learns to fix.

This is the agent intended for eventual production deployment, tested against the
apprentice loop.
"""

from aprntc.demos.byteplus.kb import Chunk, KnowledgeBase, build_kb
from aprntc.demos.byteplus.agent import ByteplusSupportAgent
from aprntc.demos.byteplus.gold import GOLD, GoldQA
from aprntc.demos.byteplus.outcome import byteplus_outcome

__all__ = [
    "Chunk", "KnowledgeBase", "build_kb", "ByteplusSupportAgent",
    "GOLD", "GoldQA", "byteplus_outcome",
]
