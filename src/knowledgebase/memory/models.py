"""Data models for OpenClaw Memory Module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class MemoryType(str, Enum):
    """Types of memory an agent can store."""

    EPISODIC = "episodic"      # Events, observations, things that happened
    SEMANTIC = "semantic"      # Facts, learnings, knowledge
    PROCEDURAL = "procedural"  # How-to, workflows, procedures


class Scope(str, Enum):
    """Visibility scope for a memory entry."""

    PRIVATE = "private"  # Only the owning agent
    TEAM = "team"        # Agents in shared teams
    GLOBAL = "global"    # All agents


@dataclass
class Agent:
    """A registered agent in the memory system."""

    id: UUID
    name: str
    display_name: str | None = None
    agent_type: str = "openclaw"
    metadata: dict = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime | None = None
    last_seen_at: datetime | None = None


@dataclass
class MemoryEntry:
    """A single memory entry (episodic, semantic, or procedural)."""

    id: UUID | None = None
    agent_id: UUID | None = None
    agent_name: str | None = None

    memory_type: MemoryType = MemoryType.SEMANTIC
    scope: Scope = Scope.PRIVATE

    content: str = ""
    summary: str | None = None
    embedding: list[float] | None = None

    # Optional link to existing RAG data
    source_id: int | None = None
    chunk_id: int | None = None

    # Organization
    tags: list[str] = field(default_factory=list)
    namespace: str = "default"
    metadata: dict = field(default_factory=dict)

    # Lifecycle
    importance: float = 0.5
    similarity: float | None = None  # populated by search results
    access_count: int = 0
    created_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass
class Team:
    """A group of agents that can share team-scoped memories."""

    id: UUID | None = None
    name: str = ""
    description: str | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None


@dataclass
class SearchResult:
    """A unified search result from memory + RAG."""

    result_type: str  # "memory" or "rag"
    result_id: str
    agent_name: str | None = None
    content: str = ""
    similarity: float = 0.0
    metadata: dict = field(default_factory=dict)
