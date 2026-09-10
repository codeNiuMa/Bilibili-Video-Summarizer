from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ai.catalog import (
    DEFAULT_PROVIDER,
    OPENAI_TRANSCRIPTION_MODEL,
    PROVIDERS,
    provider_default_model,
)

APP_DIR = Path.home() / ".bili_summarizer"
CONFIG_FILE = APP_DIR / "config.json"
API_KEY_FILE = APP_DIR / "api_key.txt"  # legacy Gemini key file
API_KEYS_FILE = APP_DIR / "api_keys.json"
MODEL_CACHE_FILE = APP_DIR / "model_cache.json"
LOG_DIR = APP_DIR / "logs"
PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = PROJECT_DIR / "downloads"


def _default_models() -> dict[str, str]:
    return {
        provider_id: provider_default_model(provider_id)
        for provider_id in PROVIDERS
    }


def _default_transcription_models() -> dict[str, str]:
    return {
        "gemini": provider_default_model("gemini"),
        "openai": OPENAI_TRANSCRIPTION_MODEL,
    }


@dataclass
class Settings:
    provider: str = DEFAULT_PROVIDER
    provider_models: dict[str, str] = field(default_factory=_default_models)
    transcription_provider: str = "auto"
    transcription_models: dict[str, str] = field(default_factory=_default_transcription_models)
    cookie_file: str = ""
    keep_download: bool = False
    appearance: str = "system"

    def get_model(self, provider_id: str | None = None) -> str:
        provider_id = (provider_id or self.provider or DEFAULT_PROVIDER).strip().lower()
        return (
            str(self.provider_models.get(provider_id) or "").strip()
            or provider_default_model(provider_id)
        )

    def set_model(self, provider_id: str, model: str) -> None:
        provider_id = (provider_id or DEFAULT_PROVIDER).strip().lower()
        model = (model or "").strip()
        if model:
            self.provider_models[provider_id] = model

    def get_transcription_model(self, provider_id: str) -> str:
        provider_id = (provider_id or "").strip().lower()
        if provider_id == "openai":
            fallback = OPENAI_TRANSCRIPTION_MODEL
        else:
            fallback = provider_default_model(provider_id or "gemini")
        return (
            str(self.transcription_models.get(provider_id) or "").strip()
            or fallback
        )

    def set_transcription_model(self, provider_id: str, model: str) -> None:
        provider_id = (provider_id or "").strip().lower()
        model = (model or "").strip()
        if provider_id in {"gemini", "openai"} and model:
            self.transcription_models[provider_id] = model

    # Backward compatibility for older UI code/plugins.
    @property
    def model(self) -> str:
        return self.get_model(self.provider)

    @model.setter
    def model(self, value: str) -> None:
        self.set_model(self.provider, value)


def ensure_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)



def _normalize_model_list(models) -> list[str]:
    """Normalize, de-duplicate and bound provider model lists before caching."""
    result: list[str] = []
    seen: set[str] = set()

    for value in models or []:
        model = str(value or "").strip()
        if not model or model in seen:
            continue
        seen.add(model)
        result.append(model)

        # Defensive limit; provider model endpoints should never need thousands
        # of entries in this desktop selector.
        if len(result) >= 500:
            break

    return result


def _read_model_cache_payload() -> dict:
    ensure_dirs()
    try:
        payload = json.loads(MODEL_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, ValueError, TypeError):
        pass

    return {
        "version": 1,
        "providers": {},
    }


def load_model_cache() -> dict[str, list[str]]:
    """Load the last successfully refreshed model list for every provider.

    The cache is deliberately persistent and has no hard TTL. Model discovery
    is user-triggered; startup uses the last known good list immediately and
    the refresh buttons explicitly replace it when the user wants fresh data.
    """
    payload = _read_model_cache_payload()
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        return {}

    result: dict[str, list[str]] = {}

    for provider_id in PROVIDERS:
        entry = providers.get(provider_id)

        if isinstance(entry, dict):
            models = entry.get("models")
        else:
            # Tolerate an early/simple cache shape: {"gemini": ["..."]}.
            models = entry

        normalized = _normalize_model_list(models)
        if normalized:
            result[provider_id] = normalized

    return result


def model_cache_updated_at(provider_id: str) -> str:
    """Return the cache timestamp for UI hints; empty when unavailable."""
    payload = _read_model_cache_payload()
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        return ""

    entry = providers.get((provider_id or "").strip().lower())
    if not isinstance(entry, dict):
        return ""

    return str(entry.get("updated_at") or "").strip()


