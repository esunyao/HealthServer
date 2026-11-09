"""Verify executable behavior independently of Python import seams."""

import os
import subprocess
import sys

import pytest


def run_cli(arguments):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("NUTRIATHENA_", "AGENTDEVELOP_"))
    }
    environment.update(
        PYTHON_DOTENV_DISABLED="1",
        PYTHONIOENCODING="utf-8",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
    )
    return subprocess.run(
        [sys.executable, "-m", "nutriathena_agent.main", *arguments],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


@pytest.mark.parametrize(
    "command", ["graph", "agent", "serve", "migrate", "meal", "smoke"]
)
def test_each_command_help_is_available_without_service_configuration(command):
    result = run_cli([command, "--help"])
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


@pytest.mark.parametrize(
    "arguments",
    [
        ["serve"],
        ["migrate"],
        [
            "meal",
            "--task-id",
            "11111111-1111-4111-8111-111111111111",
            "--attempt-id",
            "22222222-2222-4222-8222-222222222222",
        ],
        [
            "smoke",
            "--task-id",
            "11111111-1111-4111-8111-111111111111",
            "--attempt-id",
            "22222222-2222-4222-8222-222222222222",
            "--trace-id",
            "offline-test",
        ],
    ],
)
def test_service_commands_fail_without_required_configuration(arguments):
    result = run_cli(arguments)
    assert result.returncode == 2


def test_default_executable_runs_the_offline_graph():
    result = run_cli([])
    assert result.returncode == 0, result.stderr
    assert "route = accept" in result.stdout
