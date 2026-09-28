from __future__ import annotations

from nutriathena_agent import main as cli


def test_cli_without_arguments_runs_the_default_offline_graph(monkeypatch):
    received: list[str] = []
    monkeypatch.setattr(cli, "run_graph", received.append)

    assert cli.main([]) == 0
    assert received == [cli.DEFAULT_TEXT]
