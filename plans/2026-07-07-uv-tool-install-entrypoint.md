# uv tool install entry point — standalone `searchloinc` command

**Date:** 2026-07-07
**Status:** landed (2026-07-07)  <!-- drafted | in progress | landed -->

## Goal
The wrapper runs today only as `uv run python -m searchloinc` from a checkout. Make it an
installable console command so `uv tool install .` (and `uv tool install` from a future
published/VCS source) puts a `searchloinc` executable on PATH that starts the stdio MCP
server. This is the last step before it can be pointed at from an MCP client config without a
working-copy checkout — and a prerequisite for the Databricks-app path later.

## Architecture
- **Entry point.** Add a `[project.scripts]` table to `pyproject.toml`:
  `searchloinc = "searchloinc.__main__:main"`. `main()` already exists (`__main__.py:8`) and
  calls `mcp.run(transport="stdio")` — no code change needed to the server; the console script
  just becomes a second way to reach the same `main()`. hatchling already builds the
  `searchloinc/` package (build-backend set), so no packaging config beyond the script table.
- **Credential delivery (the one real decision).** Today `.mcp.json` injects creds via
  `uv run --env-file .env`. An installed `searchloinc` command has no `--env-file`. Keep the
  wrapper thin and env-only (CAIRN #3): the installed command reads `LOINC_USERNAME` /
  `LOINC_PASSWORD` from its inherited environment, exactly as `client.py:_credentials()`
  already does. Credentials reach it via the MCP client config's `env` block (values sourced
  from the user's secret store / shell, never committed) — **not** by adding a `python-dotenv`
  dependency and **not** by committing creds into `.mcp.json`. This preserves "credentials are
  secrets" and adds zero dependencies. `.mcp.json` for the local checkout can stay as-is (dev
  convenience); the README documents the installed-command form separately.
- **No new runtime surface.** No new tools, flags, or transports. `LoincAuthError` still
  surfaces lazily on first tool call if creds are absent — acceptable for a stdio server;
  starting the process without creds is not itself an error.

## Tech Stack
- `pyproject.toml` `[project.scripts]` (PEP 621 console_scripts), hatchling build backend
  (already configured).
- `uv tool install` / `uv tool uninstall` for the install lifecycle.
- Existing: FastMCP (`mcp[cli]`), httpx.

## Tasks
<!-- Concrete file paths and code. NO placeholders. -->
- [x] Add `[project.scripts]` to `pyproject.toml` with
      `searchloinc = "searchloinc.__main__:main"` (place after `[project.optional-dependencies]`,
      before `[tool.ruff]`).
- [x] Verify `main()` in `searchloinc/__main__.py` is import-safe as a console entry point:
      confirm module import has no side effects beyond defining `mcp`/`main` (it imports
      `.server`; check `server.py` does no work at import time that would break a bare
      `searchloinc` invocation). — Confirmed: `server.py` only builds `mcp = FastMCP(...)` and
      registers tools at import; `LoincClient()` (creds read) is lazy inside each tool call.
- [x] Build-sanity: run `uv build` and confirm the wheel's entry-points metadata contains the
      `searchloinc` console script (e.g. inspect `dist/*.whl` `entry_points.txt`). — Wheel
      `entry_points.txt` shows `[console_scripts]\nsearchloinc = searchloinc.__main__:main`.
- [x] Install end-to-end: `uv tool install .`, then confirm `which searchloinc` resolves and
      `searchloinc` starts the stdio server (it should block reading stdin; a clean start with
      no traceback is the pass). Clean up with `uv tool uninstall searchloinc` after. —
      `which searchloinc` → `~/.local/bin/searchloinc`; process ran alive as stdio server with
      no traceback; uninstalled after.
- [x] Update `README.md` "Run" section: document `uv tool install .` → `searchloinc` as the
      standalone invocation, and show an MCP client config that runs `command: "searchloinc"`
      with credentials supplied via the client's `env` block (referencing `LOINC_USERNAME` /
      `LOINC_PASSWORD`), alongside the existing `uv run python -m searchloinc` dev form.
- [x] Update `CLAUDE.md` "Development" section to mention the installed-command path
      (`uv tool install .` → `searchloinc`) next to `uv run python -m searchloinc`.

## Acceptance criteria
<!-- What cairn-accept checks before "landed". Conditions, not steps. -->
- `uv tool install .` succeeds and puts a `searchloinc` executable on PATH (`which searchloinc`
  resolves inside the uv tools shim dir).
- Running `searchloinc` with `LOINC_USERNAME` / `LOINC_PASSWORD` set starts the stdio MCP
  server with no traceback and serves the same four `search_*` tools + `get_loinc` as
  `python -m searchloinc` (behavior parity — the console script is just another route to
  `main()`).
- No credentials are committed; the installed command reads them from the environment only
  (no `python-dotenv` dependency added, no creds in `.mcp.json`).
- `uv run ruff check searchloinc` clean and `uv run pytest` green (no regression; existing
  `python -m searchloinc` path still works).
- README and CLAUDE.md document the standalone `searchloinc` command and how credentials reach
  it when installed.
