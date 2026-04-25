from __future__ import annotations

import typer

from gcli.tools.exall import exall_command
from gcli.tools.visualize import visualize_command

app = typer.Typer(help="Tool operations")
app.command("exall")(exall_command)
app.command("visualize")(visualize_command)
