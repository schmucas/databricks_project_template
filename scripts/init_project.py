#!/usr/bin/env python3
"""Turn a copy of this template into a new project.

Run once, right after cloning or using the GitHub "Use this template" button:

    python3 scripts/init_project.py

It rewrites the template's placeholder identity everywhere it appears, generates
a fresh bundle UUID, retitles the README, and then deletes itself along with the
template-only docs. Nothing else in the repo is touched.

Non-interactive form, for scripting:

    python3 scripts/init_project.py \\
        --name retail_analytics --catalog-prefix retail \\
        --host https://dbc-xxxx.cloud.databricks.com --yes

`--dry-run` prints what would change and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The template's own identity, replaced everywhere it appears.
TEMPLATE_NAME = "databricks_project_template"
TEMPLATE_PREFIX = "tpl"
TEMPLATE_HOST = "https://your-workspace.cloud.databricks.com"
TEMPLATE_UUID = "00000000-0000-0000-0000-000000000000"

# Files removed once the project is its own thing.
TEMPLATE_ONLY = ["scripts/init_project.py", "docs/TEMPLATE.md"]

SKIP_DIRS = {".git", ".venv", ".databricks", "__pycache__", ".ruff_cache", ".pytest_cache", "node_modules"}
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".toml", ".json", ".md", ".ipynb", ".txt", ".cfg", ".example", ""}

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,49}$")
PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]{1,19}$")
HOST_RE = re.compile(r"^https://[a-zA-Z0-9.\-]+$")


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def prompt(label: str, default: str, pattern: re.Pattern[str], hint: str) -> str:
    while True:
        raw = input(f"{label} [{default}]: ").strip() or default
        if pattern.match(raw):
            return raw
        print(f"  {hint}")


def candidate_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if SKIP_DIRS & set(path.relative_to(REPO_ROOT).parts):
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        files.append(path)
    return sorted(files)


def build_replacements(name: str, prefix: str, host: str, bundle_uuid: str) -> list[tuple[str, str]]:
    # Longest first so no replacement eats another's left-hand side.
    return [
        (TEMPLATE_UUID, bundle_uuid),
        (TEMPLATE_HOST, host),
        (TEMPLATE_NAME, name),
        # Only the bundle variable's default carries the bare prefix; matching it
        # with its quotes keeps the word "tpl" in prose from being rewritten.
        (f"default: {TEMPLATE_PREFIX}\n", f"default: {prefix}\n"),
        (f'"{TEMPLATE_PREFIX}"', f'"{prefix}"'),
        (f"`{TEMPLATE_PREFIX}_", f"`{prefix}_"),
        (f"{TEMPLATE_PREFIX}_dev", f"{prefix}_dev"),
    ]


def _escaped(pair: tuple[str, str]) -> tuple[str, str]:
    """JSON-escape a replacement pair.

    Notebook source lines live inside JSON strings, so a literal `"tpl"` is
    stored on disk as `\"tpl\"` and a plain string replace never matches it.
    """
    old, new = pair
    return json.dumps(old)[1:-1], json.dumps(new)[1:-1]


def rewrite(files: list[Path], replacements: list[tuple[str, str]], dry_run: bool) -> int:
    changed = 0
    for path in files:
        try:
            original = path.read_text()
        except UnicodeDecodeError:
            continue
        pairs = replacements
        if path.suffix == ".ipynb":
            pairs = [_escaped(pair) for pair in replacements] + replacements
        updated = original
        for old, new in pairs:
            updated = updated.replace(old, new)
        if updated == original:
            continue
        changed += 1
        rel = path.relative_to(REPO_ROOT)
        print(f"  {'would update' if dry_run else 'updated'} {rel}")
        if not dry_run:
            path.write_text(updated)
    return changed


def retitle_readme(name: str, prefix: str, dry_run: bool) -> None:
    readme = REPO_ROOT / "README.md"
    if not readme.exists():
        return
    body = f"""# {name}

A Databricks Declarative Automation Bundle (DAB) project.

Unity Catalog layout: `{prefix}_dev`, `{prefix}_stage`, `{prefix}_prod`, each with
`bronze` / `silver` / `gold` schemas. Raw source data lands in `{prefix}_ingest`.

## Quickstart

```bash
cp .envrc.example .envrc      # fill in host + PAT, then: direnv allow
uv sync --group dev

databricks bundle validate --target dev
databricks bundle deploy --target dev

databricks bundle run setup_job --target dev              # once, destructive
databricks bundle run bronze_ingestion_job --target dev
databricks bundle run declarative_pipeline_silver_gold --target dev
```

## Layout

