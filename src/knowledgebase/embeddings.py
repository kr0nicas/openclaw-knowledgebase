"""Embedding provider system for OpenClaw Knowledgebase.

Supports multiple embedding backends through a provider registry.
All consumers call get_embedding() / get_embeddings_batch() — the active
provider is selected via EMBEDDING_PROVIDER in config.

Built-in providers:
    - ollama: Local embeddings via Ollama (default)
    - google: Google AI (Gemini) text-embedding-004
    - openai: OpenAI text-embedding-3-small / text-embedding-3-large
    - custom: Bring-your-own via any OpenAI-compatible API

Adding a new provider:
    1. Create a class implementing EmbeddingProvider
    2. Register it with @register_provider("name")
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Any

import requests

from knowledgebase.config import get_config

logger = logging.getLogger(__name__)

# ── Provider registry ────────────────────────────────────────────────

_providers: dict[str, type[EmbeddingProvider]] = {}


def register_provider(name: str):
    """Decorator to register an embedding provider."""
    def decorator(cls: type[EmbeddingProvider]):
        _providers[name] = cls
        return cls
    return decorator


def get_provider(name: str | None = None) -> EmbeddingProvider:
    """Get an initialized provider by name (default: from config)."""
    config = get_config()
    name = name or config.embedding_provider
    cls = _providers.get(name)
    if cls is None:
        available = ", ".join(sorted(_providers.keys()))
        raise ValueError(
            f"Unknown embedding provider '{name}'. Available: {available}"
        )
    return cls(config)


# ── Base class ───────────────────────────────────────────────────────

class EmbeddingProvider(abc.ABC):
    """Base class for embedding providers."""

    def __init__(self, config: Any):
        self.config = config

    @abc.abstractmethod
    def embed(self, text: str) -> list[float] | None:
        """Generate embedding for a single text. Returns None on error."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts.

        Default implementation calls embed() sequentially.
        Providers with native batch support should override this.
        """
        return [self.embed(t) for t in texts]

    @abc.abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Test provider connectivity. Returns (ok, message)."""
        ...

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    def max_chars(self) -> int:
        """Max input characters before truncation. Override per provider."""
        return 8000

    def _truncate(self, text: str) -> str:
        """Truncate text to max_chars."""
        return text[:self.max_chars] if len(text) > self.max_chars else text


# ── Ollama provider ─────────────────────────────────────────────────

@register_provider("ollama")
class OllamaProvider(EmbeddingProvider):

    @property
    def name(self) -> str:
        return "Ollama"

    @property
    def max_chars(self) -> int:
        # nomic-embed-text has ~2k token limit; be conservative
        return 3000

    def embed(self, text: str) -> list[float] | None:
        text = self._truncate(text)
        if not text.strip():
            return None
        try:
            resp = requests.post(
                f"{self.config.ollama_url}/api/embeddings",
                json={"model": self.config.embedding_model, "prompt": text},
                timeout=self.config.embedding_timeout,
            )
            resp.raise_for_status()
            embedding = resp.json().get("embedding")
            return embedding if embedding else None
        except requests.exceptions.RequestException as e:
            logger.warning("Ollama embedding failed: %s", e)
            return None

    def test_connection(self) -> tuple[bool, str]:
        try:
            resp = requests.get(
                f"{self.config.ollama_url}/api/tags", timeout=5
            )
            resp.raise_for_status()
            models = resp.json().get("models", [])
            names = [m.get("name", "").split(":")[0] for m in models]
            if self.config.embedding_model not in names:
                return False, (
                    f"Model '{self.config.embedding_model}' not found. "
                    f"Run: ollama pull {self.config.embedding_model}"
                )
            return True, (
                f"Ollama OK, model '{self.config.embedding_model}' available"
            )
        except requests.exceptions.ConnectionError:
            return False, f"Cannot connect to Ollama at {self.config.ollama_url}"
        except requests.exceptions.RequestException as e:
            return False, f"Ollama error: {e}"


# ── Google AI provider ───────────────────────────────────────────────

