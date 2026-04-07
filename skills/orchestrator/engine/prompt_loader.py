"""Prompt loading and echo-signature extraction."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from prompt_echo import auto_extract_prompt_sigs

log = logging.getLogger(__name__)


def load_prompts(args) -> tuple[str, str, list[str]]:
    """Load full prompt, condensed prompt, and auto-extract echo signatures.

    Returns:
        (full_prompt, condensed_prompt, prompt_sigs)
    """
    # Load full prompt
    if args.prompt:
        full_prompt = args.prompt
    else:
        path = Path(args.prompt_file)
        if not path.exists():
            log.error(f"Prompt file not found: {args.prompt_file}")
            sys.exit(1)
        _MAX_PROMPT_BYTES = 512_000  # 500 KB ceiling
        if path.stat().st_size > _MAX_PROMPT_BYTES:
            log.error(f"Prompt file exceeds 500 KB limit ({path.stat().st_size} bytes): {args.prompt_file}")
            sys.exit(1)
        full_prompt = path.read_text(encoding="utf-8")

    # Load condensed prompt (optional — falls back to full prompt)
    if args.condensed_prompt:
        condensed_prompt = args.condensed_prompt
    elif args.condensed_prompt_file:
        path = Path(args.condensed_prompt_file)
        if not path.exists():
            log.error(f"Condensed prompt file not found: {args.condensed_prompt_file}")
            sys.exit(1)
        condensed_prompt = path.read_text(encoding="utf-8")
    else:
        condensed_prompt = full_prompt

    # Extract prompt-echo detection signatures
    if args.prompt_sigs:
        prompt_sigs = [s.strip() for s in args.prompt_sigs.split(",") if s.strip()]
    else:
        prompt_sigs = auto_extract_prompt_sigs(full_prompt)

    log.info(f"Full prompt: {len(full_prompt)} chars | Condensed: {len(condensed_prompt)} chars | Sigs: {prompt_sigs}")
    return full_prompt, condensed_prompt, prompt_sigs
