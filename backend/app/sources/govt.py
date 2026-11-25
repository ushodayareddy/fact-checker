"""Government / official sources via domain-restricted search.

No first-party search API is integrated yet (PIB has none; data.gov.in needs per-dataset
resource IDs), so this searches an allowlist of official domains. data.gov.in dataset lookup
is a known gap for statistical claims.
"""

from __future__ import annotations

from .web import SiteSearch, WebSearch

GOVT_DOMAINS = [
    "pib.gov.in", "factcheck.pib.gov.in", "rbi.org.in", "eci.gov.in", "mohfw.gov.in",
    "icmr.gov.in", "data.gov.in", "mospi.gov.in", "niti.gov.in", "india.gov.in",
    "indiabudget.gov.in", "census.gov.in", "prsindia.org",
]  # fmt: skip


def make_govt_source(web: WebSearch) -> SiteSearch:
    return SiteSearch("govt", GOVT_DOMAINS, web)
