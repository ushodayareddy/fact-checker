from functools import lru_cache
from pathlib import Path

import yaml

from .models import Language

_DATA = Path(__file__).parent / "data" / "languages.yaml"


@lru_cache
def load_languages() -> dict[str, Language]:
    raw = yaml.safe_load(_DATA.read_text(encoding="utf-8"))
    return {entry["code"]: Language(**entry) for entry in raw["languages"]}


def get_language(code: str) -> Language:
    langs = load_languages()
    if code not in langs:
        raise KeyError(f"Unsupported language code: {code}")
    return langs[code]
