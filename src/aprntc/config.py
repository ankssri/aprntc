"""Configuration — loaded from environment / a local ``.env`` file.

Core stays dependency-free, so this is a tiny stdlib ``.env`` reader rather than
a third-party loader. Real secrets live in ``.env`` (gitignored); ``.env.example``
documents every variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | os.PathLike[str] = ".env", *, override: bool = False) -> dict[str, str]:
    """Parse a ``.env`` file into ``os.environ``. Returns the parsed pairs.

    Minimal by design: ``KEY=value`` per line, ``#`` comments, blank lines and
    surrounding quotes ignored. Missing file is a no-op (returns ``{}``).
    """
    p = Path(path)
    parsed: dict[str, str] = {}
    if not p.exists():
        return parsed
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        parsed[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return parsed


@dataclass(frozen=True)
class ModelArkConfig:
    """BytePlus ModelArk (LLM) settings. ``policy`` and ``judge`` MUST differ."""

    api_key: str
    base_url: str
    policy_model: str
    judge_model: str

    def validate(self) -> None:
        missing = [
            name
            for name, val in (
                ("ARK_API_KEY", self.api_key),
                ("APRNTC_POLICY_MODEL", self.policy_model),
                ("APRNTC_JUDGE_MODEL", self.judge_model),
            )
            if not val
        ]
        if missing:
            raise ValueError(f"ModelArk config missing: {', '.join(missing)}")
        if self.policy_model == self.judge_model:
            raise ValueError(
                "judge model must differ from policy model (recused judge); "
                f"both are {self.policy_model!r}"
            )


@dataclass(frozen=True)
class VikingDBConfig:
    """BytePlus VikingDB settings for the REST adapter + SigV4 signing."""

    ak: str
    sk: str
    region: str
    data_host: str
    control_host: str
    # SigV4 signing service. MUST be "vikingdb" for the V2 API (control + data planes);
    # confirmed live (service="air" 403s — the earlier volc_auth.py used a different API).
    service: str = "vikingdb"

    def validate(self) -> None:
        missing = [
            name
            for name, val in (
                ("VIKINGDB_AK", self.ak),
                ("VIKINGDB_SK", self.sk),
                ("VIKINGDB_REGION", self.region),
                ("VIKINGDB_DATA_HOST", self.data_host),
                ("VIKINGDB_CONTROL_HOST", self.control_host),
            )
            if not val
        ]
        if missing:
            raise ValueError(f"VikingDB config missing: {', '.join(missing)}")


@dataclass(frozen=True)
class Settings:
    modelark: ModelArkConfig
    vikingdb: VikingDBConfig

    @classmethod
    def from_env(cls, *, dotenv: str | os.PathLike[str] | None = ".env") -> "Settings":
        if dotenv is not None:
            load_dotenv(dotenv)
        env = os.environ
        return cls(
            modelark=ModelArkConfig(
                api_key=env.get("ARK_API_KEY", ""),
                base_url=env.get("ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3"),
                policy_model=env.get("APRNTC_POLICY_MODEL", ""),
                judge_model=env.get("APRNTC_JUDGE_MODEL", ""),
            ),
            vikingdb=VikingDBConfig(
                ak=env.get("VIKINGDB_AK", ""),
                sk=env.get("VIKINGDB_SK", ""),
                region=env.get("VIKINGDB_REGION", "ap-southeast-1"),
                data_host=env.get("VIKINGDB_DATA_HOST", "api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com"),
                control_host=env.get("VIKINGDB_CONTROL_HOST", "vikingdb.ap-southeast-1.byteplusapi.com"),
            ),
        )
