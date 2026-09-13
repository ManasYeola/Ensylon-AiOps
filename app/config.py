"""
Central configuration loader — reads config.yaml once and provides typed access.
All thresholds and weights are loaded from here; never hardcode them in business logic.
.env is loaded automatically so GROQ_API_KEY / GEMINI_API_KEY etc. are always available.
"""
from pathlib import Path
from functools import lru_cache
import yaml

# Load .env at import time — this runs once, before any os.getenv() call in the app
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars


CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_correlation_cfg() -> dict:
    return load_config()["correlation"]


def get_severity_cfg() -> dict:
    return load_config()["severity"]


def get_confidence_cfg() -> dict:
    return load_config()["confidence"]


def get_detection_cfg() -> dict:
    return load_config()["detection"]


def get_validation_cfg() -> dict:
    return load_config()["validation"]


def get_fingerprint_cfg() -> dict:
    return load_config()["fingerprint"]
