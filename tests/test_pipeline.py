from __future__ import annotations

import io

import pytest
import typer
from rich.console import Console

from gcli.cli import search_command
from gcli.command_meta import get_command_spec
from gcli.pipeline import (
    PipelineCommand,
    PipelineDefinition,
    PipelineStep,
    load_pipeline,
    resolve_upfront_inputs,
    run_pipeline,
)
from gcli.tools.exall import exall_command
from gcli.tools.visualize import visualize_command


def test_command_contracts_define_interactive_designation() -> None:
    assert get_command_spec(search_command).interactive is True
    assert get_command_spec(exall_command).interactive is False
    assert get_command_spec(visualize_command).interactive is False


def test_resolve_upfront_inputs_minimal_prompts_only_required() -> None:
    search_spec = get_command_spec(search_command)
    step = PipelineStep(id="search", command=search_spec.command)
    prompts: list[str] = []

    def prompt_func(text: str, **_: object) -> str:
        prompts.append(text)
        return "invoice"

    resolved = resolve_upfront_inputs(
        steps=(step,),
        registry={search_spec.command: PipelineCommand(spec=search_spec, execute=lambda *_: None)},
        provided={},
        iext=False,
        prompt_func=prompt_func,
    )
    assert resolved["search.terms"] == "invoice"
    assert len(prompts) == 1


def test_resolve_upfront_inputs_extended_prompts_optional() -> None:
    search_spec = get_command_spec(search_command)
    step = PipelineStep(id="search", command=search_spec.command)
    prompts: list[str] = []

    def prompt_func(text: str, **_: object) -> str:
        prompts.append(text)
        if "required" in text.lower():
            return "invoice"
        if "--from" in text:
            return "alice@example.com"
        return ""

    resolved = resolve_upfront_inputs(
        steps=(step,),
        registry={search_spec.command: PipelineCommand(spec=search_spec, execute=lambda *_: None)},
        provided={},
        iext=True,
        prompt_func=prompt_func,
    )
    assert resolved["search.terms"] == "invoice"
    assert resolved["search.sender"] == "alice@example.com"
    assert len(prompts) > 1


def test_pipeline_fails_before_execution_when_required_input_missing() -> None:
    search_spec = get_command_spec(search_command)
    executed: list[str] = []
    pipeline = PipelineDefinition(
        name="emailgph",
        steps=(PipelineStep(id="search", command=search_spec.command),),
    )
    registry = {
        search_spec.command: PipelineCommand(
            spec=search_spec,
            execute=lambda *_: executed.append("search"),
        )
    }
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, color_system=None)

    with pytest.raises(typer.BadParameter):
        run_pipeline(
            pipeline=pipeline,
            registry=registry,
            from_step=None,
            until_step=None,
            verbose=False,
            iext=False,
            provided_inputs={},
            prompt_func=lambda *_args, **_kwargs: "",
            console=console,
        )
    assert executed == []
    assert output.getvalue() == ""


def test_pipeline_execution_success_with_upfront_inputs() -> None:
    search_spec = get_command_spec(search_command)
    exall_spec = get_command_spec(exall_command)
    viz_spec = get_command_spec(visualize_command)
    pipeline = PipelineDefinition(
        name="emailgph",
        steps=(
            PipelineStep(id="search", command=search_spec.command),
            PipelineStep(id="extract", command=exall_spec.command),
            PipelineStep(id="visualize", command=viz_spec.command),
        ),
    )
    order: list[str] = []
    run_ids: set[str] = set()

    def mk_exec(step_id: str):
        def _exec(_step_inputs: dict[str, str], run_id: str) -> None:
            order.append(step_id)
            run_ids.add(run_id)

        return _exec

    registry = {
        search_spec.command: PipelineCommand(spec=search_spec, execute=mk_exec("search")),
        exall_spec.command: PipelineCommand(spec=exall_spec, execute=mk_exec("extract")),
        viz_spec.command: PipelineCommand(spec=viz_spec, execute=mk_exec("visualize")),
    }
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, color_system=None)

    run_pipeline(
        pipeline=pipeline,
        registry=registry,
        from_step=None,
        until_step=None,
        verbose=False,
        iext=False,
        provided_inputs={"search.terms": "invoice"},
        prompt_func=lambda *_args, **_kwargs: "",
        console=console,
    )
    text = output.getvalue()
    assert order == ["search", "extract", "visualize"]
    assert len(run_ids) == 1
    assert "[RUN] emailgph" in text
    assert "[STEP] search .......... OK" in text
    assert "[STEP] extract .......... OK" in text
    assert "[STEP] visualize .......... OK" in text
    assert "[DONE] Pipeline completed successfully" in text


def test_emailgph_pipeline_config_exists() -> None:
    pipeline = load_pipeline("emailgph")
    assert pipeline.name == "emailgph"
    assert [step.id for step in pipeline.steps] == ["search", "extract", "visualize"]


def test_pipeline_step_options_loaded_and_normalised() -> None:
    pipeline = load_pipeline("emailgph")
    search_step = next(s for s in pipeline.steps if s.id == "search")
    assert search_step.options.get("match_all") == "true"


def test_pipeline_step_options_flow_into_step_execute() -> None:
    """Step options become pre-set inputs; the execute function receives them."""
    search_spec = get_command_spec(search_command)
    received: list[dict] = []

    def capture_exec(step_inputs: dict, run_id: str) -> None:
        received.append(dict(step_inputs))

    step = PipelineStep(id="search", command=search_spec.command, options={"match_all": "true"})
    registry = {search_spec.command: PipelineCommand(spec=search_spec, execute=capture_exec)}
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, color_system=None)

    run_pipeline(
        pipeline=PipelineDefinition(name="test", steps=(step,)),
        registry=registry,
        from_step=None,
        until_step=None,
        verbose=False,
        iext=False,
        provided_inputs={"search.terms": "invoice"},
        prompt_func=lambda *_args, **_kwargs: "",
        console=console,
    )
    assert received[0]["match_all"] == "true"


def test_pipeline_step_user_input_overrides_step_option() -> None:
    """User --input values override step-level options."""
    search_spec = get_command_spec(search_command)
    received: list[dict] = []

    def capture_exec(step_inputs: dict, run_id: str) -> None:
        received.append(dict(step_inputs))

    step = PipelineStep(id="search", command=search_spec.command, options={"match_all": "true"})
    registry = {search_spec.command: PipelineCommand(spec=search_spec, execute=capture_exec)}
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, color_system=None)

    run_pipeline(
        pipeline=PipelineDefinition(name="test", steps=(step,)),
        registry=registry,
        from_step=None,
        until_step=None,
        verbose=False,
        iext=False,
        provided_inputs={"search.terms": "invoice", "search.match_all": "false"},
        prompt_func=lambda *_args, **_kwargs: "",
        console=console,
    )
    assert received[0]["match_all"] == "false"
