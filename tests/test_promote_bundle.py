"""The gate → UI contract: a gate report + diff serialize into a review bundle the
UI consumes. Keeps the human-review surface decoupled from live model calls."""

import json

from aprntc.distill import Playbook, PlaybookDiff
from aprntc.promote.stats import GateReport


def _report(**over) -> GateReport:
    base = dict(n=100, wins=60, losses=8, ties=0, win_rate=0.60, ci_low=0.51,
                ci_high=0.69, loss_rate=0.08, regression_failures=0, safety_failures=0,
                win_rate_ok=True, ci_ok=True, loss_ok=True, regression_ok=True, safety_ok=True)
    base.update(over)
    return GateReport(**base)


def test_review_bundle_is_json_serializable_and_complete(tmp_path):
    diff = PlaybookDiff(add_directives=["cite docs"], add_watch_out=["don't guess"],
                        provenance={"cite docs": ["les_1"]})
    pb = Playbook(system_prompt="s")
    rep = _report()
    bundle = {
        "diff": diff.to_dict(),
        "gate": {
            "n": rep.n, "win_rate": rep.win_rate, "ci_low": rep.ci_low,
            "loss_rate": rep.loss_rate, "regression_failures": rep.regression_failures,
            "safety_failures": rep.safety_failures, "passed": rep.passed,
            "win_rate_ok": rep.win_rate_ok, "ci_ok": rep.ci_ok, "loss_ok": rep.loss_ok,
            "regression_ok": rep.regression_ok, "safety_ok": rep.safety_ok,
        },
        "candidate_playbook_hash": pb.hash,
        "lineage_path": str(tmp_path / "lineage.json"),
    }
    # round-trips through JSON (the UI reads it from disk)
    path = tmp_path / "review_bundle.json"
    path.write_text(json.dumps(bundle))
    loaded = json.loads(path.read_text())
    assert loaded["gate"]["passed"] is True
    assert loaded["diff"]["add_directives"] == ["cite docs"]
    assert loaded["candidate_playbook_hash"].startswith("pb_")


def test_failing_report_marks_not_passed():
    rep = _report(ci_low=0.40, ci_ok=False)
    assert rep.passed is False and rep.decision == "reject"
