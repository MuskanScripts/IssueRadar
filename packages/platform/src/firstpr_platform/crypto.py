"""Encrypting GitHub tokens at rest.

Fernet keys come from FIRSTPR_TOKEN_KEYS (comma-separated, newest first). New
tokens are encrypted with the first key; any listed key can decrypt, which is
how keys are rotated. In production the keys come from the host's secret store.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet


class TokenBox:
    def __init__(self, keys: str) -> None:
        parts = [k.strip() for k in keys.split(",") if k.strip()]
        if not parts:
            raise ValueError("FIRSTPR_TOKEN_KEYS is empty")
        self._fernet = MultiFernet([Fernet(k.encode()) for k in parts])

    def seal(self, token: str) -> bytes:
        return self._fernet.encrypt(token.encode())

    def open(self, sealed: bytes) -> str:
        return self._fernet.decrypt(sealed).decode()

    @staticmethod
    def new_key() -> str:
        return Fernet.generate_key().decode()
