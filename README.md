# OpenClaw Knowledgebase

A self-hosted RAG system with **multi-agent shared memory**. Uses Ollama for local embeddings and Supabase/pgvector for vector storage.

100% local. 100% free. No OpenAI API needed.

## What it does

- **RAG Pipeline** — Crawl URLs, upload documents (PDF, Word, Excel, etc.), chunk text, generate embeddings, and search by semantic similarity
- **Multi-Agent Memory** — Agents register with unique identities, store memories (episodic, semantic, procedural), and share knowledge across teams
- **Unified Search** — Query both agent memories and RAG knowledge bases in a single call
- **Scoped Access** — Private, team, and global visibility controls with Row-Level Security

## Architecture

```
┌──────────────────────────────────────────┐
│           OpenClaw Agents                │
│  agent-a         agent-b       agent-c   │
└─────┬──────────────┬──────────────┬──────┘
      │              │              │
      ▼              ▼              ▼
┌──────────────────────────────────────────┐
│          AgentMemory (Python)            │
│  remember() / recall() / recall_all()    │
│  ┌──────────────┐  ┌──────────────────┐  │
│  │  mb_memory   │  │  KnowledgeBase   │  │
│  │  (agent mem) │  │  (RAG chunks)    │  │
│  └──────┬───────┘  └────────┬─────────┘  │
└─────────┼────────────────────┼───────────┘
          │                    │
   ┌──────▼────────────────────▼──────┐
   │      Supabase + pgvector         │
   │  mb_agents │ mb_memory │ mb_teams│
   │  kb_sources│ kb_chunks │ RLS     │
   └──────────────────┬───────────────┘
                      │
               ┌──────▼──────┐
               │   Ollama    │
               │  (embeddings│
               │   768-dim)  │
               └─────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) running locally
- [Supabase](https://supabase.com) (self-hosted or cloud) with pgvector

### Install

```bash
git clone https://github.com/openclaw/openclaw-knowledgebase.git
cd openclaw-knowledgebase

# Install with uv (recommended)
uv sync

# Or with pip (pick what you need)
pip install -e ".[all]"    # everything
pip install -e ".[web]"    # web UI only
pip install -e ".[docling]" # PDF/Office parsing
pip install -e ".[crawl]"  # web crawling
```

### Setup

```bash
# 1. Pull the embedding model
ollama pull nomic-embed-text

# 2. Configure environment
cp .env.example .env
# Edit .env with your Supabase URL and key

# 3. Apply database schema (in Supabase SQL Editor)
#    Run schema.sql first, then schema_memory.sql

# 4. Bootstrap an agent (validates, registers, tests)
python3 skills/bootstrap/bootstrap.py all

# 5. Start the web UI
kb serve
```

## Agent Memory (Multi-Agent)

Register agents, store memories with scoping, and share knowledge:

```python
from knowledgebase.memory import AgentMemory, Scope, MemoryType

agent = AgentMemory("my-agent", api_key="oc_sk_...")
agent.authenticate()

# Store memories with different types and scopes
agent.learn("API v3 requires OAuth2", scope=Scope.GLOBAL, tags=["api"])
agent.log_event("Deploy succeeded at 14:30", scope=Scope.TEAM)
agent.save_procedure("To deploy: tag → CI → approve → merge", scope=Scope.TEAM)

# Search agent memories
results = agent.recall("API authentication")

# Unified search: memories + RAG knowledge bases
combined = agent.recall_all("deployment process")

# Share RAG sources with all agents
agent.share_source(source_id=42, scope=Scope.GLOBAL)

# Teams
team = agent.create_team("backend", description="Backend team")
agent.join_team(team.id)
```

### Memory Types

| Type | Use for | Example |
|------|---------|---------|
| `semantic` | Facts, learnings, knowledge | "The payments API uses OAuth2" |
| `episodic` | Events, observations | "Deploy failed at 14:30 due to timeout" |
| `procedural` | Workflows, how-tos | "To reset the cache: ssh → systemctl restart redis" |

### Scopes

| Scope | Visible to |
|-------|-----------|
| `private` | Only the owning agent |
| `team` | Agents in shared teams |
| `global` | All registered agents |

## RAG Pipeline

The original knowledgebase functionality works standalone or alongside agent memory:

```python
from knowledgebase import KnowledgeBase, search, search_hybrid

