from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from gcli.cache import load_latest_cache
from gcli.command_meta import CommandInput, CommandSpec, command_contract

console = Console()

VISUALIZE_COMMAND_SPEC = CommandSpec(
    command="gcli tools visualize",
    interactive=False,
    inputs=(
        CommandInput(name="from_cache", required=False, source="cache"),
        CommandInput(name="output", required=False, source="default"),
        CommandInput(name="cache_run_id", required=False, source="cache"),
    ),
    outputs=("html_file",),
)


def _compute_degrees(graph: dict[str, Any]) -> dict[str, int]:
    """Return a mapping of node id -> total degree (in + out)."""
    degree: dict[str, int] = {}
    for edge in graph.get("edges", []):
        for key in ("from", "to"):
            nid = edge.get(key, "")
            if nid:
                degree[nid] = degree.get(nid, 0) + 1
    return degree


def _to_cytoscape_elements(graph: dict[str, Any]) -> list[dict[str, Any]]:
    degree = _compute_degrees(graph)
    max_degree = max(degree.values(), default=1)

    elements: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        email = node.get("email", "")
        node_degree = degree.get(email, 0)
        # Map degree onto a node diameter: isolated nodes ~30 px, hubs ~90 px.
        size = 30 + int(60 * node_degree / max(max_degree, 1))
        elements.append(
            {
                "data": {
                    "id": email,
                    "label": email,
                    "type": node.get("type", "EmailAddress"),
                    "degree": node_degree,
                    "size": size,
                }
            }
        )

    for edge in graph.get("edges", []):
        source = edge.get("from", "")
        target = edge.get("to", "")
        edge_type = edge.get("type", "")
        edge_id = f"{edge_type}:{source}->{target}"
        elements.append(
            {
                "data": {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "type": edge_type,
                    "frequency": edge.get("frequency", 0),
                }
            }
        )
    return elements


def _build_html(elements: list[dict[str, Any]], title: str) -> str:
    payload = json.dumps(elements)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
  <script src="https://unpkg.com/cytoscape-cose-bilkent@4.1.0/cytoscape-cose-bilkent.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; }}
    #cy {{ width: 100vw; height: 100vh; display: block; }}
  </style>
</head>
<body>
  <div id="cy"></div>
  <script>
    const elements = {payload};
    cytoscape({{
      container: document.getElementById('cy'),
      elements,
      style: [
        {{
          selector: 'node',
          style: {{
            'label': 'data(label)',
            'background-color': '#1f77b4',
            'color': '#111',
            // font scales with degree: base 11px, hubs up to 15px
            'font-size': 'mapData(degree, 0, 10, 11, 15)',
            'text-wrap': 'wrap',
            'text-max-width': '200px',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': '8px',
            // node circle diameter comes from pre-computed size (30–90 px)
            'width': 'data(size)',
            'height': 'data(size)'
          }}
        }},
        {{
          selector: 'edge',
          style: {{
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'line-color': '#999',
            'target-arrow-color': '#999',
            'label': 'data(type)',
            'font-size': '10px',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.8,
            'text-background-padding': '3px'
          }}
        }},
        {{
          selector: 'edge[type = "SENT_TO"]',
          style: {{
            'line-color': '#2ca02c',
            'target-arrow-color': '#2ca02c'
          }}
        }},
        {{
          selector: 'edge[type = "MENTIONS"]',
          style: {{
            'line-color': '#ff7f0e',
            'target-arrow-color': '#ff7f0e'
          }}
        }}
      ],
      layout: {{
        name: 'cose-bilkent',
        animate: false,
        padding: 60,
        // Hub nodes get much stronger repulsion; isolated nodes stay compact.
        nodeRepulsion: function(node) {{
          return 6000 * (1 + node.data('degree'));
        }},
        // Edges touching high-degree nodes should be longer.
        idealEdgeLength: function(edge) {{
          const srcDeg = edge.source().data('degree') || 0;
          const tgtDeg = edge.target().data('degree') || 0;
          return 120 + 20 * (srcDeg + tgtDeg);
        }},
        edgeElasticity: 0.1,
        nestingFactor: 0.1,
        gravity: 0.25,
        numIter: 2500,
        tile: true,
        tilingPaddingVertical: 40,
        tilingPaddingHorizontal: 40,
        gravityRangeCompound: 1.5,
        gravityCompound: 1.0,
        gravityRange: 3.8
      }}
    }});
  </script>
</body>
</html>
"""


@command_contract(VISUALIZE_COMMAND_SPEC)
def visualize_command(
    from_cache: Annotated[
        str | None,
        typer.Option("--from-cache", help="Load latest cache from a specific command"),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", help="Output HTML file path"),
    ] = Path("graph.html"),
    cache_run_id: Annotated[
        str | None,
        typer.Option("--cache-run-id", help="Pipeline cache run identifier", hidden=True),
    ] = None,
) -> None:
    """Render a cached graph as a Cytoscape.js HTML visualization."""
    source_command = from_cache or "exall"
    try:
        payload = load_latest_cache(source_command, run_id=cache_run_id)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if not payload.entries:
        raise typer.BadParameter(f"Cache for '{source_command}' is empty.")
    graph = payload.entries[0]
    if "nodes" not in graph or "edges" not in graph:
        raise typer.BadParameter(f"Cache for '{source_command}' does not contain graph data.")

    elements = _to_cytoscape_elements(graph)
    html = _build_html(elements, title="gcli Email Graph")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    console.print(f"[green]Visualization written:[/green] {output.resolve()}")
