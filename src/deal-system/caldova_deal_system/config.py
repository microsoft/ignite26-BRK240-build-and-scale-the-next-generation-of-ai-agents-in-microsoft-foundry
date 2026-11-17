"""Settings, read from DEAL_SYSTEM_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent  # src/deal-system
REPO_ROOT = PACKAGE_DIR.parents[2]


@dataclass
class Settings:
    state_dir: Path = PROJECT_DIR / ".state"
    seed_path: Path = REPO_ROOT / "data" / "generated" / "deal_system_seed.json"
    template_path: Path = PACKAGE_DIR / "templates" / "term-sheet-template.md"
    api_key: str | None = None
    port: int = 8080
    approval_ttl_minutes: int = 240

    @property
    def local_url(self) -> str:
        return f"http://localhost:{self.port}"

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        settings = cls(api_key=env.get("DEAL_SYSTEM_API_KEY") or None, port=int(env.get("DEAL_SYSTEM_PORT") or 8080))
        if env.get("DEAL_SYSTEM_STATE_DIR"):
            settings.state_dir = Path(env["DEAL_SYSTEM_STATE_DIR"])
        if env.get("DEAL_SYSTEM_SEED_PATH"):
            settings.seed_path = Path(env["DEAL_SYSTEM_SEED_PATH"])
        return settings
