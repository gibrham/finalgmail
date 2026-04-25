from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from gcli.auth import initialize_token
from gcli.cache import write_cache
from gcli.config import default_credentials_dir
from gcli.gmail import GmailClient
from gcli.tools import app as tools_app

app = typer.Typer(help="Gmail CLI")
tag_app = typer.Typer(help="Tag operations")
app.add_typer(tag_app, name="tag")
app.add_typer(tools_app, name="tools")
console = Console()


def _resolve_credentials_dir(credentials_dir: Path | None) -> Path:
    return credentials_dir or default_credentials_dir()


def _validate_label_name(value: str) -> str:
    if not value.strip():
        raise typer.BadParameter("Label name cannot be empty.")
    if value.startswith("/") or value.endswith("/") or "//" in value:
        raise typer.BadParameter("Nested labels must use non-empty segments (e.g. Parent/Child).")
    return value


def build_search_query(
    terms: list[str],
    sender: str | None,
    recipient: str | None,
    subject: str | None,
    has_words: str | None,
    label: str | None,
    after: str | None,
    before: str | None,
) -> str:
    query_parts = [term for term in terms if term.strip()]
    if sender:
        query_parts.append(f"from:{sender}")
    if recipient:
        query_parts.append(f"to:{recipient}")
    if subject:
        query_parts.append(f"subject:{subject}")
    if has_words:
        query_parts.append(has_words)
    if label:
        query_parts.append(f"label:{label}")
    if after:
        query_parts.append(f"after:{after}")
    if before:
        query_parts.append(f"before:{before}")
    return " ".join(query_parts).strip()


@app.command("init")
def init_command(
    credentials_dir: Annotated[
        Path | None,
        typer.Option(help="Credentials directory containing secrets.json and token.json"),
    ] = None,
) -> None:
    token_path = initialize_token(_resolve_credentials_dir(credentials_dir))
    console.print(f"[green]Token saved:[/green] {token_path}")


@app.command("search")
def search_command(
    terms: Annotated[list[str] | None, typer.Argument(help="Search terms")] = None,
    sender: Annotated[str | None, typer.Option("--from", help="Filter by sender")] = None,
    recipient: Annotated[str | None, typer.Option("--to", help="Filter by recipient")] = None,
    subject: Annotated[str | None, typer.Option(help="Filter by subject")] = None,
    has_words: Annotated[str | None, typer.Option(help="Additional raw Gmail query terms")] = None,
    label: Annotated[str | None, typer.Option(help="Filter by label")] = None,
    after: Annotated[str | None, typer.Option(help="After date (YYYY/MM/DD)")] = None,
    before: Annotated[str | None, typer.Option(help="Before date (YYYY/MM/DD)")] = None,
    max_results: Annotated[int, typer.Option(min=1, max=500)] = 25,
    cache_output: Annotated[bool, typer.Option("--cache", help="Save output to cache")] = False,
    credentials_dir: Annotated[
        Path | None,
        typer.Option(help="Credentials directory containing secrets.json and token.json"),
    ] = None,
) -> None:
    query = build_search_query(
        terms or [],
        sender,
        recipient,
        subject,
        has_words,
        label,
        after,
        before,
    )
    if not query:
        raise typer.BadParameter("Provide at least one term or filter.")

    client = GmailClient.from_credentials_dir(_resolve_credentials_dir(credentials_dir))
    messages = client.search_messages(query=query, max_results=max_results)
    if not messages:
        console.print("[yellow]No emails found.[/yellow]")
        return

    table = Table(title=f"Search Results ({len(messages)})")
    table.add_column("#", justify="right")
    table.add_column("From")
    table.add_column("Subject")
    table.add_column("Date")
    table.add_column("Snippet")
    for index, message in enumerate(messages, start=1):
        table.add_row(
            str(index),
            message["from"],
            message["subject"],
            message["date"],
            message["snippet"],
        )
    console.print(table)
    if cache_output:
        cache_path = write_cache(
            command="search",
            args={
                "terms": terms or [],
                "from": sender,
                "to": recipient,
                "subject": subject,
                "has_words": has_words,
                "label": label,
                "after": after,
                "before": before,
                "max_results": max_results,
            },
            entries=messages,
        )
        console.print(f"[green]Saved cache:[/green] {cache_path}")


@tag_app.command("create")
def create_tag_command(
    name: Annotated[str, typer.Argument(callback=_validate_label_name, help="Label name")],
    credentials_dir: Annotated[
        Path | None,
        typer.Option(help="Credentials directory containing secrets.json and token.json"),
    ] = None,
) -> None:
    client = GmailClient.from_credentials_dir(_resolve_credentials_dir(credentials_dir))
    created = client.ensure_nested_label(name)
    if not created:
        console.print(f"[yellow]Tag already exists:[/yellow] {name}")
        return
    console.print("[green]Created tags:[/green] " + ", ".join(created))


def run() -> None:
    app()


if __name__ == "__main__":
    run()
