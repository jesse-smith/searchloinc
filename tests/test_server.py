"""Tests for the MCP surface: tool registration, budgeted search output, and get_loinc.

The API is stubbed with a fake LoincClient that serves fixtures, so these tests never touch
the network or require credentials.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import toon_format

from searchloinc import server

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FakeClient:
    """Stand-in for LoincClient: returns a preloaded response, records the call."""

    def __init__(self, response: dict) -> None:
        self._response = response
        self.calls: list[dict] = []

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def search(self, scope: str, query: str, **kwargs: object) -> dict:
        self.calls.append({"scope": scope, "query": query, **kwargs})
        return self._response

    async def loincs(self, query: str, **kwargs: object) -> dict:
        return await self.search("loincs", query, **kwargs)


def _patch_client(monkeypatch, response: dict) -> FakeClient:
    fake = FakeClient(response)
    monkeypatch.setattr(server, "LoincClient", lambda *a, **k: fake)
    return fake


# --- Registration -----------------------------------------------------------


def test_all_five_tools_registered_with_expected_schemas():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert set(tools) == {
        "search_loincs",
        "search_answerlists",
        "search_parts",
        "search_groups",
        "get_loinc",
    }
    for name in ("search_loincs", "search_answerlists", "search_parts", "search_groups"):
        props = tools[name].inputSchema["properties"]
        assert {"query", "rows", "offset", "sortorder", "language", "include_facets"} <= set(props)
    assert set(tools["get_loinc"].inputSchema["properties"]) == {"code"}


def test_descriptions_teach_the_workflow():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    loincs_desc = tools["search_loincs"].description.lower()
    # scope-selection, ranking/reformulate, and compact->drill-in are all conveyed.
    assert "relevance-ranked" in loincs_desc
    assert "reformulate" in loincs_desc
    assert "get_loinc" in loincs_desc
    assert "drill" in tools["get_loinc"].description.lower()


# --- Search behavior --------------------------------------------------------


def test_search_returns_budgeted_toon_and_honest_envelope(monkeypatch):
    _patch_client(monkeypatch, _load("loincs_783-1.json"))
    result = asyncio.run(server.search_loincs("783-1", rows=5))
    assert result["total"] == 1
    assert result["returned"] == 1
    assert result["truncated"] is False
    assert "results_toon" in result
    decoded = toon_format.decode(result["results_toon"])
    assert decoded[0]["LOINC_NUM"] == "783-1"


def test_default_facets_off_no_sidecar(monkeypatch):
    fake = _patch_client(monkeypatch, _load("loincs_783-1.json"))
    result = asyncio.run(server.search_loincs("783-1"))
    assert "facets" not in result
    assert fake.calls[0]["includefiltercounts"] is False


def test_include_facets_adds_sidecar_and_respects_budget(monkeypatch):
    # Use the LARGE glucose facet fixture (~21K raw chars) — the small parts fixture that was
    # here originally let Bug 1 (facet overflow) slip through. Summarized + packed, the full
    # payload must fit the budget and still return rows.
    _patch_client(monkeypatch, _load("loincs_glucose_facets.json"))
    result = asyncio.run(server.search_loincs("glucose", rows=5, include_facets=True))
    assert "facets" in result and result["facets"]
    assert result["returned"] > 0
    serialized = json.dumps(result, ensure_ascii=False)
    assert len(serialized) <= 9500


def test_raw_json_env_flag_switches_search_to_raw_rows(monkeypatch):
    # The debug escape hatch must actually reach the MCP surface (regression: it was read in
    # config but never passed through _run_search, so TOON was always emitted).
    _patch_client(monkeypatch, _load("loincs_783-1.json"))
    monkeypatch.setattr(server, "raw_json_enabled", lambda: True)
    result = asyncio.run(server.search_loincs("783-1", rows=5))
    assert "results" in result and "results_toon" not in result
    assert result["returned"] == 1


def test_search_passes_paging_params_through(monkeypatch):
    fake = _patch_client(monkeypatch, _load("loincs_783-1.json"))
    asyncio.run(server.search_loincs("glucose", rows=10, offset=20))
    call = fake.calls[0]
    assert call["rows"] == 10 and call["offset"] == 20


# --- get_loinc --------------------------------------------------------------


def test_get_loinc_drops_nulls_keeps_link(monkeypatch):
    _patch_client(monkeypatch, _load("loincs_783-1.json"))
    record = asyncio.run(server.get_loinc("783-1"))
    # Null fields from the fixture are gone...
    assert "FORMULA" not in record  # was null
    assert "PanelType" not in record  # was null
    # ...populated fields and Link remain.
    assert record["LOINC_NUM"] == "783-1"
    assert record["Link"] == "https://loinc.org/783-1"
    assert "COMPONENT" in record


def test_get_loinc_not_found_when_no_exact_match(monkeypatch):
    # Fixture's only row is 783-1; asking for a different code → not_found.
    _patch_client(monkeypatch, _load("loincs_783-1.json"))
    result = asyncio.run(server.get_loinc("9999-9"))
    assert result["error"] == "not_found"
    assert result["code"] == "9999-9"
