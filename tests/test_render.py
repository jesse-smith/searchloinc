"""Tests for compact-row projection, TOON serialization, and budget packing."""

from __future__ import annotations

import json
from pathlib import Path

import toon_format

from searchloinc.config import (
    COMPACT_COLUMNS,
    FACET_DROP_GROUPS,
    FACET_TOP_N,
    TOON_DELIMITER,
)
from searchloinc.render import (
    build_payload,
    drop_empty_fields,
    encode_table,
    pack_to_budget,
    summarize_facets,
    to_compact_rows,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _results(name: str) -> list[dict]:
    return _load(name)["Results"]


# --- to_compact_rows: uniformity -------------------------------------------


def test_compact_rows_have_exactly_the_scope_columns():
    rows = to_compact_rows("loincs", _results("loincs_783-1.json"))
    assert rows, "fixture should yield at least one row"
    for row in rows:
        assert list(row.keys()) == COMPACT_COLUMNS["loincs"]


def test_empty_and_missing_fields_kept_as_empty_string():
    # A row missing every compact column must still emit all columns as "".
    rows = to_compact_rows("loincs", [{}])
    assert list(rows[0].keys()) == COMPACT_COLUMNS["loincs"]
    assert all(v == "" for v in rows[0].values())


def test_none_values_become_empty_string_not_the_word_none():
    rows = to_compact_rows("loincs", [{"METHOD_TYP": None, "LOINC_NUM": "1-1"}])
    assert rows[0]["METHOD_TYP"] == ""
    assert rows[0]["LOINC_NUM"] == "1-1"


def test_numeric_and_bool_fields_stringified():
    rows = to_compact_rows("loincs", [{"CLASSTYPE": 1, "COMMON_TEST_RANK": 354}])
    assert rows[0]["CLASSTYPE"] == "1"
    assert rows[0]["COMMON_TEST_RANK"] == "354"


def test_all_scopes_project_uniform_rows():
    cases = {
        "answerlists": "answerlists_smoking.json",
        "parts": "parts_hemoglobin.json",
        "groups": "groups_glucose.json",
    }
    for scope, fixture in cases.items():
        rows = to_compact_rows(scope, _results(fixture))
        assert rows
        for row in rows:
            assert list(row.keys()) == COMPACT_COLUMNS[scope]


# --- encode_table: TOON shape + round-trip + escaping ----------------------


def test_encode_table_round_trips():
    rows = to_compact_rows("loincs", _results("loincs_783-1.json"))
    encoded = encode_table(rows)
    decoded = toon_format.decode(encoded)
    assert decoded == rows


def test_encode_uses_tab_delimiter_and_header():
    rows = to_compact_rows("parts", _results("parts_hemoglobin.json"))
    encoded = encode_table(rows)
    header = encoded.splitlines()[0]
    # Tabular header lists the columns joined by the delimiter.
    assert TOON_DELIMITER.join(COMPACT_COLUMNS["parts"]) in header


def test_delimiter_bearing_value_is_escaped_not_split():
    # A value containing a tab must not break row structure: it round-trips intact.
    rows = [{"a": "x\ty", "b": "z"}]
    encoded = encode_table(rows)
    assert toon_format.decode(encoded) == rows


def test_comma_values_are_safe_under_tab_delimiter():
    # Real data (parts.Classlist, groups) contains commas; tab delimiter must keep them inline.
    rows = [{"a": "CHEM, DRUG/TOX", "b": "Glucose^Pt|Ser/Plas"}]
    encoded = encode_table(rows)
    assert toon_format.decode(encoded) == rows


# --- pack_to_budget: the budget invariant ----------------------------------


def _wide_rows(n: int) -> list[dict[str, str]]:
    """Synthesize n wide/long compact rows to force truncation under the budget."""
    filler = "Promyelocytes/Leukocytes in Blood by Manual count " * 3
    return [{col: f"{col}-{i}-{filler}" for col in COMPACT_COLUMNS["loincs"]} for i in range(n)]


def test_packed_payload_never_exceeds_budget():
    rows = _wide_rows(500)
    budget = 9500
    payload, serialized, fit = pack_to_budget(
        rows, total=500, offset=0, requested=500, budget=budget
    )
    assert len(serialized) <= budget
    assert payload["returned"] == fit
    assert 0 < fit < len(rows), "wide fixture should force a partial page"


def test_truncation_sets_flag_and_usable_offset():
    rows = _wide_rows(500)
    payload, _, fit = pack_to_budget(rows, total=500, offset=0, requested=500, budget=9500)
    assert payload["truncated"] is True
    # Next page starts where this one ended.
    next_offset = payload["offset"] + payload["returned"]
    assert next_offset == fit
    assert next_offset < payload["total"]


def test_no_truncation_when_everything_fits():
    rows = to_compact_rows("loincs", _results("loincs_783-1.json"))
    payload, serialized, fit = pack_to_budget(rows, total=1, offset=0, requested=5)
    assert fit == len(rows)
    assert payload["truncated"] is False
    assert payload["returned"] == 1


def test_truncated_true_when_more_pages_exist_even_if_page_fits():
    # One row returned but total says there are more → truncated must be honest.
    rows = to_compact_rows("parts", _results("parts_hemoglobin.json"))
    payload, _, _ = pack_to_budget(rows, total=202, offset=0, requested=5)
    assert payload["truncated"] is True


def test_envelope_fields_present_and_typed():
    rows = to_compact_rows("loincs", _results("loincs_783-1.json"))
    payload, _, _ = pack_to_budget(rows, total=1, offset=0, requested=5)
    for key in ("requested", "returned", "total", "offset", "truncated"):
        assert key in payload
    assert "results_toon" in payload
    assert isinstance(payload["results_toon"], str)


def test_raw_json_debug_path_embeds_rows_and_keeps_envelope():
    rows = to_compact_rows("loincs", _results("loincs_783-1.json"))
    payload = build_payload(rows, total=1, offset=0, requested=5, truncated=False, raw_json=True)
    assert "results" in payload and "results_toon" not in payload
    assert payload["results"] == rows
    # Envelope stays honest regardless of encoding.
    assert payload["returned"] == len(rows)


# --- drop_empty_fields (tier-2 detail projection) --------------------------


def test_drop_empty_fields_removes_empties_keeps_link():
    record = _results("loincs_783-1.json")[0]
    dropped = drop_empty_fields(record)
    # Null/empty fields from the fixture are gone.
    assert "FORMULA" not in dropped
    assert "ExampleAnswers" not in dropped
    assert "TermDescriptions" not in dropped  # was []
    # Populated fields and Link survive.
    assert dropped["LOINC_NUM"] == "783-1"
    assert dropped["Link"] == "https://loinc.org/783-1"


def test_drop_empty_fields_keeps_link_even_if_empty():
    dropped = drop_empty_fields({"LOINC_NUM": "1-1", "Link": ""})
    assert dropped["Link"] == ""
    assert dropped["LOINC_NUM"] == "1-1"


def test_drop_empty_fields_preserves_falsey_nonempty_values():
    # 0 and "0"-like ranks are meaningful, not empty — must survive.
    dropped = drop_empty_fields({"COMMON_ORDER_RANK": 0, "x": None}, always_keep=())
    assert dropped["COMMON_ORDER_RANK"] == 0
    assert "x" not in dropped


# --- summarize_facets (Bug 1 regression: raw facets blew the budget) --------


def _facets(name: str) -> dict:
    return _load(name)["FilterCounts"]


def test_summarize_facets_drops_version_groups():
    summary = summarize_facets(_facets("loincs_glucose_facets.json"))
    for group in FACET_DROP_GROUPS:
        assert group not in summary


def test_summarize_facets_caps_every_group_at_top_n():
    raw = _facets("loincs_glucose_facets.json")
    summary = summarize_facets(raw)
    # Every kept group is capped at FACET_TOP_N (no group is expanded in full), while `total`
    # always reflects the full pre-cap count so the agent knows the tail exists.
    for group, block in summary.items():
        assert block["shown"] == min(FACET_TOP_N, len(raw[group]))
        assert block["total"] == len(raw[group])
    # System has more values than the cap in the fixture — so it genuinely exercises truncation.
    assert len(raw["System"]) > FACET_TOP_N
    assert summary["System"]["shown"] == FACET_TOP_N


def test_summarize_facets_keeps_highest_counts_and_is_toon():
    summary = summarize_facets(_facets("loincs_glucose_facets.json"))
    decoded = toon_format.decode(summary["System"]["values_toon"])
    counts = [int(row["Count"]) for row in decoded]
    assert counts == sorted(counts, reverse=True), "top-N keeps the highest counts, in order"
    # Search filter fragment is preserved so the agent can re-query the dropped tail.
    assert all(row["Search"] for row in decoded)


def test_large_facets_respect_budget_and_preserve_rows():
    # THE Bug 1 regression: raw glucose facets are ~21K chars. Summarized + packed with rows,
    # the whole payload must fit the budget AND still return rows (not starve them to zero).
    fixture = _load("loincs_glucose_facets.json")
    rows = to_compact_rows("loincs", fixture["Results"])
    total = fixture["ResponseSummary"]["RecordsFound"]
    payload, serialized, fit = pack_to_budget(
        rows, total=total, offset=0, requested=5, facets=fixture["FilterCounts"]
    )
    assert len(serialized) <= 9500
    assert payload["returned"] > 0, "facets must not starve the row table to zero"
    assert "facets" in payload


def test_facets_included_when_provided():
    rows = to_compact_rows("loincs", _results("loincs_783-1.json"))
    payload, serialized, _ = pack_to_budget(
        rows, total=1, offset=0, requested=5, facets=_facets("loincs_glucose_facets.json")
    )
    assert payload["facets"]
    assert len(serialized) <= 9500
