from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    remote_llm_base_url: str = "https://openrouter.ai/api/v1"
    session_ttl_seconds: int = 3600
    salt_length_bytes: int = 16
    hash_hex_chars: int = 12
    presidio_entities: list[str] = [
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "DATE_TIME",
        "LOCATION",
        "CREDIT_CARD",
        "IBAN_CODE",
        "US_SSN",
        "NRP",
        "MEDICAL_LICENSE",
    ]
    inject_system_notice: bool = True
    openrouter_api_key: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
