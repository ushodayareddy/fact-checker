import httpx
import respx

from app.config import Settings
from app.sources.factcheck import GoogleFactCheck, make_factcheck_source
from app.sources.govt import make_govt_source
from app.sources.web import WebSearch, parse_duckduckgo
from app.sources.wiki import WikidataSource, WikipediaSource

DDG_HTML = """
<html><body>
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpib.gov.in%2Fa%3Fid%3D1&rut=x">PIB release</a>
<a class="result__snippet">GDP grew 8.2 percent</a></div>
<div class="result"><a class="result__a" href="https://example.com/blog">Random blog</a>
<a class="result__snippet">Opinion piece</a></div>
<div class="result"><span>no link here</span></div>
</body></html>
"""


def test_parse_duckduckgo_unwraps_redirect_and_skips_malformed():
    rows = parse_duckduckgo(DDG_HTML)
    assert [r["url"] for r in rows] == ["https://pib.gov.in/a?id=1", "https://example.com/blog"]
    assert rows[0]["snippet"] == "GDP grew 8.2 percent"


@respx.mock
async def test_govt_source_keeps_only_allowlisted_domains():
    respx.post("https://html.duckduckgo.com/html/").mock(return_value=httpx.Response(200, text=DDG_HTML))
    web = WebSearch(Settings())
    out = await make_govt_source(web).search("GDP growth", "en", "c1")
    assert len(out) == 1
    assert out[0].source == "govt" and out[0].url == "https://pib.gov.in/a?id=1"
    assert out[0].id.startswith("govt:")


@respx.mock
async def test_web_prefers_tavily_when_key_set():
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json={"results": [{"url": "https://x.in/1", "title": "T", "content": "C"}]})
    )
    out = await WebSearch(Settings(tavily_api_key="k")).search("q", "en", "c1")
    assert route.called and out[0].snippet == "C"


@respx.mock
async def test_google_factcheck_maps_reviews():
    respx.get("https://factchecktools.googleapis.com/v1alpha1/claims:search").mock(
        return_value=httpx.Response(
            200,
            json={"claims": [{
                "text": "Hot water cures cancer", "claimant": "WhatsApp forward",
                "claimReview": [{
                    "url": "https://boomlive.in/x", "title": "No, it does not",
                    "publisher": {"name": "BOOM"}, "textualRating": "False",
                    "reviewDate": "2025-03-04T00:00:00Z", "languageCode": "en",
                }],
            }]},
        )
    )
    out = await GoogleFactCheck(Settings(google_factcheck_api_key="k")).search("hot water", "en", "c1")
    assert out[0].published == "2025-03-04"
    assert "Rating by BOOM: False" in out[0].snippet


def test_factcheck_falls_back_to_site_search_without_key():
    web = WebSearch(Settings())
    assert make_factcheck_source(web, Settings()).name == "factcheck"
    assert not GoogleFactCheck(Settings()).available()


@respx.mock
async def test_wikipedia_skips_languages_without_edition():
    # Dogri has no Wikipedia edition: no HTTP call should be made.
    assert await WikipediaSource(Settings()).search("दिल्ली", "doi", "c1") == []


@respx.mock
async def test_wikipedia_returns_extracts_in_rank_order():
    respx.get("https://hi.wikipedia.org/w/api.php").mock(
        return_value=httpx.Response(
            200,
            json={"query": {"pages": {
                "2": {"pageid": 2, "index": 2, "title": "B", "extract": "second", "fullurl": "https://hi.wikipedia.org/wiki/B"},
                "1": {"pageid": 1, "index": 1, "title": "A", "extract": "first", "fullurl": "https://hi.wikipedia.org/wiki/A"},
                "3": {"pageid": 3, "index": 3, "title": "C", "extract": ""},
            }}},
        )
    )
    out = await WikipediaSource(Settings()).search("दिल्ली", "hi", "c1")
    assert [e.title for e in out] == ["A", "B"]


@respx.mock
async def test_wikidata_maps_entities():
    respx.get("https://www.wikidata.org/w/api.php").mock(
        return_value=httpx.Response(
            200,
            json={"search": [{"id": "Q987", "label": "Delhi", "description": "capital of India",
                              "concepturi": "http://www.wikidata.org/entity/Q987"}]},
        )
    )
    out = await WikidataSource(Settings()).search("Delhi", "en", "c1")
    assert out[0].snippet == "Delhi: capital of India"
