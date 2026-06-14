"""B0 playbook serving — registry (register/infer/promote/rollback) + the fetch API."""

import pytest

from aprntc.distill.playbook import Playbook
from aprntc.serving import PlaybookRegistry, infer_g0_from_messages


# ─── registry ────────────────────────────────────────────────────────────────

def test_register_and_get_active(tmp_path):
    reg = PlaybookRegistry(tmp_path / "pb.json")
    reg.register("agent-1", Playbook(system_prompt="You are support."))
    ap = reg.get_active("agent-1")
    assert ap.generation == 0 and ap.source == "registered"
    assert "support" in ap.playbook.system_prompt
    assert ap.hash.startswith("pb_")


def test_get_active_unknown_raises(tmp_path):
    with pytest.raises(KeyError):
        PlaybookRegistry(tmp_path / "pb.json").get_active("nope")


def test_infer_g0_from_traffic():
    msgs = [{"role": "system", "content": "You are a BytePlus expert."},
            {"role": "user", "content": "hi"}]
    pb = infer_g0_from_messages(msgs)
    assert pb is not None and "BytePlus expert" in pb.system_prompt


def test_infer_g0_none_when_no_system_message():
    assert infer_g0_from_messages([{"role": "user", "content": "hi"}]) is None


def test_ensure_g0_from_traffic_only_when_absent(tmp_path):
    reg = PlaybookRegistry(tmp_path / "pb.json")
    msgs = [{"role": "system", "content": "Observed prompt."}]
    ap = reg.ensure_g0_from_traffic("a", msgs)
    assert ap.source == "inferred"
    # second call is a no-op (already has a playbook) — keeps the inferred one
    again = reg.ensure_g0_from_traffic("a", [{"role": "system", "content": "different"}])
    assert again.playbook.system_prompt == "Observed prompt."


def test_promote_and_rollback_flip_active(tmp_path):
    reg = PlaybookRegistry(tmp_path / "pb.json")
    reg.register("a", Playbook(system_prompt="base"))
    g1 = reg.promote("a", Playbook(system_prompt="base", directives=["cite sources"]))
    assert g1.generation == 1 and g1.source == "promoted"
    assert reg.get_active("a").generation == 1

    back = reg.rollback("a")
    assert back.generation == 0                 # external agent now fetches G0 again
    assert reg.history("a") == [0, 1]           # both versions retained


def test_rollback_at_g0_errors(tmp_path):
    reg = PlaybookRegistry(tmp_path / "pb.json")
    reg.register("a", Playbook(system_prompt="base"))
    with pytest.raises(RuntimeError):
        reg.rollback("a")


def test_registry_persists(tmp_path):
    path = tmp_path / "pb.json"
    PlaybookRegistry(path).register("a", Playbook(system_prompt="hello"))
    assert PlaybookRegistry(path).get_active("a").playbook.system_prompt == "hello"


# ─── API endpoints ───────────────────────────────────────────────────────────

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from aprntc.web.app import AppState, create_app  # noqa: E402


def _client(tmp_path):
    state = AppState(
        lineage_path=str(tmp_path / "l.json"),
        bundle_path=str(tmp_path / "b.json"),
        playbooks=PlaybookRegistry(tmp_path / "pb.json"),
    )
    return TestClient(create_app(state))


def test_api_register_then_fetch_active(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/playbooks/ext-agent/register",
               json={"system_prompt": "You are a LangChain agent.", "directives": ["be precise"]})
    assert r.status_code == 200 and r.json()["generation"] == 0

    got = c.get("/api/playbooks/ext-agent/active").json()
    assert "LangChain agent" in got["playbook"]["system_prompt"]
    # the rendered prompt the agent actually uses includes the directive
    assert "be precise" in got["rendered_prompt"]


def test_api_register_requires_system_prompt(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/playbooks/x/register", json={}).status_code == 400


def test_api_fetch_unknown_agent_404(tmp_path):
    assert _client(tmp_path).get("/api/playbooks/none/active").status_code == 404


def test_api_rollback(tmp_path):
    c = _client(tmp_path)
    c.post("/api/playbooks/a/register", json={"system_prompt": "base"})
    # rollback at G0 (nothing earlier) -> 409
    assert c.post("/api/playbooks/a/rollback").status_code == 409
