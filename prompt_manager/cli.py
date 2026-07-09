"""CLI for Prompt Manager.

Usage:
    prompt-manager push agentic-inbox:draft-reply --file prompt.txt --env staging
    prompt-manager list
    prompt-manager get agentic-inbox:draft-reply
    prompt-manager diff agentic-inbox:draft-reply --v1 v3 --v2 v4
    prompt-manager rollback agentic-inbox:draft-reply --to v3 --env production
    prompt-manager ab-test start ... --variants v4:10,v3:90
    prompt-manager promote agentic-inbox:draft-reply --from staging --to production
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prompt_manager.schema import ABVariant, PromptVersion
from prompt_manager.storage import PromptStore

app = typer.Typer(
    name="prompt-manager",
    help="Version-controlled prompt management with staged rollouts, A/B testing, and rollbacks.",
    no_args_is_help=True,
)

console = Console()


def _get_store() -> PromptStore:
    root = os.environ.get("PROMPT_MANAGER_DIR")
    return PromptStore(root=root) if root else PromptStore()


def _render_entry(entry) -> Panel:
    rows: list[str] = []
    rows.append(f"[bold]Name:[/]         {entry.name}")
    rows.append("[bold]Environments:[/]  ")
    for env, ver in sorted(entry.environments.items()):
        rows.append(f"  {env}: [cyan]{ver}[/]")
    rows.append(f"[bold]Versions:[/]      {', '.join(v.version for v in entry.versions)}")
    if entry.ab_tests:
        rows.append("[bold]A/B Tests:[/]     ")
        rows.extend(
            f"  {t.id}: {t.status.value} ({len(t.variants)} variants)" for t in entry.ab_tests
        )
    if entry.eval_suite:
        rows.append(f"[bold]Eval Suite:[/]    {entry.eval_suite}")
    text = "\n".join(rows)
    return Panel(Text.from_markup(text), title=entry.name)


# ── Commands ───────────────────────────────────────────────────────────────────


@app.command()
def push(
    name: str = typer.Argument(..., help="Prompt name, e.g. agentic-inbox:draft-reply"),
    file: str = typer.Option(..., "--file", "-f", help="Path to prompt content file"),
    version: str = typer.Option(..., "--version", "-v", help="Version label, e.g. v4"),
    env: str = typer.Option("staging", "--env", "-e", help="Target environment"),
    description: str = typer.Option("", "--description", "-d", help="Version description"),
):
    """Push a new prompt version to an environment."""
    content = Path(file).read_text()
    pv = PromptVersion(version=version, content=content)
    pv.compute_hash()
    if description:
        pv.metadata["description"] = description

    entry = _get_store().push_version(name, env, pv)
    console.print(f"[green]✓[/] Pushed [bold]{version}[/] ({pv.hash}) → [cyan]{env}[/]")
    console.print(_render_entry(entry))


@app.command()
def pull(
    name: str = typer.Argument(..., help="Prompt name"),
    env: str = typer.Option("production", "--env", "-e", help="Environment to pull from"),
):
    """Pull the current prompt version from an environment."""
    try:
        content = _get_store().pull_version(name, env)
        console.print(content)
    except Exception as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e


@app.command(name="list")
def list_(
    env: str | None = typer.Option(None, "--env", "-e", help="Filter by environment"),
):
    """List all managed prompts."""
    prompts = _get_store().list_all()
    if env:
        prompts = [p for p in prompts if env in p.environments]

    if not prompts:
        console.print("[yellow]No prompts managed.[/]")
        return

    table = Table(title="Managed Prompts")
    table.add_column("Name", style="cyan")
    table.add_column("Staging")
    table.add_column("Production")
    table.add_column("Versions", style="dim")
    table.add_column("A/B Tests")

    for p in sorted(prompts, key=lambda x: x.name):
        ab_count = str(len([t for t in p.ab_tests if t.status.value == "running"]))
        table.add_row(
            p.name,
            p.environments.get("staging", "-"),
            p.environments.get("production", "-"),
            str(len(p.versions)),
            ab_count,
        )

    console.print(table)
    console.print(f"[dim]{len(prompts)} prompt(s)[/]")


@app.command()
def get(
    name: str = typer.Argument(..., help="Prompt name to retrieve"),
):
    """Show full details for a prompt."""
    try:
        entry = _get_store().get(name)
        console.print(_render_entry(entry))
        for v in entry.versions:
            preview = v.content[:120].replace("\n", "\\n")
            console.print(f"  [dim]{v.version}[/] ({v.hash}) — {preview}...")
    except (KeyError, FileNotFoundError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e


@app.command()
def diff(
    name: str = typer.Argument(..., help="Prompt name"),
    v1: str = typer.Option(..., "--v1", help="First version to compare"),
    v2: str = typer.Option(..., "--v2", help="Second version to compare"),
):
    """Show diff between two versions of a prompt."""
    entry = _get_store().get(name)
    pv1 = entry.get_version(v1)
    pv2 = entry.get_version(v2)

    if not pv1:
        console.print(f"[red]✗[/] Version '{v1}' not found.")
        raise typer.Exit(1)
    if not pv2:
        console.print(f"[red]✗[/] Version '{v2}' not found.")
        raise typer.Exit(1)

    console.print(f"[bold]Diff: {v1} → {v2}[/]")
    console.print(f"[dim]v1 hash: {pv1.hash}  v2 hash: {pv2.hash}[/]")
    console.print()

    if pv1.content == pv2.content:
        console.print("[yellow]No content difference.[/]")
        return

    lines1 = pv1.content.splitlines()
    lines2 = pv2.content.splitlines()

    for _i, (l1, l2) in enumerate(zip(lines1, lines2, strict=False)):
        if l1 != l2:
            console.print(f"[red]- {l1}[/]")
            console.print(f"[green]+ {l2}[/]")
    if len(lines1) > len(lines2):
        for line in lines1[len(lines2) :]:
            console.print(f"[red]- {line}[/]")
    elif len(lines2) > len(lines1):
        for line in lines2[len(lines1) :]:
            console.print(f"[green]+ {line}[/]")


@app.command()
def rollback(
    name: str = typer.Argument(..., help="Prompt name"),
    to: str = typer.Option(..., "--to", help="Version to rollback to"),
    env: str = typer.Option("production", "--env", "-e", help="Environment to rollback"),
):
    """Rollback an environment to a previous version."""
    try:
        _get_store().rollback(name, env, to)
        console.print(f"[green]✓[/] Rolled back [bold]{name}[/] → {to} in [cyan]{env}[/]")
    except (ValueError, KeyError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e


@app.command()
def promote(
    name: str = typer.Argument(..., help="Prompt name"),
    from_env: str = typer.Option("staging", "--from", help="Source environment"),
    to_env: str = typer.Option("production", "--to", help="Target environment"),
):
    """Promote a prompt version from one environment to another."""
    entry = _get_store().get(name)
    version = entry.current_version(from_env)
    if not version:
        console.print(f"[red]✗[/] No version in {from_env}.")
        raise typer.Exit(1)

    entry.environments[to_env] = version
    entry.updated_at = datetime.now(timezone.utc)
    _get_store().put(entry)
    console.print(f"[green]✓[/] Promoted [bold]{version}[/] from {from_env} → [cyan]{to_env}[/]")


@app.command()
def validate(
    name: str = typer.Argument(..., help="Prompt name to validate"),
    env: str = typer.Option("staging", "--env", "-e", help="Environment to validate"),
):
    """Validate a prompt against its configured eval suite (delegates to eval-harness)."""
    entry = _get_store().get(name)
    if not entry.eval_suite:
        console.print("[yellow]No eval suite configured for this prompt.[/]")
        console.print("Set one with: prompt-manager config --eval-suite <suite_name>")
        return

    version = entry.current_version(env)
    if not version:
        console.print(f"[red]✗[/] No version in {env}.")
        raise typer.Exit(1)

    console.print(f"[bold]Validation required for:[/] {entry.eval_suite}")
    console.print(f"[dim]Prompt: {name}@{env}={version}[/]")
    console.print()
    console.print("[yellow]Run manually:[/] `evalh run --suite {entry.eval_suite}`")
    console.print("[dim]Eval harness integration coming in v0.2.0[/]")


# ── A/B Test ───────────────────────────────────────────────────────────────────


ab_app = typer.Typer(help="A/B test management", no_args_is_help=True)
app.add_typer(ab_app, name="ab-test")


@ab_app.command("start")
def ab_start(
    name: str = typer.Argument(..., help="Prompt name"),
    variants: str = typer.Option(
        ..., "--variants", help="Comma-separated version:weight pairs, e.g. v4:10,v3:90"
    ),
    control: str = typer.Option(..., "--control", help="Control version"),
):
    """Start an A/B test with weighted variants."""
    parsed: list[ABVariant] = []
    for pair in variants.split(","):
        ver, weight = pair.strip().split(":")
        parsed.append(ABVariant(version=ver, weight=float(weight) / 100))

    total = sum(v.weight for v in parsed)
    if abs(total - 1.0) > 0.01:
        console.print(f"[red]✗[/] Variant weights must sum to 100%. Got: {total * 100:.0f}%")
        raise typer.Exit(1)

    _get_store().start_ab_test(name, parsed, control)
    console.print(f"[green]✓[/] Started A/B test on [bold]{name}[/]")
    for v in parsed:
        console.print(f"  {v.version}: {v.weight * 100:.0f}%")


@ab_app.command("stop")
def ab_stop(
    name: str = typer.Argument(..., help="Prompt name"),
    test_id: str = typer.Option(..., "--test-id", help="Test ID to stop"),
    winner: str | None = typer.Option(None, "--winner", help="Winning version to promote"),
):
    """Stop a running A/B test."""
    entry = _get_store().stop_ab_test(name, test_id, winner=winner)
    console.print(f"[green]✓[/] Stopped A/B test [bold]{test_id}[/]")
    if winner:
        console.print(f"  Winner: [cyan]{winner}[/] (promoted to production)")
    console.print(_render_entry(entry))


@ab_app.command("list")
def ab_list(
    name: str | None = typer.Option(None, "--name", "-n", help="Filter by prompt name"),
):
    """List active A/B tests."""
    prompts = _get_store().list_all()
    found = 0
    for p in prompts:
        if name and p.name != name:
            continue
        for t in p.ab_tests:
            if t.status.value == "running":
                console.print(f"[bold]{p.name}[/] — {t.id}")
                for v in t.variants:
                    console.print(f"  {v.version}: {v.weight * 100:.0f}% {v.description}")
                console.print(f"  control: {t.control_version}")
                found += 1

    if not found:
        console.print("[yellow]No running A/B tests.[/]")


# ── Config ─────────────────────────────────────────────────────────────────────


@app.command()
def config(
    name: str = typer.Argument(..., help="Prompt name"),
    eval_suite: str | None = typer.Option(
        None, "--eval-suite", help="Eval suite for gate validation"
    ),
):
    """Configure prompt settings."""
    entry = _get_store().get(name)
    if eval_suite:
        entry.eval_suite = eval_suite
    _get_store().put(entry)
    console.print(f"[green]✓[/] Updated config for [bold]{name}[/]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
