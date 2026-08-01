import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class DataCipher:
    """Application-level encryption for prompts, results, and A2A messages."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode())

    def decrypt(self, value: bytes) -> str:
        try:
            return self._fernet.decrypt(value).decode()
        except InvalidToken as exc:
            raise ValueError("Encrypted AI data could not be authenticated") from exc

    def encrypt_json(self, value: Any) -> bytes:
        return self.encrypt(json.dumps(value, separators=(",", ":"), default=str))

    def decrypt_json(self, value: bytes) -> Any:
        return json.loads(self.decrypt(value))

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()
