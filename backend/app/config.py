from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FC_", extra="ignore")

    ollama_url: str = "http://localhost:11434"
    # Verify these tags against the Ollama library when pulling; override via FC_* env vars.
    reasoning_model: str = "qwen3:14b"
    fallback_model: str = "gemma3:12b"
    embedding_model: str = "bge-m3"

    llm_timeout_s: float = 180.0
    llm_json_retries: int = 2
    llm_temperature: float = 0.1

    http_timeout_s: float = 15.0
    max_evidence_per_claim: int = 12
    max_claims: int = 5

    # Optional keys for evidence sources; adapters skip themselves when unset.
    google_factcheck_api_key: str = ""
    data_gov_in_api_key: str = ""
    tavily_api_key: str = ""
    searxng_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
