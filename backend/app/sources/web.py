"""General web search with pluggable backends: Tavily (key) > SearXNG (self-hosted) > DuckDuckGo HTML.

`SiteSearch` wraps it with a domain allowlist; the govt and fact-check-archive adapters are built
on that so they need no per-site scraper.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from lxml import html as lxml_html

from ..config import Settings, get_settings
from ..models import Evidence
from .base import evidence_id

log = logging.getLogger(__name__)
_UA = {"User-Agent": "Mozilla/5.0 (fact-checker research bot)"}


class WebSearch:
    name = "web"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or httpx.AsyncClient(
            timeout=self.settings.http_timeout_s, follow_redirects=True, headers=_UA
        )

    def available(self) -> bool:
        return True  # DuckDuckGo needs no key

    async def search(self, query: str, lang: str, claim_id: str) -> list[Evidence]:
        s = self.settings
        if s.tavily_api_key:
            rows = await self._tavily(query)
        elif s.searxng_url:
            rows = await self._searxng(query, lang)
        else:
            rows = await self._duckduckgo(query)
        return [
            Evidence(
                id=evidence_id(self.name, r["url"]), claim_id=claim_id, source=self.name,
                url=r["url"], title=r["title"], snippet=r["snippet"], lang=lang,
                published=r.get("published"),
            )
            for r in rows
            if r["url"]
        ]  # fmt: skip

    async def _tavily(self, query: str) -> list[dict]:
        r = await self.client.post(
            "https://api.tavily.com/search",
            json={"api_key": self.settings.tavily_api_key, "query": query, "max_results": 8},
        )
        r.raise_for_status()
        return [
            {"url": x["url"], "title": x.get("title", ""), "snippet": x.get("content", ""),
             "published": x.get("published_date")}
            for x in r.json().get("results", [])
        ]  # fmt: skip

    async def _searxng(self, query: str, lang: str) -> list[dict]:
        r = await self.client.get(
            f"{self.settings.searxng_url.rstrip('/')}/search",
            params={"q": query, "format": "json", "language": lang},
        )
        r.raise_for_status()
        return [
            {"url": x["url"], "title": x.get("title", ""), "snippet": x.get("content", ""),
             "published": x.get("publishedDate")}
            for x in r.json().get("results", [])[:8]
        ]  # fmt: skip

    async def _duckduckgo(self, query: str) -> list[dict]:
        r = await self.client.post("https://html.duckduckgo.com/html/", data={"q": query})
        r.raise_for_status()
        return parse_duckduckgo(r.text)


def _unwrap_ddg(href: str) -> str:
    """DDG wraps result links as //duckduckgo.com/l/?uddg=<encoded-url>."""
    if "uddg=" in href:
        target = parse_qs(urlparse(href).query).get("uddg", [""])[0]
        return unquote(target)
    return href


def parse_duckduckgo(page: str) -> list[dict]:
    tree = lxml_html.fromstring(page)
    rows = []
    for node in tree.cssselect("div.result"):
        link = node.cssselect("a.result__a")
        if not link:
            continue
        snippet = node.cssselect(".result__snippet")
        rows.append(
            {
                "url": _unwrap_ddg(link[0].get("href", "")),
                "title": link[0].text_content().strip(),
                "snippet": snippet[0].text_content().strip() if snippet else "",
            }
        )
    return rows[:8]


class SiteSearch:
    """Web search restricted to an allowlist of domains via `site:` operators."""

    def __init__(self, name: str, domains: list[str], web: WebSearch):
        self.name, self.domains, self.web = name, domains, web

    def available(self) -> bool:
        return self.web.available()

    async def search(self, query: str, lang: str, claim_id: str) -> list[Evidence]:
        scope = " OR ".join(f"site:{d}" for d in self.domains)
        rows = await self.web.search(f"{query} ({scope})", lang, claim_id)
        allowed = [r for r in rows if any(d in r.url for d in self.domains)]
        return [r.model_copy(update={"source": self.name, "id": evidence_id(self.name, r.url)}) for r in allowed]
