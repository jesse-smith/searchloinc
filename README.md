# SearchLOINC

A thin [MCP](https://modelcontextprotocol.io) server wrapping the
[LOINC Search API](https://loinc.org/kb/api/search-api/) so LLMs can search LOINC the same
way a human does via [loinc.org/search](https://loinc.org/search/) — free-text,
relevance-ranked, faceted. It targets the documented Search API
(`https://loinc.regenstrief.org/searchapi/`), **not** the FHIR terminology service.

## Setup

```bash
uv sync --extra dev
cp .env.example .env   # then fill in your LOINC credentials
```

Credentials come from a free registration on [loinc.org](https://loinc.org). Set
`LOINC_USERNAME` and `LOINC_PASSWORD` in the environment (never commit them).

## Run

From a checkout (development):

```bash
uv run python -m searchloinc
```

Or install it as a standalone command and run it from anywhere:

```bash
uv tool install .          # puts a `searchloinc` executable on PATH
searchloinc                # starts the stdio server
```

Both run the server over **stdio** (the transport MCP clients expect). Point your client at
the command, or add it to your client's MCP server config. When you use the installed command,
supply credentials through the client's `env` block (sourced from your secret store / shell —
never committed):

```json
{
  "mcpServers": {
    "searchloinc": {
      "command": "searchloinc",
      "env": {
        "LOINC_USERNAME": "your-loinc-username",
        "LOINC_PASSWORD": "your-loinc-password"
      }
    }
  }
}
```

The checked-in [`.mcp.json`](.mcp.json) uses the dev form (`uv run --env-file .env`) so a local
checkout picks up credentials from `.env` automatically.

## Tools

Two-tier design — cheap compact **search** for triage, explicit **drill-in** for detail:

- `search_loincs` — LOINC terms (lab tests, vitals, measurements, panels, surveys). The main table.
- `search_answerlists` — enumerated answer sets attached to survey/nominal terms.
- `search_parts` — the LP-coded building blocks (components, systems, methods, properties).
- `search_groups` — curated collections of related terms.
- `get_loinc(code)` — drill into one term by exact code; returns the full flat record.

Each search tool takes `query` (required), `rows`, `offset`, `sortorder`, `language`, and
`include_facets`. Pick the scope that matches what you're after; results are
relevance-ranked, so if the top hits miss, **reformulate rather than deep-page**. Triage with
a search tool, then `get_loinc` the code you want.

## Output shape

Search responses are a JSON **envelope** plus a result **table**:

- The table is serialized as [TOON](https://pypi.org/project/toon-format/) — a compact tabular
  format that pays the column-name cost once, so wide uniform tables stay small. Columns are
  fixed per scope; empty fields render as `""` to preserve row uniformity. Tab-delimited
  (LOINC display values contain commas but never tabs).
- The envelope reports `requested`, `returned`, `total`, `offset`, and `truncated`.

**Character budget & pagination.** The whole serialized payload is capped at **9500 characters**
(a cushion under the ~10K downstream tool-result limit). The row-packing loop encodes and
measures the full payload incrementally and stops before the cap; when results don't all fit,
`truncated` is `true` — page forward with `offset`. `include_facets` (filter counts) is **off by
default** and opt-in; facet payloads still respect the budget.

`get_loinc` returns a single JSON object — the flat search-API record with null/empty fields
dropped (always keeping `Link`), so the field set adapts to the term type. Page-only content
(part `LP` hierarchy, language variants, curated part descriptions) is **not** in the flat
record — follow `Link` to loinc.org for it.

There is a debug-only raw-JSON path toggled by the `SEARCHLOINC_RAW_JSON` env var; it is never
exposed as an agent-facing tool parameter.

## Development

```bash
uv run ruff check searchloinc   # lint
uv run pytest                   # tests (no network; API stubbed with fixtures)
```

The [`/loinc-search`](.claude/skills/loinc-search/SKILL.md) skill drives the live API to
validate wrapper output against ground truth.

## Status

Wrapper is implemented and validated against the live API. Eventual deployment target is a
Databricks app (credentials via secret scope, inference via AI Gateway).

## License & attribution

The SearchLOINC code is licensed under the [MIT License](LICENSE).

This project wraps the LOINC Search API and includes sample LOINC API responses as test
fixtures. That LOINC (and referenced SNOMED CT) content is **not** covered by the MIT license
and remains under its own terms — see [NOTICE](NOTICE) for the required attributions.

> This material contains content from LOINC (http://loinc.org). LOINC is copyright © Regenstrief
> Institute, Inc. and the Logical Observation Identifiers Names and Codes (LOINC) Committee and is
> available at no cost under the license at http://loinc.org/license. LOINC® is a registered
> United States trademark of Regenstrief Institute, Inc.
