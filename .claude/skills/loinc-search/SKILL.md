---
name: loinc-search
description: Run a live query against the LOINC Search API and pretty-print results, to validate wrapper behavior against what the loinc.org UI returns. Use when testing or debugging the MCP server, or to check what the API returns for a given query. Takes a query string and optional scope.
disable-model-invocation: true
---

# loinc-search

Exercise the real LOINC Search API end-to-end so you can compare the MCP wrapper's output
against ground truth. Usage: `/loinc-search <query> [scope]`

- `$ARGUMENTS` = the search text, optionally followed by a scope keyword:
  `loincs` (default), `answerlists`, `parts`, or `groups`.
- Examples: `/loinc-search glucose` · `/loinc-search "sodium serum" loincs` ·
  `/loinc-search hemoglobin parts`

## Steps

1. Confirm `LOINC_USERNAME` and `LOINC_PASSWORD` are set in the environment. If missing,
   stop and tell the user to export them (credentials come from a loinc.org registration).
2. Parse `$ARGUMENTS`: last token, if one of the four scope keywords, is the endpoint;
   everything else is the `query`. Default scope is `loincs`.
3. Call the API with Basic Auth (curl `-u "$LOINC_USERNAME:$LOINC_PASSWORD"`), URL-encoding
   the query, requesting a small page (`rows=10`):

   ```bash
   curl -sS -u "$LOINC_USERNAME:$LOINC_PASSWORD" \
     --get "https://loinc.regenstrief.org/searchapi/<scope>" \
     --data-urlencode "query=<query>" \
     --data-urlencode "rows=10" \
     --data-urlencode "includefiltercounts=true"
   ```

4. If the wrapper (MCP server) already exists, ALSO call the corresponding MCP tool with the
   same query and diff the two result sets — flag any divergence in count, order, or fields.
5. Pretty-print: total hits, then per result the LOINC number, LONG_COMMON_NAME (or the
   scope's primary display field), COMPONENT/SYSTEM if present. Note if results look
   mis-ranked vs. what the loinc.org/search UI would show.
6. On a non-2xx response, surface the status and body verbatim (401 → bad/missing creds).

Keep credentials out of any output you print.
