from __future__ import annotations

import json
import re
from collections import defaultdict
from email.utils import getaddresses
from pathlib import Path
from typing import Annotated, Any

import typer
from ladybug import Connection, Database
from rich.console import Console
from rich.table import Table

from gcli.cache import build_artifact_id, generate_ulid, load_artifact_reference, write_artifact
from gcli.command_meta import CommandInput, CommandSpec, command_contract

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


def _escape_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _graph_db_path(base_dir: Path | None = None, *, artifact_id: str | None = None) -> Path:
    artifacts_dir = (base_dir or Path.cwd()) / ".artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    if artifact_id and "_" in artifact_id:
        ulid = artifact_id.rsplit("_", 1)[-1]
    else:
        ulid = generate_ulid()
    return artifacts_dir / f"exall_{ulid}.lbug"


def _materialize_graph_in_ladybug(
    nodes: set[str],
    edges: list[dict[str, Any]],
    *,
    db_path: Path,
) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(str(db_path))
    conn = Connection(db)
    try:
        conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS EmailAddress(email STRING, PRIMARY KEY (email));"
        )
        conn.execute(
            "CREATE REL TABLE IF NOT EXISTS SENT_TO("
            "FROM EmailAddress TO EmailAddress,"
            " timestamp STRING, source_ref STRING, frequency INT64,"
            " source_references STRING, timestamps STRING, content_sources STRING"
            ");"
        )
        conn.execute(
            "CREATE REL TABLE IF NOT EXISTS MENTIONS("
            "FROM EmailAddress TO EmailAddress,"
            " timestamp STRING, source_ref STRING, frequency INT64,"
            " source_references STRING, timestamps STRING, content_sources STRING"
            ");"
        )

        for email in sorted(nodes):
            escaped_email = _escape_query_value(email)
            conn.execute(f"MERGE (:EmailAddress {{email:'{escaped_email}'}})")

        for edge in edges:
            rel_type = edge["type"]
            source = _escape_query_value(edge["from"])
            target = _escape_query_value(edge["to"])
            timestamp = _escape_query_value(edge.get("timestamp") or "")
            source_ref = _escape_query_value((edge.get("source_references") or [""])[0] or "")
            source_references = _escape_query_value(json.dumps(edge.get("source_references") or []))
            timestamps = _escape_query_value(json.dumps(edge.get("timestamps") or []))
            content_sources = _escape_query_value(json.dumps(edge.get("content_sources") or []))
            frequency = int(edge.get("frequency", 0))
            conn.execute(
                "MATCH (a:EmailAddress {email:'"
                + source
                + "'}), (b:EmailAddress {email:'"
                + target
                + "'}) "
                + "MERGE (a)-[r:"
                + rel_type
                + "]->(b) "
                + "SET r.timestamp='"
                + timestamp
                + "', r.source_ref='"
                + source_ref
                + "', r.frequency="
                + str(frequency)
                + ", r.source_references='"
                + source_references
                + "', r.timestamps='"
                + timestamps
                + "', r.content_sources='"
                + content_sources
                + "'"
            )

        node_rows = conn.execute(
            "MATCH (n:EmailAddress) RETURN n.email AS email ORDER BY n.email"
        ).get_all()
        sent_rows = conn.execute(
            "MATCH (a:EmailAddress)-[r:SENT_TO]->(b:EmailAddress) "
            "RETURN a.email, b.email, r.timestamp, r.source_references, r.timestamps, "
            "r.content_sources, r.frequency ORDER BY a.email, b.email"
        ).get_all()
        mention_rows = conn.execute(
            "MATCH (a:EmailAddress)-[r:MENTIONS]->(b:EmailAddress) "
            "RETURN a.email, b.email, r.timestamp, r.source_references, r.timestamps, "
            "r.content_sources, r.frequency ORDER BY a.email, b.email"
        ).get_all()
    finally:
        conn.close()
        db.close()

    nodes_payload = [{"type": "EmailAddress", "email": row[0]} for row in node_rows]
    edges_payload: list[dict[str, Any]] = []
    for rel_type, rows in [("SENT_TO", sent_rows), ("MENTIONS", mention_rows)]:
        for row in rows:
            source_references = json.loads(row[3] or "[]")
            timestamps = json.loads(row[4] or "[]")
            content_sources = json.loads(row[5] or "[]")
            edges_payload.append(
                {
                    "type": rel_type,
                    "from": row[0],
                    "to": row[1],
                    "timestamp": row[2] or "",
                    "source_references": source_references,
                    "timestamps": timestamps,
                    "content_sources": content_sources,
                    "frequency": int(row[6] or 0),
                }
            )
    return {"nodes": nodes_payload, "edges": edges_payload, "ladybug_db_path": str(db_path)}


def build_email_graph(
    messages: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Build an EmailAddress graph from messages and materialize it in Ladybug."""
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

    edges_payload = sorted(
        edge_map.values(),
        key=lambda edge: (edge["type"], edge["from"], edge["to"]),
    )
    return _materialize_graph_in_ladybug(nodes, edges_payload, db_path=db_path or _graph_db_path())


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


EXALL_COMMAND_SPEC = CommandSpec(
    command="gcli tools exall",
    interactive=False,
    inputs=(
        CommandInput(name="input_artifact", required=False, source="artifact"),
        CommandInput(name="artifact_output", required=False, source="default"),
        CommandInput(name="artifact_id", required=False, source="artifact"),
    ),
    outputs=("graph_payload_artifact", "ladybug_db"),
)


@command_contract(EXALL_COMMAND_SPEC)
def exall_command(
    input_artifact: Annotated[
        str | None,
        typer.Option("--input-artifact", help="Upstream artifact id or file path"),
    ] = None,
    artifact_output: Annotated[
        bool,
        typer.Option("--artifact", help="Save output graph payload as an artifact"),
    ] = False,
    artifact_id: Annotated[
        str | None,
        typer.Option("--artifact-id", help="Explicit artifact id", hidden=True),
    ] = None,
) -> None:
    """Extract relationship edges from search artifacts using Ladybug graph materialization."""
    if not input_artifact:
        raise typer.BadParameter("Missing --input-artifact.")
    output_artifact_id = artifact_id if artifact_id else build_artifact_id("exall")
    try:
        payload = load_artifact_reference(input_artifact)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    graph = build_email_graph(
        payload.entries,
        db_path=_graph_db_path(artifact_id=output_artifact_id),
    )
    edges = graph["edges"]
    if not edges:
        console.print("[yellow]No relationships found in input artifact.[/yellow]")
        return

    _render_edges(edges)
    _render_summary(edges)
    console.print(f"[green]Ladybug graph:[/green] {graph['ladybug_db_path']}")
    if artifact_output:
        artifact_path = write_artifact(
            command="exall",
            args={
                "input_artifact": payload.path.name,
                "ladybug_db_path": graph["ladybug_db_path"],
            },
            entries=[graph],
            artifact_id=output_artifact_id,
        )
        console.print(f"[green]Saved artifact:[/green] {artifact_path}")
