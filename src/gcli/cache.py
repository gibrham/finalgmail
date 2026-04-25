from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CACHE_DIRNAME = ".cache"
META_TYPE = "meta"
DATA_TYPE = "data"


@dataclass
class CacheMetadata:
    command: str
    timestamp: str
    args: dict[str, Any]


@dataclass
class CachePayload:
    metadata: CacheMetadata
    entries: list[dict[str, Any]]
    path: Path


def _normalize_command_name(command: str) -> str:
    return command.strip().replace(" ", "_").replace("/", "_")


def _cache_dir(base_dir: Path | None = None) -> Path:
    return (base_dir or Path.cwd()) / CACHE_DIRNAME


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_cache(
    command: str,
    args: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    base_dir: Path | None = None,
    timestamp: str | None = None,
) -> Path:
    command_name = _normalize_command_name(command)
    cache_dir = _cache_dir(base_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_timestamp = timestamp or _current_timestamp()
    cache_path = cache_dir / f"{command_name}_{cache_timestamp}.jsonl"

    metadata = CacheMetadata(command=command_name, timestamp=cache_timestamp, args=args)
    with cache_path.open("w", encoding="utf-8") as cache_file:
        cache_file.write(
            json.dumps(
                {
                    "record_type": META_TYPE,
                    "metadata": {
                        "command": metadata.command,
                        "timestamp": metadata.timestamp,
                        "args": metadata.args,
                    },
                }
            )
            + "\n"
        )
        for entry in entries:
            cache_file.write(json.dumps({"record_type": DATA_TYPE, "entry": entry}) + "\n")
    return cache_path


def load_cache(cache_path: Path) -> CachePayload:
    metadata: CacheMetadata | None = None
    entries: list[dict[str, Any]] = []

    with cache_path.open("r", encoding="utf-8") as cache_file:
        for line in cache_file:
            record = json.loads(line)
            record_type = record.get("record_type")
            if record_type == META_TYPE:
                meta = record.get("metadata", {})
                metadata = CacheMetadata(
                    command=meta.get("command", ""),
                    timestamp=meta.get("timestamp", ""),
                    args=meta.get("args", {}),
                )
            elif record_type == DATA_TYPE:
                entry = record.get("entry")
                if isinstance(entry, dict):
                    entries.append(entry)

    if metadata is None:
        raise ValueError(f"Cache file is missing metadata: {cache_path}")
    return CachePayload(metadata=metadata, entries=entries, path=cache_path)


def resolve_latest_cache(command: str, *, base_dir: Path | None = None) -> Path | None:
    command_name = _normalize_command_name(command)
    cache_dir = _cache_dir(base_dir)
    if not cache_dir.exists():
        return None
    matches = sorted(cache_dir.glob(f"{command_name}_*.jsonl"))
    if not matches:
        return None
    return matches[-1]


def load_latest_cache(command: str, *, base_dir: Path | None = None) -> CachePayload:
    latest = resolve_latest_cache(command, base_dir=base_dir)
    if latest is None:
        raise FileNotFoundError(f"No cache file found for command '{command}'.")
    return load_cache(latest)
