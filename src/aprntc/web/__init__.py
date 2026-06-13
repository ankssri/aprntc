"""Web dashboard backend — FastAPI REST API over the aprntc engine.

Exposes the promotion gate, lineage, trajectory store, and experience memory so a
modern React frontend can drive the human-in-the-loop review. Needs the `web`
extra:  pip install -e '.[web]'.  Run:  uvicorn aprntc.web.app:app --reload
"""

from aprntc.web.app import create_app

__all__ = ["create_app"]
