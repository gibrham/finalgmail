from __future__ import annotations

from gcli.cache import load_cache, resolve_latest_cache, write_cache


def test_cache_round_trip(tmp_path) -> None:
    cache_path = write_cache(
        command="search",
        args={"terms": ["invoice"]},
        entries=[{"id": "1"}, {"id": "2"}],
        base_dir=tmp_path,
        timestamp="20260101T000000Z",
    )

    payload = load_cache(cache_path)
    assert payload.metadata.command == "search"
    assert payload.metadata.timestamp == "20260101T000000Z"
    assert payload.metadata.args == {"terms": ["invoice"]}
    assert payload.metadata.run_id is None
    assert payload.entries == [{"id": "1"}, {"id": "2"}]


def test_resolve_latest_cache_uses_newest_timestamp(tmp_path) -> None:
    write_cache(
        command="search",
        args={},
        entries=[],
        base_dir=tmp_path,
        timestamp="20260101T000000Z",
    )
    expected = write_cache(
        command="search",
        args={},
        entries=[],
        base_dir=tmp_path,
        timestamp="20260101T010000Z",
    )

    latest = resolve_latest_cache("search", base_dir=tmp_path)
    assert latest == expected


def test_resolve_latest_cache_filters_by_run_id(tmp_path) -> None:
    baseline = write_cache(
        command="search",
        args={},
        entries=[{"id": "base"}],
        base_dir=tmp_path,
        timestamp="20260101T000000Z",
    )
    pipeline_cache = write_cache(
        command="search",
        args={},
        entries=[{"id": "run"}],
        base_dir=tmp_path,
        timestamp="20260101T010000Z",
        run_id="run-1",
    )

    assert resolve_latest_cache("search", base_dir=tmp_path) == baseline
    assert resolve_latest_cache("search", base_dir=tmp_path, run_id="run-1") == pipeline_cache
