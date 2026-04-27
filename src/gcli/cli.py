from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from gcli.auth import initialize_token
from gcli.cache import write_cache
from gcli.command_meta import CommandInput, CommandSpec, command_contract, get_command_spec
from gcli.config import default_credentials_dir
from gcli.gmail import GmailClient
from gcli.pipeline import (
    PipelineCommand,
    load_pipeline,
    parse_input_overrides,
    run_pipeline,
)
from gcli.tools import app as tools_app
from gcli.tools.exall import exall_command
from gcli.tools.visualize import visualize_command

app = typer.Typer(help="Gmail CLI")
tag_app = typer.Typer(help="Tag operations")
app.add_typer(tag_app, name="tag")
app.add_typer(tools_app, name="tools")
console = Console()

SEARCH_COMMAND_SPEC = CommandSpec(
    command="gcli search",
    interactive=True,
    inputs=(
        CommandInput(
            name="terms",
            required=True,
            source="user",
            prompt="Search terms (required)",
        ),
        CommandInput(
            name="sender",
            required=False,
            source="user",
            prompt="Sender filter (--from)",
        ),
        CommandInput(
            name="recipient",
            required=False,
            source="user",
            prompt="Recipient filter (--to)",
        ),
        CommandInput(name="subject", required=False, source="user", prompt="Subject filter"),
        CommandInput(
            name="has_words",
            required=False,
            source="user",
            prompt="Extra Gmail query terms",
        ),
        CommandInput(name="label", required=False, source="user", prompt="Label filter"),
        CommandInput(name="after", required=False, source="user", prompt="After date (YYYY/MM/DD)"),
        CommandInput(
            name="before",
            required=False,
            source="user",
            prompt="Before date (YYYY/MM/DD)",
        ),
        CommandInput(name="max_results", required=False, source="default"),
        CommandInput(name="credentials_dir", required=False, source="default"),
        CommandInput(name="cache_output", required=False, source="default"),
        CommandInput(name="cache_run_id", required=False, source="cache"),
    ),
    outputs=("search_cache",),
)


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
@command_contract(SEARCH_COMMAND_SPEC)
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
    cache_run_id: Annotated[
        str | None,
        typer.Option("--cache-run-id", help="Pipeline cache run identifier", hidden=True),
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
            run_id=cache_run_id,
        )
        console.print(f"[green]Saved cache:[/green] {cache_path}")


def _execute_search_step(step_inputs: dict[str, str | None], run_id: str) -> None:
    terms_raw = (step_inputs.get("terms") or "").strip()
    terms = terms_raw.split() if terms_raw else []
    max_results_raw = (step_inputs.get("max_results") or "").strip()
    max_results = int(max_results_raw) if max_results_raw else 25
    credentials_dir_raw = (step_inputs.get("credentials_dir") or "").strip()
    credentials_dir = Path(credentials_dir_raw) if credentials_dir_raw else None
    search_command(
        terms=terms,
        sender=step_inputs.get("sender"),
        recipient=step_inputs.get("recipient"),
        subject=step_inputs.get("subject"),
        has_words=step_inputs.get("has_words"),
        label=step_inputs.get("label"),
        after=step_inputs.get("after"),
        before=step_inputs.get("before"),
        max_results=max_results,
        cache_output=True,
        credentials_dir=credentials_dir,
        cache_run_id=run_id,
    )


def _execute_exall_step(step_inputs: dict[str, str | None], run_id: str) -> None:
    exall_command(
        from_cache=step_inputs.get("from_cache") or "search",
        cache_output=True,
        cache_run_id=run_id,
    )


def _execute_visualize_step(step_inputs: dict[str, str | None], run_id: str) -> None:
    output_raw = (step_inputs.get("output") or "").strip()
    output = Path(output_raw) if output_raw else Path("graph.html")
    visualize_command(
        from_cache=step_inputs.get("from_cache") or "exall",
        output=output,
        cache_run_id=run_id,
    )


def _pipeline_registry() -> dict[str, PipelineCommand]:
    return {
        "gcli search": PipelineCommand(
            spec=get_command_spec(search_command),
            execute=_execute_search_step,
        ),
        "gcli tools exall": PipelineCommand(
            spec=get_command_spec(exall_command),
            execute=_execute_exall_step,
        ),
        "gcli tools visualize": PipelineCommand(
            spec=get_command_spec(visualize_command),
            execute=_execute_visualize_step,
        ),
    }


@app.command("run")
def run_command(
    pipeline_name: Annotated[str, typer.Argument(help="Pipeline name")],
    from_step: Annotated[str | None, typer.Option("--from", help="Start from step id")] = None,
    until_step: Annotated[str | None, typer.Option("--until", help="Stop after step id")] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Show detailed execution logs")
    ] = False,
    iext: Annotated[
        bool,
        typer.Option("--iext", help="Interactive extended mode (prompt optional user inputs)"),
    ] = False,
    inputs: Annotated[
        list[str] | None,
        typer.Option("--input", "-i", help="Provide upfront input values as key=value"),
    ] = None,
) -> None:
    pipeline = load_pipeline(pipeline_name)
    provided_inputs = parse_input_overrides(inputs or [])
    run_pipeline(
        pipeline=pipeline,
        registry=_pipeline_registry(),
        from_step=from_step,
        until_step=until_step,
        verbose=verbose,
        iext=iext,
        provided_inputs=provided_inputs,
        prompt_func=typer.prompt,
        console=console,
    )


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
