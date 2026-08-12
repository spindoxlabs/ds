"""`ds-conformance` — measure the rulebook against the blueprints and the tests.

    ds-conformance status          # rewrite docs/rulebook/status.md
    ds-conformance status --check  # fail if the committed file is stale
    ds-conformance summary         # the counts, to a terminal
    ds-conformance rule A-11       # what evidences one rule
    ds-conformance problems        # structural inconsistencies only

`status` is the one that matters; the rest are for working on a single row
without regenerating the page.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import typer

from .assess import assess
from .report import Verdict, judge_all, render, summarise
from .rulebook import sort_key

app = typer.Typer(add_completion=False, help=__doc__)

DEFAULT_OUTPUT = Path("docs/rulebook/status.md")


def _repo(option: Path | None) -> Path:
    if option is not None:
        return option.resolve()
    # Walk up to the checkout root rather than trusting the working directory,
    # so the tool answers the same from any subdirectory.
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "docs" / "rulebook").is_dir() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise typer.BadParameter("not inside a ds checkout; pass --repo")


def _commit(repo: Path) -> str:
    """The commit the measurement was taken at, so a stale page is obvious.

    Falls back to a marker rather than raising: the tool must work in a tarball
    export, and "unknown" is a true answer where a crash is not.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    revision = result.stdout.strip()
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return revision or "unknown"
    return f"{revision}-dirty" if dirty else revision or "unknown"


def _generated_on(repo: Path) -> date:
    """The commit's date, not today's.

    `status.md` is committed, so stamping it with the wall clock would make
    every regeneration a diff even when nothing measured changed — which trains
    a reader to skim past exactly the diff this file exists to show.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return datetime.fromisoformat(result.stdout.strip()).date()
    except (subprocess.SubprocessError, OSError, ValueError):
        return datetime.now(UTC).date()


@app.command()
def status(
    repo: Path | None = typer.Option(None, help="Checkout root. Discovered by default."),
    output: Path = typer.Option(DEFAULT_OUTPUT, help="Where to write the page."),
    check: bool = typer.Option(
        False, "--check", help="Do not write; exit 1 if the committed page is stale."
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help=(
            "Exit 1 when a rule claims enforcement with no test naming it. "
            "Off by default — this is a report, not a gate."
        ),
    ),
) -> None:
    """Rewrite `docs/rulebook/status.md` from the tree."""
    root = _repo(repo)
    assessment = assess(root)
    page = render(assessment, generated_on=_generated_on(root), commit=_commit(root))
    target = output if output.is_absolute() else root / output

    if check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != page:
            typer.echo(f"{target} is stale — run `task rulebook:status`", err=True)
            raise typer.Exit(1)
        typer.echo(f"{target} is up to date")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        typer.echo(f"wrote {target}")

    counts = summarise(assessment)
    typer.echo(
        f"{counts['evidenced']}/{counts['claiming']} rules claiming enforcement are "
        f"evidenced · {counts['unassessed']} binding blueprint rows unassessed · "
        f"{counts['problems']} structural problems"
    )

    if strict and (counts["unevidenced"] or counts["contradicted"] or counts["problems"]):
        raise typer.Exit(1)


@app.command()
def summary(
    repo: Path | None = typer.Option(None),
    as_json: bool = typer.Option(False, "--json", help="Emit the counts as JSON."),
) -> None:
    """Print the counts without writing anything."""
    counts = summarise(assess(_repo(repo)))
    if as_json:
        typer.echo(json.dumps(counts, indent=2, sort_keys=True))
        return
    width = max(len(key) for key in counts)
    for key in sorted(counts):
        typer.echo(f"{key.rjust(width)}  {counts[key]}")


@app.command()
def rule(
    rule_id: str = typer.Argument(..., help="A rule id, e.g. A-11."),
    repo: Path | None = typer.Option(None),
) -> None:
    """Show one rule: what it claims, and every test that names it."""
    assessment = assess(_repo(repo))
    for verdict in judge_all(assessment):
        if verdict.rule.id != rule_id:
            continue
        typer.echo(f"{verdict.rule.id}  ({verdict.rule.page}.md:{verdict.rule.line})")
        typer.echo(f"  section   {verdict.rule.section}")
        typer.echo(f"  claims    {verdict.rule.status or '— (precedence row)'}")
        typer.echo(f"  verdict   {verdict.verdict.value}")
        typer.echo(f"  statement {verdict.rule.statement[:200]}")
        if not verdict.evidence:
            typer.echo("  evidence  none")
        else:
            typer.echo(f"  evidence  {len(verdict.evidence)} node(s)")
            for item in verdict.evidence:
                typer.echo(f"            [{item.layer.value}] {item.node}")
                typer.echo(f"                {item.file}:{item.line}")
        return
    typer.echo(f"no rule {rule_id} in docs/rulebook/", err=True)
    raise typer.Exit(1)


@app.command()
def unevidenced(repo: Path | None = typer.Option(None)) -> None:
    """List the rules that claim enforcement and name no test."""
    assessment = assess(_repo(repo))
    rows = [v for v in judge_all(assessment) if v.verdict is Verdict.UNEVIDENCED]
    for verdict in sorted(rows, key=lambda v: sort_key(v.rule.id)):
        typer.echo(f"{verdict.rule.id:<8} {verdict.rule.page:<24} {verdict.rule.statement[:90]}")
    typer.echo(f"\n{len(rows)} rules", err=True)


@app.command()
def problems(repo: Path | None = typer.Option(None)) -> None:
    """List structural inconsistencies only."""
    assessment = assess(_repo(repo))
    for problem in sorted(assessment.problems, key=lambda p: (p.kind, p.subject)):
        location = f" ({problem.where})" if problem.where else ""
        typer.echo(f"{problem.kind}: {problem.subject}{location}\n    {problem.detail}")
    typer.echo(f"\n{len(assessment.problems)} problems", err=True)
    if assessment.problems:
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(app())
