from unittest.mock import Mock

import pytest

from bili_notes.credentials import Credentials


def test_session_overrides_environment_and_is_not_persisted(monkeypatch):
    import keyring

    save = Mock()
    monkeypatch.setattr(keyring, "set_password", save)
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    credentials = Credentials()
    assert credentials.get() == "env-key"
    credentials.set("session-key")
    assert credentials.get() == "session-key"
    save.assert_not_called()


def test_plaintext_backend_cannot_save_key(monkeypatch):
    import keyring

    monkeypatch.setattr(keyring, "get_keyring", lambda: object())
    credentials = Credentials()
    with pytest.raises(RuntimeError, match="系统凭据库"):
        credentials.set("test-only", remember=True)
    assert credentials.session == ""
