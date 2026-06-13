"""Unit tests for the SigV4 signer — deterministic, no network, no SDK needed.

These lock the algorithm's structure (header set, scope, key derivation,
canonicalization). The byte-for-byte equivalence to the official SDK lives in
``test_signing_oracle.py`` (marked ``oracle``).
"""

from datetime import datetime, timezone

import pytest

from aprntc.byteplus.signing import Credentials, sign, signing_key

CREDS = Credentials(ak="AKTEST", sk="SKTEST", service="air", region="ap-southeast-1")
PINNED = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
HOST = "api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com"


def _sign_get():
    return sign(method="GET", host=HOST, path="/api/collection/info", creds=CREDS,
                query={"collection_name": "test"}, now=PINNED)


def _sign_post():
    return sign(method="POST", host=HOST, path="/api/vikingdb/data/upsert", creds=CREDS,
                body=b'{"collection_name":"c"}',
                headers={"Content-Type": "application/json"}, now=PINNED)


def test_authorization_header_shape():
    r = _sign_get()
    auth = r.headers["Authorization"]
    assert auth.startswith("HMAC-SHA256 ")
    assert "Credential=AKTEST/20260613/ap-southeast-1/air/request" in auth
    assert "SignedHeaders=" in auth and "Signature=" in auth


def test_x_date_and_content_sha_headers():
    r = _sign_get()
    assert r.headers["X-Date"] == "20260613T120000Z"
    # empty-body GET → empty-string sha256
    assert r.headers["X-Content-Sha256"] == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_signed_headers_sorted_and_include_required():
    r = _sign_get()
    signed = r.headers["Authorization"].split("SignedHeaders=")[1].split(",")[0]
    names = signed.split(";")
    assert names == sorted(names)  # canonical order
    assert "host" in names and "x-content-sha256" in names and "x-date" in names


def test_post_signs_content_type_and_body_hash():
    r = _sign_post()
    signed = r.headers["Authorization"].split("SignedHeaders=")[1].split(",")[0]
    assert "content-type" in signed.split(";")
    # body hash is the sha256 of the JSON body, not the empty hash
    assert r.headers["X-Content-Sha256"] != (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_determinism_same_inputs_same_signature():
    assert _sign_get().headers["Authorization"] == _sign_get().headers["Authorization"]


def test_different_body_changes_signature():
    a = sign(method="POST", host=HOST, path="/p", creds=CREDS, body=b"a",
             headers={"Content-Type": "application/json"}, now=PINNED)
    b = sign(method="POST", host=HOST, path="/p", creds=CREDS, body=b"b",
             headers={"Content-Type": "application/json"}, now=PINNED)
    assert a.headers["Authorization"] != b.headers["Authorization"]


def test_signing_key_derivation_is_stable():
    assert signing_key(CREDS, "20260613") == signing_key(CREDS, "20260613")
    assert signing_key(CREDS, "20260613") != signing_key(CREDS, "20260614")


def test_url_includes_canonical_query():
    r = _sign_get()
    assert r.url == f"https://{HOST}/api/collection/info?collection_name=test"


def test_empty_path_defaults_to_root():
    r = sign(method="GET", host=HOST, path="", creds=CREDS, now=PINNED)
    assert r.url == f"https://{HOST}/"
