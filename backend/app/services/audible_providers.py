import logging
from typing import Dict, List, Optional, Tuple

import langcodes

logger = logging.getLogger(__name__)


# (provider value, display label, audnexus region)
AUDIBLE_PROVIDERS: List[Tuple[str, str, str]] = [
    ("audible", "Audible.com", "US"),
    ("audible.ca", "Audible.ca", "CA"),
    ("audible.uk", "Audible.co.uk", "UK"),
    ("audible.au", "Audible.com.au", "AU"),
    ("audible.fr", "Audible.fr", "FR"),
    ("audible.de", "Audible.de", "DE"),
    ("audible.jp", "Audible.co.jp", "JP"),
    ("audible.it", "Audible.it", "IT"),
    ("audible.in", "Audible.in", "IN"),
    ("audible.es", "Audible.es", "ES"),
]

_PROVIDER_TO_REGION: Dict[str, str] = {p: r for p, _, r in AUDIBLE_PROVIDERS}

# ISO 639-1 code -> default audnexus region
LANGUAGE_REGION_MAP: Dict[str, str] = {
    "en": "US",
    "de": "DE",
    "fr": "FR",
    "it": "IT",
    "es": "ES",
    "ja": "JP",
}


def region_for_provider(provider: Optional[str]) -> Optional[str]:
    """Return the audnexus region for a known audible provider, else None."""
    if not provider:
        return None
    return _PROVIDER_TO_REGION.get(provider)


def normalize_language(language: Optional[str]) -> Optional[str]:
    """Normalize freeform language input (code, English name, native name) to ISO 639-1."""
    if not language:
        return None
    text = language.strip()
    if not text:
        return None

    # Try as a language code first (handles "en", "de", "fr-FR", etc.).
    try:
        lang = langcodes.Language.get(text)
        if lang.is_valid() and lang.language:
            return lang.language.lower()
    except Exception:
        pass

    # Fall back to name lookup (handles "English", "Deutsch", "Japanese", etc.).
    try:
        lang = langcodes.find(text)
        if lang and lang.language:
            return lang.language.lower()
    except LookupError:
        pass

    return None


def region_for_language(language: Optional[str]) -> Optional[str]:
    """Map freeform language input (code, English name, native name) to a region."""
    code = normalize_language(language)
    if not code:
        return None
    return LANGUAGE_REGION_MAP.get(code)


def all_regions() -> List[str]:
    """All audible regions, in declaration order."""
    return [r for _, _, r in AUDIBLE_PROVIDERS]


def provider_dropdown() -> List[Dict[str, str]]:
    """Provider list shaped for the frontend dropdown."""
    return [{"value": p, "label": label} for p, label, _ in AUDIBLE_PROVIDERS]
