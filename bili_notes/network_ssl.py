"""TLS setup for Windows machines with an unreadable certificate store."""

from __future__ import annotations

import ssl


_configured = False


def configure_default_ssl_context() -> None:
    """Fall back to certifi only when Python cannot load the system CA store."""
    global _configured
    if _configured:
        return

    try:
        ssl.create_default_context()
    except ssl.SSLError:
        import certifi

        original = ssl.create_default_context
        default_cafile = certifi.where()

        def create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            *,
            cafile=None,
            capath=None,
            cadata=None,
        ):
            if cafile is None and capath is None and cadata is None:
                cafile = default_cafile
            return original(
                purpose=purpose,
                cafile=cafile,
                capath=capath,
                cadata=cadata,
            )

        ssl.create_default_context = create_default_context

    _configured = True
