"""Tests for the render_page tool: the mocked unit tests cover its
subprocess-handling logic (success/timeout/crash/malformed-output), and
a real end-to-end test actually launches the subprocess (real Chromium,
real page) to verify the whole path works, not just the plumbing around
it - the failure mode this exists to catch (an OOM-killed render) can
only show up when something really runs the browser."""

from unittest.mock import MagicMock, patch

from agentos.tools.browser import render_page


def _completed(stdout="", stderr="", returncode=0):
    return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)


def test_render_page_success():
    ok = _completed(stdout='{"title": "Example Domain", "text": "This is an example page."}\n')
    with patch("agentos.tools.browser.subprocess.run", return_value=ok) as mock_run:
        result = render_page(url="https://example.com")

    assert "Example Domain" in result
    assert "This is an example page." in result
    args = mock_run.call_args.args[0]
    assert args[-1] == "https://example.com"
    assert "agentos.tools._render_subprocess" in args


def test_render_page_reports_tool_level_error():
    err = _completed(stdout='{"error": "not a safe public http(s) URL"}\n')
    with patch("agentos.tools.browser.subprocess.run", return_value=err):
        result = render_page(url="http://127.0.0.1/secret")
    assert "not a safe public" in result


def test_render_page_handles_timeout():
    import subprocess as subprocess_module

    with patch("agentos.tools.browser.subprocess.run",
              side_effect=subprocess_module.TimeoutExpired(cmd="x", timeout=25)):
        result = render_page(url="https://example.com")
    assert "timed out" in result


def test_render_page_handles_oom_kill():
    # a negative returncode (e.g. -9) means the OS killed the process by
    # signal - this is exactly the failure mode subprocess isolation
    # exists to contain, so it must be reported, not raise or hang
    killed = _completed(stdout="", stderr="", returncode=-9)
    with patch("agentos.tools.browser.subprocess.run", return_value=killed):
        result = render_page(url="https://example.com")
    assert "failed" in result.lower()
    assert "-9" in result


def test_render_page_handles_malformed_output():
    garbled = _completed(stdout="not json at all")
    with patch("agentos.tools.browser.subprocess.run", return_value=garbled):
        result = render_page(url="https://example.com")
    assert "unexpected output" in result


def test_render_page_end_to_end_real_browser():
    """No mocking: actually runs the subprocess against a real page and
    confirms the whole path - subprocess launch, real Chromium, real
    navigation, JSON handoff back - works, not just each piece in
    isolation. Uses pypi.org rather than example.com since some sandboxed
    CI-like network policies allow the former but not the latter."""
    import socket

    try:
        socket.create_connection(("pypi.org", 443), timeout=5).close()
    except OSError:
        import pytest
        pytest.skip("no network access to pypi.org in this environment")

    result = render_page(url="https://pypi.org/")
    assert "unavailable" not in result.lower()
    assert "failed" not in result.lower()
    assert "PyPI" in result
