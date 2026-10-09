"""Unpaywall, for the open access versions of a work by DOI (EF-COL-02, EF-SEL-14).

Unpaywall asks for a contact address (``email``) with each request and up to 100,000
requests a day; the tool waits a tenth of a second between requests.
"""

from typing import Any
from urllib.parse import quote

import httpx2
from pydantic import SecretStr

from revue_portee.sources.http import RateLimiter, SourceAccessError, get_json
from revue_portee.sources.records import OpenAccessLocation

__all__ = ["API", "Unpaywall", "unpaywall_locations"]

API = "https://api.unpaywall.org/v2/"
SERVICE = "Unpaywall"


class Unpaywall:
    def __init__(
        self,
        client: httpx2.Client,
        *,
        email: SecretStr,
        limiter: RateLimiter | None = None,
        owns_client: bool = False,
    ) -> None:
        self._client = client
        self._email = email
        self._limiter = limiter or RateLimiter(0.1)
        self._owns_client = owns_client

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def locations(self, doi: str) -> tuple[list[OpenAccessLocation], dict[str, Any]]:
        """Open access PDFs that Unpaywall knows for ``doi`` (none if it does not know
        the DOI), and the raw answer."""
        try:
            raw = get_json(
                self._client,
                API + quote(doi.lower(), safe="/"),
                {"email": self._email.get_secret_value()},
                service=SERVICE,
                limiter=self._limiter,
            )
        except SourceAccessError as error:
            if error.status == 404:
                return [], {"status": 404}
            raise
        return unpaywall_locations(raw), raw


def unpaywall_locations(record: dict[str, Any]) -> list[OpenAccessLocation]:
    """Locations of an Unpaywall record with a PDF, the best one first."""
    found: list[OpenAccessLocation] = []
    for location in [record.get("best_oa_location"), *(record.get("oa_locations") or [])]:
        if not location or not location.get("url_for_pdf"):
            continue
        item = OpenAccessLocation(
            pdf_url=str(location["url_for_pdf"]),
            license=str(location.get("license") or ""),
            version=str(location.get("version") or ""),
            host_type=str(location.get("host_type") or ""),
        )
        if all(item.pdf_url != other.pdf_url for other in found):
            found.append(item)
    return found
