"""Unit tests for prompt_loader.py."""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

# Stub prompt_echo before import
if "prompt_echo" not in sys.modules:
    mock_prompt_echo = types.ModuleType("prompt_echo")
    mock_prompt_echo.auto_extract_prompt_sigs = MagicMock(return_value=["sig1", "sig2"])
    sys.modules["prompt_echo"] = mock_prompt_echo

from prompt_loader import load_prompts


class TestLoadPrompts:
    """Tests for load_prompts()."""

    def _make_args(self, **kwargs):
        """Create a mock args namespace."""
        defaults = {
            "prompt": None,
            "prompt_file": None,
            "condensed_prompt": "",
            "condensed_prompt_file": "",
            "prompt_sigs": "",
        }
        defaults.update(kwargs)
        args = MagicMock(**defaults)
        # Ensure attribute access works like a real namespace
        for k, v in defaults.items():
            setattr(args, k, v)
        return args

    def test_load_prompt_from_text(self):
        """load_prompts returns text when args.prompt is set."""
        args = self._make_args(prompt="hello world")
        full, condensed, sigs = load_prompts(args)
        assert full == "hello world"

    def test_load_prompt_from_file(self, tmp_path):
        """load_prompts reads file content when args.prompt_file is set."""
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("file content here", encoding="utf-8")

        args = self._make_args(prompt_file=str(prompt_file))
        full, condensed, sigs = load_prompts(args)
        assert full == "file content here"

    def test_load_prompt_file_not_found_exits(self):
        """load_prompts exits(1) when prompt_file does not exist."""
        import pytest
        args = self._make_args(prompt_file="/nonexistent/path/prompt.md")
        with pytest.raises(SystemExit) as exc_info:
            load_prompts(args)
        assert exc_info.value.code == 1

    def test_load_prompt_file_too_large_exits(self, tmp_path):
        """load_prompts exits(1) when prompt_file exceeds 500 KB."""
        import pytest
        large_file = tmp_path / "large.md"
        large_file.write_bytes(b"x" * (512_001))

        args = self._make_args(prompt_file=str(large_file))
        with pytest.raises(SystemExit) as exc_info:
            load_prompts(args)
        assert exc_info.value.code == 1

    def test_condensed_prompt_from_text(self):
        """load_prompts uses args.condensed_prompt when set."""
        args = self._make_args(prompt="full prompt", condensed_prompt="short")
        full, condensed, sigs = load_prompts(args)
        assert condensed == "short"

    def test_condensed_prompt_from_file(self, tmp_path):
        """load_prompts reads condensed prompt from file."""
        cfile = tmp_path / "condensed.md"
        cfile.write_text("condensed content", encoding="utf-8")

        args = self._make_args(prompt="full", condensed_prompt_file=str(cfile))
        full, condensed, sigs = load_prompts(args)
        assert condensed == "condensed content"

    def test_condensed_prompt_file_not_found_exits(self):
        """load_prompts exits(1) when condensed_prompt_file does not exist."""
        import pytest
        args = self._make_args(prompt="full", condensed_prompt_file="/nonexistent/cond.md")
        with pytest.raises(SystemExit) as exc_info:
            load_prompts(args)
        assert exc_info.value.code == 1

    def test_condensed_prompt_defaults_to_full(self):
        """load_prompts uses full prompt as condensed when no condensed args given."""
        args = self._make_args(prompt="my full prompt")
        full, condensed, sigs = load_prompts(args)
        assert condensed == full

    def test_prompt_sigs_from_args(self):
        """load_prompts parses comma-separated prompt_sigs from args."""
        args = self._make_args(prompt="test", prompt_sigs="A,B,C")
        full, condensed, sigs = load_prompts(args)
        assert sigs == ["A", "B", "C"]

    def test_prompt_sigs_auto_extracted(self):
        """load_prompts calls auto_extract when no prompt_sigs given."""
        import prompt_loader as _pl_mod
        mock_auto = MagicMock(return_value=["auto1", "auto2"])
        with patch.object(_pl_mod, "auto_extract_prompt_sigs", mock_auto):
            args = self._make_args(prompt="test prompt here")
            full, condensed, sigs = load_prompts(args)
        mock_auto.assert_called_once_with("test prompt here")
        assert sigs == ["auto1", "auto2"]

    def test_prompt_sigs_strips_whitespace(self):
        """load_prompts strips whitespace from prompt_sigs."""
        args = self._make_args(prompt="test", prompt_sigs=" A , B , C ")
        full, condensed, sigs = load_prompts(args)
        assert sigs == ["A", "B", "C"]
