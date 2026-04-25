from __future__ import annotations

from gcli.tools.exall import build_email_graph


def test_build_email_graph_preserves_edge_types_and_direction() -> None:
    graph = build_email_graph(
        [
            {
                "id": "m1",
                "from": "Alice <alice@example.com>",
                "to": "bob@example.com",
                "cc": "team@example.com",
                "bcc": "",
                "body": "FYI: loop in carol@example.com",
                "date": "Mon, 01 Jan 2026 10:00:00 +0000",
            },
            {
                "id": "m2",
                "from": "alice@example.com",
                "to": "bob@example.com",
                "cc": "",
                "bcc": "",
                "body": "Escalate to carol@example.com",
                "date": "Mon, 01 Jan 2026 11:00:00 +0000",
            },
        ]
    )

    edges = {(edge["type"], edge["from"], edge["to"]): edge for edge in graph["edges"]}
    assert ("SENT_TO", "alice@example.com", "bob@example.com") in edges
    assert ("SENT_TO", "alice@example.com", "team@example.com") in edges
    assert ("MENTIONS", "alice@example.com", "carol@example.com") in edges
    assert edges[("SENT_TO", "alice@example.com", "bob@example.com")]["frequency"] == 2
    assert edges[("MENTIONS", "alice@example.com", "carol@example.com")]["frequency"] == 2
