# Agent-facing wrapper shape — two-tier search + detail, char-budgeted TOON output

**Date:** 2026-07-06
**Status:** landed (2026-07-07)  <!-- drafted | in progress | landed -->

## Goal
Shape the LOINC Search API MCP wrapper so an agent can use it effectively: informative,
workflow-teaching tool descriptions and a robust mechanism for keeping results under the
downstream ~10K-character tool-result cap. The design is **two-tier** — cheap compact search
for triage, explicit drill-in for detail — with tabular results serialized in TOON to fit the
character budget while preserving the API's relevance ranking (CAIRN non-negotiable #1).

## Architecture
Settled decisions from `/cairn:brainstorm` (see CAIRN.md for the durable non-negotiables):

- **Two-tier.** Four scoped search tools (`/loincs`, `/answerlists`, `/parts`, `/groups`) return
  *compact* rows for triage. A separate `get_loinc(code)` detail **verb** returns the detail
  record for one code. This adds a verb alongside the four scope tools — CAIRN #4 says revisit
  that deliberately; this plan does, and keeps it (a verb is not a fifth scope). Detail tool is a
  plain MCP **tool, not a resource** (model-initiated drill-in; universal client support incl. the
  future Databricks app; payload is small so no laziness win).
- **`get_loinc` = tier 2 (flat search-API record), confirmed against live 783-1.** There is **no
  separate detail endpoint**; `get_loinc` re-queries the search API for the exact code and returns
  the single flat record (~50 fields). It returns **all non-null/non-empty fields, always keeping
  `Link`** (dynamic null-drop, not a static allowlist — self-adapts across term types so panels
  keep `PanelType`, surveys keep `ExampleAnswers`, calculated terms keep `FORMULA`, while null HL7/
  survey/attachment cruft is dropped). Single object, so the 9500-char budget does not apply.
  **Explicitly out of scope** (page-only content the flat record does NOT carry, per the
  783-1 vs loinc.org/783-1 comparison): part `LP` codes and the numerator/denominator part
  hierarchy, bundled language variants, and curated part-level descriptions. The record's `Link`
  field points to loinc.org for that deeper content — surface it so the agent can hand off.
  See fixture `tests/fixtures/loincs_783-1.json`.
- **Compact column set** (LOINC search / `/loincs`): the loinc.org/search GUI columns minus
  Version First Released, Version Last Changed, and Copyright →
  `Status, LOINC, LongCommonName, Component, Property, Timing, System, Scale, Method, Class,
  Type, ExampleUCUMUnits, Order/Observation, Rank`. Other scopes get their own compact sets
  (confirm primary display fields per scope against live API).
