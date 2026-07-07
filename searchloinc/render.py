"""Compact-row projection, TOON serialization, and character-budget packing.

The core mechanism: turn raw API rows into a fixed, uniform compact table, serialize it as
TOON (which pays the column-name cost once — big saving on wide uniform tables), and pack as
many rows as fit under the character budget, measuring the *whole* serialized payload
post-encoding rather than estimating from per-row averages.
"""

from __future__ import annotations

import json
from typing import Any

import toon_format
from toon_format import EncodeOptions

from .config import (
    CHAR_BUDGET,
    COMPACT_COLUMNS,
    FACET_COLUMNS,
    FACET_DROP_GROUPS,
    FACET_TOP_N,
    TOON_DELIMITER,
)


def _stringify(value: Any) -> str:
    """Coerce an API field to its table-cell string.

    None and missing → "" (kept, never dropped: empties preserve TOON row uniformity, which
    is what keeps the tabular encoding compact). Everything else is str()'d; booleans and
    numbers become their natural text.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def to_compact_rows(scope: str, api_rows: list[dict]) -> list[dict[str, str]]:
    """Project raw API rows onto the scope's fixed compact column set.

    Every returned dict has exactly the scope's columns, in order, all present (empties as "").
    Non-scalar or non-compact API fields are dropped — they belong to tier-2 drill-in.
    """
    if scope not in COMPACT_COLUMNS:
        raise ValueError(f"No compact column set for scope {scope!r}.")
    columns = COMPACT_COLUMNS[scope]
    return [{col: _stringify(row.get(col)) for col in columns} for row in api_rows]


def encode_table(rows: list[dict[str, str]], delimiter: str = TOON_DELIMITER) -> str:
    """Serialize a list of uniform row dicts as a TOON tabular array."""
    return toon_format.encode(rows, EncodeOptions(delimiter=delimiter))


def _serialize_payload(payload: dict) -> str:
    """Serialize the full tool payload exactly as it will go over the wire, for measurement.

    ensure_ascii=False so multi-byte characters are counted as the single characters they are
    (the downstream cap is on characters, not bytes).
    """
    return json.dumps(payload, ensure_ascii=False)


def summarize_facets(filter_counts: dict) -> dict:
    """Summarize raw API FilterCounts into a compact, TOON-encoded facet block.

    Every group is minimized to its top FACET_TOP_N values by Count, and pure-noise
    version-history groups (FACET_DROP_GROUPS) are dropped entirely. Raw FilterCounts run ~20K
    chars on broad queries; this lands them well under budget.

    Each group's entries are projected onto FACET_COLUMNS (uniform, empty Description -> "")
    so TOON can use its compact tabular form, then TOON-encoded. Every group reports `shown`
    and `total`; each value keeps its `Search` filter fragment, so an agent can re-query the
    tail. Returns {group: {"values_toon": str, "shown": int, "total": int}}.
    """
    summary: dict[str, Any] = {}
    for group, entries in filter_counts.items():
        if group in FACET_DROP_GROUPS:
            continue
        if not isinstance(entries, list):
            continue
        ordered = sorted(entries, key=lambda e: e.get("Count", 0), reverse=True)
        shown = ordered[:FACET_TOP_N]
        uniform = [{col: _stringify(entry.get(col)) for col in FACET_COLUMNS} for entry in shown]
        summary[group] = {
            "values_toon": encode_table(uniform),
            "shown": len(uniform),
            "total": len(entries),
        }
    return summary


def build_payload(
    rows: list[dict[str, str]],
    *,
    total: int,
    offset: int,
    requested: int,
    truncated: bool,
    facets: Any = None,
    raw_json: bool = False,
) -> dict:
    """Assemble the tool response: honest envelope + the result table.

    Envelope stays JSON; the table is TOON unless `raw_json` (debug path), where rows are
    embedded as JSON instead. `returned` always reflects the rows actually included.

    `facets`, when present, is the raw API FilterCounts. It is summarized + TOON-encoded via
    summarize_facets — except under `raw_json`, where the full raw block passes through so the
    debug path shows everything.
    """
    payload: dict[str, Any] = {
        "requested": requested,
        "returned": len(rows),
        "total": total,
        "offset": offset,
        "truncated": truncated,
    }
    if raw_json:
        payload["results"] = rows
    else:
        payload["results_toon"] = encode_table(rows)
    if facets is not None:
        payload["facets"] = facets if raw_json else summarize_facets(facets)
    return payload


def drop_empty_fields(record: dict, *, always_keep: tuple[str, ...] = ("Link",)) -> dict:
    """Tier-2 detail projection: drop null/empty fields, always keep `always_keep`.

    Dynamic null-drop (not a static allowlist) so it self-adapts across term types — panels
    keep `PanelType`, surveys keep `ExampleAnswers`, calculated terms keep `FORMULA`, while null
    HL7/survey/attachment cruft falls away. "Empty" = None, "", [], or {}. Fields in
    `always_keep` are retained even if empty (the agent always needs `Link` to hand off).
    """

    def _is_empty(value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}

    return {
        key: value for key, value in record.items() if key in always_keep or not _is_empty(value)
    }


def pack_to_budget(
    rows: list[dict[str, str]],
    *,
    total: int,
    offset: int,
    requested: int,
    budget: int = CHAR_BUDGET,
    facets: Any = None,
    raw_json: bool = False,
) -> tuple[dict, str, int]:
    """Include as many rows as fit under `budget`, measuring the whole encoded payload.

    Incrementally grows the row prefix, re-encoding and re-measuring the *entire* serialized
    payload each step (TOON's per-row width varies, so averaging is wrong), and keeps the
    largest prefix whose serialization is ≤ budget.

    `truncated` is honest: True whenever more results exist than are returned — either budget
    forced a partial page, or the API's `total` exceeds `offset + returned`.

    Returns (payload_dict, serialized_str, fit_count).
    """

    def _payload_for(n: int) -> tuple[dict, str]:
        prefix = rows[:n]
        more = (n < len(rows)) or (offset + n < total)
        payload = build_payload(
            prefix,
            total=total,
            offset=offset,
            requested=requested,
            truncated=more,
            facets=facets,
            raw_json=raw_json,
        )
        return payload, _serialize_payload(payload)

    # Grow the prefix one row at a time; stop at the largest that still fits.
    fit = 0
    best_payload, best_serialized = _payload_for(0)
    for n in range(1, len(rows) + 1):
        payload, serialized = _payload_for(n)
        if len(serialized) > budget:
            break
        fit = n
        best_payload, best_serialized = payload, serialized

    return best_payload, best_serialized, fit
