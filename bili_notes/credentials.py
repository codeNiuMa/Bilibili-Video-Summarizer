import os

SERVICE = "bili-notes"
ACCOUNT = "gemini-api-key"


class Credentials:
    def __init__(self):
        self.session = ""

    def get(self):
        if self.session:
            return self.session
        if key := os.environ.get("GEMINI_API_KEY"):
            return key.strip()
        try:
            import keyring

            return keyring.get_password(SERVICE, ACCOUNT) or ""
        except Exception:
            return ""

    def set(self, value, remember=False):
        if remember:
            import keyring

            # Only OS credential stores; never accept an installed plaintext backend.
            backend = keyring.get_keyring()
            module = type(backend).__module__
            if module not in {
                "keyring.backends.Windows",
                "keyring.backends.macOS",
                "keyring.backends.SecretService",
                "keyring.backends.kwallet",
            }:
                raise RuntimeError("没有可用的系统凭据库，请取消“记住密钥”，仅在本次会话使用。")
            keyring.set_password(SERVICE, ACCOUNT, value)
        self.session = value

    def forget(self):
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(SERVICE, ACCOUNT)
        except PasswordDeleteError:
            pass
        self.session = ""
