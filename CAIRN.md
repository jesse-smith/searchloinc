# CAIRN.md — Project Constitution

The durable rules and intent for SearchLOINC. cairn plans and acceptance gates read this as
the source of truth. Keep it stable; change it deliberately, not per-task.

## Purpose

A **thin** MCP server that wraps the LOINC Search API so an LLM can search LOINC the same way
a person does through the loinc.org/search UI — free-text, relevance-ranked, faceted.

## Non-negotiables

1. **Thin wrapper.** Map MCP tool args → LOINC Search API params → structured response.
   Do not reimplement ranking, filtering, or scoring client-side. Pass through what the API
   returns. If the UI and the API diverge, the API is ground truth — surface the divergence,
   don't paper over it.
2. **Right backend.** Target the documented Search API (`https://loinc.regenstrief.org/searchapi/`),
   NOT the FHIR terminology service (`fhir.loinc.org`). They are different systems.
3. **Credentials are secrets.** HTTP Basic auth from `LOINC_USERNAME` / `LOINC_PASSWORD` env
   vars. Never hardcode, never log, never commit. Databricks secret scope when deployed.
4. **Four scopes, four tools.** `/loincs`, `/answerlists`, `/parts`, `/groups` each map to one
   MCP tool. Keep them distinct rather than overloading one tool with a scope flag, unless a
   plan explicitly revisits this.
5. **HIPAA-aware.** This tooling is used in a clinical-research context. Don't route data
   through ungoverned external services; prefer on-prem / governed-catalog patterns.

## Stack

Python (FastMCP), `uv` for env/deps, `ruff` for format+lint. Eventual deployment target is a
Databricks app — keep the server runnable both standalone (stdio) and adaptable to that.

## Definition of done (per change)

- `uv run ruff check searchloinc` clean.
- `uv run pytest` green (add tests alongside behavior).
- Live behavior validated against the real API where relevant (see `/loinc-search` skill).
- No secret material in code, logs, or committed files.
