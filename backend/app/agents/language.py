"""Language ID agent: identify which of the 22 scheduled languages (or English) the input is in.

Script detection resolves most cases deterministically. Devanagari, Bengali-script and Arabic-script
languages share scripts, so those fall through to lingua; anything lingua can't place falls back
to the dominant language of the script.
"""

from __future__ import annotations

import unicodedata
from collections import Counter

from ..languages import get_language, load_languages
from ..models import Language
from ..state import PipelineState

# Unicode name prefix -> script label used in languages.yaml
_SCRIPT_PREFIXES = {
    "DEVANAGARI": "Devanagari",
    "BENGALI": "Bengali",
    "TAMIL": "Tamil",
    "TELUGU": "Telugu",
    "GUJARATI": "Gujarati",
    "KANNADA": "Kannada",
    "MALAYALAM": "Malayalam",
    "GURMUKHI": "Gurmukhi",
    "ORIYA": "Odia",
    "ARABIC": "Arabic",
    "MEETEI": "Meetei Mayek",
    "OL CHIKI": "Ol Chiki",
    "LATIN": "Latin",
}

# Default language when a script maps to many languages and no finer signal is available.
_SCRIPT_DEFAULT = {
    "Devanagari": "hi",
    "Bengali": "bn",
    "Arabic": "ur",
    "Latin": "en",
}


def dominant_script(text: str) -> str | None:
    counts: Counter[str] = Counter()
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        for prefix, script in _SCRIPT_PREFIXES.items():
            if name.startswith(prefix):
                counts[script] += 1
                break
    return counts.most_common(1)[0][0] if counts else None


def _lingua_detector():
    from lingua import Language as L
    from lingua import LanguageDetectorBuilder

    # lingua covers only a subset of Indian languages; restrict to those that share scripts
    # with other candidates so it can disambiguate (hi/mr/ne, bn/as, ur/sd/ks).
    wanted = [L.ENGLISH, L.HINDI, L.MARATHI, L.BENGALI, L.URDU, L.TAMIL, L.TELUGU,
              L.GUJARATI, L.PUNJABI]  # fmt: skip
    return LanguageDetectorBuilder.from_languages(*wanted).build()


_LINGUA_TO_CODE = {
    "ENGLISH": "en", "HINDI": "hi", "MARATHI": "mr", "BENGALI": "bn", "URDU": "ur",
    "TAMIL": "ta", "TELUGU": "te", "GUJARATI": "gu", "PUNJABI": "pa",
}  # fmt: skip

_detector = None


def detect_language(text: str) -> Language:
    global _detector
    langs = load_languages()
    script = dominant_script(text)
    if script is None:
        return langs["en"]

    candidates = [lang for lang in langs.values() if lang.script == script]
    if len(candidates) == 1:
        return candidates[0]

    # Shared-script: ask lingua, restricted to candidates that share this script.
    if _detector is None:
        _detector = _lingua_detector()
    result = _detector.detect_language_of(text)
    if result is not None:
        code = _LINGUA_TO_CODE.get(result.name)
        if code and langs[code].script == script:
            return langs[code]
    return get_language(_SCRIPT_DEFAULT.get(script, "en"))


class LanguageAgent:
    name = "language_id"

    async def run(self, state: PipelineState) -> PipelineState:
        await state.emit(self.name, "started")
        state.language = detect_language(state.text or state.raw_input)
        lang = state.language
        if lang.tier == "low":
            state.warnings.append(
                f"{lang.name} is a low-resource language for local models; "
                "retrieval and verification quality is reduced and confidence is capped."
            )
        await state.emit(
            self.name, "done", f"Detected {lang.name}", code=lang.code, tier=lang.tier.value
        )
        return state
