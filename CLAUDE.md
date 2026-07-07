# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A thin MCP server wrapping the **LOINC Search API** so LLMs can search LOINC the same
way a human does via the loinc.org/search UI. Eventually intended to run as a Databricks app.

Stack: Python (FastMCP), managed with `uv`. Credentials via environment variables.

## LOINC Search API contract

This wraps the **documented Search API** (`https://loinc.regenstrief.org/searchapi/`) — the
same backend the loinc.org/search UI calls. Do **not** confuse it with the FHIR terminology
service (`fhir.loinc.org`), which is a different, structured code-system API that does NOT
reproduce the UI's free-text relevance ranking.

- Docs: https://loinc.org/kb/api/search-api/ · auth: https://loinc.org/kb/api/auth/ ·
  syntax: https://loinc.org/kb/search/basic and /kb/search/advanced-search-syntax
- Four scoped GET endpoints — one MCP tool each is the intended design:
  `/loincs` (terms), `/answerlists`, `/parts`, `/groups`
- Query params: `query` (required), `rows`, `offset`, `sortorder` (`field asc|desc`),
  `language` (int code from `LinguisticVariants.csv`), `includefiltercounts` (bool)
- Auth: **HTTP Basic** with a LOINC username/password (register on loinc.org). Never
  hardcode — read `LOINC_USERNAME` / `LOINC_PASSWORD` from the environment.

## Development

- `uv sync` to install (`--extra dev` for ruff/pytest); `uv run <cmd>` to run inside the
  project venv (do not use system `python3`). `toon-format` is a prerelease pin (`>=0.9.0b1`).
- Run the server: `uv run python -m searchloinc` (stdio transport). Or install it as a
  standalone command with `uv tool install .` and run `searchloinc` (same stdio server via the
  `[project.scripts]` entry point → `searchloinc.__main__:main`); pass creds through the MCP
  client's `env` block, since the installed command has no `--env-file`.
- Test a live query end-to-end with the `/loinc-search` skill before trusting wrapper output.
- Format/lint with `ruff` (via `uv run ruff format` / `uv run ruff check`). Note: a save hook
  runs `ruff --fix`, which strips not-yet-used imports — add an import in the same edit as its
  first use, or it vanishes before you reference it.

## Module map

Thin layered wrapper (`searchloinc/`):

- `config.py` — static config: API base URL, `CHAR_BUDGET` (9500), TOON delimiter (tab),
  per-scope compact column sets, facet-summarization knobs, raw-JSON debug env flag.
- `client.py` — async httpx client; Basic auth from env; one `search(scope, ...)` per scope;
  surfaces non-2xx as `LoincAPIError` (creds never logged).
- `render.py` — the core mechanism: `to_compact_rows` (uniform projection), `encode_table`
  (TOON), `pack_to_budget` (char-budgeted packing), `summarize_facets`, `drop_empty_fields`.
- `server.py` — FastMCP surface: four `search_*` tools + `get_loinc` detail verb.
- `__main__.py` — `main()` runs the stdio server; reached via `python -m searchloinc` and via
  the `searchloinc` console script (`[project.scripts]` in `pyproject.toml`).

## Conventions

- polars over pandas for any dataframe work.
- Keep the wrapper thin: map MCP tool args → API params → structured response. Don't
  reimplement LOINC's ranking or filtering client-side; pass through what the API returns.
- Treat LOINC credentials as secrets. Env vars locally; Databricks secret scope when deployed.

## Databricks-app path (future)

Deployment target is a Databricks app. When we get there, the Databricks Solutions
`ai-dev-kit` (https://github.com/databricks-solutions/ai-dev-kit) has reusable skills —
reference only, not yet adopted. Inference/creds should route through governed Databricks
patterns (secret scopes, AI Gateway), not ungoverned external services.
