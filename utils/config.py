# utils/config.py
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# X credentials: the secrets file outside OneDrive wins; the legacy in-repo
# file (gitignored) is only a fallback so an older setup keeps working.
# Override the secrets path with the ADDOMINUM_ENV environment variable.
SECRETS_ENV_FILE = Path(os.environ.get("ADDOMINUM_ENV", Path.home() / ".secrets" / "x-addominum.env"))
LEGACY_ENV_FILE = BASE_DIR / "config" / "api_keys.env"
ENV_FILE_USED: Path | None = None

try:
    from dotenv import load_dotenv
    for _candidate in (SECRETS_ENV_FILE, LEGACY_ENV_FILE):
        if _candidate.is_file():
            load_dotenv(_candidate)
            ENV_FILE_USED = _candidate
            break
except ImportError:
    pass

try:
    import yaml
    _sf = BASE_DIR / "config" / "settings.yaml"
    _settings = yaml.safe_load(_sf.read_text(encoding="utf-8")) or {} if _sf.exists() else {}
except Exception:
    _settings = {}

_DEFAULTS = {
    "dry_run": True, "loop_forever": True,
    "posts_per_day_min": 4, "posts_per_day_max": 10,
    "post_window_start": 8, "post_window_end": 20,
    "quote_to_history_ratio": 3, "queue_max_size": 300,
    "queue_cache_hours": 6, "max_post_length": 280,
}

class Config:
    def __init__(self):
        self._data = {**_DEFAULTS, **_settings}
        self.x_api_key       = os.getenv("X_API_KEY", "")
        self.x_api_secret    = os.getenv("X_API_SECRET", "")
        self.x_access_token  = os.getenv("X_ACCESS_TOKEN", "")
        self.x_access_secret = os.getenv("X_ACCESS_SECRET", "")
        self.x_bearer_token  = os.getenv("X_BEARER_TOKEN", "")

    def get(self, key, default=None):
        return self._data.get(key, default)

    @property
    def dry_run(self): return bool(self._data.get("dry_run", True))
    @property
    def loop_forever(self): return bool(self._data.get("loop_forever", True))
    @property
    def min_interval_minutes(self): return int(self._data.get("min_interval_minutes", 55))
    @property
    def max_interval_minutes(self): return int(self._data.get("max_interval_minutes", 110))
    @property
    def has_credentials(self):
        return all([self.x_api_key, self.x_api_secret,
                    self.x_access_token, self.x_access_secret])

    def __repr__(self):
        return (f"Config(dry_run={self.dry_run}, "
                f"interval={self.min_interval_minutes}-{self.max_interval_minutes}min, "
                f"credentials={'yes' if self.has_credentials else 'missing'}, "
                f"env_file={ENV_FILE_USED.name if ENV_FILE_USED else 'none'})")

config = Config()
