from __future__ import annotations

import asyncio
import json

import typer
import uvicorn

from agentflow.app import create_app
from agentflow.loader import load_pipeline_from_path
from agentflow.orchestrator import Orchestrator
from agentflow.store import RunStore

app = typer.Typer(add_completion=False)


def _build_runtime(runs_dir: str, max_concurrent_runs: int) -> tuple[RunStore, Orchestrator]:
    store = RunStore(runs_dir)
    orchestrator = Orchestrator(store=store, max_concurrent_runs=max_concurrent_runs)
    return store, orchestrator


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    runs_dir: str = typer.Option(".agentflow/runs", envvar="AGENTFLOW_RUNS_DIR"),
    max_concurrent_runs: int = typer.Option(2, envvar="AGENTFLOW_MAX_CONCURRENT_RUNS"),
) -> None:
    store, orchestrator = _build_runtime(runs_dir, max_concurrent_runs)
    uvicorn.run(create_app(store=store, orchestrator=orchestrator), host=host, port=port)


@app.command()
def validate(path: str) -> None:
    pipeline = load_pipeline_from_path(path)
    typer.echo(json.dumps(pipeline.model_dump(mode="json"), indent=2))


@app.command()
def run(
    path: str,
    runs_dir: str = typer.Option(".agentflow/runs", envvar="AGENTFLOW_RUNS_DIR"),
    max_concurrent_runs: int = typer.Option(2, envvar="AGENTFLOW_MAX_CONCURRENT_RUNS"),
) -> None:
    store, orchestrator = _build_runtime(runs_dir, max_concurrent_runs)
    pipeline = load_pipeline_from_path(path)

    async def _run() -> None:
        run_record = await orchestrator.submit(pipeline)
        completed = await orchestrator.wait(run_record.id, timeout=None)
        typer.echo(json.dumps(completed.model_dump(mode="json"), indent=2))
        raise typer.Exit(code=0 if completed.status.value == "completed" else 1)

    asyncio.run(_run())


if __name__ == "__main__":
    app()
