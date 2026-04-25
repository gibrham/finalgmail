from __future__ import annotations

import re
from collections import defaultdict
from email.utils import getaddresses
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from gcli.cache import load_latest_cache, write_cache

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

console = Console()


def _parse_header_emails(value: str | None) -> set[str]:
    if not value:
        return set()
    return {address.lower() for _, address in getaddresses([value]) if address}


def _extract_body_emails(content: str | None) -> set[str]:
    if not content:
        return set()
    return {match.lower() for match in EMAIL_PATTERN.findall(content)}


def _resolve_message_content(message: dict[str, Any]) -> tuple[str, str]:
    body = (message.get("body") or "").strip()
    if body:
        return body, "body"
    snippet = (message.get("snippet") or "").strip()
    if snippet:
        return snippet, "snippet"
    return "", "none"


def build_email_graph(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Build EmailAddress nodes and SENT_TO/MENTIONS edges from message dictionaries."""
    nodes: set[str] = set()
    edge_map: dict[tuple[str, str, str], dict[str, Any]] = {}

    for message in messages:
        sender_candidates = _parse_header_emails(message.get("from"))
        if not sender_candidates:
            continue
        sender = sorted(sender_candidates)[0]
        nodes.add(sender)

        recipients = set()
        recipients.update(_parse_header_emails(message.get("to")))
        recipients.update(_parse_header_emails(message.get("cc")))
        recipients.update(_parse_header_emails(message.get("bcc")))
        content, content_source = _resolve_message_content(message)
        mentions = _extract_body_emails(content)

        timestamp = message.get("date")
        source_ref = message.get("id") or message.get("threadId")

        for recipient in recipients:
            nodes.add(recipient)
            key = ("SENT_TO", sender, recipient)
            edge = edge_map.setdefault(
                key,
                {
                    "type": "SENT_TO",
                    "from": sender,
                    "to": recipient,
                    "timestamp": timestamp,
                    "timestamps": [],
                    "source_references": [],
                    "frequency": 0,
                },
            )
            edge["frequency"] += 1
            if timestamp and timestamp not in edge["timestamps"]:
                edge["timestamps"].append(timestamp)
            if source_ref and source_ref not in edge["source_references"]:
                edge["source_references"].append(source_ref)
            if not edge.get("timestamp") and timestamp:
                edge["timestamp"] = timestamp

        for mentioned in mentions:
            if mentioned == sender:
                continue
            nodes.add(mentioned)
            key = ("MENTIONS", sender, mentioned)
            edge = edge_map.setdefault(
                key,
                {
                    "type": "MENTIONS",
                    "from": sender,
                    "to": mentioned,
                    "timestamp": timestamp,
                    "timestamps": [],
                    "source_references": [],
                    "content_sources": [],
                    "frequency": 0,
                },
            )
            edge["frequency"] += 1
            if timestamp and timestamp not in edge["timestamps"]:
                edge["timestamps"].append(timestamp)
            if source_ref and source_ref not in edge["source_references"]:
                edge["source_references"].append(source_ref)
            if content_source not in edge["content_sources"]:
                edge["content_sources"].append(content_source)
            if not edge.get("timestamp") and timestamp:
                edge["timestamp"] = timestamp

    nodes_payload = [{"type": "EmailAddress", "email": email} for email in sorted(nodes)]
    edges_payload = sorted(
        edge_map.values(),
        key=lambda edge: (edge["type"], edge["from"], edge["to"]),
    )
    return {"nodes": nodes_payload, "edges": edges_payload}


def _render_edges(edges: list[dict[str, Any]]) -> None:
    table = Table(title=f"Extracted Relationships ({len(edges)})")
    table.add_column("Type")
    table.add_column("From")
    table.add_column("To")
    table.add_column("Frequency", justify="right")
    table.add_column("Sources", justify="right")
    for edge in edges:
        table.add_row(
            edge["type"],
            edge["from"],
            edge["to"],
            str(edge["frequency"]),
            str(len(edge["source_references"])),
        )
    console.print(table)


def _render_summary(edges: list[dict[str, Any]]) -> None:
    by_type: dict[str, int] = defaultdict(int)
    for edge in edges:
        by_type[edge["type"]] += edge["frequency"]
    summary = ", ".join(f"{edge_type}={count}" for edge_type, count in sorted(by_type.items()))
    console.print(f"[green]Relationship totals:[/green] {summary}")


def exall_command(
    from_cache: Annotated[
        str | None,
        typer.Option("--from-cache", help="Load latest cache from a specific command"),
    ] = None,
    cache_output: Annotated[bool, typer.Option("--cache", help="Save output to cache")] = False,
) -> None:
    """Extract relationship edges from cached search data and render/save the graph payload."""
    source_command = from_cache or "search"
    try:
        payload = load_latest_cache(source_command)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    graph = build_email_graph(payload.entries)
    edges = graph["edges"]
    if not edges:
        console.print("[yellow]No relationships found in cache.[/yellow]")
        return

    _render_edges(edges)
    _render_summary(edges)
    if cache_output:
        cache_path = write_cache(
            command="exall",
            args={"from_cache": source_command, "source_cache_file": payload.path.name},
            entries=[graph],
        )
        console.print(f"[green]Saved cache:[/green] {cache_path}")