```
databricks.yml                 bundle definition: env + catalog_prefix, 3 targets
resources/                     one file per job or pipeline
src/setup/                     environment creation and seed data
src/ingestion/                 bronze: Auto Loader and Delta CDF patterns
src/silver/                    declarative pipeline: typed, deduplicated, CDC applied
src/gold/                      declarative pipeline: dimensional model
src/maintenance/               OPTIMIZE / VACUUM
src/utils/                     importable helpers, unit tested
tests/                         bundle guardrails (pure Python) + utils unit tests
.github/workflows/             pr, deploy-dev, deploy-stage, deploy-prod
```

## CI/CD

Trunk based: a single `main` plus short lived feature branches. The three deploy
targets are bundle targets, not git branches.

| Trigger | Workflow | Effect |
|---|---|---|
| PR to `main` | `pr.yml` | ruff, `bundle validate --target dev`, pytest, summary report |
| Merge to `main` | `deploy-dev.yml` | deploy to `dev` |
| Tag `v*-rc*` or manual dispatch | `deploy-stage.yml` | deploy to `stage` |
| Tag `v*` or manual dispatch | `deploy-prod.yml` | gated deploy to `prod` via the `production` GitHub Environment |

Repository secrets required: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`.

See [CLAUDE.md](CLAUDE.md) for the conventions this project holds itself to, and
[docs/mcp-setup.md](docs/mcp-setup.md) for wiring the Databricks MCP server.
"""
    print(f"  {'would rewrite' if dry_run else 'rewrote'} README.md")
    if not dry_run:
        readme.write_text(body)


def remove_template_files(dry_run: bool) -> None:
    for rel in TEMPLATE_ONLY:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        print(f"  {'would remove' if dry_run else 'removed'} {rel}")
        if not dry_run:
            path.unlink()


def reset_git_history(dry_run: bool) -> None:
    print(f"  {'would reset' if dry_run else 'resetting'} git history to a single initial commit")
    if dry_run:
        return
    git_dir = REPO_ROOT / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
    try:
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "Initial commit from template"]):
            subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        # Most often: git has no user.name / user.email configured here.
        detail = getattr(exc, "stderr", b"") or b""
        print(f"  note: could not create the initial commit ({detail.decode().strip() or exc})")
        print("  the working tree is correct; commit it yourself when git is configured")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="project and bundle name, e.g. retail_analytics")
    parser.add_argument("--catalog-prefix", help="Unity Catalog prefix, e.g. retail")
    parser.add_argument("--host", help="dev workspace URL, no trailing slash")
    parser.add_argument("--keep-git-history", action="store_true", help="do not re-init the git repo")
    parser.add_argument("--dry-run", action="store_true", help="print changes, write nothing")
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    if not (REPO_ROOT / "databricks.yml").exists():
        fail("run this from inside the project repo")

    interactive = not (args.name and args.catalog_prefix and args.host)
    if interactive and not sys.stdin.isatty():
        fail("not a terminal: pass --name, --catalog-prefix and --host")

    name = args.name or prompt(
        "Project / bundle name", "my_databricks_project", NAME_RE, "lowercase letters, digits and underscores"
    )
    if not NAME_RE.match(name):
        fail(f"invalid project name: {name}")

    prefix = args.catalog_prefix or prompt(
        "Unity Catalog prefix", name.split("_")[0], PREFIX_RE, "lowercase letters, digits and underscores"
    )
    if not PREFIX_RE.match(prefix):
        fail(f"invalid catalog prefix: {prefix}")

    host = (args.host or prompt("Dev workspace URL", TEMPLATE_HOST, HOST_RE, "e.g. https://dbc-xxxx.cloud.databricks.com")).rstrip("/")
    if not HOST_RE.match(host):
        fail(f"invalid workspace URL: {host}")

    bundle_uuid = str(uuid.uuid4())

    print()
    print(f"  bundle name    {name}")
    print(f"  catalogs       {prefix}_dev / {prefix}_stage / {prefix}_prod (+ {prefix}_ingest)")
    print(f"  dev workspace  {host}")
    print(f"  bundle uuid    {bundle_uuid}")
    print()

    needs_confirmation = not args.yes and not args.dry_run
    if needs_confirmation and input("Apply? [y/N]: ").strip().lower() not in {"y", "yes"}:
        print("aborted")
        return 1

    replacements = build_replacements(name, prefix, host, bundle_uuid)
    changed = rewrite(candidate_files(), replacements, args.dry_run)
    retitle_readme(name, prefix, args.dry_run)
    remove_template_files(args.dry_run)
    if not args.keep_git_history:
        reset_git_history(args.dry_run)

    print()
    print(f"{'would update' if args.dry_run else 'updated'} {changed} file(s).")
    if not args.dry_run:
        print("Next:")
        print("  cp .envrc.example .envrc && direnv allow")
        print("  uv sync --group dev")
        print("  databricks bundle validate --target dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
