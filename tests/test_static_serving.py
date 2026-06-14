"""B1 deploy — static frontend serving (SPA fallback) without shadowing the API."""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from aprntc.web.app import AppState, create_app  # noqa: E402


def _app(tmp_path, static_dir=None, monkeypatch=None):
    if static_dir is not None and monkeypatch is not None:
        monkeypatch.setenv("APRNTC_STATIC_DIR", str(static_dir))
    elif monkeypatch is not None:
        monkeypatch.delenv("APRNTC_STATIC_DIR", raising=False)
    return create_app(AppState(
        lineage_path=str(tmp_path / "l.json"),
        bundle_path=str(tmp_path / "b.json"),
    ))


def test_api_only_when_no_build(tmp_path, monkeypatch):
    # point static dir at an empty path -> no mount; API still works, unknown path 404s
    c = TestClient(_app(tmp_path, static_dir=tmp_path / "nope", monkeypatch=monkeypatch))
    assert c.get("/api/health").status_code == 200
    assert c.get("/some/spa/route").status_code == 404  # no SPA fallback without a build


def _make_build(d):
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text("<!doctype html><div id=root>aprntc</div>")
    (d / "assets").mkdir(exist_ok=True)
    (d / "assets" / "app.js").write_text("console.log('app')")
    return d


def test_spa_served_when_built(tmp_path, monkeypatch):
    build = _make_build(tmp_path / "dist")
    c = TestClient(_app(tmp_path, static_dir=build, monkeypatch=monkeypatch))

    # root serves index.html
    root = c.get("/")
    assert root.status_code == 200 and "aprntc" in root.text

    # client-side route falls back to index.html (SPA)
    spa = c.get("/trajectories")
    assert spa.status_code == 200 and "id=root" in spa.text

    # a real asset is served directly
    asset = c.get("/assets/app.js")
    assert asset.status_code == 200 and "console.log" in asset.text


def test_api_not_shadowed_by_spa(tmp_path, monkeypatch):
    build = _make_build(tmp_path / "dist")
    c = TestClient(_app(tmp_path, static_dir=build, monkeypatch=monkeypatch))
    # /api/* still returns JSON, NOT the SPA index.html
    h = c.get("/api/health")
    assert h.status_code == 200 and h.json()["status"] == "ok"
    # unknown /api/* path 404s as API, not SPA fallback
    assert c.get("/api/does-not-exist").status_code == 404
