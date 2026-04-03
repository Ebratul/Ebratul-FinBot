"""
FinBot Configuration using Pydantic Settings.

All settings are loaded from the .env file (or environment variables).
Import `settings` to access any config value across the backend.

Usage:
    from backend.config import settings

    llm = ChatGroq(api_key=settings.groq_api_key, model=settings.groq_model_name)
"""

from functools import lru_cache
from typing import Optional
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────
    groq_api_key: SecretStr = Field(..., description="Groq API key")
    groq_model_name: str = Field("llama3-8b-8192", description="Groq model to use")

    # ── Embedding Model ───────────────────────────────────────
    embed_model_id: str = Field(
        "sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace sentence-transformer model for embeddings",
    )

    # ── Qdrant ────────────────────────────────────────────────
    qdrant_path: str = Field(
        "/tmp/my_lang_vs",
        description="Local path for on-disk Qdrant persistence",
    )
    qdrant_url: str | None = Field(
        None,
        description="Remote Qdrant server URL (overrides qdrant_path if set)",
    )
    qdrant_api_key: SecretStr | None = Field(
        None,
        description="API key for Qdrant Cloud (optional)",
    )

    # ── API Keys ──────────────────────────────────────────────
    hf_token: Optional[SecretStr] = None

    # ── Semantic Router ───────────────────────────────────────
    semantic_router_encoder: str = Field(
        "sentence-transformers/all-MiniLM-L6-v2",
        description="Encoder model for semantic router",
    )

    # ── Session Rate Limiting ─────────────────────────────────
    session_max_queries: int = Field(
        20,
        description="Maximum queries allowed per session",
    )


@lru_cache
def get_settings() -> Settings:
    """Returns the cached Settings singleton. Reads .env once on first call."""
    return Settings()


# Convenience singleton — import this directly everywhere
settings = get_settings()
