"""Unit tests for orchestrator argument parsing.

Tests UT-OR-01 through UT-OR-11.

NOTE: orchestrator.py has module-level side effects (_ensure_venv, _ensure_dependencies)
that call subprocess.run and os.execv. We mock these to prevent them from firing.
"""

import importlib
import os
import sys
import types
import unittest.mock
from pathlib import Path

# Engine directory
ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")

# We need to import orchestrator while blocking its module-level side effects.
# The module calls _ensure_venv() and _ensure_dependencies() at module level,
# and after that imports from playwright and other engine modules.
# Strategy: We'll patch the functions before import, and mock unavailable modules.


def _import_orchestrator():
    """Import orchestrator module while neutralizing side effects."""
    if "orchestrator" in sys.modules:
        return sys.modules["orchestrator"]

    # Add engine dir to path
    if ENGINE_DIR not in sys.path:
        sys.path.insert(0, ENGINE_DIR)

    # Read the source and exec it with mocked functions
    src_path = Path(ENGINE_DIR) / "orchestrator.py"
    source = src_path.read_text(encoding="utf-8")

    # Create a mock module for playwright
    mock_playwright = types.ModuleType("playwright")
    mock_async_api = types.ModuleType("playwright.async_api")
    mock_async_api.async_playwright = unittest.mock.MagicMock()
    mock_async_api.BrowserContext = unittest.mock.MagicMock()
    mock_playwright.async_api = mock_async_api
    sys.modules["playwright"] = mock_playwright
    sys.modules["playwright.async_api"] = mock_async_api

    # Create mock for agent_fallback
    mock_agent = types.ModuleType("agent_fallback")
    mock_agent.AgentFallbackManager = unittest.mock.MagicMock()
    sys.modules["agent_fallback"] = mock_agent

    # Create mock for platforms
    mock_platforms = types.ModuleType("platforms")
    mock_platforms.ALL_PLATFORMS = {
        "claude_ai": unittest.mock.MagicMock(),
        "chatgpt": unittest.mock.MagicMock(),
        "copilot": unittest.mock.MagicMock(),
        "perplexity": unittest.mock.MagicMock(),
        "grok": unittest.mock.MagicMock(),
        "deepseek": unittest.mock.MagicMock(),
        "gemini": unittest.mock.MagicMock(),
    }
    sys.modules["platforms"] = mock_platforms

    # Patch _ensure_venv and _ensure_dependencies to be no-ops
    # We'll replace the calls in the source with pass statements
    modified_source = source.replace(
        "_ensure_venv()            # Create .venv/ and re-exec if not already in a venv",
        "pass  # _ensure_venv() skipped in test"
    ).replace(
        "_ensure_dependencies()    # pip install missing packages (safe inside venv)",
        "pass  # _ensure_dependencies() skipped in test"
    )

    # Compile and exec
    module = types.ModuleType("orchestrator")
    module.__file__ = str(src_path)
    code = compile(modified_source, str(src_path), "exec")
    exec(code, module.__dict__)

    sys.modules["orchestrator"] = module
    return module


# Import orchestrator with mocks
orchestrator = _import_orchestrator()
parse_args = orchestrator.parse_args


class TestOrchestratorArgs:
    """Tests for orchestrator parse_args()."""

    def test_ut_or_01_prompt_flag_required(self):
        """UT-OR-01: --prompt or --prompt-file is required."""
        import pytest
        with pytest.raises(SystemExit):
            parse_args.__wrapped__ if hasattr(parse_args, '__wrapped__') else None
            # argparse calls sys.exit on error
            with unittest.mock.patch("sys.argv", ["orchestrator.py"]):
                parse_args()

    def test_ut_or_02_prompt_text(self):
        """UT-OR-02: --prompt accepts literal text."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "Hello world"]):
            args = parse_args()
        assert args.prompt == "Hello world"
        assert args.prompt_file is None

    def test_ut_or_03_prompt_file(self):
        """UT-OR-03: --prompt-file accepts a file path."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt-file", "/tmp/test.md"]):
            args = parse_args()
        assert args.prompt_file == "/tmp/test.md"
        assert args.prompt is None

    def test_ut_or_04_mode_default_regular(self):
        """UT-OR-04: Default mode is REGULAR."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test"]):
            args = parse_args()
        assert args.mode == "REGULAR"

    def test_ut_or_05_mode_deep(self):
        """UT-OR-05: --mode DEEP is accepted (case insensitive)."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--mode", "deep"]):
            args = parse_args()
        assert args.mode == "DEEP"

    def test_ut_or_06_task_name(self):
        """UT-OR-06: --task-name is stored correctly."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--task-name", "My Run"]):
            args = parse_args()
        assert args.task_name == "My Run"

    def test_ut_or_07_resolve_output_dir_with_task_name(self):
        """UT-OR-07: _resolve_output_dir with task-name returns reports/<task-name>."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--task-name", "My Run"]):
            args = parse_args()
        resolved = orchestrator._resolve_output_dir(args)
        assert resolved.endswith("reports/My Run"), f"Expected path ending with 'reports/My Run', got: {resolved}"

    def test_ut_or_08_platforms_default_all(self):
        """UT-OR-08: Default --platforms is 'all'."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test"]):
            args = parse_args()
        assert args.platforms == "all"

    def test_ut_or_09_platforms_custom(self):
        """UT-OR-09: --platforms accepts comma-separated list."""
        with unittest.mock.patch("sys.argv", [
            "orchestrator.py", "--prompt", "test",
            "--platforms", "claude_ai,chatgpt"
        ]):
            args = parse_args()
        assert args.platforms == "claude_ai,chatgpt"

    def test_ut_or_10_tier_default_free(self):
        """UT-OR-10: Default tier is 'free'."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test"]):
            args = parse_args()
        assert args.tier == "free"

    def test_ut_or_11_headless_flag(self):
        """UT-OR-11: --headless flag is stored as True."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--headless"]):
            args = parse_args()
        assert args.headless is True
