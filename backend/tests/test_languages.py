from app.languages import get_language, load_languages
from app.models import LanguageTier

SCHEDULED_22 = {
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml",
    "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
}  # fmt: skip


def test_all_22_scheduled_languages_plus_english():
    codes = set(load_languages())
    assert codes == SCHEDULED_22 | {"en"}


def test_every_language_has_indictrans_code():
    assert all(lang.indictrans_code for lang in load_languages().values())


def test_low_resource_languages_are_tiered_low():
    for code in ("sat", "brx", "doi", "ks", "mni"):
        assert get_language(code).tier == LanguageTier.LOW


def test_languages_without_wikipedia_edition_are_null():
    assert get_language("doi").wiki_code is None
    assert get_language("brx").wiki_code is None