# Quick search
results = search("home assistant automation", limit=5)

# Hybrid search (semantic + keyword)
results = search_hybrid("zigbee pairing", limit=5)

# Full client
kb = KnowledgeBase()
source = kb.add_source(url="https://docs.example.com", title="Docs")
kb.add_chunk(source_id=source.id, content="...", chunk_index=0)
```

## CLI

```bash
kb status              # Check connections and stats
kb find "query"        # Semantic search
kb find "query" --hybrid   # Hybrid search
kb sources             # List all sources
kb embed               # Generate embeddings for new chunks
kb providers           # List available embedding providers
kb serve               # Start web UI on port 8080
kb serve -p 3000       # Custom port
```

## Web UI

Start with `kb serve` and open http://localhost:8080.

- **Dashboard** — Stats, connection status, recent sources
- **Search** — Live semantic search with hybrid mode
- **Sources** — Browse and manage ingested content
- **Add Knowledge** — Crawl URLs or upload documents

### API Endpoints

```
GET  /api/health          # Health check
GET  /api/search?q=...    # Search (supports hybrid, limit params)
GET  /api/stats           # Knowledgebase statistics
GET  /api/sources         # List sources
DELETE /api/sources/{id}  # Delete a source
POST /api/crawl           # Crawl a URL (form: url, max_depth, title)
POST /api/upload          # Upload a document (form: file, title)
GET  /api/jobs            # List background jobs
GET  /api/jobs/{id}       # Job status
```

## Supported Formats

**Native** (no extra dependencies): TXT, Markdown, RST, JSON, YAML, CSV, TSV

**With Docling** (`pip install .[docling]`): PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML

**Web Crawling** (`pip install .[crawl]`): Recursive crawling with depth control, rate limiting, same-domain restriction

## Configuration

Environment variables (`.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase REST API URL | Required |
| `SUPABASE_KEY` | Supabase service_role key | Required |
| `TABLE_PREFIX` | Table name prefix | `kb` |
| `EMBEDDING_PROVIDER` | Provider: ollama, google, openai, custom | `ollama` |
| `EMBEDDING_MODEL` | Model name (provider-specific) | `nomic-embed-text` |
| `EMBEDDING_DIMENSIONS` | Vector dimensions | `768` |
| `EMBEDDING_TIMEOUT` | Request timeout (seconds) | `120` |
| `OLLAMA_URL` | Ollama API URL | `http://localhost:11434` |
| `GOOGLE_API_KEY` | Google AI API key | — |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL | `https://api.openai.com/v1` |
| `LOG_LEVEL` | Logging level: DEBUG, INFO, WARNING, ERROR | `INFO` |
| `LOG_FORMAT` | Log output: rich, json, plain | `rich` |
| `CHUNK_SIZE` | Characters per chunk | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `200` |
| `OPENCLAW_AGENT_NAME` | Agent identity (for memory module) | Auto-generated |
| `OPENCLAW_AGENT_KEY` | Agent API key (for memory module) | Generated on bootstrap |

## Database Schema

Both schema files must be applied in order via the Supabase SQL Editor:

1. `schema.sql` — RAG tables, HNSW vector index, search functions
2. `schema_memory.sql` — Multi-agent memory tables, RLS policies, memory RPC functions

Extensions (`vector`, `pgcrypto`) are created in the `extensions` schema (Supabase default). All RPC functions use `SECURITY DEFINER` and `SET search_path = public, extensions` to ensure correct function resolution and prevent search_path injection.

### RAG Tables (`kb_*`)

```sql
kb_sources (id, url, title, source_type, metadata, created_at)
kb_chunks  (id, source_id, url, chunk_index, content, embedding vector(768))
```

Vector index: **HNSW** (`vector_cosine_ops`) — better recall than ivfflat, no rebuild needed as data grows.

### Memory Tables (`mb_*`)

