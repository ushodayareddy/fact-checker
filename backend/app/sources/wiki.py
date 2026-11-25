"""Wikipedia (multilingual extracts) and Wikidata (entity grounding) adapters."""

from __future__ import annotations

import httpx

from ..config import Settings, get_settings
from ..languages import load_languages
from ..models import Evidence
from .base import evidence_id

_UA = {"User-Agent": "fact-checker/0.1 (research project)"}


class WikipediaSource:
    name = "wikipedia"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        s = settings or get_settings()
        self.client = client or httpx.AsyncClient(timeout=s.http_timeout_s, headers=_UA)

    def available(self) -> bool:
        return True

    async def search(self, query: str, lang: str, claim_id: str) -> list[Evidence]:
        language = load_languages().get(lang)
        wiki = language.wiki_code if language else None
        if not wiki:
            return []  # no Wikipedia edition for this language; English query covers it
        r = await self.client.get(
            f"https://{wiki}.wikipedia.org/w/api.php",
            params={
                "action": "query", "format": "json", "generator": "search",
                "gsrsearch": query, "gsrlimit": 4, "prop": "extracts|info",
                "exintro": 1, "explaintext": 1, "exsentences": 6, "inprop": "url",
            },
        )  # fmt: skip
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {}).values()
        out = []
        for p in sorted(pages, key=lambda p: p.get("index", 99)):
            if not p.get("extract"):
                continue
            url = p.get("fullurl") or f"https://{wiki}.wikipedia.org/?curid={p['pageid']}"
            out.append(
                Evidence(
                    id=evidence_id(self.name, url), claim_id=claim_id, source=self.name, url=url,
                    title=p.get("title", ""), snippet=p["extract"], lang=lang,
                    published=(p.get("touched") or "")[:10] or None,
                )
            )  # fmt: skip
        return out


class WikidataSource:
    """Entity grounding only: confirms an entity exists and returns its label/description.

    Statistical claims need real property lookups (SPARQL); that is deliberately out of scope
    for v1 and surfaced as a limitation rather than faked.
    """

    name = "wikidata"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        s = settings or get_settings()
        self.client = client or httpx.AsyncClient(timeout=s.http_timeout_s, headers=_UA)

    def available(self) -> bool:
        return True

    async def search(self, query: str, lang: str, claim_id: str) -> list[Evidence]:
        r = await self.client.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbsearchentities", "format": "json", "search": query[:200],
                    "language": lang, "uselang": lang, "limit": 4},
        )  # fmt: skip
        r.raise_for_status()
        out = []
        for e in r.json().get("search", []):
            url = e.get("concepturi") or f"https://www.wikidata.org/wiki/{e['id']}"
            desc = e.get("description", "")
            out.append(
                Evidence(
                    id=evidence_id(self.name, url), claim_id=claim_id, source=self.name, url=url,
                    title=e.get("label", e["id"]), snippet=f"{e.get('label', '')}: {desc}".strip(": "),
                    lang=lang,
                )
            )  # fmt: skip
        return out
