#!/usr/bin/env python3
"""
create_linkedin_credentials.py

Helper script to generate an encrypted LinkedIn credentials file for
linkedin_job_matcher.py.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def derive_key(passphrase: str, salt: bytes) -> bytes:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an encrypted LinkedIn credentials file for linkedin_job_matcher.py"
    )
    parser.add_argument("--credentials-file", required=True, help="Path to write the encrypted credentials file.")
    parser.add_argument("--linkedin-email", help="LinkedIn login email.")
    parser.add_argument("--linkedin-password", help="LinkedIn login password.")
    parser.add_argument("--credentials-passphrase", help="Passphrase used to encrypt the credentials.")
    args = parser.parse_args()

    email = args.linkedin_email or input("LinkedIn email: ").strip()
    password = args.linkedin_password or getpass.getpass("LinkedIn password: ")
    passphrase = args.credentials_passphrase or getpass.getpass("Credentials passphrase: ")

    if not email or not password or not passphrase:
        raise SystemExit("LinkedIn email, password, and credentials passphrase are all required.")

    create_encrypted_credentials(
        Path(args.credentials_file),
        email,
        password,
        passphrase,
    )
    print(f"Encrypted credentials file created at {args.credentials_file}")


if __name__ == "__main__":
    main()
