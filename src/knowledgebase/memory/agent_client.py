"""AgentMemory — Multi-agent memory client for OpenClaw.

Wraps the existing KnowledgeBase (for RAG) and adds a memory layer
backed by mb_memory in Supabase. Agents authenticate with API keys
and can store/retrieve memories with configurable scope and type.

Usage:
    from knowledgebase.memory import AgentMemory, Scope

    agent = AgentMemory("my-agent", api_key="oc_sk_...")
    agent.authenticate()

    agent.learn("Users prefer dark mode", scope=Scope.GLOBAL, tags=["ux"])
    results = agent.recall("user preferences")
    combined = agent.recall_all("dark mode")  # memory + RAG
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import requests

from knowledgebase.client import Chunk, KnowledgeBase
from knowledgebase.config import Config, get_config
from knowledgebase.embeddings import get_embedding
from knowledgebase.log import get_logger
from knowledgebase.memory.models import (
    Agent,
    MemoryEntry,
    MemoryType,
    Scope,
    SearchResult,
    Team,
)

logger = get_logger(__name__)


class AgentMemory:
    """Multi-agent memory client.

    Composes (not inherits) KnowledgeBase for RAG operations and adds
    the mb_memory layer for agent-owned memories with scoping.
    """

    def __init__(
        self,
        agent_name: str,
        api_key: str,
        config: Config | None = None,
    ):
        self.config = config or get_config()
        self._agent_name = agent_name
        self._api_key = api_key
        self._agent: Agent | None = None

        # Reuse existing KnowledgeBase for RAG operations
        self._kb = KnowledgeBase(config=self.config)

        self._base_url = self.config.supabase_url
        self._headers = {
            "apikey": self.config.supabase_key,
            "Authorization": f"Bearer {self.config.supabase_key}",
            "Content-Type": "application/json",
        }

    def _rpc(self, fn_name: str, params: dict, timeout: int = 30) -> requests.Response:
        """Call a Supabase RPC function."""
        return requests.post(
            f"{self._base_url}/rest/v1/rpc/{fn_name}",
            headers=self._headers,
            json=params,
            timeout=timeout,
        )

    def _rest(
        self,
        method: str,
        table: str,
        data: dict | list | None = None,
        params: dict | None = None,
        prefer: str | None = None,
    ) -> requests.Response:
        """Make a Supabase REST API request."""
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        return requests.request(
            method,
            f"{self._base_url}/rest/v1/{table}",
            headers=headers,
            json=data,
            params=params,
            timeout=30,
        )

    # ── Authentication ──────────────────────────────────────────────

    @property
    def agent(self) -> Agent:
        """Get the authenticated agent. Raises if not authenticated."""
        if self._agent is None:
            raise RuntimeError(
                "Agent not authenticated. Call authenticate() first."
            )
        return self._agent

    @property
    def agent_id(self) -> UUID:
        """Shortcut to the authenticated agent's ID."""
        return self.agent.id

    def authenticate(self) -> Agent:
        """Authenticate this agent using its API key.

        Returns the Agent on success, raises on failure.
        """
        resp = self._rpc("mb_authenticate_agent", {"p_api_key": self._api_key})
        if resp.status_code != 200:
            raise RuntimeError(f"Authentication failed: HTTP {resp.status_code}")

        results = resp.json()
        if not results:
            raise RuntimeError(
                f"Authentication failed: invalid API key for agent '{self._agent_name}'"
            )

        row = results[0]
        self._agent = Agent(
            id=UUID(row["agent_id"]),
            name=row["agent_name"],
            agent_type=row.get("agent_type", "openclaw"),
        )
        logger.info("Authenticated as agent '%s' (%s)", self._agent.name, self._agent.id)
        return self._agent

    def register(
        self,
        display_name: str | None = None,
        agent_type: str = "openclaw",
        metadata: dict | None = None,
    ) -> Agent:
        """Register this agent (creates it in mb_agents).

        The API key is hashed server-side via pgcrypto.
        Call this once per agent, then use authenticate() afterward.
        """
        resp = self._rpc(
            "mb_register_agent",
            {
                "p_name": self._agent_name,
                "p_api_key": self._api_key,
                "p_display_name": display_name,
                "p_agent_type": agent_type,
                "p_metadata": metadata or {},
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Registration failed: HTTP {resp.status_code} — {resp.text}"
            )

        agent_id = resp.json()
        # Strip quotes if returned as JSON string
        if isinstance(agent_id, str):
            agent_id = agent_id.strip('"')

        self._agent = Agent(
            id=UUID(agent_id),
            name=self._agent_name,
            display_name=display_name,
            agent_type=agent_type,
            metadata=metadata or {},
        )
        logger.info("Registered agent '%s' (%s)", self._agent.name, self._agent.id)
        return self._agent

    # ── Memory CRUD ─────────────────────────────────────────────────

    def remember(
        self,
        content: str,
        *,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        scope: Scope = Scope.PRIVATE,
        tags: list[str] | None = None,
        namespace: str = "default",
        importance: float = 0.5,
        summary: str | None = None,
        metadata: dict | None = None,
        source_id: int | None = None,
        chunk_id: int | None = None,
        expires_at: datetime | None = None,
    ) -> MemoryEntry:
        """Store a memory entry with automatic embedding generation.

        Args:
            content: The text content to remember.
            memory_type: episodic, semantic, or procedural.
            scope: private (only you), team, or global (all agents).
            tags: Optional list of tags for filtering.
            namespace: Logical grouping (e.g. "project-x").
            importance: 0.0-1.0, used for decay/prioritization.
            summary: Short version for listings.
            metadata: Arbitrary JSON metadata.
            source_id: Link to an existing kb_sources entry.
            chunk_id: Link to an existing kb_chunks entry.
            expires_at: Auto-delete after this time (None = never).

        Returns:
            The created MemoryEntry with its ID and embedding.
        """
        # Generate embedding
        embedding = get_embedding(content)

        data = {
            "agent_id": str(self.agent_id),
            "memory_type": memory_type.value,
            "scope": scope.value,
            "content": content,
            "summary": summary,
            "embedding": embedding,
            "tags": tags or [],
            "namespace": namespace,
            "importance": importance,
            "metadata": metadata or {},
        }
        if source_id is not None:
            data["source_id"] = source_id
        if chunk_id is not None:
            data["chunk_id"] = chunk_id
        if expires_at is not None:
            data["expires_at"] = expires_at.isoformat()

        resp = self._rest(
            "POST", "mb_memory", data=data, prefer="return=representation"
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Failed to store memory: HTTP {resp.status_code} — {resp.text}")

        rows = resp.json()
        row = rows[0] if isinstance(rows, list) else rows

        return MemoryEntry(
            id=UUID(row["id"]),
            agent_id=self.agent_id,
            agent_name=self._agent_name,
            memory_type=memory_type,
            scope=scope,
            content=content,
            summary=summary,
            embedding=embedding,
            tags=tags or [],
            namespace=namespace,
            importance=importance,
            metadata=metadata or {},
            source_id=source_id,
            chunk_id=chunk_id,
            created_at=row.get("created_at"),
            expires_at=expires_at,
        )

    def recall(
        self,
        query: str,
        *,
        limit: int = 10,
        memory_types: list[MemoryType] | None = None,
        scopes: list[Scope] | None = None,
        namespace: str | None = None,
        tags: list[str] | None = None,
        threshold: float = 0.5,
    ) -> list[MemoryEntry]:
        """Search agent memories by semantic similarity.

        Returns memories the agent has access to based on scope
        (own private + team + global).
        """
        embedding = get_embedding(query)
        if not embedding:
            return []

        params: dict = {
            "p_agent_id": str(self.agent_id),
            "p_query_embedding": embedding,
            "p_match_count": limit,
            "p_similarity_threshold": threshold,
        }
        if memory_types:
            params["p_memory_types"] = [mt.value for mt in memory_types]
        if scopes:
            params["p_scopes"] = [s.value for s in scopes]
        if namespace:
            params["p_namespace"] = namespace
        if tags:
            params["p_tags"] = tags

        resp = self._rpc("mb_search_memory", params)
        if resp.status_code != 200:
            logger.error("Memory search failed: %s", resp.text)
            return []

        results = resp.json()
        entries = []
        for r in results:
            entry = MemoryEntry(
                id=UUID(r["id"]),
                agent_id=UUID(r["agent_id"]),
                agent_name=r.get("agent_name"),
                memory_type=MemoryType(r["memory_type"]),
                scope=Scope(r["scope"]),
                content=r["content"],
                summary=r.get("summary"),
                tags=r.get("tags", []),
                namespace=r.get("namespace", "default"),
                metadata=r.get("metadata", {}),
                importance=r.get("importance", 0.5),
                similarity=r.get("similarity"),
                created_at=r.get("created_at"),
            )
            entries.append(entry)

            # Log access asynchronously (append-only, no row locks)
            self._log_access(entry.id)

        return entries

    def recall_all(
        self,
        query: str,
        *,
        limit: int = 10,
        threshold: float = 0.5,
    ) -> list[SearchResult]:
        """Unified search across agent memories AND RAG knowledge bases.

        Returns a mixed list of memory entries and RAG chunks,
        sorted by similarity.
        """
        embedding = get_embedding(query)
        if not embedding:
            return []

        resp = self._rpc(
            "mb_search_all",
            {
                "p_agent_id": str(self.agent_id),
                "p_query_embedding": embedding,
                "p_match_count": limit,
                "p_similarity_threshold": threshold,
            },
        )
        if resp.status_code != 200:
            logger.error("Unified search failed: %s", resp.text)
            return []

        return [
            SearchResult(
                result_type=r["result_type"],
                result_id=r["result_id"],
                agent_name=r.get("agent_name"),
                content=r["content"],
                similarity=r.get("similarity", 0.0),
                metadata=r.get("metadata", {}),
            )
            for r in resp.json()
        ]

    def forget(self, memory_id: UUID) -> bool:
        """Delete a memory entry (only own memories)."""
        resp = self._rest(
            "DELETE",
            "mb_memory",
            params={
                "id": f"eq.{memory_id}",
                "agent_id": f"eq.{self.agent_id}",
            },
        )
        return resp.status_code in (200, 204)

    def update_memory(
        self,
        memory_id: UUID,
        *,
        content: str | None = None,
        summary: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
        scope: Scope | None = None,
        metadata: dict | None = None,
        expires_at: datetime | None = None,
    ) -> bool:
        """Update fields on an existing memory (only own memories)."""
        data: dict = {"updated_at": "now()"}
        if content is not None:
            data["content"] = content
            data["embedding"] = get_embedding(content)
        if summary is not None:
            data["summary"] = summary
        if importance is not None:
            data["importance"] = importance
        if tags is not None:
            data["tags"] = tags
        if scope is not None:
            data["scope"] = scope.value
        if metadata is not None:
            data["metadata"] = metadata
        if expires_at is not None:
            data["expires_at"] = expires_at.isoformat()

        resp = self._rest(
            "PATCH",
            "mb_memory",
            data=data,
            params={
                "id": f"eq.{memory_id}",
                "agent_id": f"eq.{self.agent_id}",
            },
        )
        return resp.status_code in (200, 204)

    # ── Convenience methods for memory types ─────────────────────────

    def learn(self, fact: str, **kwargs) -> MemoryEntry:
        """Store a semantic memory (fact, learning, insight)."""
        return self.remember(fact, memory_type=MemoryType.SEMANTIC, **kwargs)

    def log_event(self, event: str, **kwargs) -> MemoryEntry:
        """Store an episodic memory (event, observation)."""
        return self.remember(event, memory_type=MemoryType.EPISODIC, **kwargs)

    def save_procedure(self, howto: str, **kwargs) -> MemoryEntry:
        """Store a procedural memory (workflow, how-to, recipe)."""
        return self.remember(howto, memory_type=MemoryType.PROCEDURAL, **kwargs)

    # ── RAG delegation (existing KnowledgeBase) ──────────────────────

    def search_knowledge(self, query: str, **kwargs) -> list[Chunk]:
        """Search RAG knowledge bases via the existing KnowledgeBase client."""
        return self._kb.search_semantic(query, **kwargs)

    def search_knowledge_hybrid(self, query: str, **kwargs) -> list[Chunk]:
        """Hybrid search on RAG knowledge bases."""
        return self._kb.search_hybrid(query, **kwargs)

    # ── Sharing & Access ─────────────────────────────────────────────

    def share_source(
        self,
        source_id: int,
        scope: Scope = Scope.GLOBAL,
        team_id: UUID | None = None,
    ) -> bool:
        """Share an existing RAG source with other agents.

        scope=GLOBAL makes it available to all agents.
        scope=TEAM requires a team_id.
        """
        data: dict = {
            "source_id": source_id,
            "scope": scope.value,
            "permission": "read",
            "granted_by": str(self.agent_id),
        }
        if scope == Scope.TEAM and team_id:
            data["team_id"] = str(team_id)

        resp = self._rest("POST", "mb_kb_access", data=data)
        return resp.status_code in (200, 201)

    def grant_source_access(
        self,
        source_id: int,
        agent_id: UUID,
        permission: str = "read",
    ) -> bool:
        """Grant a specific agent access to a RAG source."""
        data = {
            "source_id": source_id,
            "agent_id": str(agent_id),
            "scope": "private",
            "permission": permission,
            "granted_by": str(self.agent_id),
        }
        resp = self._rest("POST", "mb_kb_access", data=data)
        return resp.status_code in (200, 201)

    def bootstrap_access(self) -> int:
        """Grant this agent global access to ALL existing kb_sources.

        Useful during initial migration. Returns number of sources granted.
        """
        resp = self._rpc(
            "mb_bootstrap_agent_access",
            {"p_agent_id": str(self.agent_id)},
        )
        if resp.status_code == 200:
            result = resp.json()
            return result if isinstance(result, int) else 0
        return 0

    # ── Teams ────────────────────────────────────────────────────────

    def create_team(
        self,
        name: str,
        description: str = "",
    ) -> Team:
        """Create a new team and automatically join as admin."""
        data = {
            "name": name,
            "description": description,
            "created_by": str(self.agent_id),
        }
        resp = self._rest("POST", "mb_teams", data=data, prefer="return=representation")
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create team: {resp.text}")

        rows = resp.json()
        row = rows[0] if isinstance(rows, list) else rows
        team_id = UUID(row["id"])

        # Auto-join as admin
        self._rest(
            "POST",
            "mb_team_members",
            data={
                "team_id": str(team_id),
                "agent_id": str(self.agent_id),
                "role": "admin",
            },
        )

        return Team(
            id=team_id,
            name=name,
            description=description,
            created_by=self.agent_id,
        )

    def join_team(self, team_id: UUID, role: str = "member") -> bool:
        """Join an existing team."""
        resp = self._rest(
            "POST",
            "mb_team_members",
            data={
                "team_id": str(team_id),
                "agent_id": str(self.agent_id),
                "role": role,
            },
        )
        return resp.status_code in (200, 201)

    def list_teams(self) -> list[Team]:
        """List teams this agent belongs to."""
        resp = self._rest(
            "GET",
            "mb_team_members",
            params={
                "agent_id": f"eq.{self.agent_id}",
                "select": "team_id,role,mb_teams(id,name,description,created_at)",
            },
        )
        if resp.status_code != 200:
            return []

        teams = []
        for row in resp.json():
            t = row.get("mb_teams", {})
            if t:
                teams.append(Team(
                    id=UUID(t["id"]),
                    name=t["name"],
                    description=t.get("description"),
                    created_at=t.get("created_at"),
                ))
        return teams

    # ── Stats ────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Get memory stats for this agent."""
        resp = self._rpc("mb_agent_stats", {"p_agent_id": str(self.agent_id)})
        if resp.status_code == 200:
            result = resp.json()
            if result:
                return result[0] if isinstance(result, list) else result
        return {}

    # ── Internal ─────────────────────────────────────────────────────

    def _log_access(self, memory_id: UUID) -> None:
        """Log a memory access (append-only, no row locks on mb_memory)."""
        try:
            self._rpc(
                "mb_log_access",
                {
                    "p_memory_id": str(memory_id),
                    "p_agent_id": str(self.agent_id),
                },
            )
        except Exception:
            # Non-critical: access logging should never break recall
            pass
