"""CLI tests for `cli.py social` - added in response to a review comment
pointing out the new command had no coverage. Uses typer's CliRunner,
the standard way to invoke a Typer app's commands in tests without
actually spawning a subprocess."""

from unittest.mock import patch

from typer.testing import CliRunner

from cli import app

runner = CliRunner()


def test_social_disconnect_calls_memory_with_default_scope():
    with patch("agentos.memory.default_memory.disconnect_social") as mock_disconnect:
        result = runner.invoke(app, ["social", "disconnect", "instagram"])
    assert result.exit_code == 0
    assert "Disconnected instagram" in result.output
    mock_disconnect.assert_called_once_with("default", "instagram")


def test_social_disconnect_linkedin():
    with patch("agentos.memory.default_memory.disconnect_social") as mock_disconnect:
        result = runner.invoke(app, ["social", "disconnect", "linkedin"])
    assert result.exit_code == 0
    mock_disconnect.assert_called_once_with("default", "linkedin")


def test_social_rejects_unknown_platform():
    with patch("agentos.memory.default_memory.disconnect_social") as mock_disconnect:
        result = runner.invoke(app, ["social", "disconnect", "twitter"])
    assert result.exit_code == 1
    assert "Usage:" in result.output
    mock_disconnect.assert_not_called()


def test_social_rejects_unknown_action():
    with patch("agentos.memory.default_memory.disconnect_social") as mock_disconnect:
        result = runner.invoke(app, ["social", "connect", "instagram"])
    assert result.exit_code == 1
    assert "Usage:" in result.output
    mock_disconnect.assert_not_called()
