# Maintaining this template

Notes for the template repo itself. `scripts/init_project.py` deletes this file
when a project is initialized, so nothing here follows you into a real project.

## The placeholder identity

Four literals carry the template's identity. The init script replaces all four:

| Literal | Lives in | Becomes |
|---|---|---|
| `databricks_project_template` | `databricks.yml`, `pyproject.toml`, README | the project name |
| `tpl` | `catalog_prefix` default in `databricks.yml`, notebook fallbacks | the catalog prefix |
| `https://your-workspace.cloud.databricks.com` | dev target in `databricks.yml` | the dev workspace URL |
| `00000000-0000-0000-0000-000000000000` | `bundle.uuid` | a fresh UUID |

They are real, valid values rather than `{{MUSTACHE}}` placeholders, so the
template repo itself stays lintable, testable and `bundle validate`-able. Its own
CI is therefore a real check on the template.

If you add a fifth thing that needs rewriting, add it to `build_replacements()`
and to this table.

## Checks before committing a change to the template

```bash
uv sync --group dev
uv run ruff check .
uv run pytest tests/test_bundle_config.py -v     # pure Python, no workspace needed
databricks bundle validate --target dev          # needs a workspace
```

And dry-run the init script, which should report every file it would touch:

```bash
python3 scripts/init_project.py --name check_me --catalog-prefix chk \
    --host https://example.cloud.databricks.com --dry-run
```

## What belongs here, and what does not

Belongs: anything every project needs on day one and would otherwise be
copy-pasted, plus one worked example per pattern so the shape is obvious.

Does not belong: a specific project's business logic; a second example of a
pattern already shown; anything that cannot be deleted in under a minute. The
example is meant to be thrown away, so keep it small enough that throwing it away
is easy.

## Keeping the guardrails honest

`tests/test_bundle_config.py` encodes the conventions in `CLAUDE.md`. When a
convention changes, change both. A convention with no test is a suggestion.
