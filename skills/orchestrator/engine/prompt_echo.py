"""Generic prompt-echo detection module.

When a user submits a prompt to an AI platform, the platform often renders
the prompt text on the page alongside its response. During extraction, we
need to distinguish the echoed prompt from the actual AI response.

This module provides two functions:
  - auto_extract_prompt_sigs(prompt) — extract distinctive phrases from any prompt
  - is_prompt_echo(text, prompt_sigs) — check if extracted text is an echoed prompt
"""

from __future__ import annotations

import re


def auto_extract_prompt_sigs(prompt: str, max_sigs: int = 5) -> list[str]:
    """Extract distinctive ALL-CAPS phrases from the prompt.

    Strategy:
      1. Find ALL-CAPS phrases (section headers like "SYSTEM ROLE & MINDSET")
      2. If fewer than max_sigs found, add long distinctive words (15+ chars)

    These signatures are used to detect when a platform echoes the user's
    prompt on the page instead of (or alongside) the AI response.

    Args:
        prompt: The full prompt text to extract signatures from.
        max_sigs: Maximum number of signatures to return.

    Returns:
        List of distinctive phrases/words found in the prompt.
    """
    sigs: list[str] = []

    # 1. ALL-CAPS phrases (2+ words, all uppercase letters/spaces/punctuation)
    caps_pattern = re.compile(r'\b([A-Z][A-Z &()\-,]{4,}[A-Z])\b')
    for match in caps_pattern.finditer(prompt):
        phrase = match.group(1).strip()
        if len(phrase) >= 8 and phrase not in sigs:
            sigs.append(phrase)
            if len(sigs) >= max_sigs:
                return sigs

    # 2. Fallback: long distinctive words (15+ chars, not common English)
    if len(sigs) < max_sigs:
        words = set(re.findall(r'\b[a-zA-Z]{15,}\b', prompt))
        for word in sorted(words):
            if word not in sigs:
                sigs.append(word)
                if len(sigs) >= max_sigs:
                    break

    return sigs


def is_prompt_echo(text: str, prompt_sigs: list[str], sample_size: int = 3000) -> bool:
    """Return True if text appears to be the echoed user prompt.

    Checks whether the first `sample_size` characters of `text` contain
    any of the prompt signatures. If signatures are found, the text is
    likely the user's prompt being rendered on the page, not an AI response.

    Args:
        text: The extracted text to check.
        prompt_sigs: List of distinctive phrases from the original prompt.
        sample_size: Number of leading characters to check (default 3000).

    Returns:
        True if the text appears to be a prompt echo; False otherwise.
    """
    if not prompt_sigs:
        return False
    sample = text[:sample_size]
    return any(sig in sample for sig in prompt_sigs)
