from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARTIFACT_DIRNAME = ".artifacts"
META_TYPE = "meta"
DATA_TYPE = "data"
_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@dataclass
class ArtifactMetadata:
    command: str
    artifact_id: str
    ulid: str
    args: dict[str, Any]


@dataclass
class ArtifactPayload:
    metadata: ArtifactMetadata
    entries: list[dict[str, Any]]
    path: Path


def _normalize_command_name(command: str) -> str:
    return command.strip().replace(" ", "_").replace("/", "_")


def _artifact_dir(base_dir: Path | None = None) -> Path:
    return (base_dir or Path.cwd()) / ARTIFACT_DIRNAME


def _encode_crockford(value: int, length: int) -> str:
    chars = ["0"] * length
    for idx in range(length - 1, -1, -1):
        chars[idx] = _ULID_ALPHABET[value & 0b11111]
        value >>= 5
    return "".join(chars)


def generate_ulid() -> str:
    timestamp_ms = int(time.time() * 1000)
    if timestamp_ms >= (1 << 48):
        raise ValueError("ULID timestamp out of range")
    timestamp_part = _encode_crockford(timestamp_ms, 10)
    random_part = _encode_crockford(int.from_bytes(secrets.token_bytes(10), "big"), 16)
    return f"{timestamp_part}{random_part}"


def build_artifact_id(command: str, *, ulid: str | None = None) -> str:
    command_name = _normalize_command_name(command)
    return f"{command_name}_{ulid or generate_ulid()}"


def artifact_path(artifact_id: str, *, base_dir: Path | None = None) -> Path:
    return _artifact_dir(base_dir) / f"{artifact_id}.jsonl"


def resolve_artifact_path(reference: str, *, base_dir: Path | None = None) -> Path:
    path = Path(reference)
    if path.exists():
        return path
    return artifact_path(reference, base_dir=base_dir)


def write_artifact(
    command: str,
    args: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    artifact_id: str | None = None,
    base_dir: Path | None = None,
) -> Path:
    command_name = _normalize_command_name(command)
    output_artifact_id = artifact_id or build_artifact_id(command_name)
    prefix = f"{command_name}_"
    if not output_artifact_id.startswith(prefix):
        message = (
            f"artifact_id '{output_artifact_id}' must start with '{prefix}' "
            f"for command '{command_name}'."
        )
        raise ValueError(
            message
        )
    ulid = output_artifact_id[len(prefix) :]

    out_dir = _artifact_dir(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = artifact_path(output_artifact_id, base_dir=base_dir)

    metadata = ArtifactMetadata(
        command=command_name,
        artifact_id=output_artifact_id,
        ulid=ulid,
        args=args,
    )
    with out_path.open("w", encoding="utf-8") as output_file:
        output_file.write(
            json.dumps(
                {
                    "record_type": META_TYPE,
                    "metadata": {
                        "command": metadata.command,
                        "artifact_id": metadata.artifact_id,
                        "ulid": metadata.ulid,
                        "args": metadata.args,
                    },
                }
            )
            + "\n"
        )
        for entry in entries:
            output_file.write(json.dumps({"record_type": DATA_TYPE, "entry": entry}) + "\n")
    return out_path


def load_artifact(output_path: Path) -> ArtifactPayload:
    metadata: ArtifactMetadata | None = None
    entries: list[dict[str, Any]] = []

    with output_path.open("r", encoding="utf-8") as artifact_file:
        for line in artifact_file:
            record = json.loads(line)
            record_type = record.get("record_type")
            if record_type == META_TYPE:
                meta = record.get("metadata", {})
                metadata = ArtifactMetadata(
                    command=meta.get("command", ""),
                    artifact_id=meta.get("artifact_id", ""),
                    ulid=meta.get("ulid", ""),
                    args=meta.get("args", {}),
                )
            elif record_type == DATA_TYPE:
                entry = record.get("entry")
                if isinstance(entry, dict):
                    entries.append(entry)

    if metadata is None:
        raise ValueError(f"Artifact file is missing metadata: {output_path}")
    return ArtifactPayload(metadata=metadata, entries=entries, path=output_path)


def load_artifact_reference(reference: str, *, base_dir: Path | None = None) -> ArtifactPayload:
    resolved = resolve_artifact_path(reference, base_dir=base_dir)
    if not resolved.exists():
        raise FileNotFoundError(f"Artifact not found: {reference}")
    return load_artifact(resolved)