def save_model_cache(provider_id: str, models) -> None:
    """Persist one provider's last successful model-list refresh atomically."""
    provider_id = (provider_id or "").strip().lower()
    if provider_id not in PROVIDERS:
        return

    normalized = _normalize_model_list(models)
    if not normalized:
        # Never destroy a last-known-good cache with an empty/broken response.
        return

    payload = _read_model_cache_payload()
    payload["version"] = 1

    providers = payload.get("providers")
    if not isinstance(providers, dict):
        providers = {}
        payload["providers"] = providers

    providers[provider_id] = {
        "models": normalized,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    ensure_dirs()
    temp_path = MODEL_CACHE_FILE.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(MODEL_CACHE_FILE)

def load_settings() -> Settings:
    ensure_dirs()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return Settings()

    provider = str(data.get("provider") or data.get("active_provider") or DEFAULT_PROVIDER).lower()
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER

    models = _default_models()
    raw_models = data.get("provider_models")
    if isinstance(raw_models, dict):
        for provider_id, model in raw_models.items():
            if provider_id in PROVIDERS and str(model or "").strip():
                models[provider_id] = str(model).strip()

    # Migration from the old single Gemini model field.
    old_model = str(data.get("model") or "").strip()
    if old_model:
        models["gemini"] = old_model

    transcription_provider = str(data.get("transcription_provider") or "auto").lower()
    if transcription_provider not in {"auto", "gemini", "openai"}:
        transcription_provider = "auto"

    # Keep transcription and summary models independent. For existing users,
    # preserve the historical behavior by initially using their saved Gemini
    # summary model as the Gemini transcription model.
    transcription_models = _default_transcription_models()
    raw_transcription_models = data.get("transcription_models")
    if isinstance(raw_transcription_models, dict):
        for provider_id, model in raw_transcription_models.items():
            if provider_id in {"gemini", "openai"} and str(model or "").strip():
                transcription_models[provider_id] = str(model).strip()
    else:
        transcription_models["gemini"] = models["gemini"]

    return Settings(
        provider=provider,
        provider_models=models,
        transcription_provider=transcription_provider,
        transcription_models=transcription_models,
        cookie_file=str(data.get("cookie_file") or ""),
        keep_download=bool(data.get("keep_download", False)),
        appearance=str(data.get("appearance") or "system"),
    )


def save_settings(settings: Settings) -> None:
    ensure_dirs()
    CONFIG_FILE.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_saved_api_keys() -> dict[str, str]:
    ensure_dirs()
    saved: dict[str, str] = {}
    try:
        raw = json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            saved = {
                str(k): str(v).strip()
                for k, v in raw.items()
                if str(k) in PROVIDERS and str(v or "").strip()
            }
    except (OSError, ValueError, TypeError):
        pass

    # Automatic migration from the historical Gemini api_key.txt.
    if not saved.get("gemini"):
        try:
            legacy = API_KEY_FILE.read_text(encoding="utf-8").strip()
            if legacy:
                saved["gemini"] = legacy
        except OSError:
            pass
    return saved


def api_key_from_env(provider_id: str) -> bool:
    spec = PROVIDERS.get(provider_id)
    return bool(spec and os.environ.get(spec.env_var, "").strip())


def load_api_key(provider_id: str = DEFAULT_PROVIDER) -> str:
    provider_id = (provider_id or DEFAULT_PROVIDER).strip().lower()
    spec = PROVIDERS.get(provider_id)
    if spec is None:
        return ""

    env_key = os.environ.get(spec.env_var, "").strip()
    if env_key:
        return env_key

    return _read_saved_api_keys().get(provider_id, "").strip()


def load_api_keys() -> dict[str, str]:
    return {
        provider_id: load_api_key(provider_id)
        for provider_id in PROVIDERS
    }


def save_api_key(api_key: str, provider_id: str = DEFAULT_PROVIDER) -> None:
    provider_id = (provider_id or DEFAULT_PROVIDER).strip().lower()
    if provider_id not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_id}")

    ensure_dirs()
    saved = _read_saved_api_keys()
    value = (api_key or "").strip()
    if value:
        saved[provider_id] = value
    else:
        saved.pop(provider_id, None)

    API_KEYS_FILE.write_text(
        json.dumps(saved, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Keep legacy Gemini file synchronized for a smooth rollback path.
    if provider_id == "gemini":
        try:
            API_KEY_FILE.write_text(value, encoding="utf-8")
        except OSError:
            pass
