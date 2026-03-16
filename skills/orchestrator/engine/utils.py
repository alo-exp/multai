"""Shared utilities: text cleaning and deduplication."""

from __future__ import annotations

import re


def pre_clean_text(text: str) -> str:
    """Universal cleaning pipeline — strip patterns that trigger content filters."""
    cleaned = text
    cleaned = re.sub(r'https?://\S+', '[URL]', cleaned)               # strip URLs
    cleaned = re.sub(r'(\w+)=(\w+)', r'\1:\2', cleaned)               # neutralise word=word
    cleaned = re.sub(r'\?[a-zA-Z0-9&=_%\.+\-]+', '[PARAMS]', cleaned) # strip query strings
    cleaned = re.sub(r'[A-Za-z0-9+/]{60,}={0,2}', '[B64]', cleaned)  # strip base64 blobs
    cleaned = re.sub(r'citeturn\d+view\d+', '[cite]', cleaned)        # ChatGPT citation markers
    return cleaned.strip()


def deduplicate_response(text: str, marker: str = "End of Report.") -> str:
    """
    Remove DOM duplication (e.g., ChatGPT renders the response twice).
    Slices at the first occurrence of the marker.
    """
    idx = text.find(marker)
    if idx >= 0:
        return text[:idx + len(marker)]
    return text
