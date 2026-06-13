"""Streamlit review UI — the human promotion gate.

Shows the candidate playbook diff, the gate report (win-rate / CI / loss / hard
gates), and lets a reviewer **Promote** (record a new generation) or **Rollback**
(revert to the prior generation). This is the human-in-the-loop control surface;
the acceptance bar is computed by :class:`aprntc.promote.PromotionGate` — the UI
only displays it and records the human decision in the lineage registry.

Reads a small JSON "review bundle" (written by an eval run) so the UI stays
decoupled from live model calls:

    {
      "diff": {...PlaybookDiff.to_dict()...},
      "gate": {...GateReport fields...},
      "candidate_playbook_hash": "pb_...",
      "lineage_path": "lineage.json"
    }

Run:  streamlit run src/aprntc/ui/review_app.py -- --bundle review_bundle.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import streamlit as st  # provided by the `ui` extra

from aprntc.promote.lineage import LineageRegistry


def _load_bundle(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", default="review_bundle.json")
    args, _ = parser.parse_known_args()
    bundle = _load_bundle(args.bundle)

    st.set_page_config(page_title="aprntc — promotion review", layout="wide")
    st.title("aprntc — Promotion Review")
    st.caption("Human-in-the-loop gate: review the candidate child, then promote or roll back.")

    if not bundle:
        st.warning(f"No review bundle found at {args.bundle!r}. Run an eval to produce one.")
        return

    gate = bundle.get("gate", {})
    diff = bundle.get("diff", {})
    cand_hash = bundle.get("candidate_playbook_hash", "?")
    lineage_path = bundle.get("lineage_path", "lineage.json")
    registry = LineageRegistry(lineage_path)

    # -- gate metrics --------------------------------------------------------
    st.subheader("Acceptance bar")
    passed = gate.get("passed") if "passed" in gate else _all_ok(gate)
    cols = st.columns(4)
    cols[0].metric("Win-rate", _pct(gate.get("win_rate")), help="≥ 55% to pass")
    cols[1].metric("CI low", _pct(gate.get("ci_low")), help="> 50% to pass (95% CI)")
    cols[2].metric("Loss-rate", _pct(gate.get("loss_rate")), help="< 10% to pass")
    cols[3].metric("N", str(gate.get("n", "—")))

    hard = []
    if gate.get("regression_failures"):
        hard.append(f"{gate['regression_failures']} regression failure(s)")
    if gate.get("safety_failures"):
        hard.append(f"{gate['safety_failures']} safety failure(s)")
    if hard:
        st.error("HARD GATE FAILED (zero-tolerance): " + ", ".join(hard))
    st.markdown(f"**Decision (automated):** {'✅ PROMOTE-eligible' if passed else '❌ REJECT'}  ·  "
                f"candidate `{cand_hash}`")

    # -- the attributable diff ----------------------------------------------
    st.subheader("Candidate playbook diff (attributable)")
    _render_list("➕ Directives", diff.get("add_directives", []))
    _render_list("➕ Exemplars", diff.get("add_exemplars", []))
    _render_list("⚠️ Watch-out (anti-patterns)", diff.get("add_watch_out", []))
    with st.expander("Provenance (item → source lesson ids)"):
        st.json(diff.get("provenance", {}))

    # -- lineage + actions ---------------------------------------------------
    st.subheader("Lineage")
    cur = registry.current
    st.write(f"Current generation: **G{cur.generation if cur else '—'}**"
             + (f" (`{cur.playbook_hash}`)" if cur else ""))
    st.json([g.to_dict() for g in registry.history()])

    c1, c2 = st.columns(2)
    with c1:
        disabled = not passed
        if st.button("✅ Promote candidate", type="primary", disabled=disabled,
                     help="Disabled until the acceptance bar passes"):
            if cur is None:
                registry.register_parent(cand_hash, note="seeded at first promote")
            g = registry.promote(cand_hash, gate_summary=_summary(gate), note="human-approved")
            st.success(f"Promoted to G{g.generation}. The child is now the live parent.")
            st.rerun()
    with c2:
        if st.button("↩️ Rollback to previous generation",
                     disabled=(cur is None or cur.parent_generation is None)):
            g = registry.rollback()
            st.success(f"Rolled back to G{g.generation}.")
            st.rerun()


def _all_ok(gate: dict) -> bool:
    return (
        gate.get("win_rate_ok", False) and gate.get("ci_ok", False)
        and gate.get("loss_ok", False) and gate.get("regression_ok", False)
        and gate.get("safety_ok", False)
    )


def _summary(gate: dict) -> str:
    return (f"n={gate.get('n')} win={_pct(gate.get('win_rate'))} "
            f"ci_low={_pct(gate.get('ci_low'))} loss={_pct(gate.get('loss_rate'))}")


def _pct(x) -> str:
    return f"{x:.0%}" if isinstance(x, (int, float)) else "—"


def _render_list(title: str, items: list) -> None:
    st.markdown(f"**{title}**")
    if not items:
        st.caption("(none)")
        return
    for it in items:
        st.markdown(f"- {it}")


if __name__ == "__main__":
    main()
