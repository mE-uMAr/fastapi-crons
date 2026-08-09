"""Tests for the fastapi-crons console script and CLI commands."""

import re
import threading
from importlib import metadata
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fastapi_crons.cli as cli_module
from fastapi_crons.cli import cli

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_cli_backends(temp_db):
    """Point the CLI at a throwaway database and clear its cached backends."""
    original_path = cli_module.config.sqlite_db_path
    cli_module.config.sqlite_db_path = temp_db
    cli_module.state_backend = None
    cli_module.lock_manager = None
    yield
    cli_module.config.sqlite_db_path = original_path
    cli_module.state_backend = None
    cli_module.lock_manager = None


def declared_console_scripts() -> dict[str, str]:
    """The console scripts fastapi-crons declares.

    Read from installed metadata when the package is installed, which is what
    actually decides whether pip creates the script. Fall back to pyproject.toml
    for a plain source checkout. tomllib is deliberately not used: it only
    exists on 3.11+ and this package supports 3.10.
    """
    try:
        dist = metadata.distribution("fastapi-crons")
    except metadata.PackageNotFoundError:
        dist = None

    if dist is not None:
        return {ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"}

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    section = re.search(
        r"^\[project\.scripts\]\s*$(.*?)(?=^\[|\Z)",
        pyproject.read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    if section is None:
        return {}

    return dict(re.findall(r'^\s*"?([\w.-]+)"?\s*=\s*"([^"]+)"', section.group(1), re.MULTILINE))


class TestConsoleScript:
    """The entry point declared in pyproject.toml (issue #18)."""

    def test_console_script_is_declared(self):
        """The documented fastapi-crons script must be declared."""
        assert declared_console_scripts().get("fastapi-crons") == "fastapi_crons.cli:cli"

    def test_entry_point_target_is_callable(self):
        """The path in the entry point must resolve to the Typer app."""
        assert callable(cli)


class TestCommandNames:
    """Command names are pinned, so the documented ones cannot drift."""

    @pytest.mark.parametrize(
        "name",
        ["list", "run-job", "status", "config-set", "config-show", "start-scheduler", "logs"],
    )
    def test_command_is_registered(self, name):
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert name in result.stdout


class TestCommands:
    """Commands run to completion and release their backends."""

    def test_list_with_no_jobs(self):
        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "No jobs found" in result.stdout

    def test_status(self):
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "System Status" in result.stdout

    def test_config_show(self):
        result = runner.invoke(cli, ["config-show"])

        assert result.exit_code == 0
        assert "sqlite_db_path" in result.stdout

    def test_run_job_with_unknown_name(self):
        result = runner.invoke(cli, ["run-job", "does-not-exist"])

        assert result.exit_code == 0
        assert "not found" in result.stdout

    def test_run_job_with_unimportable_module(self):
        result = runner.invoke(cli, ["run-job", "whatever", "-i", "no_such_module_here"])

        assert result.exit_code == 1
        assert "Could not import" in result.stdout

    def test_backends_are_closed_after_a_command(self):
        """aiosqlite's worker thread is not a daemon: an unclosed connection
        keeps the interpreter alive forever after the command has printed."""
        before = {t.name for t in threading.enumerate()}

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert cli_module.state_backend is None

        leaked = [
            t
            for t in threading.enumerate()
            if t.name not in before and t.is_alive() and not t.daemon
        ]
        assert leaked == []
