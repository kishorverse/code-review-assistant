"""Command line for the evaluation: ``uv run python -m evaluation --help``."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from app.log import configure_logging
from app.review.merge import is_reported
from app.review.planner import DEFAULT_MIN_CONFIDENCE
from evaluation import agreement, latency, report, routing_sim
from evaluation.dataset import load_dataset
from evaluation.runner import RUNS_DIR, RunKind, RunSpec, load_records, records_path, run
from evaluation.scoring import Prediction, matches

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def check() -> None:
    """Validate the seeded dataset's labels against its files."""
    dataset = load_dataset()
    console.print(
        f"{dataset.name} v{dataset.version}: {len(dataset.files)} files "
        f"({len(dataset.clean_files)} clean), {len(dataset.labels)} labels"
    )


@app.command(name="run")
def run_command(
    kind: Annotated[RunKind, typer.Argument(help="static, llm-only, hybrid or model.")],
    provider: Annotated[
        str | None, typer.Option(help="The single provider for a model run.")
    ] = None,
    files: Annotated[
        list[str] | None, typer.Option("--file", help="Only these dataset files.")
    ] = None,
    concurrency: Annotated[int, typer.Option(min=1, help="Files scanned at once.")] = 4,
    fresh: Annotated[bool, typer.Option(help="Discard earlier records of this run.")] = False,
    rounds: Annotated[
        int, typer.Option(min=1, help="Passes over files still incomplete, to wait out limits.")
    ] = 1,
    wait: Annotated[float, typer.Option(min=0, help="Seconds between passes.")] = 65.0,
) -> None:
    """Run one configuration over the dataset, resuming unless --fresh."""
    configure_logging("ERROR", "console")
    spec = RunSpec(kind, provider)
    records = asyncio.run(
        run(
            spec,
            load_dataset(),
            files=files,
            concurrency=concurrency,
            fresh=fresh,
            rounds=rounds,
            wait_seconds=wait,
        )
    )
    incomplete = [record for record in records.values() if not record.complete]
    console.print(
        f"{spec.name}: {len(records)} files recorded, {len(incomplete)} incomplete "
        f"-> {records_path(spec)}"
    )
    for record in incomplete:
        console.print(f"  [yellow]{record.file}[/yellow] {record.error or record.stats}")


@app.command()
def curate() -> None:
    """List every reported static finding and whether it matches a label.

    Used while writing the dataset, before any model sees it: a finding that
    matches no label is either an accidental issue to remove from the file or a
    real issue to label.
    """
    dataset = load_dataset()
    records = load_records(records_path(RunSpec(RunKind.STATIC)))
    table = Table("file", "line", "category", "source", "rule", "title", "label")
    for name in dataset.files:
        record = records.get(name)
        for finding in record.variants.get("A", []) if record else []:
            if not is_reported(finding, DEFAULT_MIN_CONFIDENCE):
                continue
            prediction = Prediction.from_finding(finding)
            hit = [lb.label.id for lb in dataset.labels if matches(prediction, lb)]
            table.add_row(
                name,
                str(finding.start_line),
                finding.category.value,
                ",".join(finding.sources),
                finding.rule_id or "",
                finding.title[:60],
                ", ".join(hit) or "[red]none[/red]",
            )
    console.print(table)


@app.command(name="score")
def score_command() -> None:
    """Score every recorded run and write scores.json and tables.md."""
    dataset = load_dataset()
    results = report.evaluate(dataset)
    report.write(dataset, results)
    for result in results:
        overall = result.scorecard.overall
        console.print(
            f"{result.variant:>10}: P={report.pct(overall.precision)} "
            f"R={report.pct(overall.recall)} F1={report.pct(overall.f1)} "
            f"({result.complete_files}/{result.files} files)"
        )
    console.print(f"-> {report.RESULTS_DIR}")


@app.command()
def routing() -> None:
    """Simulate a scan's calls under rate limits: plain clients versus the router."""
    configure_logging("ERROR", "console")
    outcomes = asyncio.run(routing_sim.simulate())
    table = routing_sim.to_markdown(outcomes)
    path = report.RESULTS_DIR / "routing.md"
    path.write_text(table, encoding="utf-8", newline="\n")
    console.print(table)
    console.print(f"-> {path}")


@app.command(name="latency")
def latency_command(
    static_runs: Annotated[int, typer.Option(min=1)] = 5,
    hybrid_runs: Annotated[int, typer.Option(min=1)] = 3,
) -> None:
    """Time whole scans of 50, 200 and 500-line files and of the seeded project."""
    configure_logging("ERROR", "console")
    measurements = asyncio.run(latency.benchmark(static_runs, hybrid_runs))
    table = latency.to_markdown(measurements)
    path = report.RESULTS_DIR / "latency.md"
    path.write_text(table, encoding="utf-8", newline="\n")
    console.print(table)
    console.print(f"-> {path}")


@app.command(name="sample")
def sample_command(
    variant: Annotated[str, typer.Option(help="Configuration to sample from.")] = "E",
    size: Annotated[int, typer.Option(min=1)] = 30,
    seed: Annotated[int, typer.Option()] = 2026,
) -> None:
    """Write a blind rating sheet of AI suggestions for human raters."""
    run_name = {"B": "llm-only", "D": "hybrid", "E": "hybrid"}.get(variant, variant)
    records = load_records(RUNS_DIR / f"{run_name}.jsonl")
    items = agreement.sample(list(records.values()), variant, size, seed)
    agreement.write_sheet(items)
    console.print(f"{len(items)} items -> {agreement.HUMAN_EVAL_DIR / 'rating_sheet.csv'}")


@app.command(name="agreement")
def agreement_command() -> None:
    """Summarize the human ratings and how far raters agree."""
    summary = agreement.summarize()
    path = report.RESULTS_DIR / "human_ratings.md"
    path.write_text(summary, encoding="utf-8", newline="\n")
    console.print(summary)


if __name__ == "__main__":
    app()
