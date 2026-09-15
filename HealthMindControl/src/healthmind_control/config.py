from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HMC_", env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 8765
    database_dsn: str | None = None
    nutri_database_dsn: str | None = None
    kafka_bootstrap_servers: str = ""
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: str | None = None
    kafka_ssl_ca_location: str | None = None
    dify_url: str = ""
    mcp_url: str = ""
    auth_url: str = ""
    dify_console_token: str | None = None
    difyctl_path: str = "difyctl"
    nutri_api_url: str = ""
    enable_expert_mode: bool = False
    debug_db_path: Path = ROOT / "var" / "debug" / "control.sqlite3"
    refresh_seconds: int = Field(5, ge=2, le=60)
    stale_minutes: int = Field(5, ge=1, le=1440)
    query_limit: int = Field(100, ge=1, le=100)
    preview_ttl_seconds: int = Field(120, ge=30, le=600)
    task_retention_days: int = Field(180, ge=1, le=3650)
    audit_path: Path = ROOT / "var" / "audit" / "admin-actions.jsonl"
    kafka_max_scan_messages: int = Field(50000, ge=100, le=500000)
    kafka_metadata_cache_seconds: int = Field(8, ge=2, le=300)
    probe_cache_ttl_seconds: int = Field(15, ge=5, le=300)
    database_pool_min_size: int = Field(1, ge=0, le=10)
    database_pool_max_size: int = Field(8, ge=1, le=32)

    def missing_external_envs(self) -> tuple[str, ...]:
        required = {
            "HMC_KAFKA_BOOTSTRAP_SERVERS": self.kafka_bootstrap_servers,
            "HMC_DIFY_URL": self.dify_url,
            "HMC_MCP_URL": self.mcp_url,
            "HMC_AUTH_URL": self.auth_url,
        }
        return tuple(name for name, value in required.items() if not value.strip())

    @property
    def nutri_dsn(self) -> str | None:
        return self.nutri_database_dsn or self.database_dsn


settings = Settings()
