"""
Verify that ``python -m mcp_tts.server.lifecycle`` does NOT emit the
RuntimeWarning about the module already being in sys.modules.

We launch subprocesses with ``-W error`` (turn all warnings into errors)
to confirm the import ordering is correct.
"""

import subprocess
import sys
import textwrap

import pytest


def test_no_runpy_warning_on_server_import():
    """Importing mcp_tts.server must NOT pre-load lifecycle into sys.modules."""
    script = textwrap.dedent("""\
        import sys
        import mcp_tts.server  # this is what runpy does first
        # After the package init, lifecycle must NOT be in sys.modules
        if "mcp_tts.server.lifecycle" in sys.modules:
            print("FAIL: mcp_tts.server.lifecycle found in sys.modules after package import")
            sys.exit(1)
        print("PASS: lifecycle is not prematurely loaded")
    """)

    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"Import test failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "PASS" in result.stdout


def test_no_warning_with_dash_m():
    """``python -W error -m mcp_tts.server.lifecycle`` must not warn.

    We use runpy.run_module() in a subprocess that patches mcp.run()
    to prevent actual server blocking, then verify no warning is raised.
    """
    script = textwrap.dedent("""\
        import sys
        import runpy

        # Patch mcp.run after the package is imported but before
        # lifecycle's run_server is called, so the server doesn't block.
        import mcp_tts.server as _pkg
        _pkg.mcp.run = lambda **kw: None

        # Simulate 'python -m mcp_tts.server.lifecycle'.
        # At this point lifecycle is NOT yet in sys.modules (our fix).
        runpy.run_module("mcp_tts.server.lifecycle", run_name="__main__", alter_sys=True)
        print("PASS: no RuntimeWarning")
    """)

    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"dash-m test failed (return code {result.returncode}).\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