```sql
mb_agents            (id, name, agent_type, api_key_hash, metadata, is_active, last_seen_at)
mb_memory            (id, agent_id, memory_type, scope, content, embedding, tags[], namespace, importance, expires_at)
mb_teams             (id, name, description, created_by)
mb_team_members      (team_id, agent_id, role)
mb_kb_access         (source_id, agent_id, team_id, scope, permission)
mb_memory_access_log (memory_id, agent_id, accessed_at)  -- append-only, aggregated via cron
```

Row-Level Security is enabled on `mb_memory` and `kb_chunks`. Agents see their own private memories, team memories via shared teams, and all global memories.

### RPC Functions

All functions use ANN search via HNSW index (CTE with `ORDER BY <=> LIMIT` before filtering) for optimal performance.

| Function | Purpose |
|----------|---------|
| `kb_search_semantic()` | Vector similarity search on RAG chunks |
| `kb_search_hybrid()` | Combined semantic + keyword search |
| `kb_stats()` | Source and chunk counts |
| `mb_register_agent()` | Register a new agent (bcrypt key hash via pgcrypto) |
| `mb_authenticate_agent()` | Validate agent API key |
| `mb_search_memory()` | Search agent memories with scope/type/tag filtering |
| `mb_search_all()` | Unified search across memories + RAG |
| `mb_bootstrap_agent_access()` | Grant agent global access to all existing sources |
| `mb_log_access()` | Append-only memory access log (no row locks) |
| `mb_aggregate_access_counts()` | Batch update access_count from log (cron job) |
| `mb_purge_expired()` | Delete memories past their expires_at |
| `mb_agent_stats()` | Per-agent stats (memories, sources, teams) |

## Agent Bootstrap (Skill)

New agents can self-configure by reading `skills/bootstrap/instructions.md`:

```bash
python3 skills/bootstrap/bootstrap.py all
```

This validates the environment, applies schemas, registers the agent, grants RAG access, and runs a smoke test.

## Embedding Providers

Set `EMBEDDING_PROVIDER` in `.env` to switch providers. Each provider has its own configuration.

### Ollama (default, local)

```env
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
OLLAMA_URL=http://localhost:11434
```

| Model | Dimensions | Speed | Notes |
|-------|-----------|-------|-------|
| `nomic-embed-text` | 768 | Fast | **Default**, best balance |
| `mxbai-embed-large` | 1024 | Medium | Higher quality |
| `all-minilm` | 384 | Fastest | Lightweight |

### Google AI

```env
EMBEDDING_PROVIDER=google
EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIMENSIONS=768
GOOGLE_API_KEY=AIza...
```

Google's `text-embedding-004` supports configurable output dimensions (default 768). Free tier includes 1,500 requests/minute.

### OpenAI

```env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
OPENAI_API_KEY=sk-...
```

| Model | Dimensions | Notes |
|-------|-----------|-------|
| `text-embedding-3-small` | 1536 | Cost-effective |
| `text-embedding-3-large` | 3072 | Highest quality |

Both support `EMBEDDING_DIMENSIONS` to reduce output size (e.g. 768 for schema compatibility).

### Custom (OpenAI-compatible)

Any API that implements the OpenAI `/v1/embeddings` endpoint (vLLM, LiteLLM, LocalAI, etc.):

```env
EMBEDDING_PROVIDER=custom
EMBEDDING_MODEL=your-model
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=http://localhost:8000/v1
```

### Important: Changing providers

- Changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS` requires re-embedding all existing content (`kb embed`)
- If the new dimensions differ from 768, the `vector(768)` columns in `schema.sql` and `schema_memory.sql` must be altered manually
- Embeddings from different models are **not compatible** — you cannot mix providers within the same table

## License

MIT License - see [LICENSE](LICENSE)

## Credits

- [Ollama](https://ollama.ai) — Local LLM inference
- [Supabase](https://supabase.com) — Postgres + pgvector
- [Docling](https://github.com/DS4SD/docling) — Document parsing (IBM)
- [HTMX](https://htmx.org) — Web UI interactions
- [Tailwind CSS](https://tailwindcss.com) — Styling

---

Built by the OpenClaw community
