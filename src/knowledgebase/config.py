"""Configuration management for OpenClaw Knowledgebase."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Knowledgebase configuration."""

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    table_prefix: str = "kb"

    # Embedding provider
    embedding_provider: str = "ollama"  # ollama | google | openai | custom
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    embedding_timeout: int = 120  # seconds

    # Ollama-specific
    ollama_url: str = "http://localhost:11434"

    # Google AI-specific
    google_api_key: str = ""

    # OpenAI / Custom-specific
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Search
    default_match_count: int = 10
    similarity_threshold: float = 0.5
    semantic_weight: float = 0.7

    # OpenClaw Memory Module (optional — empty = legacy single-tenant mode)
    agent_name: str = ""
    agent_api_key: str = ""

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Config":
        """Load configuration from environment variables."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        return cls(
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_key=os.getenv("SUPABASE_KEY", ""),
            table_prefix=os.getenv("TABLE_PREFIX", "kb"),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "ollama"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "768")),
            embedding_timeout=int(os.getenv("EMBEDDING_TIMEOUT", "120")),
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            google_api_key=os.getenv("GOOGLE_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
            default_match_count=int(os.getenv("DEFAULT_MATCH_COUNT", "10")),
            similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.5")),
            semantic_weight=float(os.getenv("SEMANTIC_WEIGHT", "0.7")),
            agent_name=os.getenv("OPENCLAW_AGENT_NAME", ""),
            agent_api_key=os.getenv("OPENCLAW_AGENT_KEY", ""),
        )

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.supabase_url:
            errors.append("SUPABASE_URL is required")
        if not self.supabase_key:
            errors.append("SUPABASE_KEY is required")

        provider = self.embedding_provider
        if provider == "google" and not self.google_api_key:
            errors.append("GOOGLE_API_KEY is required when EMBEDDING_PROVIDER=google")
        if provider in ("openai", "custom") and not self.openai_api_key:
            errors.append("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai|custom")

        return errors


# Global config instance
_config: Config | None = None

# Cache dict for external clearing
_config_cache: dict = {}


def get_config() -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None or "reload" in _config_cache:
        _config = Config.from_env()
        _config_cache.pop("reload", None)
    return _config


def set_config(config: Config) -> None:
    """Set global config instance."""
    global _config
    _config = config


def reload_config() -> Config:
    """Force reload config from environment."""
    _config_cache["reload"] = True
    return get_config()
