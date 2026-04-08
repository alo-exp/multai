"""Unit tests for engine_setup.py.

Tests for _strip_quotes, _load_dotenv, _ensure_venv, _ensure_dependencies,
_verify_playwright, _verify_browser_use.

Each test imports the real engine_setup module (bypassing any stub) and
restores a stub in teardown so other test modules are not affected.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


def _stub_engine_setup():
    """Install a no-op engine_setup stub into sys.modules."""
    stub = types.ModuleType("engine_setup")
    stub._load_dotenv = lambda: None
    stub._ensure_venv = lambda: None
    stub._ensure_dependencies = lambda: None
    sys.modules["engine_setup"] = stub


def _import_real_engine_setup():
    """Remove any stub and load the real engine_setup module fresh."""
    sys.modules.pop("engine_setup", None)
    spec = importlib.util.spec_from_file_location(
        "engine_setup", Path(ENGINE_DIR) / "engine_setup.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["engine_setup"] = module
    spec.loader.exec_module(module)
    return module


import pytest


@pytest.fixture(autouse=True)
def _restore_stub():
    """Restore the engine_setup stub after each test."""
    yield
    _stub_engine_setup()


class TestStripQuotes:
    """Tests for _strip_quotes."""

    def test_strip_quotes_double(self):
        """Double-quoted value is stripped."""
        es = _import_real_engine_setup()
        assert es._strip_quotes('"hello"') == "hello"

    def test_strip_quotes_single(self):
        """Single-quoted value is stripped."""
        es = _import_real_engine_setup()
        assert es._strip_quotes("'hello'") == "hello"

    def test_strip_quotes_none(self):
        """Unquoted value is returned unchanged."""
        es = _import_real_engine_setup()
        assert es._strip_quotes("hello") == "hello"

    def test_strip_quotes_mismatched(self):
        """Mismatched quotes are not stripped."""
        es = _import_real_engine_setup()
        assert es._strip_quotes("'hello\"") == "'hello\""

    def test_strip_quotes_short_string(self):
        """Single char string is returned unchanged."""
        es = _import_real_engine_setup()
        assert es._strip_quotes('"') == '"'

    def test_strip_quotes_empty(self):
        """Empty string is returned unchanged."""
        es = _import_real_engine_setup()
        assert es._strip_quotes("") == ""


class TestLoadDotenv:
    """Tests for _load_dotenv."""

    def test_load_dotenv_reads_env_file(self, tmp_path):
        """_load_dotenv reads KEY=value from .env file."""
        es = _import_real_engine_setup()
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY_XYZ=test_value_xyz\n", encoding="utf-8")

        os.environ.pop("TEST_KEY_XYZ", None)
        try:
            # Patch the module-level _PROJECT_ROOT in the loaded module
            es._PROJECT_ROOT = tmp_path
            es._load_dotenv()
            assert os.environ.get("TEST_KEY_XYZ") == "test_value_xyz"
        finally:
            os.environ.pop("TEST_KEY_XYZ", None)

    def test_load_dotenv_skips_existing(self, tmp_path):
        """_load_dotenv does not overwrite existing env vars."""
        es = _import_real_engine_setup()
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_KEY_ZZZ=new_value\n", encoding="utf-8")

        os.environ["EXISTING_KEY_ZZZ"] = "original"
        try:
            es._PROJECT_ROOT = tmp_path
            es._load_dotenv()
            assert os.environ["EXISTING_KEY_ZZZ"] == "original"
        finally:
            os.environ.pop("EXISTING_KEY_ZZZ", None)

    def test_load_dotenv_handles_comments_and_blanks(self, tmp_path):
        """_load_dotenv skips comments and blank lines."""
        es = _import_real_engine_setup()
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nVALID_KEY_ABC=hello\n", encoding="utf-8")

        os.environ.pop("VALID_KEY_ABC", None)
        try:
            es._PROJECT_ROOT = tmp_path
            es._load_dotenv()
            assert os.environ.get("VALID_KEY_ABC") == "hello"
        finally:
            os.environ.pop("VALID_KEY_ABC", None)

    def test_load_dotenv_strips_quotes(self, tmp_path):
        """_load_dotenv strips quotes from values."""
        es = _import_real_engine_setup()
        env_file = tmp_path / ".env"
        env_file.write_text('QUOTED_KEY_QQQ="quoted_value"\n', encoding="utf-8")

        os.environ.pop("QUOTED_KEY_QQQ", None)
        try:
            es._PROJECT_ROOT = tmp_path
            es._load_dotenv()
            assert os.environ.get("QUOTED_KEY_QQQ") == "quoted_value"
        finally:
            os.environ.pop("QUOTED_KEY_QQQ", None)

    def test_load_dotenv_no_file(self, tmp_path):
        """_load_dotenv does not raise when .env file does not exist."""
        es = _import_real_engine_setup()
        es._PROJECT_ROOT = tmp_path
        # No .env file in tmp_path
        es._load_dotenv()  # Should not raise


class TestEnsureVenv:
    """Tests for _ensure_venv.

    Logic: returns early (noop) if sys.prefix != sys.base_prefix (already IN venv).
    Calls check_call/execv when sys.prefix == sys.base_prefix (NOT in venv).

    Since patch() doesn't intercept es.subprocess/es.os (separate references),
    we patch the module's attributes directly and restore them.
    """

    def test_ensure_venv_noop_in_venv(self):
        """_ensure_venv returns immediately when already in a venv."""
        es = _import_real_engine_setup()
        orig_prefix = sys.prefix
        orig_base = sys.base_prefix
        # prefix != base_prefix => we ARE in a venv => early return
        sys.prefix = "/venv/path"
        sys.base_prefix = "/system/path"
        mock_cc = MagicMock()
        mock_execv = MagicMock()
        orig_cc = es.subprocess.check_call
        orig_execv = es.os.execv
        es.subprocess.check_call = mock_cc
        es.os.execv = mock_execv
        try:
            es._ensure_venv()
            mock_cc.assert_not_called()
            mock_execv.assert_not_called()
        finally:
            es.subprocess.check_call = orig_cc
            es.os.execv = orig_execv
            sys.prefix = orig_prefix
            sys.base_prefix = orig_base

    def test_ensure_venv_creates_venv_when_missing(self, tmp_path):
        """_ensure_venv creates venv + re-execs when NOT in venv and venv missing."""
        es = _import_real_engine_setup()
        orig_prefix = sys.prefix
        orig_base = sys.base_prefix
        orig_file = es._ensure_venv.__globals__["__file__"]
        # prefix == base_prefix => NOT in a venv => proceed
        sys.prefix = "/system/base"
        sys.base_prefix = "/system/base"
        # Point __file__ so venv dir is tmp_path/.venv (doesn't exist)
        es._ensure_venv.__globals__["__file__"] = str(tmp_path / "engine_setup.py")
        mock_cc = MagicMock(return_value=0)
        mock_execv = MagicMock()
        orig_cc = es.subprocess.check_call
        orig_execv = es.os.execv
        es.subprocess.check_call = mock_cc
        es.os.execv = mock_execv
        try:
            es._ensure_venv()
            mock_cc.assert_called_once()
            mock_execv.assert_called_once()
        finally:
            es.subprocess.check_call = orig_cc
            es.os.execv = orig_execv
            es._ensure_venv.__globals__["__file__"] = orig_file
            sys.prefix = orig_prefix
            sys.base_prefix = orig_base

    def test_ensure_venv_execs_if_venv_exists(self, tmp_path):
        """_ensure_venv re-execs without creating venv when venv python exists."""
        es = _import_real_engine_setup()
        # Create venv python at expected path
        venv_python = tmp_path / ".venv" / "bin" / "python3"
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()

        orig_prefix = sys.prefix
        orig_base = sys.base_prefix
        orig_file = es._ensure_venv.__globals__["__file__"]
        sys.prefix = "/system/base"
        sys.base_prefix = "/system/base"
        es._ensure_venv.__globals__["__file__"] = str(tmp_path / "engine_setup.py")
        mock_cc = MagicMock()
        mock_execv = MagicMock()
        orig_cc = es.subprocess.check_call
        orig_execv = es.os.execv
        es.subprocess.check_call = mock_cc
        es.os.execv = mock_execv
        try:
            es._ensure_venv()
            mock_cc.assert_not_called()
            mock_execv.assert_called_once()
        finally:
            es.subprocess.check_call = orig_cc
            es.os.execv = orig_execv
            es._ensure_venv.__globals__["__file__"] = orig_file
            sys.prefix = orig_prefix
            sys.base_prefix = orig_base


class TestEnsureDependencies:
    """Tests for _ensure_dependencies."""

    def test_ensure_dependencies_playwright_present(self):
        """No pip install for playwright when already importable."""
        es = _import_real_engine_setup()
        with patch("importlib.util.find_spec", return_value=MagicMock()), \
             patch("subprocess.check_call") as mock_cc, \
             patch.object(es, "_verify_playwright", return_value=None), \
             patch.object(es, "_verify_browser_use", return_value=None):
            es._ensure_dependencies()
            for call in mock_cc.call_args_list:
                args_str = " ".join(str(a) for a in call[0][0])
                assert "playwright==1.58.0" not in args_str

    def test_ensure_dependencies_playwright_missing_installs(self):
        """pip install playwright called when playwright is missing."""
        es = _import_real_engine_setup()

        def fake_find_spec(name):
            if name == "playwright":
                return None
            return MagicMock()

        with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
             patch("subprocess.check_call") as mock_cc, \
             patch.object(es, "_verify_playwright", return_value=None), \
             patch.object(es, "_verify_browser_use", return_value=None):
            es._ensure_dependencies()
            called_args = [" ".join(str(a) for a in c[0][0]) for c in mock_cc.call_args_list]
            assert any("playwright" in a for a in called_args)

    def test_ensure_dependencies_browser_use_missing_installs(self):
        """pip install browser-use called when browser_use is missing."""
        es = _import_real_engine_setup()

        def fake_find_spec(name):
            if name == "browser_use":
                return None
            return MagicMock()

        with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
             patch("subprocess.check_call") as mock_cc, \
             patch.object(es, "_verify_playwright", return_value=None), \
             patch.object(es, "_verify_browser_use", return_value=None):
            es._ensure_dependencies()
            called_args = [" ".join(str(a) for a in c[0][0]) for c in mock_cc.call_args_list]
            assert any("browser-use" in a for a in called_args)

    def test_ensure_dependencies_optional_install_failure_nonfatal(self):
        """Optional package install failure does not exit."""
        es = _import_real_engine_setup()
        import subprocess

        def fake_find_spec(name):
            if name == "browser_use":
                return None
            return MagicMock()

        call_count = [0]
        def fake_check_call(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                raise subprocess.CalledProcessError(1, args[0])

        with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
             patch("subprocess.check_call", side_effect=fake_check_call), \
             patch.object(es, "_verify_playwright", return_value=None):
            es._ensure_dependencies()  # Should not raise


class TestVerifyPlaywright:
    """Tests for _verify_playwright."""

    def test_verify_playwright_cached_stamp(self, tmp_path):
        """Stamp file with matching version skips subprocess call."""
        es = _import_real_engine_setup()
        venv_dir = tmp_path
        python_exe = str(tmp_path / "bin" / "python3")
        stamp = venv_dir / ".playwright-verified"

        pw_version = "1.58.0"
        stamp.write_text(pw_version, encoding="utf-8")

        with patch("importlib.metadata.version", return_value=pw_version), \
             patch("subprocess.run") as mock_run:
            es._verify_playwright(python_exe)
            mock_run.assert_not_called()

    def test_verify_playwright_import_fails(self, tmp_path, capsys):
        """Warning printed when playwright import subprocess returns non-zero."""
        es = _import_real_engine_setup()
        python_exe = str(tmp_path / "bin" / "python3")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("importlib.metadata.version", side_effect=Exception("not installed")), \
             patch("subprocess.run", return_value=mock_result):
            es._verify_playwright(python_exe)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_verify_playwright_headless_fails(self, tmp_path, capsys):
        """Warning printed when headless launch fails."""
        es = _import_real_engine_setup()
        python_exe = str(tmp_path / "bin" / "python3")

        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = "OK"

        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stdout = ""

        call_count = [0]
        def fake_run(*args, **kwargs):
            call_count[0] += 1
            return ok_result if call_count[0] == 1 else fail_result

        with patch("importlib.metadata.version", side_effect=Exception("not installed")), \
             patch("subprocess.run", side_effect=fake_run):
            es._verify_playwright(python_exe)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_verify_playwright_writes_stamp(self, tmp_path):
        """Stamp file written after successful verification."""
        es = _import_real_engine_setup()
        venv_dir = tmp_path
        python_exe = str(tmp_path / "bin" / "python3")
        stamp = venv_dir / ".playwright-verified"

        pw_version = "1.58.0"
        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = "OK"

        with patch("importlib.metadata.version", return_value=pw_version), \
             patch("subprocess.run", return_value=ok_result):
            es._verify_playwright(python_exe)

        assert stamp.exists()
        assert stamp.read_text() == pw_version

    def test_verify_playwright_exception_during_import_check(self, tmp_path, capsys):
        """Warning printed when subprocess.run raises during import check."""
        es = _import_real_engine_setup()
        python_exe = str(tmp_path / "bin" / "python3")

        with patch("importlib.metadata.version", side_effect=Exception("not installed")), \
             patch("subprocess.run", side_effect=Exception("no python")):
            es._verify_playwright(python_exe)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_verify_playwright_exception_during_headless_check(self, tmp_path, capsys):
        """Warning printed when subprocess.run raises during headless check."""
        es = _import_real_engine_setup()
        python_exe = str(tmp_path / "bin" / "python3")

        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = "OK"

        call_count = [0]
        def fake_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ok_result
            raise Exception("chromium crash")

        with patch("importlib.metadata.version", side_effect=Exception("not installed")), \
             patch("subprocess.run", side_effect=fake_run):
            es._verify_playwright(python_exe)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out


class TestVerifyBrowserUse:
    """Tests for _verify_browser_use."""

    def test_verify_browser_use_ok(self):
        """No warning when browser-use imports OK."""
        es = _import_real_engine_setup()
        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = "OK"

        with patch("subprocess.run", return_value=ok_result):
            es._verify_browser_use("/fake/python3")  # No exception

    def test_verify_browser_use_fail(self, capsys):
        """Warning printed when browser-use import fails."""
        es = _import_real_engine_setup()
        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stdout = ""

        with patch("subprocess.run", return_value=fail_result):
            es._verify_browser_use("/fake/python3")

        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_verify_browser_use_exception(self, capsys):
        """Warning printed when subprocess raises."""
        es = _import_real_engine_setup()
        with patch("subprocess.run", side_effect=Exception("no python")):
            es._verify_browser_use("/fake/python3")

        captured = capsys.readouterr()
        assert "WARNING" in captured.out


class TestLoadDotenvLineCoverage:
    """Additional tests to cover line 32 (_load_dotenv continue branch)."""

    def test_load_dotenv_line_without_equals(self, tmp_path):
        """Line without '=' is skipped (hits continue on line 32)."""
        es = _import_real_engine_setup()
        env_file = tmp_path / ".env"
        env_file.write_text("NO_EQUALS_HERE\nGOOD_KEY_LLL=value\n", encoding="utf-8")
        os.environ.pop("GOOD_KEY_LLL", None)
        try:
            es._PROJECT_ROOT = tmp_path
            es._load_dotenv()
            assert os.environ.get("GOOD_KEY_LLL") == "value"
        finally:
            os.environ.pop("GOOD_KEY_LLL", None)


class TestVerifyPlaywrightStampException:
    """Cover lines 84-85: stamp file read raises exception."""

    def test_verify_playwright_stamp_read_exception(self, tmp_path):
        """Lines 84-85: exception reading stamp file is swallowed, verification proceeds."""
        es = _import_real_engine_setup()
        python_exe = str(tmp_path / "bin" / "python3")
        stamp = tmp_path / ".playwright-verified"
        stamp.write_text("1.58.0", encoding="utf-8")

        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = "OK"

        # Make stamp.read_text raise so the except branch at line 84-85 is hit
        with patch("importlib.metadata.version", return_value="1.58.0"), \
             patch("pathlib.Path.read_text", side_effect=OSError("disk error")), \
             patch("subprocess.run", return_value=ok_result):
            es._verify_playwright(python_exe)
            # Should not raise — stamp read exception is silently swallowed


class TestVerifyPlaywrightStampWriteException:
    """Cover lines 135-136: stamp file write raises exception."""

    def test_verify_playwright_stamp_write_exception(self, tmp_path, capsys):
        """Lines 135-136: exception writing stamp is swallowed (non-fatal)."""
        es = _import_real_engine_setup()
        python_exe = str(tmp_path / "bin" / "python3")

        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = "OK"

        with patch("importlib.metadata.version", return_value="1.58.0"), \
             patch("subprocess.run", return_value=ok_result), \
             patch("pathlib.Path.write_text", side_effect=OSError("read-only")):
            es._verify_playwright(python_exe)
            # Should not raise — write exception is non-fatal


class TestEnsureDependenciesFailPaths:
    """Cover lines 169-172, 178-181: playwright install failure causes sys.exit(1)."""

    def test_playwright_pip_install_failure_exits(self):
        """Lines 169-172: playwright pip install fails -> sys.exit(1)."""
        import subprocess as sp
        es = _import_real_engine_setup()

        def fake_find_spec(name):
            if name == "playwright":
                return None
            return MagicMock()

        call_count = [0]
        def fake_check_call(*args, **kwargs):
            call_count[0] += 1
            raise sp.CalledProcessError(1, args[0])

        orig_cc = es.subprocess.check_call
        exit_called = []
        orig_exit = es.sys.exit
        es.subprocess.check_call = fake_check_call
        es.sys.exit = lambda code: exit_called.append(code)
        try:
            with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
                 patch.object(es, "_verify_playwright", return_value=None):
                es._ensure_dependencies()
        finally:
            es.subprocess.check_call = orig_cc
            es.sys.exit = orig_exit
        assert 1 in exit_called

    def test_playwright_chromium_install_failure_exits(self):
        """Lines 178-181: chromium install fails -> sys.exit(1)."""
        import subprocess as sp
        es = _import_real_engine_setup()

        def fake_find_spec(name):
            if name == "playwright":
                return None
            return MagicMock()

        call_count = [0]
        def fake_check_call(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return 0  # pip install playwright OK
            raise sp.CalledProcessError(1, args[0])  # playwright install chromium FAIL

        orig_cc = es.subprocess.check_call
        exit_called = []
        orig_exit = es.sys.exit
        es.subprocess.check_call = fake_check_call
        es.sys.exit = lambda code: exit_called.append(code)
        try:
            with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
                 patch.object(es, "_verify_playwright", return_value=None):
                es._ensure_dependencies()
        finally:
            es.subprocess.check_call = orig_cc
            es.sys.exit = orig_exit
        assert 1 in exit_called

    def test_optional_install_failure_nonfatal_with_verify(self):
        """Lines 198-201: optional package install failure is non-fatal."""
        import subprocess as sp
        es = _import_real_engine_setup()

        def fake_find_spec(name):
            if name == "browser_use":
                return None
            return MagicMock()

        def fake_check_call(*args, **kwargs):
            raise sp.CalledProcessError(1, args[0])

        orig_cc = es.subprocess.check_call
        es.subprocess.check_call = fake_check_call
        try:
            with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
                 patch.object(es, "_verify_playwright", return_value=None):
                es._ensure_dependencies()  # Should not raise or exit
        finally:
            es.subprocess.check_call = orig_cc
