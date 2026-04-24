from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from gcli.cli import app, build_search_query

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
    init_mock = mocker.patch("gcli.cli.initialize_token", return_value=tmp_path / "credentials/token.json")
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

