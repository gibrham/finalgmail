from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from gcli.cache import CacheMetadata, CachePayload
from gcli.cli import app, build_search_query
from gcli.gmail import SearchResult

runner = CliRunner()


def test_build_search_query_with_filters() -> None:
    query = build_search_query(
        terms=["invoice", "april"],
        sender="sender@example.com",
        recipient="to@example.com",
        subject="Payment",
        has_words="has:attachment",
        label="Finance",
        after="2026/01/01",
        before="2026/02/01",
    )
    assert query == (
        "invoice april from:sender@example.com to:to@example.com subject:Payment "
        "has:attachment label:Finance after:2026/01/01 before:2026/02/01"
    )


def test_init_command_uses_default_credentials_dir(mocker, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    init_mock = mocker.patch(
        "gcli.cli.initialize_token",
        return_value=tmp_path / "credentials/token.json",
    )
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    init_mock.assert_called_once_with(tmp_path / "credentials")


def test_search_requires_query() -> None:
    result = runner.invoke(app, ["search"])
    assert result.exit_code != 0
    assert "Provide at least one term or filter." in result.output


def test_create_tag_calls_nested_creation(mocker, tmp_path: Path) -> None:
    fake_client = mocker.Mock()
    fake_client.ensure_nested_label.return_value = ["Parent", "Parent/Child"]
    mocker.patch("gcli.cli.GmailClient.from_credentials_dir", return_value=fake_client)
    result = runner.invoke(
        app,
        ["tag", "create", "Parent/Child", "--credentials-dir", str(tmp_path / "credentials")],
    )
    assert result.exit_code == 0
    fake_client.ensure_nested_label.assert_called_once_with("Parent/Child")


def test_search_cache_option_writes_cache(mocker, tmp_path: Path) -> None:
    fake_client = mocker.Mock()
    fake_client.search_messages.return_value = SearchResult(
        messages=[
            {
                "id": "msg-1",
                "from": "alice@example.com",
                "to": "bob@example.com",
                "cc": "",
                "bcc": "",
                "subject": "Hello",
                "date": "Mon, 01 Jan 2026 10:00:00 +0000",
                "snippet": "Contact us at support@example.com",
                "body": "Contact us at support@example.com",
            }
        ],
        pages=1,
    )
    mocker.patch("gcli.cli.GmailClient.from_credentials_dir", return_value=fake_client)
    write_cache_mock = mocker.patch(
        "gcli.cli.write_cache",
        return_value=tmp_path / ".cache/search_1.jsonl",
    )

    result = runner.invoke(app, ["search", "invoice", "--cache"])
    assert result.exit_code == 0
    write_cache_mock.assert_called_once()
    assert write_cache_mock.call_args.kwargs["command"] == "search"


def test_tools_exall_uses_default_search_cache(mocker, tmp_path: Path) -> None:
    payload = CachePayload(
        metadata=CacheMetadata(command="search", timestamp="20260101T000000Z", args={}),
        entries=[
            {
                "id": "msg-1",
                "from": "Alice <alice@example.com>",
                "to": "bob@example.com",
                "cc": "",
                "bcc": "",
                "body": "Loop in carol@example.com",
                "date": "Mon, 01 Jan 2026 10:00:00 +0000",
            }
        ],
        path=tmp_path / ".cache/search_20260101T000000Z.jsonl",
    )
    load_mock = mocker.patch("gcli.tools.exall.load_latest_cache", return_value=payload)

    result = runner.invoke(app, ["tools", "exall"])
    assert result.exit_code == 0
    load_mock.assert_called_once_with("search", run_id=None)
    assert "SENT_TO" in result.output
    assert "MENTIONS" in result.output


def test_tools_exall_respects_from_cache_override(mocker, tmp_path: Path) -> None:
    payload = CachePayload(
        metadata=CacheMetadata(command="search", timestamp="20260101T000000Z", args={}),
        entries=[],
        path=tmp_path / ".cache/search_20260101T000000Z.jsonl",
    )
    load_mock = mocker.patch("gcli.tools.exall.load_latest_cache", return_value=payload)

    result = runner.invoke(app, ["tools", "exall", "--from-cache", "custom_search"])
    assert result.exit_code == 0
    load_mock.assert_called_once_with("custom_search", run_id=None)


def test_tools_visualize_writes_html(mocker, tmp_path: Path) -> None:
    payload = CachePayload(
        metadata=CacheMetadata(command="exall", timestamp="20260101T000000Z", args={}),
        entries=[
            {
                "nodes": [{"type": "EmailAddress", "email": "alice@example.com"}],
                "edges": [
                    {
                        "type": "SENT_TO",
                        "from": "alice@example.com",
                        "to": "bob@example.com",
                        "frequency": 2,
                    }
                ],
            }
        ],
        path=tmp_path / ".cache/exall_20260101T000000Z.jsonl",
    )
    load_mock = mocker.patch("gcli.tools.visualize.load_latest_cache", return_value=payload)
    output_path = tmp_path / "graph.html"

    result = runner.invoke(app, ["tools", "visualize", "--output", str(output_path)])
    assert result.exit_code == 0
    load_mock.assert_called_once_with("exall", run_id=None)
    html = output_path.read_text(encoding="utf-8")
    assert "cytoscape" in html
    assert "alice@example.com" in html


def test_non_interactive_visualize_fails_without_cache_and_never_prompts(
    mocker, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    prompt_mock = mocker.patch("typer.prompt", side_effect=AssertionError("prompt should not run"))
    result = runner.invoke(app, ["tools", "visualize"])
    assert result.exit_code != 0
    prompt_mock.assert_not_called()


def test_search_match_all_passes_flag_to_client(mocker, tmp_path: Path) -> None:
    fake_client = mocker.Mock()
    fake_client.search_messages.return_value = SearchResult(messages=[], pages=1)
    mocker.patch("gcli.cli.GmailClient.from_credentials_dir", return_value=fake_client)

    result = runner.invoke(app, ["search", "invoice", "--match-all"])
    assert result.exit_code == 0
    fake_client.search_messages.assert_called_once()
    _, kwargs = fake_client.search_messages.call_args
    assert kwargs.get("match_all") is True


def test_search_without_match_all_uses_default_max_results(mocker, tmp_path: Path) -> None:
    fake_client = mocker.Mock()
    fake_client.search_messages.return_value = SearchResult(messages=[], pages=1)
    mocker.patch("gcli.cli.GmailClient.from_credentials_dir", return_value=fake_client)

    result = runner.invoke(app, ["search", "invoice"])
    assert result.exit_code == 0
    fake_client.search_messages.assert_called_once()
    _, kwargs = fake_client.search_messages.call_args
    assert kwargs.get("match_all") is False


def test_non_interactive_exall_fails_without_cache_and_never_prompts(
    mocker, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    prompt_mock = mocker.patch("typer.prompt", side_effect=AssertionError("prompt should not run"))
    result = runner.invoke(app, ["tools", "exall"])
    assert result.exit_code != 0
    prompt_mock.assert_not_called()
