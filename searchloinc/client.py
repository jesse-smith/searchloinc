"""Thin async HTTP client for the LOINC Search API.

Maps a scope + query params to a GET against the documented Search API and returns the
parsed JSON body. Deliberately thin (CAIRN #1): no client-side ranking, filtering, or
reshaping — that belongs in render.py and the server layer. Credentials come from the
environment (CAIRN #3) and are never logged.
"""

from __future__ import annotations

import os

import httpx

from .config import API_BASE_URL, SCOPES

USERNAME_ENV_VAR = "LOINC_USERNAME"
PASSWORD_ENV_VAR = "LOINC_PASSWORD"

# Sort direction is "field asc|desc" per the API; we pass sortorder through untouched.


class LoincAuthError(RuntimeError):
    """Credentials are missing from the environment."""


class LoincAPIError(RuntimeError):
    """The API returned a non-2xx response. Carries status + body, never credentials."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"LOINC Search API returned HTTP {status_code}: {body}")


def _credentials() -> tuple[str, str]:
    """Read Basic-auth credentials from the environment, or raise LoincAuthError."""
    username = os.environ.get(USERNAME_ENV_VAR)
    password = os.environ.get(PASSWORD_ENV_VAR)
    if not username or not password:
        raise LoincAuthError(
            f"Set {USERNAME_ENV_VAR} and {PASSWORD_ENV_VAR} in the environment "
            "(register at loinc.org for credentials)."
        )
    return username, password


class LoincClient:
    """Async client wrapping the four scoped Search API endpoints.

    Usage:
        async with LoincClient() as client:
            data = await client.search("loincs", "glucose", rows=25)
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._auth = httpx.BasicAuth(*_credentials())
        self._client = httpx.AsyncClient(
            base_url=API_BASE_URL,
            auth=self._auth,
            timeout=timeout,
        )

    async def __aenter__(self) -> LoincClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(
        self,
        scope: str,
        query: str,
        *,
        rows: int | None = None,
        offset: int | None = None,
        sortorder: str | None = None,
        language: int | None = None,
        includefiltercounts: bool = False,
    ) -> dict:
        """GET one scope endpoint and return the parsed JSON body.

        `scope` must be one of the four documented scopes. Only non-None params are sent,
        so the API applies its own defaults for anything omitted.
        """
        if scope not in SCOPES:
            raise ValueError(f"Unknown scope {scope!r}; expected one of {SCOPES}.")

        params: dict[str, str | int] = {"query": query}
        if rows is not None:
            params["rows"] = rows
        if offset is not None:
            params["offset"] = offset
        if sortorder is not None:
            params["sortorder"] = sortorder
        if language is not None:
            params["language"] = language
        # Always explicit: the API defaults filter counts off, but be unambiguous.
        params["includefiltercounts"] = "true" if includefiltercounts else "false"

        response = await self._client.get(f"/{scope}", params=params)
        if response.status_code // 100 != 2:
            # Surface status + body verbatim; httpx keeps auth in headers, not the body,
            # so this never leaks credentials.
            raise LoincAPIError(response.status_code, response.text)
        return response.json()

    # Convenience wrappers — one per scope, matching the intended one-tool-per-scope design.
    async def loincs(self, query: str, **kwargs: object) -> dict:
        return await self.search("loincs", query, **kwargs)  # type: ignore[arg-type]

    async def answerlists(self, query: str, **kwargs: object) -> dict:
        return await self.search("answerlists", query, **kwargs)  # type: ignore[arg-type]

    async def parts(self, query: str, **kwargs: object) -> dict:
        return await self.search("parts", query, **kwargs)  # type: ignore[arg-type]

    async def groups(self, query: str, **kwargs: object) -> dict:
        return await self.search("groups", query, **kwargs)  # type: ignore[arg-type]
