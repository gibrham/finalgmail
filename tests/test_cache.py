from __future__ import annotations

from gcli.cache import (
    build_artifact_id,
    load_artifact,
    load_artifact_reference,
    write_artifact,
)


def test_artifact_round_trip(tmp_path) -> None:
    artifact_path = write_artifact(
        command="search",
        artifact_id="search_01JTEST000000000000000000",
        args={"terms": ["invoice"]},
        entries=[{"id": "1"}, {"id": "2"}],
        base_dir=tmp_path,
    )

    payload = load_artifact(artifact_path)
    assert payload.metadata.command == "search"
    assert payload.metadata.artifact_id == "search_01JTEST000000000000000000"
    assert payload.metadata.ulid == "01JTEST000000000000000000"
    assert payload.metadata.args == {"terms": ["invoice"]}
    assert payload.entries == [{"id": "1"}, {"id": "2"}]


def test_build_artifact_id_uses_command_prefix() -> None:
    artifact_id = build_artifact_id("gcli tools exall", ulid="01JULID000000000000000000")
    assert artifact_id == "gcli_tools_exall_01JULID000000000000000000"


def test_load_artifact_reference_supports_id_lookup(tmp_path) -> None:
    write_artifact(
        command="search",
        artifact_id="search_01JAAA000000000000000000",
        args={},
        entries=[{"id": "base"}],
        base_dir=tmp_path,
    )

    payload = load_artifact_reference("search_01JAAA000000000000000000", base_dir=tmp_path)
    assert payload.entries == [{"id": "base"}]
