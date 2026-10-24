"""Maps the many different category labels used by each provider onto one
small, shared taxonomy, so facilities from different sources can be filtered
consistently in the UI.

Matching is done by substring on a lowercased, diacritics-insensitive version
of the raw label. Add new aliases here as new provider category names are
discovered during scraping - no other code needs to change.
"""

_TRANSLATE_DIACRITICS = str.maketrans(
    "ąćęłńóśźż", "acelnoszz"
)


def _fold(text: str) -> str:
    return text.lower().translate(_TRANSLATE_DIACRITICS)


# canonical name -> substrings (already folded) that map to it
CATEGORY_ALIASES: dict[str, list[str]] = {
    "Siłownia": ["silown"],
    "Basen": ["basen", "plywa"],
    "Zajęcia fitness": ["fitness", "zajecia"],
    "Sztuki walki": ["walk", "boks", "sztuki", "karate", "judo", "mma"],
    "Squash": ["squash"],
    "Tenis": ["tenis"],
    "Joga": ["joga", "yoga"],
    "Taniec": ["tan"],
    "Wspinaczka": ["wspinacz", "climbing"],
    "Sporty zespołowe": ["pilka", "football", "siatk", "koszyk"],
}


def normalize_category(raw_name: str) -> str:
    folded = _fold(raw_name.strip())
    for canonical, substrings in CATEGORY_ALIASES.items():
        if any(s in folded for s in substrings):
            return canonical
    return raw_name.strip().title() or "Inne"
