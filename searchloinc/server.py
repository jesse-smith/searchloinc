"""FastMCP server exposing the LOINC Search API as agent-facing tools.

Two-tier design: four scoped *search* tools return compact, relevance-ranked rows (TOON,
budget-capped) for triage; `get_loinc` drills into one code for the full flat record. Tool
descriptions teach the workflow — which scope to pick, that results are relevance-ranked
(reformulate rather than deep-page), and the cheap compact→drill-in path.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import LoincAPIError, LoincAuthError, LoincClient
from .config import (
    FILTER_COUNTS_KEY,
    RECORDS_FOUND_KEY,
    RESULTS_KEY,
    STARTING_OFFSET_KEY,
    SUMMARY_KEY,
    raw_json_enabled,
)
from .render import drop_empty_fields, pack_to_budget, to_compact_rows

mcp = FastMCP("searchloinc")

# Shared workflow guidance stitched into each search tool's description.
_WORKFLOW_NOTE = (
    "Results are relevance-ranked by the LOINC Search API (same ranking as the loinc.org/search "
    "UI); if the top hits miss, reformulate the query rather than deep-paging. Rows are compact "
    "for triage — call get_loinc(code) to drill into the full record for a specific LOINC. "
    "Output is a TOON table capped to a character budget; when truncated, page with `offset`."
)


async def _run_search(
    scope: str,
    query: str,
    rows: int,
    offset: int,
    sortorder: str | None,
    language: int | None,
    include_facets: bool,
) -> dict:
    """Shared search implementation: call the API, project compact rows, pack to budget."""
    try:
        async with LoincClient() as client:
            data = await client.search(
                scope,
                query,
                rows=rows,
                offset=offset,
                sortorder=sortorder,
                language=language,
                includefiltercounts=include_facets,
            )
    except LoincAuthError as exc:
        return {"error": "auth", "message": str(exc)}
    except LoincAPIError as exc:
        return {"error": "api", "status": exc.status_code, "message": exc.body}

    summary = data.get(SUMMARY_KEY, {})
    total = summary.get(RECORDS_FOUND_KEY, 0)
    api_offset = summary.get(STARTING_OFFSET_KEY, offset)
    api_rows = data.get(RESULTS_KEY, [])
    facets = data.get(FILTER_COUNTS_KEY) if include_facets else None

    compact = to_compact_rows(scope, api_rows)
    payload, _, _ = pack_to_budget(
        compact,
        total=total,
        offset=api_offset,
        requested=rows,
        facets=facets,
        raw_json=raw_json_enabled(),
    )
    return payload


@mcp.tool(
    description=(
        "Search LOINC terms (observations/measurements — the main LOINC table). Use this for "
        "lab tests, vital signs, clinical measurements, panels, and surveys — anything you'd "
        "look up by a test name like 'hemoglobin', 'sodium serum', or a LOINC number. "
        + _WORKFLOW_NOTE
    )
)
async def search_loincs(
    query: str,
    rows: int = 25,
    offset: int = 0,
    sortorder: str | None = None,
    language: int | None = None,
    include_facets: bool = False,
) -> dict:
    return await _run_search("loincs", query, rows, offset, sortorder, language, include_facets)


@mcp.tool(
    description=(
        "Search LOINC answer lists (the enumerated answer sets attached to survey/nominal "
        "terms, e.g. smoking-status choices). Use when you need the allowed answers for a "
        "term rather than the term itself. " + _WORKFLOW_NOTE
    )
)
async def search_answerlists(
    query: str,
    rows: int = 25,
    offset: int = 0,
    sortorder: str | None = None,
    language: int | None = None,
    include_facets: bool = False,
) -> dict:
    return await _run_search(
        "answerlists", query, rows, offset, sortorder, language, include_facets
    )


@mcp.tool(
    description=(
        "Search LOINC parts (the LP-coded building blocks — components, systems, methods, "
        "properties — that compose LOINC terms). Use when you need the canonical part behind "
        "a concept, or to explore the axis vocabulary. " + _WORKFLOW_NOTE
    )
)
async def search_parts(
    query: str,
    rows: int = 25,
    offset: int = 0,
    sortorder: str | None = None,
    language: int | None = None,
    include_facets: bool = False,
) -> dict:
    return await _run_search("parts", query, rows, offset, sortorder, language, include_facets)


@mcp.tool(
    description=(
        "Search LOINC groups (curated collections of related terms — e.g. all glucose "
        "measurements, or a molecular-conversion group). Use when you want a pre-grouped set "
        "of related LOINCs rather than individual terms. " + _WORKFLOW_NOTE
    )
)
async def search_groups(
    query: str,
    rows: int = 25,
    offset: int = 0,
    sortorder: str | None = None,
    language: int | None = None,
    include_facets: bool = False,
) -> dict:
    return await _run_search("groups", query, rows, offset, sortorder, language, include_facets)


@mcp.tool(
    description=(
        "Drill into one LOINC term by its exact code (e.g. '783-1') and return the full flat "
        "record — all populated fields (names, the six-axis parts, related names, ranks, "
        "example units, status/change history) plus `Link` to loinc.org. This is tier-2 of the "
        "search→detail workflow: triage with search_loincs, then get_loinc the code you want. "
        "Null/empty fields are dropped, so the field set adapts to the term type. Content that "
        "lives only on the loinc.org page (part LP hierarchy, language variants, curated part "
        "descriptions) is not in this record — follow `Link` for it."
    )
)
async def get_loinc(code: str) -> dict:
    """Re-query /loincs for the exact code and return the single flat record, null-dropped."""
    try:
        async with LoincClient() as client:
            data = await client.loincs(code, rows=1)
    except LoincAuthError as exc:
        return {"error": "auth", "message": str(exc)}
    except LoincAPIError as exc:
        return {"error": "api", "status": exc.status_code, "message": exc.body}

    results = data.get(RESULTS_KEY, [])
    # Guard: the search may return near-matches; only return an exact LOINC_NUM hit.
    exact = next((r for r in results if r.get("LOINC_NUM") == code), None)
    if exact is None:
        return {"error": "not_found", "code": code, "message": f"No LOINC term with code {code!r}."}
    return drop_empty_fields(exact)


__all__ = [
    "mcp",
    "search_loincs",
    "search_answerlists",
    "search_parts",
    "search_groups",
    "get_loinc",
]
