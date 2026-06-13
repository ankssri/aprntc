# ADR 0001 — VikingDB access via REST (not the SDK)

**Status:** Accepted (2026-06)

## Context
The Experience Memory store is VikingDB (BytePlus). It offers a Python SDK (`volcengine`) and a REST
API. We need a clean, light, swappable integration consistent with the anti-lock-in principle.

## Decision
Access VikingDB over **REST (httpx)**, with our **own Volcengine Signature-V4 signer**
(`src/aprntc/byteplus/signing.py`). The `volcengine` SDK is used only as a **dev-only test oracle** to
validate our signer byte-for-byte — never a runtime dependency.

## Rationale
- Lighter dependency, async-friendly, full control over retries/timeouts/pooling.
- Keeps the core dependency-light; VikingDB stays behind the `MemoryStore` interface (swappable).
- The one risk — owning request signing — is contained in one unit-tested module and proven against
  the SDK oracle (`tests/test_signing_oracle.py`) AND the live endpoint (Stage 0 smoke test).

## Alternatives rejected
- **Volcengine SDK at runtime** — heavier monolithic dep, mostly sync, ties us to its release cadence
  and surface. (We still use it as the signing oracle in dev.)

## Consequences
- We maintain the SigV4 signer. Mitigated by the oracle test (regression-proof).
- **Live finding:** VikingDB **control plane uses `Action=` query params**, data plane uses fixed
  paths — the Stage 5 adapter must handle both shapes.
