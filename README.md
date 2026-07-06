# SearchLOINC

A thin [MCP](https://modelcontextprotocol.io) server wrapping the
[LOINC Search API](https://loinc.org/kb/api/search-api/) so LLMs can search LOINC the same
way a human does via [loinc.org/search](https://loinc.org/search/).

## Setup

```bash
uv sync --extra dev
cp .env.example .env   # then fill in your LOINC credentials
```

Credentials come from a free registration on [loinc.org](https://loinc.org). Set
`LOINC_USERNAME` and `LOINC_PASSWORD` in the environment (never commit them).

## Status

Early scaffold. The server wraps four scoped endpoints — `/loincs`, `/answerlists`,
`/parts`, `/groups` — one MCP tool each. Intended to eventually run as a Databricks app.
