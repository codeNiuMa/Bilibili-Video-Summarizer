from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

APP_DIR = Path.home() / ".bili_summarizer"
CONFIG_FILE = APP_DIR / "config.json"
API_KEY_FILE = APP_DIR / "api_key.txt"
LOG_DIR = APP_DIR / "logs"
PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = PROJECT_DIR / "downloads"

DEFAULT_MODEL = "gemini-3.5-flash-lite"


@dataclass
class Settings:
    model: str = DEFAULT_MODEL
    cookie_file: str = ""
    keep_download: bool = False
    appearance: str = "system"


def ensure_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    ensure_dirs()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return Settings(
            model=str(data.get("model") or DEFAULT_MODEL),
            cookie_file=str(data.get("cookie_file") or ""),
            keep_download=bool(data.get("keep_download", False)),
            appearance=str(data.get("appearance") or "system"),
        )
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    ensure_dirs()
    CONFIG_FILE.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_api_key() -> str:
    """Environment variable wins; otherwise read the local key file."""
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key

    ensure_dirs()
    try:
        return API_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_api_key(api_key: str) -> None:
    ensure_dirs()
    API_KEY_FILE.write_text(api_key.strip(), encoding="utf-8")
