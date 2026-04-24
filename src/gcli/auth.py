from __future__ import annotations

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from gcli.config import ensure_secure_directory, secure_write_json

SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
)


def _secrets_path(credentials_dir: Path) -> Path:
    return credentials_dir / "secrets.json"


def _token_path(credentials_dir: Path) -> Path:
    return credentials_dir / "token.json"


def initialize_token(credentials_dir: Path) -> Path:
    ensure_secure_directory(credentials_dir)
    secrets_path = _secrets_path(credentials_dir)
    if not secrets_path.exists():
        raise FileNotFoundError(f"Missing OAuth client file: {secrets_path}")

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), scopes=list(SCOPES))
    creds = flow.run_local_server(port=0, open_browser=True)
    secure_write_json(_token_path(credentials_dir), json.loads(creds.to_json()))
    return _token_path(credentials_dir)


def load_credentials(credentials_dir: Path) -> Credentials:
    ensure_secure_directory(credentials_dir)
    token_path = _token_path(credentials_dir)
    if not token_path.exists():
        raise FileNotFoundError(f"Missing token file: {token_path}. Run `gcli init` first.")

    creds = Credentials.from_authorized_user_file(str(token_path), list(SCOPES))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        secure_write_json(token_path, json.loads(creds.to_json()))

    if not creds.valid:
        raise RuntimeError("Invalid credentials. Run `gcli init` again.")

    return creds

