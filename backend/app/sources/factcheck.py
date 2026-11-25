"""Existing fact-checks: Google Fact Check Tools API when keyed, else domain-restricted web search."""

from __future__ import annotations

import httpx

from ..config import Settings, get_settings
from ..models import Evidence
from .base import evidence_id
from .web import SiteSearch, WebSearch

FACTCHECK_DOMAINS = [
    "boomlive.in", "altnews.in", "factly.in", "vishvasnews.com", "newschecker.in",
    "thequint.com/news/webqoof", "factcheck.pib.gov.in", "indiatoday.in/fact-check",
    "afwa.in", "factchecker.in", "digitaleye.in", "factcrescendo.com",
]  # fmt: skip


class GoogleFactCheck:
    name = "factcheck"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or httpx.AsyncClient(timeout=self.settings.http_timeout_s)

    def available(self) -> bool:
        return bool(self.settings.google_factcheck_api_key)

    async def search(self, query: str, lang: str, claim_id: str) -> list[Evidence]:
        r = await self.client.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={"query": query[:300], "languageCode": lang, "pageSize": 8,
                    "key": self.settings.google_factcheck_api_key},
        )  # fmt: skip
        r.raise_for_status()
        out = []
        for claim in r.json().get("claims", []):
            for review in claim.get("claimReview", []):
                url = review.get("url")
                if not url:
                    continue
                publisher = review.get("publisher", {}).get("name", "")
                rating = review.get("textualRating", "")
                snippet = (
                    f"Claim: {claim.get('text', '')} | Claimant: {claim.get('claimant', 'unknown')} | "
                    f"Rating by {publisher}: {rating}"
                )
                out.append(
                    Evidence(
                        id=evidence_id(self.name, url), claim_id=claim_id, source=self.name, url=url,
                        title=review.get("title", ""), snippet=snippet,
                        lang=review.get("languageCode", lang),
                        published=(review.get("reviewDate") or "")[:10] or None,
                    )
                )  # fmt: skip
        return out


def make_factcheck_source(web: WebSearch, settings: Settings | None = None):
    google = GoogleFactCheck(settings)
    return google if google.available() else SiteSearch("factcheck", FACTCHECK_DOMAINS, web)
