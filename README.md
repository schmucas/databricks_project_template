# databricks_project_template

Starting point for Databricks Declarative Automation Bundle (DAB) projects on
Free Edition: three deploy targets, four GitHub Actions workflows, the bronze /
silver / gold skeleton, and a thin end-to-end example that deploys and runs on
day one.

## Start a new project

```bash
# GitHub: "Use this template", or locally:
git clone https://github.com/<you>/databricks_project_template my_new_project
cd my_new_project

python3 scripts/init_project.py
```

It asks for three things: project name, Unity Catalog prefix, dev workspace URL.

## What you get

```
databricks.yml                 bundle definition: env + catalog_prefix, 3 targets
resources/
  setup.yml                    job: create catalog, schemas, volumes, seed data
  bronze_ingestion.yml         job: Auto Loader + Delta CDF ingestion tasks
  declarative_pipeline.yml     pipeline (silver + gold) + the job that refreshes it
  maintenance.yml              job: OPTIMIZE / VACUUM
src/
  setup/environment_setup.ipynb    catalog + schema + volume creation, sample source
  ingestion/autoloader_json.ipynb  incremental file ingestion from a UC volume
  ingestion/delta_cdf.ipynb        incremental ingestion from a Delta change feed
  silver/dp_events.py              @dp.table streaming append, with expectations
  silver/dp_items.py               create_auto_cdc_flow SCD1 from the change feed
  gold/dp_agg_daily_category.py    @dp.materialized_view with PK constraint
  maintenance/optimize_tables.ipynb
  utils/transform_utils.py         importable, unit-tested helpers
tests/
  test_bundle_config.py        pure-Python guardrails, no Spark needed
  test_transform_utils.py      Spark-backed unit tests (skip without a workspace)
.github/workflows/             pr, deploy-dev, deploy-stage, deploy-prod
.mcp.json, docs/mcp-setup.md   Databricks managed MCP server for Claude Code
.claude/settings.json          plugin marketplaces enabled for the project
CLAUDE.md                      the conventions, written for Claude and for you
```

Data flow: `bronze.events_raw` + `bronze.items_raw` (job) then `silver.dp_events`
+ `silver.dp_items` then `gold.dp_agg_daily_category` (one pipeline, which
resolves silver → gold ordering itself).

## Everything is driven by two variables

`env` (dev / stage / prod) and `catalog_prefix`. The working catalog is
`<catalog_prefix>_<env>`; raw source data lands in `<catalog_prefix>_ingest`.

Nothing in `src/` hardcodes a catalog name, and a guardrail test fails the build
if something starts to. Notebooks read both values from job parameters via
`dbutils.notebook.entry_point.getCurrentBindings()`; pipeline source files read
them with `spark.conf.get(...)`, because pipelines have no widgets.

## Naming rule inside declerative pipeline

The pipeline sets `schema: silver`, so bare dataset names resolve to the silver
schema. Anything outside it is fully qualified: bronze sources and gold targets
both spell out `<catalog>.<schema>.<table>`. Moving the silver layer is
therefore a one line change in `resources/declarative_pipeline.yml`.

## Quickstart, once initialized

```bash
cp .envrc.example .envrc      # fill in host + PAT, then: direnv allow
uv sync --group dev

databricks bundle validate --target dev
databricks bundle deploy --target dev

databricks bundle run setup_job --target dev              # once, destructive
databricks bundle run bronze_ingestion_job --target dev
databricks bundle run declarative_pipeline_silver_gold --target dev
```

## CI/CD

Trunk based: a single `main` plus short lived feature branches. The three deploy
targets are bundle targets, not git branches.

| Trigger | Workflow | Effect |
|---|---|---|
| PR to `main` | `pr.yml` | ruff, `bundle validate --target dev`, pytest, summary report |
| Merge to `main` | `deploy-dev.yml` | deploy to `dev` |
| Tag `v*-rc*` or manual dispatch | `deploy-stage.yml` | deploy to `stage`, integration tests (TODO) |
| Tag `v*` or manual dispatch | `deploy-prod.yml` | gated deploy to `prod` via the `production` GitHub Environment |

Repository secrets required: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`.

Free Edition has no account console, so OAuth M2M is unavailable: use PAT auth in
Actions. If dev, stage and prod ever live in separate workspaces, move the
credentials into per Environment secrets and add `environment:` to each deploy
job.

For the prod gate: Settings, Environments, New environment `production`, then add
yourself as a required reviewer. On GitHub Free, required reviewers work only in
PUBLIC repositories. In a private repo on Free the environment still exists and
the deploy still runs, it just runs unattended with no approval step. Keep the
repo public, or treat the tag itself as the gate.
