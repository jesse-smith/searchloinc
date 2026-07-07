# Facet follow-ups — deferred from the agent-facing wrapper shape slice

**Date:** 2026-07-07
**Status:** drafted  <!-- drafted | in progress | landed -->

## Goal
Capture the facet-related work deliberately deferred out of
[2026-07-06-agent-facing-wrapper-shape.md](2026-07-06-agent-facing-wrapper-shape.md) so it
isn't lost. That slice landed a *usable* facet baseline (`summarize_facets`: every group
top-5 by Count, `Version*` groups dropped, TOON-encoded with forced-uniform columns, whole
payload under the 9500-char budget). These are the refinements we chose not to fold into that
defect fix. Nothing here is a known bug — the baseline is correct; this is ergonomics + reach.

## Context (why deferred)
During verify, raw `FilterCounts` were found to run ~20K chars on broad queries (2×+ the
budget), so facets are now summarized. The summarization is intentionally blunt (uniform
top-5, no per-group intelligence) to get to something usable. Fine-tuning was punted so the
core slice could land. See that plan's "Facet-overflow decision" note for the settled baseline.

## Tasks
<!-- Each is independently shippable; order is rough priority, not a dependency chain. -->

**1. Dedicated full-facet drill-in call (progressive disclosure)**
- [ ] Add a verb that returns *one* facet group's complete value list on demand (e.g.
      `get_facet(query, scope, group)` or similar), so an agent that needs the tail beyond
      top-5 can fetch it without re-scanning. The summarized block already carries each value's
      `Search` fragment and the group `total`, so the agent knows when a drill-in is worth it.
- [ ] **CAIRN #4 gate:** this adds another verb alongside the four scopes + `get_loinc`. CAIRN
      says revisit that deliberately — this task must make the case explicitly (like the
      `get_loinc` verb did) or find a non-verb shape. Decide before building.
- [ ] Budget/serialization: a single group's full list can itself be large (glucose `System`
      had 48 values, ~broad). Reuse the char-budget + TOON machinery; page within a group if needed.

**2. Per-group facet tuning**
- [ ] Revisit the blunt uniform top-5. Some groups may warrant more values (flatter
      distributions like `Class`/`Property`) and some fewer. We tried GUI-style
      expand-Status/Class/ClassType and reverted it as not worth the special-casing — any
      per-group scheme needs to clearly beat "uniform top-5" to earn the complexity.
- [ ] Reconsider `FACET_DROP_GROUPS`. `Version*` are dropped as triage noise; confirm nothing
      else is dead weight, and that dropping is still right if the drill-in call (task 1) exists.
- [ ] Knobs live in `config.py` (`FACET_TOP_N`, `FACET_DROP_GROUPS`, `FACET_COLUMNS`).

**3. `Search`-fragment escaping ergonomics**
- [ ] The `Search` filter fragments carry double escaping in the wire output — the API's own
      regex-escaped filter syntax, then TOON-escaped, then JSON-escaped (e.g.
      `"=system:\\\\^Patient"`, codesystems `urn\\\\:iso...`). It is *correct* (an agent that
      decodes the TOON gets the API's intended `=system:\^Patient`), but visually noisy and a
      place an agent could stumble if it used the fragment without decoding.
- [ ] Decide: leave as-is (correct, documented), pre-decode before emitting, or emit the
      fragment in a form the agent can paste back into a `query` without un-escaping. Validate
      whatever we pick by round-tripping a fragment back through the live search API.

## Acceptance criteria
<!-- Per task; this is a grab-bag stub, so criteria are per-item, not one gate. -->
- Any new verb (task 1) passes the same bar as the search tools: registered, callable over
  stdio, budgeted TOON output, honest envelope, description teaches when to use it — and the
  CAIRN #4 decision is written down.
- Facet tuning (task 2) is backed by measured before/after char counts on ≥2 broad live
  queries, and doesn't regress the 9500-char budget invariant.
- Escaping decision (task 3) is validated by a live round-trip: the emitted fragment, fed back
  as a query, reproduces the expected filtered result set.
- `uv run ruff check searchloinc` clean; `uv run pytest` green; no creds in code/logs/fixtures.