@register_provider("google")
class GoogleProvider(EmbeddingProvider):

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"

    @property
    def name(self) -> str:
        return "Google AI"

    @property
    def max_chars(self) -> int:
        return 10000

    def _url(self, action: str = "embedContent") -> str:
        model = self.config.embedding_model
        return f"{self.ENDPOINT}/{model}:{action}?key={self.config.google_api_key}"

    def embed(self, text: str) -> list[float] | None:
        text = self._truncate(text)
        if not text.strip():
            return None
        if not self.config.google_api_key:
            logger.error("GOOGLE_API_KEY not set")
            return None
        try:
            resp = requests.post(
                self._url("embedContent"),
                json={
                    "model": f"models/{self.config.embedding_model}",
                    "content": {"parts": [{"text": text}]},
                    **({"outputDimensionality": self.config.embedding_dimensions}
                       if self.config.embedding_dimensions else {}),
                },
                timeout=self.config.embedding_timeout,
            )
            resp.raise_for_status()
            values = resp.json().get("embedding", {}).get("values")
            return values if values else None
        except requests.exceptions.RequestException as e:
            logger.warning("Google embedding failed: %s", e)
            return None

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Google supports native batch embedding."""
        if not self.config.google_api_key:
            return [None] * len(texts)
        requests_payload = [
            {
                "model": f"models/{self.config.embedding_model}",
                "content": {"parts": [{"text": self._truncate(t)}]},
                **({"outputDimensionality": self.config.embedding_dimensions}
                   if self.config.embedding_dimensions else {}),
            }
            for t in texts
            if t.strip()
        ]
        if not requests_payload:
            return [None] * len(texts)
        try:
            resp = requests.post(
                self._url("batchEmbedContents"),
                json={"requests": requests_payload},
                timeout=self.config.embedding_timeout,
            )
            resp.raise_for_status()
            embeddings = resp.json().get("embeddings", [])
            return [
                e.get("values") if e else None
                for e in embeddings
            ]
        except requests.exceptions.RequestException as e:
            logger.warning("Google batch embedding failed, falling back: %s", e)
            return [self.embed(t) for t in texts]

    def test_connection(self) -> tuple[bool, str]:
        if not self.config.google_api_key:
            return False, "GOOGLE_API_KEY not set"
        try:
            resp = requests.post(
                self._url("embedContent"),
                json={
                    "model": f"models/{self.config.embedding_model}",
                    "content": {"parts": [{"text": "test"}]},
                },
                timeout=10,
            )
            if resp.status_code == 200:
                dims = len(resp.json().get("embedding", {}).get("values", []))
                return True, (
                    f"Google AI OK, model '{self.config.embedding_model}' "
                    f"({dims} dimensions)"
                )
            return False, f"Google AI error: HTTP {resp.status_code} — {resp.text[:200]}"
        except requests.exceptions.RequestException as e:
            return False, f"Google AI error: {e}"


# ── OpenAI provider ─────────────────────────────────────────────────

@register_provider("openai")
class OpenAIProvider(EmbeddingProvider):

    @property
    def name(self) -> str:
        return "OpenAI"

    @property
    def max_chars(self) -> int:
        return 30000  # ~8k tokens

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.openai_api_key}",
            "Content-Type": "application/json",
        }

    def _base_url(self) -> str:
        return self.config.openai_base_url.rstrip("/")

    def embed(self, text: str) -> list[float] | None:
        text = self._truncate(text)
        if not text.strip():
            return None
        if not self.config.openai_api_key:
            logger.error("OPENAI_API_KEY not set")
            return None
        try:
            body: dict = {
                "model": self.config.embedding_model,
                "input": text,
            }
            if self.config.embedding_dimensions:
                body["dimensions"] = self.config.embedding_dimensions
            resp = requests.post(
                f"{self._base_url()}/embeddings",
                headers=self._headers(),
                json=body,
                timeout=self.config.embedding_timeout,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data[0]["embedding"] if data else None
        except requests.exceptions.RequestException as e:
            logger.warning("OpenAI embedding failed: %s", e)
            return None

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """OpenAI supports native batch embedding."""
        if not self.config.openai_api_key:
            return [None] * len(texts)
        truncated = [self._truncate(t) for t in texts if t.strip()]
        if not truncated:
            return [None] * len(texts)
        try:
            body: dict = {
                "model": self.config.embedding_model,
                "input": truncated,
            }
            if self.config.embedding_dimensions:
                body["dimensions"] = self.config.embedding_dimensions
            resp = requests.post(
                f"{self._base_url()}/embeddings",
                headers=self._headers(),
                json=body,
                timeout=self.config.embedding_timeout,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [d["embedding"] for d in data]
        except requests.exceptions.RequestException as e:
            logger.warning("OpenAI batch embedding failed, falling back: %s", e)
            return [self.embed(t) for t in texts]

    def test_connection(self) -> tuple[bool, str]:
        if not self.config.openai_api_key:
            return False, "OPENAI_API_KEY not set"
        try:
            resp = requests.post(
                f"{self._base_url()}/embeddings",
                headers=self._headers(),
                json={"model": self.config.embedding_model, "input": "test"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                dims = len(data[0]["embedding"]) if data else 0
                return True, (
                    f"OpenAI OK, model '{self.config.embedding_model}' "
                    f"({dims} dimensions)"
                )
            return False, f"OpenAI error: HTTP {resp.status_code} — {resp.text[:200]}"
        except requests.exceptions.RequestException as e:
            return False, f"OpenAI error: {e}"


# ── Custom provider (OpenAI-compatible API) ──────────────────────────

@register_provider("custom")
class CustomProvider(OpenAIProvider):
    """Any OpenAI-compatible embedding API (e.g. vLLM, LiteLLM, LocalAI).

    Set OPENAI_BASE_URL to point at your endpoint.
    Uses the same protocol as the OpenAI provider.
    """

    @property
    def name(self) -> str:
        return f"Custom ({self.config.openai_base_url})"


# ── Public API (backwards-compatible) ────────────────────────────────

def get_embedding(text: str, **kwargs) -> list[float] | None:
    """Generate embedding for text using the configured provider.

    This is the primary entry point. All consumers call this function.
    Provider is selected via config.embedding_provider.

    Args:
        text: Text to embed.
        **kwargs: Ignored (kept for backwards compatibility).

    Returns:
        List of floats (embedding vector) or None on error.
    """
    provider = get_provider()
    return provider.embed(text)


def get_embeddings_batch(texts: list[str], **kwargs) -> list[list[float] | None]:
    """Generate embeddings for multiple texts.

    Uses native batch API if the provider supports it,
    otherwise falls back to sequential calls.

    Args:
        texts: List of texts to embed.
        **kwargs: Ignored (kept for backwards compatibility).

    Returns:
        List of embedding vectors (or None for failed embeddings).
    """
    provider = get_provider()
    return provider.embed_batch(texts)


def test_connection(provider_name: str | None = None) -> tuple[bool, str]:
    """Test the embedding provider connection.

    Args:
        provider_name: Override provider (default: from config).

    Returns:
        Tuple of (success, message).
    """
    try:
        provider = get_provider(provider_name)
        return provider.test_connection()
    except ValueError as e:
        return False, str(e)


# Backwards-compatible alias
test_ollama_connection = test_connection


def list_providers() -> list[str]:
    """Return names of all registered providers."""
    return sorted(_providers.keys())
