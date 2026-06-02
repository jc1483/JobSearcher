from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Tuple

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    Fernet = None
    InvalidToken = Exception
    hashes = None
    PBKDF2HMAC = None


def ensure_crypto_available() -> None:
    if Fernet is None or PBKDF2HMAC is None or hashes is None:
        raise ImportError(
            "Encrypted credentials require cryptography. "
            "Install it with: pip install cryptography"
        )


def derive_key(passphrase: str, salt: bytes) -> bytes:
    ensure_crypto_available()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def create_encrypted_credentials(credentials_path: Path, email: str, password: str, passphrase: str) -> None:
    salt = os.urandom(16)
    key = derive_key(passphrase, salt)
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    token = Fernet(key).encrypt(payload).decode("utf-8")

    credentials_path.write_text(
        json.dumps(
            {
                "salt": base64.urlsafe_b64encode(salt).decode("utf-8"),
                "token": token,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load_credentials(credentials_path: Path, passphrase: str) -> Tuple[str, str]:
    ensure_crypto_available()
    content = json.loads(credentials_path.read_text(encoding="utf-8"))
    salt = base64.urlsafe_b64decode(content["salt"])
    token = content["token"].encode("utf-8")
    key = derive_key(passphrase, salt)
    try:
        decrypted = Fernet(key).decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt credentials. Check the passphrase and encrypted credentials file.") from exc
    creds = json.loads(decrypted)
    return creds["email"], creds["password"]
