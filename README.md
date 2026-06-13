# aprntc

> An **apprentice** agent that shadows a live **parent** agent, distills lessons from its
> behavior, becomes a measurably better version, and — gated by a human — is **promoted**
> to replace it. Then the cycle repeats. Codename **"Shadow."**

**Status:** Stage 0 (scaffolding). Not yet usable end-to-end. See the build plan.

## What it is
A standalone, framework-agnostic, self-improving-agent framework:
**observe → label → distill → evaluate → promote**, with a human only at the promotion gate.
Phase 1 learns via **Experience Memory (RAG) + playbook distillation** (no fine-tuning yet);
quality is **anchored on outcomes**, with a **recused LLM judge** (judge ≠ policy).

This is **not** a monitoring/observability product — it learns from the parent's overall
**response quality** to produce a better successor.

## Layout
```
src/aprntc/
  config.py            # env/.env settings (ModelArk + VikingDB)
  byteplus/
    signing.py         # Volcengine Signature-V4 signer (the VikingDB gate)
    modelark.py        # thin OpenAI-compatible ModelArk client (seed of LLMProvider)
scripts/
  smoke_byteplus.py    # live smoke test: signed VikingDB call + policy/judge reachable
tests/
  test_signing.py        # SigV4 unit tests (no network/SDK)
  test_signing_oracle.py # byte-for-byte vs the volcengine SDK (marker: oracle)
```

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[byteplus]'          # runtime (httpx)
pip install -e . pytest volcengine    # + dev/oracle deps

cp .env.example .env                   # then fill in real keys (gitignored)
```

## Configuration
All config via `.env` (see `.env.example`). Region is `ap-southeast-1`.
- **ModelArk:** `ARK_API_KEY`, `APRNTC_POLICY_MODEL` (Seed-2.0-pro), `APRNTC_JUDGE_MODEL`
  (DeepSeek-V4-pro — must differ from policy).
- **VikingDB:** `VIKINGDB_AK`, `VIKINGDB_SK` (+ hosts/region defaulted).

## Tests
```bash
pytest                 # unit tests (signing algorithm, deterministic)
pytest -m oracle       # byte-for-byte signing equivalence vs volcengine SDK
python scripts/smoke_byteplus.py   # live: needs real keys in .env
```

## License
MIT.
