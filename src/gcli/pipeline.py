from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.console import Console

from gcli.cache import generate_ulid
from gcli.command_meta import CommandInput, CommandSpec


@dataclass(frozen=True)
class PipelineStep:
    id: str
    command: str
    options: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineDefinition:
    name: str
    steps: tuple[PipelineStep, ...]


@dataclass(frozen=True)
class PipelineCommand:
    spec: CommandSpec
    execute: Callable[[dict[str, str], str], None]


def default_pipeline_dir() -> Path:
    return Path(__file__).parent / "pipelines"


def load_pipeline(name: str, *, pipeline_dir: Path | None = None) -> PipelineDefinition:
    source_dir = pipeline_dir or default_pipeline_dir()
    path = source_dir / f"{name}.json"
    if not path.exists():
        raise typer.BadParameter(f"Pipeline '{name}' not found.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_steps = payload.get("steps", [])
    steps = tuple(
        PipelineStep(
            id=step["id"],
            command=step["command"],
            options={k.replace("-", "_"): str(v) for k, v in step.get("options", {}).items()},
        )
        for step in raw_steps
    )
    if not steps:
        raise typer.BadParameter(f"Pipeline '{name}' has no steps.")
    return PipelineDefinition(name=payload.get("name", name), steps=steps)


def parse_input_overrides(items: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter(f"Invalid --input value '{item}'. Expected key=value.")
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _collect_input(
    step_id: str,
    command_input: CommandInput,
    *,
    provided: dict[str, str],
    collected: dict[str, str],
    interactive: bool,
    iext: bool,
    prompt_func: Callable[..., str],
) -> None:
    canonical = f"{step_id}.{command_input.name}"
    value = provided.get(canonical)
    if value is None:
        value = provided.get(command_input.name)
    if value:
        collected[canonical] = value
        return

    should_prompt = interactive and command_input.source == "user"
    if not should_prompt:
        return
    if command_input.required or iext:
        prompt_text = command_input.prompt or f"{step_id}.{command_input.name}"
        prompted = prompt_func(prompt_text, default="", show_default=False).strip()
        if prompted:
            collected[canonical] = prompted


def resolve_upfront_inputs(
    *,
    steps: tuple[PipelineStep, ...],
    registry: dict[str, PipelineCommand],
    provided: dict[str, str],
    iext: bool,
    prompt_func: Callable[..., str],
) -> dict[str, str]:
    collected: dict[str, str] = {}
    for step in steps:
        cmd = registry.get(step.command)
        if cmd is None:
            raise typer.BadParameter(f"Unsupported command in pipeline: {step.command}")
        for command_input in cmd.spec.inputs:
            _collect_input(
                step.id,
                command_input,
                provided=provided,
                collected=collected,
                interactive=cmd.spec.interactive,
                iext=iext,
                prompt_func=prompt_func,
            )

    missing: list[str] = []
    for step in steps:
        cmd = registry[step.command]
        for command_input in cmd.spec.inputs:
            if command_input.source != "user" or not command_input.required:
                continue
            key = f"{step.id}.{command_input.name}"
            if not collected.get(key):
                missing.append(key)
    if missing:
        missing_display = ", ".join(sorted(missing))
        raise typer.BadParameter(f"Missing required pipeline inputs: {missing_display}")
    return collected


def _slice_steps(
    steps: tuple[PipelineStep, ...], from_step: str | None, until_step: str | None
) -> tuple[PipelineStep, ...]:
    start = 0
    end = len(steps) - 1
    ids = [step.id for step in steps]
    if from_step:
        if from_step not in ids:
            raise typer.BadParameter(f"Unknown --from step '{from_step}'.")
        start = ids.index(from_step)
    if until_step:
        if until_step not in ids:
            raise typer.BadParameter(f"Unknown --until step '{until_step}'.")
        end = ids.index(until_step)
    if start > end:
        raise typer.BadParameter("--from step must come before --until step.")
    return tuple(steps[start : end + 1])


def _pipeline_run_id() -> str:
    return generate_ulid()


def run_pipeline(
    *,
    pipeline: PipelineDefinition,
    registry: dict[str, PipelineCommand],
    from_step: str | None,
    until_step: str | None,
    verbose: bool,
    iext: bool,
    provided_inputs: dict[str, str],
    prompt_func: Callable[..., str],
    console: Console,
) -> None:
    selected_steps = _slice_steps(pipeline.steps, from_step, until_step)
    # Merge step-level options as pre-set inputs; user-provided inputs take precedence
    step_options: dict[str, str] = {}
    for step in selected_steps:
        for key, val in step.options.items():
            step_options[f"{step.id}.{key}"] = val
    effective_provided = {**step_options, **provided_inputs}
    resolved_inputs = resolve_upfront_inputs(
        steps=selected_steps,
        registry=registry,
        provided=effective_provided,
        iext=iext,
        prompt_func=prompt_func,
    )
    run_id = _pipeline_run_id()
    console.print(f"[RUN] {pipeline.name}")

    for step in selected_steps:
        cmd = registry[step.command]
        step_inputs = {
            command_input.name: resolved_inputs.get(f"{step.id}.{command_input.name}")
            for command_input in cmd.spec.inputs
        }
        try:
            if verbose:
                console.print(f"\n[STEP] {step.id}")
                console.print(f"Executing: {step.command}")
            cmd.execute(step_inputs, run_id)
            if not verbose:
                console.print(f"[STEP] {step.id} .......... OK")
        except Exception as exc:
            if not verbose:
                console.print(f"[STEP] {step.id} .......... FAIL ({type(exc).__name__}: {exc})")
            raise
    console.print("[DONE] Pipeline completed successfully")
