from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def default_credentials_dir() -> Path:
    return Path.cwd() / "credentials"


def ensure_secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)


def secure_write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_secure_directory(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-token-", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            if os.name != "nt":
                os.fchmod(tmp_file.fileno(), 0o600)
            json.dump(payload, tmp_file, indent=2)
            tmp_file.write("\n")
        os.replace(tmp_name, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink()

