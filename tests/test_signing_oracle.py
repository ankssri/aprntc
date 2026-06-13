"""Byte-for-byte equivalence: our SigV4 signer vs the official ``volcengine`` SDK.

This is THE gate for the VikingDB adapter. The BytePlus docs' reference
``volc_auth.py`` builds a ``volcengine`` ``Request`` and calls
``SignerV4.sign(r, Credentials(ak, sk, "air", "ap-southeast-1"))``. We reproduce
that exact call and assert the resulting ``Authorization`` (and the signed
headers it covers) match ours for identical inputs and a pinned timestamp.

Skipped automatically if ``volcengine`` isn't installed (it is a DEV-only
oracle, never a runtime dependency). Run with: ``pytest -m oracle``.
"""

from datetime import datetime, timezone

import pytest

from aprntc.byteplus.signing import Credentials, sign

volcengine = pytest.importorskip("volcengine", reason="dev-only signing oracle")

from volcengine.auth.SignerV4 import SignerV4  # noqa: E402
from volcengine.base.Request import Request  # noqa: E402
from volcengine.Credentials import Credentials as SdkCredentials  # noqa: E402

pytestmark = pytest.mark.oracle

AK, SK = "AKIDEXAMPLE", "SKEXAMPLEKEY"
REGION, SERVICE = "ap-southeast-1", "air"
HOST = "api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com"


def _sdk_sign(method: str, path: str, *, body: str = "", query: dict | None = None) -> Request:
    """Sign via the official SDK. It stamps X-Date with wall-clock time (no pinning
    kwarg in this SDK version), so callers read X-Date back to align our signer."""
    r = Request()
    r.set_shema("https")
    r.set_method(method)
    r.set_host(HOST)
    r.set_path(path)
    headers = {"Host": HOST}
    if body:
        headers["Content-Type"] = "application/json"
        r.set_body(body)
    r.set_headers(headers)
    if query:
        r.set_query(query)
    SignerV4.sign(r, SdkCredentials(AK, SK, SERVICE, REGION))
    return r


def _sdk_x_date(r: Request) -> datetime:
    xdate = r.headers["X-Date"]
    return datetime.strptime(xdate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def _ours(method: str, path: str, *, when: datetime, body: str = "", query: dict | None = None):
    return sign(
        method=method, host=HOST, path=path,
        creds=Credentials(ak=AK, sk=SK, service=SERVICE, region=REGION),
        body=body.encode("utf-8") if body else b"",
        query=query,
        headers={"Content-Type": "application/json"} if body else None,
        now=when,
    )


def _norm(auth: str) -> str:
    return auth.replace(" ", "")


@pytest.mark.parametrize(
    "method,path,body,query",
    [
        ("GET", "/api/collection/info", "", {"collection_name": "test_collection"}),
        ("POST", "/api/vikingdb/data/upsert", '{"collection_name":"c"}', None),
        ("POST", "/api/vikingdb/data/search/vector", '{"index_name":"i","limit":5}', None),
        ("GET", "/api/index/info", "", None),
    ],
)
def test_authorization_matches_sdk(method, path, body, query):
    # Sign with the SDK, align our timestamp to the SDK's stamped X-Date, then compare.
    sdk = _sdk_sign(method, path, body=body, query=query)
    ours = _ours(method, path, when=_sdk_x_date(sdk), body=body, query=query)
    sdk_auth = sdk.headers.get("Authorization") or sdk.headers.get("authorization")
    assert _norm(ours.headers["Authorization"]) == _norm(sdk_auth)


def test_x_content_sha256_matches_sdk():
    sdk = _sdk_sign("POST", "/api/vikingdb/data/upsert", body='{"a":1}')
    ours = _ours("POST", "/api/vikingdb/data/upsert", when=_sdk_x_date(sdk), body='{"a":1}')
    sdk_hash = sdk.headers.get("X-Content-Sha256") or sdk.headers.get("x-content-sha256")
    assert ours.headers["X-Content-Sha256"] == sdk_hash
