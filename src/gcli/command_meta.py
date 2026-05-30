from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

InputSource = Literal["user", "artifact", "default"]


@dataclass(frozen=True)
class CommandInput:
    name: str
    required: bool
    source: InputSource
    prompt: str | None = None


@dataclass(frozen=True)
class CommandSpec:
    command: str
    interactive: bool
    inputs: tuple[CommandInput, ...]
    outputs: tuple[str, ...] = ()


def command_contract(spec: CommandSpec) -> Callable:
    def decorator(func: Callable) -> Callable:
        func.__gcli_command_spec__ = spec
        return func

    return decorator


def get_command_spec(func: Callable) -> CommandSpec:
    spec = getattr(func, "__gcli_command_spec__", None)
    if spec is None:
        raise ValueError(f"Command '{func.__name__}' is missing command contract metadata.")
    return spec
