"""Volcengine Signature V4 (HMAC-SHA256) request signing — the VikingDB gate.

We talk to VikingDB over REST (no SDK at runtime), so we own the signing. This
module reimplements Volcengine's SigV4 (AWS-SigV4-style). It is THE highest-risk
piece of the VikingDB adapter: a single mismatch in canonicalization yields a
403 InvalidSignature. It is therefore validated byte-for-byte against the
``volcengine`` SDK's ``SignerV4.sign`` in ``tests/test_signing_oracle.py``.

Algorithm (per BytePlus VikingDB "Prerequisites and Signature" docs; the SDK
reference uses ``Credentials(ak, sk, "air", "ap-southeast-1")``):

  signed headers  = host;x-content-sha256;x-date   (+ content-type when a body
                    is present, inserted in sorted order)
  x-date          = UTC, ``%Y%m%dT%H%M%SZ``
  x-content-sha256= lowercase hex SHA-256 of the raw request body (empty-string
                    hash when there is no body)
  credential scope= {YYYYMMDD}/{region}/{service}/request
  canonical req   = METHOD\\n CanonicalURI\\n CanonicalQuery\\n
                    CanonicalHeaders\\n SignedHeaders\\n HashedPayload
  string to sign  = HMAC-SHA256\\n {x-date}\\n {credential scope}\\n
                    hex(SHA256(canonical req))
  signing key     = HMAC(HMAC(HMAC(HMAC(sk, YYYYMMDD), region), service), "request")
  Authorization   = HMAC-SHA256 Credential={ak}/{scope},
                    SignedHeaders={signed}, Signature={hex hmac}
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

_ALGORITHM = "HMAC-SHA256"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


@dataclass(frozen=True)
class Credentials:
    ak: str
    sk: str
    service: str = "air"
    region: str = "ap-southeast-1"


@dataclass
class SignedRequest:
    """Result of signing: everything needed to issue the HTTP call."""

    method: str
    url: str
    headers: dict[str, str]
    body: bytes
    query: dict[str, str] = field(default_factory=dict)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _hmac_hex(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _canonical_query(query: dict[str, str]) -> str:
    """Sorted, percent-encoded ``k=v&...`` (empty string when no query)."""
    if not query:
        return ""
    items = sorted(query.items())
    # Volcengine/AWS canonicalization: encode with no safe chars beyond unreserved.
    return urlencode(items, quote_via=lambda s, *_: quote(s, safe="-_.~"))


def _canonical_uri(path: str) -> str:
    """Canonical URI = the request path, used verbatim (already absolute)."""
    return path or "/"


def signing_key(creds: Credentials, date_stamp: str) -> bytes:
    """Derive the SigV4 signing key: sk → date → region → service → 'request'."""
    k_date = _hmac(creds.sk.encode("utf-8"), date_stamp)
    k_region = _hmac(k_date, creds.region)
    k_service = _hmac(k_region, creds.service)
    return _hmac(k_service, "request")


def sign(
    *,
    method: str,
    host: str,
    path: str,
    creds: Credentials,
    body: bytes = b"",
    query: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    now: datetime | None = None,
) -> SignedRequest:
    """Sign a request and return it with the ``Authorization`` header populated.

    ``now`` is injectable so the oracle test can pin a deterministic timestamp.
    """
    method = method.upper()
    query = dict(query or {})
    extra_headers = dict(headers or {})

    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    x_date = ts.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = ts.strftime("%Y%m%d")

    payload_hash = _sha256_hex(body) if body else _EMPTY_SHA256

    # Headers that are always signed.
    signed: dict[str, str] = {
        "host": host,
        "x-content-sha256": payload_hash,
        "x-date": x_date,
    }
    # content-type is signed when present (e.g. JSON POST bodies).
    content_type = extra_headers.get("Content-Type") or extra_headers.get("content-type")
    if content_type:
        signed["content-type"] = content_type

    signed_header_names = ";".join(sorted(signed))
    canonical_headers = "".join(f"{k}:{signed[k]}\n" for k in sorted(signed))

    canonical_request = "\n".join(
        [
            method,
            _canonical_uri(path),
            _canonical_query(query),
            canonical_headers,
            signed_header_names,
            payload_hash,
        ]
    )

    credential_scope = f"{date_stamp}/{creds.region}/{creds.service}/request"
    string_to_sign = "\n".join(
        [
            _ALGORITHM,
            x_date,
            credential_scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )

    signature = _hmac_hex(signing_key(creds, date_stamp), string_to_sign)
    authorization = (
        f"{_ALGORITHM} "
        f"Credential={creds.ak}/{credential_scope}, "
        f"SignedHeaders={signed_header_names}, "
        f"Signature={signature}"
    )

    out_headers = {
        **extra_headers,
        "Host": host,
        "X-Date": x_date,
        "X-Content-Sha256": payload_hash,
        "Authorization": authorization,
    }

    scheme = "https"
    qs = _canonical_query(query)
    url = f"{scheme}://{host}{_canonical_uri(path)}" + (f"?{qs}" if qs else "")

    return SignedRequest(method=method, url=url, headers=out_headers, body=body, query=query)
