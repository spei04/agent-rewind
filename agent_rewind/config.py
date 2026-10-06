from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REWIND_", env_file=".env", extra="ignore")
    mode: Literal["development", "production"] = "development"
    database_url: str = "sqlite:///.rewind/metadata.sqlite"
    data_dir: Path = Path(".rewind")
    encryption_key: SecretStr
    bootstrap_key: SecretStr | None = None
    public_url: str = "http://127.0.0.1:8080"
    storage: Literal["local", "s3"] = "local"
    s3_bucket: str = ""
    s3_endpoint: str | None = None
    s3_region: str = "us-east-1"
    sandbox_runtime: str = "runsc"
    allow_insecure_runtime: bool = False
    allowed_images: str = ""
    sandbox_memory_mb: int = 512
    workspace_mb: int = 32
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr | None = None
    oidc_audience: str = ""
    oidc_role_claim: str = "rewind_role"
    model_url: str = ""
    model_api_key: SecretStr | None = None
    model_name: str = ""
    model_input_price: float = 0
    model_output_price: float = 0
    model_seed_supported: bool = False
    model_reasoning_effort: Literal[
        "", "none", "minimal", "low", "medium", "high", "xhigh", "max"
    ] = ""
    model_max_input_tokens: int = Field(default=128000, ge=1000, le=1000000)
    model_max_output_tokens: int = Field(default=2048, ge=1, le=128000)
    model_timeout_seconds: int = 90
    max_job_seconds: int = 7200

    @model_validator(mode="after")
    def secure_defaults(self) -> "Settings":
        if self.mode == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL.")
            if self.sandbox_runtime != "runsc" or self.allow_insecure_runtime:
                raise ValueError("Production requires runsc; insecure fallback is forbidden.")
            if not self.oidc_issuer or not self.oidc_client_id:
                raise ValueError("Production requires an identity provider.")
            if not self.public_url.startswith("https://"):
                raise ValueError("Production requires an HTTPS public URL.")
        for url in (self.model_url, self.oidc_issuer):
            if url and urlparse(url).scheme != "https":
                raise ValueError("Identity and model endpoints must use HTTPS.")
        if self.storage == "s3" and not self.s3_bucket:
            raise ValueError("S3 storage requires a bucket.")
        if self.bootstrap_key and len(self.bootstrap_key.get_secret_value()) < 32:
            raise ValueError("Bootstrap API keys must contain at least 32 characters.")
        if not 8 <= self.workspace_mb <= 512 or not 128 <= self.sandbox_memory_mb <= 8192:
            raise ValueError("Workspace or memory limit is out of range.")
        if self.model_input_price < 0 or self.model_output_price < 0:
            raise ValueError("Model prices cannot be negative.")
        return self