- **Character budget.** The whole *serialized envelope* (rows + envelope fields + any facet
  sidecar) must fit under a cap set below the ~10K-char downstream limit — target **9500** as a
  cushion. Measurement is **post-encoding**: the row-packing loop encodes-and-measures the whole
  payload incrementally and stops before the cap. No estimating from per-row byte averages
  (TOON's variable per-row width makes averages wrong).
- **Overflow → pagination.** When results exceed one page, page via `offset`. The envelope is
  explicit about `requested`, `returned`, `total`, `offset`, and `truncated`. We do *not* nudge
  the agent to narrow — agents narrow on their own.
- **Facets** (`includefiltercounts`): **off by default**, opt-in `include_facets` arg. Large,
  orthogonal to rows, would blow the budget if default-on.
  - **Facet-overflow decision (2026-07-07, resolved during verify).** Raw `FilterCounts` run
    ~20K chars on broad queries (glucose 21.7K, sodium 19.1K) — 2×+ the whole budget alone, so
    row-trimming alone can't fit them (it starved rows to 0). Chosen strategy: `summarize_facets`
    (a) **TOON-encodes** each group with **forced-uniform columns** (`Label, Count, Description,
    Search`; empty Description → `""`), (b) caps **every** group at **top-`FACET_TOP_N`=5 by
    Count** (no group expanded in full — we tried GUI-style expand-Status/Class/ClassType but it
    wasn't worth the special-casing), (c) **drops** `VersionFirstReleased`/`VersionLastChanged`
    (pure triage noise, the biggest char sink). Result: glucose facets-on 21.7K→5.3K, sodium
    →4.8K, under budget with rows preserved. Each group still reports `shown`/`total` and every
    value keeps its `Search` filter fragment, so an agent can re-query the dropped tail.
    `pack_to_budget`'s row-trim remains the final backstop. The raw-JSON debug path passes
    **un-summarized** facets through (debug = see everything). Per-group fine-tuning (which
    groups matter, how many values each) is explicit follow-up work.
  - **Deferred follow-up (own plan item):** a dedicated full-facet drill-in *call* (progressive
    disclosure — let an agent fetch a single group's complete value list on demand). Touches
    CAIRN #4 (another verb), so it belongs in its own plan, not folded into this defect fix.
- **TOON for the result table.** Uniform tabular array (`[N]{cols}:` + one line/row) pays the
  column-name cost once — big character saving on wide uniform tables. Rules:
  - **Fixed columns, always all present.** Empty fields serialize as empty string, **never
    omitted** — dropping fields breaks row uniformity and forces TOON's verbose fallback, which
    destroys the savings. (Reverses the usual "drop nulls" instinct; uniformity beats sparsity.)
  - **Delimiter.** Confirm empirically (live query) whether LOINC display values ever contain the
    delimiter. Default comma; switch to **tab** if commas appear in values (avoids quoting/escape
    overhead). Whichever delimiter, encoder must handle escaping correctly.
- **Envelope + detail responses stay JSON.** TOON only earns its keep on the multi-row table.
  The envelope is a single non-tabular object; `get_loinc` returns a single object. JSON there.
- **JSON escape hatch is debug-only, NOT on the MCP surface.** A raw-JSON (un-TOON'd) response
  path for debugging, toggled by env var / internal flag — never an agent-facing tool parameter.
- **Tool descriptions teach the workflow, not the ontology.** (a) when to pick which scope,
  (b) results are relevance-ranked so reformulating beats deep paging, (c) the compact→drill-in
  path so the agent knows the cheap route.

## Tech Stack
Python (FastMCP / `mcp[cli]`), `httpx` for the API calls, `toon-format` (toon-python) for tabular
serialization, `uv` env, `ruff`, `pytest`. HTTP Basic auth from `LOINC_USERNAME`/`LOINC_PASSWORD`.

## Tasks
<!-- Order roughly = build order. File paths concrete; confirm-against-live items flagged. -->

**Groundwork / confirm-against-live (do first, informs the rest)**
- [x] Add `toon-format` to `pyproject.toml` dependencies; `uv sync`. Pinned `toon-format>=0.9.0b1`
      (the 0.1.0 stable is a namespace stub; 0.9.0b1 is the first functional release). API:
      `toon_format.encode(obj, EncodeOptions(delimiter="\t"))`; `EncodeOptions` is a TypedDict and
      `delimiter` is a plain string (use `toon_format.constants.TAB`), *not* an `encode()` kwarg.
      Encoder quotes any value containing the delimiter, so escaping is handled for us.
- [x] `/loincs` confirmed live against 783-1 → `tests/fixtures/loincs_783-1.json`. Envelope =
      `ResponseSummary` with `RecordsFound` (→ total), `StartingOffset` (→ offset), `RowsReturned`
      (→ returned); rows under `Results`. Flat record ~50 fields incl. all name forms, parts,
      `RELATEDNAMES2`, `CHANGE_REASON_PUBLIC`, ranks, `Link`.
- [x] Capture fixtures for the other three scopes (`/answerlists`, `/parts`, `/groups`) to
      `tests/fixtures/`; record each scope's envelope + primary display fields (may differ from
      `/loincs`). Captured live: `answerlists_smoking.json`, `parts_hemoglobin.json`,
      `groups_glucose.json` (all HTTP 200, creds verified absent from files).
      **Envelope is identical across all four scopes:** `ResponseSummary` with `RecordsFound`
      (→ total), `StartingOffset` (→ offset), `RowsReturned` (→ returned); rows under `Results`;
      `FilterCounts` sidecar when `includefiltercounts=true`. Multi-result responses also carry
      `ResponseSummary.Next` (a ready-made next-page URL) — informational; we page via `offset`.
- [x] Confirm the compact column set per scope. **Delimiter: TAB (confirmed).** Across all four
      fixtures (777 string values) **zero contained a tab**, while commas *do* appear in real
      values — `parts.Classlist` ("CHEM, DRUG/TOX", comma-joined) and `groups` values use `,` `|`
      `^` `<>` `:` structurally. Comma-as-delimiter would force quoting on common rows; tab never
      does. Encoder still escapes defensively. **Compact column sets** (primary display scalars —
      nested arrays `Answers`/`Loincs`, the comma-joined `parts.Classlist`, and detail free-text
      are drill-in only, excluded from the table):
      - `/answerlists`: `AnswerListId, Name, ExtDefinedYN, Link`
      - `/parts`: `PartNumber, PartTypeName, PartName, PartDisplayName, Status, Link`
      - `/groups`: `ParentGroupId, ParentGroup, GroupId, Group, STATUS, Category, Link`
      (`/loincs` compact set already fixed above in Architecture.)

**Core client + config**
- [x] `searchloinc/client.py`: thin async httpx client. Basic-auth from env; one method per scope
      GET (`query`, `rows`, `offset`, `sortorder`, `language`, `includefiltercounts` params);
      raise/surface non-2xx with status+body (creds never logged). `LoincAuthError` on missing
      creds, `LoincAPIError(status, body)` on non-2xx, `ValueError` on unknown scope. Validated
      live against 783-1 + parts/hemoglobin (incl. filter-counts opt-in) and the no-creds path.
- [x] `searchloinc/config.py`: budget constant (`CHAR_BUDGET = 9500`), delimiter (`TOON_DELIMITER`
      = tab), debug-JSON env flag (`SEARCHLOINC_RAW_JSON` via `raw_json_enabled()`), compact column
      maps per scope, and the shared `ResponseSummary`/`Results`/`FilterCounts` envelope keys.

**Serialization + budgeting (the core mechanism)**
- [x] `searchloinc/render.py`: `to_compact_rows(scope, api_rows)` → list of uniform dicts (fixed
      columns, empties as `""`). `encode_table(rows, delimiter)` → TOON string.
- [x] `searchloinc/render.py`: `pack_to_budget(rows, envelope, budget)` — incrementally add rows,
      re-encode the *full* payload (TOON table + JSON envelope), stop before budget; return packed
      rows + how many fit. Envelope fields: `requested`, `returned`, `total`, `offset`,
      `truncated`. Debug flag bypasses TOON (raw JSON) but still reports the envelope honestly.
      `truncated` is honest about both causes (budget cutoff *and* more API pages beyond
      `offset+returned`). Measurement is post-encoding on the full JSON payload
      (`ensure_ascii=False`, char-accurate). `build_payload` assembles envelope+table/rows.
- [x] Unit tests `tests/test_render.py`: uniformity (empty fields kept as `""`), TOON round-trip/
      shape, delimiter escaping, and **budget invariant** (packed payload always ≤ budget; a
      wide/long fixture forces a partial page with `truncated: true` and a usable `offset`).
      16 tests, all green; also live-verified on `glucose` (1024 hits → 47 rows packed @ 9433 ch).

**MCP surface**
- [x] `searchloinc/server.py`: FastMCP server; four search tools (`search_loincs`,
      `search_answerlists`, `search_parts`, `search_groups`) — args `query`, `rows`, `offset`,
      `sortorder`, `language`, `include_facets` (default False); plus `get_loinc(code)` detail
      tool that re-queries `/loincs` for the exact code and returns the flat record as JSON,
      **dropping all null/empty fields, always keeping `Link`**. Descriptions teach
      scope-selection + compact→drill-in + ranking/paging behavior. `get_loinc` guards on an
      exact `LOINC_NUM` match (returns `not_found` otherwise). Auth/API errors surface as
      structured `{"error": ...}` payloads rather than raising into the transport.
- [x] `searchloinc/__main__.py`: `python -m searchloinc` runs the stdio server. Smoke-tested:
      completes the MCP `initialize` handshake over stdio.
- [x] Tests `tests/test_server.py`: tools registered with expected schemas; search tool over a
      fixture returns budgeted TOON + honest envelope; `include_facets=True` adds the sidecar and
      still respects the budget; `get_loinc` returns the flat record with null/empty fields
      dropped and `Link` present (assert over the 783-1 fixture). 27 tests total green; API stubbed
      with a fake client (no network/creds in tests). Also live-drove all five tools end-to-end.

**Docs**
- [x] Update `README.md`: two-tier model, TOON output, char budget/pagination, run command.

## Acceptance criteria
<!-- What cairn-accept checks before "landed". Conditions, not steps. -->
- `uv run ruff check searchloinc` clean; `uv run pytest` green.
- All four search tools + `get_loinc` are registered and callable over stdio; descriptions
  convey scope-selection and the compact→drill-in workflow.
- Search results serialize as TOON with a fixed, uniform column set (empties as `""`), and the
  **full serialized payload is always ≤ 9500 characters** — verified on a fixture large enough to
  force truncation.
- When truncated, the response envelope reports `requested`, `returned`, `total`, `offset`, and
  `truncated`, and paging via `offset` returns the next page.
- `include_facets` is off by default and opt-in; facet payloads still respect the budget.
- The raw-JSON debug path is reachable only via env/internal flag — not exposed as an MCP tool
  parameter.
- No credentials in code, logs, or committed fixtures; behavior validated against the live API.
