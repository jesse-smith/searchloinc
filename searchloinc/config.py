"""Static configuration for the SearchLOINC wrapper.

Single source of truth for the four API scopes, their compact (triage) column sets,
the character budget, the TOON delimiter, and the debug-JSON escape hatch. All of
these were confirmed against live fixtures — see the plan's groundwork slice.
"""

from __future__ import annotations

import os

# --- Endpoint ---------------------------------------------------------------
# The documented LOINC Search API — NOT the FHIR terminology service. See CAIRN.md #2.
API_BASE_URL = "https://loinc.regenstrief.org/searchapi"

# --- Budgeting --------------------------------------------------------------
# The whole serialized envelope (TOON table + JSON envelope + any facet sidecar) must
# stay under the ~10K-char downstream tool-result cap. 9500 leaves a cushion.
CHAR_BUDGET = 9500

# TOON table delimiter. Confirmed empirically across all four scope fixtures: values
# never contain a tab, but commas do appear in real data (parts.Classlist, groups),
# which would force per-row quoting under a comma delimiter. Tab avoids that.
TOON_DELIMITER = "\t"

# --- Facet summarization ----------------------------------------------------
# Raw FilterCounts run ~20K chars on broad queries (all long-count-tail), 2x+ the budget.
# We minimize every group to its top values by Count and drop the noisiest groups outright.
# Combined with TOON encoding + forced-uniform columns (empty Description -> ""), this lands
# broad-query facets well under budget. Each summarized group still reports its full `total`
# and each value keeps its `Search` filter fragment, so an agent can re-query to recover the
# tail. See plan's facet-overflow decision. (Follow-up work may fine-tune per-group behavior.)
FACET_TOP_N = 5
# Version-history groups are noise for triage and the biggest char sink; drop them outright.
FACET_DROP_GROUPS = ("VersionFirstReleased", "VersionLastChanged")
# Uniform column set every facet entry is projected onto before TOON encoding.
FACET_COLUMNS = ("Label", "Count", "Description", "Search")

# --- Debug escape hatch -----------------------------------------------------
# When set (truthy), search tools return raw JSON instead of TOON. Debug-only, toggled
# by env var — never exposed as an agent-facing MCP tool parameter (plan decision).
RAW_JSON_ENV_VAR = "SEARCHLOINC_RAW_JSON"


def raw_json_enabled() -> bool:
    """True if the raw-JSON debug path is enabled via environment."""
    return os.environ.get(RAW_JSON_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


# --- Scopes -----------------------------------------------------------------
# The four API scopes (CAIRN #4: four scopes, four tools). Order matters only for display.
SCOPES = ("loincs", "answerlists", "parts", "groups")

# Compact column set per scope: the primary display scalars an agent triages on. Fixed and
# always all present in a row (empties render as "" to preserve TOON row uniformity). Nested
# arrays (Answers/Loincs), comma-joined Classlist, and detail free-text are drill-in only and
# deliberately excluded. Confirmed against live fixtures.
COMPACT_COLUMNS: dict[str, list[str]] = {
    "loincs": [
        "STATUS",
        "LOINC_NUM",
        "LONG_COMMON_NAME",
        "COMPONENT",
        "PROPERTY",
        "TIME_ASPCT",
        "SYSTEM",
        "SCALE_TYP",
        "METHOD_TYP",
        "CLASS",
        "CLASSTYPE",
        "EXAMPLE_UCUM_UNITS",
        "ORDER_OBS",
        "COMMON_TEST_RANK",
    ],
    "answerlists": [
        "AnswerListId",
        "Name",
        "ExtDefinedYN",
        "Link",
    ],
    "parts": [
        "PartNumber",
        "PartTypeName",
        "PartName",
        "PartDisplayName",
        "Status",
        "Link",
    ],
    "groups": [
        "ParentGroupId",
        "ParentGroup",
        "GroupId",
        "Group",
        "STATUS",
        "Category",
        "Link",
    ],
}

# Envelope field mapping: the API's ResponseSummary uses these names in every scope.
SUMMARY_KEY = "ResponseSummary"
RESULTS_KEY = "Results"
FILTER_COUNTS_KEY = "FilterCounts"
RECORDS_FOUND_KEY = "RecordsFound"
STARTING_OFFSET_KEY = "StartingOffset"
ROWS_RETURNED_KEY = "RowsReturned"
