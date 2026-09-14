from healthmind_control.config import Settings


def test_external_endpoints_have_no_repository_defaults(monkeypatch):
    for name in (
        "HMC_KAFKA_BOOTSTRAP_SERVERS",
        "HMC_DIFY_URL",
        "HMC_MCP_URL",
        "HMC_AUTH_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)

    assert settings.kafka_bootstrap_servers == ""
    assert settings.dify_url == ""
    assert settings.mcp_url == ""
    assert settings.auth_url == ""
    assert settings.missing_external_envs() == (
        "HMC_KAFKA_BOOTSTRAP_SERVERS",
        "HMC_DIFY_URL",
        "HMC_MCP_URL",
        "HMC_AUTH_URL",
    )


def test_external_endpoints_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("HMC_KAFKA_BOOTSTRAP_SERVERS", "kafka.example.invalid:9092")
    monkeypatch.setenv("HMC_DIFY_URL", "https://dify.example.invalid")
    monkeypatch.setenv("HMC_MCP_URL", "https://mcp.example.invalid/mcp")
    monkeypatch.setenv("HMC_AUTH_URL", "https://auth.example.invalid")

    settings = Settings(_env_file=None)

    assert settings.missing_external_envs() == ()
    assert settings.mcp_url.endswith("/mcp")
