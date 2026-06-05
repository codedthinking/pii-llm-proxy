from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    upstream_base_url: str = "https://openrouter.ai/api/v1"
    upstream_api_key: str | None = None  # fallback if client doesn't send auth
    session_ttl_seconds: int = 3600
    salt_length_bytes: int = 16
    inject_system_notice: bool = True
    pii_detector_backend: str = "regex"  # "regex" or "presidio"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
